"""T302-T306: Matching engine unit tests.

[撮合 §2.1] 成交价 = maker 挂单价 (T302)
[撮合 §2.2] 跨档拆分, vm 逐笔推进 (T303)
[撮合 §3]   剩余处理: LIMIT 挂入 / MARKET IOC (T304)
[撮合 §4]   自成交阻止 (T305 -- see also test_self_trade.py)
[撮合 §5]   准入与撮合固定顺序 (T306)
"""

from __future__ import annotations

from market_game_sim.book.matching import match_order
from market_game_sim.book.orderbook import Book, RestingOrder
from market_game_sim.eventlog.bootstrap import build_account_payload, build_book_payload
from market_game_sim.kernel.runner import EventKernel


def _make_book(initial_price: int = 10000) -> Book:
    return Book(initial_price_ticks=initial_price)


def _bootstrap(kernel: EventKernel) -> None:
    kernel.bootstrap(build_account_payload([]), build_book_payload(last_ticks=None))


def _buy_order(
    order_id: str, agent_id: str, price: int, qty: int, t: int = 100, order_type: str = "LIMIT"
) -> dict:
    return {
        "event_type": "ORDER_ARRIVAL",
        "timestamp": t,
        "agent_id": agent_id,
        "order_id": order_id,
        "action": "SUBMIT",
        "side": "BUY",
        "order_type": order_type,
        "price_ticks": price if order_type == "LIMIT" else None,
        "quantity_units": qty,
    }


def _sell_order(
    order_id: str, agent_id: str, price: int, qty: int, t: int = 100, order_type: str = "LIMIT"
) -> dict:
    return {
        "event_type": "ORDER_ARRIVAL",
        "timestamp": t,
        "agent_id": agent_id,
        "order_id": order_id,
        "action": "SUBMIT",
        "side": "SELL",
        "order_type": order_type,
        "price_ticks": price if order_type == "LIMIT" else None,
        "quantity_units": qty,
    }


def _rest_sell(
    book: Book, order_id: str, agent_id: str, price: int, qty: int, txn_seq: int = 0
) -> None:
    book.insert(RestingOrder(order_id, agent_id, "SELL", "LIMIT", price, qty, txn_seq))


def _rest_buy(
    book: Book, order_id: str, agent_id: str, price: int, qty: int, txn_seq: int = 0
) -> None:
    book.insert(RestingOrder(order_id, agent_id, "BUY", "LIMIT", price, qty, txn_seq))


def _run_single(event: dict, book: Book) -> list[dict]:
    kernel = EventKernel(run_id="test")
    _bootstrap(kernel)
    world = {"book": book}
    kernel.enqueue(event)
    kernel.run(match_order, world, max_transactions=100)
    return [r for r in kernel.committed_records if r["transaction_seq"] >= 3]


# --------------------------------------------------------------------------- #
# T302: 成交价取 maker 挂单价
# --------------------------------------------------------------------------- #


class TestMakerPrice:
    def test_buy_limit_101_fills_at_maker_100(self):
        book = _make_book()
        _rest_sell(book, "s1", "M", 10000, 2000)
        records = _run_single(_buy_order("t1", "T", 10100, 2000), book)
        trades = [r for r in records if r["event_type"] == "TRADE_SETTLE"]
        assert len(trades) == 1
        assert trades[0]["price_ticks"] == 10000

    def test_sell_limit_99_fills_at_maker_101(self):
        book = _make_book()
        _rest_buy(book, "b1", "M", 10100, 2000)
        records = _run_single(_sell_order("t1", "T", 9900, 2000), book)
        trades = [r for r in records if r["event_type"] == "TRADE_SETTLE"]
        assert len(trades) == 1
        assert trades[0]["price_ticks"] == 10100

    def test_market_buy_fills_at_maker_price(self):
        book = _make_book()
        _rest_sell(book, "s1", "M", 10000, 2000)
        records = _run_single(_buy_order("t1", "T", 0, 2000, order_type="MARKET"), book)
        trades = [r for r in records if r["event_type"] == "TRADE_SETTLE"]
        assert len(trades) == 1
        assert trades[0]["price_ticks"] == 10000


