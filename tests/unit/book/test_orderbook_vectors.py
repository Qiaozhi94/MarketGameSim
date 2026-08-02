"""T308: Order book acceptance vectors OB-1 through OB-7 and OB-9a.

Exit condition E3: all 8 vectors pass with integer-exact assertions.

[订单簿向量 §2] Each vector asserts:
  1. Event sequence (kind + record_index)
  2. TRADE_SETTLE fields: price_ticks, quantity_units, maker_order_id,
     fill_index, fill_count, vm_before, vm_after, risk_mark
  3. ORDER_CANCELLED fields: cancelled_qty_units, price_ticks, side, reason
  4. Post-transaction book state (aggregate qty per price level)
  5. All log_key strictly increasing

All comparisons are integer-exact. No tolerance assertions.

Bootstrap transactions (SNAPSHOT ACCOUNT/BOOK) are at transaction_seq 1,2;
business events start at transaction_seq 3. The OB vector tables use
relative transaction_seq (1,2,...) but tests use absolute values.
"""

from __future__ import annotations

from market_game_sim.book.simulator import BookLevel, run_simulation

T = 100


def _buy(oid: str, aid: str, price: int, qty: int, order_type: str = "LIMIT") -> dict:
    return {
        "event_type": "ORDER_ARRIVAL",
        "timestamp": T,
        "agent_id": aid,
        "order_id": oid,
        "action": "SUBMIT",
        "side": "BUY",
        "order_type": order_type,
        "price_ticks": price if order_type == "LIMIT" else None,
        "quantity_units": qty,
    }


def _sell(oid: str, aid: str, price: int, qty: int, order_type: str = "LIMIT") -> dict:
    return {
        "event_type": "ORDER_ARRIVAL",
        "timestamp": T,
        "agent_id": aid,
        "order_id": oid,
        "action": "SUBMIT",
        "side": "SELL",
        "order_type": order_type,
        "price_ticks": price if order_type == "LIMIT" else None,
        "quantity_units": qty,
    }


def _biz_records(records: list[dict]) -> list[dict]:
    return [r for r in records if r["transaction_seq"] >= 3]


def _assert_log_keys_increasing(records: list[dict]) -> None:
    keys = [(r["timestamp"], r["transaction_seq"], r["record_index"]) for r in records]
    for i in range(1, len(keys)):
        assert keys[i] > keys[i - 1], f"log_key not strictly increasing at {i}"


def _assert_event_sequence(biz: list[dict], expected: list[tuple[int, str]]) -> None:
    """expected = [(record_index, event_type), ...] within a single transaction."""
    actual = [(r["record_index"], r["event_type"]) for r in biz]
    assert actual == expected, f"Event sequence mismatch: {actual} != {expected}"


# --------------------------------------------------------------------------- #
# OB-1: Price priority
# --------------------------------------------------------------------------- #


