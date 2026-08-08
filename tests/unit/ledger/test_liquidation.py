"""T203, T205: Liquidation quantity calculation (账户合同 §4.2, §4.3)."""

from __future__ import annotations

from market_game_sim.ledger.account import Account
from market_game_sim.ledger.liquidation import (
    recompute_required_qty,
    required_liquidation_qty,
)

MULT = 1000
MAINT_BP = 500
TARGET_BP = 1000
TAKER_BPS = 5
P100 = 10000  # 100.00 in ticks


def _acct(wallet: int, position: int, entry: int) -> Account:
    return Account(
        agent_id="x",
        wallet_units=wallet,
        position_units=position,
        entry_notional_units=entry,
    )


def test_qty_zero_when_no_position():
    assert (
        required_liquidation_qty(_acct(100_000_000_000, 0, 0), P100, TARGET_BP, TAKER_BPS, MULT)
        == 0
    )


def test_qty_zero_when_already_above_target():
    """Equity 1e12, notional 1e11 -> ratio 100000 bp >= 1000 bp target."""
    acct = _acct(1_000_000_000_000, 10000, 100_000_000_000)
    assert required_liquidation_qty(acct, P100, TARGET_BP, TAKER_BPS, MULT) == 0


def test_qty_full_position_when_even_full_close_cannot_save():
    """wallet 1, position 100, entry 1e9 -> massively underwater; return |position|."""
    acct = _acct(1, 100, 1_000_000_000)
    qty = required_liquidation_qty(acct, P100, TARGET_BP, TAKER_BPS, MULT)
    assert qty == 100


def test_qty_short_position_symmetric():
    """Short position mirrored: same magnitude yields 0 qty when healthy."""
    acct = _acct(1_000_000_000_000, -10000, -100_000_000_000)
    assert required_liquidation_qty(acct, P100, TARGET_BP, TAKER_BPS, MULT) == 0


def test_qty_returns_positive_integer_for_underwater():
    """Underwater account must return positive qty < |position|.

    Setup: wallet 1e9, position 10000, entry 2e11.
    equity = 1e9 + 1e11 - 2e11 = -9e10
    notional = 1e11
    ratio = -9e10 * 1e4 / 1e11 = -9000 bp (well below maint)
    """
    acct = _acct(1_000_000_000, 10000, 200_000_000_000)
    qty = required_liquidation_qty(acct, P100, TARGET_BP, TAKER_BPS, MULT)
    assert 0 < qty <= 10000


def test_recompute_returns_integer_in_range():
    acct = _acct(1_000_000_000, 10000, 200_000_000_000)
    q = recompute_required_qty(acct, 8000, TARGET_BP, TAKER_BPS, MULT)
    assert 0 <= q <= 10000
