"""T503 (metrics-dictionary §5.2): Per-trade PnL bridge.

Δequity = Spread + Impact + Revaluation + Funding − Fees

Each component is computed from the trade's TRADE_POSTING data and
valuation_mark snapshots.  Residual must be exactly 0 (integer).

``equity_delta`` here is the *valuation equity* delta (wallet +
unrealized_pnl_at_valuation_mark, 账户合同 §2.2), not the raw
``wallet_delta_units`` -- a trade's wallet only moves by realized PnL and
fees (账本层 apply_fill), while spread/impact/revaluation also account for
the mark-to-market swing of the position the account already held before
this trade.  Reconstructing it needs ``entry_notional_delta_units`` and
``position_after_units`` from the posting in addition to
``wallet_delta_units``, matching the independently-implemented,
acceptance-vector-validated reference in
tests/unit/ledger/test_acceptance_vectors.py::_replay_check.  Omitting the
entry_notional/position-revaluation term (using ``wallet_delta_units``
alone) looks correct for opening trades (pos_before == 0) but produces a
nonzero residual for any trade against a pre-existing position combined
with a moved valuation mark.

All components are denominated in cash_units, which already include the
``MULT`` scaling factor (notional_cash_units = price_ticks * qty_units *
MULT, ADR-001 §1); ``vm_before_half``/``vm_after_half`` are in half-ticks
(best_bid+best_ask), so the tick-domain terms carry an implicit factor of 2
that ``mult // 2`` cancels out.  All arithmetic stays integer-only (no
float), per the no-float-in-core rule.
"""

from __future__ import annotations


def bridge_trade(
    posting: dict,
    vm_before_half: int,
    vm_after_half: int,
    trade_price_ticks: int,
    position_before_units: int,
    mult: int = 1000,
    funding_delta: int = 0,
) -> dict[str, int]:
    """Decompose Δequity for one side of a trade.

    Returns:
        spread, impact, revaluation, funding, fees, residual
    """
    delta_pos = posting.get("position_delta_units", 0)
    wallet_delta = posting.get("wallet_delta_units", 0)
    fee_delta = posting.get("fee_delta_units", 0)
    entry_notional_delta = posting.get("entry_notional_delta_units", 0)
    position_after_units = posting.get("position_after_units", position_before_units + delta_pos)
    mult_half = mult // 2
    spread = delta_pos * (vm_before_half - 2 * trade_price_ticks) * mult_half
    impact = delta_pos * (vm_after_half - vm_before_half) * mult_half
    revaluation = position_before_units * (vm_after_half - vm_before_half) * mult_half
    equity_delta = (
        wallet_delta
        + position_after_units * vm_after_half * mult_half
        - position_before_units * vm_before_half * mult_half
        - entry_notional_delta
    )
    total = spread + impact + revaluation + funding_delta - fee_delta
    residual = equity_delta - total
    return {
        "spread": spread,
        "impact": impact,
        "revaluation": revaluation,
        "funding": funding_delta,
        "fees": fee_delta,
        "equity_delta": equity_delta,
        "residual": residual,
    }
