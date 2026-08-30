"""T215: resumable, twice-run formal flagship execution."""

from __future__ import annotations

import dataclasses
import gzip
import json
from pathlib import Path

import pytest

from market_game_sim.experiment.factorial import FactorialSeedPlan, load_factorial_plan
from market_game_sim.experiment.runner import RunResult
from market_game_sim.metrics.liquidation import LiquidationMetrics, RunClassification
from market_game_sim.showcase import formal

ROOT = Path(__file__).resolve().parents[2]
REAL_PLAN = ROOT / "docs" / "experiments" / "0.1.5-factorial-plan.json"


def _result(config) -> RunResult:
    return RunResult(
        seed=config.seed,
        terminated="COMPLETED",
        abort_code=None,
        events=[
            {"event_type": "TRADE_SETTLE", "timestamp": 10, "price_ticks": 10_001},
            {"event_type": "RUN_BOUNDARY", "timestamp": 100},
        ],
        book_last_ticks=10_001,
        accounts={},
        liquidation_metrics=LiquidationMetrics(),
        classification=RunClassification(),
        group_label=config.group_label,
    )


def _small_binding():
    binding = load_factorial_plan(REAL_PLAN)
    return dataclasses.replace(
        binding,
        seed_plan=FactorialSeedPlan(
            planned_seeds=(30_000,), reserve_seeds=(), minimum_valid_blocks=1
        ),
    )


def test_formal_runner_executes_primary_and_ti2_rerun_then_resumes(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(formal, "load_factorial_plan", lambda _path: _small_binding())

    def fake_run(config):
        calls.append((config.seed, config.group_label))
        return _result(config)

    monkeypatch.setattr(formal, "run_one", fake_run)
    first = formal.run_formal_experiment(
        tmp_path,
        plan_path=REAL_PLAN,
        bootstrap_resamples=10,
        sign_flip_resamples=20,
    )
    assert len(calls) == 16  # 8 primary + 8 deterministic reruns
    assert first["complete"] is True
    assert first["valid_seeds"] == [30_000]
    assert first["analysis"].is_file()
    assert first["manifest"].is_file()

    second = formal.run_formal_experiment(
        tmp_path,
        plan_path=REAL_PLAN,
        bootstrap_resamples=10,
        sign_flip_resamples=20,
    )
    assert len(calls) == 16, "resume must not execute an already checkpointed block"
    assert second["new_blocks"] == 0
    assert second["complete"] is True

    progress = json.loads((tmp_path / formal.PROGRESS_NAME).read_text(encoding="utf-8"))
    assert progress["evidence_class"] == "formal-research"
    assert progress["run_family"] == "SPONTANEOUS"
    assert progress["inference_eligible"] is True
    checkpoint = formal._read_checkpoint(
        tmp_path / formal.CHECKPOINT_DIR_NAME / "seed-30000.json.gz"
    )
    for model_id, cells in checkpoint["audit_event_summary_sha256"].items():
        for cell_id, audit_digest in cells.items():
            assert (
                audit_digest
                == checkpoint["primary_runs"][model_id][cell_id]["event_summary_sha256"]
            )


def test_operational_pause_writes_ineligible_progress_without_analysis(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        formal, "run_one", lambda config: calls.append(config.seed) or _result(config)
    )
    result = formal.run_formal_experiment(
        tmp_path,
        plan_path=REAL_PLAN,
        max_new_blocks=1,
    )
    assert len(calls) == 16
    assert result["executed_seeds"] == [30_000]
    assert result["complete"] is False
    assert result["analysis"] is None
    assert result["manifest"] is None
    progress = json.loads(result["progress"].read_text(encoding="utf-8"))
    assert progress["stopping_rule_reached"] is False
    assert progress["inference_eligible"] is False


def test_checkpoint_digest_tampering_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(formal, "load_factorial_plan", lambda _path: _small_binding())
    monkeypatch.setattr(formal, "run_one", _result)
    formal.run_formal_experiment(
        tmp_path,
        plan_path=REAL_PLAN,
        bootstrap_resamples=10,
        sign_flip_resamples=20,
    )
    checkpoint = tmp_path / formal.CHECKPOINT_DIR_NAME / "seed-30000.json.gz"
    with gzip.open(checkpoint, "rb") as stream:
        envelope = json.loads(stream.read().decode("utf-8"))
    envelope["body"]["seed"] = 30_001
    with gzip.open(checkpoint, "wb") as stream:
        stream.write(json.dumps(envelope).encode("utf-8"))
    with pytest.raises(formal.FormalRunError, match="body digest mismatch"):
        formal.run_formal_experiment(
            tmp_path,
            plan_path=REAL_PLAN,
            bootstrap_resamples=10,
            sign_flip_resamples=20,
        )


def test_formal_runner_refuses_committed_experiment_directory(tmp_path):
    with pytest.raises(formal.FormalRunError, match="docs/experiments"):
        formal.run_formal_experiment(
            tmp_path / "docs" / "experiments" / "raw",
            plan_path=REAL_PLAN,
            max_new_blocks=1,
        )


def test_max_new_blocks_must_be_positive(tmp_path):
    with pytest.raises(formal.FormalRunError, match="positive integer"):
        formal.run_formal_experiment(tmp_path, plan_path=REAL_PLAN, max_new_blocks=0)
