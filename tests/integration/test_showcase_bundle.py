"""AC-011 (T203 / FR-027): single-command showcase bundle (R1 gate).

Drives the real pipeline (run_one -> raw log -> build_replay -> summary ->
manifest) through ``build_showcase_bundle`` into a temp dir and asserts the
five fixed bundle files exist and carry the required provenance + the
mandatory ``不可作结论`` disclaimer.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from market_game_sim import __version__
from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.experiment.config import ExperimentConfig, compute_config_hash
from market_game_sim.showcase.generate import build_showcase_bundle
from market_game_sim.showcase.manifest import (
    ShowcaseManifestError,
    validate_showcase_manifest,
)
from market_game_sim.showcase.summary import DISCLAIMER, assert_disclaimer_present

REBUILD_CMD = "python -m market_game_sim.showcase.generate <config.yaml>"


def _mm_spec() -> AgentSpec:
    return AgentSpec(
        agent_id="mm-0",
        role="inventory_market_maker",
        observe_interval_ns=100_000_000,
        latency_ns=5_000_000,
        is_market_maker=True,
        half_spread_ticks=5,
        quote_size=10_000,
        max_inventory=100_000,
        inventory_skew_k_bp=10_000,
    )


def _belief_spec() -> AgentSpec:
    return AgentSpec(
        agent_id="agent-0",
        role="retail",
        observe_interval_ns=1_000_000_000,
        latency_ns=50_000_000,
        leverage_tier=10,
        aggressiveness_bp=5_000,
        max_order_qty=5_000,
    )


def _small_config() -> ExperimentConfig:
    return ExperimentConfig(
        seed=1,
        max_transactions=60,
        agent_specs=[_mm_spec(), _belief_spec()],
        agent_signals={"agent-0": 10_000},
    )


def _blake2b_hex(data: bytes) -> str:
    h = hashlib.blake2b(digest_size=32)
    h.update(data)
    return h.hexdigest()


def test_showcase_bundle_produces_five_files(tmp_path):
    config = _small_config()
    result = build_showcase_bundle(
        config,
        tmp_path,
        tick_size="0.01",
        min_quantity="0.001",
        cash_unit="0.01",
        gate="R1",
        rebuild_command=REBUILD_CMD,
    )

    for name in ("run.jsonl", "replay.html", "summary.md", "RUN.md", "manifest.json"):
        assert (tmp_path / name).is_file(), f"missing bundle file: {name}"

    assert result["terminated"] == "COMPLETED"
    assert result["run_id"] == f"exp-s{config.seed}"


def test_manifest_carries_provenance_and_hashes(tmp_path):
    config = _small_config()
    build_showcase_bundle(
        config,
        tmp_path,
        tick_size="0.01",
        min_quantity="0.001",
        cash_unit="0.01",
        gate="R1",
        rebuild_command=REBUILD_CMD,
    )

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))

    # Fixed provenance fields.
    assert manifest["evidence_class"] == "engineering-demonstration"
    assert manifest["code_version"] == __version__
    assert manifest["config_hash"] == compute_config_hash(config)
    assert manifest["seed"] == config.seed
    assert manifest["gate"] == "R1"
    assert manifest["manifest_version"] == 1

    # 4 non-manifest bundle files declared, each with a real blake2b hash.
    entries = {e["artifact_id"]: e for e in manifest["artifacts"]}
    assert set(entries) == {"run_log", "replay", "summary", "run_doc"}
    for entry in entries.values():
        assert entry["hash_algorithm"] == "blake2b"
        assert entry["producer"] == "0.1.5 T203"
        actual = _blake2b_hex((tmp_path / entry["path"]).read_bytes())
        assert actual == entry["hash"], f"hash mismatch for {entry['path']}"

    # The manifest itself validates against the showcase schema.
    validate_showcase_manifest(manifest)


def test_summary_carries_not_a_conclusion_disclaimer(tmp_path):
    config = _small_config()
    build_showcase_bundle(
        config,
        tmp_path,
        tick_size="0.01",
        min_quantity="0.001",
        cash_unit="0.01",
        gate="R1",
        rebuild_command=REBUILD_CMD,
    )

    text = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert DISCLAIMER in text
    assert "不可作结论" in text
    assert "engineering-demonstration" in text


def test_replay_is_offline_single_file(tmp_path):
    config = _small_config()
    build_showcase_bundle(
        config,
        tmp_path,
        tick_size="0.01",
        min_quantity="0.001",
        cash_unit="0.01",
        gate="R1",
        rebuild_command=REBUILD_CMD,
    )

    html = (tmp_path / "replay.html").read_text(encoding="utf-8")
    assert html.count("<html") == 1
    assert "replay-data" in html
    assert "fetch(" not in html
    assert "http://" not in html
    assert "https://" not in html
    assert "cdn" not in html.lower()


def test_run_md_references_rebuild_command(tmp_path):
    config = _small_config()
    build_showcase_bundle(
        config,
        tmp_path,
        tick_size="0.01",
        min_quantity="0.001",
        cash_unit="0.01",
        gate="R1",
        rebuild_command=REBUILD_CMD,
    )

    text = (tmp_path / "RUN.md").read_text(encoding="utf-8")
    assert REBUILD_CMD in text
    assert "engineering-demonstration" in text
    assert "R5/T220" in text or "R5" in text


def test_raw_log_is_replay_readable(tmp_path):
    config = _small_config()
    build_showcase_bundle(
        config,
        tmp_path,
        tick_size="0.01",
        min_quantity="0.001",
        cash_unit="0.01",
        gate="R1",
        rebuild_command=REBUILD_CMD,
    )

    # The raw log must round-trip through the replay reader (offline reader
    # validates RUN_HEADER/EVENT/RUN_TRAILER structure + record_count).
    from market_game_sim.replay.reader import read_log

    log = read_log(tmp_path / "run.jsonl")
    assert log.run_id == f"exp-s{config.seed}"
    assert len(log.events) > 0


def test_disclaimer_guard_rejects_missing_disclaimer():
    # FR-027: generation must fail if the disclaimer is absent. A summary
    # missing it must never be shippable.
    with pytest.raises(ValueError, match="不可作结论"):
        assert_disclaimer_present("no disclaimer here")


def test_manifest_rejects_wrong_evidence_class():
    bad = {
        "manifest_version": 1,
        "artifact_root": ".",
        "artifacts": [],
        "code_version": "0.1.0",
        "config_hash": "abc",
        "seed": 1,
        "evidence_class": "bogus-class",
        "gate": "R1",
    }
    with pytest.raises(ShowcaseManifestError, match="evidence_class"):
        validate_showcase_manifest(bad)


def test_manifest_rejects_missing_top_level_field():
    bad = {
        "manifest_version": 1,
        "artifact_root": ".",
        "artifacts": [],
        "code_version": "0.1.0",
        "config_hash": "abc",
        "seed": 1,
        "evidence_class": "engineering-demonstration",
    }
    with pytest.raises(ShowcaseManifestError, match="top-level fields mismatch"):
        validate_showcase_manifest(bad)


# --------------------------------------------------------------------------- #
# R018-C012 regression: the showcase manifest records the frozen seed_plan
# (not just the scalar seed) so provenance states the bundle's place in it.
# --------------------------------------------------------------------------- #


def test_manifest_records_closed_seed_plan(tmp_path):
    config = _small_config()
    config.seed_plan = {"n_seeds": 8, "cells": ["L_low_M_low", "L_high_M_high"]}
    build_showcase_bundle(
        config,
        tmp_path,
        tick_size="0.01",
        min_quantity="0.001",
        cash_unit="0.01",
        gate="R1",
        rebuild_command=REBUILD_CMD,
    )
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["seed_plan"] == {
        "n_seeds": 8,
        "cells": ["L_low_M_low", "L_high_M_high"],
    }
    assert manifest["seed"] == config.seed
    # The optional field validates when present.
    validate_showcase_manifest(manifest)


def test_manifest_without_seed_plan_still_valid(tmp_path):
    """seed_plan is optional: a bundle without one (scalar seed only) is a
    valid manifest -- existing single-seed showcases keep working."""
    config = _small_config()
    build_showcase_bundle(
        config,
        tmp_path,
        tick_size="0.01",
        min_quantity="0.001",
        cash_unit="0.01",
        gate="R1",
        rebuild_command=REBUILD_CMD,
    )
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert "seed_plan" not in manifest
    validate_showcase_manifest(manifest)