class TestOB1PricePriority:
    """A BUY 10000×5000, B BUY 10100×5000, C SELL 10000×3000 -> fills at 10100."""

    def test_runs_without_error(self):
        records, book = run_simulation(
            events=[
                _buy("o1", "A", 10000, 5000),
                _buy("o2", "B", 10100, 5000),
                _sell("c1", "C", 10000, 3000),
            ],
        )
        assert records is not None

    def test_tx1_sequence(self):
        records, _ = run_simulation(
            events=[
                _buy("o1", "A", 10000, 5000),
                _buy("o2", "B", 10100, 5000),
                _sell("c1", "C", 10000, 3000),
            ]
        )
        biz = _biz_records(records)
        tx1 = [r for r in biz if r["transaction_seq"] == 3]
        _assert_event_sequence(tx1, [(0, "ORDER_ARRIVAL"), (1, "MARKET_DATA_PUBLISH")])

    def test_tx2_sequence(self):
        records, _ = run_simulation(
            events=[
                _buy("o1", "A", 10000, 5000),
                _buy("o2", "B", 10100, 5000),
                _sell("c1", "C", 10000, 3000),
            ]
        )
        biz = _biz_records(records)
        tx2 = [r for r in biz if r["transaction_seq"] == 4]
        _assert_event_sequence(tx2, [(0, "ORDER_ARRIVAL"), (1, "MARKET_DATA_PUBLISH")])

    def test_tx3_sequence_and_trade(self):
        records, _ = run_simulation(
            events=[
                _buy("o1", "A", 10000, 5000),
                _buy("o2", "B", 10100, 5000),
                _sell("c1", "C", 10000, 3000),
            ]
        )
        biz = _biz_records(records)
        tx3 = [r for r in biz if r["transaction_seq"] == 5]
        _assert_event_sequence(
            tx3, [(0, "ORDER_ARRIVAL"), (1, "TRADE_SETTLE"), (2, "MARKET_DATA_PUBLISH")]
        )
        trade = tx3[1]
        assert trade["price_ticks"] == 10100
        assert trade["quantity_units"] == 3000
        assert trade["maker_order_id"] == "o2"
        assert trade["fill_index"] == 0
        assert trade["fill_count"] == 1
        assert trade["valuation_mark_before_half_ticks"] == 20000
        assert trade["valuation_mark_after_half_ticks"] == 20200
        assert trade["risk_mark_ticks"] == 10100

    def test_post_tx_book(self):
        _, book = run_simulation(
            events=[
                _buy("o1", "A", 10000, 5000),
                _buy("o2", "B", 10100, 5000),
                _sell("c1", "C", 10000, 3000),
            ]
        )
        assert book.bid_levels() == [(10100, 2000), (10000, 5000)]
        assert book.ask_levels() == []

    def test_log_keys_increasing(self):
        records, _ = run_simulation(
            events=[
                _buy("o1", "A", 10000, 5000),
                _buy("o2", "B", 10100, 5000),
                _sell("c1", "C", 10000, 3000),
            ]
        )
        _assert_log_keys_increasing(records)


# --------------------------------------------------------------------------- #
# OB-2: Time priority (same price, by transaction_seq)
# --------------------------------------------------------------------------- #


class TestOB2TimePriority:
    """A BUY 10000×5000 (o1), B BUY 10000×5000 (o2), C SELL 10000×3000 -> fills o1."""

    def test_trade_hits_o1_not_o2(self):
        records, _ = run_simulation(
            events=[
                _buy("o1", "A", 10000, 5000),
                _buy("o2", "B", 10000, 5000),
                _sell("c1", "C", 10000, 3000),
            ]
        )
        biz = _biz_records(records)
        tx3 = [r for r in biz if r["transaction_seq"] == 5]
        trade = [r for r in tx3 if r["event_type"] == "TRADE_SETTLE"][0]
        assert trade["maker_order_id"] == "o1"
        assert trade["price_ticks"] == 10000
        assert trade["quantity_units"] == 3000

    def test_vm_before_after(self):
        records, _ = run_simulation(
            events=[
                _buy("o1", "A", 10000, 5000),
                _buy("o2", "B", 10000, 5000),
                _sell("c1", "C", 10000, 3000),
            ]
        )
        biz = _biz_records(records)
        trade = [r for r in biz if r["event_type"] == "TRADE_SETTLE"][0]
        assert trade["valuation_mark_before_half_ticks"] == 20000
        assert trade["valuation_mark_after_half_ticks"] == 20000
        assert trade["risk_mark_ticks"] == 10000

    def test_tx2_publishes_on_depth_change(self):
        records, _ = run_simulation(
            events=[
                _buy("o1", "A", 10000, 5000),
                _buy("o2", "B", 10000, 5000),
                _sell("c1", "C", 10000, 3000),
            ]
        )
        biz = _biz_records(records)
        tx2 = [r for r in biz if r["transaction_seq"] == 4]
        mdp = [r for r in tx2 if r["event_type"] == "MARKET_DATA_PUBLISH"]
        assert len(mdp) == 1
        assert mdp[0]["best_bid"] == 10000
        assert mdp[0]["best_ask"] is None

    def test_post_tx_book(self):
        _, book = run_simulation(
            events=[
                _buy("o1", "A", 10000, 5000),
                _buy("o2", "B", 10000, 5000),
                _sell("c1", "C", 10000, 3000),
            ]
        )
        assert book.bid_levels() == [(10000, 7000)]
        assert book.ask_levels() == []

    def test_log_keys_increasing(self):
        records, _ = run_simulation(
            events=[
                _buy("o1", "A", 10000, 5000),
                _buy("o2", "B", 10000, 5000),
                _sell("c1", "C", 10000, 3000),
            ]
        )
        _assert_log_keys_increasing(records)


