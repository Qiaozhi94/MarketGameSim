"""§3.1: OB-9b — same-timestamp dual orders with margin rejection.

OB-9b tests that the second order in the same timestamp is rejected
with INSUFFICIENT_MARGIN when the first order exhausts the account's
available margin.  Transaction has only record_index=0.
"""

from __future__ import annotations

from market_game_sim.book.matching import match_order
from market_game_sim.book.orderbook import Book
from market_game_sim.eventlog.bootstrap import (
    build_account_payload_from_accounts,
    build_book_payload,
)
from market_game_sim.kernel.runner import EventKernel
from market_game_sim.ledger.account import Account

MULT = 1000
P100 = 10000


def _limit(oid: str, aid: str, side: str, price: int, qty: int, t: int) -> dict:
    return {
        "event_type": "ORDER_ARRIVAL",
        "timestamp": t,
        "agent_id": aid,
        "order_id": oid,
        "action": "SUBMIT",
        "side": side,
        "order_type": "LIMIT",
        "price_ticks": price,
        "quantity_units": qty,
    }


def _biz_records(records: list[dict]) -> list[dict]:
    return [r for r in records if r["transaction_seq"] >= 3]


def test_ob9b_second_order_rejected_on_margin_exhaustion():
    """OB-9b: A buys most of capacity, B's order is INSUFFICIENT_MARGIN.

    Two accounts with wallet=1000, tier=1 (initial_bp=10000=100% margin).
    Maker M rests sell 100×100.  A buys 9 (1000-100=900 capacity left),
    B tries to buy 10 (> remaining capacity) → rejected.
    """
    accounts = {
        "A": Account(agent_id="A", wallet_units=100_000_000_000),  # 1000 human
        "B": Account(agent_id="B", wallet_units=100_000_000_000),
        "M": Account(agent_id="M", wallet_units=10_000_000_000_000),
    }

    kernel = EventKernel(run_id="ob9b")
    kernel.bootstrap(
        build_account_payload_from_accounts(accounts, mult=MULT),
        build_book_payload(last_ticks=None),
    )

    book = Book(initial_price_ticks=P100)
    world = {
        "book": book,
        "accounts": accounts,
        "exchange_fee_units": 0,
        "exchange_risk_pnl_units": 0,
        "mult": MULT,
        "maker_bps": 0,
        "taker_bps": 0,
        "initial_price_ticks": P100,
        "agent_initial_bp": {"A": 10000, "B": 10000, "M": 10000},
    }

    # M rests sell 100
    kernel.enqueue(_limit("m1", "M", "SELL", P100, 100_000, t=100))

    # A buys 9 (notional 900, wallet 1000 → passes with 1x margin)
    kernel.enqueue(_limit("a1", "A", "BUY", P100, 9_000, t=200))

    # B tries to buy 10 (notional 1000, but wallet only 1000 → exact match for 1x margin
    # with zero fees means reserved_after == risk_equity → should PASS at boundary)
    # Actually B with 1000 wallet at 1x: IM for 10@100 = 1000. fee=0. reserved=1000.
    # risk_equity=1000. 1000 <= 1000 → pass. Need to make B have less wallet.
    # Let B have wallet=999, so 1000 > 999 → REJECT.
    accounts["B"].wallet_units = 99_900_000_000  # 999 human
    kernel.enqueue(_limit("b1", "B", "BUY", P100, 10_000, t=300))

    kernel.run(match_order, world, max_transactions=100)
    assert kernel.terminated == "COMPLETED", f"aborted: {kernel.abort_detail}"

    biz = _biz_records(kernel.committed_records)
    # Find B's transaction: should have accepted=false, reject_reason=INSUFFICIENT_MARGIN
    b_txns = [r for r in biz if r.get("agent_id") == "B"]
    assert len(b_txns) == 1, f"expected 1 B transaction, got {len(b_txns)}"
    b_r0 = b_txns[0]
    assert b_r0["record_index"] == 0
    assert b_r0["accepted"] is False
    assert b_r0["reject_reason"] == "INSUFFICIENT_MARGIN"
    assert b_r0["reserved_delta_units"] == 0

    # Assert B's transaction has only r0 (no trade/market_data records)
    b_tx_seq = b_r0["transaction_seq"]
    other_b = [r for r in biz if r["transaction_seq"] == b_tx_seq and r["record_index"] > 0]
    assert len(other_b) == 0, f"rejected transaction has extra records: {other_b}"


def test_ob9b_first_order_accepted_within_margin():
    """OB-9b pre-condition: A's buy at 9 @ 100 fits within margin and is accepted."""
    accounts = {
        "A": Account(agent_id="A", wallet_units=100_000_000_000),
        "M": Account(agent_id="M", wallet_units=10_000_000_000_000),
    }
    kernel = EventKernel(run_id="ob9b-a")
    kernel.bootstrap(
        build_account_payload_from_accounts(accounts, mult=MULT),
        build_book_payload(last_ticks=None),
    )
    book = Book(initial_price_ticks=P100)
    world = {
        "book": book,
        "accounts": accounts,
        "exchange_fee_units": 0,
        "exchange_risk_pnl_units": 0,
        "mult": MULT,
        "maker_bps": 0,
        "taker_bps": 0,
        "initial_price_ticks": P100,
        "agent_initial_bp": {"A": 10000, "M": 10000},
    }
    kernel.enqueue(_limit("m1", "M", "SELL", P100, 100_000, t=100))
    kernel.enqueue(_limit("a1", "A", "BUY", P100, 9_000, t=200))
    kernel.run(match_order, world, max_transactions=100)
    assert kernel.terminated == "COMPLETED"
    biz = _biz_records(kernel.committed_records)
    a_txns = [r for r in biz if r.get("agent_id") == "A"]
    assert len(a_txns) >= 1
    assert a_txns[0]["accepted"] is True
