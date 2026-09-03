"""T805/T812 integration tests for the input journal and deterministic replay."""

import json

import pytest

from market_game_sim.interactive import (
    InputAction,
    InputJournal,
    InputJournalRecord,
    JournalValidationError,
    ReasonCode,
    read_input_journal,
    replay_input_journal,
)


def _journal(session_id: str, received_at_wall: str) -> InputJournal:
    journal = InputJournal(session_id)
    journal.append(
        InputJournalRecord(
            session_id=session_id,
            input_seq=0,
            client_request_id="request-0",
            action=InputAction.PLACE_ORDER,
            payload={
                "order_id": "human-0",
                "side": "BUY",
                "order_type": "LIMIT",
                "quantity_units": 1,
                "price_ticks": 10_000,
            },
            assigned_timestamp=10,
            accepted=True,
            reason_code=ReasonCode.OK,
            received_at_wall=received_at_wall,
        )
    )
    journal.append(
        InputJournalRecord(
            session_id=session_id,
            input_seq=1,
            client_request_id="request-1",
            action=InputAction.STEP,
            payload={},
            assigned_timestamp=10_000_000_000_000,
            accepted=True,
            reason_code=ReasonCode.OK,
            received_at_wall=received_at_wall,
        )
    )
    journal.append(
        InputJournalRecord(
            session_id=session_id,
            input_seq=2,
            client_request_id="request-2",
            action=InputAction.PLACE_ORDER,
            payload=None,
            assigned_timestamp=None,
            accepted=False,
            reason_code=ReasonCode.INVALID_INPUT,
            received_at_wall=received_at_wall,
        )
    )
    return journal


def test_journal_is_canonical_and_hash_excludes_diagnostics(tmp_path) -> None:
    first = _journal("session-a", "2026-09-04T01:02:03+08:00")
    second = _journal("session-b", "2026-09-04T02:03:04+08:00")
    first_path = tmp_path / "first" / "input-journal.jsonl"
    second_path = tmp_path / "second" / "input-journal.jsonl"

    first.write(first_path)
    second.write(second_path)

    assert first.input_hash == second.input_hash
    assert first_path.read_bytes() != second_path.read_bytes()
    raw = first_path.read_bytes()
    assert raw.endswith(b"\n")
    assert b"\r" not in raw
    for line in raw.splitlines():
        assert (
            json.dumps(
                json.loads(line), ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
            == line
        )
    loaded = read_input_journal(first_path)
    assert loaded.records == first.records
    assert loaded.input_hash == first.input_hash


def test_replay_uses_saved_order_without_wall_clock_wait(tmp_path) -> None:
    path = tmp_path / "input-journal.jsonl"
    journal = _journal("session-a", "2026-09-04T01:02:03+08:00")
    journal.write(path)
    dispatched = []

    result = replay_input_journal(path, dispatched.append)

    assert [record.input_seq for record in dispatched] == [0, 1, 2]
    assert dispatched[1].assigned_timestamp == 10_000_000_000_000
    assert result.input_count == 3
    assert result.input_hash == journal.input_hash


def test_invalid_append_is_atomic_and_fresh_retry_succeeds() -> None:
    journal = InputJournal("session-a")
    invalid = InputJournalRecord(
        session_id="session-a",
        input_seq=1,
        client_request_id="request-1",
        action=InputAction.END,
        payload={},
        assigned_timestamp=1,
        accepted=True,
        reason_code=ReasonCode.OK,
        received_at_wall=None,
    )

    with pytest.raises(JournalValidationError, match="input_seq"):
        journal.append(invalid)

    assert journal.records == ()
    valid = InputJournalRecord(
        session_id="session-a",
        input_seq=0,
        client_request_id="request-0",
        action=InputAction.END,
        payload={},
        assigned_timestamp=1,
        accepted=True,
        reason_code=ReasonCode.OK,
        received_at_wall=None,
    )
    journal.append(valid)
    assert journal.records == (valid,)


@pytest.mark.xfail(strict=True, reason="T812 replay tamper checks are not implemented yet")
def test_replay_contract_rejects_truncation_and_duplicate_idempotency_key():
    pytest.fail("T812 pending")
