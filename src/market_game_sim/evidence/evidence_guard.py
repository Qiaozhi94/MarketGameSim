"""T212: evidence-class + cross-family report/aggregation permission guard.

The evidence classes (``engineering-demonstration`` / ``experiment-preview``
/ ``formal-research``) are owned by ``docs/features/README.md``; this module
is the **runtime** guard that keeps STRESS / BENCHMARK / legacy evidence out
of formal research conclusions (FR-026 / IR-502 / AC-008).

Rules (fail closed, never silently downgraded):

- only a ``SPONTANEOUS`` run may produce ``formal-research`` evidence, and
  only via a frozen preregistration (the flag is checked by the caller);
- ``STRESS`` and ``BENCHMARK`` runs may only produce
  ``engineering-demonstration``;
- the report entry cannot aggregate evidence across run families -- a
  mixed-family batch is rejected rather than implicitly downgraded.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class EvidenceClassError(ValueError):
    """Raised when an evidence class violates the run-family permission."""


class EvidenceClass(StrEnum):
    ENGINEERING_DEMONSTRATION = "engineering-demonstration"
    EXPERIMENT_PREVIEW = "experiment-preview"
    FORMAL_RESEARCH = "formal-research"


@dataclass(frozen=True, slots=True)
class FrozenPreregistrationReference:
    """Content-addressed reference to a machine-resolvable frozen artifact."""

    preregistration_id: str
    artifact_path: Path
    content_sha256: str

    @classmethod
    def from_artifact(cls, artifact_path: str | Path) -> FrozenPreregistrationReference:
        path = Path(artifact_path)
        try:
            raw = path.read_bytes()
            payload = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EvidenceClassError(
                f"cannot resolve preregistration artifact {path}: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise EvidenceClassError("preregistration artifact root must be an object")
        preregistration_id = payload.get("preregistration_id")
        if not isinstance(preregistration_id, str) or not preregistration_id:
            raise EvidenceClassError(
                "preregistration artifact requires non-empty preregistration_id"
            )
        return cls(
            preregistration_id=preregistration_id,
            artifact_path=path,
            content_sha256=hashlib.sha256(raw).hexdigest(),
        )

    def validate(
        self,
        *,
        control_config_hash: str,
        treatment_config_hash: str,
        seeds: list[int],
    ) -> dict:
        try:
            raw = self.artifact_path.read_bytes()
            payload = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EvidenceClassError(
                f"cannot resolve preregistration artifact {self.artifact_path}: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise EvidenceClassError("preregistration artifact root must be an object")
        actual_digest = hashlib.sha256(raw).hexdigest()
        if actual_digest != self.content_sha256:
            raise EvidenceClassError("preregistration artifact digest drifted after freeze")
        expected = {
            "schema_version": 1,
            "status": "FROZEN",
            "preregistration_id": self.preregistration_id,
            "control_config_hash": control_config_hash,
            "treatment_config_hash": treatment_config_hash,
            "seed_plan": {"n_seeds": len(seeds), "seeds": list(seeds)},
        }
        for field, value in expected.items():
            if payload.get(field) != value:
                raise EvidenceClassError(
                    f"preregistration artifact field {field} is not bound to this run "
                    f"(expected {value!r}, got {payload.get(field)!r})"
                )
        return payload

    def report_reference(self) -> dict[str, str]:
        return {
            "preregistration_id": self.preregistration_id,
            "artifact_path": str(self.artifact_path),
            "content_sha256": self.content_sha256,
        }


#: Run family -> the evidence classes its runs are allowed to carry.
#: SPONTANEOUS may additionally produce formal-research when the frozen
#: preregistration is in place (checked by the caller via the prereg flag).
_ALLOWED_BY_FAMILY: dict[str, set[EvidenceClass]] = {
    "SPONTANEOUS": {
        EvidenceClass.ENGINEERING_DEMONSTRATION,
        EvidenceClass.EXPERIMENT_PREVIEW,
        EvidenceClass.FORMAL_RESEARCH,
    },
    "STRESS": {EvidenceClass.ENGINEERING_DEMONSTRATION},
    "BENCHMARK": {EvidenceClass.ENGINEERING_DEMONSTRATION},
}


def guard_evidence_class(family: str, evidence_class: str) -> EvidenceClass:
    """Validate that ``evidence_class`` is allowed for ``family``.

    Returns the parsed :class:`EvidenceClass` on success; raises
    :class:`EvidenceClassError` with the field path and reason on violation
    (IR-502: report entry cannot claim a conclusion the run family cannot
    support).
    """
    try:
        cls = EvidenceClass(evidence_class)
    except ValueError:
        raise EvidenceClassError(
            f"evidence_class {evidence_class!r} is not a known evidence class; "
            f"must be one of {[c.value for c in EvidenceClass]}"
        ) from None

    allowed = _ALLOWED_BY_FAMILY.get(family)
    if allowed is None:
        raise EvidenceClassError(f"run_family {family!r} is not a known run family")
    if cls not in allowed:
        raise EvidenceClassError(
            f"evidence_class '{cls.value}' is not allowed for run family '{family}' "
            f"(allowed: {sorted(c.value for c in allowed)})"
        )
    return cls


def guard_formal_research(
    family: str,
    evidence_class: str,
    preregistration: FrozenPreregistrationReference | None,
    *,
    control_config_hash: str = "",
    treatment_config_hash: str = "",
    seeds: list[int] | None = None,
) -> None:
    """Guard the formal-research gate: only a SPONTANEOUS run carrying a
    frozen preregistration REFERENCE (id / digest, not a bare bool) may claim
    ``formal-research`` (FR-026 / docs/features/README.md: ``formal-research``
    是唯一能建立研究声明的类别).  A bare ``True`` is rejected -- the caller
    must bind an actual frozen preregistration so the conclusion is
    traceable (R018-C011, Round 7)."""
    cls = guard_evidence_class(family, evidence_class)
    if cls != EvidenceClass.FORMAL_RESEARCH:
        return
    if not isinstance(preregistration, FrozenPreregistrationReference):
        raise EvidenceClassError(
            "formal-research evidence requires a resolved frozen preregistration "
            "reference and digest (FR-026); a run without one may only produce "
            "engineering-demonstration / experiment-preview"
        )
    preregistration.validate(
        control_config_hash=control_config_hash,
        treatment_config_hash=treatment_config_hash,
        seeds=list(seeds or []),
    )


def guard_aggregation(items: list[tuple[str, str]]) -> None:
    """Reject cross-family aggregation (IR-502: 禁止跨族聚合).

    ``items`` is a list of ``(run_family, evidence_class)`` pairs to be
    aggregated into one report.  All items must belong to the same run
    family -- a batch mixing SPONTANEOUS and BENCHMARK evidence is rejected
    rather than implicitly downgraded to the weakest class.  Each item's
    class is also validated against its own family.
    """
    families = {family for family, _ in items}
    if len(families) != 1:
        raise EvidenceClassError(
            f"cross-family aggregation is forbidden (IR-502): batch mixes families "
            f"{sorted(families)}"
        )
    family = next(iter(families))
    for _, ec in items:
        guard_evidence_class(family, ec)


__all__ = [
    "EvidenceClass",
    "EvidenceClassError",
    "FrozenPreregistrationReference",
    "guard_aggregation",
    "guard_evidence_class",
    "guard_formal_research",
    "validate_decision_evidence_v1",
]


# --------------------------------------------------------------------------- #
# R018-C009: DecisionEvidenceV1 closed-structure validation (DR-501).
# The nested object is declared as a plain ``object`` in event_fields.json
# (no sub-structure), so its closed field set / types / enums / version are
# validated here against the frozen contract (goal_contract_v2.json
# structures.DecisionEvidenceV1) -- unknown/missing/mistyped members fail
# closed instead of silently entering the evidence chain.
# --------------------------------------------------------------------------- #

_DECISION_EVIDENCE_FIELDS = {
    "schema_version": int,
    "goal_model_id": str,
    "goal_model_version": int,
    "desired_position_units": int,
    "executable_position_units": int,
    "constraint_binding": bool,
    "constraint_reason": (type(None), str),
    "trigger_provenance": str,
    "observation_event_id": str,
    "cursor_from_event_id": str,
    "cursor_to_event_id": str,
}

_TRIGGER_PROVENANCE_VALUES = {"ENDOGENOUS_AGENT", "LIQUIDATION", "EXOGENOUS_STRESS"}
_CONSTRAINT_REASON_VALUES = {
    "MARGIN_LIMIT",
    "MAX_ORDER_QTY",
    "MARK_UNDEFINED",
    "NON_POSITIVE_EQUITY",
    "EWMA_WARMUP",
}


def validate_decision_evidence_v1(ev: dict | None) -> None:
    """Validate a DecisionEvidenceV1 dict against the frozen closed schema.

    Raises :class:`EvidenceClassError` on missing / unknown / mistyped /
    out-of-enum members.  ``None`` is allowed for the v1 BENCHMARK and
    market-maker paths (they carry no goal evidence, event-schema.md §4.5).
    """
    if ev is None:
        return
    if not isinstance(ev, dict):
        raise EvidenceClassError(f"decision_evidence must be an object, got {type(ev).__name__}")

    unknown = set(ev) - set(_DECISION_EVIDENCE_FIELDS)
    if unknown:
        raise EvidenceClassError(f"decision_evidence has unknown fields: {sorted(unknown)}")
    missing = set(_DECISION_EVIDENCE_FIELDS) - set(ev)
    if missing:
        raise EvidenceClassError(f"decision_evidence is missing required fields: {sorted(missing)}")

    for fname, expected in _DECISION_EVIDENCE_FIELDS.items():
        value = ev[fname]
        # R018-C009 (Round 3): isinstance(True, int) is True, so integer
        # fields silently accepted bools.  Use an exact type check for int.
        ok = type(value) is int if expected is int else isinstance(value, expected)
        if not ok:
            raise EvidenceClassError(
                f"decision_evidence.{fname} must be {expected}, got {type(value).__name__}"
            )

    if ev["trigger_provenance"] not in _TRIGGER_PROVENANCE_VALUES:
        raise EvidenceClassError(
            f"decision_evidence.trigger_provenance must be one of "
            f"{sorted(_TRIGGER_PROVENANCE_VALUES)}, got {ev['trigger_provenance']!r}"
        )
    reason = ev["constraint_reason"]
    if reason is not None and reason not in _CONSTRAINT_REASON_VALUES:
        raise EvidenceClassError(
            f"decision_evidence.constraint_reason must be one of "
            f"{sorted(_CONSTRAINT_REASON_VALUES)} or null, got {reason!r}"
        )
    if ev["schema_version"] != 1:
        raise EvidenceClassError(
            f"decision_evidence.schema_version must be 1, got {ev['schema_version']}"
        )
