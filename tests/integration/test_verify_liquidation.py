"""§1.11 integration: real liquidation log → verify_log must pass (KPI-006/E7)."""

from __future__ import annotations

import json

from market_game_sim.book.matching import match_order
from market_game_sim.book.orderbook import Book
from market_game_sim.eventlog.bootstrap import (
    build_account_payload_from_accounts,
    build_book_payload,
)
from market_game_sim.kernel.runner import EventKernel
from market_game_sim.ledger.account import Account
from market_game_sim.verify import verify_log

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


def test_real_liquidation_log_passes_verify(tmp_path):
    """§1.11: A real liquidation scenario log must pass verify_log.

    M rests sell at 94, leveraged A (500 qty at 100, tier=10) sees
    risk_mark drop to 94 → PENDING_LIQUIDATION → LIQUIDATION order
    scheduled → next trade fills it.  The combined log must pass
    the independent verifier including KPI-006 checks.
    """
    accounts = {
        "M": Account(agent_id="M", wallet_units=10**16),
        "A": Account(
            agent_id="A",
            wallet_units=5000 * CASH,
            position_units=500_000,
            entry_notional_units=50000 * CASH,
        ),
        "S": Account(
            agent_id="S",
            wallet_units=50000 * CASH,
            position_units=-500_000,
            entry_notional_units=-50000 * CASH,
        ),
        "X": Account(agent_id="X", wallet_units=10**16),
    }
    kernel = EventKernel(run_id="liq-verify")
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
        "agent_initial_bp": {"A": 1000, "M": 1000, "S": 1000, "X": 1000},
    }
    # M rests sell, X crosses → risk_mark drops, A triggers PENDING_LIQUIDATION
    # Explicit origin="" on non-agent orders so KPI-006 only checks LIQUIDATION path
    e1 = _limit("m1", "M", "SELL", 9400, 500_000, t=100)
    e1["origin"] = ""
    kernel.enqueue(e1)
    e2 = _market("x1", "X", "BUY", 100_000, t=200)
    e2["origin"] = ""
    kernel.enqueue(e2)
    kernel.run(match_order, world, max_transactions=200)
    assert kernel.terminated == "COMPLETED", f"aborted: {kernel.abort_detail}"

    records = kernel.committed_records
    header = {
        "record_kind": "RUN_HEADER",
        "run_id": "liq-verify",
        "schema_version": 3,
    }
    trailer = {
        "record_kind": "RUN_TRAILER",
        "terminated": "COMPLETED",
        "record_count": len(records) + 2,
    }
    log_path = tmp_path / "liq-verify.jsonl"
    lines = [json.dumps(r, ensure_ascii=False) for r in [header, *records, trailer]]
    log_path.write_text("\n".join(lines), encoding="utf-8")

    result = verify_log(log_path)
    assert result["success"], f"verify failed: {result}"
    assert result["kpi006_liquidation_covered"] is True, f"kpi006: {result}"


def test_real_liquidation_log_multi_account_same_batch_passes_verify(tmp_path):
    """§1.11 batch regression: two accounts (A, B) breach margin in the SAME
    risk scan (same ORDER_ARRIVAL transaction), producing two MARGIN_CALL
    records in one batch.  This exercises the ``mc_base_index + mc_idx``
    indexing in matching.py::_run_post_batch_risk_check that assigns each
    LIQUIDATION order's ``decision_event_id`` -- a single-account test
    cannot distinguish correct per-account indexing from an implementation
    that always points at the first (or last) MARGIN_CALL in the batch.

    M rests a big sell at 94; X's market buy drops last_ticks to 94, which
    breaches BOTH A and B (identical leveraged longs) in the same phase-2
    scan.  ``all_mc`` is sorted by agent_id, so A gets mc_idx=0 and B gets
    mc_idx=1; each LIQUIDATION order's decision_event_id must reference its
    own MARGIN_CALL, not the other account's.
    """
    accounts = {
        "M": Account(agent_id="M", wallet_units=10**16),
        "A": Account(
            agent_id="A",
            wallet_units=5000 * CASH,
            position_units=500_000,
            entry_notional_units=50000 * CASH,
        ),
        "B": Account(
            agent_id="B",
            wallet_units=5000 * CASH,
            position_units=500_000,
            entry_notional_units=50000 * CASH,
        ),
        "S": Account(
            agent_id="S",
            wallet_units=100000 * CASH,
            position_units=-1_000_000,
            entry_notional_units=-100000 * CASH,
        ),
        "X": Account(agent_id="X", wallet_units=10**16),
    }
    kernel = EventKernel(run_id="liq-verify-batch")
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
        "agent_initial_bp": {"A": 1000, "B": 1000, "M": 1000, "S": 1000, "X": 1000},
    }
    e1 = _limit("m1", "M", "SELL", 9400, 500_000, t=100)
    e1["origin"] = ""
    kernel.enqueue(e1)
    e2 = _market("x1", "X", "BUY", 100_000, t=200)
    e2["origin"] = ""
    kernel.enqueue(e2)
    kernel.run(match_order, world, max_transactions=200)
    assert kernel.terminated == "COMPLETED", f"aborted: {kernel.abort_detail}"

    records = kernel.committed_records
    mc_records = [r for r in records if r["event_type"] == "MARGIN_CALL"]
    assert {r["agent_id"] for r in mc_records} == {"A", "B"}, (
        "expected both A and B to breach in the same batch"
    )
    liq_orders = {
        r["agent_id"]: r
        for r in records
        if r["event_type"] == "ORDER_ARRIVAL" and r.get("origin") == "LIQUIDATION"
    }
    assert set(liq_orders) == {"A", "B"}
    mc_event_id = {r["agent_id"]: r["event_id"] for r in mc_records}
    for aid in ("A", "B"):
        assert liq_orders[aid]["decision_event_id"] == mc_event_id[aid], (
            f"{aid}'s LIQUIDATION order must reference its own MARGIN_CALL, "
            f"got {liq_orders[aid]['decision_event_id']!r} vs "
            f"{mc_event_id[aid]!r}"
        )

    header = {
        "record_kind": "RUN_HEADER",
        "run_id": "liq-verify-batch",
        "schema_version": 3,
    }
    trailer = {
        "record_kind": "RUN_TRAILER",
        "terminated": "COMPLETED",
        "record_count": len(records) + 2,
    }
    log_path = tmp_path / "liq-verify-batch.jsonl"
    lines = [json.dumps(r, ensure_ascii=False) for r in [header, *records, trailer]]
    log_path.write_text("\n".join(lines), encoding="utf-8")

    result = verify_log(log_path)
    assert result["success"], f"verify failed: {result}"
    assert result["kpi006_liquidation_covered"] is True, f"kpi006: {result}"
