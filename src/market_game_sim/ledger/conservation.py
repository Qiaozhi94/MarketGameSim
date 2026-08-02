"""T406: C1/C2 per-event conservation (账户合同 §2.3).

[C1] Σ position_units ≡ 0                          (each trade: one long, one short)
[C2] Σ (wallet − entry_notional) + exchange_fee + exchange_risk_pnl
     = Σ wallet_units(0)

C2 must include ``entry_notional`` -- without it, legitimate cross-price
handoff (案例 2) is wrongly flagged.  All assertions are integer-exact; no
tolerance.
"""

from __future__ import annotations

from market_game_sim.ledger.account import Account


def check_c1(accounts: dict[str, Account]) -> tuple[bool, str]:
    total = sum(a.position_units for a in accounts.values())
    if total == 0:
        return True, "C1 ok"
    return False, f"C1 violated: Σposition_units = {total} (expected 0)"


def check_c2(
    accounts: dict[str, Account],
    exchange_fee_units: int,
    exchange_risk_pnl_units: int,
    initial_wallet_sum: int,
) -> tuple[bool, str]:
    lhs = (
        sum(a.wallet_units - a.entry_notional_units for a in accounts.values())
        + exchange_fee_units
        + exchange_risk_pnl_units
    )
    if lhs == initial_wallet_sum:
        return True, "C2 ok"
    diff = lhs - initial_wallet_sum
    return (
        False,
        f"C2 violated: Σ(wallet−entry) + fees + risk = {lhs}, "
        f"expected Σwallet(0) = {initial_wallet_sum}, diff = {diff}",
    )


def check_c1_c2(
    accounts: dict[str, Account],
    exchange_fee_units: int,
    exchange_risk_pnl_units: int,
    initial_wallet_sum: int,
) -> tuple[bool, str]:
    ok1, msg1 = check_c1(accounts)
    if not ok1:
        return False, msg1
    ok2, msg2 = check_c2(accounts, exchange_fee_units, exchange_risk_pnl_units, initial_wallet_sum)
    if not ok2:
        return False, msg2
    return True, "C1+C2 ok"


def initial_wallet_sum_of(accounts: dict[str, Account]) -> int:
    """Σ wallet_units at the current state -- only equals the true initial sum
    when no trade has occurred yet.  Capture the true initial sum at bootstrap."""
    return sum(a.wallet_units for a in accounts.values())
