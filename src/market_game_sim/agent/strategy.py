"""T403: Signal -> target position -> order intent (代理策略 §5-§7)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from market_game_sim.ledger.account import initial_margin_bp_for_tier

# A target-position function has the BehaviorMapping contract (agent/mapping.py)
# but strategy.py deliberately does NOT import mapping.py -- mapping.py imports
# strategy.target_position as the linear baseline, so importing the other way
# would create a cycle.  The shared execution pipeline (T103) calls the injected
# callable instead of the module-level target_position, keeping the mapping
# contrast a single-variable difference at the pipeline's *input*.
TargetFn = Callable[[int, int, int, int, int], int]


@dataclass
class OrderIntent:
    intent_id: str
    action: str
    side: str
    order_type: str
    price_ticks: int | None
    quantity_units: int
    leverage_tier: int
    aggressiveness_bp: int


def target_position(
    signal_bp: int,
    equity_units: int,
    valuation_mark_ticks: int,
    initial_bp: int,
    min_qty: int,
) -> int:
    """Convert signal to integer target position in qty units (代理策略 §5).

    ``max_position = floor(equity × 10000 / (initial_bp × valuation_mark))``.
    ``target = trunc(signal_bp × max_position / 10000)`` (toward zero).
    """
    if valuation_mark_ticks <= 0 or initial_bp <= 0 or min_qty <= 0:
        return 0
    max_pos = (equity_units * 10_000) // (initial_bp * valuation_mark_ticks)
    raw = signal_bp * max_pos
    raw = raw // 10_000 if raw >= 0 else -((-raw) // 10_000)
    return _trunc_toward_zero(raw, min_qty)


def _trunc_toward_zero(x: int, step: int) -> int:
    """Truncate toward zero to step multiple.  Round half away from zero."""
    if x == 0:
        return 0
    sign = 1 if x > 0 else -1
    abs_x = abs(x)
    truncated = (abs_x // step) * step
    return sign * truncated


def order_intent_from_signal(
    intent_id: str,
    signal_bp: int,
    current_position: int,
    equity_units: int,
    valuation_mark_ticks: int,
    leverage_tier: int,
    aggressiveness_bp: int,
    best_bid: int | None,
    best_ask: int | None,
    max_order_qty: int,
    min_qty: int,
    target_fn: TargetFn = target_position,
) -> OrderIntent | None:
    """Compute one order intent from signal + state (代理策略 §6).

    ``target_fn`` (T103 shared pipeline): injects the behavior mapping's
    target-position function so the mapping contrast is a single-variable
    difference at the pipeline's *input*; the rest of the pipeline (delta,
    side, price, admission) is shared and identical across mappings.  Defaults
    to the module-level linear ``target_position`` (0.1.2 baseline).

    Returns ``None`` if no actionable order.
    """
    if best_bid is None or best_ask is None:
        return None
    initial_bp = initial_margin_bp_for_tier(leverage_tier)
    target = target_fn(signal_bp, equity_units, valuation_mark_ticks, initial_bp, min_qty)
    delta = target - current_position
    if abs(delta) < min_qty:
        return None
    if delta > 0:
        side = "BUY"
    else:
        side = "SELL"
        delta = -delta
    delta = min(delta, max_order_qty)
    if delta < min_qty:
        return None
    if side == "BUY":
        spread = best_ask - best_bid
        price = best_bid + (aggressiveness_bp * spread) // 10_000
    else:
        spread = best_ask - best_bid
        price = best_ask - (aggressiveness_bp * spread) // 10_000
    return OrderIntent(
        intent_id=intent_id,
        action="SUBMIT",
        side=side,
        order_type="LIMIT",
        price_ticks=price,
        quantity_units=delta,
        leverage_tier=leverage_tier,
        aggressiveness_bp=aggressiveness_bp,
    )


def market_maker_intents(
    agent_id: str,
    inventory: int,
    max_inventory: int,
    half_spread_ticks: int,
    quote_size: int,
    inventory_skew_k_bp: int,
    valuation_mark_ticks: int | None,
    best_bid: int | None,
    best_ask: int | None,
    margin_ratio_bp: int | None = None,
    maint_bp: int = 500,
) -> list[OrderIntent]:
    """Inventory market maker: bilateral quotes with skew (代理策略 §8).

    When margin_ratio_bp < maint_bp, only quotes the position-reducing
    direction (代理策略 §8 last bullet).
    """
    if valuation_mark_ticks is None or max_inventory <= 0:
        return []
    inv_ratio = Decimal(inventory) / Decimal(max_inventory)
    inv_ratio = max(Decimal(-1), min(Decimal(1), inv_ratio))
    skew_ticks = int(inv_ratio * inventory_skew_k_bp * half_spread_ticks / Decimal(10_000))
    bid = valuation_mark_ticks - half_spread_ticks - skew_ticks
    ask = valuation_mark_ticks + half_spread_ticks - skew_ticks

    margin_warning = margin_ratio_bp is not None and margin_ratio_bp < maint_bp
    intents: list[OrderIntent] = []
    if inventory < max_inventory and (not margin_warning or inventory < 0):
        intents.append(
            OrderIntent(
                intent_id=f"{agent_id}-mm-bid",
                action="SUBMIT",
                side="BUY",
                order_type="LIMIT",
                price_ticks=bid,
                quantity_units=quote_size,
                leverage_tier=1,
                aggressiveness_bp=0,
            )
        )
    if inventory > -max_inventory and (not margin_warning or inventory > 0):
        intents.append(
            OrderIntent(
                intent_id=f"{agent_id}-mm-ask",
                action="SUBMIT",
                side="SELL",
                order_type="LIMIT",
                price_ticks=ask,
                quantity_units=quote_size,
                leverage_tier=1,
                aggressiveness_bp=0,
            )
        )
    return intents
