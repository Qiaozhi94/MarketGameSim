"""T401-T403: Account entity, entry_notional update, and dual-notch equity.

[账户 §1]   Account fields (all minimum-unit integers, ADR-001 §1).
[账户 §2.1] entry_notional update: same-direction / reverse / flip.
[账户 §2.2] unrealized_pnl + risk_equity / valuation_equity (dual notch).

Stdlib only (KR-005). Integer-only arithmetic. No floats.

Units reminder (BENCH-001):
    MULT = tick_size * min_quantity / cash_unit = 1000
    notional_cash_units = price_ticks * qty_units * MULT
    entry_notional_units is in cash_units (includes MULT).
    risk_mark is in ticks (integer); valuation_mark is in half-ticks
    (best_bid + best_ask, an integer even when mid is x.5 ticks).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from market_game_sim.config.types import div_ceil, div_round_toward_zero, round_fee


class AccountState(StrEnum):
    """Account state machine (账户合同 §1, plan §3.4).

    For 0.1.1 all accounts start and remain ``ACTIVE`` -- ``PENDING_LIQUIDATION``
    and ``LIQUIDATED`` are 0.1.2 concerns, but the enum is in place so 0.1.2
    does not stack on a missing definition.
    """

    ACTIVE = "ACTIVE"
    PENDING_LIQUIDATION = "PENDING_LIQUIDATION"
    LIQUIDATED = "LIQUIDATED"


@dataclass
class Account:
    """Linear perpetual account (账户合同 §1).

    All fields are minimum-unit integers. ``entry_notional_units`` carries the
    same sign as ``position_units`` (long -> positive, short -> negative) and
    is denominated in cash_units (i.e. it includes ``MULT``).
    """

    agent_id: str
    wallet_units: int
    position_units: int = 0
    entry_notional_units: int = 0
    reserved_units: int = 0
    realized_pnl_units: int = 0
    state: AccountState = AccountState.ACTIVE
    liquidation_generation: int = 0
    chain_id: str | None = None
    chain_depth: int | None = None


# --------------------------------------------------------------------------- #
# T402: entry_notional update -- same-direction / reverse / flip
# --------------------------------------------------------------------------- #


def apply_fill(
    account: Account,
    side: str,
    price_ticks: int,
    qty_units: int,
    mult: int,
    fee_bps: int,
) -> dict[str, int]:
    """Apply one fill to ``account`` (mutating) and return the delta dict.

    Implements 账户合同 §2.1:

    * same-direction (or opening from 0): ``entry += Δpos × price × MULT``.
    * reverse (partial or full close): ``avg_entry = entry / pos`` (toward
      zero, remainder stays in ``entry``), ``realized += closed × (price −
      avg_entry) × sign(pos)``, ``entry -= closed × avg_entry × sign(pos)``.
    * flip (reverse exceeds |pos|): the leftover is treated as a same-direction
      open at ``price``.

    ``side`` is THIS agent's side in the fill (``"BUY"`` -> Δpos positive).
    ``fee_bps`` is this agent's fee bps (maker or taker); the fee is rounded
    unfavourably to the agent via :func:`round_fee` (ADR-001 §3).

    Returns a dict with the six delta fields + the six ``*_after`` fields
    needed by ``TRADE_POSTING`` (event Schema §4.2.1).  ``risk_pnl_delta_units``
    is always 0 for a trade (核销 only happens in ``MARGIN_CALL``).
    """
    if side not in ("BUY", "SELL"):
        raise ValueError(f"side must be BUY or SELL, got {side!r}")
    if qty_units <= 0:
        raise ValueError(f"qty_units must be positive, got {qty_units}")
    if mult <= 0:
        raise ValueError(f"mult must be positive, got {mult}")

    delta_pos = qty_units if side == "BUY" else -qty_units
    pos = account.position_units
    entry = account.entry_notional_units

    if pos == 0 or (pos > 0) == (delta_pos > 0):
        # Same-direction add (or open from zero).
        entry_delta = delta_pos * price_ticks * mult
        realized_delta = 0
    else:
        # Reverse: close part or all of the position.
        closed = min(abs(delta_pos), abs(pos))
        # avg_entry = entry / pos, toward zero. entry and pos share sign so
        # div_round_toward_zero yields a positive per-unit cost; the rounding
        # remainder stays in entry_notional (账户合同 §2.1 last paragraph).
        avg_entry = div_round_toward_zero(entry, pos)
        sign_pos = 1 if pos > 0 else -1
        # realized = closed * (price - avg_entry) * sign(pos), all in cash_units
        # (price_ticks * MULT and avg_entry are both cash-per-qty-unit).
        realized_delta = closed * (price_ticks * mult - avg_entry) * sign_pos
        entry_delta = -closed * avg_entry * sign_pos
        # If the reverse flips direction, the leftover opens a new position.
        leftover = abs(delta_pos) - closed
        if leftover > 0:
            entry_delta += leftover * (1 if delta_pos > 0 else -1) * price_ticks * mult

    notional_cash = price_ticks * qty_units * mult
    fee_delta = round_fee(notional_cash, fee_bps)
    wallet_delta = realized_delta - fee_delta

    # Mutate account.
    account.position_units = pos + delta_pos
    account.entry_notional_units = entry + entry_delta
    account.wallet_units = account.wallet_units + wallet_delta
    account.realized_pnl_units = account.realized_pnl_units + realized_delta

    return {
        "wallet_delta_units": wallet_delta,
        "position_delta_units": delta_pos,
        "entry_notional_delta_units": entry_delta,
        "realized_pnl_delta_units": realized_delta,
        "fee_delta_units": fee_delta,
        "wallet_after_units": account.wallet_units,
        "position_after_units": account.position_units,
        "entry_notional_after_units": account.entry_notional_units,
        "risk_pnl_delta_units": 0,
    }


# --------------------------------------------------------------------------- #
# T403: unrealized PnL + dual-notch equity
# --------------------------------------------------------------------------- #


def _mult_half(mult: int) -> int:
    """``MULT // 2`` -- valid because BENCH-001 MULT=1000 is even.

    ``position × mid × MULT = position × (vm_half/2) × MULT = position ×
    vm_half × (MULT//2)`` exactly when MULT is even.
    """
    if mult % 2 != 0:
        raise ValueError(f"mult must be even for half-tick equity, got {mult}")
    return mult // 2


def unrealized_pnl_at_risk_mark(account: Account, risk_mark_ticks: int, mult: int) -> int:
    """``position × risk_mark − entry_notional`` in cash_units (账户合同 §2.2).

    ``risk_mark`` is in ticks (the last trade price). Both ``position ×
    risk_mark × MULT`` and ``entry_notional_units`` are in cash_units.
    """
    return account.position_units * risk_mark_ticks * mult - account.entry_notional_units


def unrealized_pnl_at_valuation_mark(
    account: Account, valuation_mark_half_ticks: int, mult: int
) -> int:
    """``position × valuation_mark − entry_notional`` in cash_units.

    ``valuation_mark`` is in half-ticks (``best_bid + best_ask``); dividing by
    2 is folded into ``MULT // 2`` so the result stays integer.
    """
    return (
        account.position_units * valuation_mark_half_ticks * _mult_half(mult)
        - account.entry_notional_units
    )


def risk_equity(account: Account, risk_mark_ticks: int, mult: int) -> int:
    """``wallet + unrealized_pnl(risk_mark)`` -- for margin/admission/liquidation."""
    return account.wallet_units + unrealized_pnl_at_risk_mark(account, risk_mark_ticks, mult)


def valuation_equity(account: Account, valuation_mark_half_ticks: int, mult: int) -> int:
    """``wallet + unrealized_pnl(valuation_mark)`` -- for reporting/PnL bridge.

    Must NOT be substituted for :func:`risk_equity` (账户合同 §2.2).
    """
    return account.wallet_units + unrealized_pnl_at_valuation_mark(
        account, valuation_mark_half_ticks, mult
    )


# --------------------------------------------------------------------------- #
# Margin ratio (账户合同 §3.2) -- used by TRADE_POSTING.margin_ratio_after_bp
# --------------------------------------------------------------------------- #


def margin_ratio_bp(account: Account, risk_mark_ticks: int, mult: int) -> int | None:
    """Current margin ratio in integer bp (账户合同 §3.2).

    ``margin_ratio_bp = floor(risk_equity × 10000 / notional)`` where
    ``notional = |position| × risk_mark × MULT``.  Returns ``None`` when
    ``position == 0`` (no position -> ratio undefined, 账户合同 §3.2 boundary).
    Floor per §3.1.1 (向下取整 so临界 accounts do not look safe).
    """
    if account.position_units == 0:
        return None
    notional = abs(account.position_units) * risk_mark_ticks * mult
    if notional == 0:
        return None
    re = risk_equity(account, risk_mark_ticks, mult)
    # Python // is floor division -> 向下取整 (toward -inf), matching §3.1.1.
    return re * 10000 // notional


def initial_margin_bp_for_tier(leverage_tier: int) -> int:
    """``ceil(10000 / leverage_tier)`` (账户合同 §3.1, §3.1.1 向上)."""
    if leverage_tier <= 0:
        raise ValueError(f"leverage_tier must be positive, got {leverage_tier}")
    return div_ceil(10000, leverage_tier)


def snapshot_entry(account: Account, risk_mark_ticks: int | None, mult: int) -> dict[str, Any]:
    """Build an ``ACCOUNT_SNAPSHOT_ENTRY`` dict from an account (event Schema §4.6.1)."""
    return {
        "agent_id": account.agent_id,
        "wallet_units": account.wallet_units,
        "position_units": account.position_units,
        "entry_notional_units": account.entry_notional_units,
        "reserved_units": account.reserved_units,
        "realized_pnl_units": account.realized_pnl_units,
        "state": account.state.value,
        "margin_ratio_bp": (
            margin_ratio_bp(account, risk_mark_ticks, mult) if risk_mark_ticks is not None else None
        ),
        "liquidation_generation": account.liquidation_generation,
        "chain_id": account.chain_id,
        "chain_depth": account.chain_depth,
    }
