"""T104: Canonical JSONL serialization (ADR-001 §7).

Produces byte-deterministic JSON following a subset of RFC 8785 (JSON
Canonicalization Scheme):

  - Numeric values are JSON **integers** -- ``float`` is rejected.
  - Missing values are ``null`` (never NaN, Infinity, or empty string).
  - Booleans are ``true`` / ``false``.
  - Encoding is UTF-8 without BOM; strings are NFC-normalized;
    non-ASCII is **not** escaped (``ensure_ascii=False``).
  - Object keys are sorted by Unicode code point (``sort_keys=True``).
  - Separators are exactly ``,`` and ``:`` (no whitespace).
  - Each event occupies one line terminated by a single LF (no CRLF).

Two calls on the same input must produce byte-identical output.
"""

from __future__ import annotations

import json
import unicodedata
from typing import Any


class SerializationError(Exception):
    """Raised when input violates ADR-001 §7 serialization rules."""


def _reject_floats(obj: Any, path: str = "root") -> None:
    """Walk the object tree and reject any ``float`` value."""
    if isinstance(obj, float):
        raise SerializationError(f"Float value at '{path}'; ADR-001 §7 requires JSON integers only")
    if isinstance(obj, dict):
        for k, v in obj.items():
            _reject_floats(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _reject_floats(v, f"{path}[{i}]")


def _nfc_normalize(obj: Any) -> Any:
    """Recursively NFC-normalize all strings (keys and values)."""
    if isinstance(obj, str):
        return unicodedata.normalize("NFC", obj)
    if isinstance(obj, dict):
        return {unicodedata.normalize("NFC", k): _nfc_normalize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_nfc_normalize(item) for item in obj]
    if isinstance(obj, tuple):
        return [_nfc_normalize(item) for item in obj]
    return obj


def canonical_serialize(obj: Any) -> bytes:
    """Serialize *obj* to canonical JSON bytes (no trailing newline).

    Raises :class:`SerializationError` if any ``float`` value is found.
    Raises :class:`ValueError` if NaN or Infinity is found.
    """
    _reject_floats(obj)
    normalized = _nfc_normalize(obj)
    text = json.dumps(
        normalized,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )
    return text.encode("utf-8")


def serialize_event(event: Any) -> bytes:
    """Serialize a single event to canonical JSON bytes with a trailing LF."""
    return canonical_serialize(event) + b"\n"


def serialize_events(events: list[Any]) -> bytes:
    """Serialize multiple events to canonical JSONL bytes.

    Each event occupies exactly one line terminated by a single LF.
    An empty list produces empty bytes.
    """
    if not events:
        return b""
    return b"".join(serialize_event(e) for e in events)
