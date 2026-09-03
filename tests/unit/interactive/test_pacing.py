"""Tests for deterministic interactive input admission and logical-time pacing."""

import pytest

from market_game_sim.interactive import (
    IdempotencyConflictError,
    InboxFullError,
    InputAction,
    InputInbox,
    LogicalPacer,
    PacingError,
    ReasonCode,
)


def test_same_boundary_uses_input_sequence_as_the_tie_breaker() -> None:
    inbox = InputInbox()
    pacer = LogicalPacer()
    first = inbox.submit("request-1", InputAction.PLACE_ORDER, {"side": "BUY"})
    second = inbox.submit("request-2", InputAction.CANCEL_ORDER, {"order_id": "o-1"})

    assigned = pacer.assign_boundary(inbox.drain(), timestamp=42)

    assert [item.input_seq for item in assigned] == [first.input_seq, second.input_seq]
    assert [item.assigned_timestamp for item in assigned] == [42, 42]


def test_timestamp_regression_is_rejected_without_advancing_the_clock() -> None:
    pacer = LogicalPacer()
    pacer.assign_boundary((), timestamp=10)

    with pytest.raises(PacingError):
        pacer.assign_boundary((), timestamp=9)

    assert pacer.last_timestamp == 10


def test_same_request_is_idempotent_but_changed_payload_conflicts() -> None:
    inbox = InputInbox()
    original_payload = {"quantity": 1, "nested": {"value": 2}}
    first = inbox.submit("request-1", InputAction.PLACE_ORDER, original_payload)
    original_payload["quantity"] = 99

    duplicate = inbox.submit(
        "request-1", InputAction.PLACE_ORDER, {"nested": {"value": 2}, "quantity": 1}
    )

    assert duplicate is first
    assert duplicate.payload == {"nested": {"value": 2}, "quantity": 1}
    assert inbox.pending_count == 1

    with pytest.raises(IdempotencyConflictError) as exc_info:
        inbox.submit("request-1", InputAction.PLACE_ORDER, {"quantity": 2})

    assert exc_info.value.reason_code is ReasonCode.IDEMPOTENCY_CONFLICT
    assert inbox.pending_count == 1


def test_capacity_rejection_does_not_consume_input_sequence() -> None:
    inbox = InputInbox(capacity=2)
    inbox.submit("request-1", InputAction.PLACE_ORDER, {})
    inbox.submit("request-2", InputAction.PLACE_ORDER, {})

    with pytest.raises(InboxFullError) as exc_info:
        inbox.submit("request-3", InputAction.PLACE_ORDER, {})

    assert exc_info.value.reason_code is ReasonCode.QUEUE_FULL
    inbox.drain()
    admitted = inbox.submit("request-3", InputAction.PLACE_ORDER, {})
    assert admitted.input_seq == 2


def test_pacer_rejects_non_monotonic_input_sequence_atomically() -> None:
    inbox = InputInbox()
    first = inbox.submit("request-1", InputAction.PLACE_ORDER, {})
    second = inbox.submit("request-2", InputAction.PLACE_ORDER, {})
    pacer = LogicalPacer()

    with pytest.raises(PacingError):
        pacer.assign_boundary((second, first), timestamp=1)

    assert pacer.last_timestamp is None
    assert pacer.last_input_seq == -1
