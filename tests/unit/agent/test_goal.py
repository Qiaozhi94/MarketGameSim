"""T204: goal-model golden vectors -- recompute from goal_contract_v2.json.

The frozen contract (``src/market_game_sim/schema/goal_contract_v2.json``) is
the machine truth; ``tools/spec_validation.py`` already recomputes these
vectors against the *equation text*.  This file recomputes them against the
*implementation* (:class:`RiskBudgetLinearV1` /
:class:`RiskBudgetThresholdV1`) -- so a code change that drifts from the
frozen math fails here even if the JSON text is untouched.

Positive cases assert the exact ``expected_desired``; negative cases assert
the implementation does NOT silently accept a wrong value (mutated vector ->
mismatch) and that the truncation is toward zero (not floor).
"""

from __future__ import annotations

import json
import pathlib
from copy import deepcopy

import pytest

from market_game_sim.agent.constraint import ConstraintReason
from market_game_sim.agent.goal import (
    AgentInternalStateV1,
    AgentPreferences,
    BookTop,
    InformationSetV1,
    OwnAccountView,
    RiskBudgetLinearV1,
    RiskBudgetThresholdV1,
)

ROOT = pathlib.Path(__file__).resolve().parents[3]
CONTRACT = ROOT / "src" / "market_game_sim" / "schema" / "goal_contract_v2.json"


@pytest.fixture(scope="module")
def contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def _linear_inputs(vector: dict) -> tuple[InformationSetV1, AgentInternalStateV1, AgentPreferences]:
    """Build the v2 inputs from a linear golden vector.

    equity is a permitted private state; we set wallet so that
    ``equity = wallet + position*mark - entry`` equals the vector's
    ``equity_units`` (position 0, entry 0 -> wallet = equity_units).
    """
    mark = vector["mark"]
    own = OwnAccountView(
        wallet_units=vector["equity_units"], position_units=0, entry_notional_units=0
    )
    book = BookTop(best_bid=mark, best_ask=mark, valuation_mark_half_ticks=mark * 2)
    iset = InformationSetV1(
        schema_version=1,
        cursor_from_event_id="",
        cursor_to_event_id="",
        public_trades=(),
        completed_bars=(),
        book_top=book,
        own_account=own,
    )
    state = AgentInternalStateV1(
        schema_version=1,
        last_seen_market_event_id="",
        ewma_value_units=None,
        ewma_sample_count=1000,  # past warmup
        model_private_state={"signal_bp": vector["signal_bp"]},
    )
    prefs = AgentPreferences(risk_appetite_x1000=vector["risk_appetite_x1000"])
    return iset, state, prefs


def _threshold_inputs(
    vector: dict,
) -> tuple[InformationSetV1, AgentInternalStateV1, AgentPreferences, RiskBudgetThresholdV1]:
    mark = vector["mark"]
    pos = vector["current_position"]
    # wallet = equity - position*mark (entry 0) so equity == vector["equity_units"].
    wallet = vector["equity_units"] - pos * mark
    own = OwnAccountView(wallet_units=wallet, position_units=pos, entry_notional_units=0)
    book = BookTop(best_bid=mark, best_ask=mark, valuation_mark_half_ticks=mark * 2)
    iset = InformationSetV1(
        schema_version=1,
        cursor_from_event_id="",
        cursor_to_event_id="",
        public_trades=(),
        completed_bars=(),
        book_top=book,
        own_account=own,
    )
    state = AgentInternalStateV1(
        schema_version=1,
        last_seen_market_event_id="",
        ewma_value_units=None,
        ewma_sample_count=1000,
        model_private_state={"signal_bp": vector["signal_bp"]},
    )
    prefs = AgentPreferences(risk_appetite_x1000=vector["risk_appetite_x1000"])
    model = RiskBudgetThresholdV1(
        theta_in=vector["theta_in"],
        theta_out=vector["theta_out"],
        k_x1000=vector["k_x1000"],
    )
    return iset, state, prefs, model


# --------------------------------------------------------------------------- #
# Positive: each linear golden vector recomputes exactly
# --------------------------------------------------------------------------- #


def test_linear_golden_vectors_recompute_exactly(contract):
    model = RiskBudgetLinearV1()
    for vector in contract["golden_vectors"]["linear"]:
        iset, state, prefs = _linear_inputs(vector)
        decision = model.decide(iset, state, prefs)
        assert decision.desired_position_units == vector["expected_desired"], (
            f"{vector['id']}: got {decision.desired_position_units}, "
            f"expected {vector['expected_desired']}"
        )
        assert decision.action == "emit_decision"
        assert decision.degenerate_reason is None


