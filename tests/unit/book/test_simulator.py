"""T306b: Visibility atomicity -- single transaction, multiple fills.

[撮合 §1.2] ORDER_ARRIVAL is the transaction boundary.
[事件 Schema §1.5] In-transaction state changes are immediately visible.

Acceptance: one large order crosses three levels -> three TRADE_SETTLE
(fill_index 0/1/2, fill_count 3) + only one risk check (stubbed for 0.1.1).
Expected values per OB-4 in orderbook-vectors.md.
"""

from __future__ import annotations

from market_game_sim.book.orderbook import Book
from market_game_sim.book.simulator import BookLevel, run_simulation


def _buy(order_id: str, agent_id: str, price: int, qty: int, t: int = 100) -> dict:
    return {
        "event_type": "ORDER_ARRIVAL", "timestamp": t,
        "agent_id": agent_id, "order_id": order_id,
        "action": "SUBMIT", "side": "BUY", "order_type": "LIMIT",
        "price_ticks": price, "quantity_units": qty,
    }


class TestVisibilityAtomicity:
    def test_three_fills_single_transaction(self):
        records, book = run_simulation(
            initial_book_levels=[
                BookLevel("SELL", "a1", "M", 10000, 2000),
                BookLevel("SELL", "a2", "M", 10100, 2000),
                BookLevel("SELL", "a3", "M", 10200, 2000),
                BookLevel("BUY", "n1", "N", 9900, 10000),
            ],
            events=[_buy("t1", "T", 10200, 5000)],
        )
        biz = [r for r in records if r["transaction_seq"] >= 3]
        trades = [r for r in biz if r["event_type"] == "TRADE_SETTLE"]
        assert len(trades) == 3

    def test_all_trades_share_transaction_seq(self):
        records, _ = run_simulation(
            initial_book_levels=[
                BookLevel("SELL", "a1", "M", 10000, 2000),
                BookLevel("SELL", "a2", "M", 10100, 2000),
                BookLevel("SELL", "a3", "M", 10200, 2000),
                BookLevel("BUY", "n1", "N", 9900, 10000),
            ],
            events=[_buy("t1", "T", 10200, 5000)],
        )
        biz = [r for r in records if r["transaction_seq"] >= 3]
        trades = [r for r in biz if r["event_type"] == "TRADE_SETTLE"]
        seqs = {t["transaction_seq"] for t in trades}
        assert len(seqs) == 1

    def test_fill_index_0_1_2(self):
        records, _ = run_simulation(
            initial_book_levels=[
                BookLevel("SELL", "a1", "M", 10000, 2000),
                BookLevel("SELL", "a2", "M", 10100, 2000),
                BookLevel("SELL", "a3", "M", 10200, 2000),
                BookLevel("BUY", "n1", "N", 9900, 10000),
            ],
            events=[_buy("t1", "T", 10200, 5000)],
        )
        biz = [r for r in records if r["transaction_seq"] >= 3]
        trades = [r for r in biz if r["event_type"] == "TRADE_SETTLE"]
        assert [t["fill_index"] for t in trades] == [0, 1, 2]

    def test_fill_count_is_3_on_all(self):
        records, _ = run_simulation(
            initial_book_levels=[
                BookLevel("SELL", "a1", "M", 10000, 2000),
                BookLevel("SELL", "a2", "M", 10100, 2000),
                BookLevel("SELL", "a3", "M", 10200, 2000),
                BookLevel("BUY", "n1", "N", 9900, 10000),
            ],
            events=[_buy("t1", "T", 10200, 5000)],
        )
        biz = [r for r in records if r["transaction_seq"] >= 3]
        trades = [r for r in biz if r["event_type"] == "TRADE_SETTLE"]
        assert all(t["fill_count"] == 3 for t in trades)

    def test_vm_advances_per_fill(self):
        records, _ = run_simulation(
            initial_book_levels=[
                BookLevel("SELL", "a1", "M", 10000, 2000),
                BookLevel("SELL", "a2", "M", 10100, 2000),
                BookLevel("SELL", "a3", "M", 10200, 2000),
                BookLevel("BUY", "n1", "N", 9900, 10000),
            ],
            events=[_buy("t1", "T", 10200, 5000)],
        )
        biz = [r for r in records if r["transaction_seq"] >= 3]
        trades = [r for r in biz if r["event_type"] == "TRADE_SETTLE"]
        assert trades[0]["valuation_mark_before_half_ticks"] == 19900
        assert trades[0]["valuation_mark_after_half_ticks"] == 20000
        assert trades[1]["valuation_mark_before_half_ticks"] == 20000
        assert trades[1]["valuation_mark_after_half_ticks"] == 20100
        assert trades[2]["valuation_mark_before_half_ticks"] == 20100
        assert trades[2]["valuation_mark_after_half_ticks"] == 20100

    def test_risk_mark_per_fill(self):
        records, _ = run_simulation(
            initial_book_levels=[
                BookLevel("SELL", "a1", "M", 10000, 2000),
                BookLevel("SELL", "a2", "M", 10100, 2000),
                BookLevel("SELL", "a3", "M", 10200, 2000),
                BookLevel("BUY", "n1", "N", 9900, 10000),
            ],
            events=[_buy("t1", "T", 10200, 5000)],
        )
        biz = [r for r in records if r["transaction_seq"] >= 3]
        trades = [r for r in biz if r["event_type"] == "TRADE_SETTLE"]
        assert [t["risk_mark_ticks"] for t in trades] == [10000, 10100, 10200]

    def test_only_one_market_data_publish(self):
        records, _ = run_simulation(
            initial_book_levels=[
                BookLevel("SELL", "a1", "M", 10000, 2000),
                BookLevel("SELL", "a2", "M", 10100, 2000),
                BookLevel("SELL", "a3", "M", 10200, 2000),
                BookLevel("BUY", "n1", "N", 9900, 10000),
            ],
            events=[_buy("t1", "T", 10200, 5000)],
        )
        biz = [r for r in records if r["transaction_seq"] >= 3]
        mdp = [r for r in biz if r["event_type"] == "MARKET_DATA_PUBLISH"]
        assert len(mdp) == 1

    def test_market_data_publish_is_last(self):
        records, _ = run_simulation(
            initial_book_levels=[
                BookLevel("SELL", "a1", "M", 10000, 2000),
                BookLevel("SELL", "a2", "M", 10100, 2000),
                BookLevel("SELL", "a3", "M", 10200, 2000),
                BookLevel("BUY", "n1", "N", 9900, 10000),
            ],
            events=[_buy("t1", "T", 10200, 5000)],
        )
        biz = [r for r in records if r["transaction_seq"] >= 3]
        assert biz[-1]["event_type"] == "MARKET_DATA_PUBLISH"

    def test_post_tx_book_state(self):
        _, book = run_simulation(
            initial_book_levels=[
                BookLevel("SELL", "a1", "M", 10000, 2000),
                BookLevel("SELL", "a2", "M", 10100, 2000),
                BookLevel("SELL", "a3", "M", 10200, 2000),
                BookLevel("BUY", "n1", "N", 9900, 10000),
            ],
            events=[_buy("t1", "T", 10200, 5000)],
        )
        assert book.bid_levels() == [(9900, 10000)]
        assert book.ask_levels() == [(10200, 1000)]

    def test_log_keys_strictly_increasing(self):
        records, _ = run_simulation(
            initial_book_levels=[
                BookLevel("SELL", "a1", "M", 10000, 2000),
                BookLevel("SELL", "a2", "M", 10100, 2000),
                BookLevel("SELL", "a3", "M", 10200, 2000),
                BookLevel("BUY", "n1", "N", 9900, 10000),
            ],
            events=[_buy("t1", "T", 10200, 5000)],
        )
        keys = [(r["timestamp"], r["transaction_seq"], r["record_index"]) for r in records]
        for i in range(1, len(keys)):
            assert keys[i] > keys[i - 1]
