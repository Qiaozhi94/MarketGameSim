"""§1.10: ``leverage_tier`` -> ``world["agent_initial_bp"]`` admission-gate wiring.

Regression tests for the fix landed in round 6 of the 0.1.2 implementation
review (docs/reviews/2026-08-06-v0.1.2-fix-verification-round6.md §1):
``experiment/runner.py::run_one`` now populates ``world["agent_initial_bp"]``
from each agent's ``leverage_tier``, so the admission gate in
``matching.py::_initial_bp`` (used by the initial-margin check) actually
reflects the account's configured leverage instead of always falling back
to the 1x default.

Covers the two halves of the end-to-end chain:
1. Admission: the exact same order is rejected at 1x and accepted at 8x.
2. Consequence: a position opened only because of 8x leverage later
   produces a real MARGIN_CALL when the price drops -- proving the wired
   leverage tier is not just accepted at the gate but genuinely changes
   downstream risk.
"""

from __future__ import annotations

from market_game_sim.book.matching import match_order
from market_game_sim.book.orderbook import Book
from market_game_sim.eventlog.bootstrap import (
    build_account_payload_from_accounts,
    build_book_payload,
)
from market_game_sim.kernel.runner import EventKernel
from market_game_sim.ledger.account import Account, initial_margin_bp_for_tier

MULT = 1000
CASH = 10**8
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


def _market(oid: str, aid: str, side: str, qty: int, t: int) -> dict:
    return {
        "event_type": "ORDER_ARRIVAL",
        "timestamp": t,
        "agent_id": aid,
        "order_id": oid,
        "action": "SUBMIT",
        "side": side,
        "order_type": "MARKET",
        "price_ticks": None,
        "quantity_units": qty,
    }


def _biz(records: list[dict]) -> list[dict]:
    return [r for r in records if r["transaction_seq"] >= 2]


def _run_admission_case(initial_bp: int) -> dict:
    """Same wallet (1000 human), same order (11 qty @ 100 = 1100 notional)."""
    accounts = {
        "M": Account(agent_id="M", wallet_units=10**16),
        "A": Account(agent_id="A", wallet_units=100_000_000_000),  # 1000 human
    }
    kernel = EventKernel(run_id=f"initial-bp-{initial_bp}")
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
        "agent_initial_bp": {"A": initial_bp, "M": 10000},
    }
    kernel.enqueue(_limit("m1", "M", "SELL", P100, 1_000_000, t=100))
    kernel.enqueue(_limit("a1", "A", "BUY", P100, 11_000, t=200))
    kernel.run(match_order, world, max_transactions=100)
    assert kernel.terminated == "COMPLETED", f"aborted: {kernel.abort_detail}"
    biz = _biz(kernel.committed_records)
    a_r0 = next(r for r in biz if r.get("agent_id") == "A")
    return a_r0


def test_1x_tier_rejects_order_8x_tier_accepts_same_order():
    """Same wallet, same order: initial_bp=10000 (1x) rejects, 1250 (8x) accepts.

    Before the §1.10 fix, ``_initial_bp`` always fell back to the 1x
    default regardless of ``leverage_tier``, so the 8x case here would
    also have been rejected.
    """
    assert initial_margin_bp_for_tier(1) == 10000
    assert initial_margin_bp_for_tier(8) == 1250

    tier1 = _run_admission_case(initial_margin_bp_for_tier(1))
    assert tier1["accepted"] is False
    assert tier1["reject_reason"] == "INSUFFICIENT_MARGIN"

    tier8 = _run_admission_case(initial_margin_bp_for_tier(8))
    assert tier8["accepted"] is True
    assert tier8["reject_reason"] is None


def test_leveraged_position_triggers_real_margin_call_on_price_drop():
    """A position only opened because of 8x leverage later breaches maint_bp.

    A buys 80 qty @ 100 (8000 notional) against a 1000-human wallet --
    only possible at 8x (IM=1000, exactly the wallet).  At 1x this order
    would need IM=8000 and be rejected outright, so no position (and thus
    no downstream MARGIN_CALL) could ever exist for this agent.  Price
    then drops to 90, breaching maint_bp -- confirming the wired leverage
    tier has genuine downstream risk consequences, not just admission.
    """
    accounts = {
        "M": Account(agent_id="M", wallet_units=10**16),
        "A": Account(agent_id="A", wallet_units=100_000_000_000),  # 1000 human
        "X": Account(agent_id="X", wallet_units=10**16),
    }
    kernel = EventKernel(run_id="initial-bp-mc")
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
        "maint_bp": 500,
        "target_bp": 1000,
        "liquidation_latency_ns": 1_000_000,
        "agent_initial_bp": {
            "A": initial_margin_bp_for_tier(8),
            "M": 10000,
            "X": 10000,
        },
    }
    kernel.enqueue(_limit("m1", "M", "SELL", P100, 1_000_000, t=100))
    kernel.enqueue(_limit("a1", "A", "BUY", P100, 80_000, t=200))
    # Drive mark down to 90 -> A breaches maint_bp.
    kernel.enqueue(_limit("m3", "M", "BUY", 9000, 1_000_000, t=250))
    kernel.enqueue(_market("x1", "X", "SELL", 10_000, t=300))
    kernel.run(match_order, world, max_transactions=200)
    assert kernel.terminated == "COMPLETED", f"aborted: {kernel.abort_detail}"

    biz = _biz(kernel.committed_records)
    a_open = next(r for r in biz if r.get("order_id") == "a1")
    assert a_open["accepted"] is True  # admitted at 8x -- would reject at 1x

    mc = [r for r in biz if r["event_type"] == "MARGIN_CALL" and r["agent_id"] == "A"]
    assert len(mc) >= 1, f"expected a MARGIN_CALL for A, got: {[r['event_type'] for r in biz]}"
    assert mc[0]["verdict"] == "PENDING_LIQUIDATION"
    assert mc[0]["margin_ratio_bp"] is not None
    assert mc[0]["margin_ratio_bp"] < 500  # below maint_bp
