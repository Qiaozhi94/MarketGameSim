"""T203 (FR-027): single-command showcase bundle generator + CLI.

One command produces the whole R1 bundle under ``artifacts/showcase/latest/``::

    python -m market_game_sim.showcase.generate <config.yaml>

Pipeline (reuses existing layers, no duplication):

  parse config -> build_experiment_config -> run_one (single seed)
    -> write raw event log JSONL (build_run_header + serialize_event + trailer)
    -> build_replay (single-file offline HTML) from that log
    -> render summary.md (with the mandatory 不可作结论 disclaimer)
    -> write RUN.md (rebuild command + boundary statement)
    -> write manifest.json (code_version / config_hash / seed / evidence_class
       + per-artifact blake2b hashes)

``evidence_class`` is fixed to ``engineering-demonstration``; this module
never writes into ``docs/experiments/`` (that is R5/T220's job).
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from datetime import UTC, datetime
from typing import Any

from market_game_sim import __version__
from market_game_sim.bench.runner import build_experiment_config
from market_game_sim.config.parser import parse_config
from market_game_sim.config.serialization import serialize_event
from market_game_sim.eventlog.writer import build_run_header
from market_game_sim.experiment.config import ExperimentConfig, compute_config_hash
from market_game_sim.experiment.runner import RunResult, run_one
from market_game_sim.ledger.account import initial_margin_bp_for_tier
from market_game_sim.replay.generate import build_replay
from market_game_sim.showcase.manifest import build_showcase_manifest, write_showcase_manifest
from market_game_sim.showcase.summary import assert_disclaimer_present, render_summary

EVIDENCE_CLASS = "engineering-demonstration"
PRODUCER = "0.1.5 T203"

#: Fixed bundle file names (design.md §6: RUN.md / manifest.json / replay.html /
#: summary.md + a raw event log).
LOG_NAME = "run.jsonl"
REPLAY_NAME = "replay.html"
SUMMARY_NAME = "summary.md"
RUN_DOC_NAME = "RUN.md"
MANIFEST_NAME = "manifest.json"

DEFAULT_OUT = pathlib.Path("artifacts/showcase/latest")
DEFAULT_REBUILD = "python -m market_game_sim.showcase.generate <config.yaml>"


def _agent_initial_bp(config: ExperimentConfig) -> dict[str, int]:
    return {s.agent_id: initial_margin_bp_for_tier(s.leverage_tier) for s in config.agent_specs}


def _build_trailer(result: RunResult) -> dict[str, Any]:
    max_txn = max(
        (e["transaction_seq"] for e in result.events if "transaction_seq" in e),
        default=2,
    )
    return {
        "record_kind": "RUN_TRAILER",
        "terminated": result.terminated,
        "abort_code": result.abort_code,
        "abort_detail": None,
        "last_committed_transaction_seq": max_txn,
        "record_count": 2 + len(result.events),
    }


def _write_run_log(
    path: pathlib.Path,
    result: RunResult,
    config: ExperimentConfig,
    *,
    tick_size: str,
    min_quantity: str,
    cash_unit: str,
) -> None:
    header = build_run_header(
        run_id=f"exp-s{config.seed}",
        code_version=__version__,
        config_hash=compute_config_hash(config),
        master_seed=config.seed,
        started_at_wall=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        tick_size=tick_size,
        min_quantity=min_quantity,
        cash_unit=cash_unit,
        mult=config.mult,
        fee_bps_cap=max(config.maker_bps, config.taker_bps, 0),
        initial_price_ticks=config.initial_price_ticks,
        agent_initial_bp=_agent_initial_bp(config),
        run_mode="benchmark",
    )
    trailer = _build_trailer(result)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(serialize_event(header))
        for record in result.events:
            f.write(serialize_event(record))
        f.write(serialize_event(trailer))


def _render_run_doc(*, gate: str, rebuild_command: str) -> str:
    return (
        f"# Showcase Bundle -- Gate {gate}\n"
        "\n"
        "## 重建命令\n"
        "\n"
        "```bash\n"
        f"{rebuild_command}\n"
        "```\n"
        "\n"
        "## 边界声明\n"
        "\n"
        "本成果包为工程示范（evidence_class=engineering-demonstration），仅证明"
        "端到端管线（配置 → 内核运行 → 事件日志 → 回放 → 摘要 → 清单）可一键"
        "产出可观察产物。它不构成研究结论、效应量主张或可外推的统计判断，不"
        "写入 `docs/experiments/` 正式证据索引（那是 R5/T220 的职责）。\n"
        "\n"
        "## 产物\n"
        "\n"
        f"- `{LOG_NAME}` — 原始事件日志（RUN_HEADER + EVENT × N + RUN_TRAILER）\n"
        f"- `{REPLAY_NAME}` — 单文件离线回放\n"
        f"- `{SUMMARY_NAME}` — 摘要与「不可作结论」声明\n"
        f"- `{MANIFEST_NAME}` — provenance + 产物清单\n"
    )


def build_showcase_bundle(
    config: ExperimentConfig,
    out_dir: str | pathlib.Path,
    *,
    tick_size: str = "0.01",
    min_quantity: str = "0.001",
    cash_unit: str = "0.01",
    gate: str = "R1",
    rebuild_command: str = DEFAULT_REBUILD,
    config_source: str | None = None,
) -> dict[str, Any]:
    """Produce the full R1 showcase bundle (5 files) into ``out_dir``.

    Returns a dict with the produced file paths and the run summary fields.
    """
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    result = run_one(config)
    if result.terminated == "ABORTED":
        raise RuntimeError(
            f"showcase run aborted (abort_code={result.abort_code}); "
            "cannot build a demonstration bundle from a failed run"
        )

    log_path = out / LOG_NAME
    _write_run_log(
        log_path,
        result,
        config,
        tick_size=tick_size,
        min_quantity=min_quantity,
        cash_unit=cash_unit,
    )

    replay_path = out / REPLAY_NAME
    build_replay(log_path, replay_path)

    summary_text = render_summary(
        run_id=f"exp-s{config.seed}",
        terminated=result.terminated,
        event_count=len(result.events),
        liquidation_count=result.liquidation_metrics.total_liquidations,
        code_version=__version__,
        config_hash=compute_config_hash(config),
        seed=config.seed,
        gate=gate,
        evidence_class=EVIDENCE_CLASS,
        rebuild_command=rebuild_command,
        config_source=config_source,
    )
    assert_disclaimer_present(summary_text)
    summary_path = out / SUMMARY_NAME
    summary_path.write_text(summary_text, encoding="utf-8")

    run_doc_path = out / RUN_DOC_NAME
    run_doc_path.write_text(
        _render_run_doc(gate=gate, rebuild_command=rebuild_command), encoding="utf-8"
    )

    artifact_entries = [
        {"artifact_id": "run_log", "path": LOG_NAME, "format": "jsonl", "producer": PRODUCER},
        {"artifact_id": "replay", "path": REPLAY_NAME, "format": "html", "producer": PRODUCER},
        {
            "artifact_id": "summary",
            "path": SUMMARY_NAME,
            "format": "markdown",
            "producer": PRODUCER,
        },
        {
            "artifact_id": "run_doc",
            "path": RUN_DOC_NAME,
            "format": "markdown",
            "producer": PRODUCER,
        },
    ]
    manifest = build_showcase_manifest(
        out,
        artifact_entries,
        code_version=__version__,
        config_hash=compute_config_hash(config),
        seed=config.seed,
        # R018-C012 (Round 3): FR-027 requires the frozen seed plan in the
        # manifest.  A single-seed showcase states it explicitly instead of
        # pretending the scalar seed is the whole design.
        seed_plan=getattr(config, "seed_plan", None)
        or {
            "n_seeds": 1,
            "seeds": [config.seed],
        },
        run_mode="benchmark",
        evidence_class=EVIDENCE_CLASS,
        gate=gate,
    )
    write_showcase_manifest(manifest, out / MANIFEST_NAME)

    return {
        "out_dir": out,
        "log": log_path,
        "replay": replay_path,
        "summary": summary_path,
        "run_doc": run_doc_path,
        "manifest": out / MANIFEST_NAME,
        "run_id": f"exp-s{config.seed}",
        "terminated": result.terminated,
        "event_count": len(result.events),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m market_game_sim.showcase.generate")
    parser.add_argument("config", help="bench-style YAML config path")
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help=f"output directory (default: {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--gate",
        default="R1",
        help="achievement gate label written into manifest (default: R1)",
    )
    args = parser.parse_args(argv)

    parsed = parse_config(args.config)
    config = build_experiment_config(parsed)
    rebuild = f"python -m market_game_sim.showcase.generate {args.config}"
    result = build_showcase_bundle(
        config,
        args.out,
        tick_size=str(parsed.market.tick_size),
        min_quantity=str(parsed.market.min_quantity),
        cash_unit=str(parsed.market.cash_unit),
        gate=args.gate,
        rebuild_command=rebuild,
        config_source=args.config,
    )
    print(f"showcase bundle written to {result['out_dir']}")
    print(
        f"  run_id={result['run_id']} terminated={result['terminated']} "
        f"events={result['event_count']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
