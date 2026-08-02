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
