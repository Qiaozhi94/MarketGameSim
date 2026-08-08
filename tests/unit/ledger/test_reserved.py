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

from market_game_sim.ledger.reserved import (
    ActiveOrder,
    PreMatchResult,
    compute_reserved_after,
    compute_reserved_with_prematch,
    fee_bps_cap,
)

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
            position_units=units(100),
            active_orders=[],
            risk_mark_ticks=P100,
            initial_bp=INITIAL_BP,
            fee_bps=FEE_BPS,
            mult=MULT,
        )
        assert r == 100000000000
        assert r == cash(1000)

    def test_reserved_delta_zero(self):
        r = compute_reserved_after(
            position_units=units(100),
            active_orders=[],
            risk_mark_ticks=P100,
            initial_bp=INITIAL_BP,
            fee_bps=FEE_BPS,
            mult=MULT,
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
            risk_mark_ticks=P100,
            initial_bp=INITIAL_BP,
            fee_bps=FEE_BPS,
            mult=MULT,
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
            risk_mark_ticks=P100,
            initial_bp=INITIAL_BP,
            fee_bps=FEE_BPS,
            mult=MULT,
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
            risk_mark_ticks=P100,
            initial_bp=INITIAL_BP,
            fee_bps=FEE_BPS,
            mult=MULT,
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
            risk_mark_ticks=P100,
            initial_bp=INITIAL_BP,
            fee_bps=FEE_BPS,
            mult=MULT,
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
            risk_mark_ticks=P100,
            initial_bp=INITIAL_BP,
            fee_bps=FEE_BPS,
            mult=MULT,
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
            risk_mark_ticks=P100,
            initial_bp=INITIAL_BP,
            fee_bps=FEE_BPS,
            mult=MULT,
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
            risk_mark_ticks=P100,
            initial_bp=INITIAL_BP,
            fee_bps=FEE_BPS,
            mult=MULT,
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
            risk_mark_ticks=P100,
            initial_bp=INITIAL_BP,
            fee_bps=FEE_BPS,
            mult=MULT,
        )
        r4 = compute_reserved_after(
            position_units=units(120),
            active_orders=[
                ActiveOrder("SELL", P100, units(50)),
            ],
            risk_mark_ticks=P100,
            initial_bp=INITIAL_BP,
            fee_bps=FEE_BPS,
            mult=MULT,
        )
        assert r4 - r3 == -100000000  # -1.0 human


class TestT407bNoOrders:
    """No position, no orders -> reserved 0."""

    def test_empty(self):
        r = compute_reserved_after(
            position_units=0,
            active_orders=[],
            risk_mark_ticks=P100,
            initial_bp=INITIAL_BP,
            fee_bps=FEE_BPS,
            mult=MULT,
        )
        assert r == 0

    def test_only_short_position(self):
        r = compute_reserved_after(
            position_units=-units(100),
            active_orders=[],
            risk_mark_ticks=P100,
            initial_bp=INITIAL_BP,
            fee_bps=FEE_BPS,
            mult=MULT,
        )
        assert r == cash(1000)


