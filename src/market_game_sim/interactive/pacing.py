"""Bounded input admission and deterministic logical-time assignment."""

import json
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from threading import Lock
from typing import Any

from market_game_sim.interactive.types import InputAction, ReasonCode


class InteractiveInputError(ValueError):
    """Base error with a stable reason code for adapter translation."""

    def __init__(self, message: str, reason_code: ReasonCode) -> None:
        super().__init__(message)
        self.reason_code = reason_code


class InboxFullError(InteractiveInputError):
    """Raised before sequencing when the bounded inbox has no free slot."""

    def __init__(self, capacity: int) -> None:
        super().__init__(
            f"interactive input inbox capacity {capacity} reached", ReasonCode.QUEUE_FULL
        )


class IdempotencyConflictError(InteractiveInputError):
    """Raised when one request id is reused for a different command."""

    def __init__(self, client_request_id: str) -> None:
        super().__init__(
            f"client_request_id {client_request_id!r} was already used for different input",
            ReasonCode.IDEMPOTENCY_CONFLICT,
        )


class InputValidationError(InteractiveInputError):
    """Raised for data that cannot enter the deterministic journal."""

    def __init__(self, message: str) -> None:
        super().__init__(message, ReasonCode.INVALID_INPUT)


class PacingError(ValueError):
    """Raised when a logical boundary would break deterministic ordering."""


@dataclass(frozen=True, slots=True)
class PendingInput:
    """An admitted input awaiting a logical timestamp."""

    input_seq: int
    client_request_id: str
    action: InputAction
    payload_json: str

    @property
    def payload(self) -> dict[str, Any]:
        """Return a detached payload so callers cannot mutate inbox state."""

        value = json.loads(self.payload_json)
        if not isinstance(value, dict):
            raise TypeError("stored interactive payload is not an object")
        return value


@dataclass(frozen=True, slots=True)
class AssignedInput:
    """An admitted input assigned to a deterministic scheduling boundary."""

    input_seq: int
    client_request_id: str
    action: InputAction
    payload_json: str
    assigned_timestamp: int

    @property
    def payload(self) -> dict[str, Any]:
        value = json.loads(self.payload_json)
        if not isinstance(value, dict):
            raise TypeError("stored interactive payload is not an object")
        return value


class InputInbox:
    """Thread-safe bounded queue with session-wide idempotency and sequencing."""

    def __init__(self, capacity: int = 64) -> None:
        if type(capacity) is not int or capacity <= 0:
            raise ValueError("capacity must be a positive integer")
        self._capacity = capacity
        self._pending: deque[PendingInput] = deque()
        self._by_request_id: dict[str, PendingInput] = {}
        self._next_input_seq = 0
        self._lock = Lock()

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    def submit(
        self,
        client_request_id: str,
        action: InputAction,
        payload: Mapping[str, Any] | None = None,
    ) -> PendingInput:
        """Admit once, return the original object on an exact retry."""

        request_id = self._validate_request_id(client_request_id)
        normalized_action = self._validate_action(action)
        payload_json = self._canonical_payload(payload)

        with self._lock:
            previous = self._by_request_id.get(request_id)
            if previous is not None:
                if previous.action is normalized_action and previous.payload_json == payload_json:
                    return previous
                raise IdempotencyConflictError(request_id)
            if len(self._pending) >= self._capacity:
                raise InboxFullError(self._capacity)

            admitted = PendingInput(
                input_seq=self._next_input_seq,
                client_request_id=request_id,
                action=normalized_action,
                payload_json=payload_json,
            )
            self._next_input_seq += 1
            self._pending.append(admitted)
            self._by_request_id[request_id] = admitted
            return admitted

    def drain(self) -> tuple[PendingInput, ...]:
        """Atomically remove all inputs present at this scheduling boundary."""

        with self._lock:
            drained = tuple(self._pending)
            self._pending.clear()
            return drained

    def peek(self) -> tuple[PendingInput, ...]:
        """Copy the current boundary without removing it."""

        with self._lock:
            return tuple(self._pending)

    def discard_prefix(self, expected: tuple[PendingInput, ...]) -> None:
        """Remove a previously peeked boundary after successful dispatch."""

        with self._lock:
            actual = tuple(self._pending)[: len(expected)]
            if actual != expected:
                raise RuntimeError("interactive inbox prefix changed during dispatch")
            for _ in expected:
                self._pending.popleft()

    @staticmethod
    def _validate_request_id(value: str) -> str:
        if not isinstance(value, str) or not value or len(value) > 128:
            raise InputValidationError("client_request_id must contain 1 to 128 characters")
        return value

    @staticmethod
    def _validate_action(value: InputAction) -> InputAction:
        if not isinstance(value, InputAction):
            raise InputValidationError("action must be an InputAction")
        return value

    @staticmethod
    def _canonical_payload(payload: Mapping[str, Any] | None) -> str:
        value: Mapping[str, Any] = {} if payload is None else payload
        if not isinstance(value, Mapping):
            raise InputValidationError("payload must be an object")
        try:
            return json.dumps(
                dict(value),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise InputValidationError(f"payload must be canonical JSON: {exc}") from exc


class LogicalPacer:
    """Assign inputs at explicit logical boundaries without reading wall time."""

    def __init__(self) -> None:
        self._last_timestamp: int | None = None
        self._last_input_seq = -1

    @property
    def last_timestamp(self) -> int | None:
        return self._last_timestamp

    @property
    def last_input_seq(self) -> int:
        return self._last_input_seq

    def assign_boundary(
        self, pending: Iterable[PendingInput], timestamp: int
    ) -> tuple[AssignedInput, ...]:
        """Assign one timestamp atomically, ordered by the existing input sequence."""

        if type(timestamp) is not int or timestamp < 0:
            raise PacingError("logical timestamp must be a non-negative integer")
        if self._last_timestamp is not None and timestamp < self._last_timestamp:
            raise PacingError("logical timestamp cannot move backwards")

        items = tuple(pending)
        previous_seq = self._last_input_seq
        for item in items:
            if item.input_seq <= previous_seq:
                raise PacingError("input_seq must be strictly increasing across boundaries")
            previous_seq = item.input_seq

        assigned = tuple(
            AssignedInput(
                input_seq=item.input_seq,
                client_request_id=item.client_request_id,
                action=item.action,
                payload_json=item.payload_json,
                assigned_timestamp=timestamp,
            )
            for item in items
        )
        self._last_timestamp = timestamp
        self._last_input_seq = previous_seq
        return assigned
