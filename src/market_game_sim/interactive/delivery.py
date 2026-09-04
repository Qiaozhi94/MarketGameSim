"""T815 single-command representative H1 interactive delivery."""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import shutil
import sys
import tempfile
from datetime import UTC, datetime

from market_game_sim import __version__
from market_game_sim.config.serialization import canonical_serialize, serialize_event
from market_game_sim.eventlog.digest import rolling_digest_hex
from market_game_sim.eventlog.writer import build_run_header
from market_game_sim.interactive.bundle import (
    build_interactive_manifest,
    write_interactive_manifest,
)
from market_game_sim.interactive.journal import InputJournal, InputJournalRecord
from market_game_sim.interactive.replay_session import replay_session
from market_game_sim.interactive.runtime import InputResult, InteractiveRuntime
from market_game_sim.interactive.types import InputAction
from market_game_sim.replay.generate import build_replay
from market_game_sim.replay.reader import read_log
from market_game_sim.schema.registry import get_registry

DEFAULT_OUT = pathlib.Path("artifacts/showcase/H1")
REBUILD_COMMAND = "python -m market_game_sim.interactive.delivery"


class InteractiveDeliveryError(OSError):
    """Stable failure raised before an incomplete bundle can be published."""

    abort_code = "INTERNAL_ABORT"


def generate_interactive_delivery(
    out_dir: str | pathlib.Path = DEFAULT_OUT,
    *,
    fail_after: str | None = None,
) -> dict[str, pathlib.Path]:
    """Build in staging and publish only a complete, self-consistent bundle."""

    destination = pathlib.Path(out_dir)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite existing bundle: {destination}")
    staging = pathlib.Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    try:
        result = _build(staging, fail_after=fail_after)
        staging.replace(destination)
        return {name: destination / path.name for name, path in result.items()}
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _build(out: pathlib.Path, *, fail_after: str | None) -> dict[str, pathlib.Path]:
    session_id = "h1-representative-s7"
    runtime = InteractiveRuntime(session_id)
    runtime.start()
    commands = [
        (
            InputAction.PLACE_ORDER,
            "h1-market",
            {
                "order_id": "human-market",
                "side": "BUY",
                "order_type": "MARKET",
                "quantity_units": 3,
                "price_ticks": None,
            },
        ),
        (
            InputAction.PLACE_ORDER,
            "h1-limit",
            {
                "order_id": "human-resting",
                "side": "SELL",
                "order_type": "LIMIT",
                "quantity_units": 1,
                "price_ticks": 10_030,
            },
        ),
        (InputAction.CANCEL_ORDER, "h1-cancel", {"order_id": "human-resting"}),
        (InputAction.STEP, "h1-step", {}),
        (InputAction.END, "h1-end", {}),
    ]
    journal = InputJournal(session_id)
    for action, request_id, payload in commands:
        result = _apply(runtime, action, request_id, payload)
        journal.append(_journal_record(session_id, action, request_id, payload, result))

    input_path = out / "input-journal.jsonl"
    journal.write(input_path)
    _fail_if(fail_after, "journal")
    event_path = out / "run.jsonl"
    config_hash = hashlib.sha256(
        canonical_serialize({"profile": "H1", "seed": 7, "initial_price_ticks": 10_000})
    ).hexdigest()
    _write_event_log(event_path, runtime, config_hash)
    _fail_if(fail_after, "event_log")
    replay_path = out / "replay.html"
    build_replay(event_path, replay_path)
    run_path = out / "RUN.md"
    run_path.write_text(_run_document(), encoding="utf-8")
    replayed = replay_session(str(input_path))
    log = read_log(event_path)
    event_hash = rolling_digest_hex(log.events, get_registry())
    manifest = build_interactive_manifest(
        out,
        {
            "run_doc": "RUN.md",
            "input_journal": "input-journal.jsonl",
            "event_log": "run.jsonl",
            "replay": "replay.html",
        },
        session_id=session_id,
        client_version="browser-v1",
        code_version=__version__,
        config_hash=config_hash,
        seed=7,
        input_hash=journal.input_hash,
        event_summary_hash=event_hash,
        frame_hash=replayed.frame_hash,
        termination_state=runtime.state.value,
        abort_code=None,
    )
    manifest_path = out / "manifest.json"
    write_interactive_manifest(manifest, manifest_path)
    return {
        "run_doc": run_path,
        "input_journal": input_path,
        "event_log": event_path,
        "replay": replay_path,
        "manifest": manifest_path,
    }


def _apply(
    runtime: InteractiveRuntime,
    action: InputAction,
    request_id: str,
    payload: dict,
) -> InputResult:
    command = {"client_request_id": request_id, **payload}
    if action is InputAction.PLACE_ORDER:
        return runtime.place_order(command)
    if action is InputAction.CANCEL_ORDER:
        return runtime.cancel_order(command)
    return runtime.control(action, request_id)


def _journal_record(
    session_id: str,
    action: InputAction,
    request_id: str,
    payload: dict,
    result: InputResult,
) -> InputJournalRecord:
    return InputJournalRecord(
        session_id=session_id,
        input_seq=result.input_seq if result.input_seq is not None else 0,
        client_request_id=request_id,
        action=action,
        payload=payload,
        assigned_timestamp=result.assigned_timestamp,
        accepted=result.accepted,
        reason_code=result.reason_code,
        received_at_wall=None,
    )


def _write_event_log(path: pathlib.Path, runtime: InteractiveRuntime, config_hash: str) -> None:
    header = build_run_header(
        run_id=runtime.session_id,
        code_version=__version__,
        config_hash=config_hash,
        master_seed=7,
        started_at_wall=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        tick_size="0.01",
        min_quantity="0.001",
        cash_unit="0.01",
        mult=runtime.adapter.mult,
        fee_bps_cap=5,
        initial_price_ticks=runtime.adapter.initial_price_ticks,
        agent_initial_bp={"human": 10_000, "maker": 10_000},
        run_mode="interactive",
    )
    events = runtime.adapter.records
    trailer = {
        "record_kind": "RUN_TRAILER",
        "terminated": "COMPLETED",
        "abort_code": None,
        "abort_detail": None,
        "last_committed_transaction_seq": max(
            (item["transaction_seq"] for item in events), default=0
        ),
        "record_count": len(events) + 2,
    }
    path.write_bytes(
        b"".join(
            [
                serialize_event(header),
                *(serialize_event(item) for item in events),
                serialize_event(trailer),
            ]
        )
    )


def _run_document() -> str:
    return (
        "# H1 Interactive Delivery\n\n"
        "## 重建\n\n"
        f"```bash\n{REBUILD_COMMAND}\n```\n\n"
        "## 查看与重放\n\n"
        "离线打开 `replay.html`；运行 "
        "`python -m market_game_sim.interactive.replay_session input-journal.jsonl` "
        "验证输入、事件与逐帧状态。\n\n"
        "本包属于 `interactive + engineering-demonstration`：合成市场、无真实资金、"
        "非交易建议，不属于正式研究证据。\n"
    )


def _fail_if(requested: str | None, stage: str) -> None:
    if requested == stage:
        raise InteractiveDeliveryError(f"INTERNAL_ABORT: injected {stage} write failure")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)
    result = generate_interactive_delivery(args.out)
    print(f"H1 interactive delivery written to {result['manifest'].parent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