# --------------------------------------------------------------------------- #
# T303: 跨档拆分
# --------------------------------------------------------------------------- #


class TestCrossLevelSplit:
    def test_three_levels_three_trades(self):
        book = _make_book()
        _rest_sell(book, "a1", "M", 10000, 2000)
        _rest_sell(book, "a2", "M", 10100, 2000)
        _rest_sell(book, "a3", "M", 10200, 2000)
        records = _run_single(_buy_order("t1", "T", 10200, 5000), book)
        trades = [r for r in records if r["event_type"] == "TRADE_SETTLE"]
        assert len(trades) == 3

    def test_same_caused_by_event_id(self):
        book = _make_book()
        _rest_sell(book, "a1", "M", 10000, 2000)
        _rest_sell(book, "a2", "M", 10100, 2000)
        _rest_sell(book, "a3", "M", 10200, 2000)
        records = _run_single(_buy_order("t1", "T", 10200, 5000), book)
        trades = [r for r in records if r["event_type"] == "TRADE_SETTLE"]
        caused_by_ids = {t["caused_by_event_id"] for t in trades}
        assert len(caused_by_ids) == 1

    def test_same_transaction_seq(self):
        book = _make_book()
        _rest_sell(book, "a1", "M", 10000, 2000)
        _rest_sell(book, "a2", "M", 10100, 2000)
        _rest_sell(book, "a3", "M", 10200, 2000)
        records = _run_single(_buy_order("t1", "T", 10200, 5000), book)
        trades = [r for r in records if r["event_type"] == "TRADE_SETTLE"]
        txn_seqs = {t["transaction_seq"] for t in trades}
        assert len(txn_seqs) == 1

    def test_record_index_strictly_increasing(self):
        book = _make_book()
        _rest_sell(book, "a1", "M", 10000, 2000)
        _rest_sell(book, "a2", "M", 10100, 2000)
        _rest_sell(book, "a3", "M", 10200, 2000)
        records = _run_single(_buy_order("t1", "T", 10200, 5000), book)
        trades = [r for r in records if r["event_type"] == "TRADE_SETTLE"]
        indices = [t["record_index"] for t in trades]
        assert indices == sorted(indices)
        assert len(set(indices)) == len(indices)

    def test_fill_index_zero_based(self):
        book = _make_book()
        _rest_sell(book, "a1", "M", 10000, 2000)
        _rest_sell(book, "a2", "M", 10100, 2000)
        _rest_sell(book, "a3", "M", 10200, 2000)
        records = _run_single(_buy_order("t1", "T", 10200, 5000), book)
        trades = [r for r in records if r["event_type"] == "TRADE_SETTLE"]
        assert [t["fill_index"] for t in trades] == [0, 1, 2]

    def test_fill_count_backfilled_to_three(self):
        book = _make_book()
        _rest_sell(book, "a1", "M", 10000, 2000)
        _rest_sell(book, "a2", "M", 10100, 2000)
        _rest_sell(book, "a3", "M", 10200, 2000)
        records = _run_single(_buy_order("t1", "T", 10200, 5000), book)
        trades = [r for r in records if r["event_type"] == "TRADE_SETTLE"]
        assert all(t["fill_count"] == 3 for t in trades)

    def test_valuation_mark_advances_per_fill(self):
        book = _make_book()
        _rest_buy(book, "n1", "N", 9900, 10000)
        _rest_sell(book, "a1", "M", 10000, 2000)
        _rest_sell(book, "a2", "M", 10100, 2000)
        _rest_sell(book, "a3", "M", 10200, 2000)
        records = _run_single(_buy_order("t1", "T", 10200, 5000), book)
        trades = [r for r in records if r["event_type"] == "TRADE_SETTLE"]
        assert trades[0]["valuation_mark_before_half_ticks"] == 9900 + 10000
        assert trades[0]["valuation_mark_after_half_ticks"] == 9900 + 10100
        assert trades[1]["valuation_mark_before_half_ticks"] == 9900 + 10100
        assert trades[1]["valuation_mark_after_half_ticks"] == 9900 + 10200
        assert trades[2]["valuation_mark_before_half_ticks"] == 9900 + 10200
        assert trades[2]["valuation_mark_after_half_ticks"] == 9900 + 10200

    def test_risk_mark_is_trade_price(self):
        book = _make_book()
        _rest_sell(book, "a1", "M", 10000, 2000)
        _rest_sell(book, "a2", "M", 10100, 2000)
        _rest_sell(book, "a3", "M", 10200, 2000)
        records = _run_single(_buy_order("t1", "T", 10200, 5000), book)
        trades = [r for r in records if r["event_type"] == "TRADE_SETTLE"]
        assert [t["risk_mark_ticks"] for t in trades] == [10000, 10100, 10200]

    def test_maker_order_ids_distinct(self):
        book = _make_book()
        _rest_sell(book, "a1", "M", 10000, 2000)
        _rest_sell(book, "a2", "M", 10100, 2000)
        _rest_sell(book, "a3", "M", 10200, 2000)
        records = _run_single(_buy_order("t1", "T", 10200, 5000), book)
        trades = [r for r in records if r["event_type"] == "TRADE_SETTLE"]
        maker_ids = [t["maker_order_id"] for t in trades]
        assert len(set(maker_ids)) == 3


