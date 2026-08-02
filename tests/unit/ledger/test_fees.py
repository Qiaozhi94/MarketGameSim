"""T404: Fee computation -- ceil, unfavourable to agent (ADR-001 §3).

acceptance-vectors §4 case 5 integers:
  taker fee 50000000, maker fee -10000000, exchange net 40000000.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from market_game_sim.ledger.fees import compute_mult, compute_notional_and_fees

MULT = 1000
CASH = 10**8


def cash(h: float | int) -> int:
    return int(round(h * CASH))


class TestT404Mult:
    def test_bench001_mult_is_1000(self):
        m = compute_mult(Decimal("0.01"), Decimal("0.001"), Decimal("1e-8"))
        assert m == 1000

    def test_non_integral_mult_rejected(self):
        with pytest.raises(ValueError):
            compute_mult(Decimal("0.01"), Decimal("0.001"), Decimal("7"))


class TestT404NotionalAndFees:
    def test_notional_exact_no_rounding(self):
        n, _, _ = compute_notional_and_fees(10000, 10000, 0, 0, MULT)
        assert n == 1e11  # 10000 * 10000 * 1000

    def test_case5_taker_fee_ceil(self):
        # notional 1e11, taker 5 bps -> ceil(1e11*5/10000) = 5e7 = 50000000.
        _, _, taker = compute_notional_and_fees(10000, 10000, -1, 5, MULT)
        assert taker == cash(0.5)
        assert taker == 50000000

    def test_case5_maker_rebate_ceil(self):
        # notional 1e11, maker -1 bps -> ceil(-1e11/10000) = -1e7.
        _, maker, _ = compute_notional_and_fees(10000, 10000, -1, 5, MULT)
        assert maker == -cash(0.1)
        assert maker == -10000000

    def test_case5_exchange_net_fee(self):
        _, maker, taker = compute_notional_and_fees(10000, 10000, -1, 5, MULT)
        assert maker + taker == cash(0.4)
        assert maker + taker == 40000000

    def test_positive_fee_ceil_unfavourable(self):
        # notional that doesn't divide evenly: 1e11 + 1, taker 5 bps.
        # ceil((1e11+1)*5/10000) = ceil(5e7 + 5e-5) -> 50000001? 
        # (100000000001 * 5) = 500000000005; /10000 = 50000000.0005; ceil = 50000001.
        _, _, taker = compute_notional_and_fees(10001, 10000, 0, 5, MULT)
        # notional = 10001*10000*1000 = 100010000000; *5/10000 = 50005000.0 exact
        assert taker == 50005000

    def test_rebate_ceil_unfavourable_to_agent(self):
        # maker -1 bps on non-even notional: ceil(-X) -> agent gets less.
        # notional 100010000000, *(-1)/10000 = -10001000.0 exact -> -10001000.
        _, maker, _ = compute_notional_and_fees(10001, 10000, -1, 5, MULT)
        assert maker == -10001000

    def test_rebate_non_even_ceil_toward_zero(self):
        # notional 10003*10000*1000 = 100030000000; *(-1)/10000 = -10003000.0 exact.
        # Use odd: notional 100000000001 (prime-ish). -100000000001/10000 = -10000000.0001
        # ceil = -10000000 (toward +inf = toward zero for negatives -> agent gets less).
        n = 100000000001
        from market_game_sim.config.types import round_fee
        assert round_fee(n, -1) == -10000000  # ceil(-10000000.0001) = -10000000

    def test_zero_bps_zero_fee(self):
        _, maker, taker = compute_notional_and_fees(10000, 10000, 0, 0, MULT)
        assert maker == 0
        assert taker == 0
