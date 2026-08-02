"""T302-T306b + T404/T405: Matching engine -- the TransactionHandler for ORDER_ARRIVAL.

[撮合 §2.1] 成交价 = maker 挂单价
[撮合 §2.2] 跨档拆分: 逐档 TRADE_SETTLE, valuation_mark 逐笔推进
[撮合 §3]   剩余处理: LIMIT 挂入簿, MARKET IOC 撤销
[撮合 §4]   自成交阻止: cancel-resting
[撮合 §5]   准入与撮合固定顺序 (0.1.1 admission stub; reserved still computed)
[撮合 §6]   空簿/单边簿 valuation_mark 退化
[账户 §2.1] entry_notional update via ledger.apply_fill
[账户 §2.3] exchange_fee_units is a signed cumulative account
[事件 §4.2.1] postings length 2, [MAKER, TAKER], 15 fields each

Injected as the ``handler`` callback in ``EventKernel.run``.  The ``world``
dict carries ``book`` plus the ledger state (accounts, exchange fees, active
orders).  When the ledger state is absent (legacy Phase-3 callers) it is
lazily initialised with BENCH-001 defaults so existing tests keep working.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from market_game_sim.book.orderbook import Book, RestingOrder
from market_game_sim.hook.crypto_perp import CryptoPerpRegime
from market_game_sim.hook.interface import RegimeHook
from market_game_sim.kernel.runner import EventKernel
from market_game_sim.ledger.account import (
    Account,
    apply_fill,
    margin_ratio_bp,
    risk_equity,
)
from market_game_sim.ledger.fees import compute_notional_and_fees
from market_game_sim.ledger.reserved import ActiveOrder, compute_reserved_after, fee_bps_cap

_INITIAL_MARGIN_BP_011 = 10000
_DEFAULT_MULT = 1000
_DEFAULT_WALLET = 10**14  # 1,000,000 human -- large enough to never breach in OB tests


def match_order(event: dict, world: dict, kernel: EventKernel) -> list[dict]:
    if event["event_type"] == "SNAPSHOT":
        return []
    if event["event_type"] != "ORDER_ARRIVAL":
        return []

    book: Book = world["book"]
    _ensure_world(world)
    cfg = world["_cfg"]
    initial_price = cfg["initial_price_ticks"]
    book._initial_price_ticks = initial_price

    _populate_r0_defaults(event, book, initial_price, world)
    book.reset_dirty()

    # ── 撮合 §5 step 0: session state ──────────────────────────────
    regime: RegimeHook = world.setdefault("regime", CryptoPerpRegime())
    if regime.session_state(event["timestamp"], world.get("config")) != "OPEN":
        event["accepted"] = False
        event["reject_reason"] = "SESSION_CLOSED"
        return []

    if event["action"] == "CANCEL":
        return _handle_cancel(event, book, world, kernel)

    # ── 撮合 §5 step 3: initial margin check (stub in 0.1.1) ──────
    agent_id = event.get("agent_id")
    acct = world["accounts"].get(agent_id)
    if acct is not None:
        reserved_after = event.get("reserved_delta_units", 0)
        ok, reject = regime.margin_rule(
            acct,
            event.get("quantity_units", 0),
            event.get("price_ticks", 0),
            world.get("config"),
            reserved_after,
        )
        if not ok:
            event["accepted"] = False
            event["reject_reason"] = reject
            return []

    caused_by = f"e{kernel.current_transaction_seq}_0"
    records: list[dict] = []

    taker_side = event["side"]
    opposite_side = "SELL" if taker_side == "BUY" else "BUY"
    remaining = event["quantity_units"]
    limit_price = event.get("price_ticks")
    vm_running = book.valuation_mark_half_ticks()
    trade_idx = 0

    while remaining > 0:
        maker = book.peek_best_maker(opposite_side)
        if maker is None:
            break
        if not _crosses(taker_side, limit_price, maker.price_ticks):
            break

        if maker.agent_id == event["agent_id"]:
            cancelled = book.pop_best_maker(opposite_side)
            assert cancelled is not None
            _remove_active_order(world, cancelled.order_id, cancelled.agent_id)
            account = world["accounts"].get(cancelled.agent_id)
            risk_mark = book.last_ticks or initial_price
            old_r = account.reserved_units if account else 0
            new_r = _reserved_for(world, account, cancelled.agent_id, risk_mark) if account else 0
            if account:
                account.reserved_units = new_r
            reserved_delta = new_r - old_r
            records.append(
                _build_order_cancelled(
                    order=cancelled,
                    reason="SELF_TRADE_PREVENTION",
                    caused_by=caused_by,
                    reserved_delta=reserved_delta,
                )
            )
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

        postings = _settle_fill(
            maker=maker,
            taker_agent_id=event["agent_id"],
            taker_side=taker_side,
            fill_qty=fill_qty,
            maker_consumed=maker_consumed,
            world=world,
        )

        records.append(
            _build_trade_settle(
                maker=maker,
                taker_order_id=event["order_id"],
                taker_agent_id=event["agent_id"],
                fill_qty=fill_qty,
                vm_before=vm_before,
                vm_after=vm_after,
                risk_mark=maker.price_ticks,
                caused_by=caused_by,
                trade_idx=trade_idx,
                txn_seq=kernel.current_transaction_seq,
                postings=postings,
                world=world,
            )
        )
        trade_idx += 1

    if remaining > 0:
        if event["order_type"] == "LIMIT":
            assert limit_price is not None
            rest = RestingOrder(
                order_id=event["order_id"],
                agent_id=event["agent_id"],
                side=taker_side,
                order_type="LIMIT",
                price_ticks=limit_price,
                quantity_units=remaining,
                transaction_seq=kernel.current_transaction_seq,
            )
            book.insert(rest)
            _add_active_order(world, rest)
            acct = world["accounts"].get(rest.agent_id)
            if acct:
                acct.reserved_units = _reserved_for(
                    world,
                    acct,
                    rest.agent_id,
                    book.last_ticks or world.get("initial_price_ticks", 10000),
                )
        else:
            records.append(
                _build_ioc_cancel(
                    order_id=event["order_id"],
                    agent_id=event["agent_id"],
                    side=taker_side,
                    cancelled_qty=remaining,
                    caused_by=caused_by,
                )
            )

    # ── 撮合 §5 step 6: price bounds (stub in 0.1.1) ────────────
    # settlement_rule is INSTANT (inline — no delayed clearing needed).
    regime.price_bound(book.last_ticks or initial_price, world.get("config"))

    if book.dirty:
        records.append(_build_market_data_publish(book))

    return records


# --------------------------------------------------------------------------- #
# World initialisation (lazy, backward-compatible)
# --------------------------------------------------------------------------- #


def _ensure_world(world: dict) -> None:
    if "_cfg" in world:
        return
    config = world.get("config")
    if config is not None:
        market = config.market
        mult = int(market.tick_size * market.min_quantity / market.cash_unit)
        maker_bps = market.fees.maker_bps
        taker_bps = market.fees.taker_bps
        initial_price = market.initial_price_ticks
    else:
        mult = world.get("mult", _DEFAULT_MULT)
        maker_bps = world.get("maker_bps", -1)
        taker_bps = world.get("taker_bps", 5)
        initial_price = world.get("initial_price_ticks", 10000)
    world["_cfg"] = {
        "mult": mult,
        "maker_bps": maker_bps,
        "taker_bps": taker_bps,
        "initial_price_ticks": initial_price,
        "fee_bps_cap": fee_bps_cap(maker_bps, taker_bps),
    }
    world.setdefault("accounts", {})
    world.setdefault("exchange_fee_units", 0)
    world.setdefault("exchange_risk_pnl_units", 0)
    world.setdefault("active_orders_by_agent", {})
    world.setdefault("agent_initial_bp", {})
    world.setdefault("default_wallet_units", _DEFAULT_WALLET)
    if "initial_wallet_sum" not in world:
        captured = sum(a.wallet_units for a in world["accounts"].values())
        world["initial_wallet_sum"] = captured


def _get_account(world: dict, agent_id: str) -> Account:
    accts = world["accounts"]
    if agent_id not in accts:
        accts[agent_id] = Account(
            agent_id=agent_id,
            wallet_units=world.get("default_wallet_units", _DEFAULT_WALLET),
        )
    return accts[agent_id]


def _initial_bp(world: dict, agent_id: str) -> int:
    return world.get("agent_initial_bp", {}).get(agent_id, _INITIAL_MARGIN_BP_011)


def _active_orders(world: dict, agent_id: str) -> list[ActiveOrder]:
    return list(world.get("active_orders_by_agent", {}).get(agent_id, {}).values())


def _add_active_order(world: dict, order: RestingOrder) -> None:
    ao_by_agent = world.setdefault("active_orders_by_agent", {})
    ao_by_agent.setdefault(order.agent_id, {})[order.order_id] = ActiveOrder(
        order.side, order.price_ticks, order.quantity_units
    )


def _remove_active_order(world: dict, order_id: str, agent_id: str) -> None:
    ao_by_agent = world.get("active_orders_by_agent", {})
    if agent_id in ao_by_agent:
        ao_by_agent[agent_id].pop(order_id, None)


def _reduce_active_order(world: dict, order: RestingOrder, fill_qty: int, consumed: bool) -> None:
    ao_by_agent = world.get("active_orders_by_agent", {})
    agent_orders = ao_by_agent.get(order.agent_id, {})
    if consumed:
        agent_orders.pop(order.order_id, None)
    elif order.order_id in agent_orders:
        old = agent_orders[order.order_id]
        new_qty = old.quantity_units - fill_qty
        if new_qty <= 0:
            agent_orders.pop(order.order_id, None)
        else:
            agent_orders[order.order_id] = ActiveOrder(old.side, old.price_ticks, new_qty)


# --------------------------------------------------------------------------- #
# Fill settlement -- account updates + postings (T405)
# --------------------------------------------------------------------------- #


def _reserved_for(world: dict, account: Account, agent_id: str, risk_mark_ticks: int) -> int:
    cfg = world["_cfg"]
    return compute_reserved_after(
        position_units=account.position_units,
        active_orders=_active_orders(world, agent_id),
        risk_mark_ticks=risk_mark_ticks,
        initial_bp=_initial_bp(world, agent_id),
        fee_bps=cfg["fee_bps_cap"],
        mult=cfg["mult"],
    )


def _settle_fill(
    maker: RestingOrder,
    taker_agent_id: str,
    taker_side: str,
    fill_qty: int,
    maker_consumed: bool,
    world: dict,
) -> list[dict[str, Any]]:
    cfg = world["_cfg"]
    mult = cfg["mult"]
    maker_bps = cfg["maker_bps"]
    taker_bps = cfg["taker_bps"]
    price = maker.price_ticks
    risk_mark = price

    notional, maker_fee, taker_fee = compute_notional_and_fees(
        price, fill_qty, maker_bps, taker_bps, mult
    )
    world["exchange_fee_units"] += maker_fee + taker_fee

    maker_acct = _get_account(world, maker.agent_id)
    taker_acct = _get_account(world, taker_agent_id)

    maker_reserved_before = _reserved_for(world, maker_acct, maker.agent_id, risk_mark)
    taker_reserved_before = _reserved_for(world, taker_acct, taker_agent_id, risk_mark)

    maker_deltas = apply_fill(maker_acct, maker.side, price, fill_qty, mult, maker_bps)
    taker_deltas = apply_fill(taker_acct, taker_side, price, fill_qty, mult, taker_bps)

    _reduce_active_order(world, maker, fill_qty, maker_consumed)

    maker_reserved_after = _reserved_for(world, maker_acct, maker.agent_id, risk_mark)
    taker_reserved_after = _reserved_for(world, taker_acct, taker_agent_id, risk_mark)
    maker_acct.reserved_units = maker_reserved_after
    taker_acct.reserved_units = taker_reserved_after

    maker_posting = _build_trade_posting(
        agent_id=maker.agent_id,
        role="MAKER",
        deltas=maker_deltas,
        account=maker_acct,
        risk_mark=risk_mark,
        mult=mult,
        reserved_delta=maker_reserved_after - maker_reserved_before,
    )
    taker_posting = _build_trade_posting(
        agent_id=taker_agent_id,
        role="TAKER",
        deltas=taker_deltas,
        account=taker_acct,
        risk_mark=risk_mark,
        mult=mult,
        reserved_delta=taker_reserved_after - taker_reserved_before,
    )
    return [maker_posting, taker_posting]


def _build_trade_posting(
    agent_id: str,
    role: str,
    deltas: dict[str, int],
    account: Account,
    risk_mark: int,
    mult: int,
    reserved_delta: int,
) -> dict[str, Any]:
    return {
        "posting_type": "TRADE_POSTING",
        "agent_id": agent_id,
        "role": role,
        "wallet_delta_units": deltas["wallet_delta_units"],
        "position_delta_units": deltas["position_delta_units"],
        "entry_notional_delta_units": deltas["entry_notional_delta_units"],
        "realized_pnl_delta_units": deltas["realized_pnl_delta_units"],
        "fee_delta_units": deltas["fee_delta_units"],
        "reserved_delta_units": reserved_delta,
        "wallet_after_units": deltas["wallet_after_units"],
        "position_after_units": deltas["position_after_units"],
        "entry_notional_after_units": deltas["entry_notional_after_units"],
        "equity_after_units": risk_equity(account, risk_mark, mult),
        "margin_ratio_after_bp": margin_ratio_bp(account, risk_mark, mult),
        "risk_pnl_delta_units": 0,
    }


# --------------------------------------------------------------------------- #
# Crossing logic
# --------------------------------------------------------------------------- #


def _crosses(taker_side: str, limit_price: int | None, maker_price: int) -> bool:
    if limit_price is None:
        return True
    if taker_side == "BUY":
        return maker_price <= limit_price
    return maker_price >= limit_price


# --------------------------------------------------------------------------- #
# CANCEL action (agent-initiated; stub for 0.1.1)
# --------------------------------------------------------------------------- #


def _handle_cancel(event: dict, book: Book, world: dict, kernel: EventKernel) -> list[dict]:
    caused_by = f"e{kernel.current_transaction_seq}_0"
    target_id = event.get("target_order_id")
    if target_id is None:
        return []
    order = _find_and_remove(book, target_id)
    if order is None:
        return []
    _remove_active_order(world, order.order_id, order.agent_id)

    agent_id = order.agent_id
    account = world["accounts"].get(agent_id)
    risk_mark = book.last_ticks or world.get("initial_price_ticks", 10000)
    old_reserved = account.reserved_units if account else 0
    new_reserved = _reserved_for(world, account, agent_id, risk_mark) if account else 0
    if account:
        account.reserved_units = new_reserved
    reserved_delta = new_reserved - old_reserved

    return [
        _build_order_cancelled(
            order=order,
            reason="AGENT_REQUEST",
            caused_by=caused_by,
            reserved_delta=reserved_delta,
        )
    ]


def _find_and_remove(book: Book, order_id: str) -> RestingOrder | None:
    for side in ("BUY", "SELL"):
        book_dict, prices = book._side_refs(side)  # type: ignore[attr-defined]
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
                    book._dirty = True  # type: ignore[attr-defined]
                    return o
    return None


# --------------------------------------------------------------------------- #
# Record builders
# --------------------------------------------------------------------------- #


def _populate_r0_defaults(event: dict, book: Book, initial_price: int, world: dict) -> None:
    regime: RegimeHook = world.get("regime", CryptoPerpRegime())
    account = world["accounts"].get(event.get("agent_id"))
    accepted, reason = regime.validate_order(event, account, book, world.get("config"))
    # ── 撮合 §5 step 2: quantity / tick alignment (FR-003) ─────────
    if accepted:
        qty = event.get("quantity_units", 0)
        if qty is not None and qty <= 0:
            accepted = False
            reason = "INVALID_QUANTITY"
    event["accepted"] = accepted
    event["reject_reason"] = reason
    event.setdefault("origin", "AGENT")
    event.setdefault("trigger_ratio_bp", None)
    event.setdefault("liquidation_generation", None)
    event.setdefault("intent_id", "intent")
    event.setdefault("decision_event_id", "e0_0")
    event.setdefault("submitted_at", event["timestamp"])

    agent_id = event.get("agent_id", "")
    if not agent_id:
        event["reserved_delta_units"] = 0
        return
    account = _get_account(world, agent_id)

    # MARKET orders are IOC — they never rest, so reserved_delta is 0 (no
    # persistent margin reservation to track).  0.1.2 will replace this with
    # the admission-stage worst-case notional estimate when the margin gate
    # becomes active.
    if event.get("order_type") == "MARKET":
        event["reserved_delta_units"] = 0
        return

    risk_mark = book.last_ticks or initial_price
    old_reserved = _reserved_for(world, account, agent_id, risk_mark)

    new_order = ActiveOrder(
        side=event.get("side", "BUY"),
        price_ticks=event.get("price_ticks") or risk_mark,
        quantity_units=event.get("quantity_units", 0),
    )
    _add_active_order(
        world,
        RestingOrder(
            order_id=event.get("order_id", "_r0_tmp"),
            agent_id=agent_id,
            side=new_order.side,
            order_type="LIMIT",
            price_ticks=new_order.price_ticks,
            quantity_units=new_order.quantity_units,
            transaction_seq=0,
        ),
    )
    new_reserved = _reserved_for(world, account, agent_id, risk_mark)
    _remove_active_order(world, event.get("order_id", "_r0_tmp"), agent_id)

    event["reserved_delta_units"] = new_reserved - old_reserved


def _build_trade_settle(
    maker: RestingOrder,
    taker_order_id: str,
    taker_agent_id: str,
    fill_qty: int,
    vm_before: int,
    vm_after: int,
    risk_mark: int,
    caused_by: str,
    trade_idx: int,
    txn_seq: int,
    postings: list[dict[str, Any]],
    world: dict,
) -> dict[str, Any]:
    cfg = world["_cfg"]
    mult = cfg["mult"]
    notional = maker.price_ticks * fill_qty * mult
    maker_fee = postings[0]["fee_delta_units"]
    taker_fee = postings[1]["fee_delta_units"]
    return {
        "event_type": "TRADE_SETTLE",
        "maker_order_id": maker.order_id,
        "taker_order_id": taker_order_id,
        "maker_agent_id": maker.agent_id,
        "taker_agent_id": taker_agent_id,
        "price_ticks": maker.price_ticks,
        "quantity_units": fill_qty,
        "notional_cash_units": notional,
        "maker_fee_cash_units": maker_fee,
        "taker_fee_cash_units": taker_fee,
        "valuation_mark_before_half_ticks": vm_before,
        "valuation_mark_after_half_ticks": vm_after,
        "risk_mark_ticks": risk_mark,
        "postings": postings,
        "trade_id": f"t{txn_seq}_{trade_idx}",
        "caused_by_event_id": caused_by,
    }


def _build_order_cancelled(
    order: RestingOrder,
    reason: str,
    caused_by: str,
    reserved_delta: int = 0,
) -> dict[str, Any]:
    return {
        "event_type": "ORDER_CANCELLED",
        "order_id": order.order_id,
        "agent_id": order.agent_id,
        "cancelled_qty_units": order.quantity_units,
        "price_ticks": order.price_ticks if order.order_type == "LIMIT" else None,
        "side": order.side,
        "order_type": order.order_type,
        "reason": reason,
        "reserved_delta_units": reserved_delta,
        "caused_by_event_id": caused_by,
    }


def _build_ioc_cancel(
    order_id: str,
    agent_id: str,
    side: str,
    cancelled_qty: int,
    caused_by: str,
) -> dict[str, Any]:
    return {
        "event_type": "ORDER_CANCELLED",
        "order_id": order_id,
        "agent_id": agent_id,
        "cancelled_qty_units": cancelled_qty,
        "price_ticks": None,
        "side": side,
        "order_type": "MARKET",
        "reason": "IOC_REMAINDER",
        "reserved_delta_units": 0,
        "caused_by_event_id": caused_by,
    }


def _build_market_data_publish(book: Book) -> dict[str, Any]:
    return {
        "event_type": "MARKET_DATA_PUBLISH",
        "best_bid": book.best_bid(),
        "best_ask": book.best_ask(),
        "bid_depth_k": book.bid_depth_k(),
        "ask_depth_k": book.ask_depth_k(),
        "last": book.last_ticks,
    }
