"""T204e3 + T405: Bootstrap snapshot helpers.

[事件 Schema §4.6.3] 强制初态快照

Builds the two ``SNAPSHOT`` payloads that the kernel pre-enqueues at
``t=0``: ``ACCOUNT`` (all accounts, sorted by ``agent_id`` codepoint
ascending) and ``BOOK`` (initial empty book with ``last_ticks=null``).

The ``ACCOUNT`` snapshot **must** include every account -- even those
that never trade -- because C1/C2 conservation sums need the full set
and the replayer cannot infer the existence of a never-traded account
from trade postings alone.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from market_game_sim.ledger.account import Account, snapshot_entry


def build_account_snapshot_entry(
    agent_id: str,
    wallet_units: int,
    position_units: int,
    entry_notional_units: int,
    reserved_units: int,
    realized_pnl_units: int,
    state: str,
    liquidation_generation: int,
    margin_ratio_bp: int | None = None,
    chain_id: str | None = None,
    chain_depth: int | None = None,
) -> dict[str, Any]:
    return {
        "agent_id": agent_id,
        "wallet_units": wallet_units,
        "position_units": position_units,
        "entry_notional_units": entry_notional_units,
        "reserved_units": reserved_units,
        "realized_pnl_units": realized_pnl_units,
        "state": state,
        "margin_ratio_bp": margin_ratio_bp,
        "liquidation_generation": liquidation_generation,
        "chain_id": chain_id,
        "chain_depth": chain_depth,
    }


def build_account_payload(
    accounts: list[dict[str, Any]],
    exchange_fee_cash_units: int = 0,
    exchange_risk_pnl_units: int = 0,
) -> dict[str, Any]:
    """Build an ``ACCOUNT`` snapshot payload.

    ``accounts`` is sorted by ``agent_id`` codepoint ascending (§4.6.1).
    The exchange snapshot is appended as a nested object.
    """
    sorted_accounts = sorted(accounts, key=lambda a: a["agent_id"])
    return {
        "accounts": sorted_accounts,
        "exchange": {
            "fee_cash_units": exchange_fee_cash_units,
            "risk_pnl_units": exchange_risk_pnl_units,
        },
    }


def build_book_level(price_ticks: int, quantity_units: int, order_count: int) -> dict[str, Any]:
    return {
        "price_ticks": price_ticks,
        "quantity_units": quantity_units,
        "order_count": order_count,
    }


def build_book_payload(
    bids: list[dict[str, Any]] | None = None,
    asks: list[dict[str, Any]] | None = None,
    last_ticks: int | None = None,
) -> dict[str, Any]:
    """Build a ``BOOK`` snapshot payload (§4.6.2).

    Bids are sorted by ``price_ticks`` descending; asks ascending.
    ``last_ticks`` is ``null`` before the first trade.
    """
    sorted_bids = sorted(bids or [], key=lambda b: b["price_ticks"], reverse=True)
    sorted_asks = sorted(asks or [], key=lambda a: a["price_ticks"])
    return {
        "bids": sorted_bids,
        "asks": sorted_asks,
        "last_ticks": last_ticks,
    }


def build_account_entries_from_accounts(
    accounts: Mapping[str, Account],
    risk_mark_ticks: int | None = None,
    mult: int = 1000,
) -> list[dict[str, Any]]:
    """Build ``ACCOUNT_SNAPSHOT_ENTRY`` list from ``Account`` objects.

    Sorted by ``agent_id`` codepoint ascending (§4.6.1).  Includes every
    account in the mapping -- callers must ensure never-traded accounts
    are present (C1/C2 need the full set).
    """
    return [snapshot_entry(acc, risk_mark_ticks, mult) for _, acc in sorted(accounts.items())]


def build_account_payload_from_accounts(
    accounts: Mapping[str, Account],
    exchange_fee_cash_units: int = 0,
    exchange_risk_pnl_units: int = 0,
    risk_mark_ticks: int | None = None,
    mult: int = 1000,
) -> dict[str, Any]:
    """Build an ``ACCOUNT`` snapshot payload from ``Account`` objects."""
    entries = build_account_entries_from_accounts(accounts, risk_mark_ticks, mult)
    return build_account_payload(
        entries,
        exchange_fee_cash_units=exchange_fee_cash_units,
        exchange_risk_pnl_units=exchange_risk_pnl_units,
    )
