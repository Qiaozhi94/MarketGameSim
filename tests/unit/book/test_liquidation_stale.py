"""§1.9 (T202b): LIQUIDATION_STALE rejection for expired liquidation orders.

Regression tests for the fix landed in round 6 of the 0.1.2 implementation
review (docs/reviews/2026-08-06-v0.1.2-fix-verification-round6.md §2):
``matching.py`` now compares an incoming ``origin=LIQUIDATION`` order's
carried ``liquidation_generation`` against the account's current one and
rejects on mismatch (账户合同 T202b).

Covers both acceptance-vector-style validation cases:
1. Delayed-window recovery -- account returns to ACTIVE before its
   scheduled liquidation order arrives; the stale order must be rejected
   and the account must not be over-liquidated.
2. Out-of-order arrival -- multiple generations arrive out of numeric
   order; only the order matching the account's *current* generation may
   pass, regardless of arrival sequence.

Also documents (as an expected failure, not yet fixed) the residual gap
found during round 6: a liquidation order missing ``liquidation_generation``
entirely (``None``) bypasses the check.  The production scheduler
(``_run_post_batch_risk_check``) always supplies an integer, so this gap is
not reachable via the normal pipeline -- but nothing stops a malformed
event from reaching ``match_order`` directly.
"""

from __future__ import annotations

from market_game_sim.book.matching import match_order
from market_game_sim.book.orderbook import Book
from market_game_sim.eventlog.bootstrap import (
    build_account_payload_from_accounts,
    build_book_payload,
)
from market_game_sim.kernel.runner import EventKernel
from market_game_sim.ledger.account import Account, AccountState

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


def _liq_market(oid: str, aid: str, side: str, qty: int, t: int, gen: int | None, dec: str) -> dict:
    """A hand-crafted ``origin=LIQUIDATION`` order carrying an explicit generation."""
    event = _market(oid, aid, side, qty, t)
    event["origin"] = "LIQUIDATION"
    event["decision_event_id"] = dec
    if gen is not None:
        event["liquidation_generation"] = gen
    return event


def _biz(records: list[dict]) -> list[dict]:
    return [r for r in records if r["transaction_seq"] >= 2]


def test_stale_order_rejected_after_recovery_in_delay_window():
    """Account跌破维持保证金 -> 强平单排程 -> 延迟窗口内恢复 -> 过期强平单必须被拒.

    A (wallet=5000, position=500, entry=50000, tier such that maint applies)
    is driven to PENDING_LIQUIDATION at mark=94 (gen 0->1).  Before the
    scheduled liquidation order arrives (latency=5,000,000ns later), a
    second trade drives the mark back up to 102, recovering A to ACTIVE
    (gen 1->2).  The stale gen=1 order must then be rejected with
    LIQUIDATION_STALE and must not touch A's position.
    """
    accounts = {
        "M": Account(agent_id="M", wallet_units=10**16),
        "A": Account(
            agent_id="A",
            wallet_units=5000 * CASH,
            position_units=500_000,
            entry_notional_units=50000 * CASH,
        ),
        "X": Account(agent_id="X", wallet_units=10**16),
        "M2": Account(agent_id="M2", wallet_units=10**16),
        "Y": Account(agent_id="Y", wallet_units=10**16),
    }
    kernel = EventKernel(run_id="stale-recovery")
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
        "liquidation_latency_ns": 5_000_000,
        "agent_initial_bp": {"A": 1000, "M": 1000, "X": 1000, "M2": 1000, "Y": 1000},
    }
    # Drive mark down to 94 -> A breaches maint_bp -> PENDING_LIQUIDATION, gen=1,
    # a liquidation order is auto-scheduled at t=200 + 5,000,000.
    kernel.enqueue(_limit("m1", "M", "SELL", 9400, 100_000, t=100))
    kernel.enqueue(_market("x1", "X", "BUY", 50_000, t=200))
    # Before the scheduled order arrives, drive mark back up to 102 -- A recovers.
    kernel.enqueue(_limit("m2", "M2", "SELL", 10200, 100_000, t=250))
    kernel.enqueue(_market("y1", "Y", "BUY", 60_000, t=300))
    kernel.run(match_order, world, max_transactions=200)
    assert kernel.terminated == "COMPLETED", f"aborted: {kernel.abort_detail}"

    biz = _biz(kernel.committed_records)
    mc = [r for r in biz if r["event_type"] == "MARGIN_CALL" and r["agent_id"] == "A"]
    assert [r["verdict"] for r in mc] == ["PENDING_LIQUIDATION", "OK"]
    assert mc[0]["liquidation_generation_after"] == 1
    assert mc[1]["liquidation_generation_after"] == 2

    liq_orders = [
        r
        for r in biz
        if r["event_type"] == "ORDER_ARRIVAL" and r.get("order_id", "").startswith("liq-A-")
    ]
    assert len(liq_orders) == 1, (
        f"expected exactly one auto-scheduled liquidation order: {liq_orders}"
    )
    stale = liq_orders[0]
    assert stale["liquidation_generation"] == 1
    assert stale["accepted"] is False
    assert stale["reject_reason"] == "LIQUIDATION_STALE"

    # The rejected transaction must have no side effects: no fill, no position change.
    assert accounts["A"].position_units == 500_000
    assert accounts["A"].state == AccountState.ACTIVE


