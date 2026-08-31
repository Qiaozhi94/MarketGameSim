"""T216: formal evidence index and conditional endpoint conclusions.

This generator consumes only the completed T215 material.  It verifies the
manifest-to-analysis/progress hashes, every seed-block checkpoint hash, the
frozen preregistration binding, and the ``SPONTANEOUS + formal-research``
permission before writing the repository evidence index.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from typing import Any

from market_game_sim import __version__
from market_game_sim.evidence.evidence_guard import guard_evidence_class
from market_game_sim.experiment.factorial import (
    CELL_IDS,
    CONTRASTS,
    ENDPOINT_FAMILIES,
    METRICS,
    MODEL_IDS,
    FactorialPlanBinding,
    analyze_flagship_results,
    load_factorial_plan,
    validate_flagship_configs,
)
from market_game_sim.showcase.formal import (
    FormalRunError,
    _read_checkpoint,
    _source_tree_sha256,
    _validate_checkpoint_body,
)
from market_game_sim.showcase.preview import _combined_config_hash, build_preview_configs

PRODUCER = "0.1.5 T216"
EVIDENCE_CLASS = "formal-research"
RUN_FAMILY = "SPONTANEOUS"
DEFAULT_T215_DIR = pathlib.Path("artifacts/formal/T215")
DEFAULT_OUT = pathlib.Path("docs/experiments/0.1.5-evidence-index.json")

FAMILY_LABELS = {
    "crash": "崩盘",
    "surge": "暴涨",
    "liquidity_drought": "流动性枯竭",
}


class EvidenceIndexError(RuntimeError):
    """T215 material cannot authorize a T216 evidence index."""


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_object(path: pathlib.Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceIndexError(f"cannot read {label} at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceIndexError(f"{label} root must be an object")
    return value


def _portable_path(path: pathlib.Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(pathlib.Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _require_exact_keys(value: Any, expected: set[str], label: str) -> None:
    if not isinstance(value, dict):
        raise EvidenceIndexError(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        raise EvidenceIndexError(
            f"{label} fields mismatch: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def _validate_common_scope(payload: dict[str, Any], label: str) -> None:
    if payload.get("run_family") != RUN_FAMILY:
        raise EvidenceIndexError(
            f"{label}.run_family must be {RUN_FAMILY!r}, got {payload.get('run_family')!r}"
        )
    if payload.get("evidence_class") != EVIDENCE_CLASS:
        raise EvidenceIndexError(
            f"{label}.evidence_class must be {EVIDENCE_CLASS!r}, "
            f"got {payload.get('evidence_class')!r}"
        )


def _validate_plan_reference(reference: Any, binding: FactorialPlanBinding, label: str) -> None:
    if reference != binding.report_reference():
        raise EvidenceIndexError(
            f"{label} does not match the resolved frozen factorial plan reference"
        )


def _validate_effect(
    effect: Any,
    *,
    binding: FactorialPlanBinding,
    valid_blocks: int,
    label: str,
) -> None:
    expected = {
        "effect",
        "ci_low",
        "ci_high",
        "p_value",
        "n_blocks",
        "bootstrap_resamples",
        "sign_flip_resamples",
        "bh_adjusted_p_value",
        "bh_significant",
    }
    _require_exact_keys(effect, expected, label)
    for field in ("effect", "ci_low", "ci_high", "p_value", "bh_adjusted_p_value"):
        value = effect[field]
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise EvidenceIndexError(f"{label}.{field} must be numeric")
    if effect["ci_low"] > effect["effect"] or effect["effect"] > effect["ci_high"]:
        raise EvidenceIndexError(f"{label} effect must lie inside its confidence interval")
    if not 0 <= effect["p_value"] <= 1 or not 0 <= effect["bh_adjusted_p_value"] <= 1:
        raise EvidenceIndexError(f"{label} p-values must be in [0, 1]")
    expected_fixed = {
        "n_blocks": valid_blocks,
        "bootstrap_resamples": binding.bootstrap_resamples,
        "sign_flip_resamples": binding.sign_flip_resamples,
    }
    for field, expected_value in expected_fixed.items():
        if effect[field] != expected_value:
            raise EvidenceIndexError(
                f"{label}.{field} must be {expected_value}, got {effect[field]!r}"
            )
    if type(effect["bh_significant"]) is not bool:
        raise EvidenceIndexError(f"{label}.bh_significant must be boolean")


def _family_conclusion(
    family_id: str,
    family: dict[str, Any],
    *,
    binding: FactorialPlanBinding,
    valid_blocks: int,
    evidence_sufficient: bool,
) -> dict[str, Any]:
    family_label = f"analysis.endpoint_families.{family_id}"
    if valid_blocks == 0:
        _require_exact_keys(
            family,
            {"evidence_sufficient", "inference_eligible", "reason", "models"},
            family_label,
        )
        if family["models"] != {} or not isinstance(family["reason"], str):
            raise EvidenceIndexError(f"{family_label} empty-result fields are invalid")
    else:
        expected_keys = {
            "evidence_sufficient",
            "inference_eligible",
            "experimental_validity",
            "models",
            "bh_q",
            "bh_family_size",
        }
        if family.get("experimental_validity") == "degenerate":
            expected_keys.add("reason")
        _require_exact_keys(family, expected_keys, family_label)
    informative = valid_blocks > 0 and family.get("experimental_validity") == "informative"
    expected_eligibility = evidence_sufficient and informative
    if (
        family["evidence_sufficient"] is not evidence_sufficient
        or family["inference_eligible"] is not expected_eligibility
    ):
        raise EvidenceIndexError(
            f"{family_label} eligibility differs from the frozen stopping result"
        )
    if valid_blocks > 0 and (family["bh_q"] != binding.bh_q or family["bh_family_size"] != 12):
        raise EvidenceIndexError(f"{family_label} BH family drifted from 12 tests at q=0.05")
    models = family["models"]
    if valid_blocks > 0:
        _require_exact_keys(models, set(MODEL_IDS), f"{family_label}.models")
    significant: list[str] = []
    for model_id in MODEL_IDS if valid_blocks > 0 else ():
        metrics = models[model_id]
        _require_exact_keys(
            metrics,
            set(METRICS),
            f"analysis.endpoint_families.{family_id}.models.{model_id}",
        )
        for metric in METRICS:
            contrasts = metrics[metric]
            _require_exact_keys(
                contrasts,
                set(CONTRASTS),
                f"analysis.endpoint_families.{family_id}.models.{model_id}.{metric}",
            )
            for contrast in CONTRASTS:
                effect = contrasts[contrast]
                hypothesis_id = f"{model_id}.{metric}.{contrast}"
                _validate_effect(
                    effect,
                    binding=binding,
                    valid_blocks=valid_blocks,
                    label=f"analysis.endpoint_families.{family_id}.{hypothesis_id}",
                )
                if expected_eligibility and effect["bh_significant"]:
                    significant.append(hypothesis_id)

    label = FAMILY_LABELS[family_id]
    if valid_blocks > 0 and not informative:
        status = "degenerate"
        statement = (
            f"{label}家族的全部预注册块内对比均为零，未通过市场充分性门槛；"
            "不得将退化输出解释为支持 H0 或制度无效应。"
        )
    elif not evidence_sufficient:
        status = "evidence-insufficient"
        statement = (
            f"冻结种子池已耗尽，仅得到 {valid_blocks} 个技术有效配对 seed block，低于预注册"
            f"最低要求 {binding.seed_plan.minimum_valid_blocks}；{label}家族不得进行研究声明，"
            "现有描述性统计不得解释为支持或否定 H1。"
        )
    elif significant:
        status = "supported"
        statement = (
            f"在冻结的代理结构、L×M 四 cell、两个目标模型与 {valid_blocks} 个有效"
            f"配对 seed block 范围内，{label}家族有 {len(significant)}/12 个预注册检验在"
            "BH q=0.05 后支持处理效应；支持仅限列出的模型、指标与对比，不得外推。"
        )
    else:
        status = "not-supported"
        statement = (
            f"在冻结的代理结构、L×M 四 cell、两个目标模型与 {valid_blocks} 个有效"
            f"配对 seed block 范围内，{label}家族 0/12 个预注册检验在 BH q=0.05 后支持"
            "处理效应；本结果是不支持预注册 H1，不等于接受 H0，也不得外推为现实市场无效应。"
        )
    return {
        "status": status,
        "statement": statement,
        "significant_hypotheses": significant,
        "bh_q": family.get("bh_q", binding.bh_q),
        "bh_family_size": family.get("bh_family_size", 12),
        "models": models,
    }


def _validate_experimental_validity(value: Any, binding: FactorialPlanBinding) -> bool:
    _require_exact_keys(
        value,
        {"status", "criterion", "minimum_informative_hypotheses_per_family", "families"},
        "experimental_validity",
    )
    if value["minimum_informative_hypotheses_per_family"] != (
        binding.minimum_informative_hypotheses_per_family
    ):
        raise EvidenceIndexError("experimental validity threshold drifted from the frozen plan")
    if value["status"] == "no-valid-blocks":
        if value["families"] != {}:
            raise EvidenceIndexError("no-valid-blocks validity must have no family results")
        return False
    _require_exact_keys(value["families"], set(ENDPOINT_FAMILIES), "experimental_validity.families")
    all_informative = True
    expected_hypotheses = {
        f"{model_id}.{metric}.{contrast}"
        for model_id in MODEL_IDS
        for metric in METRICS
        for contrast in CONTRASTS
    }
    for family_id in ENDPOINT_FAMILIES:
        family = value["families"][family_id]
        _require_exact_keys(
            family,
            {"status", "informative_hypotheses", "nonzero_block_counts"},
            f"experimental_validity.families.{family_id}",
        )
        counts = family["nonzero_block_counts"]
        _require_exact_keys(
            counts, expected_hypotheses, f"experimental_validity.families.{family_id}.counts"
        )
        if any(type(count) is not int or count < 0 for count in counts.values()):
            raise EvidenceIndexError("experimental validity counts must be non-negative integers")
        expected_informative = sorted(key for key, count in counts.items() if count > 0)
        if family["informative_hypotheses"] != expected_informative:
            raise EvidenceIndexError(
                "experimental validity informative hypothesis list is inconsistent"
            )
        expected_status = (
            "informative"
            if len(expected_informative) >= binding.minimum_informative_hypotheses_per_family
            else "degenerate"
        )
        if family["status"] != expected_status:
            raise EvidenceIndexError("experimental validity family status is inconsistent")
        all_informative &= expected_status == "informative"
    expected_overall = "informative" if all_informative else "degenerate"
    if value["status"] != expected_overall:
        raise EvidenceIndexError("experimental validity overall status is inconsistent")
    return all_informative


def _validate_t215(
    t215_dir: pathlib.Path,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    FactorialPlanBinding,
    list[dict[str, str]],
]:
    progress_path = t215_dir / "progress.json"
    analysis_path = t215_dir / "analysis.json"
    manifest_path = t215_dir / "run-manifest.json"
    progress = _read_object(progress_path, "T215 progress")
    analysis = _read_object(analysis_path, "T215 analysis")
    manifest = _read_object(manifest_path, "T215 run manifest")
    for label, payload in (("progress", progress), ("analysis", analysis), ("manifest", manifest)):
        _validate_common_scope(payload, label)
    guard_evidence_class(RUN_FAMILY, EVIDENCE_CLASS)

    if manifest.get("progress_sha256") != _sha256(progress_path):
        raise EvidenceIndexError("manifest.progress_sha256 does not match progress.json")
    if manifest.get("analysis_sha256") != _sha256(analysis_path):
        raise EvidenceIndexError("manifest.analysis_sha256 does not match analysis.json")
    if progress.get("stopping_rule_reached") is not True:
        raise EvidenceIndexError(
            "T215 stopping rule has not been reached; partial progress is ineligible"
        )

    plan_reference = manifest.get("plan")
    if not isinstance(plan_reference, dict):
        raise EvidenceIndexError("manifest.plan must be an object")
    plan_path_value = plan_reference.get("factorial_plan_path")
    if not isinstance(plan_path_value, str) or not plan_path_value:
        raise EvidenceIndexError("manifest.plan.factorial_plan_path must be a path")
    binding = load_factorial_plan(plan_path_value)
    current_source = _source_tree_sha256()
    manifest_source = manifest.get("source_tree_sha256")
    if manifest_source != current_source:
        raise EvidenceIndexError(
            "manifest.source_tree_sha256 differs from the current package source tree; "
            "rerun T215 after source changes"
        )
    if progress.get("source_tree_sha256") != manifest_source:
        raise EvidenceIndexError("progress.source_tree_sha256 differs from manifest")
    if manifest.get("code_version") != __version__ or progress.get("code_version") != __version__:
        raise EvidenceIndexError("T215 code_version differs from the current package version")
    for label, reference in (
        ("manifest.plan", manifest.get("plan")),
        ("progress.plan", progress.get("plan")),
        ("analysis.report.plan", analysis.get("report", {}).get("plan")),
    ):
        _validate_plan_reference(reference, binding, label)

    executed = progress.get("executed_seeds")
    valid = progress.get("valid_seeds")
    excluded = progress.get("excluded_seed_blocks")
    minimum = progress.get("minimum_valid_blocks")
    if executed != manifest.get("executed_seed_plan", {}).get("seeds"):
        raise EvidenceIndexError("progress.executed_seeds differs from manifest seed plan")
    if valid != manifest.get("valid_seeds") or excluded != manifest.get("excluded_seed_blocks"):
        raise EvidenceIndexError("progress valid/excluded seeds differ from manifest")
    if not isinstance(executed, list) or not all(type(seed) is int for seed in executed):
        raise EvidenceIndexError("progress.executed_seeds must be an integer list")
    if not isinstance(valid, list) or not all(type(seed) is int for seed in valid):
        raise EvidenceIndexError("progress.valid_seeds must be an integer list")
    if not isinstance(excluded, dict):
        raise EvidenceIndexError("progress.excluded_seed_blocks must be an object")
    if minimum != binding.seed_plan.minimum_valid_blocks:
        raise EvidenceIndexError("progress minimum differs from the frozen seed plan")
    sufficient = len(valid) >= minimum
    if progress.get("evidence_sufficient") is not sufficient:
        raise EvidenceIndexError("progress.evidence_sufficient differs from its valid seed count")
    exhausted = not sufficient
    if progress.get("seed_pool_exhausted") is not exhausted:
        raise EvidenceIndexError("progress.seed_pool_exhausted differs from the stopping result")
    if exhausted and executed != list(binding.seed_plan.pool):
        raise EvidenceIndexError(
            "insufficient evidence is only final after the frozen seed pool exhausts"
        )
    report_seed_plan = analysis.get("report", {}).get("seed_plan")
    expected_report_seed_plan = {
        "executed_seeds": executed,
        "valid_seeds": valid,
        "excluded_seed_blocks": excluded,
        "minimum_valid_blocks": minimum,
        "evidence_sufficient": sufficient,
    }
    if report_seed_plan != expected_report_seed_plan:
        raise EvidenceIndexError("analysis.report.seed_plan differs from T215 progress")

    checkpoint_hashes = manifest.get("checkpoint_sha256")
    if not isinstance(checkpoint_hashes, dict) or set(checkpoint_hashes) != {
        str(seed) for seed in executed
    }:
        raise EvidenceIndexError("manifest checkpoint index does not match executed seeds")
    checkpoint_entries: list[dict[str, str]] = []
    collected = {model_id: {cell_id: [] for cell_id in CELL_IDS} for model_id in MODEL_IDS}
    all_config_hashes: dict[int, dict[str, dict[str, str]]] = {}
    for seed in executed:
        checkpoint = t215_dir / "checkpoints" / f"seed-{seed}.json.gz"
        if not checkpoint.is_file():
            raise EvidenceIndexError(f"checkpoint path does not exist: {checkpoint}")
        digest = _sha256(checkpoint)
        if checkpoint_hashes[str(seed)] != digest:
            raise EvidenceIndexError(f"checkpoint SHA-256 mismatch for seed {seed}")
        try:
            configs = build_preview_configs(seed, binding)
            config_hashes = validate_flagship_configs(configs, binding)
            body = _read_checkpoint(checkpoint)
            block = _validate_checkpoint_body(
                body,
                seed=seed,
                binding=binding,
                config_hashes=config_hashes,
                expected_code_version=manifest["code_version"],
                expected_source_tree_sha256=manifest_source,
            )
        except (FormalRunError, KeyError, TypeError, ValueError) as exc:
            raise EvidenceIndexError(f"checkpoint contract invalid for seed {seed}: {exc}") from exc
        all_config_hashes[seed] = config_hashes
        for model_id in MODEL_IDS:
            for cell_id in CELL_IDS:
                collected[model_id][cell_id].append(block[model_id][cell_id])
        checkpoint_entries.append(
            {"seed": str(seed), "path": _portable_path(checkpoint), "sha256": digest}
        )
    if manifest.get("config_hash") != _combined_config_hash(all_config_hashes):
        raise EvidenceIndexError("manifest.config_hash does not match reconstructed configs")
    recomputed_report = analyze_flagship_results(
        collected, binding, bootstrap_resamples=1, sign_flip_resamples=1
    )
    # Persisted JSON stringifies integer exclusion-map keys; compare in that same domain.
    recomputed_report = json.loads(json.dumps(recomputed_report))
    persisted_report = analysis.get("report")
    if not isinstance(persisted_report, dict):
        raise EvidenceIndexError("analysis.report must be an object")
    if persisted_report.get("seed_plan") != recomputed_report["seed_plan"]:
        raise EvidenceIndexError("analysis seed plan does not match reconstructed checkpoints")
    if persisted_report.get("experimental_validity") != recomputed_report["experimental_validity"]:
        raise EvidenceIndexError("analysis validity does not match reconstructed checkpoints")
    if valid:
        for family_id in ENDPOINT_FAMILIES:
            for model_id in MODEL_IDS:
                for metric in METRICS:
                    for contrast in CONTRASTS:
                        persisted_effect = persisted_report["endpoint_families"][family_id][
                            "models"
                        ][model_id][metric][contrast]
                        recomputed_effect = recomputed_report["endpoint_families"][family_id][
                            "models"
                        ][model_id][metric][contrast]
                        if persisted_effect.get("effect") != recomputed_effect["effect"]:
                            raise EvidenceIndexError(
                                "analysis effect does not match reconstructed checkpoints: "
                                f"{family_id}.{model_id}.{metric}.{contrast}"
                            )
    inference_eligible = recomputed_report["research_claim_eligibility"] == "eligible"
    if progress.get("inference_eligible") is not inference_eligible:
        raise EvidenceIndexError("progress.inference_eligible differs from experimental validity")
    if analysis.get("inference_eligible") is not inference_eligible:
        raise EvidenceIndexError("analysis.inference_eligible differs from experimental validity")
    return progress, analysis, manifest, binding, checkpoint_entries


def build_evidence_index(t215_dir: str | pathlib.Path = DEFAULT_T215_DIR) -> dict[str, Any]:
    t215 = pathlib.Path(t215_dir)
    progress, analysis, manifest, binding, checkpoints = _validate_t215(t215)
    report = analysis["report"]
    evidence_sufficient = progress["evidence_sufficient"]
    experimental_validity = report.get("experimental_validity")
    informative = _validate_experimental_validity(experimental_validity, binding)
    valid_blocks = len(progress["valid_seeds"])
    families = report.get("endpoint_families")
    _require_exact_keys(families, set(ENDPOINT_FAMILIES), "analysis.report.endpoint_families")
    endpoint_results = {
        family_id: _family_conclusion(
            family_id,
            families[family_id],
            binding=binding,
            valid_blocks=valid_blocks,
            evidence_sufficient=evidence_sufficient,
        )
        for family_id in ENDPOINT_FAMILIES
    }
    direction_asymmetry = report.get("direction_asymmetry")
    expected_direction_models = set(MODEL_IDS) if valid_blocks > 0 else set()
    _require_exact_keys(
        direction_asymmetry,
        expected_direction_models,
        "analysis.report.direction_asymmetry",
    )

    source_artifacts = []
    for name in ("progress.json", "analysis.json", "run-manifest.json"):
        path = t215 / name
        source_artifacts.append(
            {"artifact": name, "path": _portable_path(path), "sha256": _sha256(path)}
        )
    return {
        "schema_version": 1,
        "milestone": "0.1.5",
        "producer": PRODUCER,
        "run_family": RUN_FAMILY,
        "evidence_class": EVIDENCE_CLASS,
        "research_claim_eligibility": (
            "eligible" if evidence_sufficient and informative else "ineligible"
        ),
        "code": {
            "package_version": manifest["code_version"],
            "source_tree_sha256": manifest["source_tree_sha256"],
            "config_hash": manifest["config_hash"],
        },
        "preregistration": binding.report_reference(),
        "seed_plan": {
            "executed_seeds": progress["executed_seeds"],
            "valid_seeds": progress["valid_seeds"],
            "excluded_seed_blocks": progress["excluded_seed_blocks"],
            "minimum_valid_blocks": progress["minimum_valid_blocks"],
            "evidence_sufficient": evidence_sufficient,
            "stopping_rule_reached": progress["stopping_rule_reached"],
            "seed_pool_exhausted": progress["seed_pool_exhausted"],
        },
        "source_artifacts": source_artifacts,
        "checkpoints": checkpoints,
        "endpoint_results": endpoint_results,
        "experimental_validity": experimental_validity,
        "direction_asymmetry": direction_asymmetry,
        "limitations": [
            "结论仅适用于冻结的仿真代理、参数、种子与 2×2 制度处理，不外推到现实市场。",
            "未通过 BH 的检验表示预注册 H1 未获支持，不表示接受 H0 或证明效应严格为零。",
            "有效性门槛仅保证每个终点家族至少存在一个非零块内对比，不保证全部指标变化或统计功效。",
            "本产物不是交易信号，不连接真实账户、交易所或钱包。",
        ],
    }


def validate_evidence_index(index: dict[str, Any], *, require_paths: bool = True) -> None:
    expected = {
        "schema_version",
        "milestone",
        "producer",
        "run_family",
        "evidence_class",
        "research_claim_eligibility",
        "code",
        "preregistration",
        "seed_plan",
        "source_artifacts",
        "checkpoints",
        "endpoint_results",
        "experimental_validity",
        "direction_asymmetry",
        "limitations",
    }
    _require_exact_keys(index, expected, "evidence index")
    fixed = {
        "schema_version": 1,
        "milestone": "0.1.5",
        "producer": PRODUCER,
        "run_family": RUN_FAMILY,
        "evidence_class": EVIDENCE_CLASS,
    }
    for field, value in fixed.items():
        if index[field] != value:
            raise EvidenceIndexError(f"evidence index.{field} must be {value!r}")
    _require_exact_keys(
        index["code"],
        {"package_version", "source_tree_sha256", "config_hash"},
        "evidence index.code",
    )
    for field, length in (("source_tree_sha256", 64), ("config_hash", 32)):
        digest = index["code"][field]
        if (
            not isinstance(digest, str)
            or len(digest) != length
            or any(char not in "0123456789abcdef" for char in digest)
        ):
            raise EvidenceIndexError(f"evidence index.code.{field} must be lowercase hex")
    if (
        index["code"]["package_version"] != __version__
        or index["code"]["source_tree_sha256"] != _source_tree_sha256()
    ):
        raise EvidenceIndexError(
            "evidence index code binding differs from the current package; rebuild T215/T216"
        )
    _require_exact_keys(
        index["seed_plan"],
        {
            "executed_seeds",
            "valid_seeds",
            "excluded_seed_blocks",
            "minimum_valid_blocks",
            "evidence_sufficient",
            "stopping_rule_reached",
            "seed_pool_exhausted",
        },
        "evidence index.seed_plan",
    )
    seed_plan = index["seed_plan"]
    executed = seed_plan["executed_seeds"]
    valid = seed_plan["valid_seeds"]
    if (
        not isinstance(executed, list)
        or not all(type(seed) is int for seed in executed)
        or not isinstance(valid, list)
        or not all(type(seed) is int for seed in valid)
    ):
        raise EvidenceIndexError("evidence index seed lists must contain integers")
    if seed_plan["minimum_valid_blocks"] != 128:
        raise EvidenceIndexError("evidence index minimum valid block count must be 128")
    sufficient = len(valid) >= seed_plan["minimum_valid_blocks"]
    if seed_plan["evidence_sufficient"] is not sufficient:
        raise EvidenceIndexError("evidence index sufficiency differs from its valid seed count")
    if seed_plan["stopping_rule_reached"] is not True:
        raise EvidenceIndexError("evidence index may only describe a reached stopping rule")
    if seed_plan["seed_pool_exhausted"] is not (not sufficient):
        raise EvidenceIndexError("evidence index pool exhaustion differs from sufficiency")
    if not isinstance(seed_plan["excluded_seed_blocks"], dict):
        raise EvidenceIndexError("evidence index excluded_seed_blocks must be an object")

    preregistration = index["preregistration"]
    expected_preregistration_fields = {
        "preregistration_id",
        "preregistration_path",
        "preregistration_sha256",
        "factorial_plan_path",
        "factorial_plan_sha256",
    }
    _require_exact_keys(
        preregistration, expected_preregistration_fields, "evidence index.preregistration"
    )
    binding = load_factorial_plan(preregistration["factorial_plan_path"])
    if preregistration != binding.report_reference():
        raise EvidenceIndexError("evidence index preregistration binding has drifted")
    informative = _validate_experimental_validity(index["experimental_validity"], binding)
    expected_eligibility = "eligible" if sufficient and informative else "ineligible"
    if index["research_claim_eligibility"] != expected_eligibility:
        raise EvidenceIndexError(
            "evidence index.research_claim_eligibility differs from evidence sufficiency/validity"
        )
    if not sufficient and executed != list(binding.seed_plan.pool):
        raise EvidenceIndexError(
            "ineligible evidence index must contain the exhausted frozen seed pool"
        )

    _require_exact_keys(index["endpoint_results"], set(ENDPOINT_FAMILIES), "endpoint_results")
    for family_id in ENDPOINT_FAMILIES:
        result = index["endpoint_results"][family_id]
        _require_exact_keys(
            result,
            {
                "status",
                "statement",
                "significant_hypotheses",
                "bh_q",
                "bh_family_size",
                "models",
            },
            f"endpoint_results.{family_id}",
        )
        regenerated = _family_conclusion(
            family_id,
            (
                {
                    "evidence_sufficient": sufficient,
                    "inference_eligible": sufficient
                    and (
                        index["experimental_validity"]["families"][family_id]["status"]
                        == "informative"
                    ),
                    "experimental_validity": index["experimental_validity"]["families"][family_id][
                        "status"
                    ],
                    "models": result["models"],
                    "bh_q": result["bh_q"],
                    "bh_family_size": result["bh_family_size"],
                    **(
                        {"reason": "all preregistered paired block contrasts are zero"}
                        if index["experimental_validity"]["families"][family_id]["status"]
                        == "degenerate"
                        else {}
                    ),
                }
                if valid
                else {
                    "evidence_sufficient": False,
                    "inference_eligible": False,
                    "reason": "no technically valid paired seed blocks",
                    "models": {},
                }
            ),
            binding=binding,
            valid_blocks=len(valid),
            evidence_sufficient=sufficient,
        )
        if result != regenerated:
            raise EvidenceIndexError(
                f"endpoint_results.{family_id} conclusion does not match its statistics"
            )
    direction_models = set(MODEL_IDS) if valid else set()
    _require_exact_keys(index["direction_asymmetry"], direction_models, "direction_asymmetry")
    for model_id in MODEL_IDS if valid else ():
        _require_exact_keys(
            index["direction_asymmetry"][model_id],
            set(CELL_IDS),
            f"direction_asymmetry.{model_id}",
        )
    if not isinstance(index["limitations"], list) or len(index["limitations"]) < 3:
        raise EvidenceIndexError("evidence index requires at least three limitations")
    if not isinstance(index["source_artifacts"], list) or {
        entry.get("artifact") for entry in index["source_artifacts"]
    } != {"progress.json", "analysis.json", "run-manifest.json"}:
        raise EvidenceIndexError("evidence index source_artifacts set is incomplete")
    if not isinstance(index["checkpoints"], list) or {
        entry.get("seed") for entry in index["checkpoints"]
    } != {str(seed) for seed in executed}:
        raise EvidenceIndexError("evidence index checkpoint set differs from executed seeds")
    paths = [*index["source_artifacts"], *index["checkpoints"]]
    for entry in paths:
        path_value = entry.get("path")
        digest = entry.get("sha256")
        if not isinstance(path_value, str) or not isinstance(digest, str) or len(digest) != 64:
            raise EvidenceIndexError("every evidence path requires a path and SHA-256")
        if require_paths:
            path = pathlib.Path(path_value)
            if not path.is_file():
                raise EvidenceIndexError(f"evidence path does not exist: {path_value}")
            if _sha256(path) != digest:
                raise EvidenceIndexError(f"evidence path SHA-256 mismatch: {path_value}")


def generate_evidence_index(
    t215_dir: str | pathlib.Path = DEFAULT_T215_DIR,
    out_path: str | pathlib.Path = DEFAULT_OUT,
) -> pathlib.Path:
    index = build_evidence_index(t215_dir)
    validate_evidence_index(index)
    out = pathlib.Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    temp = out.with_suffix(out.suffix + ".tmp")
    temp.write_text(
        json.dumps(index, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    temp.replace(out)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m market_game_sim.showcase.evidence_index")
    parser.add_argument("--t215-dir", default=str(DEFAULT_T215_DIR))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)
    output = generate_evidence_index(args.t215_dir, args.out)
    print(f"T216 evidence index written to {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