# --------------------------------------------------------------------------- #
# OB-3: Price improvement
# --------------------------------------------------------------------------- #


class TestOB3PriceImprovement:
    """A SELL 10000×5000, B BUY 10100×3000 -> fills at 10000 (maker price)."""

    def test_trade_fills_at_maker_price(self):
        records, _ = run_simulation(
            events=[_sell("s1", "A", 10000, 5000), _buy("b1", "B", 10100, 3000)]
        )
        biz = _biz_records(records)
        trade = [r for r in biz if r["event_type"] == "TRADE_SETTLE"][0]
        assert trade["price_ticks"] == 10000
        assert trade["quantity_units"] == 3000

    def test_vm_values(self):
        records, _ = run_simulation(
            events=[_sell("s1", "A", 10000, 5000), _buy("b1", "B", 10100, 3000)]
        )
        biz = _biz_records(records)
        trade = [r for r in biz if r["event_type"] == "TRADE_SETTLE"][0]
        assert trade["valuation_mark_before_half_ticks"] == 20000
        assert trade["valuation_mark_after_half_ticks"] == 20000
        assert trade["risk_mark_ticks"] == 10000

    def test_fill_index_count(self):
        records, _ = run_simulation(
            events=[_sell("s1", "A", 10000, 5000), _buy("b1", "B", 10100, 3000)]
        )
        biz = _biz_records(records)
        trade = [r for r in biz if r["event_type"] == "TRADE_SETTLE"][0]
        assert trade["fill_index"] == 0
        assert trade["fill_count"] == 1

    def test_tx2_sequence(self):
        records, _ = run_simulation(
            events=[_sell("s1", "A", 10000, 5000), _buy("b1", "B", 10100, 3000)]
        )
        biz = _biz_records(records)
        tx2 = [r for r in biz if r["transaction_seq"] == 4]
        _assert_event_sequence(
            tx2, [(0, "ORDER_ARRIVAL"), (1, "TRADE_SETTLE"), (2, "MARKET_DATA_PUBLISH")]
        )

    def test_post_tx_book(self):
        _, book = run_simulation(
            events=[_sell("s1", "A", 10000, 5000), _buy("b1", "B", 10100, 3000)]
        )
        assert book.bid_levels() == []
        assert book.ask_levels() == [(10000, 2000)]

    def test_log_keys_increasing(self):
        records, _ = run_simulation(
            events=[_sell("s1", "A", 10000, 5000), _buy("b1", "B", 10100, 3000)]
        )
        _assert_log_keys_increasing(records)


# --------------------------------------------------------------------------- #
# OB-4: Cross three levels (vm advances per fill)
# --------------------------------------------------------------------------- #


