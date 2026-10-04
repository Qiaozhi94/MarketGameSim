"""0.4.3 T1100 (NFR-701 / AC-702): the family position ceiling divides by MULT.

Notional is ``position * mark * MULT`` (账户合同 §2.2), so a ceiling derived from
``equity * risk_appetite`` has to divide by both ``mark`` and ``MULT``.  The
0.4.1 copy divided by ``mark`` alone and asked for about 1000x the leverage its
own ``risk_appetite_x1000`` declared (0.4.1 报告 §19.3).  Both sides are pinned:
the corrected ceiling lands inside the declared leverage, and the old formula
is the one the magnitude sentinel exists to catch.  The roster side refuses an
engine ``mult`` the families do not size against.
"""

from __future__ import annotations

import copy

import pytest

from market_game_sim.agent.goal import (
    AgentPreferences,
    BookTop,
    InformationSetV1,
    OwnAccountView,
    equity_units,
)
from market_game_sim.agent.strategy_layer.families._common import (
    DEFAULT_MULT,
    assert_plausible_leverage,
    max_position_units,
)
from market_game_sim.agent.strategy_layer.protocol import (
    InformationTier,
    StrategyLayerError,
    crop_information_set,
)
from market_game_sim.experiment.h2.live_market import DEFAULT_LIVE_ROSTER
from market_game_sim.experiment.roster import RosterError, parse_roster

MARK = 10_000
WALLET = 10**14


def make_info(*, wallet_units: int = WALLET, position_units: int = 0):
    raw = InformationSetV1(
        schema_version=1,
        cursor_from_event_id="evt-0",
        cursor_to_event_id="evt-1",
        public_trades=(),
        completed_bars=(),
        book_top=BookTop(best_bid=MARK - 1, best_ask=MARK + 1, valuation_mark_half_ticks=2 * MARK),
        own_account=OwnAccountView(
            wallet_units=wallet_units,
            position_units=position_units,
            entry_notional_units=position_units * MARK * DEFAULT_MULT,
        ),
    )
    return crop_information_set(raw, InformationTier.I0, observed_at=1_000)


def implied_leverage_x1000(ceiling: int, info) -> int:
    equity = equity_units(info.own_account, MARK, DEFAULT_MULT)
    return ceiling * MARK * DEFAULT_MULT * 1000 // equity


@pytest.mark.parametrize("risk_appetite_x1000", [500, 2000, 20000])
@pytest.mark.parametrize("k_x1000", [1, 400, 1000])
def test_ceiling_implies_the_declared_leverage(risk_appetite_x1000, k_x1000):
    """Ceiling notional / equity == risk_appetite × k, up to integer truncation."""
    info = make_info()
    prefs = AgentPreferences(risk_appetite_x1000=risk_appetite_x1000)
    ceiling = max_position_units(info, prefs, MARK, k_x1000=k_x1000)
    declared_x1000 = risk_appetite_x1000 * k_x1000 // 1000
    assert ceiling > 0
    leverage = implied_leverage_x1000(ceiling, info)
    assert leverage <= declared_x1000
    # One unit of truncation is all the slack the integer arithmetic allows.
    one_unit_x1000 = MARK * DEFAULT_MULT * 1000 // WALLET + 1
    assert declared_x1000 - leverage <= one_unit_x1000


def test_contract_maximum_stays_far_below_the_sentinel():
    """risk_appetite 20x × k 1.0 is the sizing contract's ceiling: 20x, not 100x."""
    info = make_info()
    ceiling = max_position_units(
        info, AgentPreferences(risk_appetite_x1000=20000), MARK, k_x1000=1000
    )
    assert implied_leverage_x1000(ceiling, info) <= 20_000


def test_the_pre_fix_formula_is_what_the_sentinel_rejects():
    """The 0.4.1 formula (``max_notional // mark``) asks for ~1000x the declared leverage."""
    info = make_info()
    prefs = AgentPreferences(risk_appetite_x1000=2000)
    equity = equity_units(info.own_account, MARK, DEFAULT_MULT)
    pre_fix = (equity * prefs.risk_appetite_x1000 // 1000) // MARK
    assert implied_leverage_x1000(pre_fix, info) == 2_000_000  # 2000x, not 2x
    with pytest.raises(StrategyLayerError) as exc:
        assert_plausible_leverage(pre_fix, MARK, DEFAULT_MULT, equity)
    assert exc.value.code == "IMPLAUSIBLE_LEVERAGE"
    fixed = max_position_units(info, prefs, MARK, k_x1000=1000)
    assert fixed * 1000 == pre_fix


def test_ceiling_tracks_equity():
    """The ceiling scales with equity; an open position at its entry price adds none."""
    flat = make_info()
    winning = make_info(position_units=1_000)  # entry at MARK: equity == wallet
    prefs = AgentPreferences(risk_appetite_x1000=2000)
    assert max_position_units(winning, prefs, MARK, k_x1000=1000) == max_position_units(
        flat, prefs, MARK, k_x1000=1000
    )
    richer = make_info(wallet_units=2 * WALLET)
    assert max_position_units(richer, prefs, MARK, k_x1000=1000) == 2 * max_position_units(
        flat, prefs, MARK, k_x1000=1000
    )


def test_exhausted_budget_still_returns_zero():
    info = make_info(wallet_units=0)
    assert (
        max_position_units(info, AgentPreferences(risk_appetite_x1000=2000), MARK, k_x1000=500) == 0
    )


def test_roster_accepts_the_family_mult():
    assert parse_roster(DEFAULT_LIVE_ROSTER).engine["mult"] == DEFAULT_MULT


def test_roster_refuses_an_engine_mult_the_families_do_not_size_against():
    roster = copy.deepcopy(dict(DEFAULT_LIVE_ROSTER))
    roster["engine"] = {**roster["engine"], "mult": DEFAULT_MULT * 2}
    with pytest.raises(RosterError) as exc:
        parse_roster(roster)
    assert exc.value.code == "MULT_MISMATCH"


def test_roster_without_mult_sized_families_may_use_another_mult():
    """Only the families that size through ``_common`` are bound to its MULT."""
    roster = copy.deepcopy(dict(DEFAULT_LIVE_ROSTER))
    roster["engine"] = {**roster["engine"], "mult": DEFAULT_MULT * 2}
    roster["families"] = [f for f in roster["families"] if f["family_id"] == "market_maker_v2"]
    assert parse_roster(roster).engine["mult"] == DEFAULT_MULT * 2
