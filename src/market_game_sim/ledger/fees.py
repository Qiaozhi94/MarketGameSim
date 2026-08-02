"""T404: Fee computation -- sole rounding site (ADR-001 §3).

[ADR-001 §3] fees round **up** (ceil), always unfavourably to the agent.
A negative maker bps (rebate) is also ceiled -- the agent receives less.

``notional_cash_units = price_ticks × quantity_units × MULT`` where
``MULT = tick_size × min_quantity / cash_unit`` (1000 for BENCH-001).
"""

from __future__ import annotations

from market_game_sim.config.types import round_fee


def compute_mult(tick_size, min_quantity, cash_unit) -> int:
    """``int(tick_size × min_quantity / cash_unit)`` -- the notional multiplier.

    The three inputs are ``Decimal`` (from config); the quotient is integral
    for all valid configs (BENCH-001 -> 1000).
    """
    quotient = tick_size * min_quantity / cash_unit
    if quotient != quotient.to_integral_value():
        raise ValueError(f"MULT = tick_size*min_quantity/cash_unit = {quotient} is not integral")
    return int(quotient)


def compute_notional_and_fees(
    price_ticks: int,
    quantity_units: int,
    maker_bps: int,
    taker_bps: int,
    mult: int,
) -> tuple[int, int, int]:
    """Return ``(notional_cash_units, maker_fee_cash_units, taker_fee_cash_units)``.

    ``notional`` is exact (no rounding, ADR-001 §2).  Each fee is
    :func:`round_fee(notional, bps)` -- ceil toward unfavourable-to-agent.
    """
    notional = price_ticks * quantity_units * mult
    maker_fee = round_fee(notional, maker_bps)
    taker_fee = round_fee(notional, taker_bps)
    return notional, maker_fee, taker_fee
