"""T101, T103: Margin calculation primitives (账户合同 §3)."""

from __future__ import annotations

from market_game_sim.ledger.account import Account
from market_game_sim.ledger.margin import (
    initial_margin_required,
    margin_ratio_bp,
    margin_used,
    notional_units,
    risk_equity,
)

MULT = 1000


def test_notional_units_zero_position():
    assert notional_units(0, 10000, MULT) == 0


def test_notional_units_long():
    assert notional_units(10000, 10000, MULT) == 100_000_000_000


def test_notional_units_short_uses_absolute():
    assert notional_units(-10000, 10000, MULT) == 100_000_000_000


def test_margin_used_integral():
    assert margin_used(100_000_000_000, 500) == 5_000_000_000


def test_margin_used_ceiling_rounds_up():
    assert margin_used(99_900_000, 500) == 4_995_000


def test_margin_used_zero_notional():
    assert margin_used(0, 500) == 0


def test_initial_margin_required_basic():
    assert initial_margin_required(1000, 3334) == 334


def test_initial_margin_required_3x_boundary():
    notional = 29994 * 10000 * MULT
    required = initial_margin_required(notional, 3334)
    assert required == 99_999_996_000


def test_risk_equity_at_mark():
    acct = Account(
        agent_id="a",
        wallet_units=100_000_000_000,
        position_units=10000,
        entry_notional_units=100_000_000_000,
    )
    assert risk_equity(acct, 10000, MULT) == 100_000_000_000


def test_risk_equity_with_loss():
    acct = Account(
        agent_id="a",
        wallet_units=50_000_000_000,
        position_units=10000,
        entry_notional_units=200_000_000_000,
    )
    # unrealized = 10000*10000*1000 - 200_000_000_000 = -100_000_000_000
    # risk_equity = 50_000_000_000 - 100_000_000_000 = -50_000_000_000
    assert risk_equity(acct, 10000, MULT) == -50_000_000_000


def test_margin_ratio_bp_none_for_zero_position():
    acct = Account(agent_id="a", wallet_units=100_000_000_000)
    assert margin_ratio_bp(acct, 10000, MULT) is None


def test_margin_ratio_bp_well_above_maint():
    acct = Account(
        agent_id="a",
        wallet_units=1_000_000_000_000,
        position_units=10000,
        entry_notional_units=100_000_000_000,
    )
    assert margin_ratio_bp(acct, 10000, MULT) == 100_000
