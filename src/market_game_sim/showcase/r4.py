"""T217 / gate R4: formal flagship result bundle.

Consumes the T216 index plus its verified T215 checkpoint set and produces a
portable R4 bundle under ``artifacts/showcase/R4``.  Representative replay
selection is outcome-independent: first valid seed, linear model, LL cell.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from market_game_sim.experiment.config import compute_config_hash
from market_game_sim.experiment.factorial import (
    CELL_IDS,
    CONTRASTS,
    ENDPOINT_FAMILIES,
    METRICS,
    MODEL_IDS,
    event_summary_sha256,
    load_factorial_plan,
)
from market_game_sim.experiment.runner import RunResult
from market_game_sim.metrics.liquidation import LiquidationMetrics, RunClassification
from market_game_sim.replay.downsample import DownsampleRule
from market_game_sim.replay.generate import build_replay
from market_game_sim.showcase.evidence_index import (
    EVIDENCE_CLASS,
    RUN_FAMILY,
    validate_evidence_index,
)
from market_game_sim.showcase.formal import _read_checkpoint
from market_game_sim.showcase.manifest import (
    build_showcase_manifest,
    validate_showcase_manifest,
    write_showcase_manifest,
)
from market_game_sim.showcase.preview import _write_run_log, build_preview_configs

GATE = "R4"
PRODUCER = "0.1.5 T217"
DEFAULT_EVIDENCE_INDEX = pathlib.Path("docs/experiments/0.1.5-evidence-index.json")
DEFAULT_OUT = pathlib.Path("artifacts/showcase/R4")
MAX_REPLAY_BYTES = 5 * 1024 * 1024

COMPARISON_NAME = "comparison.json"
EVIDENCE_COPY_NAME = "evidence-index.json"
LOG_NAME = "replay-run.jsonl"
REPLAY_NAME = "replay.html"
SUMMARY_NAME = "summary.md"
RUN_DOC_NAME = "RUN.md"
MANIFEST_NAME = "manifest.json"

REPRESENTATIVE_MODEL = MODEL_IDS[0]
REPRESENTATIVE_CELL = CELL_IDS[0]

REQUIRED_SUMMARY_SECTIONS = (
    "## 运行族与研究资格",
    "## 三终点正式结果",
    "## 效应量与不确定性",
    "## 方向不对称",
    "## 排除与停止规则",
    "## 代表性回放",
    "## 限制与失效边界",
)


class R4BundleError(RuntimeError):
    """Formal R4 bundle input or output violates the frozen contract."""


def _read_object(path: pathlib.Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise R4BundleError(f"cannot read {label} at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise R4BundleError(f"{label} must be an object")
    return value


def _result_from_payload(payload: dict[str, Any]) -> RunResult:
    expected = {
        "seed",
        "terminated",
        "abort_code",
        "events",
        "book_last_ticks",
        "classification",
        "group_label",
        "event_summary_sha256",
    }
    if set(payload) != expected:
        raise R4BundleError("representative checkpoint result fields do not match schema v2")
    result = RunResult(
        seed=payload["seed"],
        terminated=payload["terminated"],
        abort_code=payload["abort_code"],
        events=payload["events"],
        book_last_ticks=payload["book_last_ticks"],
        accounts={},
        liquidation_metrics=LiquidationMetrics(),
        classification=RunClassification(**payload["classification"]),
        group_label=payload["group_label"],
    )
    if event_summary_sha256(result) != payload["event_summary_sha256"]:
        raise R4BundleError("representative checkpoint event digest mismatch")
    if result.classification.is_technical_invalid or result.terminated != "COMPLETED":
        raise R4BundleError("representative run must be technically valid and COMPLETED")
    return result


def _select_representative(index: dict[str, Any]) -> tuple[int, str, str]:
    valid = index["seed_plan"]["valid_seeds"]
    if not valid:
        raise R4BundleError("evidence index has no valid seed for representative replay")
    return valid[0], REPRESENTATIVE_MODEL, REPRESENTATIVE_CELL


def _load_representative(
    index: dict[str, Any], seed: int, model_id: str, cell_id: str
) -> tuple[RunResult, Any]:
    entry = next(
        (item for item in index["checkpoints"] if item["seed"] == str(seed)),
        None,
    )
    if entry is None:
        raise R4BundleError(f"evidence index has no checkpoint for representative seed {seed}")
    body = _read_checkpoint(pathlib.Path(entry["path"]))
    fixed = {
        "schema_version": 2,
        "evidence_class": EVIDENCE_CLASS,
        "run_family": RUN_FAMILY,
        "seed": seed,
        "exclusion_codes": [],
    }
    for field, expected in fixed.items():
        if body.get(field) != expected:
            raise R4BundleError(
                f"representative checkpoint.{field} must be {expected!r}, got {body.get(field)!r}"
            )
    try:
        payload = body["primary_runs"][model_id][cell_id]
        audit_digest = body["audit_event_summary_sha256"][model_id][cell_id]
        config_digest = body["config_hashes"][model_id][cell_id]
    except (KeyError, TypeError) as exc:
        raise R4BundleError("representative checkpoint lacks the frozen model/cell") from exc
    result = _result_from_payload(payload)
    if audit_digest != payload["event_summary_sha256"]:
        raise R4BundleError("representative checkpoint TI-2 rerun digest does not match primary")

    binding = load_factorial_plan(index["preregistration"]["factorial_plan_path"])
    config = build_preview_configs(seed, binding)[model_id][cell_id]
    if compute_config_hash(config) != config_digest:
        raise R4BundleError("representative checkpoint config hash does not match frozen config")
    return result, config


def _build_bounded_replay(log_path: pathlib.Path, replay_path: pathlib.Path) -> int:
    build_replay(log_path, replay_path)
    if replay_path.stat().st_size <= MAX_REPLAY_BYTES:
        return 1
    keep_every = 2
    while keep_every <= 1_048_576:
        build_replay(
            log_path,
            replay_path,
            downsample=DownsampleRule(keep_every=keep_every),
        )
        if replay_path.stat().st_size <= MAX_REPLAY_BYTES:
            return keep_every
        keep_every *= 2
    raise R4BundleError("representative replay remains larger than 5 MB after downsampling")


def _render_summary(
    index: dict[str, Any], *, seed: int, model_id: str, cell_id: str, keep_every: int
) -> str:
    lines = [
        "# 0.1.5 正式旗舰实验结果 — Gate R4",
        "",
        "## 运行族与研究资格",
        "",
        f"- 运行族：`{index['run_family']}`",
        f"- 证据类别：`{index['evidence_class']}`",
        f"- 研究声明资格：`{index['research_claim_eligibility']}`",
        f"- 目标模型：`{MODEL_IDS[0]}`（主）与 `{MODEL_IDS[1]}`（稳健性）",
        "- 制度处理：`L(low/high) × M(low/high)` 四 cell；三终点分别推断。",
        "",
        "## 三终点正式结果",
        "",
    ]
    for family_id in ENDPOINT_FAMILIES:
        result = index["endpoint_results"][family_id]
        lines.extend(
            [
                f"### {family_id}",
                "",
                f"- 判定：`{result['status']}`",
                f"- 条件性结论：{result['statement']}",
                "",
            ]
        )

    lines.extend(
        [
            "## 效应量与不确定性",
            "",
            "下表逐项报告预注册效应、percentile bootstrap 95% CI、双侧 sign-flip p 值与 "
            "BH 调整值。",
            "",
            "| family | model | metric | contrast | effect | 95% CI | p | BH p | significant |",
            "|---|---|---|---|---:|---|---:|---:|---|",
        ]
    )
    for family_id in ENDPOINT_FAMILIES:
        models = index["endpoint_results"][family_id]["models"]
        for current_model in MODEL_IDS:
            for metric in METRICS:
                for contrast in CONTRASTS:
                    effect = models[current_model][metric][contrast]
                    lines.append(
                        f"| {family_id} | {current_model} | {metric} | {contrast} "
                        f"| {effect['effect']:.6f} "
                        f"| [{effect['ci_low']:.6f}, {effect['ci_high']:.6f}] "
                        f"| {effect['p_value']:.6f} | {effect['bh_adjusted_p_value']:.6f} "
                        f"| {str(effect['bh_significant']).lower()} |"
                    )
    lines.extend(["", "## 方向不对称", ""])
    lines.extend(
        [
            "`crash occurrence − surge occurrence`；该量是预注册描述量，不另产生 p 值。",
            "",
            "| model | cell | effect | 95% CI |",
            "|---|---|---:|---|",
        ]
    )
    for current_model in MODEL_IDS:
        for current_cell in CELL_IDS:
            effect = index["direction_asymmetry"][current_model][current_cell]
            lines.append(
                f"| {current_model} | {current_cell} | {effect['effect']:.6f} "
                f"| [{effect['ci_low']:.6f}, {effect['ci_high']:.6f}] |"
            )
    excluded = index["seed_plan"]["excluded_seed_blocks"]
    lines.extend(
        [
            "",
            "## 排除与停止规则",
            "",
            f"- 执行 block：{len(index['seed_plan']['executed_seeds'])}",
            f"- 有效 block：{len(index['seed_plan']['valid_seeds'])}",
            f"- 排除 block：{len(excluded)}",
            "- 达到冻结的 128 个有效 block 后停止；未按结果方向、p 值或 CI 追加样本。",
            "",
            "## 代表性回放",
            "",
            f"- 选择规则：第一个有效 seed；`{model_id}`；`{cell_id}`。",
            f"- 代表运行：seed `{seed}`，run_id `exp-s{seed}`。",
            f"- 降采样：`keep_every={keep_every}`（1 表示未降采样）。",
            "- 该规则不读取终点、效应或显著性，不构成结果导向挑选。",
            "",
            "## 限制与失效边界",
            "",
        ]
    )
    lines.extend(f"- {limitation}" for limitation in index["limitations"])
    lines.extend(
        [
            "- 本 R4 包依赖 T215 原始 checkpoint；正式交付入口与仓库内回放由 T220/R5 生成。",
            "",
        ]
    )
    return "\n".join(lines)


def _render_run_doc(rebuild_command: str) -> str:
    return (
        "# Formal Flagship Bundle — Gate R4\n\n"
        "## 重建命令\n\n"
        f"```bash\n{rebuild_command}\n```\n\n"
        "## 输入边界\n\n"
        "仅接受由 T216 验证的 `SPONTANEOUS + formal-research` evidence index 与其绑定的 "
        "T215 checkpoint。任何路径、哈希、运行族、证据类别或条件性结论漂移都会失败。\n\n"
        "## 产物\n\n"
        f"- `{SUMMARY_NAME}` — 三终点条件性结论与 36 项正式效应/不确定性\n"
        f"- `{COMPARISON_NAME}` — 机器可读正式结果\n"
        f"- `{EVIDENCE_COPY_NAME}` — 本次使用的 evidence index 快照\n"
        f"- `{REPLAY_NAME}` — ≤5 MB 单文件离线代表性回放\n"
        f"- `{MANIFEST_NAME}` — 可复现 provenance 与产物摘要\n"
    )


def _assert_summary(text: str) -> None:
    missing = [section for section in REQUIRED_SUMMARY_SECTIONS if section not in text]
    if missing:
        raise R4BundleError(f"R4 summary is missing required sections: {missing}")


def generate_r4_bundle(
    out_dir: str | pathlib.Path = DEFAULT_OUT,
    *,
    evidence_index_path: str | pathlib.Path = DEFAULT_EVIDENCE_INDEX,
    rebuild_command: str | None = None,
) -> dict[str, Any]:
    out = pathlib.Path(out_dir)
    evidence_path = pathlib.Path(evidence_index_path)
    index = _read_object(evidence_path, "T216 evidence index")
    validate_evidence_index(index)
    if index["run_family"] != RUN_FAMILY or index["evidence_class"] != EVIDENCE_CLASS:
        raise R4BundleError("R4 only accepts SPONTANEOUS + formal-research")
    seed, model_id, cell_id = _select_representative(index)
    result, config = _load_representative(index, seed, model_id, cell_id)
    out.mkdir(parents=True, exist_ok=True)

    evidence_copy = out / EVIDENCE_COPY_NAME
    evidence_copy.write_bytes(evidence_path.read_bytes())
    comparison = {
        "schema_version": 1,
        "producer": PRODUCER,
        "gate": GATE,
        "run_family": RUN_FAMILY,
        "evidence_class": EVIDENCE_CLASS,
        "research_claim_eligibility": index["research_claim_eligibility"],
        "preregistration": index["preregistration"],
        "seed_plan": index["seed_plan"],
        "endpoint_results": index["endpoint_results"],
        "direction_asymmetry": index["direction_asymmetry"],
        "limitations": index["limitations"],
    }
    comparison_path = out / COMPARISON_NAME
    comparison_path.write_text(
        json.dumps(comparison, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    log_path = out / LOG_NAME
    _write_run_log(
        log_path,
        result,
        config,
        run_id=f"exp-s{seed}",
        tick_size="0.01",
        min_quantity="0.001",
        cash_unit="0.01",
        started_at_wall="1970-01-01T00:00:00Z",
    )
    replay_path = out / REPLAY_NAME
    keep_every = _build_bounded_replay(log_path, replay_path)
    if replay_path.stat().st_size > MAX_REPLAY_BYTES:
        raise R4BundleError("representative replay exceeds the 5 MB contract")

    if rebuild_command is None:
        rebuild_command = (
            "python -m market_game_sim.showcase.r4 "
            f"--evidence-index {evidence_path.as_posix()} --out {out.as_posix()}"
        )
    summary_text = _render_summary(
        index,
        seed=seed,
        model_id=model_id,
        cell_id=cell_id,
        keep_every=keep_every,
    )
    _assert_summary(summary_text)
    summary_path = out / SUMMARY_NAME
    summary_path.write_text(summary_text, encoding="utf-8")
    run_doc_path = out / RUN_DOC_NAME
    run_doc_path.write_text(_render_run_doc(rebuild_command), encoding="utf-8")

    entries = [
        {"artifact_id": "comparison", "path": COMPARISON_NAME, "format": "json"},
        {"artifact_id": "evidence_index", "path": EVIDENCE_COPY_NAME, "format": "json"},
        {"artifact_id": "replay_log", "path": LOG_NAME, "format": "jsonl"},
        {"artifact_id": "replay", "path": REPLAY_NAME, "format": "html"},
        {"artifact_id": "summary", "path": SUMMARY_NAME, "format": "markdown"},
        {"artifact_id": "run_doc", "path": RUN_DOC_NAME, "format": "markdown"},
    ]
    artifact_entries = [{**entry, "producer": PRODUCER} for entry in entries]
    manifest = build_showcase_manifest(
        out,
        artifact_entries,
        code_version=index["code"]["package_version"],
        config_hash=index["code"]["config_hash"],
        seed=seed,
        seed_plan={
            "n_seeds": len(index["seed_plan"]["executed_seeds"]),
            "seeds": index["seed_plan"]["executed_seeds"],
        },
        evidence_class=EVIDENCE_CLASS,
        gate=GATE,
    )
    validate_showcase_manifest(manifest)
    manifest_path = write_showcase_manifest(manifest, out / MANIFEST_NAME)
    return {
        "out_dir": out,
        "comparison": comparison_path,
        "evidence_index": evidence_copy,
        "log": log_path,
        "replay": replay_path,
        "summary": summary_path,
        "run_doc": run_doc_path,
        "manifest": manifest_path,
        "representative_seed": seed,
        "representative_model": model_id,
        "representative_cell": cell_id,
        "replay_keep_every": keep_every,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m market_game_sim.showcase.r4")
    parser.add_argument("--evidence-index", default=str(DEFAULT_EVIDENCE_INDEX))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)
    command = (
        "python -m market_game_sim.showcase.r4 "
        f"--evidence-index {args.evidence_index} --out {args.out}"
    )
    result = generate_r4_bundle(
        args.out,
        evidence_index_path=args.evidence_index,
        rebuild_command=command,
    )
    print(
        f"R4 formal bundle written to {result['out_dir']} "
        f"(representative seed={result['representative_seed']}, "
        f"replay={result['replay'].stat().st_size} bytes)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
