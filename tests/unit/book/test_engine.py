"""ADR-013: L1a matching core, used standalone (no ledger, no kernel, no world).

[撮合 §2.1] fill price = maker price; [撮合 §2.2] per-level split with
per-fill valuation marks; [撮合 §3] LIMIT rests / MARKET IOC remainder;
[撮合 §4] self-trade cancel-resting interleaved with fills.
"""

from __future__ import annotations

from market_game_sim.book import engine
from market_game_sim.book.engine import Fill, IncomingOrder, SelfTradeCancel
from market_game_sim.book.orderbook import Book, RestingOrder


def _rest(book: Book, oid: str, owner: str, side: str, price: int, qty: int, seq: int = 0):
    book.insert(RestingOrder(oid, owner, side, "LIMIT", price, qty, seq))  # type: ignore[arg-type]


def _order(
    side: str = "BUY",
    order_type: str = "LIMIT",
    price: int | None = 10_010,
    qty: int = 10,
    owner: str = "taker",
    seq: int = 7,
) -> IncomingOrder:
    return IncomingOrder(
        order_id="o-in",
        owner_id=owner,
        side=side,  # type: ignore[arg-type]
        order_type=order_type,  # type: ignore[arg-type]
        price_ticks=price,
        quantity_units=qty,
        sequence=seq,
    )


def _ladder() -> Book:
    book = Book(initial_price_ticks=10_000)
    _rest(book, "b1", "mm", "BUY", 9_990, 5)
    _rest(book, "a1", "mm", "SELL", 10_000, 3)
    _rest(book, "a2", "mm2", "SELL", 10_000, 4)
    _rest(book, "a3", "mm", "SELL", 10_010, 6)
    return book


def test_sweeps_levels_in_price_time_order_with_per_fill_marks() -> None:
    book = _ladder()
    result = engine.match(book, _order(qty=10))

    assert [(f.maker_order_id, f.price_ticks, f.quantity_units) for f in result.fills] == [
        ("a1", 10_000, 3),
        ("a2", 10_000, 4),
        ("a3", 10_010, 3),
    ]
    assert [f.maker_consumed for f in result.fills] == [True, True, False]
    marks = [
        (f.valuation_mark_before_half_ticks, f.valuation_mark_after_half_ticks)
        for f in result.fills
    ]
    assert marks == [(19_990, 19_990), (19_990, 20_000), (20_000, 20_000)]
    assert result.rested is None and result.unfilled_units == 0
    assert book.ask_levels() == [(10_010, 3)]
    assert book.last_ticks == 10_010


def test_limit_remainder_rests_with_sequence_and_market_remainder_is_dropped() -> None:
    limit_book = _ladder()
    limit = engine.match(limit_book, _order(price=10_000, qty=9, seq=42))
    assert sum(f.quantity_units for f in limit.fills) == 7
    assert limit.rested is not None
    assert (limit.rested.price_ticks, limit.rested.quantity_units) == (10_000, 2)
    assert limit.rested.transaction_seq == 42
    assert limit_book.bid_levels()[0] == (10_000, 2)
    assert limit.unfilled_units == 0

    market_book = _ladder()
    market = engine.match(market_book, _order(order_type="MARKET", price=None, qty=20))
    assert sum(f.quantity_units for f in market.fills) == 13
    assert market.rested is None
    assert market.unfilled_units == 7
    assert market_book.ask_levels() == []


def test_non_crossing_limit_rests_without_touching_the_other_side() -> None:
    book = _ladder()
    ops_before = book.operation_count
    result = engine.match(book, _order(price=9_995, qty=2))
    assert result.steps == ()
    assert result.rested is not None
    assert book.ask_levels() == [(10_000, 7), (10_010, 6)]
    assert book.last_ticks is None
    assert book.operation_count == ops_before + 1


def test_self_trade_cancel_is_interleaved_and_carries_the_mark_at_that_instant() -> None:
    book = _ladder()
    result = engine.match(book, _order(owner="mm2", qty=10))

    kinds = [type(s).__name__ for s in result.steps]
    assert kinds == ["Fill", "SelfTradeCancel", "Fill"]
    stp = result.steps[1]
    assert isinstance(stp, SelfTradeCancel)
    assert stp.order.order_id == "a2"
    assert stp.last_ticks == 10_000  # set by the preceding fill, not the final price
    last = result.steps[2]
    assert isinstance(last, Fill) and last.quantity_units == 6
    assert result.rested is not None and result.rested.quantity_units == 1
    assert book.last_ticks == 10_010


def test_cancel_removes_only_the_named_order() -> None:
    book = _ladder()
    removed = engine.cancel(book, "a2")
    assert removed is not None and removed.order_id == "a2"
    assert book.ask_levels() == [(10_000, 3), (10_010, 6)]
    assert engine.cancel(book, "a2") is None
    assert engine.cancel(book, "nope") is None


def test_dry_run_matches_real_match_and_does_not_mutate() -> None:
    book = _ladder()
    before = (book.bid_levels(), book.ask_levels(), book.operation_count, book.last_ticks)
    qty, price_qty = engine.dry_run(book, "BUY", 10_010, 10)
    assert (book.bid_levels(), book.ask_levels(), book.operation_count, book.last_ticks) == before
    assert qty == 10
    assert price_qty == 3 * 10_000 + 4 * 10_000 + 3 * 10_010

    fills = engine.match(book, _order(qty=10)).fills
    assert sum(f.quantity_units for f in fills) == qty
    assert sum(f.quantity_units * f.price_ticks for f in fills) == price_qty

    assert engine.dry_run(Book(), "SELL", 1, 5) == (0, 0)
