"""L1a matching core (ADR-013): orders in, match outcomes out.

[撮合 §1.1] 价格时间优先（由 :class:`Book` 保证）
[撮合 §2.1] 成交价 = maker 挂单价
[撮合 §2.2] 跨档逐笔拆分，valuation_mark 逐笔推进
[撮合 §3]   剩余处理：LIMIT 挂入簿，MARKET IOC 返回未成交量
[撮合 §4]   自成交阻止：cancel-resting
[撮合 §7]   确定性：纯整数、无字典遍历顺序依赖

This module is the generic half of L1: it knows order books and nothing
else.  It must not import ``ledger``/``hook``/``kernel``/``eventlog`` or any
upper layer (locked by ``tests/unit/book/test_engine_isolation.py``) -- no
accounts, margin, fees, liquidation, event ids or regime rules.  Those live
in L1b (``book/matching.py``), which consumes a :class:`MatchResult` step by
step and turns it into ledger postings and events.

Everything a caller needs to settle a step is carried on the step itself
(identities, price, quantity, marks at that instant), so L1b never has to
read the book mid-match and the core stays reusable without the ledger.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Literal

from market_game_sim.book.orderbook import Book, RestingOrder, Side

OrderType = Literal["LIMIT", "MARKET"]


@dataclass(frozen=True)
class IncomingOrder:
    """The order-flow port: one order as the matching core sees it.

    ``owner_id`` is only used for self-trade prevention; ``sequence`` is the
    time-priority stamp the order carries if it rests.
    """

    order_id: str
    owner_id: str
    side: Side
    order_type: OrderType
    price_ticks: int | None
    quantity_units: int
    sequence: int


@dataclass(frozen=True)
class Fill:
    """One maker level consumed (fully or partially) by the incoming order."""

    maker_order_id: str
    maker_owner_id: str
    maker_side: Side
    price_ticks: int
    quantity_units: int
    maker_consumed: bool
    valuation_mark_before_half_ticks: int
    valuation_mark_after_half_ticks: int


@dataclass(frozen=True)
class SelfTradeCancel:
    """A resting order of the same owner, removed instead of being filled.

    ``last_ticks`` is the book's last trade price at the moment of removal
    (earlier fills in the same match may already have moved it).
    """

    order: RestingOrder
    last_ticks: int | None


MatchStep = Fill | SelfTradeCancel


@dataclass(frozen=True)
class MatchResult:
    """Ordered outcome of one incoming order.

    ``steps`` preserves the exact interleaving of fills and self-trade
    cancels.  After the steps, exactly one of these holds for a remainder:
    ``rested`` is the order now resting in the book (LIMIT), or
    ``unfilled_units > 0`` is an IOC remainder that was dropped (MARKET).
    """

    steps: tuple[MatchStep, ...]
    rested: RestingOrder | None
    unfilled_units: int

    @property
    def fills(self) -> tuple[Fill, ...]:
        return tuple(s for s in self.steps if isinstance(s, Fill))


def crosses(taker_side: Side, limit_price: int | None, maker_price: int) -> bool:
    if limit_price is None:
        return True
    if taker_side == "BUY":
        return maker_price <= limit_price
    return maker_price >= limit_price


def match(book: Book, order: IncomingOrder) -> MatchResult:
    """Match ``order`` against ``book`` and mutate the book accordingly."""
    taker_side = order.side
    opposite_side: Side = "SELL" if taker_side == "BUY" else "BUY"
    remaining = order.quantity_units
    limit_price = order.price_ticks
    vm_running = book.valuation_mark_half_ticks()
    steps: list[MatchStep] = []

    while remaining > 0:
        maker = book.peek_best_maker(opposite_side)
        if maker is None:
            break
        if not crosses(taker_side, limit_price, maker.price_ticks):
            break

        if maker.agent_id == order.owner_id:
            cancelled = book.pop_best_maker(opposite_side)
            assert cancelled is not None
            steps.append(SelfTradeCancel(order=cancelled, last_ticks=book.last_ticks))
            continue

        fill_qty = min(remaining, maker.quantity_units)
        vm_before = vm_running
        maker.quantity_units -= fill_qty
        remaining -= fill_qty
        maker_consumed = maker.quantity_units == 0
        if maker_consumed:
            book.pop_best_maker(opposite_side)
        else:
            book._dirty = True
        book.last_ticks = maker.price_ticks
        vm_after = book.valuation_mark_half_ticks()
        vm_running = vm_after
        steps.append(
            Fill(
                maker_order_id=maker.order_id,
                maker_owner_id=maker.agent_id,
                maker_side=maker.side,
                price_ticks=maker.price_ticks,
                quantity_units=fill_qty,
                maker_consumed=maker_consumed,
                valuation_mark_before_half_ticks=vm_before,
                valuation_mark_after_half_ticks=vm_after,
            )
        )

    rested: RestingOrder | None = None
    unfilled = 0
    if remaining > 0:
        if order.order_type == "LIMIT":
            assert limit_price is not None
            rested = RestingOrder(
                order_id=order.order_id,
                agent_id=order.owner_id,
                side=taker_side,
                order_type="LIMIT",
                price_ticks=limit_price,
                quantity_units=remaining,
                transaction_seq=order.sequence,
            )
            book.insert(rested)
        else:
            unfilled = remaining
    return MatchResult(steps=tuple(steps), rested=rested, unfilled_units=unfilled)


def cancel(book: Book, order_id: str) -> RestingOrder | None:
    """Remove a resting order by id; ``None`` if it is not in the book."""
    for side in ("BUY", "SELL"):
        book_dict, prices = book._side_refs(side)
        for price in list(prices):
            dq = book_dict[price]
            for o in dq:
                if o.order_id == order_id:
                    new_dq = deque((x for x in dq if x.order_id != order_id), maxlen=dq.maxlen)
                    if new_dq:
                        book_dict[price] = new_dq
                    else:
                        del book_dict[price]
                        prices.remove(price)
                    book._dirty = True
                    return o
    return None


def dry_run(
    book: Book, side: Side, limit_price: int | None, quantity_units: int
) -> tuple[int, int]:
    """Non-mutating walk of the opposite side at real per-level prices.

    Returns ``(immediate_qty_units, immediate_price_qty_sum)`` where the
    second value is ``sum(take * level_price)`` -- the caller scales it into
    cash units.  Self-trade-prevention skips are not modelled: a level that
    would be skipped counts as fillable (the conservative direction for any
    worst-case estimate built on top of this).
    """
    levels = book.ask_levels() if side == "BUY" else book.bid_levels()
    remaining = quantity_units
    immediate_qty = 0
    price_qty_sum = 0
    for level_price, level_qty in levels:
        if remaining <= 0:
            break
        if not crosses(side, limit_price, level_price):
            break
        take = min(remaining, level_qty)
        immediate_qty += take
        price_qty_sum += take * level_price
        remaining -= take
    return immediate_qty, price_qty_sum
