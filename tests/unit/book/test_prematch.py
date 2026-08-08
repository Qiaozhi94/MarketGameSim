"""§2.18 (T102/T103): pre-match dry-run walk for two-phase fee estimation.

Round 4-9 of the 0.1.2 implementation review found ``compute_reserved_with_
prematch``/``PreMatchResult`` (ledger/reserved.py) were implemented but
never called from matching.py -- ``_populate_r0_defaults`` treated the
whole incoming order as one hypothetical resting order at its own limit
price, which systematically mis-estimates the fee for the
immediately-crossing portion (over for BUY, under for SELL -- the under
case lets under-margined orders through, per acceptance-vectors.md 案例 2's
economics of admission not requiring full notional at entry).
"""

from __future__ import annotations

from market_game_sim.book.matching import _pre_match, match_order
from market_game_sim.book.orderbook import Book, RestingOrder
from market_game_sim.eventlog.bootstrap import build_account_payload, build_book_payload
from market_game_sim.kernel.runner import EventKernel

MULT = 1000


def _rest(book: Book, side: str, price: int, qty: int, order_id: str, txn_seq: int = 0) -> None:
    book.insert(
        RestingOrder(
            order_id=order_id,
            agent_id="maker",
            side=side,
            order_type="LIMIT",
            price_ticks=price,
            quantity_units=qty,
            transaction_seq=txn_seq,
        )
    )


def _order(side: str, price: int | None, qty: int) -> dict:
    return {"side": side, "price_ticks": price, "quantity_units": qty}


def test_pre_match_empty_book_all_resting():
    book = Book(initial_price_ticks=10000)
    result = _pre_match(_order("BUY", 10000, 500), book, MULT)
    assert result.immediate_qty_units == 0
    assert result.immediate_notional == 0
    assert result.resting_qty_units == 500


def test_pre_match_single_level_full_fill_uses_real_maker_price():
    book = Book(initial_price_ticks=10000)
    _rest(book, "SELL", 9900, 500, "m1")
    result = _pre_match(_order("BUY", 10000, 500), book, MULT)
    assert result.immediate_qty_units == 500
    assert result.immediate_notional == 500 * 9900 * MULT
    assert result.resting_qty_units == 0


def test_pre_match_multi_level_uses_each_levels_real_price_not_candidate_price():
    """Candidate BUY 1500 @10200 crosses two ask levels (1000@10000,
    500@10100).  immediate_notional must be computed from the REAL prices
    walked (1000*10000 + 500*10100), not 1500*10200 (candidate's own limit
    price) -- this is the exact defect §2.18 reports."""
    book = Book(initial_price_ticks=10000)
    _rest(book, "SELL", 10000, 1000, "m1")
    _rest(book, "SELL", 10100, 1000, "m2")
    result = _pre_match(_order("BUY", 10200, 1500), book, MULT)
    assert result.immediate_qty_units == 1500
    expected_real_notional = (1000 * 10000 + 500 * 10100) * MULT
    naive_candidate_price_notional = 1500 * 10200 * MULT
    assert result.immediate_notional == expected_real_notional
    assert result.immediate_notional != naive_candidate_price_notional
    assert result.immediate_notional < naive_candidate_price_notional
    assert result.resting_qty_units == 0


def test_pre_match_sell_crossing_underestimate_direction():
    """Mirror of the BUY case for SELL: real notional from walking real bid
    prices must be HIGHER than using the candidate's own (lower) limit
    price for the whole quantity -- this is the direction that previously
    let under-margined orders through (老实现低估该部分真实手续费)."""
    book = Book(initial_price_ticks=10000)
    _rest(book, "BUY", 10200, 1000, "m1")
    _rest(book, "BUY", 10100, 1000, "m2")
    result = _pre_match(_order("SELL", 10000, 1500), book, MULT)
    expected_real_notional = (1000 * 10200 + 500 * 10100) * MULT
    naive_candidate_price_notional = 1500 * 10000 * MULT
    assert result.immediate_notional == expected_real_notional
    assert result.immediate_notional > naive_candidate_price_notional


def test_pre_match_stops_at_limit_price_leaves_remainder_resting():
    """Candidate BUY 1000 @9950 only crosses the 9900 level (500 qty);
    the deeper 10000 level is beyond its limit, so 500 units must be
    reported as resting, not immediately filled."""
    book = Book(initial_price_ticks=10000)
    _rest(book, "SELL", 9900, 500, "m1")
    _rest(book, "SELL", 10000, 1000, "m2")
    result = _pre_match(_order("BUY", 9950, 1000), book, MULT)
    assert result.immediate_qty_units == 500
    assert result.immediate_notional == 500 * 9900 * MULT
    assert result.resting_qty_units == 500
    assert result.reservation_mark_ticks == 9950


def test_pre_match_no_cross_all_resting():
    book = Book(initial_price_ticks=10000)
    _rest(book, "SELL", 10100, 500, "m1")
    result = _pre_match(_order("BUY", 10000, 500), book, MULT)
    assert result.immediate_qty_units == 0
    assert result.resting_qty_units == 500


def test_reserved_delta_wired_end_to_end_uses_real_prematch_fee():
    """§2.18 end-to-end wiring: _populate_r0_defaults must actually use
    _pre_match's real per-level prices for the admission-check
    reserved_delta_units, not the candidate's own limit price.

    T submits SELL 1500 @10000 (default fee_bps_cap=5, from world defaults
    maker_bps=-1/taker_bps=5) against two resting BUYs (1000@10200,
    1000@10100) -- crosses both levels fully.  The naive "whole order at
    own limit price" estimate (superseded by §2.18) would price the
    immediate portion's fee at 1500*10000*MULT, systematically UNDER the
    real 1000*10200*MULT + 500*10100*MULT (the exact under-reservation
    direction acceptance-vectors round 9/2.18 flagged as letting
    under-margined SELL-side orders through).
    """
    book = Book(initial_price_ticks=10000)
    _rest(book, "BUY", 10200, 1000, "m1")
    _rest(book, "BUY", 10100, 1000, "m2")

    kernel = EventKernel(run_id="prematch-wiring")
    kernel.bootstrap(build_account_payload([]), build_book_payload(last_ticks=None))
    world = {"book": book}
    event = {
        "event_type": "ORDER_ARRIVAL",
        "timestamp": 100,
        "agent_id": "T",
        "order_id": "t1",
        "action": "SUBMIT",
        "side": "SELL",
        "order_type": "LIMIT",
        "price_ticks": 10000,
        "quantity_units": 1500,
    }
    kernel.enqueue(event)
    kernel.run(match_order, world, max_transactions=100)

    order_arrival = next(
        r
        for r in kernel.committed_records
        if r.get("event_type") == "ORDER_ARRIVAL" and r.get("order_id") == "t1"
    )
    real_immediate_notional = 1000 * 10200 * MULT + 500 * 10100 * MULT
    real_fee_immediate = (real_immediate_notional * 5 + 9999) // 10000
    margin_part = (
        1500 * 10000 * MULT
    )  # worst_abs(1500) * risk_mark(10000, no trade yet) * MULT * 100%
    expected_reserved_delta = margin_part + real_fee_immediate

    naive_notional = 1500 * 10000 * MULT  # candidate's own limit price for the whole qty
    naive_fee = (naive_notional * 5 + 9999) // 10000
    naive_reserved_delta = margin_part + naive_fee

    assert order_arrival["reserved_delta_units"] == expected_reserved_delta
    assert order_arrival["reserved_delta_units"] != naive_reserved_delta
    assert order_arrival["reserved_delta_units"] > naive_reserved_delta
