"""ADR-015: the economic projection of an event log.

Frozen evidence binds full event-log digests.  An L1 fix that only adds or
removes *market-data bookkeeping* (``MARKET_DATA_PUBLISH`` records and the
cursor fields that point at them) changes those digests without changing a
single order, fill, cancel, margin call or decision.  ADR-015 allows rebinding
frozen evidence in exactly that case, and this module is the definition of
"exactly that case".

The projection is an **exclusion list**, not a whitelist: every record and every
field is kept except the ones listed below.  A whitelist would silently ignore
any field nobody thought to list; an exclusion list makes every unexpected
difference count.  Changing what is excluded is a change to ADR-015 itself and
must bump :data:`PROJECTION_VERSION`.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

PROJECTION_VERSION = 1

EXCLUDED_EVENT_TYPES = frozenset({"MARKET_DATA_PUBLISH"})
# Fields whose value is the identity or time of a MARKET_DATA_PUBLISH record.
EXCLUDED_FIELDS = frozenset(
    {"market_data_event_id", "cursor_from_event_id", "cursor_to_event_id", "observed_at"}
)
# decision_evidence mirrors the observation cursor it consumed.
EXCLUDED_NESTED = {"decision_evidence": frozenset({"cursor_from_event_id", "cursor_to_event_id"})}


def _strip(record: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in record.items() if k not in EXCLUDED_FIELDS}
    for key, nested in EXCLUDED_NESTED.items():
        value = out.get(key)
        if isinstance(value, dict):
            out[key] = {k: v for k, v in value.items() if k not in nested}
    return out


def project(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every record except market-data bookkeeping, in log order."""
    return [_strip(e) for e in events if e.get("event_type") not in EXCLUDED_EVENT_TYPES]


def economic_digest(events: list[dict[str, Any]]) -> str:
    """sha256 of the canonical JSON of :func:`project` (key order independent)."""
    blob = json.dumps(project(events), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
