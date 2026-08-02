"""T301/T307: Order book structure and degenerate-state tests.

[撮合 §1.1] 价格优先 + 时间优先
[撮合 §6]   空簿 / 单边簿 valuation_mark 退化
[撮合 §7]   确定性: 不依赖字典遍历顺序
"""

from __future__ import annotations

from market_game_sim.book.orderbook import Book, RestingOrder


def _resting(
    order_id: str, agent_id: str, side: str, price: int, qty: int, txn_seq: int = 0
) -> RestingOrder:
    return RestingOrder(
        order_id=order_id,
        agent_id=agent_id,
        side=side,
        order_type="LIMIT",
        price_ticks=price,
        quantity_units=qty,
        transaction_seq=txn_seq,
    )


class TestBookStructure:
    """T301: price-time priority ordering."""

    def test_best_bid_is_highest_price(self):
        book = Book()
        book.insert(_resting("b1", "A", "BUY", 9900, 100))
        book.insert(_resting("b2", "A", "BUY", 10100, 100))
        book.insert(_resting("b3", "A", "BUY", 10000, 100))
        assert book.best_bid() == 10100

    def test_best_ask_is_lowest_price(self):
        book = Book()
        book.insert(_resting("s1", "A", "SELL", 10200, 100))
        book.insert(_resting("s2", "A", "SELL", 10000, 100))
        book.insert(_resting("s3", "A", "SELL", 10100, 100))
        assert book.best_ask() == 10000

    def test_empty_book_best_bid_ask_none(self):
        book = Book()
        assert book.best_bid() is None
        assert book.best_ask() is None

    def test_time_priority_within_same_price_buy(self):
        book = Book()
        book.insert(_resting("o1", "A", "BUY", 10000, 100, txn_seq=3))
        book.insert(_resting("o2", "B", "BUY", 10000, 100, txn_seq=5))
        maker = book.peek_best_maker("BUY")
        assert maker is not None
        assert maker.order_id == "o1"

    def test_time_priority_within_same_price_sell(self):
        book = Book()
        book.insert(_resting("s1", "A", "SELL", 10000, 100, txn_seq=3))
        book.insert(_resting("s2", "B", "SELL", 10000, 100, txn_seq=5))
        maker = book.peek_best_maker("SELL")
        assert maker is not None
        assert maker.order_id == "s1"

    def test_pop_best_maker_buy_returns_highest_first(self):
        book = Book()
        book.insert(_resting("b1", "A", "BUY", 10000, 100))
        book.insert(_resting("b2", "A", "BUY", 10100, 100))
        first = book.pop_best_maker("BUY")
        assert first is not None
        assert first.order_id == "b2"
        assert book.best_bid() == 10000

    def test_pop_best_maker_sell_returns_lowest_first(self):
        book = Book()
        book.insert(_resting("s1", "A", "SELL", 10100, 100))
        book.insert(_resting("s2", "A", "SELL", 10000, 100))
        first = book.pop_best_maker("SELL")
        assert first is not None
        assert first.order_id == "s2"
        assert book.best_ask() == 10100

    def test_pop_removes_empty_price_level(self):
        book = Book()
        book.insert(_resting("s1", "A", "SELL", 10000, 100))
        book.pop_best_maker("SELL")
        assert book.best_ask() is None
        assert book.ask_depth_k() == 0

    def test_pop_partial_keeps_level(self):
        book = Book()
        book.insert(_resting("s1", "A", "SELL", 10000, 100))
        maker = book.peek_best_maker("SELL")
        assert maker is not None
        maker.quantity_units -= 40
        if maker.quantity_units == 0:
            book.pop_best_maker("SELL")
        else:
            book._dirty = True
        assert book.best_ask() == 10000
        levels = book.ask_levels()
        assert levels == [(10000, 60)]

    def test_bid_levels_sorted_descending(self):
        book = Book()
        book.insert(_resting("b1", "A", "BUY", 10000, 100))
        book.insert(_resting("b2", "A", "BUY", 10100, 200))
        book.insert(_resting("b3", "A", "BUY", 9900, 300))
        assert book.bid_levels() == [(10100, 200), (10000, 100), (9900, 300)]

    def test_ask_levels_sorted_ascending(self):
        book = Book()
        book.insert(_resting("s1", "A", "SELL", 10200, 100))
        book.insert(_resting("s2", "A", "SELL", 10000, 200))
        book.insert(_resting("s3", "A", "SELL", 10100, 300))
        assert book.ask_levels() == [(10000, 200), (10100, 300), (10200, 100)]

    def test_aggregate_qty_at_same_price(self):
        book = Book()
        book.insert(_resting("b1", "A", "BUY", 10000, 3000, txn_seq=3))
        book.insert(_resting("b2", "B", "BUY", 10000, 5000, txn_seq=4))
        assert book.bid_levels() == [(10000, 8000)]

    def test_depth_k_counts_price_levels(self):
        book = Book()
        book.insert(_resting("b1", "A", "BUY", 10000, 100))
        book.insert(_resting("b2", "A", "BUY", 10000, 200))
        book.insert(_resting("b3", "A", "BUY", 10100, 300))
        assert book.bid_depth_k() == 2

    def test_dirty_flag_on_insert(self):
        book = Book()
        assert not book.dirty
        book.insert(_resting("b1", "A", "BUY", 10000, 100))
        assert book.dirty
        book.reset_dirty()
        assert not book.dirty

    def test_dirty_flag_on_pop(self):
        book = Book()
        book.insert(_resting("b1", "A", "BUY", 10000, 100))
        book.reset_dirty()
        book.pop_best_maker("BUY")
        assert book.dirty

    def test_deterministic_ordering_no_dict_dependency(self):
        """Insert in non-sorted order; best price must still be correct."""
        book = Book()
        prices_asks = [10500, 10100, 10300, 10000, 10400, 10200]
        for i, p in enumerate(prices_asks):
            book.insert(_resting(f"s{i}", "A", "SELL", p, 100))
        assert book.best_ask() == 10000
        assert [p for p, _ in book.ask_levels()] == sorted(prices_asks)


