"""Tests for the interactive session state machine and its single writer."""

import pytest

from market_game_sim.interactive import (
    InputAction,
    ReasonCode,
    SessionController,
    SessionDispatchError,
    SessionState,
    SessionTransitionError,
)


def test_session_starts_paused_and_invalid_start_is_atomic() -> None:
    session = SessionController("session-1", dispatch=lambda inputs: None)

    assert session.view().state is SessionState.CREATED
    started = session.start()

    assert started.state is SessionState.PAUSED
    assert started.snapshot_revision == 1

    with pytest.raises(SessionTransitionError) as exc_info:
        session.start()

    assert exc_info.value.reason_code is ReasonCode.INVALID_STATE
    assert session.view() == started


def test_resume_pause_step_and_end_follow_the_state_machine() -> None:
    dispatched = []
    session = SessionController("session-1", dispatch=dispatched.append)
    session.start()
    session.submit("request-1", InputAction.PLACE_ORDER, {"quantity": 1})
    session.submit("request-2", InputAction.CANCEL_ORDER, {"order_id": "o-1"})

    assigned = session.step(10)

    assert [item.input_seq for item in assigned] == [0, 1]
    assert {item.assigned_timestamp for item in assigned} == {10}
    assert dispatched == [assigned]
    assert session.view().state is SessionState.PAUSED
    assert session.view().processed_transactions == 1

    session.resume()
    assert session.view().state is SessionState.RUNNING
    session.pause()
    assert session.view().state is SessionState.PAUSED
    session.end()
    assert session.view().state is SessionState.COMPLETED


def test_step_is_only_legal_while_paused() -> None:
    session = SessionController("session-1", dispatch=lambda inputs: None)
    session.start()
    session.resume()
    before = session.view()

    with pytest.raises(SessionTransitionError) as exc_info:
        session.step(1)

    assert exc_info.value.reason_code is ReasonCode.INVALID_STATE
    assert session.view() == before


def test_invalid_logical_boundary_keeps_pending_input() -> None:
    session = SessionController("session-1", dispatch=lambda inputs: None)
    session.start()
    session.step(10)
    session.submit("request-1", InputAction.PLACE_ORDER, {})

    with pytest.raises(ValueError, match="cannot move backwards"):
        session.step(9)

    assert session.view().pending_inputs == 1
    assert session.view().logical_timestamp == 10
    assert session.view().processed_transactions == 1


def test_transaction_budget_completes_the_session() -> None:
    session = SessionController("session-1", dispatch=lambda inputs: None, max_transactions=2)
    session.start()

    session.step(1)
    session.step(2)

    assert session.view().state is SessionState.COMPLETED
    assert session.view().processed_transactions == 2
    with pytest.raises(SessionTransitionError):
        session.resume()


def test_dispatch_failure_aborts_and_preserves_the_cause() -> None:
    def fail_dispatch(inputs: object) -> None:
        raise RuntimeError("kernel transaction failed")

    session = SessionController("session-1", dispatch=fail_dispatch)
    session.start()
    session.submit("request-1", InputAction.PLACE_ORDER, {})

    with pytest.raises(SessionDispatchError, match="kernel transaction failed") as exc_info:
        session.step(1)

    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert session.view().state is SessionState.ABORTED
    assert session.view().processed_transactions == 0
