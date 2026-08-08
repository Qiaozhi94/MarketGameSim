"""T701/E5-E6 calibration: pre-positioned leveraged accounts.

Building a leveraged position *through* the normal AGENT_DECIDE loop and
then shocking it fights itself: forcing high conviction + a large
``max_order_qty`` so the position builds fast makes that same buying
pressure move price before the shock lands, and price moving in the
position's favor raises equity, which raises the target position, which
causes more buying -- a real feedback loop (see docs/experiments/
0.1.2-exit-evidence-index.json's E5 entry for the empirical trace: forced
positions ran away to 145,950 lots against a 100,000-lot wallet).

This sidesteps the buildup phase entirely: accounts are bootstrapped
directly into an already-open leveraged position (matching
acceptance-vectors.md 案例7/8's ``A``/``S`` construction, already verified
bit-for-bit against the real engine), with no ``AgentSpec`` and no decision
loop -- pure static risk sitting in the book, waiting for the market's own
price action (or bench/shock.py's sustained pressure) to move margin_ratio_bp
below ``maint_bp``. Belief-agent/market-maker research logic is untouched.
"""

from __future__ import annotations

CASH_PER_HUMAN_UNIT = 10**8  # 1 / cash_unit (BENCH-001: cash_unit = 1e-8)
TICKS_PER_HUMAN_PRICE = 100  # 1 / tick_size (BENCH-001: tick_size = 0.01)
UNITS_PER_HUMAN_QTY = 1_000  # 1 / min_quantity (BENCH-001: min_quantity = 0.001)


def build_leveraged_victims(
    count: int = 20,
    wallet_human: int = 5_000,
    position_human: int = 500,
    entry_price_human: int = 100,
    mult: int = 1_000,
    side: str = "LONG",
    stagger_position_step: int = 0,
) -> dict[str, dict[str, int]]:
    """Returns an ``extra_positions``-shaped dict: ``count`` victim accounts
    each long (or short) ``position_human`` at ``entry_price_human``, plus
    one large counterparty account absorbing the offsetting position (C1:
    Σposition_units ≡ 0).

    Defaults replicate acceptance-vectors.md 案例7's exact ratio (wallet
    5000, position 500, entry 100 -- notional 10x wallet, i.e. already at
    the 10x tier's admission ceiling): that scenario is verified (Case 7
    test) to breach 500bp maintenance when price moves ~6% against it.

    ``stagger_position_step`` > 0 gives each successive victim a slightly
    larger position (same wallet), so their breach thresholds spread out
    instead of all firing from the same external price move at once --
    needed to observe a genuine *chain* (one victim's own liquidation
    trade pushing price far enough to newly breach the next victim), as
    opposed to many liquidations that are each independently triggered by
    the same external shock (chain_depth stays 0 for those: 事件 Schema
    §4.2.2 only increments depth when the triggering event is itself a
    LIQUIDATION-origin trade).
    """
    entry_price_ticks = entry_price_human * TICKS_PER_HUMAN_PRICE
    wallet_units = wallet_human * CASH_PER_HUMAN_UNIT
    sign = 1 if side == "LONG" else -1

    positions: dict[str, dict[str, int]] = {}
    total_position_units = 0
    for i in range(count):
        qty_human = position_human + i * stagger_position_step
        position_units = qty_human * UNITS_PER_HUMAN_QTY
        entry_notional_units = position_units * entry_price_ticks * mult
        positions[f"bench-victim-{i}"] = {
            "wallet_units": wallet_units,
            "position_units": sign * position_units,
            "entry_notional_units": sign * entry_notional_units,
        }
        total_position_units += position_units
    counterparty_notional = total_position_units * entry_price_ticks * mult
    positions["bench-victim-counterparty"] = {
        "wallet_units": wallet_units * count * 10,  # large enough to never itself breach
        "position_units": -sign * total_position_units,
        "entry_notional_units": -sign * counterparty_notional,
    }
    return positions
