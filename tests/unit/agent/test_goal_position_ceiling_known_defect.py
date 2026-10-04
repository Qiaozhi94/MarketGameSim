"""0.4.3 T1101: the v0.1 goal models carry the same missing-MULT defect -- known, not fixed.

``risk_budget_linear_v1`` and ``risk_budget_threshold_v1`` size
``max_position = max_notional // mark`` without dividing by ``MULT``, so a
declared 2x ``risk_appetite_x1000`` asks for 2000x.  0.4.3 fixed the copy in
``families/_common.py`` (T1100) but **not these two**: they are frozen v0.1
contract, T215 and the H2 treatment arm run through them, and correcting them
would void the v0.1/v0.2 sign-off evidence -- the economic-equivalence proof
would fail because the positions really shrink, leaving only a full T215 rerun
(0.4.1 报告 §20.3).  The ledger's margin gate clips the request, which is why
the frozen evidence still describes markets that obeyed the margin contract.

These are ``xfail(strict=True)`` on purpose: they assert the *correct*
contract.  If someone fixes either model, the test XPASSes and goes red, so the
evidence consequences get reviewed instead of slipping in unannounced.
"""

from __future__ import annotations

import pytest

from market_game_sim.agent.goal import (
    AgentInternalStateV1,
    AgentPreferences,
    BookTop,
    InformationSetV1,
    OwnAccountView,
    RiskBudgetLinearV1,
    RiskBudgetThresholdV1,
)

MARK = 10_000
EQUITY = 10**14
MULT = 1000
DECLARED_X1000 = 2000  # risk_appetite_x1000 = 2x

REASON = (
    "0.4.3 T1101 known defect: frozen v0.1 goal model omits MULT in max_position; "
    "fixing it voids T215/H2 sign-off evidence (0.4.1 报告 §20.3)"
)


def _decide(model):
    info = InformationSetV1(
        schema_version=1,
        cursor_from_event_id="evt-0",
        cursor_to_event_id="evt-1",
        public_trades=(),
        completed_bars=(),
        book_top=BookTop(best_bid=MARK - 1, best_ask=MARK + 1, valuation_mark_half_ticks=2 * MARK),
        own_account=OwnAccountView(wallet_units=EQUITY, position_units=0, entry_notional_units=0),
    )
    state = AgentInternalStateV1(
        schema_version=1,
        last_seen_market_event_id="evt-0",
        ewma_value_units=None,
        ewma_sample_count=0,
        model_private_state={"signal_bp": 10_000},  # full-strength signal
    )
    decision = model.decide(info, state, AgentPreferences(risk_appetite_x1000=DECLARED_X1000))
    assert decision.degenerate_reason is None
    return decision.desired_position_units


def _implied_leverage_x1000(position_units: int) -> int:
    return abs(position_units) * MARK * MULT * 1000 // EQUITY


@pytest.mark.xfail(strict=True, reason=REASON)
def test_risk_budget_linear_v1_respects_declared_leverage():
    assert _implied_leverage_x1000(_decide(RiskBudgetLinearV1())) <= DECLARED_X1000


@pytest.mark.xfail(strict=True, reason=REASON)
def test_risk_budget_threshold_v1_respects_declared_leverage():
    model = RiskBudgetThresholdV1(theta_in=100, theta_out=50, k_x1000=1000)
    assert _implied_leverage_x1000(_decide(model)) <= DECLARED_X1000


def test_the_defect_is_exactly_the_missing_mult():
    """Not xfail: pins *what* is wrong, so a different regression cannot hide behind the xfail."""
    assert _implied_leverage_x1000(_decide(RiskBudgetLinearV1())) == DECLARED_X1000 * MULT
    model = RiskBudgetThresholdV1(theta_in=100, theta_out=50, k_x1000=1000)
    assert _implied_leverage_x1000(_decide(model)) == DECLARED_X1000 * MULT