class TestComputeReservedWithPrematch:
    """§2.18 (T102/T103): two-phase fee estimate on top of
    compute_reserved_after's margin sizing."""

    def test_margin_part_matches_compute_reserved_after_ignoring_candidate_price(self):
        """Regression: an earlier version of compute_reserved_with_prematch
        blended the candidate's own limit price into the margin-sizing mark
        (via a "reservation_mark" that took max(risk_mark, order prices)).
        That broke acceptance-vectors.md 案例 2 (三代理跨价换手): C, with a
        wallet that only covers the position at the *current* risk_mark, is
        admitted to buy at a limit price *above* risk_mark because 账户合同
        §2.1 admission does not require covering notional at the order's own
        price -- 开仓不扣名义本金.  margin_part must equal
        compute_reserved_after's result (risk_mark-only), independent of
        how far the candidate's limit price is from risk_mark."""
        risk_mark = P100
        candidate = ActiveOrder("BUY", price_ticks=P100 + 5000, quantity_units=units(10))
        reserved, fee_immediate, fee_resting = compute_reserved_with_prematch(
            position_units=0,
            active_orders=[],
            candidate=candidate,
            pre_match=PreMatchResult(
                immediate_qty_units=units(10),
                immediate_notional=units(10) * risk_mark * MULT,
                resting_qty_units=0,
                reservation_mark_ticks=P100 + 5000,
            ),
            risk_mark_ticks=risk_mark,
            initial_bp=10000,
            fee_bps=0,
            mult=MULT,
        )
        baseline = compute_reserved_after(
            position_units=0,
            active_orders=[candidate],
            risk_mark_ticks=risk_mark,
            initial_bp=10000,
            fee_bps=0,
            mult=MULT,
        )
        assert reserved == baseline
        assert fee_immediate == 0
        assert fee_resting == 0

    def test_fee_immediate_uses_prematch_real_notional_not_candidate_price(self):
        """Positive case: fee_immediate must be priced off
        pre_match.immediate_notional (real per-level maker prices), not
        candidate.quantity_units * candidate.price_ticks."""
        candidate = ActiveOrder("BUY", price_ticks=P100 + 200, quantity_units=units(10))
        pre_match = PreMatchResult(
            immediate_qty_units=units(10),
            immediate_notional=units(10) * P100 * MULT,  # real fill price = P100
            resting_qty_units=0,
            reservation_mark_ticks=P100 + 200,
        )
        _reserved, fee_immediate, fee_resting = compute_reserved_with_prematch(
            position_units=0,
            active_orders=[],
            candidate=candidate,
            pre_match=pre_match,
            risk_mark_ticks=P100,
            initial_bp=INITIAL_BP,
            fee_bps=FEE_BPS,
            mult=MULT,
        )
        naive_fee = (units(10) * (P100 + 200) * MULT * FEE_BPS) // 10000
        real_fee = (units(10) * P100 * MULT * FEE_BPS + 9999) // 10000  # div_ceil
        assert fee_immediate == real_fee
        assert fee_immediate != naive_fee
        assert fee_resting == 0

    def test_fee_resting_covers_active_orders_and_candidate_leftover_at_own_prices(self):
        """resting_qty_units > 0 (candidate partially rests) must be fee'd
        at the candidate's own limit price; existing active_orders keep
        being fee'd at their own resting prices, same as
        compute_reserved_after."""
        existing = ActiveOrder("SELL", price_ticks=P100 - 50, quantity_units=units(5))
        candidate = ActiveOrder("BUY", price_ticks=P100 + 50, quantity_units=units(10))
        pre_match = PreMatchResult(
            immediate_qty_units=units(4),
            immediate_notional=units(4) * P100 * MULT,
            resting_qty_units=units(6),
            reservation_mark_ticks=P100 + 50,
        )
        _reserved, fee_immediate, fee_resting = compute_reserved_with_prematch(
            position_units=0,
            active_orders=[existing],
            candidate=candidate,
            pre_match=pre_match,
            risk_mark_ticks=P100,
            initial_bp=INITIAL_BP,
            fee_bps=FEE_BPS,
            mult=MULT,
        )
        expected_resting_notional = units(5) * (P100 - 50) * MULT + units(6) * (P100 + 50) * MULT
        expected_fee_resting = (expected_resting_notional * FEE_BPS + 9999) // 10000
        assert fee_resting == expected_fee_resting

    def test_zero_fee_bps_yields_zero_fees_regardless_of_prematch(self):
        candidate = ActiveOrder("BUY", price_ticks=P100 + 500, quantity_units=units(10))
        pre_match = PreMatchResult(
            immediate_qty_units=units(10),
            immediate_notional=units(10) * P100 * MULT,
            resting_qty_units=0,
            reservation_mark_ticks=P100 + 500,
        )
        reserved, fee_immediate, fee_resting = compute_reserved_with_prematch(
            position_units=0,
            active_orders=[],
            candidate=candidate,
            pre_match=pre_match,
            risk_mark_ticks=P100,
            initial_bp=INITIAL_BP,
            fee_bps=0,
            mult=MULT,
        )
        assert fee_immediate == 0
        assert fee_resting == 0
        assert reserved == compute_reserved_after(
            position_units=0,
            active_orders=[candidate],
            risk_mark_ticks=P100,
            initial_bp=INITIAL_BP,
            fee_bps=0,
            mult=MULT,
        )

    def test_no_prematch_falls_back_to_flat_all_orders_notional(self):
        """pre_match=None (no book-walk info available) must fall back to
        pricing every order -- including the candidate -- at its own
        price, matching compute_reserved_after's fee_part exactly."""
        candidate = ActiveOrder("BUY", price_ticks=P100, quantity_units=units(10))
        reserved, fee_immediate, fee_resting = compute_reserved_with_prematch(
            position_units=0,
            active_orders=[],
            candidate=candidate,
            pre_match=None,
            risk_mark_ticks=P100,
            initial_bp=INITIAL_BP,
            fee_bps=FEE_BPS,
            mult=MULT,
        )
        baseline = compute_reserved_after(
            position_units=0,
            active_orders=[candidate],
            risk_mark_ticks=P100,
            initial_bp=INITIAL_BP,
            fee_bps=FEE_BPS,
            mult=MULT,
        )
        assert fee_immediate == 0
        assert reserved == baseline
