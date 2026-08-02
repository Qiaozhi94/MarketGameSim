"""T305: Self-trade prevention (cancel-resting) dedicated tests.

[撮合 §4] maker_agent_id == taker_agent_id -> cancel maker, taker continues.
[事件 Schema §4.7] ORDER_CANCELLED with reason=SELF_TRADE_PREVENTION.
"""

from __future__ import annotations

from market_game_sim.book.matching import match_order
from market_game_sim.book.orderbook import Book, RestingOrder
from market_game_sim.eventlog.bootstrap import build_account_payload, build_book_payload
from market_game_sim.kernel.runner import EventKernel


def _rest_sell(book: Book, order_id: str, agent_id: str, price: int, qty: int) -> None:
    book.insert(RestingOrder(order_id, agent_id, "SELL", "LIMIT", price, qty, 0))


def _rest_buy(book: Book, order_id: str, agent_id: str, price: int, qty: int) -> None:
    book.insert(RestingOrder(order_id, agent_id, "BUY", "LIMIT", price, qty, 0))


def _buy(order_id: str, agent_id: str, price: int, qty: int, t: int = 100) -> dict:
    return {
        "event_type": "ORDER_ARRIVAL",
        "timestamp": t,
        "agent_id": agent_id,
        "order_id": order_id,
        "action": "SUBMIT",
        "side": "BUY",
        "order_type": "LIMIT",
        "price_ticks": price,
        "quantity_units": qty,
    }


def _sell(order_id: str, agent_id: str, price: int, qty: int, t: int = 100) -> dict:
    return {
        "event_type": "ORDER_ARRIVAL",
        "timestamp": t,
        "agent_id": agent_id,
        "order_id": order_id,
        "action": "SUBMIT",
        "side": "SELL",
        "order_type": "LIMIT",
        "price_ticks": price,
        "quantity_units": qty,
    }


def _run(event: dict, book: Book) -> list[dict]:
    kernel = EventKernel(run_id="stp")
    kernel.bootstrap(build_account_payload([]), build_book_payload(last_ticks=None))
    world = {"book": book}
    kernel.enqueue(event)
    kernel.run(match_order, world, max_transactions=100)
    return [r for r in kernel.committed_records if r["transaction_seq"] >= 3]


class TestSelfTradeCancelResting:
    def test_cancels_resting_not_taker(self):
        book = Book()
        _rest_sell(book, "s1", "A", 10000, 2000)
        _rest_sell(book, "s2", "B", 10100, 2000)
        records = _run(_buy("t1", "A", 10100, 3000), book)
        cancels = [r for r in records if r["event_type"] == "ORDER_CANCELLED"]
        assert len(cancels) == 1
        assert cancels[0]["order_id"] == "s1"
        assert cancels[0]["agent_id"] == "A"
        assert cancels[0]["side"] == "SELL"
        assert cancels[0]["order_type"] == "LIMIT"
        assert cancels[0]["reason"] == "SELF_TRADE_PREVENTION"
        assert cancels[0]["cancelled_qty_units"] == 2000
        assert cancels[0]["price_ticks"] == 10000

    def test_taker_continues_to_next_level(self):
        book = Book()
        _rest_sell(book, "s1", "A", 10000, 2000)
        _rest_sell(book, "s2", "B", 10100, 2000)
        records = _run(_buy("t1", "A", 10100, 3000), book)
        trades = [r for r in records if r["event_type"] == "TRADE_SETTLE"]
        assert len(trades) == 1
        assert trades[0]["maker_order_id"] == "s2"
        assert trades[0]["price_ticks"] == 10100
        assert trades[0]["quantity_units"] == 2000

    def test_taker_qty_not_consumed_by_self_cancel(self):
        book = Book()
        _rest_sell(book, "s1", "A", 10000, 2000)
        _rest_sell(book, "s2", "B", 10100, 2000)
        records = _run(_buy("t1", "A", 10100, 3000), book)
        trades = [r for r in records if r["event_type"] == "TRADE_SETTLE"]
        assert trades[0]["quantity_units"] == 2000
        assert book.bid_levels() == [(10100, 1000)]

    def test_multiple_self_trades_cancel_all(self):
        book = Book()
        _rest_sell(book, "s1", "A", 10000, 2000)
        _rest_sell(book, "s2", "A", 10100, 2000)
        _rest_sell(book, "s3", "B", 10200, 2000)
        records = _run(_buy("t1", "A", 10200, 5000), book)
        cancels = [r for r in records if r["event_type"] == "ORDER_CANCELLED"]
        assert len(cancels) == 2
        assert {c["order_id"] for c in cancels} == {"s1", "s2"}
        trades = [r for r in records if r["event_type"] == "TRADE_SETTLE"]
        assert len(trades) == 1
        assert trades[0]["maker_order_id"] == "s3"

    def test_self_trade_sell_taker_cancels_buy_maker(self):
        book = Book()
        _rest_buy(book, "b1", "A", 10100, 2000)
        _rest_buy(book, "b2", "B", 10000, 2000)
        records = _run(_sell("t1", "A", 10000, 3000), book)
        cancels = [r for r in records if r["event_type"] == "ORDER_CANCELLED"]
        assert len(cancels) == 1
        assert cancels[0]["order_id"] == "b1"
        assert cancels[0]["side"] == "BUY"
        trades = [r for r in records if r["event_type"] == "TRADE_SETTLE"]
        assert len(trades) == 1
        assert trades[0]["maker_order_id"] == "b2"

    def test_record_index_fill_index_misalignment(self):
        """OB-7: record_index and fill_index diverge due to self-trade cancel."""
        book = Book()
        _rest_sell(book, "s1", "A", 10000, 2000)
        _rest_sell(book, "s2", "B", 10100, 2000)
        records = _run(_buy("t1", "A", 10100, 3000), book)
        cancel = [r for r in records if r["event_type"] == "ORDER_CANCELLED"][0]
        trade = [r for r in records if r["event_type"] == "TRADE_SETTLE"][0]
        assert cancel["record_index"] == 1
        assert trade["record_index"] == 2
        assert trade["fill_index"] == 0

    def test_no_self_trade_different_agents(self):
        book = Book()
        _rest_sell(book, "s1", "M", 10000, 2000)
        records = _run(_buy("t1", "T", 10100, 2000), book)
        cancels = [r for r in records if r["event_type"] == "ORDER_CANCELLED"]
        assert len(cancels) == 0
        trades = [r for r in records if r["event_type"] == "TRADE_SETTLE"]
        assert len(trades) == 1

    def test_caused_by_event_id_points_to_r0(self):
        book = Book()
        _rest_sell(book, "s1", "A", 10000, 2000)
        _rest_sell(book, "s2", "B", 10100, 2000)
        records = _run(_buy("t1", "A", 10100, 3000), book)
        r0 = records[0]
        expected_caused_by = f"e{r0['transaction_seq']}_0"
        for r in records[1:]:
            if r["event_type"] in ("ORDER_CANCELLED", "TRADE_SETTLE"):
                assert r["caused_by_event_id"] == expected_caused_by
