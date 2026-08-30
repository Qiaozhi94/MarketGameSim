"""T220 / gate R5: repository-visible v0.1 research delivery.

The command consumes the committed T216 evidence index, reproduces the
outcome-independent representative run from frozen code/config/seed inputs,
and writes both the ignored R5 bundle and the repository delivery files::

    python -m market_game_sim.showcase.r5

Raw T215 checkpoints are deliberately not required for this delivery rebuild.
The index must still bind to the current package source, frozen
preregistration, complete statistics, and ``SPONTANEOUS + formal-research``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import tempfile
from typing import Any

from market_game_sim.experiment.factorial import (
    CELL_IDS,
    MODEL_IDS,
    event_summary_sha256,
    load_factorial_plan,
    validate_flagship_configs,
)
from market_game_sim.experiment.runner import RunResult, run_one
from market_game_sim.showcase.evidence_index import (
    EVIDENCE_CLASS,
    RUN_FAMILY,
    validate_evidence_index,
)
from market_game_sim.showcase.manifest import (
    build_showcase_manifest,
    validate_showcase_manifest,
    write_showcase_manifest,
)
from market_game_sim.showcase.preview import _write_run_log, build_preview_configs
from market_game_sim.showcase.r4 import MAX_REPLAY_BYTES, _build_bounded_replay, _render_summary

GATE = "R5"
PRODUCER = "0.1.5 T220"
DEFAULT_EVIDENCE_INDEX = pathlib.Path("docs/experiments/0.1.5-evidence-index.json")
DEFAULT_OUT = pathlib.Path("artifacts/showcase/R5")
DEFAULT_DOCS_DIR = pathlib.Path("docs/experiments")

REPLAY_NAME = "replay.html"
SUMMARY_NAME = "summary.md"
RUN_DOC_NAME = "RUN.md"
EVIDENCE_COPY_NAME = "evidence-index.json"
MANIFEST_NAME = "manifest.json"
BUNDLE_FILES = (
    EVIDENCE_COPY_NAME,
    MANIFEST_NAME,
    REPLAY_NAME,
    RUN_DOC_NAME,
    SUMMARY_NAME,
)

DOC_REPORT_NAME = "0.1.5-flagship-report.md"
DOC_REPLAY_NAME = "0.1.5-representative-replay.html"
DOC_EVIDENCE_NAME = "0.1.5-evidence-index.json"

REPRESENTATIVE_MODEL = MODEL_IDS[0]
REPRESENTATIVE_CELL = CELL_IDS[0]


class R5DeliveryError(RuntimeError):
    """The R5 input or generated delivery violates the frozen contract."""


def _read_object(path: pathlib.Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise R5DeliveryError(f"cannot read {label} at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise R5DeliveryError(f"{label} must be an object")
    return value


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_write_bytes(path: pathlib.Path, payload: bytes) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(payload)
    temp.replace(path)
    return path


def _representative_run(index: dict[str, Any]) -> tuple[int, str, str, RunResult, Any]:
    valid_seeds = index["seed_plan"]["valid_seeds"]
    if not valid_seeds:
        raise R5DeliveryError("eligible R5 evidence requires a valid representative seed")
    seed = valid_seeds[0]
    binding = load_factorial_plan(index["preregistration"]["factorial_plan_path"])
    configs = build_preview_configs(seed, binding)
    validate_flagship_configs(configs, binding)
    config = configs[REPRESENTATIVE_MODEL][REPRESENTATIVE_CELL]
    primary = run_one(config)
    audit = run_one(config)
    if event_summary_sha256(primary) != event_summary_sha256(audit):
        raise R5DeliveryError("representative deterministic rerun digest mismatch")
    if primary.terminated != "COMPLETED" or primary.classification.is_technical_invalid:
        raise R5DeliveryError("representative run must be technically valid and COMPLETED")
    return seed, REPRESENTATIVE_MODEL, REPRESENTATIVE_CELL, primary, config


def _render_r5_report(
    index: dict[str, Any],
    *,
    seed: int,
    model_id: str,
    cell_id: str,
    keep_every: int,
    evidence_sha256: str,
    replay_link: str,
    evidence_link: str,
) -> str:
    base = _render_summary(
        index,
        seed=seed,
        model_id=model_id,
        cell_id=cell_id,
        keep_every=keep_every,
    )
    base = base.replace(
        "# 0.1.5 正式旗舰实验结果 — Gate R4",
        "# 0.1.5 正式旗舰实验研究交付 — Gate R5",
        1,
    ).replace(
        "- 本 R4 包依赖 T215 原始 checkpoint；正式交付入口与仓库内回放由 T220/R5 生成。",
        "- 本 R5 交付由已提交 evidence index 与同源码、同配置、同 seed 的双次确定性重放生成。",
        1,
    )
    lines = [
        base.rstrip(),
        "",
        "## 版本签收",
        "",
        f"- 里程碑：`{index['milestone']}`；成果门：`R5`。",
        f"- 包版本：`{index['code']['package_version']}`。",
        f"- 源码摘要：`{index['code']['source_tree_sha256']}`。",
        f"- 配置摘要：`{index['code']['config_hash']}`。",
        f"- 正式 evidence index SHA-256：`{evidence_sha256}`。",
        f"- 研究声明资格：`{index['research_claim_eligibility']}`；证据类别：`formal-research`。",
        "",
        "## 交付入口",
        "",
        f"- [代表性离线回放]({replay_link})",
        f"- [正式 evidence index]({evidence_link})",
        "",
    ]
    return "\n".join(lines)


def _render_run_doc(rebuild_command: str) -> str:
    return (
        "# v0.1 Research Delivery — Gate R5\n\n"
        "## 重建命令\n\n"
        f"```bash\n{rebuild_command}\n```\n\n"
        "## 输入边界\n\n"
        "命令仅接受与当前源码和冻结预注册一致的 `SPONTANEOUS + formal-research` "
        "evidence index。clean checkout 不需要被忽略的 `artifacts/`：代表运行由冻结配置与 "
        "seed 重新执行两次并比较事件摘要。\n\n"
        "## 固定产物\n\n"
        f"- `{SUMMARY_NAME}` — 正式结果、限制与版本签收\n"
        f"- `{REPLAY_NAME}` — ≤5 MB 单文件离线代表性回放\n"
        f"- `{EVIDENCE_COPY_NAME}` — 正式 evidence index 快照\n"
        f"- `{MANIFEST_NAME}` — 代码、配置、seed plan、证据类与产物摘要\n"
    )


def generate_r5_delivery(
    out_dir: str | pathlib.Path = DEFAULT_OUT,
    *,
    evidence_index_path: str | pathlib.Path = DEFAULT_EVIDENCE_INDEX,
    docs_dir: str | pathlib.Path = DEFAULT_DOCS_DIR,
    rebuild_command: str | None = None,
) -> dict[str, Any]:
    """Generate the R5 bundle and repository-visible delivery in one call."""
    out = pathlib.Path(out_dir)
    docs = pathlib.Path(docs_dir)
    evidence_path = pathlib.Path(evidence_index_path)
    index = _read_object(evidence_path, "T216 evidence index")
    validate_evidence_index(index, require_paths=False)
    if index["run_family"] != RUN_FAMILY or index["evidence_class"] != EVIDENCE_CLASS:
        raise R5DeliveryError("R5 only accepts SPONTANEOUS + formal-research evidence")
    if index["research_claim_eligibility"] != "eligible":
        raise R5DeliveryError("R5 research delivery requires eligible formal evidence")

    seed, model_id, cell_id, result, config = _representative_run(index)
    out.mkdir(parents=True, exist_ok=True)
    docs.mkdir(parents=True, exist_ok=True)
    evidence_bytes = evidence_path.read_bytes()
    evidence_sha256 = _sha256(evidence_path)
    evidence_copy = _atomic_write_bytes(out / EVIDENCE_COPY_NAME, evidence_bytes)
    docs_evidence = docs / DOC_EVIDENCE_NAME
    if docs_evidence.resolve() != evidence_path.resolve():
        _atomic_write_bytes(docs_evidence, evidence_bytes)

    replay_path = out / REPLAY_NAME
    with tempfile.TemporaryDirectory(prefix="market-game-sim-r5-") as temp_dir:
        log_path = pathlib.Path(temp_dir) / "representative-run.jsonl"
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
        keep_every = _build_bounded_replay(log_path, replay_path)
    if replay_path.stat().st_size > MAX_REPLAY_BYTES:
        raise R5DeliveryError("representative replay exceeds the 5 MB delivery contract")
    docs_replay = _atomic_write_bytes(docs / DOC_REPLAY_NAME, replay_path.read_bytes())

    if rebuild_command is None:
        rebuild_command = "python -m market_game_sim.showcase.r5"
    summary_text = _render_r5_report(
        index,
        seed=seed,
        model_id=model_id,
        cell_id=cell_id,
        keep_every=keep_every,
        evidence_sha256=evidence_sha256,
        replay_link=REPLAY_NAME,
        evidence_link=EVIDENCE_COPY_NAME,
    )
    summary = _atomic_write_bytes(out / SUMMARY_NAME, summary_text.encode("utf-8"))
    report_text = _render_r5_report(
        index,
        seed=seed,
        model_id=model_id,
        cell_id=cell_id,
        keep_every=keep_every,
        evidence_sha256=evidence_sha256,
        replay_link=DOC_REPLAY_NAME,
        evidence_link=DOC_EVIDENCE_NAME,
    )
    report = _atomic_write_bytes(docs / DOC_REPORT_NAME, report_text.encode("utf-8"))
    _atomic_write_bytes(out / RUN_DOC_NAME, _render_run_doc(rebuild_command).encode("utf-8"))

    entries = [
        {"artifact_id": "evidence_index", "path": EVIDENCE_COPY_NAME, "format": "json"},
        {"artifact_id": "replay", "path": REPLAY_NAME, "format": "html"},
        {"artifact_id": "summary", "path": SUMMARY_NAME, "format": "markdown"},
        {"artifact_id": "run_doc", "path": RUN_DOC_NAME, "format": "markdown"},
    ]
    manifest = build_showcase_manifest(
        out,
        [{**entry, "producer": PRODUCER} for entry in entries],
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
    if {path.name for path in out.iterdir() if path.is_file()} != set(BUNDLE_FILES):
        raise R5DeliveryError("R5 bundle file set differs from the frozen contract")
    return {
        "out_dir": out,
        "docs_dir": docs,
        "manifest": manifest_path,
        "summary": summary,
        "report": report,
        "replay": replay_path,
        "docs_replay": docs_replay,
        "evidence_copy": evidence_copy,
        "representative_seed": seed,
        "replay_keep_every": keep_every,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m market_game_sim.showcase.r5")
    parser.add_argument("--evidence-index", default=str(DEFAULT_EVIDENCE_INDEX))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--docs-dir", default=str(DEFAULT_DOCS_DIR))
    args = parser.parse_args(argv)
    command = "python -m market_game_sim.showcase.r5"
    result = generate_r5_delivery(
        args.out,
        evidence_index_path=args.evidence_index,
        docs_dir=args.docs_dir,
        rebuild_command=command,
    )
    print(
        f"R5 delivery written to {result['out_dir']} and {result['docs_dir']} "
        f"(representative seed={result['representative_seed']}, "
        f"replay={result['replay'].stat().st_size} bytes)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
