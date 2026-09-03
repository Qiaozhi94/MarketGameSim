"""Shared contract types for deterministic interactive sessions."""

from enum import StrEnum


class SessionState(StrEnum):
    """Observable lifecycle states of one interactive session."""

    CREATED = "CREATED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"


class InputAction(StrEnum):
    """Actions accepted by the interactive input journal contract."""

    PLACE_ORDER = "PLACE_ORDER"
    CANCEL_ORDER = "CANCEL_ORDER"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    STEP = "STEP"
    END = "END"


class ReasonCode(StrEnum):
    """Stable machine-readable outcomes shared with the HTTP adapter."""

    OK = "OK"
    INVALID_STATE = "INVALID_STATE"
    INVALID_INPUT = "INVALID_INPUT"
    RISK_REJECTED = "RISK_REJECTED"
    UNKNOWN_ORDER = "UNKNOWN_ORDER"
    DUPLICATE_REQUEST = "DUPLICATE_REQUEST"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    QUEUE_FULL = "QUEUE_FULL"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    ABORTED = "ABORTED"
    INTERNAL_ABORT = "INTERNAL_ABORT"
