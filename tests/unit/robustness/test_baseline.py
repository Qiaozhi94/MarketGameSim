"""T002 (方法论 §9.4/§10.3): baseline-freeze tests.

Positive + negative + multi-record cases per CLAUDE.md: stable id for
identical content, different id when any field changes, and fail-closed
refusal to overwrite a different baseline.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.experiment.config import ExperimentConfig
from market_game_sim.robustness.baseline import (
    BaselineError,
    BaselineFrozen,
    baseline_id,
    build_baseline,
    freeze_baseline,
    git_head_commit,
)


def _config() -> ExperimentConfig:
    return ExperimentConfig(
        seed=1,
        max_transactions=30000,
        agent_specs=[AgentSpec(agent_id="a1", role="retail", observe_interval_ns=1, latency_ns=1)],
    )


class TestGitHeadCommit:
    def test_returns_sha(self, tmp_path):
        import subprocess

        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "t"], check=True)
        (tmp_path / "f").write_text("x", encoding="utf-8")
        subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "c"], check=True)
        sha = git_head_commit(tmp_path)
        assert len(sha) >= 7

    def test_non_repo_returns_unknown(self, tmp_path):
        assert git_head_commit(tmp_path) == "unknown"


class TestBaselineId:
    def test_stable_for_identical(self):
        b1 = BaselineFrozen("abc123", "hash1", "three-zone", (1, 2, 3), "linear", ("KPI-005",))
        b2 = BaselineFrozen("abc123", "hash1", "three-zone", (1, 2, 3), "linear", ("KPI-005",))
        assert baseline_id(b1) == baseline_id(b2)

    def test_changes_on_any_field(self):
        base = BaselineFrozen("abc123", "hash1", "three-zone", (1, 2, 3), "linear", ("KPI-005",))
        variants = [
            BaselineFrozen("def456", "hash1", "three-zone", (1, 2, 3), "linear", ("KPI-005",)),
            BaselineFrozen("abc123", "hash2", "three-zone", (1, 2, 3), "linear", ("KPI-005",)),
            BaselineFrozen("abc123", "hash1", "three-zone", (1, 2, 4), "linear", ("KPI-005",)),
            BaselineFrozen("abc123", "hash1", "three-zone", (1, 2, 3), "threshold", ("KPI-005",)),
            BaselineFrozen(
                "abc123", "hash1", "three-zone", (1, 2, 3), "linear", ("KPI-005", "KPI-011")
            ),
        ]
        ids = {baseline_id(v) for v in variants}
        assert baseline_id(base) not in ids
        assert len(ids) == len(variants)


class TestBuildBaseline:
    def test_captures_config_hash(self):
        cfg = _config()
        b = build_baseline(cfg, repo_root=pathlib.Path(__file__).resolve().parents[3])
        assert b.config_hash  # non-empty
        assert b.behavior_mapping == "linear"
        assert b.protocol == "three-zone"
        assert "KPI-005" in b.metric_definitions

    def test_config_hash_matches_compute(self):
        from market_game_sim.experiment.config import compute_config_hash

        cfg = _config()
        b = build_baseline(cfg, repo_root=pathlib.Path(__file__).resolve().parents[3])
        assert b.config_hash == compute_config_hash(cfg)


class TestFreezeBaseline:
    def test_writes_and_returns_id(self, tmp_path):
        b = BaselineFrozen("abc123", "hash1", "three-zone", (1, 2, 3), "linear", ("KPI-005",))
        path = tmp_path / "baseline.json"
        bid = freeze_baseline(b, path)
        assert bid == baseline_id(b)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["baseline_id"] == bid

    def test_idempotent_same_content(self, tmp_path):
        b = BaselineFrozen("abc123", "hash1", "three-zone", (1, 2, 3), "linear", ("KPI-005",))
        path = tmp_path / "baseline.json"
        freeze_baseline(b, path)
        freeze_baseline(b, path)  # identical content -> no error
        assert path.exists()

    def test_refuses_overwrite_different_baseline(self, tmp_path):
        path = tmp_path / "baseline.json"
        freeze_baseline(
            BaselineFrozen("abc123", "hash1", "three-zone", (1, 2, 3), "linear", ("KPI-005",)),
            path,
        )
        other = BaselineFrozen("def456", "hash2", "three-zone", (1, 2, 3), "linear", ("KPI-005",))
        with pytest.raises(BaselineError, match="refusing to overwrite"):
            freeze_baseline(other, path)

    def test_force_overwrites(self, tmp_path):
        path = tmp_path / "baseline.json"
        freeze_baseline(
            BaselineFrozen("abc123", "hash1", "three-zone", (1, 2, 3), "linear", ("KPI-005",)),
            path,
        )
        other = BaselineFrozen("def456", "hash2", "three-zone", (1, 2, 3), "linear", ("KPI-005",))
        bid = freeze_baseline(other, path, force=True)
        assert bid == baseline_id(other)
