"""Canonical interactive input journal and wall-clock-free replay."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import tempfile
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from market_game_sim.config.serialization import SerializationError, canonical_serialize
from market_game_sim.interactive.types import InputAction, ReasonCode

INPUT_SCHEMA_VERSION = 1
INPUT_FIELDS = {
    "record_kind",
    "input_schema_version",
    "session_id",
    "input_seq",
    "client_request_id",
    "action",
    "payload",
    "assigned_timestamp",
    "accepted",
    "reason_code",
    "received_at_wall",
}
HEADER_FIELDS = {"record_kind", "input_schema_version", "session_id"}
TRAILER_FIELDS = {
    "record_kind",
    "input_schema_version",
    "session_id",
    "input_count",
    "input_hash",
}


class JournalValidationError(ValueError):
    """Raised when journal data violates the frozen v1 contract."""


@dataclass(frozen=True, slots=True, init=False)
class InputJournalRecord:
    """One normalized input and its final deterministic result."""

    session_id: str
    input_seq: int
    client_request_id: str
    action: InputAction
    assigned_timestamp: int | None
    accepted: bool
    reason_code: ReasonCode
    received_at_wall: str | None
    _payload_bytes: bytes = field(repr=False)

    def __init__(
        self,
        *,
        session_id: str,
        input_seq: int,
        client_request_id: str,
        action: InputAction | str,
        payload: Mapping[str, Any] | None,
        assigned_timestamp: int | None,
        accepted: bool,
        reason_code: ReasonCode | str,
        received_at_wall: str | None,
    ) -> None:
        normalized_session = _required_text(session_id, "session_id")
        normalized_request = _required_text(client_request_id, "client_request_id", maximum=128)
        if type(input_seq) is not int or input_seq < 0:
            raise JournalValidationError("input_seq must be a non-negative integer")
        try:
            normalized_action = InputAction(action)
        except (TypeError, ValueError) as exc:
            raise JournalValidationError(f"unknown input action: {action!r}") from exc
        try:
            normalized_reason = ReasonCode(reason_code)
        except (TypeError, ValueError) as exc:
            raise JournalValidationError(f"unknown reason_code: {reason_code!r}") from exc
        if type(accepted) is not bool:
            raise JournalValidationError("accepted must be a boolean")
        if accepted != (normalized_reason is ReasonCode.OK):
            raise JournalValidationError("accepted must be true exactly when reason_code is OK")
        if assigned_timestamp is not None and (
            type(assigned_timestamp) is not int or assigned_timestamp < 0
        ):
            raise JournalValidationError("assigned_timestamp must be non-negative or null")
        if accepted and assigned_timestamp is None:
            raise JournalValidationError("accepted input must have an assigned_timestamp")
        normalized_wall = _wall_timestamp(received_at_wall)
        payload_bytes = _payload_bytes(normalized_action, payload, accepted, normalized_reason)

        object.__setattr__(self, "session_id", normalized_session)
        object.__setattr__(self, "input_seq", input_seq)
        object.__setattr__(self, "client_request_id", normalized_request)
        object.__setattr__(self, "action", normalized_action)
        object.__setattr__(self, "assigned_timestamp", assigned_timestamp)
        object.__setattr__(self, "accepted", accepted)
        object.__setattr__(self, "reason_code", normalized_reason)
        object.__setattr__(self, "received_at_wall", normalized_wall)
        object.__setattr__(self, "_payload_bytes", payload_bytes)

    @property
    def payload(self) -> dict[str, Any] | None:
        if self._payload_bytes == b"null":
            return None
        value = json.loads(self._payload_bytes)
        if not isinstance(value, dict):
            raise TypeError("stored input payload is not an object")
        return value

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_kind": "INPUT",
            "input_schema_version": INPUT_SCHEMA_VERSION,
            "session_id": self.session_id,
            "input_seq": self.input_seq,
            "client_request_id": self.client_request_id,
            "action": self.action.value,
            "payload": self.payload,
            "assigned_timestamp": self.assigned_timestamp,
            "accepted": self.accepted,
            "reason_code": self.reason_code.value,
            "received_at_wall": self.received_at_wall,
        }

    def hash_projection(self) -> dict[str, Any]:
        projected = self.to_dict()
        del projected["session_id"]
        del projected["received_at_wall"]
        return projected


class InputJournal:
    """In-memory append-only journal finalized as canonical JSONL."""

    def __init__(self, session_id: str) -> None:
        self._session_id = _required_text(session_id, "session_id")
        self._records: list[InputJournalRecord] = []
        self._request_ids: set[str] = set()
        self._last_timestamp: int | None = None

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def records(self) -> tuple[InputJournalRecord, ...]:
        return tuple(self._records)

    @property
    def input_hash(self) -> str:
        digest = hashlib.sha256()
        for record in self._records:
            digest.update(canonical_serialize(record.hash_projection()))
            digest.update(b"\n")
        return digest.hexdigest()

    def append(self, record: InputJournalRecord) -> None:
        """Validate all invariants before changing append-only state."""

        if not isinstance(record, InputJournalRecord):
            raise TypeError("record must be an InputJournalRecord")
        expected_seq = len(self._records)
        if record.session_id != self._session_id:
            raise JournalValidationError("record session_id differs from journal")
        if record.input_seq != expected_seq:
            raise JournalValidationError(
                f"input_seq must be contiguous from zero; expected {expected_seq}"
            )
        if record.client_request_id in self._request_ids:
            raise JournalValidationError("client_request_id must be unique in the journal")
        timestamp = record.assigned_timestamp
        if (
            timestamp is not None
            and self._last_timestamp is not None
            and timestamp < self._last_timestamp
        ):
            raise JournalValidationError("assigned_timestamp cannot move backwards")

        self._records.append(record)
        self._request_ids.add(record.client_request_id)
        if timestamp is not None:
            self._last_timestamp = timestamp

    def to_bytes(self) -> bytes:
        header = {
            "record_kind": "INPUT_HEADER",
            "input_schema_version": INPUT_SCHEMA_VERSION,
            "session_id": self._session_id,
        }
        trailer = {
            "record_kind": "INPUT_TRAILER",
            "input_schema_version": INPUT_SCHEMA_VERSION,
            "session_id": self._session_id,
            "input_count": len(self._records),
            "input_hash": self.input_hash,
        }
        objects = [header, *(record.to_dict() for record in self._records), trailer]
        return b"".join(canonical_serialize(item) + b"\n" for item in objects)

    def write(self, path: str | pathlib.Path) -> None:
        """Atomically replace a completed journal in the destination directory."""

        destination = pathlib.Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary: pathlib.Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=destination.parent,
                prefix=f".{destination.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = pathlib.Path(handle.name)
                handle.write(self.to_bytes())
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()


@dataclass(frozen=True, slots=True)
class InputReplayResult:
    session_id: str
    input_count: int
    input_hash: str
    last_assigned_timestamp: int | None


def read_input_journal(path: str | pathlib.Path) -> InputJournal:
    """Read and fully validate a canonical v1 journal before returning it."""

    source = pathlib.Path(path)
    raw = source.read_bytes()
    if not raw.endswith(b"\n") or b"\r" in raw:
        raise JournalValidationError("journal must use canonical LF-terminated lines")
    lines = raw.split(b"\n")[:-1]
    if len(lines) < 2:
        raise JournalValidationError("journal requires INPUT_HEADER and INPUT_TRAILER")
    objects = [_parse_canonical_line(line, index + 1) for index, line in enumerate(lines)]
    header = objects[0]
    trailer = objects[-1]
    _require_exact_fields(header, HEADER_FIELDS, "INPUT_HEADER")
    _require_exact_fields(trailer, TRAILER_FIELDS, "INPUT_TRAILER")
    if header["record_kind"] != "INPUT_HEADER":
        raise JournalValidationError("first record must be INPUT_HEADER")
    if trailer["record_kind"] != "INPUT_TRAILER":
        raise JournalValidationError("last record must be INPUT_TRAILER")
    _require_v1(header)
    _require_v1(trailer)
    session_id = _required_text(header["session_id"], "session_id")
    if trailer["session_id"] != session_id:
        raise JournalValidationError("trailer session_id differs from header")

    journal = InputJournal(session_id)
    for index, item in enumerate(objects[1:-1], start=2):
        _require_exact_fields(item, INPUT_FIELDS, f"INPUT line {index}")
        if item["record_kind"] != "INPUT":
            raise JournalValidationError(f"line {index} must be INPUT")
        _require_v1(item)
        journal.append(
            InputJournalRecord(
                session_id=item["session_id"],
                input_seq=item["input_seq"],
                client_request_id=item["client_request_id"],
                action=item["action"],
                payload=item["payload"],
                assigned_timestamp=item["assigned_timestamp"],
                accepted=item["accepted"],
                reason_code=item["reason_code"],
                received_at_wall=item["received_at_wall"],
            )
        )
    if type(trailer["input_count"]) is not int or trailer["input_count"] != len(journal.records):
        raise JournalValidationError("trailer input_count differs from INPUT records")
    if trailer["input_hash"] != journal.input_hash:
        raise JournalValidationError("trailer input_hash differs from INPUT records")
    return journal


def replay_input_journal(
    path: str | pathlib.Path,
    dispatch: Callable[[InputJournalRecord], Any],
) -> InputReplayResult:
    """Dispatch recorded inputs in sequence without consulting or waiting on wall time."""

    if not callable(dispatch):
        raise TypeError("dispatch must be callable")
    journal = read_input_journal(path)
    for record in journal.records:
        dispatch(record)
    last_timestamp = next(
        (
            record.assigned_timestamp
            for record in reversed(journal.records)
            if record.assigned_timestamp is not None
        ),
        None,
    )
    return InputReplayResult(
        session_id=journal.session_id,
        input_count=len(journal.records),
        input_hash=journal.input_hash,
        last_assigned_timestamp=last_timestamp,
    )


def _required_text(value: object, field_name: str, maximum: int | None = None) -> str:
    if not isinstance(value, str) or not value:
        raise JournalValidationError(f"{field_name} must be a non-empty string")
    normalized = unicodedata.normalize("NFC", value)
    if maximum is not None and len(normalized) > maximum:
        raise JournalValidationError(f"{field_name} must contain at most {maximum} characters")
    return normalized


def _wall_timestamp(value: object) -> str | None:
    if value is None:
        return None
    normalized = _required_text(value, "received_at_wall")
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise JournalValidationError("received_at_wall must be an RFC 3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise JournalValidationError("received_at_wall must include a timezone")
    return normalized


def _payload_bytes(
    action: InputAction,
    payload: Mapping[str, Any] | None,
    accepted: bool,
    reason_code: ReasonCode,
) -> bytes:
    if payload is None:
        if accepted or reason_code is not ReasonCode.INVALID_INPUT:
            raise JournalValidationError("null payload is only valid for INVALID_INPUT rejection")
        return b"null"
    if not isinstance(payload, Mapping):
        raise JournalValidationError("payload must be an object or null")
    normalized = dict(payload)
    if action is InputAction.PLACE_ORDER:
        expected = {"order_id", "side", "order_type", "quantity_units", "price_ticks"}
        if set(normalized) != expected:
            raise JournalValidationError("PLACE_ORDER payload has an invalid field set")
        _required_text(normalized["order_id"], "payload.order_id")
        if type(normalized["side"]) is not str or normalized["side"] not in {"BUY", "SELL"}:
            raise JournalValidationError("payload.side must be BUY or SELL")
        if type(normalized["order_type"]) is not str or normalized["order_type"] not in {
            "LIMIT",
            "MARKET",
        }:
            raise JournalValidationError("payload.order_type must be LIMIT or MARKET")
        if type(normalized["quantity_units"]) is not int or normalized["quantity_units"] <= 0:
            raise JournalValidationError("payload.quantity_units must be a positive integer")
        price = normalized["price_ticks"]
        if normalized["order_type"] == "LIMIT" and (type(price) is not int or price <= 0):
            raise JournalValidationError("LIMIT payload.price_ticks must be a positive integer")
        if normalized["order_type"] == "MARKET" and price is not None:
            raise JournalValidationError("MARKET payload.price_ticks must be null")
    elif action is InputAction.CANCEL_ORDER:
        if set(normalized) != {"order_id"}:
            raise JournalValidationError("CANCEL_ORDER payload must contain only order_id")
        _required_text(normalized["order_id"], "payload.order_id")
    elif normalized:
        raise JournalValidationError("control action payload must be an empty object")
    try:
        return canonical_serialize(normalized)
    except (SerializationError, TypeError, ValueError) as exc:
        raise JournalValidationError(f"payload is not canonical JSON: {exc}") from exc


def _parse_canonical_line(line: bytes, line_number: int) -> dict[str, Any]:
    try:
        decoded = line.decode("utf-8")
        value = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JournalValidationError(f"invalid JSON at line {line_number}") from exc
    if not isinstance(value, dict):
        raise JournalValidationError(f"line {line_number} must be a JSON object")
    try:
        canonical = canonical_serialize(value)
    except (SerializationError, TypeError, ValueError) as exc:
        raise JournalValidationError(f"invalid canonical value at line {line_number}") from exc
    if canonical != line:
        raise JournalValidationError(f"line {line_number} is not canonical JSON")
    return value


def _require_exact_fields(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise JournalValidationError(f"{label} fields differ from the v1 contract")


def _require_v1(value: Mapping[str, Any]) -> None:
    version = value["input_schema_version"]
    if type(version) is not int or version != INPUT_SCHEMA_VERSION:
        raise JournalValidationError("unsupported input_schema_version")
