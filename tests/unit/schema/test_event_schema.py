"""R018-C009: DecisionEvidenceV1 closed-structure validation (DR-501).

The nested ``decision_evidence`` object has no sub-structure in
event_fields.json, so its closed field set / types / enums / version are
validated by ``validate_decision_evidence_v1`` (evidence/evidence_guard.py)
against the frozen contract.  Unknown / missing / mistyped / out-of-enum
members fail closed -- never silently entering the evidence chain.
"""

from __future__ import annotations

import pytest

from market_game_sim.evidence.evidence_guard import (
    EvidenceClassError,
    validate_decision_evidence_v1,
)


def _valid_evidence() -> dict:
    return {
        "schema_version": 1,
        "goal_model_id": "risk_budget_linear_v1",
        "goal_model_version": 1,
        "desired_position_units": 5000,
        "executable_position_units": 5000,
        "constraint_binding": False,
        "constraint_reason": None,
        "trigger_provenance": "ENDOGENOUS_AGENT",
        "observation_event_id": "e2_0",
        "cursor_from_event_id": "e1_0",
        "cursor_to_event_id": "e5_0",
    }


def test_valid_evidence_passes():
    validate_decision_evidence_v1(_valid_evidence())


def test_none_allowed_for_legacy_paths():
    validate_decision_evidence_v1(None)


@pytest.mark.parametrize(
    "field",
    [
        "schema_version",
        "goal_model_id",
        "goal_model_version",
        "desired_position_units",
        "executable_position_units",
        "constraint_binding",
        "constraint_reason",
        "trigger_provenance",
        "observation_event_id",
        "cursor_from_event_id",
        "cursor_to_event_id",
    ],
)
def test_missing_field_rejected(field):
    ev = _valid_evidence()
    del ev[field]
    with pytest.raises(EvidenceClassError, match=field):
        validate_decision_evidence_v1(ev)


def test_unknown_field_rejected():
    ev = _valid_evidence()
    ev["smuggled"] = 1
    with pytest.raises(EvidenceClassError, match="smuggled"):
        validate_decision_evidence_v1(ev)


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("schema_version", "1"),  # str instead of int
        ("desired_position_units", 5000.5),  # float instead of int
        ("constraint_binding", 1),  # int instead of bool
        ("trigger_provenance", 42),  # int instead of str
    ],
)
def test_mistyped_field_rejected(field, bad_value):
    ev = _valid_evidence()
    ev[field] = bad_value
    with pytest.raises(EvidenceClassError, match=field):
        validate_decision_evidence_v1(ev)


def test_trigger_provenance_enum_rejected():
    ev = _valid_evidence()
    ev["trigger_provenance"] = "ALIEN"
    with pytest.raises(EvidenceClassError, match="trigger_provenance"):
        validate_decision_evidence_v1(ev)


def test_constraint_reason_enum_rejected():
    ev = _valid_evidence()
    ev["constraint_reason"] = "NOT_A_REASON"
    with pytest.raises(EvidenceClassError, match="constraint_reason"):
        validate_decision_evidence_v1(ev)


def test_schema_version_mismatch_rejected():
    ev = _valid_evidence()
    ev["schema_version"] = 2
    with pytest.raises(EvidenceClassError, match="schema_version"):
        validate_decision_evidence_v1(ev)
