"""T216 formal evidence index and conditional-conclusion tests."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from market_game_sim import __version__
from market_game_sim.experiment.factorial import (
    CELL_IDS,
    CONTRASTS,
    ENDPOINT_FAMILIES,
    METRICS,
    MODEL_IDS,
    event_summary_sha256,
    load_factorial_plan,
    validate_flagship_configs,
)
from market_game_sim.experiment.runner import RunResult
from market_game_sim.metrics.liquidation import LiquidationMetrics, RunClassification
from market_game_sim.showcase.evidence_index import (
    EvidenceIndexError,
    build_evidence_index,
    generate_evidence_index,
    validate_evidence_index,
)
from market_game_sim.showcase.formal import (
    _checkpoint_body,
    _read_checkpoint,
    _source_tree_sha256,
    _write_checkpoint,
)
from market_game_sim.showcase.preview import build_preview_configs

ROOT = Path(__file__).resolve().parents[2]
REAL_PLAN = ROOT / "docs" / "experiments" / "0.1.5-factorial-plan.json"


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _checkpoint_result(seed: int, cell_id: str, *, invalid: bool) -> RunResult:
    classification = RunClassification(
        is_technical_invalid=invalid,
        technical_invalid_code="TI-1" if invalid else None,
    )
    return RunResult(
        seed=seed,
        terminated="COMPLETED",
        abort_code=None,
        events=[{"event_type": "RUN_BOUNDARY", "timestamp": 100}],
        book_last_ticks=10_000,
        accounts={},
        liquidation_metrics=LiquidationMetrics(),
        classification=classification,
        group_label=cell_id,
    )


def _write_checkpoint_fixture(
    path: Path, seed: int, binding, source_tree_sha256: str, *, invalid: bool
) -> None:
    configs = build_preview_configs(seed, binding)
    config_hashes = validate_flagship_configs(configs, binding)
    results = {
        model_id: {
            cell_id: _checkpoint_result(seed, cell_id, invalid=invalid) for cell_id in CELL_IDS
        }
        for model_id in MODEL_IDS
    }
    audit_hashes = {
        model_id: {
            cell_id: event_summary_sha256(results[model_id][cell_id]) for cell_id in CELL_IDS
        }
        for model_id in MODEL_IDS
    }
    _write_checkpoint(
        path,
        _checkpoint_body(
            seed=seed,
            binding=binding,
            config_hashes=config_hashes,
            results=results,
            audit_hashes=audit_hashes,
            source_tree_sha256=source_tree_sha256,
        ),
    )


@pytest.fixture(scope="module")
def t215_fixture(tmp_path_factory):
    root = tmp_path_factory.mktemp("t215_evidence")
    binding = load_factorial_plan(REAL_PLAN)
    seeds = list(binding.seed_plan.planned_seeds)
    source_tree_sha256 = _source_tree_sha256()
    checkpoints = root / "checkpoints"
    checkpoints.mkdir()
    checkpoint_hashes = {}
    for seed in seeds:
        path = checkpoints / f"seed-{seed}.json.gz"
        _write_checkpoint_fixture(path, seed, binding, source_tree_sha256, invalid=False)
        checkpoint_hashes[str(seed)] = _sha256(path)

    progress = {
        "schema_version": 1,
        "producer": "0.1.5 T215",
        "code_version": __version__,
        "source_tree_sha256": source_tree_sha256,
        "run_family": "SPONTANEOUS",
        "evidence_class": "formal-research",
        "plan": binding.report_reference(),
        "executed_seeds": seeds,
        "valid_seeds": seeds,
        "excluded_seed_blocks": {},
        "minimum_valid_blocks": 128,
        "evidence_sufficient": True,
        "inference_eligible": True,
        "stopping_rule_reached": True,
        "seed_pool_exhausted": False,
    }
    effect = {
        "effect": 0.0,
        "ci_low": 0.0,
        "ci_high": 0.0,
        "p_value": 1.0,
        "n_blocks": 128,
        "bootstrap_resamples": 10_000,
        "sign_flip_resamples": 100_000,
        "bh_adjusted_p_value": 1.0,
        "bh_significant": False,
    }
    models = {
        model_id: {metric: {contrast: dict(effect) for contrast in CONTRASTS} for metric in METRICS}
        for model_id in MODEL_IDS
    }
    analysis = {
        "schema_version": 1,
        "producer": "0.1.5 T215",
        "run_family": "SPONTANEOUS",
        "evidence_class": "formal-research",
        "inference_eligible": True,
        "report": {
            "schema_version": 1,
            "plan": binding.report_reference(),
            "seed_plan": {
                "executed_seeds": seeds,
                "valid_seeds": seeds,
                "excluded_seed_blocks": {},
                "minimum_valid_blocks": 128,
                "evidence_sufficient": True,
            },
            "endpoint_families": {
                family: {
                    "evidence_sufficient": True,
                    "inference_eligible": True,
                    "models": copy.deepcopy(models),
                    "bh_q": 0.05,
                    "bh_family_size": 12,
                }
                for family in ENDPOINT_FAMILIES
            },
            "direction_asymmetry": {
                model_id: {
                    cell_id: {
                        "effect": 0.0,
                        "ci_low": 0.0,
                        "ci_high": 0.0,
                        "bootstrap_resamples": 10_000,
                    }
                    for cell_id in CELL_IDS
                }
                for model_id in MODEL_IDS
            },
        },
    }
    _write_json(root / "progress.json", progress)
    _write_json(root / "analysis.json", analysis)
    manifest = {
        "schema_version": 1,
        "producer": "0.1.5 T215",
        "code_version": __version__,
        "source_tree_sha256": source_tree_sha256,
        "run_family": "SPONTANEOUS",
        "evidence_class": "formal-research",
        "plan": binding.report_reference(),
        "config_hash": "b" * 32,
        "executed_seed_plan": {"n_seeds": 128, "seeds": seeds},
        "valid_seeds": seeds,
        "excluded_seed_blocks": {},
        "checkpoint_sha256": checkpoint_hashes,
        "progress_sha256": _sha256(root / "progress.json"),
        "analysis_sha256": _sha256(root / "analysis.json"),
    }
    _write_json(root / "run-manifest.json", manifest)
    return root


@pytest.fixture(scope="module")
def real_index(t215_fixture):
    return build_evidence_index(t215_fixture)


def test_real_t215_builds_complete_formal_index(real_index):
    assert real_index["run_family"] == "SPONTANEOUS"
    assert real_index["evidence_class"] == "formal-research"
    assert real_index["research_claim_eligibility"] == "eligible"
    assert len(real_index["seed_plan"]["valid_seeds"]) == 128
    assert real_index["seed_plan"]["excluded_seed_blocks"] == {}
    assert len(real_index["checkpoints"]) == 128
    assert set(real_index["endpoint_results"]) == set(ENDPOINT_FAMILIES)
    assert all(
        result["status"] == "not-supported" for result in real_index["endpoint_results"].values()
    )
    assert all(
        "不等于接受 H0" in result["statement"] for result in real_index["endpoint_results"].values()
    )
    validate_evidence_index(real_index)


def test_generation_is_byte_deterministic(tmp_path, t215_fixture):
    first = generate_evidence_index(t215_fixture, tmp_path / "a.json")
    second = generate_evidence_index(t215_fixture, tmp_path / "b.json")
    assert first.read_bytes() == second.read_bytes()


def test_non_formal_manifest_is_rejected(tmp_path, t215_fixture):
    manifest = json.loads((t215_fixture / "run-manifest.json").read_text(encoding="utf-8"))
    manifest["evidence_class"] = "experiment-preview"
    fake = tmp_path / "T215"
    fake.mkdir()
    for name in ("progress.json", "analysis.json"):
        (fake / name).write_bytes((t215_fixture / name).read_bytes())
    _write_json(fake / "run-manifest.json", manifest)
    with pytest.raises(EvidenceIndexError, match="evidence_class"):
        build_evidence_index(fake)


def test_cross_family_analysis_is_rejected_after_hash_is_updated(tmp_path, t215_fixture):
    fake = tmp_path / "T215"
    fake.mkdir()
    progress = json.loads((t215_fixture / "progress.json").read_text(encoding="utf-8"))
    analysis = json.loads((t215_fixture / "analysis.json").read_text(encoding="utf-8"))
    manifest = json.loads((t215_fixture / "run-manifest.json").read_text(encoding="utf-8"))
    analysis["run_family"] = "STRESS"
    _write_json(fake / "progress.json", progress)
    _write_json(fake / "analysis.json", analysis)
    manifest["progress_sha256"] = _sha256(fake / "progress.json")
    manifest["analysis_sha256"] = _sha256(fake / "analysis.json")
    _write_json(fake / "run-manifest.json", manifest)
    with pytest.raises(EvidenceIndexError, match="analysis.run_family"):
        build_evidence_index(fake)


def test_partial_progress_is_rejected_after_hash_is_updated(tmp_path, t215_fixture):
    fake = tmp_path / "T215"
    fake.mkdir()
    progress = json.loads((t215_fixture / "progress.json").read_text(encoding="utf-8"))
    manifest = json.loads((t215_fixture / "run-manifest.json").read_text(encoding="utf-8"))
    progress["stopping_rule_reached"] = False
    progress["evidence_sufficient"] = False
    progress["inference_eligible"] = False
    _write_json(fake / "progress.json", progress)
    (fake / "analysis.json").write_bytes((t215_fixture / "analysis.json").read_bytes())
    manifest["progress_sha256"] = _sha256(fake / "progress.json")
    _write_json(fake / "run-manifest.json", manifest)
    with pytest.raises(EvidenceIndexError, match="stopping rule"):
        build_evidence_index(fake)


def test_stale_source_tree_is_rejected(tmp_path, t215_fixture):
    fake = tmp_path / "T215"
    shutil.copytree(t215_fixture, fake)
    progress = json.loads((fake / "progress.json").read_text(encoding="utf-8"))
    manifest = json.loads((fake / "run-manifest.json").read_text(encoding="utf-8"))
    progress["source_tree_sha256"] = "0" * 64
    manifest["source_tree_sha256"] = "0" * 64
    _write_json(fake / "progress.json", progress)
    manifest["progress_sha256"] = _sha256(fake / "progress.json")
    _write_json(fake / "run-manifest.json", manifest)
    with pytest.raises(EvidenceIndexError, match="current package source tree"):
        build_evidence_index(fake)


def test_internally_invalid_checkpoint_is_rejected_after_manifest_rehash(tmp_path, t215_fixture):
    fake = tmp_path / "T215"
    shutil.copytree(t215_fixture, fake)
    checkpoint = fake / "checkpoints" / "seed-30000.json.gz"
    body = _read_checkpoint(checkpoint)
    body["run_family"] = "STRESS"
    _write_checkpoint(checkpoint, body)
    manifest = json.loads((fake / "run-manifest.json").read_text(encoding="utf-8"))
    manifest["checkpoint_sha256"]["30000"] = _sha256(checkpoint)
    _write_json(fake / "run-manifest.json", manifest)
    with pytest.raises(EvidenceIndexError, match=r"checkpoint contract invalid.*run_family"):
        build_evidence_index(fake)


def test_exhausted_insufficient_run_builds_ineligible_index(tmp_path):
    binding = load_factorial_plan(REAL_PLAN)
    source_tree_sha256 = _source_tree_sha256()
    root = tmp_path / "T215"
    checkpoints = root / "checkpoints"
    checkpoints.mkdir(parents=True)
    seeds = list(binding.seed_plan.pool)
    checkpoint_hashes = {}
    for seed in seeds:
        path = checkpoints / f"seed-{seed}.json.gz"
        _write_checkpoint_fixture(path, seed, binding, source_tree_sha256, invalid=True)
        checkpoint_hashes[str(seed)] = _sha256(path)
    exclusions = {str(seed): ["TI-1"] for seed in seeds}
    progress = {
        "schema_version": 1,
        "producer": "0.1.5 T215",
        "code_version": __version__,
        "source_tree_sha256": source_tree_sha256,
        "run_family": "SPONTANEOUS",
        "evidence_class": "formal-research",
        "plan": binding.report_reference(),
        "executed_seeds": seeds,
        "valid_seeds": [],
        "excluded_seed_blocks": exclusions,
        "minimum_valid_blocks": 128,
        "evidence_sufficient": False,
        "inference_eligible": False,
        "stopping_rule_reached": True,
        "seed_pool_exhausted": True,
    }
    analysis = {
        "schema_version": 1,
        "producer": "0.1.5 T215",
        "run_family": "SPONTANEOUS",
        "evidence_class": "formal-research",
        "inference_eligible": False,
        "report": {
            "schema_version": 1,
            "plan": binding.report_reference(),
            "seed_plan": {
                "executed_seeds": seeds,
                "valid_seeds": [],
                "excluded_seed_blocks": exclusions,
                "minimum_valid_blocks": 128,
                "evidence_sufficient": False,
            },
            "endpoint_families": {
                family: {
                    "evidence_sufficient": False,
                    "inference_eligible": False,
                    "reason": "no technically valid paired seed blocks",
                    "models": {},
                }
                for family in ENDPOINT_FAMILIES
            },
            "direction_asymmetry": {},
        },
    }
    _write_json(root / "progress.json", progress)
    _write_json(root / "analysis.json", analysis)
    manifest = {
        "schema_version": 1,
        "producer": "0.1.5 T215",
        "code_version": __version__,
        "source_tree_sha256": source_tree_sha256,
        "run_family": "SPONTANEOUS",
        "evidence_class": "formal-research",
        "plan": binding.report_reference(),
        "config_hash": "b" * 32,
        "executed_seed_plan": {"n_seeds": len(seeds), "seeds": seeds},
        "valid_seeds": [],
        "excluded_seed_blocks": exclusions,
        "checkpoint_sha256": checkpoint_hashes,
        "progress_sha256": _sha256(root / "progress.json"),
        "analysis_sha256": _sha256(root / "analysis.json"),
    }
    _write_json(root / "run-manifest.json", manifest)

    index = build_evidence_index(root)

    assert index["research_claim_eligibility"] == "ineligible"
    assert index["seed_plan"]["seed_pool_exhausted"] is True
    assert index["direction_asymmetry"] == {}
    assert all(
        result["status"] == "evidence-insufficient" for result in index["endpoint_results"].values()
    )
    validate_evidence_index(index)


def test_validator_rejects_missing_or_tampered_evidence_path(real_index):
    missing = copy.deepcopy(real_index)
    missing["source_artifacts"][0]["path"] = "does/not/exist.json"
    with pytest.raises(EvidenceIndexError, match="does not exist"):
        validate_evidence_index(missing)

    tampered = copy.deepcopy(real_index)
    tampered["source_artifacts"][0]["sha256"] = "0" * 64
    with pytest.raises(EvidenceIndexError, match="SHA-256 mismatch"):
        validate_evidence_index(tampered)


def test_validator_rejects_stale_code_binding(real_index):
    stale = copy.deepcopy(real_index)
    stale["code"]["source_tree_sha256"] = "0" * 64
    with pytest.raises(EvidenceIndexError, match="current package"):
        validate_evidence_index(stale)


def test_validator_rejects_conclusion_text_that_disagrees_with_statistics(real_index):
    tampered = copy.deepcopy(real_index)
    tampered["endpoint_results"]["crash"]["statement"] = "处理有显著影响。"
    with pytest.raises(EvidenceIndexError, match="conclusion does not match"):
        validate_evidence_index(tampered)
