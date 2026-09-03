"""T807: single-command H1-A headless interactive demonstration bundle."""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import shutil
import sys
import tempfile
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from market_game_sim import __version__
from market_game_sim.config.serialization import canonical_serialize, serialize_event
from market_game_sim.eventlog.digest import rolling_digest_hex
from market_game_sim.eventlog.writer import build_run_header
from market_game_sim.experiment.config import compute_config_hash
from market_game_sim.experiment.runner import RunResult, run_one
from market_game_sim.interactive.bundle import (
    build_interactive_manifest,
    write_interactive_manifest,
)
from market_game_sim.interactive.journal import InputJournal, InputJournalRecord
from market_game_sim.interactive.types import InputAction, ReasonCode
from market_game_sim.ledger.account import initial_margin_bp_for_tier
from market_game_sim.replay.frames import _build_frames
from market_game_sim.replay.generate import build_replay
from market_game_sim.replay.reader import read_log
from market_game_sim.schema.registry import get_registry
from market_game_sim.showcase.r2 import build_r2_config

DEFAULT_OUT = pathlib.Path("artifacts/showcase/H1-A")
REBUILD_COMMAND = "python -m market_game_sim.interactive.headless"
HUMAN_AGENT_ID = "human"
HUMAN_WALLET_UNITS = 1_000_000


def generate_headless_bundle(out_dir: str | pathlib.Path = DEFAULT_OUT) -> dict[str, pathlib.Path]:
    """Generate and validate all H1-A files in staging before publishing."""

    destination = pathlib.Path(out_dir)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite existing bundle directory: {destination}")
    staging = pathlib.Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    try:
        result = _build_in_staging(staging)
        staging.replace(destination)
        return {name: destination / path.name for name, path in result.items()}
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _build_in_staging(out: pathlib.Path) -> dict[str, pathlib.Path]:
    config = build_r2_config()
    config.extra_accounts[HUMAN_AGENT_ID] = HUMAN_WALLET_UNITS
    result = run_one(config)
    if result.terminated != "COMPLETED":
        raise RuntimeError(f"headless interactive run did not complete: {result.abort_code}")

    session_id = f"exp-s{config.seed}"
    config_hash = compute_config_hash(config)
    event_log = out / "run.jsonl"
    _write_event_log(event_log, result, config_hash, config)

    final_timestamp = max(
        (
            event.get("timestamp", 0)
            for event in result.events
            if type(event.get("timestamp")) is int
        ),
        default=0,
    )
    journal = InputJournal(session_id)
    for input_seq, action, timestamp in (
        (0, InputAction.RESUME, 0),
        (1, InputAction.END, final_timestamp),
    ):
        journal.append(
            InputJournalRecord(
                session_id=session_id,
                input_seq=input_seq,
                client_request_id=f"headless-{input_seq}",
                action=action,
                payload={},
                assigned_timestamp=timestamp,
                accepted=True,
                reason_code=ReasonCode.OK,
                received_at_wall=None,
            )
        )
    input_path = out / "input-journal.jsonl"
    journal.write(input_path)

    replay_path = out / "replay.html"
    build_replay(event_log, replay_path)
    run_doc = out / "RUN.md"
    run_doc.write_text(_run_document(destination_hint=DEFAULT_OUT), encoding="utf-8")

    log = read_log(event_log)
    event_hash = rolling_digest_hex(log.events, get_registry())
    frame_hash = _frame_hash(log)
    manifest = build_interactive_manifest(
        out,
        {
            "run_doc": "RUN.md",
            "input_journal": "input-journal.jsonl",
            "event_log": "run.jsonl",
            "replay": "replay.html",
        },
        session_id=session_id,
        client_version="headless-v1",
        code_version=__version__,
        config_hash=config_hash,
        seed=config.seed,
        input_hash=journal.input_hash,
        event_summary_hash=event_hash,
        frame_hash=frame_hash,
        termination_state=result.terminated,
        abort_code=result.abort_code,
    )
    manifest_path = out / "manifest.json"
    write_interactive_manifest(manifest, manifest_path)
    return {
        "run_doc": run_doc,
        "input_journal": input_path,
        "event_log": event_log,
        "replay": replay_path,
        "manifest": manifest_path,
    }


def _write_event_log(
    path: pathlib.Path,
    result: RunResult,
    config_hash: str,
    config: Any,
) -> None:
    header = build_run_header(
        run_id=f"exp-s{config.seed}",
        code_version=__version__,
        config_hash=config_hash,
        master_seed=config.seed,
        started_at_wall=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        tick_size="0.01",
        min_quantity="0.001",
        cash_unit="0.01",
        mult=config.mult,
        fee_bps_cap=max(config.maker_bps, config.taker_bps, 0),
        initial_price_ticks=config.initial_price_ticks,
        agent_initial_bp={
            spec.agent_id: initial_margin_bp_for_tier(spec.leverage_tier)
            for spec in config.agent_specs
        }
        | {HUMAN_AGENT_ID: 10_000},
        run_mode="interactive",
    )
    max_transaction = max(
        (event["transaction_seq"] for event in result.events),
        default=2,
    )
    trailer = {
        "record_kind": "RUN_TRAILER",
        "terminated": result.terminated,
        "abort_code": result.abort_code,
        "abort_detail": None,
        "last_committed_transaction_seq": max_transaction,
        "record_count": len(result.events) + 2,
    }
    path.write_bytes(
        b"".join(
            [
                serialize_event(header),
                *(serialize_event(event) for event in result.events),
                serialize_event(trailer),
            ]
        )
    )


def _frame_hash(log: Any) -> str:
    frames = _build_frames(
        log.events,
        mult=log.config.mult,
        fee_bps_cap=log.config.fee_bps_cap,
        initial_price_ticks=log.config.initial_price_ticks,
        agent_initial_bp=log.config.agent_initial_bp,
    )
    digest = hashlib.sha256()
    for frame in frames:
        digest.update(canonical_serialize(asdict(frame)))
        digest.update(b"\n")
    return digest.hexdigest()


def _run_document(*, destination_hint: pathlib.Path) -> str:
    return (
        "# H1-A Headless Interactive Session\n\n"
        "## 重建\n\n"
        "```bash\n"
        f"{REBUILD_COMMAND} --out {destination_hint.as_posix()}\n"
        "```\n\n"
        "## 查看\n\n"
        "离线打开 `replay.html`，并使用 `input-journal.jsonl` 审计 RESUME/END 输入。\n\n"
        "## 边界\n\n"
        "本包标记为 `interactive + engineering-demonstration`，使用合成市场、无真实资金，"
        "不构成研究结论、交易建议或正式研究证据。\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=REBUILD_COMMAND)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)
    result = generate_headless_bundle(args.out)
    print(f"H1-A headless bundle written to {result['manifest'].parent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