class TestOB4CrossThreeLevels:
    """M sells 100×2/101×2/102×2, N buys 99×10. T buys 102×5 -> 3 fills."""

    LEVELS = [
        BookLevel("SELL", "a1", "M", 10000, 2000),
        BookLevel("SELL", "a2", "M", 10100, 2000),
        BookLevel("SELL", "a3", "M", 10200, 2000),
        BookLevel("BUY", "n1", "N", 9900, 10000),
    ]

    def test_three_trades_correct_prices(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS, events=[_buy("t1", "T", 10200, 5000)]
        )
        biz = _biz_records(records)
        trades = [r for r in biz if r["event_type"] == "TRADE_SETTLE"]
        assert len(trades) == 3
        assert [t["price_ticks"] for t in trades] == [10000, 10100, 10200]

    def test_quantities(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS, events=[_buy("t1", "T", 10200, 5000)]
        )
        trades = [r for r in _biz_records(records) if r["event_type"] == "TRADE_SETTLE"]
        assert [t["quantity_units"] for t in trades] == [2000, 2000, 1000]

    def test_maker_order_ids(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS, events=[_buy("t1", "T", 10200, 5000)]
        )
        trades = [r for r in _biz_records(records) if r["event_type"] == "TRADE_SETTLE"]
        assert [t["maker_order_id"] for t in trades] == ["a1", "a2", "a3"]

    def test_fill_index_and_count(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS, events=[_buy("t1", "T", 10200, 5000)]
        )
        trades = [r for r in _biz_records(records) if r["event_type"] == "TRADE_SETTLE"]
        assert [t["fill_index"] for t in trades] == [0, 1, 2]
        assert all(t["fill_count"] == 3 for t in trades)

    def test_vm_advances_per_fill(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS, events=[_buy("t1", "T", 10200, 5000)]
        )
        trades = [r for r in _biz_records(records) if r["event_type"] == "TRADE_SETTLE"]
        assert trades[0]["valuation_mark_before_half_ticks"] == 19900
        assert trades[0]["valuation_mark_after_half_ticks"] == 20000
        assert trades[1]["valuation_mark_before_half_ticks"] == 20000
        assert trades[1]["valuation_mark_after_half_ticks"] == 20100
        assert trades[2]["valuation_mark_before_half_ticks"] == 20100
        assert trades[2]["valuation_mark_after_half_ticks"] == 20100

    def test_risk_mark_per_fill(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS, events=[_buy("t1", "T", 10200, 5000)]
        )
        trades = [r for r in _biz_records(records) if r["event_type"] == "TRADE_SETTLE"]
        assert [t["risk_mark_ticks"] for t in trades] == [10000, 10100, 10200]

    def test_caused_by_same(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS, events=[_buy("t1", "T", 10200, 5000)]
        )
        trades = [r for r in _biz_records(records) if r["event_type"] == "TRADE_SETTLE"]
        ids = {t["caused_by_event_id"] for t in trades}
        assert len(ids) == 1

    def test_record_index_increasing(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS, events=[_buy("t1", "T", 10200, 5000)]
        )
        biz = _biz_records(records)
        _assert_event_sequence(
            biz,
            [
                (0, "ORDER_ARRIVAL"),
                (1, "TRADE_SETTLE"),
                (2, "TRADE_SETTLE"),
                (3, "TRADE_SETTLE"),
                (4, "MARKET_DATA_PUBLISH"),
            ],
        )

    def test_mdp_fields(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS, events=[_buy("t1", "T", 10200, 5000)]
        )
        mdp = [r for r in _biz_records(records) if r["event_type"] == "MARKET_DATA_PUBLISH"][0]
        assert mdp["best_bid"] == 9900
        assert mdp["best_ask"] == 10200

    def test_post_tx_book(self):
        _, book = run_simulation(
            initial_book_levels=self.LEVELS, events=[_buy("t1", "T", 10200, 5000)]
        )
        assert book.bid_levels() == [(9900, 10000)]
        assert book.ask_levels() == [(10200, 1000)]

    def test_log_keys_increasing(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS, events=[_buy("t1", "T", 10200, 5000)]
        )
        _assert_log_keys_increasing(records)


# --------------------------------------------------------------------------- #
# OB-5: Limit remainder rests (no record, preserves transaction_seq)
# --------------------------------------------------------------------------- #


