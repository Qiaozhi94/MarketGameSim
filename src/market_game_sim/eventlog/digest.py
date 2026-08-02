"""T206 / T206b: Event digest hash (KPI-002).

[事件 Schema §7] 事件摘要哈希
[事件 Schema E-002] 参与摘要哈希的字段（封闭清单）

Computes ``hashlib.blake2b`` over the E-002 hash projection of each
event.  The projection selects ``HASH_INCLUDE`` leaf fields (per event
type) and excludes causal foreign keys + ``event_id`` (``HASH_EXCLUDE``).

Uses ``hashlib.blake2b`` (NOT Python's built-in ``hash()`` which is
salted per process).  The hash input is the canonical serialization
(ADR-001 §7: sorted keys, no whitespace, NFC, ``ensure_ascii=False``)
of the projected dict.

T206b exercises :meth:`SchemaRegistry.check_coverage` for all 8 event
types: ``required == include ∪ exclude`` and the sets are disjoint.
"""

from __future__ import annotations

import hashlib
from typing import Any

from market_game_sim.config.serialization import canonical_serialize
from market_game_sim.schema.registry import HASH_INCLUDE, SchemaRegistry

DIGEST_SIZE = 32


def _project_structure(
    event: dict,
    structure: str,
    registry: SchemaRegistry,
) -> dict[str, Any]:
    """Project ``HASH_INCLUDE`` fields from ``event`` for ``structure``."""
    result: dict[str, Any] = {}
    for fname, fmeta in registry.get_fields(structure).items():
        if fmeta.hash_class != HASH_INCLUDE:
            continue
        if fmeta.is_leaf:
            result[fname] = event.get(fname)
        elif fmeta.value_type == "array" and fmeta.element_structure:
            elements = event.get(fname) or []
            result[fname] = [
                _project_structure(e, fmeta.element_structure, registry) for e in elements
            ]
        elif fmeta.value_type == "object" and fmeta.variants:
            obj = event.get(fname, {})
            disc_field = fmeta.discriminated_by
            variant = event.get(disc_field)
            if variant and variant in fmeta.variants:
                result[fname] = _project_structure(
                    obj, fmeta.variants[variant], registry
                )
            else:
                result[fname] = {}
        elif fmeta.value_type == "object" and fmeta.element_structure:
            obj = event.get(fname, {})
            result[fname] = _project_structure(obj, fmeta.element_structure, registry)
    return result


def event_hash_input(event: dict, registry: SchemaRegistry) -> dict[str, Any]:
    """Build the E-002 hash projection of an EVENT record.

    Combines ``EVENT_COMMON`` included fields with the event-type-specific
    included fields.  Excluded fields (``event_id``, ``run_id``, causal
    foreign keys, ``information_set``, ``internal_state``, ``submitted_at``)
    do not appear in the projection.
    """
    event_type = event["event_type"]
    projection: dict[str, Any] = {}
    projection.update(_project_structure(event, "EVENT_COMMON", registry))
    projection.update(_project_structure(event, event_type, registry))
    return projection


def event_digest(event: dict, registry: SchemaRegistry) -> bytes:
    """``blake2b`` digest of an event's E-002 hash projection (32 bytes)."""
    projection = event_hash_input(event, registry)
    return hashlib.blake2b(
        canonical_serialize(projection), digest_size=DIGEST_SIZE
    ).digest()


def event_digest_hex(event: dict, registry: SchemaRegistry) -> str:
    """Hex-encoded ``blake2b`` digest of an event."""
    return event_digest(event, registry).hex()


def rolling_digest(events: list[dict], registry: SchemaRegistry) -> bytes:
    """Rolling ``blake2b`` digest over a sequence of EVENT records.

    Each event's digest is fed into the rolling hasher in ``log_key`` order.
    Only ``record_kind = EVENT`` records should be passed (header/trailer
    are excluded per E-002).
    """
    h = hashlib.blake2b(digest_size=DIGEST_SIZE)
    for event in events:
        h.update(event_digest(event, registry))
    return h.digest()


def rolling_digest_hex(events: list[dict], registry: SchemaRegistry) -> str:
    """Hex-encoded rolling ``blake2b`` digest."""
    return rolling_digest(events, registry).hex()