def test_out_of_order_generations_only_current_passes():
    """账户合同 T202b 验收用例②: pending 期间连续两次数量变化、三张单乱序到达.

    Account A is already PENDING_LIQUIDATION at generation 3 (simulating two
    prior recounts).  Three liquidation orders carrying generations
    [2, 3, 1] arrive in that (non-monotonic) sequence.  Only the gen=3
    order -- matching A's *current* generation -- may be accepted; the
    other two must be rejected regardless of their relative arrival order.
    """
    accounts = {
        "M": Account(agent_id="M", wallet_units=10**16),
        "A": Account(
            agent_id="A",
            wallet_units=5000 * CASH,
            position_units=500_000,
            entry_notional_units=50000 * CASH,
            state=AccountState.PENDING_LIQUIDATION,
            liquidation_generation=3,
            chain_id="mc0",
            chain_depth=0,
        ),
    }
    kernel = EventKernel(run_id="stale-out-of-order")
    kernel.bootstrap(
        build_account_payload_from_accounts(accounts, mult=MULT),
        build_book_payload(last_ticks=9400),
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
        # No maint_bp/target_bp: the natural risk scan must not run and
        # flip A's hand-crafted PENDING_LIQUIDATION state -- this test
        # exercises the LIQUIDATION_STALE gate in isolation.
        "agent_initial_bp": {"A": 1000, "M": 1000},
    }
    kernel.enqueue(_limit("m1", "M", "BUY", 9400, 300_000, t=100))
    kernel.enqueue(_liq_market("liq-g2", "A", "SELL", 10_000, t=200, gen=2, dec="mc0"))
    kernel.enqueue(_liq_market("liq-g3", "A", "SELL", 10_000, t=201, gen=3, dec="mc0"))
    kernel.enqueue(_liq_market("liq-g1", "A", "SELL", 10_000, t=202, gen=1, dec="mc0"))
    kernel.run(match_order, world, max_transactions=200)
    assert kernel.terminated == "COMPLETED", f"aborted: {kernel.abort_detail}"

    biz = _biz(kernel.committed_records)
    by_order = {
        r["order_id"]: r
        for r in biz
        if r["event_type"] == "ORDER_ARRIVAL" and r.get("agent_id") == "A"
    }
    assert by_order["liq-g2"]["accepted"] is False
    assert by_order["liq-g2"]["reject_reason"] == "LIQUIDATION_STALE"
    assert by_order["liq-g3"]["accepted"] is True
    assert by_order["liq-g3"]["reject_reason"] is None
    assert by_order["liq-g1"]["accepted"] is False
    assert by_order["liq-g1"]["reject_reason"] == "LIQUIDATION_STALE"

    # Only the current-generation order (10,000 units) may have touched A's position.
    assert accounts["A"].position_units == 490_000


def test_liquidation_order_without_generation_is_rejected():
    """A malformed LIQUIDATION order (no liquidation_generation) is now
    rejected by the defensive check added in round 6: ``order_gen is None``
    itself grounds rejection with LIQUIDATION_STALE."""
    accounts = {
        "M": Account(agent_id="M", wallet_units=10**16),
        "A": Account(
            agent_id="A",
            wallet_units=5000 * CASH,
            position_units=500_000,
            entry_notional_units=50000 * CASH,
            state=AccountState.PENDING_LIQUIDATION,
            liquidation_generation=3,
            chain_id="mc0",
            chain_depth=0,
        ),
    }
    kernel = EventKernel(run_id="stale-none-gen")
    kernel.bootstrap(
        build_account_payload_from_accounts(accounts, mult=MULT),
        build_book_payload(last_ticks=9400),
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
        "agent_initial_bp": {"A": 1000, "M": 1000},
    }
    kernel.enqueue(_limit("m1", "M", "BUY", 9400, 300_000, t=100))
    kernel.enqueue(_liq_market("liq-none", "A", "SELL", 10_000, t=200, gen=None, dec="mc0"))
    kernel.run(match_order, world, max_transactions=200)
    assert kernel.terminated == "COMPLETED", f"aborted: {kernel.abort_detail}"

    biz = _biz(kernel.committed_records)
    order = next(
        r for r in biz if r["event_type"] == "ORDER_ARRIVAL" and r.get("order_id") == "liq-none"
    )
    assert order["accepted"] is False
    assert order["reject_reason"] == "LIQUIDATION_STALE"