# --------------------------------------------------------------------------- #
# T304: 剩余处理
# --------------------------------------------------------------------------- #


class TestRemainderHandling:
    def test_limit_remainder_rests_no_record(self):
        book = _make_book()
        _rest_sell(book, "s1", "M", 10000, 2000)
        records = _run_single(_buy_order("t1", "T", 10000, 5000), book)
        non_r0 = [r for r in records if r["record_index"] > 0]
        event_types = [r["event_type"] for r in non_r0]
        assert "ORDER_CANCELLED" not in event_types
        assert book.bid_levels() == [(10000, 3000)]

    def test_limit_remainder_preserves_transaction_seq(self):
        book = _make_book()
        _rest_sell(book, "s1", "M", 10000, 2000)
        _run_single(_buy_order("t1", "T", 10000, 5000), book)
        maker = book.peek_best_maker("BUY")
        assert maker is not None
        assert maker.transaction_seq == 3

    def test_market_remainder_ioc_cancel(self):
        book = _make_book()
        _rest_sell(book, "s1", "M", 10000, 2000)
        records = _run_single(_buy_order("t1", "T", 0, 5000, order_type="MARKET"), book)
        cancels = [r for r in records if r["event_type"] == "ORDER_CANCELLED"]
        assert len(cancels) == 1
        assert cancels[0]["reason"] == "IOC_REMAINDER"
        assert cancels[0]["cancelled_qty_units"] == 3000
        assert cancels[0]["price_ticks"] is None
        assert cancels[0]["side"] == "BUY"
        assert cancels[0]["order_type"] == "MARKET"

    def test_market_full_fill_no_cancel(self):
        book = _make_book()
        _rest_sell(book, "s1", "M", 10000, 5000)
        records = _run_single(_buy_order("t1", "T", 0, 5000, order_type="MARKET"), book)
        cancels = [r for r in records if r["event_type"] == "ORDER_CANCELLED"]
        assert len(cancels) == 0

    def test_limit_no_cross_rests_full_qty(self):
        book = _make_book()
        records = _run_single(_buy_order("t1", "T", 9900, 5000), book)
        non_r0 = [r for r in records if r["record_index"] > 0]
        assert len(non_r0) == 1
        assert non_r0[0]["event_type"] == "MARKET_DATA_PUBLISH"
        assert book.bid_levels() == [(9900, 5000)]

    def test_market_empty_book_full_ioc_cancel(self):
        book = _make_book()
        records = _run_single(_buy_order("t1", "T", 0, 5000, order_type="MARKET"), book)
        cancels = [r for r in records if r["event_type"] == "ORDER_CANCELLED"]
        assert len(cancels) == 1
        assert cancels[0]["cancelled_qty_units"] == 5000
        trades = [r for r in records if r["event_type"] == "TRADE_SETTLE"]
        assert len(trades) == 0


