"""T306b/T308 + T405: Simulation helper that runs an event list through the kernel.

Wraps :class:`EventKernel` + :func:`match_order` into a single call that
handles bootstrap, pre-existing resting orders, and event enqueueing.
Used by the OB-1-OB-7/OB-9a acceptance vectors (T308) and the Phase-4
account acceptance vectors (T407).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from market_game_sim.book.matching import match_order
from market_game_sim.book.orderbook import Book, RestingOrder, Side
from market_game_sim.eventlog.bootstrap import (
    build_account_payload,
    build_account_payload_from_accounts,
    build_book_payload,
)
from market_game_sim.kernel.runner import EventKernel
from market_game_sim.ledger.account import Account


@dataclass(frozen=True)
class BookLevel:
    side: Side
    order_id: str
    agent_id: str
    price_ticks: int
    quantity_units: int


def run_simulation(
    initial_book_levels: list[BookLevel] | None = None,
    events: list[dict] | None = None,
    initial_price_ticks: int = 10000,
    *,
    max_transactions: int = 10000,
    run_id: str = "sim",
    accounts: dict[str, Account] | None = None,
    config: Any | None = None,
    maker_bps: int | None = None,
    taker_bps: int | None = None,
    mult: int = 1000,
) -> tuple[list[dict], Book]:
    """Run events through the kernel and return (records, book).

    When ``config`` is provided it drives MULT/fees/initial-price and the
    bootstrap ACCOUNT snapshot.  Otherwise BENCH-001 defaults are used
    (mult=1000; maker/taker bps from the explicit args or -1/5).  An
    optional ``accounts`` mapping seeds the ledger and is **mutated in
    place** -- callers read final account state from the dict they passed.
    Agents not in the mapping are auto-created with a generous default
    wallet on first trade (sufficient for OB vectors that never assert
    wallet values).
    """
    kernel = EventKernel(run_id=run_id)

    acct_map: dict[str, Account] = accounts if accounts is not None else {}
    if config is not None:
        market = config.market
        mult = int(market.tick_size * market.min_quantity / market.cash_unit)
        maker_bps = market.fees.maker_bps
        taker_bps = market.fees.taker_bps
        initial_price_ticks = market.initial_price_ticks
    if maker_bps is None:
        maker_bps = -1
    if taker_bps is None:
        taker_bps = 5

    if acct_map:
        account_payload = build_account_payload_from_accounts(
            acct_map, mult=mult
        )
    else:
        account_payload = build_account_payload([])
    book_payload = build_book_payload(last_ticks=None)
    kernel.bootstrap(account_payload, book_payload)

    book = Book(initial_price_ticks=initial_price_ticks)
    for i, lvl in enumerate(initial_book_levels or []):
        book.insert(
            RestingOrder(
                order_id=lvl.order_id,
                agent_id=lvl.agent_id,
                side=lvl.side,
                order_type="LIMIT",
                price_ticks=lvl.price_ticks,
                quantity_units=lvl.quantity_units,
                transaction_seq=i,
            )
        )

    world: dict[str, Any] = {
        "book": book,
        "accounts": acct_map,
        "exchange_fee_units": 0,
        "exchange_risk_pnl_units": 0,
        "mult": mult,
        "maker_bps": maker_bps,
        "taker_bps": taker_bps,
        "initial_price_ticks": initial_price_ticks,
    }
    if config is not None:
        world["config"] = config

    for event in events or []:
        kernel.enqueue(event)

    kernel.run(match_order, world, max_transactions=max_transactions)
    return kernel.committed_records, book
