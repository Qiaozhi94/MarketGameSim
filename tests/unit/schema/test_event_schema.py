"""R018-C009: DecisionEvidenceV1 closed-structure validation (DR-501).

The nested ``decision_evidence`` object has no sub-structure in
event_fields.json, so its closed field set / types / enums / version are
validated by ``validate_decision_evidence_v1`` (evidence/evidence_guard.py)
against the frozen contract.  Unknown / missing / mistyped / out-of-enum
members fail closed -- never silently entering the evidence chain.
"""

from __future__ import annotations

import pytest

from market_game_sim.agent.goal import InformationSetV1
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


@pytest.mark.parametrize(
    "field",
    ["schema_version", "goal_model_version", "desired_position_units", "executable_position_units"],
)
def test_integer_fields_reject_bool(field):
    """R018-C009 (Round 3): isinstance(True, int) is True, so the previous
    check silently accepted bools in integer fields -- must be rejected."""
    ev = _valid_evidence()
    ev[field] = True
    with pytest.raises(EvidenceClassError, match=field):
        validate_decision_evidence_v1(ev)


def test_v1_structures_reject_unknown_version():
    """R018-C009 (Round 3): the versioned V1 schemas fail closed on unknown
    schema_version."""
    from market_game_sim.agent.goal import (
        AgentInternalStateV1,
        BookTop,
        InformationSetV1,
        OwnAccountView,
    )

    with pytest.raises(ValueError, match="schema_version"):
        InformationSetV1(
            schema_version=99,
            cursor_from_event_id="e1_0",
            cursor_to_event_id="e1_0",
            public_trades=(),
            completed_bars=(),
            book_top=BookTop(best_bid=1, best_ask=2, valuation_mark_half_ticks=3),
            own_account=OwnAccountView(wallet_units=1, position_units=0, entry_notional_units=0),
        )
    with pytest.raises(ValueError, match="schema_version"):
        AgentInternalStateV1(
            schema_version=99,
            last_seen_market_event_id="e1_0",
            ewma_value_units=None,
            ewma_sample_count=0,
        )


def test_risk_appetite_bounds_fail_closed():
    """R018-C009 (Round 3): risk_appetite_x1000 is frozen to [500, 20000] and
    must reject bools and out-of-range values."""
    from market_game_sim.agent.goal import AgentPreferences

    with pytest.raises(ValueError, match="500, 20000"):
        AgentPreferences(risk_appetite_x1000=499)
    with pytest.raises(ValueError, match="500, 20000"):
        AgentPreferences(risk_appetite_x1000=20_001)
    with pytest.raises(ValueError, match="int"):
        AgentPreferences(risk_appetite_x1000=True)
    AgentPreferences(risk_appetite_x1000=2000)


def _v1_iset(**overrides) -> InformationSetV1:
    from market_game_sim.agent.goal import BookTop, OwnAccountView

    defaults = dict(
        schema_version=1,
        cursor_from_event_id="e1_0",
        cursor_to_event_id="e5_0",
        public_trades=(),
        completed_bars=(),
        book_top=BookTop(best_bid=1, best_ask=2, valuation_mark_half_ticks=3),
        own_account=OwnAccountView(wallet_units=1, position_units=0, entry_notional_units=0),
    )
    defaults.update(overrides)
    return InformationSetV1(**defaults)


def test_information_set_rejects_bad_cursor_type():
    """R018-C009 (Round 5): cursor ids must be strings."""
    with pytest.raises(ValueError, match="cursor_from"):
        _v1_iset(cursor_from_event_id=1)


def test_information_set_rejects_untyped_public_trades():
    """R018-C009 (Round 5): public_trades must be PublicTrade objects."""
    with pytest.raises(ValueError, match="public_trades"):
        _v1_iset(public_trades=[{"price_ticks": 1, "quantity_units": 1, "timestamp": 0}])


def test_information_set_rejects_untyped_book_top():
    """R018-C009 (Round 5): book_top must be BookTop or None."""
    with pytest.raises(ValueError, match="book_top"):
        _v1_iset(book_top={"best_bid": 1})


def test_internal_state_rejects_negative_ewma_count():
    """R018-C009 (Round 5): ewma_sample_count must be non-negative."""
    from market_game_sim.agent.goal import AgentInternalStateV1

    with pytest.raises(ValueError, match="ewma_sample_count"):
        AgentInternalStateV1(
            schema_version=1,
            last_seen_market_event_id="e1_0",
            ewma_value_units=None,
            ewma_sample_count=-1,
        )


def test_public_trade_rejects_bool_price():
    """R018-C009 (Round 5): PublicTrade fields must be ints (bool excluded)."""
    from market_game_sim.agent.goal import PublicTrade

    with pytest.raises(ValueError, match="price_ticks"):
        PublicTrade(price_ticks=True, quantity_units=1, timestamp=0)


def test_internal_state_rejects_non_mapping_private_state():
    """R018-C009 (Round 7): model_private_state must be a Mapping."""
    from market_game_sim.agent.goal import AgentInternalStateV1

    with pytest.raises(ValueError, match="model_private_state"):
        AgentInternalStateV1(
            schema_version=1,
            last_seen_market_event_id="e1_0",
            ewma_value_units=None,
            ewma_sample_count=0,
            model_private_state=[],
        )
    # A valid Mapping is accepted.
    AgentInternalStateV1(
        schema_version=1,
        last_seen_market_event_id="e1_0",
        ewma_value_units=None,
        ewma_sample_count=0,
        model_private_state={"signal_bp": 100},
    )
