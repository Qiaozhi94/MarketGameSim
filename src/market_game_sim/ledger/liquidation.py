"""T203, T205: Liquidation quantity calculation (账户合同 §4.2, §4.3).

* :func:`required_liquidation_qty` -- binary-search minimum q that brings
  margin ratio back to ``target_bp`` after close.  Includes taker fee in
  post-close risk equity.  Both ``q`` and ``q-1 step`` are verified.

* :func:`recompute_required_qty` -- called inside a liquidation order's
  own transaction when the previous quantity was only partially filled
  and risk_mark has moved.  Returns a new integer q.

All integer math, no floats.
"""

from __future__ import annotations

from market_game_sim.config.types import div_ceil
from market_game_sim.ledger.account import Account


def _post_close_risk_equity(
    account: Account,
    close_qty_units: int,
    risk_mark_ticks: int,
    taker_bps: int,
    mult: int,
) -> int:
    """Equity after closing ``close_qty_units`` of the position at risk_mark.

    Returns actual risk_equity = wallet_after + unrealized_after.
    For close_qty==0, this is just the account's current risk_equity.
    """
    pos = account.position_units
    if close_qty_units == 0:
        return account.wallet_units + pos * risk_mark_ticks * mult - account.entry_notional_units
    if pos == 0 or close_qty_units <= 0:
        return account.wallet_units
    sign = 1 if pos > 0 else -1
    closed = min(close_qty_units, abs(pos))
    avg_entry = abs(account.entry_notional_units) // abs(pos) if pos != 0 else 0
    realized_delta = closed * (risk_mark_ticks * mult - avg_entry) * sign
    notional_closed = closed * risk_mark_ticks * mult
    fee_delta = div_ceil(notional_closed * taker_bps, 10_000) if taker_bps > 0 else 0
    wallet_after = account.wallet_units + realized_delta - fee_delta
    pos_after = pos - closed * sign
    entry_delta = -closed * avg_entry * sign
    entry_after = account.entry_notional_units + entry_delta
    return wallet_after + pos_after * risk_mark_ticks * mult - entry_after


_SENTINEL_SAFE_BP = 10**18


def _post_close_ratio_bp(
    account: Account,
    close_qty_units: int,
    risk_mark_ticks: int,
    taker_bps: int,
    mult: int,
) -> int:
    """Post-close margin ratio in integer bp.

    When no remaining notional (fully closed or no position), returns
    a sentinel indicating "safe" rather than 0——otherwise the caller's
    "even fully close cannot save us" test always triggers and the
    binary search is never entered.
    """
    pos = account.position_units
    if pos == 0:
        return _SENTINEL_SAFE_BP
    new_pos_abs = abs(pos) - close_qty_units
    if new_pos_abs <= 0:
        return _SENTINEL_SAFE_BP
    new_notional = new_pos_abs * risk_mark_ticks * mult
    new_re = _post_close_risk_equity(account, close_qty_units, risk_mark_ticks, taker_bps, mult)
    if new_notional <= 0:
        return _SENTINEL_SAFE_BP
    return new_re * 10_000 // new_notional


def required_liquidation_qty(
    account: Account,
    risk_mark_ticks: int,
    target_bp: int,
    taker_bps: int,
    mult: int,
) -> int:
    """Smallest q (in min_quantity units) that brings margin ratio >= target_bp.

    Uses integer binary search over ``q ∈ [1, |position|]``.  Both ``q`` and
    ``q - 1 step`` are verified, so the returned value is the *minimal*
    feasible quantity (账户合同 §4.2, last paragraph).

    If the account is already at or above target, returns 0.  If even fully
    closing cannot reach target, returns ``|position|``.
    """
    pos = account.position_units
    if pos == 0:
        return 0
    if _post_close_ratio_bp(account, 0, risk_mark_ticks, taker_bps, mult) >= target_bp:
        return 0

    full = abs(pos)
    if _post_close_ratio_bp(account, full, risk_mark_ticks, taker_bps, mult) < target_bp:
        return full

    lo, hi = 1, full
    best = full
    while lo <= hi:
        mid = (lo + hi) // 2
        ratio = _post_close_ratio_bp(account, mid, risk_mark_ticks, taker_bps, mult)
        if ratio >= target_bp:
            best = mid
            hi = mid - 1
        else:
            lo = mid + 1
    return best


def recompute_required_qty(
    account: Account,
    risk_mark_ticks: int,
    target_bp: int,
    taker_bps: int,
    mult: int,
) -> int:
    """Recompute required close q after risk_mark change (账户合同 §4.3).

    Called inside the liquidation order's own transaction when a previous
    liquidation was only partially filled.  Returns the new q; caller must
    compare with the previous value to decide whether a new MARGIN_CALL
    record is required.
    """
    return required_liquidation_qty(account, risk_mark_ticks, target_bp, taker_bps, mult)
