"""T102 (FR-019): Incremental state reconstruction from events.

Rebuilds account + orderbook state purely from EVENT records, mirroring the
kernel's state machine so a later frame-consistency check (E1) can compare
it against an independent oracle.  Does NOT import kernel/book/ledger.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReserveConfig:
    """Config needed to reconstruct the derived ``reserved_units`` field.

    These values live in the run config, not the log (like ``mult``), so the
    test-facing frame builder threads them in.
    """

    mult: int = 1000
    fee_bps_cap: int = 0
    initial_price_ticks: int = 10000
    agent_initial_bp: dict[str, int] = field(default_factory=dict)


@dataclass
class ReplayAccount:
    """Mutable per-account tracking state (margin_ratio_bp derived)."""

    wallet_units: int
    position_units: int
    entry_notional_units: int
    reserved_units: int
    realized_pnl_units: int
    state: str
    liquidation_generation: int
    chain_id: str | None = None
    chain_depth: int | None = None


@dataclass
class ReplayBookOrder:
    """A resting order being tracked for quantity + order_count aggregation."""

    agent_id: str
    side: str
    price_ticks: int | None
    remaining_qty: int


@dataclass
class RebuiltState:
    """The full reconstructible state at a point in the log."""

    accounts: dict[str, ReplayAccount] = field(default_factory=dict)
    book_orders: dict[str, ReplayBookOrder] = field(default_factory=dict)
    fee_cash_units: int = 0
    risk_pnl_units: int = 0
    last_ticks: int | None = None
    reserve: ReserveConfig = field(default_factory=ReserveConfig)


def new_state() -> RebuiltState:
    return RebuiltState()


def _div_ceil(a: int, b: int) -> int:
    return -(-a // b)


def _reserved_after(
    position_units: int,
    active_orders: list[ReplayBookOrder],
    risk_mark_ticks: int,
    initial_bp: int,
    fee_bps: int,
    mult: int,
) -> int:
    """Worst-case margin usage (ledger.reserved.compute_reserved_after)."""
    buy_qty = sum(o.remaining_qty for o in active_orders if o.side == "BUY")
    sell_qty = sum(o.remaining_qty for o in active_orders if o.side == "SELL")
    worst_abs = max(abs(position_units + buy_qty), abs(position_units - sell_qty))
    margin_part = _div_ceil(worst_abs * risk_mark_ticks * mult * initial_bp, 10000)
    total_notional = sum(o.remaining_qty * o.price_ticks * mult for o in active_orders)
    fee_part = _div_ceil(total_notional * fee_bps, 10000) if fee_bps > 0 else 0
    return margin_part + fee_part


def _active_orders(state: RebuiltState, agent_id: str) -> list[ReplayBookOrder]:
    return [
        o
        for o in state.book_orders.values()
        if o.agent_id == agent_id and o.remaining_qty > 0 and o.price_ticks is not None
    ]


def _recompute_reserved(state: RebuiltState, agent_id: str) -> None:
    acc = state.accounts.get(agent_id)
    if acc is None:
        return
    risk_mark = state.last_ticks or state.reserve.initial_price_ticks
    acc.reserved_units = _reserved_after(
        position_units=acc.position_units,
        active_orders=_active_orders(state, agent_id),
        risk_mark_ticks=risk_mark,
        initial_bp=state.reserve.agent_initial_bp.get(agent_id, 10000),
        fee_bps=state.reserve.fee_bps_cap,
        mult=state.reserve.mult,
    )


def _init_from_snapshot(state: RebuiltState, payload: dict[str, Any]) -> None:
    for entry in payload.get("accounts", []):
        aid = entry.get("agent_id", "")
        state.accounts[aid] = ReplayAccount(
            wallet_units=entry.get("wallet_units", 0),
            position_units=entry.get("position_units", 0),
            entry_notional_units=entry.get("entry_notional_units", 0),
            reserved_units=entry.get("reserved_units", 0),
            realized_pnl_units=entry.get("realized_pnl_units", 0),
            state=entry.get("state", "ACTIVE"),
            liquidation_generation=entry.get("liquidation_generation", 0),
            chain_id=entry.get("chain_id"),
            chain_depth=entry.get("chain_depth"),
        )
    exchange = payload.get("exchange", {})
    state.fee_cash_units = exchange.get("fee_cash_units", 0)
    state.risk_pnl_units = exchange.get("risk_pnl_units", 0)


def _init_book(state: RebuiltState, payload: dict[str, Any]) -> None:
    state.last_ticks = payload.get("last_ticks")


def apply_event(state: RebuiltState, event: dict[str, Any]) -> None:
    """Apply a single EVENT record's state effect to ``state`` (in place)."""
    et = event.get("event_type", "")

    if et == "SNAPSHOT":
        payload = event.get("payload", {})
        if event.get("snapshot_type") == "ACCOUNT":
            _init_from_snapshot(state, payload)
        elif event.get("snapshot_type") == "BOOK":
            _init_book(state, payload)
        return

    if et == "TRADE_SETTLE":
        state.last_ticks = event.get("price_ticks", state.last_ticks)
        state.fee_cash_units += event.get("maker_fee_cash_units", 0)
        state.fee_cash_units += event.get("taker_fee_cash_units", 0)
        fill_qty = event.get("quantity_units", 0)
        for oid in (event.get("maker_order_id", ""), event.get("taker_order_id", "")):
            if oid in state.book_orders:
                state.book_orders[oid].remaining_qty -= fill_qty
        for p in event.get("postings", []):
            if p.get("posting_type") != "TRADE_POSTING":
                continue
            aid = p.get("agent_id", "")
            acc = state.accounts.get(aid)
            if acc is None:
                continue
            acc.wallet_units = p.get("wallet_after_units", acc.wallet_units)
            acc.position_units = p.get("position_after_units", acc.position_units)
            acc.entry_notional_units = p.get("entry_notional_after_units", acc.entry_notional_units)
            acc.realized_pnl_units += p.get("realized_pnl_delta_units", 0)
        for aid in (event.get("maker_agent_id"), event.get("taker_agent_id")):
            _recompute_reserved(state, aid)
        return

    if et == "MARGIN_CALL":
        verdict = event.get("verdict", "")
        if verdict == "PENDING_LIQUIDATION":
            new_state_s = "PENDING_LIQUIDATION"
        elif verdict == "OK":
            new_state_s = "ACTIVE"
        else:  # BREACHED
            new_state_s = "LIQUIDATED"
        aid = event.get("agent_id", "")
        acc = state.accounts.get(aid)
        if acc is not None:
            acc.state = new_state_s
            acc.chain_id = event.get("chain_id")
            acc.chain_depth = event.get("chain_depth")
            acc.liquidation_generation = event.get("liquidation_generation_after", 0)
        for p in event.get("postings", []):
            if p.get("posting_type") != "WRITE_OFF_POSTING":
                continue
            role = p.get("role", "")
            if role == "ACCOUNT":
                a = state.accounts.get(p.get("agent_id", ""))
                if a is not None:
                    a.wallet_units += p.get("wallet_delta_units", 0)
            elif role == "EXCHANGE_RISK":
                state.risk_pnl_units += p.get("risk_pnl_delta_units", 0)
        return

    if et == "ORDER_ARRIVAL":
        if (
            event.get("action") == "SUBMIT"
            and event.get("accepted", True)
            and event.get("order_type") == "LIMIT"
            and event.get("price_ticks") is not None
        ):
            oid = event.get("order_id", "")
            state.book_orders[oid] = ReplayBookOrder(
                agent_id=event.get("agent_id", ""),
                side=event.get("side", ""),
                price_ticks=event.get("price_ticks"),
                remaining_qty=event.get("quantity_units", 0),
            )
            _recompute_reserved(state, event.get("agent_id", ""))
        return

    if et == "ORDER_CANCELLED":
        oid = event.get("order_id", "")
        agent_id = event.get("agent_id", "")
        if oid in state.book_orders:
            state.book_orders[oid].remaining_qty = 0
        _recompute_reserved(state, agent_id)
        return
