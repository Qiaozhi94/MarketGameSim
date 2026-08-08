"""§3.1, §3.3: OB-8 risk check integration + case 7 liquidation quantity.

Tests the two-phase risk scan producing MARGIN_CALL records and the
binary-search liquidation quantity against acceptance-vectors case 7.
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
from market_game_sim.ledger.liquidation import required_liquidation_qty

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
    return [r for r in records if r["transaction_seq"] >= 3]


def test_ob8_risk_check_produces_margin_call():
    """A leveraged account crosses maint_bp → MARGIN_CALL produced.

    M rests sell 100@100. Leveraged A (wallet=5000, position=500, entry=50000,
    tier=10) watches as another agent drives price down to 94.  At mark=94:
    margin_ratio=425 < 500 (maint).  Next trade triggers risk scan → MARGIN_CALL.
    """
    accounts = {
        "M": Account(agent_id="M", wallet_units=10**16),  # deep pocket maker
        "A": Account(
            agent_id="A",
            wallet_units=5000 * CASH,
            position_units=500_000,
            entry_notional_units=50000 * CASH,
        ),
        "X": Account(agent_id="X", wallet_units=10**16),  # price-driver
    }
    kernel = EventKernel(run_id="ob8")
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
        "agent_initial_bp": {"A": 1000, "M": 1000, "X": 1000},
    }
    # M rests sell at 94 (low price)
    kernel.enqueue(_limit("m1", "M", "SELL", 9400, 100_000, t=100))
    # X crosses M's sell at 94, driving risk_mark to 94
    kernel.enqueue(_market("x1", "X", "BUY", 50_000, t=200))
    kernel.run(match_order, world, max_transactions=100)
    assert kernel.terminated == "COMPLETED", f"aborted: {kernel.abort_detail}"

    biz = _biz(kernel.committed_records)
    mc = [r for r in biz if r["event_type"] == "MARGIN_CALL"]
    assert len(mc) >= 1, f"expected MARGIN_CALL, got events: {[r['event_type'] for r in biz]}"
    assert mc[0]["agent_id"] == "A"
    assert mc[0]["verdict"] == "PENDING_LIQUIDATION"
    assert mc[0]["margin_ratio_bp"] is not None
    assert mc[0]["margin_ratio_bp"] < 500  # below maint


def test_case7_liquidation_qty_exact():
    """Acceptance-vectors case 7: q=288678 at risk_mark=94, taker_fee=5 bps.

    A: wallet=5000 human, position=500 qty, entry=50000 human.
    At mark=94: margin_ratio=425 < 500 maint.  q must be 288678 units.
    """
    q = required_liquidation_qty(
        Account(
            agent_id="A",
            wallet_units=5000 * CASH,
            position_units=500_000,
            entry_notional_units=50000 * CASH,
        ),
        risk_mark_ticks=9400,
        target_bp=1000,
        taker_bps=5,
        mult=MULT,
    )
    assert q == 288678, f"expected 288678, got {q}"
    from market_game_sim.ledger.liquidation import _post_close_ratio_bp

    acct_q = Account(
        agent_id="A",
        wallet_units=5000 * CASH,
        position_units=500_000,
        entry_notional_units=50000 * CASH,
    )
    assert _post_close_ratio_bp(acct_q, q, 9400, 5, MULT) >= 1000
    acct_prev = Account(
        agent_id="A",
        wallet_units=5000 * CASH,
        position_units=500_000,
        entry_notional_units=50000 * CASH * MULT,
    )
    assert _post_close_ratio_bp(acct_prev, q - 1, 9400, 5, MULT) < 1000


def test_case7_recompute_after_partial_fill():
    """After partial fill at mark=92 (from 94), q drops to 193271.

    A: original pos=500, 200 filled at mark=92, remaining pos=300.
    wallet = 5000 - 200*(100-92)*1000 - fee.
    """
    acct = Account(
        agent_id="A",
        wallet_units=3390_800_000_00,
        position_units=300_000,
        entry_notional_units=30_000 * CASH,
    )
    q = required_liquidation_qty(acct, risk_mark_ticks=9200, target_bp=1000, taker_bps=5, mult=MULT)
    assert q == 193271, f"expected 193271, got {q}"


def test_risk_check_m_produces_correct_record_count():
    """Verify that m = actionable accounts (not all scanned accounts).

    Safe account A (no position) should not produce MARGIN_CALL.
    Underwater B should produce PENDING_LIQUIDATION.
    """
    accounts = {
        "A_safe": Account(agent_id="A_safe", wallet_units=10**16),
        "B_under": Account(
            agent_id="B_under",
            wallet_units=5000 * CASH,
            position_units=500_000,
            entry_notional_units=50000 * CASH,
        ),
        "M": Account(agent_id="M", wallet_units=10**16),
    }
    kernel = EventKernel(run_id="mtest")
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
        "agent_initial_bp": {"A_safe": 1000, "B_under": 1000, "M": 1000},
    }
    kernel.enqueue(_limit("m1", "M", "SELL", 9400, 100_000, t=100))
    kernel.enqueue(_market("x1", "A_safe", "BUY", 50_000, t=200))
    kernel.run(match_order, world, max_transactions=100)
    assert kernel.terminated == "COMPLETED"

    biz = _biz(kernel.committed_records)
    mc = [r for r in biz if r["event_type"] == "MARGIN_CALL"]
    mc_agents = {r["agent_id"] for r in mc}
    # A_safe should NOT appear (no position, no risk)
    assert "A_safe" not in mc_agents, "A_safe should not produce MARGIN_CALL"