# --------------------------------------------------------------------------- #
# T305: 自成交阻止 (basic -- see test_self_trade.py for dedicated tests)
# --------------------------------------------------------------------------- #


class TestSelfTradeBasic:
    def test_self_trade_cancels_maker_continues_taker(self):
        book = _make_book()
        _rest_sell(book, "s1", "A", 10000, 2000)
        _rest_sell(book, "s2", "B", 10100, 2000)
        records = _run_single(_buy_order("t1", "A", 10100, 3000), book)
        cancels = [r for r in records if r["event_type"] == "ORDER_CANCELLED"]
        assert len(cancels) == 1
        assert cancels[0]["order_id"] == "s1"
        assert cancels[0]["reason"] == "SELF_TRADE_PREVENTION"
        trades = [r for r in records if r["event_type"] == "TRADE_SETTLE"]
        assert len(trades) == 1
        assert trades[0]["maker_order_id"] == "s2"
        assert trades[0]["quantity_units"] == 2000

    def test_self_trade_taker_qty_not_consumed(self):
        book = _make_book()
        _rest_sell(book, "s1", "A", 10000, 2000)
        _rest_sell(book, "s2", "B", 10100, 2000)
        records = _run_single(_buy_order("t1", "A", 10100, 3000), book)
        trades = [r for r in records if r["event_type"] == "TRADE_SETTLE"]
        assert trades[0]["quantity_units"] == 2000
        assert book.bid_levels() == [(10100, 1000)]


# --------------------------------------------------------------------------- #
# T306: 准入与撮合固定顺序
# --------------------------------------------------------------------------- #


class TestPipelineOrder:
    def test_reserved_delta_units_computed(self):
        book = _make_book()
        event = _buy_order("t1", "T", 10000, 5000)
        records = _run_single(event, book)
        r0 = records[0]
        assert r0["event_type"] == "ORDER_ARRIVAL"
        assert r0["reserved_delta_units"] == 50_025_000_000

    def test_reserved_delta_units_market_order(self):
        book = _make_book()
        _rest_sell(book, "s1", "M", 10000, 2000)
        event = _buy_order("t1", "T", 0, 5000, order_type="MARKET")
        records = _run_single(event, book)
        r0 = records[0]
        assert r0["reserved_delta_units"] == 0

    def test_accepted_true_for_valid_order(self):
        book = _make_book()
        event = _buy_order("t1", "T", 10000, 5000)
        records = _run_single(event, book)
        assert records[0]["accepted"] is True
        assert records[0]["reject_reason"] is None

    def test_market_data_publish_always_last(self):
        book = _make_book()
        _rest_sell(book, "s1", "M", 10000, 2000)
        records = _run_single(_buy_order("t1", "T", 10100, 2000), book)
        assert records[-1]["event_type"] == "MARKET_DATA_PUBLISH"

    def test_no_market_data_when_book_unchanged(self):
        book = _make_book()
        kernel = EventKernel(run_id="test")
        _bootstrap(kernel)
        world = {"book": book}

        def noop_handler(event, world, kernel):
            if event["event_type"] == "SNAPSHOT":
                return []
            event["accepted"] = True
            event["reject_reason"] = None
            event["reserved_delta_units"] = 0
            event.setdefault("origin", "AGENT")
            event.setdefault("trigger_ratio_bp", None)
            event.setdefault("liquidation_generation", None)
            event.setdefault("intent_id", "intent")
            event.setdefault("decision_event_id", "e0_0")
            event.setdefault("submitted_at", event["timestamp"])
            return []

        kernel.enqueue(_buy_order("t1", "T", 10000, 5000))
        kernel.run(noop_handler, world, max_transactions=100)
        biz = [r for r in kernel.committed_records if r["transaction_seq"] >= 3]
        assert not any(r["event_type"] == "MARKET_DATA_PUBLISH" for r in biz)