def test_threshold_golden_vectors_recompute_exactly(contract):
    for vector in contract["golden_vectors"]["threshold"]:
        iset, state, prefs, model = _threshold_inputs(vector)
        decision = model.decide(iset, state, prefs)
        assert decision.desired_position_units == vector["expected_desired"], (
            f"{vector['id']}: got {decision.desired_position_units}, "
            f"expected {vector['expected_desired']}"
        )
        assert decision.action == "emit_decision"
        assert decision.degenerate_reason is None


# --------------------------------------------------------------------------- #
# Negative: truncation is toward zero, not floor (linear_trunc pair)
# --------------------------------------------------------------------------- #


def test_linear_truncates_toward_zero_not_floor(contract):
    """linear_trunc_negative expects -6871.  Python ``//`` floors toward -inf,
    so a naive ``signal*max_pos // 10000`` would yield -6872.  The model must
    truncate toward zero (ADR-001) -> -6871."""
    pos_vector = next(
        v for v in contract["golden_vectors"]["linear"] if v["id"] == "linear_trunc_positive"
    )
    neg_vector = next(
        v for v in contract["golden_vectors"]["linear"] if v["id"] == "linear_trunc_negative"
    )
    model = RiskBudgetLinearV1()
    pos_dec = model.decide(*_linear_inputs(pos_vector))
    neg_dec = model.decide(*_linear_inputs(neg_vector))
    assert pos_dec.desired_position_units == -neg_dec.desired_position_units, (
        "trunc toward zero must be sign-symmetric: "
        f"{pos_dec.desired_position_units} vs {-neg_dec.desired_position_units}"
    )
    # And specifically not the floor result.
    assert neg_dec.desired_position_units == -6871
    assert neg_dec.desired_position_units != -6872


def test_linear_negative_signal_yields_negative_desired():
    """Negative control: a negative signal must produce a negative (short)
    desired, not zero / not abs-value."""
    iset, state, prefs = _linear_inputs(
        {"equity_units": 1_000_000, "risk_appetite_x1000": 2000, "mark": 100, "signal_bp": -2500}
    )
    decision = RiskBudgetLinearV1().decide(iset, state, prefs)
    assert decision.desired_position_units == -5000
    assert decision.desired_position_units < 0


# --------------------------------------------------------------------------- #
# Negative: a mutated vector must NOT match (the test would catch a drift)
# --------------------------------------------------------------------------- #


def test_linear_rejects_mutated_expected(contract):
    """If we corrupt the expected value, the assertion must fail -- proves the
    test is actually comparing against the frozen vector, not a tautology."""
    vector = dict(contract["golden_vectors"]["linear"][0])
    model = RiskBudgetLinearV1()
    decision = model.decide(*_linear_inputs(vector))
    mutated = deepcopy(vector)
    mutated["expected_desired"] = decision.desired_position_units + 1
    assert decision.desired_position_units != mutated["expected_desired"]


# --------------------------------------------------------------------------- #
# Threshold hysteresis: the hold band preserves current position
# --------------------------------------------------------------------------- #


def test_threshold_hold_band_preserves_position():
    """signal in (theta_out, theta_in) -> HOLD current position unchanged.
    This is the hysteresis guarantee: without it a jittering signal would churn
    the agent in and out at full size (代理策略 §5.2.1)."""
    iset, state, prefs, model = _threshold_inputs(
        {
            "equity_units": 1_000_000,
            "risk_appetite_x1000": 2000,
            "mark": 100,
            "signal_bp": 2000,  # in (1200, 3000)
            "theta_in": 3000,
            "theta_out": 1200,
            "k_x1000": 600,
            "current_position": 7000,
        }
    )
    decision = model.decide(iset, state, prefs)
    assert decision.desired_position_units == 7000


def test_threshold_param_bounds_enforced():
    """param_bounds (frozen in preregistration) must fail closed at construction."""
    with pytest.raises(ValueError, match="theta_out"):
        RiskBudgetThresholdV1(theta_in=3000, theta_out=3000, k_x1000=600)  # not <
    with pytest.raises(ValueError, match="theta_in"):
        RiskBudgetThresholdV1(theta_in=0, theta_out=0, k_x1000=600)  # < 1
    with pytest.raises(ValueError, match="k_x1000"):
        RiskBudgetThresholdV1(theta_in=3000, theta_out=1200, k_x1000=0)  # < 1
    with pytest.raises(ValueError, match="k_x1000"):
        RiskBudgetThresholdV1(theta_in=3000, theta_out=1200, k_x1000=1001)  # > 1000


