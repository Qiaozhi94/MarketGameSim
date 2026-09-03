"""T214 [成果门:R3] (FR-024/FR-027, AC-006/AC-007): experiment-preview bundle.

Drives the real preview pipeline (load_factorial_plan -> build_preview_configs
-> run_one x 8 per seed -> analyze_flagship_results -> comparison.json +
summary.md + representative replay + manifest) through
``generate_preview_bundle`` into a temp dir and asserts the fixed bundle file
set, the ``experiment-preview`` scoping (fail-closed refusal of formal
conclusion wording), offline replay readability and the closed manifest.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from market_game_sim import __version__
from market_game_sim.experiment.factorial import load_factorial_plan, validate_flagship_configs
from market_game_sim.replay.reader import read_log
from market_game_sim.showcase.manifest import validate_showcase_manifest
from market_game_sim.showcase.preview import (
    LOG_NAME,
    MANIFEST_NAME,
    PRODUCER,
    REFUSAL_STATEMENT,
    REPLAY_NAME,
    REQUIRED_PREVIEW_SECTIONS,
    RUN_DOC_NAME,
    SUMMARY_NAME,
    PreviewError,
    _assert_required_sections,
    _combined_config_hash,
    build_preview_configs,
    generate_preview_bundle,
)
from market_game_sim.showcase.summary import DISCLAIMER

ROOT = Path(__file__).resolve().parents[2]
REAL_PLAN = ROOT / "docs" / "experiments" / "0.1.5-factorial-plan.json"
REPRESENTATIVE_RUN_ID = "exp-s40000"
REPRESENTATIVE_LABEL = "risk_budget_linear_v1/LL"


@pytest.fixture(scope="module")
def binding():
    return load_factorial_plan(REAL_PLAN)


@pytest.fixture(scope="module")
def preview(tmp_path_factory):
    out = tmp_path_factory.mktemp("preview_r3")
    return generate_preview_bundle(
        out,
        plan_path=REAL_PLAN,
        n_seeds=1,
        bootstrap_resamples=20,
        sign_flip_resamples=50,
    )


def _blake2b_hex(data: bytes) -> str:
    h = hashlib.blake2b(digest_size=32)
    h.update(data)
    return h.hexdigest()


def test_preview_bundle_produces_fixed_file_set(preview):
    out = preview["out_dir"]
    for name in (
        "comparison.json",
        LOG_NAME,
        REPLAY_NAME,
        SUMMARY_NAME,
        RUN_DOC_NAME,
        MANIFEST_NAME,
    ):
        assert (out / name).is_file(), f"missing bundle file: {name}"
    assert preview["evidence_class"] == "experiment-preview"
    assert preview["gate"] == "R3"
    assert preview["executed_seeds"] == [40_000]
    assert preview["valid_seeds"] == [40_000]
    assert preview["excluded_seed_blocks"] == {}


def test_manifest_marks_experiment_preview_with_executed_seed_plan(preview):
    out = preview["out_dir"]
    manifest = json.loads((out / MANIFEST_NAME).read_text(encoding="utf-8"))

    assert manifest["evidence_class"] == "experiment-preview"
    assert manifest["run_mode"] == "research"
    assert manifest["gate"] == "R3"
    assert manifest["manifest_version"] == 1
    assert manifest["code_version"] == __version__
    assert manifest["seed"] == 40_000
    assert manifest["seed_plan"] == {"n_seeds": 1, "seeds": [40_000]}

    entries = {e["artifact_id"]: e for e in manifest["artifacts"]}
    assert set(entries) == {"comparison", "replay_log", "replay", "summary", "run_doc"}
    for entry in entries.values():
        assert entry["hash_algorithm"] == "blake2b"
        assert entry["producer"] == PRODUCER
        actual = _blake2b_hex((out / entry["path"]).read_bytes())
        assert actual == entry["hash"], f"hash mismatch for {entry['path']}"

    validate_showcase_manifest(manifest)


def test_manifest_config_hash_covers_all_eight_cell_configs(preview, binding):
    manifest = json.loads((preview["out_dir"] / MANIFEST_NAME).read_text(encoding="utf-8"))
    configs = build_preview_configs(40_000, binding)
    fingerprints = validate_flagship_configs(configs, binding)
    expected = _combined_config_hash({40_000: fingerprints})
    assert manifest["config_hash"] == expected

    all_hashes = [h for cell_hashes in fingerprints.values() for h in cell_hashes.values()]
    assert len(set(all_hashes)) == 8, "each model x cell config must be individually traceable"


def test_summary_carries_required_sections_and_refusal(preview):
    text = (preview["out_dir"] / SUMMARY_NAME).read_text(encoding="utf-8")
    for section in REQUIRED_PREVIEW_SECTIONS:
        assert section in text, f"summary missing required section: {section}"
    assert DISCLAIMER in text
    assert REFUSAL_STATEMENT in text
    assert "experiment-preview" in text
    assert "formal-research" in text
    assert REPRESENTATIVE_LABEL in text
    # Significance machinery stays in comparison.json's rehearsal block only.
    assert "p_value" not in text
    assert "bh_significant" not in text


def test_comparison_json_scopes_preview_ineligible(preview):
    data = json.loads((preview["out_dir"] / "comparison.json").read_text(encoding="utf-8"))

    assert data["schema_version"] == 1
    assert data["evidence_class"] == "experiment-preview"
    assert data["gate"] == "R3"
    assert data["plan"]["preregistration_path"] == "docs/experiments/0.1.5-preregistration.md"

    scope = data["preview"]
    assert scope["executed_seeds"] == [40_000]
    assert scope["valid_seeds"] == [40_000]
    assert scope["excluded_seed_blocks"] == {}
    assert scope["frozen_minimum_valid_blocks"] == 128
    assert scope["evidence_sufficient"] is False
    assert scope["inference_eligible"] is False
    assert scope["refusal"] == REFUSAL_STATEMENT

    rehearsal = data["factorial_rehearsal"]["report"]
    assert set(rehearsal["endpoint_families"]) == {"crash", "surge", "liquidity_drought"}
    for family in rehearsal["endpoint_families"].values():
        assert family["bh_family_size"] == 12
    assert set(rehearsal["direction_asymmetry"]) == {
        "risk_budget_linear_v1",
        "risk_budget_threshold_v1",
    }

    means = data["cell_endpoint_means"]
    assert set(means) == {"crash", "surge", "liquidity_drought"}
    for family in means.values():
        assert set(family) == {"risk_budget_linear_v1", "risk_budget_threshold_v1"}
        for model in family.values():
            assert set(model) == {"LL", "LH", "HL", "HH"}
            for cell in model.values():
                assert cell["n_runs"] == 1


def test_replay_is_offline_single_file(preview):
    html = (preview["out_dir"] / REPLAY_NAME).read_text(encoding="utf-8")
    assert html.count("<html") == 1
    assert "replay-data" in html
    assert "fetch(" not in html
    assert "http://" not in html
    assert "https://" not in html
    assert "cdn" not in html.lower()


def test_replay_log_round_trips_and_matches_representative_run(preview):
    log = read_log(preview["out_dir"] / LOG_NAME)
    assert log.run_id == REPRESENTATIVE_RUN_ID
    assert len(log.events) > 0

    event_types = {event["event_type"] for event in log.events}
    assert "AGENT_DECIDE" in event_types
    assert "TRADE_SETTLE" in event_types

    summary = (preview["out_dir"] / SUMMARY_NAME).read_text(encoding="utf-8")
    assert REPRESENTATIVE_RUN_ID in summary
    assert REPRESENTATIVE_LABEL in summary


def test_run_md_carries_rebuild_command_and_preview_boundary(preview):
    text = (preview["out_dir"] / RUN_DOC_NAME).read_text(encoding="utf-8")
    assert "python -m market_game_sim.showcase.preview" in text
    assert "--plan" in text
    assert "experiment-preview" in text
    assert DISCLAIMER in text
    assert "R5/T220" in text


def test_two_seed_preview_executes_frozen_pool_prefix_in_order(tmp_path):
    result = generate_preview_bundle(
        tmp_path,
        plan_path=REAL_PLAN,
        n_seeds=2,
        bootstrap_resamples=10,
        sign_flip_resamples=20,
    )
    assert result["executed_seeds"] == [40_000, 40_001]
    assert result["valid_seeds"] == [40_000, 40_001]

    manifest = json.loads((tmp_path / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["seed_plan"] == {"n_seeds": 2, "seeds": [40_000, 40_001]}
    assert manifest["seed"] == 40_000
    validate_showcase_manifest(manifest)

    data = json.loads((tmp_path / "comparison.json").read_text(encoding="utf-8"))
    assert data["preview"]["executed_seeds"] == [40_000, 40_001]
    for family in data["cell_endpoint_means"].values():
        for model in family.values():
            for cell in model.values():
                assert cell["n_runs"] == 2


def test_preview_comparison_is_deterministic(tmp_path):
    """NFR-005: identical inputs must yield byte-identical comparison.json."""
    first = generate_preview_bundle(
        tmp_path / "a",
        plan_path=REAL_PLAN,
        n_seeds=1,
        bootstrap_resamples=10,
        sign_flip_resamples=20,
    )
    second = generate_preview_bundle(
        tmp_path / "b",
        plan_path=REAL_PLAN,
        n_seeds=1,
        bootstrap_resamples=10,
        sign_flip_resamples=20,
    )
    assert first["comparison"].read_bytes() == second["comparison"].read_bytes()
    assert first["summary"].read_text(encoding="utf-8") == second["summary"].read_text(
        encoding="utf-8"
    )


def test_preview_refuses_formal_sample_size(tmp_path):
    with pytest.raises(PreviewError, match="minimum_valid_blocks"):
        generate_preview_bundle(
            tmp_path,
            plan_path=REAL_PLAN,
            n_seeds=128,
            bootstrap_resamples=10,
            sign_flip_resamples=20,
        )


def test_preview_refuses_non_positive_seed_count(tmp_path):
    with pytest.raises(PreviewError, match="positive integer"):
        generate_preview_bundle(
            tmp_path,
            plan_path=REAL_PLAN,
            n_seeds=0,
            bootstrap_resamples=10,
            sign_flip_resamples=20,
        )


def test_preview_refuses_writing_into_docs_experiments(tmp_path):
    with pytest.raises(PreviewError, match="docs/experiments"):
        generate_preview_bundle(
            tmp_path / "docs" / "experiments" / "R3",
            plan_path=REAL_PLAN,
            n_seeds=1,
            bootstrap_resamples=10,
            sign_flip_resamples=20,
        )


def test_required_section_guard_fails_closed():
    with pytest.raises(PreviewError, match="required sections"):
        _assert_required_sections("# incomplete summary")
    complete = "\n".join(REQUIRED_PREVIEW_SECTIONS)
    _assert_required_sections(complete)