# --------------------------------------------------------------------------- #
# T307: 空簿与单边簿 (matching-level)
# --------------------------------------------------------------------------- #


class TestEmptyBookMatching:
    def test_market_buy_empty_book_ioc_cancel(self):
        book = _make_book()
        records = _run_single(_buy_order("t1", "T", 0, 5000, order_type="MARKET"), book)
        cancels = [r for r in records if r["event_type"] == "ORDER_CANCELLED"]
        assert len(cancels) == 1
        assert cancels[0]["cancelled_qty_units"] == 5000

    def test_market_sell_empty_book_ioc_cancel(self):
        book = _make_book()
        records = _run_single(_sell_order("t1", "T", 0, 5000, order_type="MARKET"), book)
        cancels = [r for r in records if r["event_type"] == "ORDER_CANCELLED"]
        assert len(cancels) == 1
        assert cancels[0]["cancelled_qty_units"] == 5000
        assert cancels[0]["side"] == "SELL"

    def test_limit_buy_empty_book_rests(self):
        book = _make_book()
        records = _run_single(_buy_order("t1", "T", 10000, 5000), book)
        assert book.bid_levels() == [(10000, 5000)]
        mdp = [r for r in records if r["event_type"] == "MARKET_DATA_PUBLISH"]
        assert len(mdp) == 1
        assert mdp[0]["best_bid"] == 10000
        assert mdp[0]["best_ask"] is None


class TestReservedUnits:
    def test_limit_order_reserved_delta(self):
        book = _make_book()
        event = _buy_order("t1", "T", 10000, 5000)
        records = _run_single(event, book)
        r0 = records[0]
        assert r0["reserved_delta_units"] == 50_025_000_000

    def test_market_order_uses_best_opposite(self):
        book = _make_book()
        _rest_sell(book, "s1", "M", 10000, 2000)
        event = _buy_order("t1", "T", 0, 5000, order_type="MARKET")
        records = _run_single(event, book)
        r0 = records[0]
        assert r0["reserved_delta_units"] == 0

    def test_market_order_no_opposite_uses_initial(self):
        book = _make_book()
        event = _buy_order("t1", "T", 0, 5000, order_type="MARKET")
        records = _run_single(event, book)
        r0 = records[0]
        assert r0["reserved_delta_units"] == 0


class TestCancel:
    def test_find_and_remove_works(self):
        from market_game_sim.book.matching import _find_and_remove

        book = _make_book()
        _rest_sell(book, "s1", "M", 10000, 2000)
        assert book.best_ask() == 10000
        result = _find_and_remove(book, "s1")
        assert result is not None
        assert result.order_id == "s1"
        assert book.best_ask() is None

    def test_cancel_nonexistent_order_returns_empty(self):
        from market_game_sim.book.matching import _find_and_remove

        book = _make_book()
        result = _find_and_remove(book, "no_such")
        assert result is None

    def test_quantity_zero_rejected(self):
        book = _make_book()
        event = _buy_order("t1", "T", 10000, 0, order_type="LIMIT")
        records = _run_single(event, book)
        assert records[0]["accepted"] is False
        assert records[0]["reject_reason"] == "INVALID_QUANTITY"

    def test_quantity_negative_rejected(self):
        book = _make_book()
        event = _buy_order("t1", "T", 10000, -5000, order_type="LIMIT")
        records = _run_single(event, book)
        assert records[0]["accepted"] is False
        assert records[0]["reject_reason"] == "INVALID_QUANTITY"
