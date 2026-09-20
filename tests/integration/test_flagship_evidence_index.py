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
    ENDPOINT_FAMILIES,
    MODEL_IDS,
    analyze_flagship_results,
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
from market_game_sim.showcase.preview import _combined_config_hash, build_preview_configs

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
    is_high_l = cell_id[0] == "H"
    is_high_m = cell_id[1] == "H"
    events = [
        {
            "event_type": "TRADE_SETTLE",
            "timestamp": 10 if not is_high_l else 30,
            "price_ticks": 5_000 if is_high_l else 10_000,
        },
        {
            "event_type": "TRADE_SETTLE",
            "timestamp": 20 if not is_high_m else 60,
            "price_ticks": 20_000 if is_high_m else 10_000,
        },
        {"event_type": "RUN_BOUNDARY", "timestamp": 100},
    ]
    return RunResult(
        seed=seed,
        terminated="COMPLETED",
        abort_code=None,
        events=events,
        book_last_ticks=10_000,
        accounts={},
        liquidation_metrics=LiquidationMetrics(),
        classification=classification,
        group_label=cell_id,
    )


def _write_checkpoint_fixture(
    path: Path, seed: int, binding, source_tree_sha256: str, *, invalid: bool
) -> tuple[dict, dict]:
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
    return results, config_hashes


