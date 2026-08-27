"""T210: StressProtocolV1 + four-cell identical-path validation (AC-004).

The stress protocol (ADR-003 §3.2) is a finite, typed, versioned event
series applied **identically** to all four institutional cells.  The shape
is frozen in ``schema/goal_contract_v2.json`` ``structures.StressProtocolV1``
(``schema_version`` / ``protocol_id`` / ``events`` / ``reads_run_outcome``)
with two invariants:

- ``events`` is finite and event-for-event identical across the four cells;
- ``reads_run_outcome`` is always ``false`` -- the protocol must not read the
  running result to extend / shorten / alter the shock (ADR-003 §3.2).

Every stress trigger is recorded with ``EXOGENOUS_STRESS`` provenance
(``DecisionEvidenceV1.trigger_provenance``), which is the audit marker that
keeps STRESS evidence out of spontaneous conclusions (FR-023 / TR-502).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


class StressProtocolError(ValueError):
    """Raised when a stress protocol violates its frozen invariants."""


@dataclass(frozen=True)
class StressEvent:
    """One typed stress event in the protocol series.

    ``event_type`` is a closed set the stress runner knows how to execute
    (e.g. a market order injection); ``params`` carries the typed payload.
    The whole series is finite (ADR-003 §3.2: 冲击必须有限).
    """

    event_type: str
    timestamp_ns: int
    params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # R018-C006 (Round 5): exact type checks (int excludes bool), and
        # params validated by the protocol's per-type spec.
        if type(self.timestamp_ns) is not int or self.timestamp_ns < 0:
            raise StressProtocolError(
                f"timestamp_ns must be a non-negative int, got {self.timestamp_ns!r}"
            )
        if not isinstance(self.params, dict):
            raise StressProtocolError(f"params must be a dict, got {type(self.params).__name__}")


#: Closed set of stress event types the runner can execute (R018-C006:
#: unknown event types must be rejected, not silently ignored).
STRESS_EVENT_TYPES = frozenset({"MARKET_ORDER"})

#: Per-type param spec: required keys, value types, enum / range (R018-C006,
#: Round 5: precise type + required + enum/range validation).
_STRESS_EVENT_PARAMS: dict[str, dict] = {
    "MARKET_ORDER": {
        "required": frozenset({"side", "quantity_units"}),
        "types": {
            "side": str,
            "quantity_units": int,
        },
        "enums": {"side": frozenset({"BUY", "SELL"})},
        "ranges": {"quantity_units": (1, None)},
    },
}


def _validate_params(event_type: str, params: dict) -> None:
    """Validate params against the per-type spec: closed keys, required
    presence, exact types, enum values and numeric ranges."""
    spec = _STRESS_EVENT_PARAMS[event_type]
    allowed_keys = set(spec["types"])
    unknown = set(params) - allowed_keys
    if unknown:
        raise StressProtocolError(
            f"{event_type} params has unknown keys {sorted(unknown)}; "
            f"allowed: {sorted(allowed_keys)}"
        )
    missing = spec["required"] - set(params)
    if missing:
        raise StressProtocolError(f"{event_type} params missing required keys {sorted(missing)}")
    for key, value in params.items():
        expected = spec["types"][key]
        if expected is int:
            if type(value) is not int:
                raise StressProtocolError(
                    f"{event_type}.params.{key} must be int, got {type(value).__name__}"
                )
            lo, hi = spec.get("ranges", {}).get(key, (None, None))
            if lo is not None and value < lo:
                raise StressProtocolError(f"{event_type}.params.{key} must be >= {lo}, got {value}")
            if hi is not None and value > hi:
                raise StressProtocolError(f"{event_type}.params.{key} must be <= {hi}, got {value}")
        elif not isinstance(value, expected):
            raise StressProtocolError(
                f"{event_type}.params.{key} must be {expected}, got {type(value).__name__}"
            )
        enum = spec.get("enums", {}).get(key)
        if enum is not None and value not in enum:
            raise StressProtocolError(
                f"{event_type}.params.{key} must be one of {sorted(enum)}, got {value!r}"
            )


@dataclass(frozen=True)
class StressProtocolV1:
    """StressProtocolV1 (goal_contract_v2.json::structures).

    ``reads_run_outcome`` is frozen to ``False`` (ADR-003 §3.2: the protocol
    must not read the running result).  ``events`` is a finite ordered list.
    ``schema_version`` must be exactly 1 and each event's type + params must
    be from the closed sets (R018-C006).
    """

    protocol_id: str
    events: tuple[StressEvent, ...]
    schema_version: int = 1
    reads_run_outcome: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise StressProtocolError(f"schema_version must be 1, got {self.schema_version}")
        if not self.protocol_id:
            raise StressProtocolError("protocol_id must be non-empty")
        if self.reads_run_outcome:
            raise StressProtocolError(
                "reads_run_outcome must be false (ADR-003 §3.2: the protocol "
                "must not read the running result)"
            )
        for i, ev in enumerate(self.events):
            if ev.event_type not in STRESS_EVENT_TYPES:
                raise StressProtocolError(
                    f"events[{i}].event_type {ev.event_type!r} not in closed set "
                    f"{sorted(STRESS_EVENT_TYPES)}"
                )
            _validate_params(ev.event_type, ev.params)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "protocol_id": self.protocol_id,
            "events": [
                {
                    "event_type": e.event_type,
                    "timestamp_ns": e.timestamp_ns,
                    "params": dict(e.params),
                }
                for e in self.events
            ],
            "reads_run_outcome": self.reads_run_outcome,
        }

    def digest(self) -> str:
        """Deterministic content hash (DR-501): the same protocol bytes must
        hash identically, so four-cell identity can be machine-checked."""
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.blake2b(canonical.encode("utf-8"), digest_size=16).hexdigest()


def validate_four_cell_same_path(protocols: dict[str, StressProtocolV1]) -> None:
    """Assert the four L/M cells carry event-for-event identical protocols.

    ``protocols`` maps a cell key (e.g. ``"L_low_M_low"``) to its protocol.
    All four must exist and be byte-identical (same ``digest``), so the only
    difference between cells is the institutional ``L`` / ``M`` treatment
    (FR-024 / AC-004).  Extra/unknown cells are rejected (closed set,
    R018-C006) -- a protocol set that is not exactly the four cells cannot
    claim four-cell identity.  Any mismatch invalidates the whole paired
    evidence.
    """
    expected_cells = {"L_low_M_low", "L_low_M_high", "L_high_M_low", "L_high_M_high"}
    missing = expected_cells - set(protocols)
    if missing:
        raise StressProtocolError(
            f"four-cell stress protocol must cover all cells; missing: {sorted(missing)}"
        )
    extra = set(protocols) - expected_cells
    if extra:
        raise StressProtocolError(
            f"four-cell stress protocol must be exactly the four L/M cells; "
            f"unexpected cells: {sorted(extra)}"
        )
    digests = {cell: p.digest() for cell, p in protocols.items()}
    if len(set(digests.values())) != 1:
        raise StressProtocolError(
            f"four-cell protocols must be event-for-event identical, got digests {digests}"
        )


def validate_stress_exogenous_provenance(evidence_list: list[dict]) -> None:
    """Assert EVERY STRESS-triggered decision is marked ``EXOGENOUS_STRESS``.

    The closed set is ``ENDOGENOUS_AGENT`` / ``LIQUIDATION`` /
    ``EXOGENOUS_STRESS`` (TR-502), but a STRESS run's protocol-driven
    decisions must be **exactly** ``EXOGENOUS_STRESS`` -- accepting
    ENDOGENOUS_AGENT here would let a stress-triggered decision masquerade
    as an endogenous one (R018-C006).  A spontaneous run must never contain
    ``EXOGENOUS_STRESS`` (spec §5) -- that rule lives in the chain verifier.
    """
    for ev in evidence_list:
        prov = ev.get("trigger_provenance")
        if prov != "EXOGENOUS_STRESS":
            raise StressProtocolError(
                f"STRESS-triggered decision must be EXOGENOUS_STRESS, got {prov!r}"
            )


__all__ = [
    "STRESS_EVENT_TYPES",
    "StressEvent",
    "StressProtocolV1",
    "StressProtocolError",
    "validate_four_cell_same_path",
    "validate_stress_exogenous_provenance",
]