class TestOB5LimitRemainder:
    """M sells 100×2. T buys 100×5 LIMIT -> fills 2000, rests 3000."""

    LEVELS = [BookLevel("SELL", "s1", "M", 10000, 2000)]

    def test_event_sequence(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS, events=[_buy("t1", "T", 10000, 5000)]
        )
        _assert_event_sequence(
            _biz_records(records),
            [
                (0, "ORDER_ARRIVAL"),
                (1, "TRADE_SETTLE"),
                (2, "MARKET_DATA_PUBLISH"),
            ],
        )

    def test_trade_fields(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS, events=[_buy("t1", "T", 10000, 5000)]
        )
        trade = [r for r in _biz_records(records) if r["event_type"] == "TRADE_SETTLE"][0]
        assert trade["price_ticks"] == 10000
        assert trade["quantity_units"] == 2000
        assert trade["fill_index"] == 0
        assert trade["fill_count"] == 1
        assert trade["valuation_mark_before_half_ticks"] == 20000
        assert trade["valuation_mark_after_half_ticks"] == 20000
        assert trade["risk_mark_ticks"] == 10000

    def test_no_cancel_record(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS, events=[_buy("t1", "T", 10000, 5000)]
        )
        cancels = [r for r in _biz_records(records) if r["event_type"] == "ORDER_CANCELLED"]
        assert len(cancels) == 0

    def test_post_tx_book(self):
        _, book = run_simulation(
            initial_book_levels=self.LEVELS, events=[_buy("t1", "T", 10000, 5000)]
        )
        assert book.bid_levels() == [(10000, 3000)]
        assert book.ask_levels() == []

    def test_resting_order_preserves_txn_seq(self):
        _, book = run_simulation(
            initial_book_levels=self.LEVELS, events=[_buy("t1", "T", 10000, 5000)]
        )
        maker = book.peek_best_maker("BUY")
        assert maker is not None
        assert maker.transaction_seq == 3

    def test_log_keys_increasing(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS, events=[_buy("t1", "T", 10000, 5000)]
        )
        _assert_log_keys_increasing(records)


# --------------------------------------------------------------------------- #
# OB-6: Market remainder IOC cancel
# --------------------------------------------------------------------------- #


class TestOB6MarketIOC:
    """M sells 100×2. T buys MARKET ×5 -> fills 2000, IOC cancels 3000."""

    LEVELS = [BookLevel("SELL", "s1", "M", 10000, 2000)]

    def test_event_sequence(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS, events=[_buy("t1", "T", 0, 5000, order_type="MARKET")]
        )
        _assert_event_sequence(
            _biz_records(records),
            [
                (0, "ORDER_ARRIVAL"),
                (1, "TRADE_SETTLE"),
                (2, "ORDER_CANCELLED"),
                (3, "MARKET_DATA_PUBLISH"),
            ],
        )

    def test_trade_fields(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS, events=[_buy("t1", "T", 0, 5000, order_type="MARKET")]
        )
        trade = [r for r in _biz_records(records) if r["event_type"] == "TRADE_SETTLE"][0]
        assert trade["price_ticks"] == 10000
        assert trade["quantity_units"] == 2000
        assert trade["fill_index"] == 0
        assert trade["fill_count"] == 1
        assert trade["valuation_mark_before_half_ticks"] == 20000
        assert trade["valuation_mark_after_half_ticks"] == 20000
        assert trade["risk_mark_ticks"] == 10000

    def test_cancel_fields(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS, events=[_buy("t1", "T", 0, 5000, order_type="MARKET")]
        )
        cancel = [r for r in _biz_records(records) if r["event_type"] == "ORDER_CANCELLED"][0]
        assert cancel["cancelled_qty_units"] == 3000
        assert cancel["price_ticks"] is None
        assert cancel["side"] == "BUY"
        assert cancel["order_type"] == "MARKET"
        assert cancel["reason"] == "IOC_REMAINDER"

    def test_post_tx_book_empty(self):
        _, book = run_simulation(
            initial_book_levels=self.LEVELS, events=[_buy("t1", "T", 0, 5000, order_type="MARKET")]
        )
        assert book.bid_levels() == []
        assert book.ask_levels() == []

    def test_mdp_fields(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS, events=[_buy("t1", "T", 0, 5000, order_type="MARKET")]
        )
        mdp = [r for r in _biz_records(records) if r["event_type"] == "MARKET_DATA_PUBLISH"][0]
        assert mdp["best_bid"] is None
        assert mdp["best_ask"] is None

    def test_log_keys_increasing(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS, events=[_buy("t1", "T", 0, 5000, order_type="MARKET")]
        )
        _assert_log_keys_increasing(records)