@pytest.fixture(scope="module")
def synthetic_t215_fixture(tmp_path_factory):
    root = tmp_path_factory.mktemp("t215_evidence")
    binding = load_factorial_plan(REAL_PLAN)
    seeds = list(binding.seed_plan.planned_seeds)
    source_tree_sha256 = _source_tree_sha256()
    checkpoints = root / "checkpoints"
    checkpoints.mkdir()
    checkpoint_hashes = {}
    all_config_hashes = {}
    collected = {model_id: {cell_id: [] for cell_id in CELL_IDS} for model_id in MODEL_IDS}
    for seed in seeds:
        path = checkpoints / f"seed-{seed}.json.gz"
        block, config_hashes = _write_checkpoint_fixture(
            path, seed, binding, source_tree_sha256, invalid=False
        )
        all_config_hashes[seed] = config_hashes
        for model_id in MODEL_IDS:
            for cell_id in CELL_IDS:
                collected[model_id][cell_id].append(block[model_id][cell_id])
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
    report = analyze_flagship_results(
        collected, binding, bootstrap_resamples=10, sign_flip_resamples=10
    )
    for family in report["endpoint_families"].values():
        for model in family["models"].values():
            for metric in model.values():
                for effect in metric.values():
                    effect["bootstrap_resamples"] = binding.bootstrap_resamples
                    effect["sign_flip_resamples"] = binding.sign_flip_resamples
    analysis = {
        "schema_version": 1,
        "producer": "0.1.5 T215",
        "run_family": "SPONTANEOUS",
        "evidence_class": "formal-research",
        "inference_eligible": True,
        "report": report,
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
        "config_hash": _combined_config_hash(all_config_hashes),
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
def synthetic_index(synthetic_t215_fixture):
    return build_evidence_index(synthetic_t215_fixture)


def test_synthetic_t215_builds_complete_formal_index(synthetic_index):
    assert synthetic_index["run_family"] == "SPONTANEOUS"
    assert synthetic_index["evidence_class"] == "formal-research"
    assert synthetic_index["research_claim_eligibility"] == "eligible"
    assert synthetic_index["experimental_validity"]["status"] == "informative"
    assert len(synthetic_index["seed_plan"]["valid_seeds"]) == 128
    assert synthetic_index["seed_plan"]["excluded_seed_blocks"] == {}
    assert len(synthetic_index["checkpoints"]) == 128
    assert set(synthetic_index["endpoint_results"]) == set(ENDPOINT_FAMILIES)
    assert all(
        result["status"] in {"supported", "not-supported"}
        for result in synthetic_index["endpoint_results"].values()
    )
    validate_evidence_index(synthetic_index)


def test_generation_is_byte_deterministic(tmp_path, synthetic_t215_fixture):
    first = generate_evidence_index(synthetic_t215_fixture, tmp_path / "a.json")
    second = generate_evidence_index(synthetic_t215_fixture, tmp_path / "b.json")
    assert first.read_bytes() == second.read_bytes()


def test_non_formal_manifest_is_rejected(tmp_path, synthetic_t215_fixture):
    manifest = json.loads(
        (synthetic_t215_fixture / "run-manifest.json").read_text(encoding="utf-8")
    )
    manifest["evidence_class"] = "experiment-preview"
    fake = tmp_path / "T215"
    fake.mkdir()
    for name in ("progress.json", "analysis.json"):
        (fake / name).write_bytes((synthetic_t215_fixture / name).read_bytes())
    _write_json(fake / "run-manifest.json", manifest)
    with pytest.raises(EvidenceIndexError, match="evidence_class"):
        build_evidence_index(fake)


def test_cross_family_analysis_is_rejected_after_hash_is_updated(tmp_path, synthetic_t215_fixture):
    fake = tmp_path / "T215"
    fake.mkdir()
    progress = json.loads((synthetic_t215_fixture / "progress.json").read_text(encoding="utf-8"))
    analysis = json.loads((synthetic_t215_fixture / "analysis.json").read_text(encoding="utf-8"))
    manifest = json.loads(
        (synthetic_t215_fixture / "run-manifest.json").read_text(encoding="utf-8")
    )
    analysis["run_family"] = "STRESS"
    _write_json(fake / "progress.json", progress)
    _write_json(fake / "analysis.json", analysis)
    manifest["progress_sha256"] = _sha256(fake / "progress.json")
    manifest["analysis_sha256"] = _sha256(fake / "analysis.json")
    _write_json(fake / "run-manifest.json", manifest)
    with pytest.raises(EvidenceIndexError, match="analysis.run_family"):
        build_evidence_index(fake)


def test_partial_progress_is_rejected_after_hash_is_updated(tmp_path, synthetic_t215_fixture):
    fake = tmp_path / "T215"
    fake.mkdir()
    progress = json.loads((synthetic_t215_fixture / "progress.json").read_text(encoding="utf-8"))
    manifest = json.loads(
        (synthetic_t215_fixture / "run-manifest.json").read_text(encoding="utf-8")
    )
    progress["stopping_rule_reached"] = False
    progress["evidence_sufficient"] = False
    progress["inference_eligible"] = False
    _write_json(fake / "progress.json", progress)
    (fake / "analysis.json").write_bytes((synthetic_t215_fixture / "analysis.json").read_bytes())
    manifest["progress_sha256"] = _sha256(fake / "progress.json")
    _write_json(fake / "run-manifest.json", manifest)
    with pytest.raises(EvidenceIndexError, match="stopping rule"):
        build_evidence_index(fake)


def test_stale_source_tree_is_rejected(tmp_path, synthetic_t215_fixture):
    fake = tmp_path / "T215"
    shutil.copytree(synthetic_t215_fixture, fake)
    progress = json.loads((fake / "progress.json").read_text(encoding="utf-8"))
    manifest = json.loads((fake / "run-manifest.json").read_text(encoding="utf-8"))
    progress["source_tree_sha256"] = "0" * 64
    manifest["source_tree_sha256"] = "0" * 64
    _write_json(fake / "progress.json", progress)
    manifest["progress_sha256"] = _sha256(fake / "progress.json")
    _write_json(fake / "run-manifest.json", manifest)
    with pytest.raises(EvidenceIndexError, match="current package source tree"):
        build_evidence_index(fake)


def test_manifest_config_hash_is_recomputed(tmp_path, synthetic_t215_fixture):
    fake = tmp_path / "T215"
    shutil.copytree(synthetic_t215_fixture, fake)
    manifest = json.loads((fake / "run-manifest.json").read_text(encoding="utf-8"))
    manifest["config_hash"] = "0" * 32
    _write_json(fake / "run-manifest.json", manifest)
    with pytest.raises(EvidenceIndexError, match="reconstructed configs"):
        build_evidence_index(fake)


def test_handwritten_analysis_effect_is_rejected(tmp_path, synthetic_t215_fixture):
    fake = tmp_path / "T215"
    shutil.copytree(synthetic_t215_fixture, fake)
    analysis_path = fake / "analysis.json"
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    # Mutate the actual nested effect while preserving a syntactically valid report.
    analysis["report"]["endpoint_families"]["crash"]["models"][MODEL_IDS[0]]["severity"]["L"][
        "effect"
    ] = 0.0
    _write_json(analysis_path, analysis)
    manifest_path = fake / "run-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["analysis_sha256"] = _sha256(analysis_path)
    _write_json(manifest_path, manifest)
    with pytest.raises(EvidenceIndexError, match="reconstructed checkpoints"):
        build_evidence_index(fake)


def test_internally_invalid_checkpoint_is_rejected_after_manifest_rehash(
    tmp_path, synthetic_t215_fixture
):
    fake = tmp_path / "T215"
    shutil.copytree(synthetic_t215_fixture, fake)
    first_seed = load_factorial_plan(REAL_PLAN).seed_plan.planned_seeds[0]
    checkpoint = fake / "checkpoints" / f"seed-{first_seed}.json.gz"
    body = _read_checkpoint(checkpoint)
    body["run_family"] = "STRESS"
    _write_checkpoint(checkpoint, body)
    manifest = json.loads((fake / "run-manifest.json").read_text(encoding="utf-8"))
    manifest["checkpoint_sha256"][str(first_seed)] = _sha256(checkpoint)
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
    all_config_hashes = {}
    collected = {model_id: {cell_id: [] for cell_id in CELL_IDS} for model_id in MODEL_IDS}
    for seed in seeds:
        path = checkpoints / f"seed-{seed}.json.gz"
        block, config_hashes = _write_checkpoint_fixture(
            path, seed, binding, source_tree_sha256, invalid=True
        )
        all_config_hashes[seed] = config_hashes
        for model_id in MODEL_IDS:
            for cell_id in CELL_IDS:
                collected[model_id][cell_id].append(block[model_id][cell_id])
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
    report = analyze_flagship_results(
        collected, binding, bootstrap_resamples=10, sign_flip_resamples=10
    )
    analysis = {
        "schema_version": 1,
        "producer": "0.1.5 T215",
        "run_family": "SPONTANEOUS",
        "evidence_class": "formal-research",
        "inference_eligible": False,
        "report": report,
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
        "config_hash": _combined_config_hash(all_config_hashes),
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


def test_validator_rejects_missing_or_tampered_evidence_path(synthetic_index):
    missing = copy.deepcopy(synthetic_index)
    missing["source_artifacts"][0]["path"] = "does/not/exist.json"
    with pytest.raises(EvidenceIndexError, match="does not exist"):
        validate_evidence_index(missing)

    tampered = copy.deepcopy(synthetic_index)
    tampered["source_artifacts"][0]["sha256"] = "0" * 64
    with pytest.raises(EvidenceIndexError, match="SHA-256 mismatch"):
        validate_evidence_index(tampered)


def test_validator_rejects_stale_code_binding(synthetic_index):
    stale = copy.deepcopy(synthetic_index)
    stale["code"]["source_tree_sha256"] = "0" * 64
    with pytest.raises(EvidenceIndexError, match="current package"):
        validate_evidence_index(stale)


def test_validator_rejects_conclusion_text_that_disagrees_with_statistics(synthetic_index):
    tampered = copy.deepcopy(synthetic_index)
    tampered["endpoint_results"]["crash"]["statement"] = "处理有显著影响。"
    with pytest.raises(EvidenceIndexError, match="conclusion does not match"):
        validate_evidence_index(tampered)


# --------------------------------------------------------------------------- #
# ADR-012：证据索引重绑必须显式盖章
#
# 守卫报错原文是 `rerun T215 after source changes`，但实践是 19 次只改
# `code.source_tree_sha256` 一行的纯重绑，无一次重跑。下面每条都是负向变异：
# 只断言"当前仓库通过"证明不了这个门禁在挡任何东西。
# --------------------------------------------------------------------------- #

REPO_INDEX = ROOT / "docs" / "experiments" / "0.1.5-evidence-index.json"


def _rebound_attestation(index: dict) -> dict:
    """把一份实跑索引改写成"重绑但已盖章"的合法形态。"""
    rebound = copy.deepcopy(index)
    rebound["attestation"] = {
        "rerun": False,
        "attested_source_tree_sha256": index["code"]["source_tree_sha256"],
        "t215_source_tree_sha256": "a" * 64,
        "t215_bound_at": "2026-08-30",
        "rebound_at": "2026-09-20",
        "reason": "呈现层改动，与 T215 运行路径无关",
    }
    return rebound


def test_repository_index_attestation_tracks_its_code_binding():
    """已提交的 0.1.5 索引必须自带与其哈希同步的盖章（ADR-012 正向）。"""
    index = json.loads(REPO_INDEX.read_text(encoding="utf-8"))
    attestation = index["attestation"]
    assert attestation["attested_source_tree_sha256"] == index["code"]["source_tree_sha256"]
    assert attestation["rerun"] is False, "当前索引是重绑而非重跑，不得声明 rerun"
    assert attestation["t215_source_tree_sha256"] != index["code"]["source_tree_sha256"]
    assert attestation["reason"].strip()
    assert attestation["rebound_at"] >= attestation["t215_bound_at"]


def test_builder_attests_a_real_rerun(synthetic_index):
    """由 T215 产物现场构建 ⇒ rerun=true，两个哈希同源，无重绑日期。"""
    attestation = synthetic_index["attestation"]
    assert attestation["rerun"] is True
    assert attestation["t215_source_tree_sha256"] == synthetic_index["code"]["source_tree_sha256"]
    assert attestation["rebound_at"] is None
    validate_evidence_index(synthetic_index)


def test_rebinding_without_reattesting_is_rejected(synthetic_index):
    """改哈希不改盖章即红——这是本门禁的全部执行力所在。"""
    stale = copy.deepcopy(synthetic_index)
    stale["attestation"]["attested_source_tree_sha256"] = "b" * 64
    with pytest.raises(EvidenceIndexError, match="re-attesting"):
        validate_evidence_index(stale)


def test_wellformed_rebinding_attestation_is_accepted(synthetic_index):
    """盖过章的重绑必须能通过——门禁不是禁止重绑，而是禁止静默重绑。"""
    validate_evidence_index(_rebound_attestation(synthetic_index))


def test_attestation_cannot_claim_a_rerun_it_did_not_do(synthetic_index):
    faked = copy.deepcopy(synthetic_index)
    faked["attestation"]["t215_source_tree_sha256"] = "c" * 64
    with pytest.raises(EvidenceIndexError, match="claims a T215 rerun"):
        validate_evidence_index(faked)


def test_rebinding_must_not_present_itself_as_the_t215_tree(synthetic_index):
    """rerun=false 却把 T215 源码树写成当前哈希 = 抹掉"证据产出环境"这一事实。"""
    laundered = _rebound_attestation(synthetic_index)
    laundered["attestation"]["t215_source_tree_sha256"] = synthetic_index["code"][
        "source_tree_sha256"
    ]
    with pytest.raises(EvidenceIndexError, match="declare rerun: true"):
        validate_evidence_index(laundered)


@pytest.mark.parametrize("field", sorted({"rerun", "reason", "t215_bound_at", "rebound_at"}))
def test_attestation_missing_field_is_rejected(synthetic_index, field):
    broken = _rebound_attestation(synthetic_index)
    del broken["attestation"][field]
    with pytest.raises(EvidenceIndexError, match="attestation"):
        validate_evidence_index(broken)


def test_rebinding_requires_a_reason_and_a_date(synthetic_index):
    undated = _rebound_attestation(synthetic_index)
    undated["attestation"]["rebound_at"] = None
    with pytest.raises(EvidenceIndexError, match="rebound_at must be YYYY-MM-DD"):
        validate_evidence_index(undated)

    unexplained = _rebound_attestation(synthetic_index)
    unexplained["attestation"]["reason"] = "   "
    with pytest.raises(EvidenceIndexError, match="reason must be a non-empty string"):
        validate_evidence_index(unexplained)


def test_rebinding_cannot_predate_the_t215_run(synthetic_index):
    inverted = _rebound_attestation(synthetic_index)
    inverted["attestation"]["rebound_at"] = "2026-08-29"
    with pytest.raises(EvidenceIndexError, match="precedes t215_bound_at"):
        validate_evidence_index(inverted)


def test_rerun_attestation_must_not_carry_a_rebinding_date(synthetic_index):
    mixed = copy.deepcopy(synthetic_index)
    mixed["attestation"]["rebound_at"] = "2026-09-20"
    with pytest.raises(EvidenceIndexError, match="must be null when rerun is true"):
        validate_evidence_index(mixed)


def test_r5_report_discloses_a_rebinding_instead_of_claiming_a_rerun():
    """R5 是给人读的交付面：重绑不得只显示当前哈希，必须披露证据真正的产出环境。"""
    from market_game_sim.showcase.r5 import _render_r5_report

    index = json.loads(REPO_INDEX.read_text(encoding="utf-8"))
    report = _render_r5_report(
        index,
        seed=index["seed_plan"]["valid_seeds"][0],
        model_id="risk_budget_linear_v1",
        cell_id="L0M0",
        keep_every=1,
        evidence_sha256="0" * 64,
        replay_link="replay.html",
        evidence_link="evidence.json",
    )
    signoff = report.split("## 版本签收", 1)[1]
    assert "未重跑 T215" in signoff
    assert index["attestation"]["t215_source_tree_sha256"] in signoff

    rerun = copy.deepcopy(index)
    rerun["attestation"] = {
        "rerun": True,
        "attested_source_tree_sha256": index["code"]["source_tree_sha256"],
        "t215_source_tree_sha256": index["code"]["source_tree_sha256"],
        "t215_bound_at": None,
        "rebound_at": None,
        "reason": "T215 产物现场重建，绑定即实跑",
    }
    rerun_report = _render_r5_report(
        rerun,
        seed=index["seed_plan"]["valid_seeds"][0],
        model_id="risk_budget_linear_v1",
        cell_id="L0M0",
        keep_every=1,
        evidence_sha256="0" * 64,
        replay_link="replay.html",
        evidence_link="evidence.json",
    )
    rerun_signoff = rerun_report.split("## 版本签收", 1)[1]
    assert "T215 实跑绑定" in rerun_signoff
    assert "未重跑" not in rerun_signoff
