"""T101, T103: Margin calculation primitives (账户合同 §3)."""

from __future__ import annotations

from market_game_sim.config.types import div_ceil
from market_game_sim.ledger.account import (
    Account,
)
from market_game_sim.ledger.account import (
    margin_ratio_bp as _account_margin_ratio_bp,
)
from market_game_sim.ledger.account import (
    risk_equity as _account_risk_equity,
)


def notional_units(position_units: int, risk_mark_ticks: int, mult: int) -> int:
    """``|position| × risk_mark × MULT`` in cash_units (账户合同 §3.2)."""
    if position_units == 0 or risk_mark_ticks <= 0 or mult <= 0:
        return 0
    return abs(position_units) * risk_mark_ticks * mult


def margin_used(notional: int, maint_bp: int) -> int:
    """``ceil(notional × maint_bp / 10000)`` (账户合同 §3.2, §3.1.1)."""
    if notional <= 0:
        return 0
    return div_ceil(notional * maint_bp, 10_000)


def initial_margin_required(notional: int, initial_bp: int) -> int:
    """``ceil(notional × initial_bp / 10000)`` (账户合同 §3.3)."""
    if notional <= 0:
        return 0
    return div_ceil(notional * initial_bp, 10_000)


def risk_equity(account: Account, risk_mark_ticks: int, mult: int) -> int:
    return _account_risk_equity(account, risk_mark_ticks, mult)


def margin_ratio_bp(account: Account, risk_mark_ticks: int, mult: int) -> int | None:
    """Returns ``None`` when ``position == 0`` (账户合同 §3.2), else floored bp."""
    return _account_margin_ratio_bp(account, risk_mark_ticks, mult)
