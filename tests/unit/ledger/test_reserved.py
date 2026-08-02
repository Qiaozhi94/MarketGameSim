"""T407b: reserved_units -- 4 scenarios (acceptance-vectors §3 case 7b, §4).

risk_mark=100, all order prices=100, tier=10 (initial_bp=1000),
maker -1 bps, taker 5 bps -> fee_bps = max(-1,5,0) = 5.

Integer expected (cash_unit=1e-8):
  scenario 1: reserved_after = 100000000000   (1000 human)
  scenario 2: reserved_after = 150250000000   (1502.5)
  scenario 3: reserved_after = 120350000000   (1203.5)
  scenario 4: reserved_after = 120250000000   (1202.5)

reserved_delta (from scenario 1 baseline 100000000000):
  scenario 2: +50250000000
  scenario 3: +20350000000
  scenario 4: -100000000
"""

from __future__ import annotations

import pytest

from market_game_sim.ledger.reserved import ActiveOrder, compute_reserved_after, fee_bps_cap

MULT = 1000
CASH = 10**8
P100 = 10000  # 100.00 in ticks


def cash(h: float | int) -> int:
    return int(round(h * CASH))


def units(h: float | int) -> int:
    return int(round(h * 1000))


INITIAL_BP = 1000  # tier 10
FEE_BPS = 5  # max(-1, 5, 0)


class TestT407bFeeBpsCap:
    def test_max_maker_taker_zero(self):
        assert fee_bps_cap(-1, 5) == 5
        assert fee_bps_cap(5, 3) == 5
        assert fee_bps_cap(-2, -1) == 0
        assert fee_bps_cap(0, 0) == 0


class TestT407bScenario1:
    """Baseline: position 100, no active orders -> reserved = IM(position)."""

    def test_reserved_after(self):
        r = compute_reserved_after(
            position_units=units(100), active_orders=[],
            risk_mark_ticks=P100, initial_bp=INITIAL_BP, fee_bps=FEE_BPS, mult=MULT,
        )
        assert r == 100000000000
        assert r == cash(1000)

    def test_reserved_delta_zero(self):
        r = compute_reserved_after(
            position_units=units(100), active_orders=[],
            risk_mark_ticks=P100, initial_bp=INITIAL_BP, fee_bps=FEE_BPS, mult=MULT,
        )
        assert r - cash(1000) == 0


class TestT407bScenario2:
    """From 1, place same-direction buys 20 + 30 -> worst_long=150."""

    def test_reserved_after(self):
        r = compute_reserved_after(
            position_units=units(100),
            active_orders=[
                ActiveOrder("BUY", P100, units(20)),
                ActiveOrder("BUY", P100, units(30)),
            ],
            risk_mark_ticks=P100, initial_bp=INITIAL_BP, fee_bps=FEE_BPS, mult=MULT,
        )
        assert r == 150250000000
        assert r == cash(1502.5)

    def test_reserved_delta(self):
        r = compute_reserved_after(
            position_units=units(100),
            active_orders=[
                ActiveOrder("BUY", P100, units(20)),
                ActiveOrder("BUY", P100, units(30)),
            ],
            risk_mark_ticks=P100, initial_bp=INITIAL_BP, fee_bps=FEE_BPS, mult=MULT,
        )
        assert r - cash(1000) == cash(502.5)
        assert r - 100000000000 == 50250000000

    def test_not_per_order_sum(self):
        # IM(100)+IM(20)+IM(30) would be 1000+200+300=1500 (wrong: double-counts position margin).
        # Total-usage: margin_part = 150*100*1000*1000/10000 = 1500 (once, on worst_long).
        r = compute_reserved_after(
            position_units=units(100),
            active_orders=[
                ActiveOrder("BUY", P100, units(20)),
                ActiveOrder("BUY", P100, units(30)),
            ],
            risk_mark_ticks=P100, initial_bp=INITIAL_BP, fee_bps=FEE_BPS, mult=MULT,
        )
        assert r != cash(1500)  # not 1500 (would miss fee_part 2.5)
        assert r == cash(1502.5)


class TestT407bScenario3:
    """From 1, place buy 20 + sell 50 -> max(|120|,|50|)=120, do NOT cancel."""

    def test_reserved_after(self):
        r = compute_reserved_after(
            position_units=units(100),
            active_orders=[
                ActiveOrder("BUY", P100, units(20)),
                ActiveOrder("SELL", P100, units(50)),
            ],
            risk_mark_ticks=P100, initial_bp=INITIAL_BP, fee_bps=FEE_BPS, mult=MULT,
        )
        assert r == 120350000000
        assert r == cash(1203.5)

    def test_reserved_delta_from_baseline(self):
        r = compute_reserved_after(
            position_units=units(100),
            active_orders=[
                ActiveOrder("BUY", P100, units(20)),
                ActiveOrder("SELL", P100, units(50)),
            ],
            risk_mark_ticks=P100, initial_bp=INITIAL_BP, fee_bps=FEE_BPS, mult=MULT,
        )
        assert r - 100000000000 == 20350000000

    def test_bidirectional_do_not_cancel(self):
        # If they cancelled: worst would be max(|100+20|,|100-50|)=120 vs |100|=100 -> 120.
        # Same as above; the point is fee_part = (20+50)*100*5/10000 = 3.5 (both orders counted).
        r = compute_reserved_after(
            position_units=units(100),
            active_orders=[
                ActiveOrder("BUY", P100, units(20)),
                ActiveOrder("SELL", P100, units(50)),
            ],
            risk_mark_ticks=P100, initial_bp=INITIAL_BP, fee_bps=FEE_BPS, mult=MULT,
        )
        assert r == cash(1200) + cash(3.5)


class TestT407bScenario4:
    """From 3, buy 20 fills -> position 120, sell 50 still active -> 1202.5."""

    def test_reserved_after(self):
        r = compute_reserved_after(
            position_units=units(120),
            active_orders=[
                ActiveOrder("SELL", P100, units(50)),
            ],
            risk_mark_ticks=P100, initial_bp=INITIAL_BP, fee_bps=FEE_BPS, mult=MULT,
        )
        assert r == 120250000000
        assert r == cash(1202.5)

    def test_reserved_delta_from_scenario3(self):
        r3 = compute_reserved_after(
            position_units=units(100),
            active_orders=[
                ActiveOrder("BUY", P100, units(20)),
                ActiveOrder("SELL", P100, units(50)),
            ],
            risk_mark_ticks=P100, initial_bp=INITIAL_BP, fee_bps=FEE_BPS, mult=MULT,
        )
        r4 = compute_reserved_after(
            position_units=units(120),
            active_orders=[
                ActiveOrder("SELL", P100, units(50)),
            ],
            risk_mark_ticks=P100, initial_bp=INITIAL_BP, fee_bps=FEE_BPS, mult=MULT,
        )
        assert r4 - r3 == -100000000  # -1.0 human


class TestT407bNoOrders:
    """No position, no orders -> reserved 0."""

    def test_empty(self):
        r = compute_reserved_after(
            position_units=0, active_orders=[],
            risk_mark_ticks=P100, initial_bp=INITIAL_BP, fee_bps=FEE_BPS, mult=MULT,
        )
        assert r == 0

    def test_only_short_position(self):
        r = compute_reserved_after(
            position_units=-units(100), active_orders=[],
            risk_mark_ticks=P100, initial_bp=INITIAL_BP, fee_bps=FEE_BPS, mult=MULT,
        )
        assert r == cash(1000)
