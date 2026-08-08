"""T206: Two-step bankruptcy write-off (账户合同 §5).

A bankruptcy occurs when a position is fully closed (or zero) but the
wallet is negative.  The two-step process:

1. ``confirm_breach`` -- identifies breached accounts (position==0,
   wallet<0) at the end of an order-arrival transaction's batch.

2. :func:`write_off_postings` -- builds the WRITE_OFF_POSTING pair that
   brings the account wallet to zero and records the symmetric
   exchange_risk_pnl delta (loss is negative per 账户合同 §5.2).

The function returns the two postings, in [ACCOUNT, EXCHANGE_RISK] order
(事件 Schema §4.2.3).  The caller mutates the ledger state.
"""

from __future__ import annotations

from market_game_sim.ledger.account import Account


def find_breached(accounts: dict[str, Account]) -> list[str]:
    """Return breached agent_ids in sorted order: ``position == 0 and wallet < 0``.

    Phase 1 of the two-phase risk check (账户合同 §4.1).  Only accounts
    touched by the current batch participate (the caller filters).
    """
    return sorted(
        aid for aid, acct in accounts.items() if acct.position_units == 0 and acct.wallet_units < 0
    )


def write_off_postings(agent_id: str, account: Account) -> list[dict]:
    """Build the WRITE_OFF_POSTING pair (ACCOUNT, EXCHANGE_RISK) for ``agent_id``.

    The account's wallet must be negative (caller is responsible for this
    check).  Returns the two postings in fixed order; the caller is
    responsible for applying the deltas to the account and to the
    exchange_risk_pnl_units total.

    Per 事件 Schema §4.2.3:

    * ACCOUNT posting carries the wallet delta and ``*_after`` fields.
    * EXCHANGE_RISK posting has ``agent_id = null`` and three
      ``*_after`` fields set to ``null`` (not 0) because the exchange
      account does not have those fields in its domain.
    """
    if account.wallet_units >= 0:
        raise ValueError(
            f"write_off_postings: account {agent_id} has non-negative wallet "
            f"{account.wallet_units}; breach requires wallet < 0"
        )
    w_neg = account.wallet_units
    return [
        {
            "posting_type": "WRITE_OFF_POSTING",
            "role": "ACCOUNT",
            "agent_id": agent_id,
            "wallet_delta_units": -w_neg,
            "wallet_after_units": 0,
            "position_after_units": 0,
            "entry_notional_after_units": 0,
            "risk_pnl_delta_units": 0,
        },
        {
            "posting_type": "WRITE_OFF_POSTING",
            "role": "EXCHANGE_RISK",
            "agent_id": None,
            "wallet_delta_units": 0,
            "wallet_after_units": None,
            "position_after_units": None,
            "entry_notional_after_units": None,
            "risk_pnl_delta_units": w_neg,
        },
    ]


def apply_write_off(accounts: dict[str, Account], exchange_risk_pnl_units: int) -> int:
    """Apply write-offs to ``accounts`` and return updated exchange_risk_pnl_units.

    For each breached account, set wallet to 0, transition state to
    LIQUIDATED, and add the negative wallet to the exchange risk account
    (C2 stays balanced: 事件 Schema §4.2.3 last paragraph).

    Returns the updated ``exchange_risk_pnl_units`` total.
    """
    from market_game_sim.ledger.account import AccountState

    for _aid, acct in list(accounts.items()):
        if acct.position_units == 0 and acct.wallet_units < 0:
            exchange_risk_pnl_units += acct.wallet_units
            acct.wallet_units = 0
            acct.state = AccountState.LIQUIDATED
            acct.chain_id = None
            acct.chain_depth = None
    return exchange_risk_pnl_units
