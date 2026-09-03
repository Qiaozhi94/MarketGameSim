"""Single-writer state machine for one deterministic interactive session."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from threading import RLock
from typing import Any

from market_game_sim.interactive.pacing import AssignedInput, InputInbox, LogicalPacer, PendingInput
from market_game_sim.interactive.types import InputAction, ReasonCode, SessionState

Dispatch = Callable[[tuple[AssignedInput, ...]], None]


class SessionTransitionError(RuntimeError):
    """Raised when a command is not legal in the current lifecycle state."""

    reason_code = ReasonCode.INVALID_STATE


class SessionDispatchError(RuntimeError):
    """Raised after a failed scheduling unit has aborted the session."""

    reason_code = ReasonCode.INTERNAL_ABORT


@dataclass(frozen=True, slots=True)
class SessionView:
    """Small immutable snapshot of controller-owned state."""

    session_id: str
    state: SessionState
    snapshot_revision: int
    processed_transactions: int
    pending_inputs: int
    logical_timestamp: int | None


class SessionController:
    """Serialize state mutation and dispatch admitted inputs at logical boundaries."""

    def __init__(
        self,
        session_id: str,
        *,
        dispatch: Dispatch,
        max_transactions: int = 80,
        inbox_capacity: int = 64,
    ) -> None:
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("session_id must be a non-empty string")
        if type(max_transactions) is not int or max_transactions <= 0:
            raise ValueError("max_transactions must be a positive integer")
        if not callable(dispatch):
            raise TypeError("dispatch must be callable")

        self._session_id = session_id
        self._dispatch = dispatch
        self._max_transactions = max_transactions
        self._inbox = InputInbox(inbox_capacity)
        self._pacer = LogicalPacer()
        self._state = SessionState.CREATED
        self._snapshot_revision = 0
        self._processed_transactions = 0
        self._lock = RLock()

    def view(self) -> SessionView:
        with self._lock:
            return SessionView(
                session_id=self._session_id,
                state=self._state,
                snapshot_revision=self._snapshot_revision,
                processed_transactions=self._processed_transactions,
                pending_inputs=self._inbox.pending_count,
                logical_timestamp=self._pacer.last_timestamp,
            )

    def submit(
        self,
        client_request_id: str,
        action: InputAction,
        payload: Mapping[str, Any] | None = None,
    ) -> PendingInput:
        """Queue a client input without directly mutating kernel state."""

        with self._lock:
            if self._state in {SessionState.COMPLETED, SessionState.ABORTED}:
                self._invalid("submit")
            return self._inbox.submit(client_request_id, action, payload)

    def start(self) -> SessionView:
        """Bootstrap into the configured default PAUSED mode."""

        with self._lock:
            self._require(SessionState.CREATED, "start")
            self._transition(SessionState.PAUSED)
            return self.view()

    def resume(self) -> SessionView:
        with self._lock:
            self._require(SessionState.PAUSED, "resume")
            self._transition(SessionState.RUNNING)
            return self.view()

    def pause(self) -> SessionView:
        with self._lock:
            self._require(SessionState.RUNNING, "pause")
            self._transition(SessionState.PAUSED)
            return self.view()

    def step(self, boundary_timestamp: int) -> tuple[AssignedInput, ...]:
        """Dispatch exactly one scheduling unit and remain paused."""

        with self._lock:
            self._require(SessionState.PAUSED, "step")
            return self._dispatch_boundary(boundary_timestamp)

    def advance(self, boundary_timestamp: int) -> tuple[AssignedInput, ...]:
        """Dispatch one unit while continuous RUNNING pacing is active."""

        with self._lock:
            self._require(SessionState.RUNNING, "advance")
            return self._dispatch_boundary(boundary_timestamp)

    def end(self) -> SessionView:
        with self._lock:
            if self._state not in {SessionState.RUNNING, SessionState.PAUSED}:
                self._invalid("end")
            self._transition(SessionState.COMPLETED)
            return self.view()

    def abort(self) -> SessionView:
        with self._lock:
            if self._state in {SessionState.COMPLETED, SessionState.ABORTED}:
                self._invalid("abort")
            self._transition(SessionState.ABORTED)
            return self.view()

    def _dispatch_boundary(self, boundary_timestamp: int) -> tuple[AssignedInput, ...]:
        pending = self._inbox.peek()
        assigned = self._pacer.assign_boundary(pending, boundary_timestamp)
        try:
            self._dispatch(assigned)
        except Exception as exc:
            self._transition(SessionState.ABORTED)
            raise SessionDispatchError(f"interactive dispatch failed: {exc}") from exc

        self._inbox.discard_prefix(pending)
        self._processed_transactions += 1
        self._snapshot_revision += 1
        if self._processed_transactions >= self._max_transactions:
            self._state = SessionState.COMPLETED
        return assigned

    def _require(self, expected: SessionState, operation: str) -> None:
        if self._state is not expected:
            self._invalid(operation)

    def _invalid(self, operation: str) -> None:
        raise SessionTransitionError(f"cannot {operation} while session is {self._state.value}")

    def _transition(self, target: SessionState) -> None:
        self._state = target
        self._snapshot_revision += 1
