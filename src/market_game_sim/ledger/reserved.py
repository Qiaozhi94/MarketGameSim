"""T407b: reserved_units -- worst-case total margin usage (账户合同 §3.3, 代理策略 §11.1).

``reserved = margin_part + fee_part`` where:

* ``margin_part = ceil(max(|worst_long|, |worst_short|) × risk_mark × MULT ×
  initial_bp / 10000)`` -- covers position AND all active orders, taking the
  worse of the two directions (orders on opposite sides do NOT cancel).
* ``fee_part = ceil(total_order_notional × fee_bps / 10000)`` -- only active
  orders contribute (the position's fees are already paid); ``fee_bps =
  max(maker_bps, taker_bps, 0)``.

All integers, all ceiled toward the exchange-safe side (§3.1.1).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from market_game_sim.config.types import div_ceil


@dataclass(frozen=True)
class ActiveOrder:
    side: str  # "BUY" | "SELL"
    price_ticks: int
    quantity_units: int


def compute_reserved_after(
    position_units: int,
    active_orders: Sequence[ActiveOrder],
    risk_mark_ticks: int,
    initial_bp: int,
    fee_bps: int,
    mult: int,
) -> int:
    """Total worst-case margin usage in cash_units (账户合同 §3.3 总占用口径)."""
    buy_qty = sum(o.quantity_units for o in active_orders if o.side == "BUY")
    sell_qty = sum(o.quantity_units for o in active_orders if o.side == "SELL")
    worst_long = position_units + buy_qty
    worst_short = position_units - sell_qty
    worst_abs = max(abs(worst_long), abs(worst_short))

    margin_part = div_ceil(worst_abs * risk_mark_ticks * mult * initial_bp, 10000)

    total_order_notional = sum(o.quantity_units * o.price_ticks * mult for o in active_orders)
    fee_part = div_ceil(total_order_notional * fee_bps, 10000) if fee_bps > 0 else 0

    return margin_part + fee_part


def fee_bps_cap(maker_bps: int, taker_bps: int) -> int:
    """``max(maker_bps, taker_bps, 0)`` -- the fee freeze rate (代理策略 §11.1)."""
    return max(maker_bps, taker_bps, 0)


@dataclass(frozen=True)
class PreMatchResult:
    """Result of pre-matching a candidate order against the book."""

    immediate_qty_units: int = 0
    immediate_notional: int = 0
    resting_qty_units: int = 0
    reservation_mark_ticks: int = 0


def compute_reserved_with_prematch(
    position_units: int,
    active_orders: Sequence[ActiveOrder],
    candidate: ActiveOrder | None,
    pre_match: PreMatchResult | None,
    risk_mark_ticks: int,
    initial_bp: int,
    fee_bps: int,
    mult: int,
) -> tuple[int, int, int]:
    """Total reserved + fee_immediate + fee_resting (代理策略 §11.1, T102/T103).

    Returns (reserved_after, fee_immediate, fee_resting).

    ``margin_part`` uses ``risk_mark_ticks`` only, exactly like
    :func:`compute_reserved_after` -- worst-case position sizing is pegged
    to the current market mark regardless of a candidate order's own limit
    price (账户合同 §2.1's "开仓不扣名义本金": admission does not require
    covering the full notional at the order's own price, only at the
    current mark; 案例 2 of acceptance-vectors.md depends on this).

    Only the *fee* estimate is split two ways: ``fee_immediate`` on the
    portion pre_match says fills right away, priced at the real per-level
    maker prices it walked (``pre_match.immediate_notional``) instead of
    the candidate's own limit price -- this is what T102/T103 fixes (the
    old single-phase estimate priced the whole order, immediate portion
    included, at the taker's own limit price, systematically wrong for the
    already-known immediate fills).  ``fee_resting`` covers active_orders
    at their own resting prices plus any leftover candidate quantity
    pre_match says will rest, at the candidate's own limit price (the
    worst/only price a resting LIMIT order can fill at).
    """
    all_orders = list(active_orders)
    if candidate is not None:
        all_orders.append(candidate)

    buy_qty = sum(o.quantity_units for o in all_orders if o.side == "BUY")
    sell_qty = sum(o.quantity_units for o in all_orders if o.side == "SELL")
    worst_abs = max(abs(position_units + buy_qty), abs(position_units - sell_qty))

    margin_part = div_ceil(worst_abs * risk_mark_ticks * mult * initial_bp, 10000)

    if fee_bps <= 0:
        return margin_part, 0, 0

    if pre_match is not None:
        fee_immediate = div_ceil(pre_match.immediate_notional * fee_bps, 10000)
        resting_total = sum(o.quantity_units * o.price_ticks * mult for o in active_orders)
        if candidate is not None and pre_match.resting_qty_units > 0:
            resting_total += pre_match.resting_qty_units * candidate.price_ticks * mult
        fee_resting = div_ceil(resting_total * fee_bps, 10000)
    else:
        total_notional = sum(o.quantity_units * o.price_ticks * mult for o in all_orders)
        fee_immediate = 0
        fee_resting = div_ceil(total_notional * fee_bps, 10000)

    return margin_part + fee_immediate + fee_resting, fee_immediate, fee_resting
