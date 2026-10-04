"""0.4.3 T1104 (NFR-701 / AC-702): the magnitude sentinel on the family position ceiling.

A ceiling that implies more than 100x leverage is a unit error, not an
aggressive parameter: real venues stop around there and the sizing contract
itself stops at 20x.  The sentinel fails closed at the point of computation, so
the ledger never gets the chance to clip the number quietly -- which is how the
missing ``MULT`` stayed hidden (0.4.1 报告 §19.5).

Both sides are asserted, and the wiring is asserted separately: a sentinel that
exists but is not called from ``max_position_units`` would pass the direct
tests and catch nothing.
"""

from __future__ import annotations

import pytest

from market_game_sim.agent.goal import AgentPreferences, BookTop, InformationSetV1, OwnAccountView
from market_game_sim.agent.strategy_layer.families import _common
from market_game_sim.agent.strategy_layer.families._common import (
    DEFAULT_MULT,
    MAX_PLAUSIBLE_LEVERAGE,
    assert_plausible_leverage,
    max_position_units,
)
from market_game_sim.agent.strategy_layer.protocol import (
    InformationTier,
    StrategyLayerError,
    crop_information_set,
)

MARK = 10_000
EQUITY = 10**14


def units_at_leverage(leverage_x1000: int) -> int:
    return EQUITY * leverage_x1000 // (1000 * MARK * DEFAULT_MULT)


def test_the_bound_is_the_real_world_figure():
    assert MAX_PLAUSIBLE_LEVERAGE == 100


@pytest.mark.parametrize("leverage_x1000", [1, 2_000, 20_000, 100_000])
@pytest.mark.parametrize("sign", [1, -1])
def test_plausible_leverage_passes(leverage_x1000, sign):
    assert_plausible_leverage(sign * units_at_leverage(leverage_x1000), MARK, DEFAULT_MULT, EQUITY)


@pytest.mark.parametrize("leverage_x1000", [100_001, 2_000_000])
@pytest.mark.parametrize("sign", [1, -1])
def test_implausible_leverage_fails_closed(leverage_x1000, sign):
    position = sign * (units_at_leverage(leverage_x1000) + 1)
    with pytest.raises(StrategyLayerError) as exc:
        assert_plausible_leverage(position, MARK, DEFAULT_MULT, EQUITY)
    assert exc.value.code == "IMPLAUSIBLE_LEVERAGE"


def test_no_equity_is_left_to_the_budget_check():
    """Zero or negative equity is the ``NO_RISK_BUDGET`` path, not a unit error."""
    assert_plausible_leverage(10**9, MARK, DEFAULT_MULT, 0)
    assert_plausible_leverage(10**9, MARK, DEFAULT_MULT, -5)


def _info():
    raw = InformationSetV1(
        schema_version=1,
        cursor_from_event_id="evt-0",
        cursor_to_event_id="evt-1",
        public_trades=(),
        completed_bars=(),
        book_top=BookTop(best_bid=MARK - 1, best_ask=MARK + 1, valuation_mark_half_ticks=2 * MARK),
        own_account=OwnAccountView(wallet_units=EQUITY, position_units=0, entry_notional_units=0),
    )
    return crop_information_set(raw, InformationTier.I0, observed_at=1_000)


def test_sentinel_is_wired_into_the_family_ceiling(monkeypatch):
    """Reintroduce the T1002 arithmetic (x1000) inside ``max_position_units``: it must raise.

    Mutation check: delete the ``assert_plausible_leverage`` call from
    ``max_position_units`` and this test goes red -- the 2000x figure gets through.
    """
    prefs = AgentPreferences(risk_appetite_x1000=2000)
    assert max_position_units(_info(), prefs, MARK, k_x1000=1000) == units_at_leverage(2_000)

    real_trunc = _common.trunc_toward_zero
    monkeypatch.setattr(_common, "trunc_toward_zero", lambda a, b: real_trunc(a, b) * DEFAULT_MULT)
    with pytest.raises(StrategyLayerError) as exc:
        max_position_units(_info(), prefs, MARK, k_x1000=1000)
    assert exc.value.code == "IMPLAUSIBLE_LEVERAGE"