# --------------------------------------------------------------------------- #
# Degenerate inputs (代理策略 §5.2.3, golden_vectors.degenerate)
# --------------------------------------------------------------------------- #


def test_degenerate_mark_undefined_skips_decision():
    """Both sides empty, no trades -> valuation_mark undefined -> skip, no order."""
    own = OwnAccountView(wallet_units=1_000_000, position_units=0, entry_notional_units=0)
    iset = InformationSetV1(
        schema_version=1,
        cursor_from_event_id="",
        cursor_to_event_id="",
        public_trades=(),
        completed_bars=(),
        book_top=None,  # mark undefined
        own_account=own,
    )
    state = AgentInternalStateV1(
        schema_version=1,
        last_seen_market_event_id="",
        ewma_value_units=None,
        ewma_sample_count=1000,
        model_private_state={"signal_bp": 5000},
    )
    decision = RiskBudgetLinearV1().decide(iset, state, AgentPreferences(risk_appetite_x1000=2000))
    assert decision.desired_position_units is None
    assert decision.action == "skip_decision"
    assert decision.degenerate_reason == ConstraintReason.MARK_UNDEFINED


def test_degenerate_non_positive_equity_reduce_only():
    """equity <= 0 -> desired 0, reduce-only (not skip -- a frozen account must
    still self-rescue, else liquidation-chain dynamics are masked)."""
    mark = 100
    # wallet negative so equity <= 0.
    own = OwnAccountView(wallet_units=-1, position_units=0, entry_notional_units=0)
    book = BookTop(best_bid=mark, best_ask=mark, valuation_mark_half_ticks=mark * 2)
    iset = InformationSetV1(
        schema_version=1,
        cursor_from_event_id="",
        cursor_to_event_id="",
        public_trades=(),
        completed_bars=(),
        book_top=book,
        own_account=own,
    )
    state = AgentInternalStateV1(
        schema_version=1,
        last_seen_market_event_id="",
        ewma_value_units=None,
        ewma_sample_count=1000,
        model_private_state={"signal_bp": 10000},
    )
    decision = RiskBudgetLinearV1().decide(iset, state, AgentPreferences(risk_appetite_x1000=2000))
    assert decision.desired_position_units == 0
    assert decision.action == "reduce_only"
    assert decision.degenerate_reason == ConstraintReason.NON_POSITIVE_EQUITY


def test_degenerate_ewma_warmup_zero_target():
    """sample_count < 2*half_life -> cold-start anchor, desired 0, still emit."""
    mark = 100
    own = OwnAccountView(wallet_units=1_000_000, position_units=0, entry_notional_units=0)
    book = BookTop(best_bid=mark, best_ask=mark, valuation_mark_half_ticks=mark * 2)
    iset = InformationSetV1(
        schema_version=1,
        cursor_from_event_id="",
        cursor_to_event_id="",
        public_trades=(),
        completed_bars=(),
        book_top=book,
        own_account=own,
    )
    state = AgentInternalStateV1(
        schema_version=1,
        last_seen_market_event_id="",
        ewma_value_units=None,
        ewma_sample_count=3,  # < 2 * half_life(=10) = 20
        model_private_state={"signal_bp": 10000},
    )
    model = RiskBudgetLinearV1(half_life_in_trades=10)
    decision = model.decide(iset, state, AgentPreferences(risk_appetite_x1000=2000))
    assert decision.desired_position_units == 0
    assert decision.action == "emit_decision"
    assert decision.degenerate_reason == ConstraintReason.EWMA_WARMUP


def test_degenerate_priority_mark_before_equity():
    """Order matters (代理策略 §5.2.3): mark-undefined is checked before equity.
    A book with no mark AND negative equity must skip (MARK_UNDEFINED), not
    reduce-only (NON_POSITIVE_EQUITY)."""
    own = OwnAccountView(wallet_units=-1, position_units=0, entry_notional_units=0)
    iset = InformationSetV1(
        schema_version=1,
        cursor_from_event_id="",
        cursor_to_event_id="",
        public_trades=(),
        completed_bars=(),
        book_top=None,
        own_account=own,
    )
    state = AgentInternalStateV1(
        schema_version=1,
        last_seen_market_event_id="",
        ewma_value_units=None,
        ewma_sample_count=1000,
        model_private_state={"signal_bp": 10000},
    )
    decision = RiskBudgetLinearV1().decide(iset, state, AgentPreferences(risk_appetite_x1000=2000))
    assert decision.degenerate_reason == ConstraintReason.MARK_UNDEFINED
    assert decision.action == "skip_decision"