class TestDegenerateStates:
    """T307: empty book and single-side book valuation_mark."""

    def test_empty_book_vm_is_initial_price_doubled(self):
        book = Book(initial_price_ticks=10000)
        assert book.valuation_mark_half_ticks() == 20000

    def test_empty_book_last_none(self):
        book = Book()
        assert book.last_ticks is None

    def test_single_side_bid_vm_is_last_doubled(self):
        book = Book(initial_price_ticks=10000)
        book.last_ticks = 10500
        book.insert(_resting("b1", "A", "BUY", 10000, 100))
        assert book.valuation_mark_half_ticks() == 10500 * 2

    def test_single_side_ask_vm_is_last_doubled(self):
        book = Book(initial_price_ticks=10000)
        book.last_ticks = 9500
        book.insert(_resting("s1", "A", "SELL", 10000, 100))
        assert book.valuation_mark_half_ticks() == 9500 * 2

    def test_single_side_no_last_vm_is_initial_doubled(self):
        book = Book(initial_price_ticks=10000)
        book.insert(_resting("b1", "A", "BUY", 10000, 100))
        assert book.valuation_mark_half_ticks() == 20000

    def test_both_sides_vm_is_bid_plus_ask(self):
        book = Book(initial_price_ticks=10000)
        book.insert(_resting("b1", "A", "BUY", 9900, 100))
        book.insert(_resting("s1", "A", "SELL", 10100, 100))
        assert book.valuation_mark_half_ticks() == 9900 + 10100

    def test_both_sights_vm_ignores_last(self):
        """When both sides present, last_ticks is not used for vm."""
        book = Book(initial_price_ticks=10000)
        book.last_ticks = 9999
        book.insert(_resting("b1", "A", "BUY", 9900, 100))
        book.insert(_resting("s1", "A", "SELL", 10100, 100))
        assert book.valuation_mark_half_ticks() == 9900 + 10100
