"""Strict, wall-clock-free replay of a completed interactive input journal."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from typing import Any

from market_game_sim.config.serialization import canonical_serialize
from market_game_sim.interactive.journal import InputJournalRecord, read_input_journal
from market_game_sim.interactive.runtime import InputResult, InteractiveRuntime
from market_game_sim.interactive.types import InputAction, ReasonCode


class SessionReplayError(ValueError):
    """Raised before a replay can claim deterministic equivalence."""


@dataclass(frozen=True, slots=True)
class SessionReplayResult:
    session_id: str
    input_hash: str
    input_count: int
    event_hash: str
    frame_hash: str
    termination_state: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "input_hash": self.input_hash,
            "input_count": self.input_count,
            "event_hash": self.event_hash,
            "frame_hash": self.frame_hash,
            "termination_state": self.termination_state,
        }


def replay_session(path: str) -> SessionReplayResult:
    journal = read_input_journal(path)
    runtime = InteractiveRuntime(journal.session_id)
    runtime.start()
    frames: list[dict[str, Any]] = [runtime.view()]
    for record in journal.records:
        result = _dispatch(runtime, record)
        if result.accepted != record.accepted or result.reason_code is not record.reason_code:
            raise SessionReplayError(
                f"input_seq {record.input_seq} result mismatch: "
                f"expected {record.reason_code.value}, got {result.reason_code.value}"
            )
        frames.append(runtime.view())
    event_hash = _hash_objects(runtime.adapter.records)
    frame_hash = _hash_objects(frames)
    return SessionReplayResult(
        session_id=journal.session_id,
        input_hash=journal.input_hash,
        input_count=len(journal.records),
        event_hash=event_hash,
        frame_hash=frame_hash,
        termination_state=runtime.state.value,
    )


def _dispatch(runtime: InteractiveRuntime, record: InputJournalRecord) -> InputResult:
    payload = record.payload
    if payload is None:
        return InputResult(
            record.input_seq,
            False,
            ReasonCode.INVALID_INPUT,
            None,
            (),
            runtime.snapshot_revision,
        )
    command = {"client_request_id": record.client_request_id, **payload}
    if record.action is InputAction.PLACE_ORDER:
        return runtime.place_order(command)
    if record.action is InputAction.CANCEL_ORDER:
        return runtime.cancel_order(command)
    return runtime.control(record.action, record.client_request_id)


def _hash_objects(objects: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for item in objects:
        digest.update(canonical_serialize(item))
        digest.update(b"\n")
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_journal")
    args = parser.parse_args(argv)
    try:
        result = replay_session(args.input_journal)
    except (OSError, ValueError) as exc:
        print(f"replay failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