# --------------------------------------------------------------------------- #
# OB-7: Self-trade cancel-resting
# --------------------------------------------------------------------------- #


class TestOB7SelfTrade:
    """A sells 100×2 (s1), B sells 101×2 (s2). A buys 101×3 -> cancels s1, fills s2."""

    LEVELS = [
        BookLevel("SELL", "s1", "A", 10000, 2000),
        BookLevel("SELL", "s2", "B", 10100, 2000),
    ]

    def test_event_sequence(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS, events=[_buy("t1", "A", 10100, 3000)]
        )
        _assert_event_sequence(
            _biz_records(records),
            [
                (0, "ORDER_ARRIVAL"),
                (1, "ORDER_CANCELLED"),
                (2, "TRADE_SETTLE"),
                (3, "MARKET_DATA_PUBLISH"),
            ],
        )

    def test_cancel_fields(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS, events=[_buy("t1", "A", 10100, 3000)]
        )
        cancel = [r for r in _biz_records(records) if r["event_type"] == "ORDER_CANCELLED"][0]
        assert cancel["order_id"] == "s1"
        assert cancel["agent_id"] == "A"
        assert cancel["cancelled_qty_units"] == 2000
        assert cancel["price_ticks"] == 10000
        assert cancel["side"] == "SELL"
        assert cancel["order_type"] == "LIMIT"
        assert cancel["reason"] == "SELF_TRADE_PREVENTION"

    def test_trade_fields(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS, events=[_buy("t1", "A", 10100, 3000)]
        )
        trade = [r for r in _biz_records(records) if r["event_type"] == "TRADE_SETTLE"][0]
        assert trade["price_ticks"] == 10100
        assert trade["quantity_units"] == 2000
        assert trade["maker_order_id"] == "s2"
        assert trade["fill_index"] == 0
        assert trade["fill_count"] == 1
        assert trade["valuation_mark_before_half_ticks"] == 20000
        assert trade["valuation_mark_after_half_ticks"] == 20200
        assert trade["risk_mark_ticks"] == 10100

    def test_record_index_fill_index_misalignment(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS, events=[_buy("t1", "A", 10100, 3000)]
        )
        biz = _biz_records(records)
        cancel = [r for r in biz if r["event_type"] == "ORDER_CANCELLED"][0]
        trade = [r for r in biz if r["event_type"] == "TRADE_SETTLE"][0]
        assert cancel["record_index"] == 1
        assert trade["record_index"] == 2
        assert trade["fill_index"] == 0

    def test_post_tx_book(self):
        _, book = run_simulation(
            initial_book_levels=self.LEVELS, events=[_buy("t1", "A", 10100, 3000)]
        )
        assert book.bid_levels() == [(10100, 1000)]
        assert book.ask_levels() == []

    def test_mdp_fields(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS, events=[_buy("t1", "A", 10100, 3000)]
        )
        mdp = [r for r in _biz_records(records) if r["event_type"] == "MARKET_DATA_PUBLISH"][0]
        assert mdp["best_bid"] == 10100
        assert mdp["best_ask"] is None

    def test_log_keys_increasing(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS, events=[_buy("t1", "A", 10100, 3000)]
        )
        _assert_log_keys_increasing(records)


# --------------------------------------------------------------------------- #
# OB-9a: Same-timestamp dual orders see committed state
# --------------------------------------------------------------------------- #


