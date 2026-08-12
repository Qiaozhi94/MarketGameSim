"""T301/T307: Price-time priority order book (stdlib only, KR-005).

[撮合 §1.1] 买方按 price_ticks 降序、卖方按升序；同价位按 transaction_seq 升序。
[撮合 §6]   空簿与单边簿的 valuation_mark 退化规则。
[撮合 §7]   确定性：不依赖字典遍历顺序、对象哈希。

Structure:
  - ``_bids`` / ``_asks``: ``dict[int, deque[RestingOrder]]`` mapping
    price_ticks to a FIFO queue of orders at that level.
  - ``_bid_prices`` / ``_ask_prices``: sorted ``list[int]`` (ascending)
    maintained via ``bisect.insort`` on level creation and ``list.remove``
    on level depletion.  Best bid = last element; best ask = first element.

Within a price level, orders are appended to the right and consumed from
the left, so insertion order (which matches transaction_seq order) gives
time priority without any dict iteration.
"""

from __future__ import annotations

import bisect
from collections import deque
from dataclasses import dataclass
from typing import Literal

Side = Literal["BUY", "SELL"]


@dataclass
class RestingOrder:
    order_id: str
    agent_id: str
    side: Side
    order_type: str
    price_ticks: int
    quantity_units: int
    transaction_seq: int


class Book:
    """Price-time priority order book with integer-only arithmetic."""

    def __init__(self, initial_price_ticks: int = 10000) -> None:
        self._bids: dict[int, deque[RestingOrder]] = {}
        self._asks: dict[int, deque[RestingOrder]] = {}
        self._bid_prices: list[int] = []
        self._ask_prices: list[int] = []
        self.last_ticks: int | None = None
        self._initial_price_ticks: int = initial_price_ticks
        self._dirty: bool = False
        # benchmarks/README.md §2 第二层：硬件无关的算法回归断言
        # ("book_operations_golden") -- counts structural mutations (insert/
        # pop), not queries; a call-count regression here would flag a
        # matching-loop change that calls the book a different number of
        # times for the same config+seed, independent of wall-clock noise.
        self.operation_count: int = 0

    # ------------------------------------------------------------------ #
    # Insertion
    # ------------------------------------------------------------------ #

    def insert(self, order: RestingOrder) -> None:
        book, prices = self._side_refs(order.side)
        price = order.price_ticks
        if price not in book:
            book[price] = deque()
            bisect.insort(prices, price)
        book[price].append(order)
        self._dirty = True
        self.operation_count += 1

    # ------------------------------------------------------------------ #
    # Best-price queries
    # ------------------------------------------------------------------ #

    def best_bid(self) -> int | None:
        return self._bid_prices[-1] if self._bid_prices else None

    def best_ask(self) -> int | None:
        return self._ask_prices[0] if self._ask_prices else None

    def best_opposite(self, taker_side: Side) -> int | None:
        return self.best_ask() if taker_side == "BUY" else self.best_bid()

    def peek_best_maker(self, maker_side: Side) -> RestingOrder | None:
        book, prices = self._side_refs(maker_side)
        if not prices:
            return None
        best_price = prices[-1] if maker_side == "BUY" else prices[0]
        return book[best_price][0]

    def pop_best_maker(self, maker_side: Side) -> RestingOrder | None:
        book, prices = self._side_refs(maker_side)
        if not prices:
            return None
        best_price = prices[-1] if maker_side == "BUY" else prices[0]
        dq = book[best_price]
        order = dq.popleft()
        if not dq:
            del book[best_price]
            prices.remove(best_price)
        self._dirty = True
        self.operation_count += 1
        return order

    # ------------------------------------------------------------------ #
    # Valuation mark (§6)
    # ------------------------------------------------------------------ #

    def valuation_mark_half_ticks(self) -> int:
        bb = self.best_bid()
        ba = self.best_ask()
        if bb is not None and ba is not None:
            return bb + ba
        if self.last_ticks is not None:
            return self.last_ticks * 2
        return self._initial_price_ticks * 2

    # ------------------------------------------------------------------ #
    # Aggregate state (for assertions / MARKET_DATA_PUBLISH)
    # ------------------------------------------------------------------ #

    def bid_levels(self) -> list[tuple[int, int]]:
        """[(price, total_qty), ...] sorted descending."""
        return [
            (p, sum(o.quantity_units for o in self._bids[p])) for p in reversed(self._bid_prices)
        ]

    def ask_levels(self) -> list[tuple[int, int]]:
        """[(price, total_qty), ...] sorted ascending."""
        return [(p, sum(o.quantity_units for o in self._asks[p])) for p in self._ask_prices]

    def bid_depth_k(self) -> int:
        return len(self._bid_prices)

    def ask_depth_k(self) -> int:
        return len(self._ask_prices)

    def level_aggregates(self) -> dict:
        """Bid/ask levels with price, total qty, and resting-order count.

        Mirrors the ``BOOK`` snapshot aggregation (event-schema §4.6.2):
        bids descending, asks ascending.  Exposed for the 0.1.4 replay
        oracle; ``order_count`` cannot be derived from quantity alone.
        """
        bids = [
            {
                "price_ticks": p,
                "quantity_units": sum(o.quantity_units for o in self._bids[p]),
                "order_count": len(self._bids[p]),
            }
            for p in reversed(self._bid_prices)
        ]
        asks = [
            {
                "price_ticks": p,
                "quantity_units": sum(o.quantity_units for o in self._asks[p]),
                "order_count": len(self._asks[p]),
            }
            for p in self._ask_prices
        ]
        return {"bids": bids, "asks": asks}

    # ------------------------------------------------------------------ #
    # Dirty flag (for MARKET_DATA_PUBLISH trigger)
    # ------------------------------------------------------------------ #

    @property
    def dirty(self) -> bool:
        return self._dirty

    def reset_dirty(self) -> None:
        self._dirty = False

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _side_refs(self, side: Side) -> tuple[dict[int, deque[RestingOrder]], list[int]]:
        if side == "BUY":
            return self._bids, self._bid_prices
        return self._asks, self._ask_prices