class TestOB9aSameTimestampDualOrders:
    """M sells 10000×2000 (s1) and 10100×2000 (s2). A and B both buy 10100×2000.
    A fills s1 at 10000; B must fill s2 at 10100 (not 10000)."""

    LEVELS = [
        BookLevel("SELL", "s1", "M", 10000, 2000),
        BookLevel("SELL", "s2", "M", 10100, 2000),
    ]

    def test_a_fills_at_10000(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS,
            events=[_buy("a1", "A", 10100, 2000), _buy("b1", "B", 10100, 2000)],
        )
        trades = [r for r in _biz_records(records) if r["event_type"] == "TRADE_SETTLE"]
        assert trades[0]["price_ticks"] == 10000
        assert trades[0]["maker_order_id"] == "s1"

    def test_b_fills_at_10100_not_10000(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS,
            events=[_buy("a1", "A", 10100, 2000), _buy("b1", "B", 10100, 2000)],
        )
        trades = [r for r in _biz_records(records) if r["event_type"] == "TRADE_SETTLE"]
        assert trades[1]["price_ticks"] == 10100
        assert trades[1]["maker_order_id"] == "s2"

    def test_vm_continuity(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS,
            events=[_buy("a1", "A", 10100, 2000), _buy("b1", "B", 10100, 2000)],
        )
        trades = [r for r in _biz_records(records) if r["event_type"] == "TRADE_SETTLE"]
        assert trades[0]["valuation_mark_before_half_ticks"] == 20000
        assert trades[0]["valuation_mark_after_half_ticks"] == 20000
        assert trades[1]["valuation_mark_before_half_ticks"] == 20000
        assert trades[1]["valuation_mark_after_half_ticks"] == 20200

    def test_risk_marks(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS,
            events=[_buy("a1", "A", 10100, 2000), _buy("b1", "B", 10100, 2000)],
        )
        trades = [r for r in _biz_records(records) if r["event_type"] == "TRADE_SETTLE"]
        assert trades[0]["risk_mark_ticks"] == 10000
        assert trades[1]["risk_mark_ticks"] == 10100

    def test_fill_index_count(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS,
            events=[_buy("a1", "A", 10100, 2000), _buy("b1", "B", 10100, 2000)],
        )
        trades = [r for r in _biz_records(records) if r["event_type"] == "TRADE_SETTLE"]
        for t in trades:
            assert t["fill_index"] == 0
            assert t["fill_count"] == 1

    def test_tx1_sequence(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS,
            events=[_buy("a1", "A", 10100, 2000), _buy("b1", "B", 10100, 2000)],
        )
        tx1 = [r for r in _biz_records(records) if r["transaction_seq"] == 3]
        _assert_event_sequence(
            tx1, [(0, "ORDER_ARRIVAL"), (1, "TRADE_SETTLE"), (2, "MARKET_DATA_PUBLISH")]
        )

    def test_tx2_sequence(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS,
            events=[_buy("a1", "A", 10100, 2000), _buy("b1", "B", 10100, 2000)],
        )
        tx2 = [r for r in _biz_records(records) if r["transaction_seq"] == 4]
        _assert_event_sequence(
            tx2, [(0, "ORDER_ARRIVAL"), (1, "TRADE_SETTLE"), (2, "MARKET_DATA_PUBLISH")]
        )

    def test_mdp_after_a(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS,
            events=[_buy("a1", "A", 10100, 2000), _buy("b1", "B", 10100, 2000)],
        )
        biz = _biz_records(records)
        mdp1 = [
            r for r in biz if r["transaction_seq"] == 3 and r["event_type"] == "MARKET_DATA_PUBLISH"
        ][0]
        assert mdp1["best_bid"] is None
        assert mdp1["best_ask"] == 10100

    def test_mdp_after_b(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS,
            events=[_buy("a1", "A", 10100, 2000), _buy("b1", "B", 10100, 2000)],
        )
        biz = _biz_records(records)
        mdp2 = [
            r for r in biz if r["transaction_seq"] == 4 and r["event_type"] == "MARKET_DATA_PUBLISH"
        ][0]
        assert mdp2["best_bid"] is None
        assert mdp2["best_ask"] is None

    def test_post_tx_book_empty(self):
        _, book = run_simulation(
            initial_book_levels=self.LEVELS,
            events=[_buy("a1", "A", 10100, 2000), _buy("b1", "B", 10100, 2000)],
        )
        assert book.bid_levels() == []
        assert book.ask_levels() == []

    def test_six_log_keys_strictly_increasing(self):
        records, _ = run_simulation(
            initial_book_levels=self.LEVELS,
            events=[_buy("a1", "A", 10100, 2000), _buy("b1", "B", 10100, 2000)],
        )
        biz = _biz_records(records)
        assert len(biz) == 6
        _assert_log_keys_increasing(biz)
