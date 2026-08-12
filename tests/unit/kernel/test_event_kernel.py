"""T204b/c/d: Event kernel behavior -- queue vs transaction records,
buffered atomic write, and fail-stop semantics.

[事件 Schema §1.4] 队列事件 vs 事务记录
[事件 Schema §1.4] 事务内记录顺序 + 缓冲写出
[事件 Schema §1.5] fail-stop 失败语义
[订单簿向量 OB-9a] 同时间戳双订单看到已提交状态
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from market_game_sim.eventlog.bootstrap import (
    build_account_payload,
    build_account_snapshot_entry,
    build_book_payload,
)
from market_game_sim.eventlog.termination import classify_log
from market_game_sim.eventlog.writer import build_run_header, serialize_log
from market_game_sim.kernel.abort import KernelAbort
from market_game_sim.kernel.runner import EventKernel

# --------------------------------------------------------------------------- #
# Minimal matching stub -- sufficient for OB-9a / OB-4 invariants.
# Phase 3 (T301-T307) replaces this with the real matching engine.
# --------------------------------------------------------------------------- #


def _make_book() -> dict[str, Any]:
    return {"bids": [], "asks": []}


def _publish(book: dict) -> dict:
    best_bid = book["bids"][-1]["price_ticks"] if book["bids"] else None
    best_ask = book["asks"][0]["price_ticks"] if book["asks"] else None
    return {
        "event_type": "MARKET_DATA_PUBLISH",
        "best_bid": best_bid,
        "best_ask": best_ask,
        "bid_depth_k": len(book["bids"]),
        "ask_depth_k": len(book["asks"]),
        "last": book.get("last"),
    }


def _rest_sell(book: dict, order_id: str, price: int, qty: int) -> None:
    book["asks"].append({"order_id": order_id, "price_ticks": price, "quantity_units": qty})
    book["asks"].sort(key=lambda x: x["price_ticks"])


def _match_buy(event: dict, book: dict) -> list[dict]:
    """Match a BUY LIMIT order against asks. Returns transaction records."""
    records: list[dict] = []
    remaining = event["quantity_units"]
    limit = event["price_ticks"]
    fills: list[dict] = []
    while remaining > 0 and book["asks"]:
        best = book["asks"][0]
        if best["price_ticks"] > limit:
            break
        fill_qty = min(remaining, best["quantity_units"])
        fills.append(
            {
                "price_ticks": best["price_ticks"],
                "quantity_units": fill_qty,
                "maker_order_id": best["order_id"],
            }
        )
        best["quantity_units"] -= fill_qty
        remaining -= fill_qty
        if best["quantity_units"] == 0:
            book["asks"].pop(0)
    event["accepted"] = True
    event["reject_reason"] = None
    event["reserved_delta_units"] = 0
    for fill in fills:
        records.append(
            {
                "event_type": "TRADE_SETTLE",
                "maker_order_id": fill["maker_order_id"],
                "taker_order_id": event["order_id"],
                "maker_agent_id": "M",
                "taker_agent_id": event["agent_id"],
                "price_ticks": fill["price_ticks"],
                "quantity_units": fill["quantity_units"],
                "notional_cash_units": fill["price_ticks"] * fill["quantity_units"],
                "maker_fee_cash_units": 0,
                "taker_fee_cash_units": 0,
                "valuation_mark_before_half_ticks": 20000,
                "valuation_mark_after_half_ticks": 20000,
                "risk_mark_ticks": fill["price_ticks"],
                "postings": [],
            }
        )
    if remaining < event["quantity_units"]:
        book["last"] = fills[-1]["price_ticks"]
    records.append(_publish(book))
    return records


def _handle_order_arrival(event: dict, book: dict) -> list[dict]:
    event["accepted"] = True
    event["reject_reason"] = None
    event["reserved_delta_units"] = 0
    if event["action"] == "SUBMIT" and event["side"] == "SELL":
        _rest_sell(book, event["order_id"], event["price_ticks"], event["quantity_units"])
        return [_publish(book)]
    if event["action"] == "SUBMIT" and event["side"] == "BUY":
        return _match_buy(event, book)
    return [_publish(book)]


def make_handler(book: dict, fault_after_fill: int | None = None):
    """Build a minimal transaction handler.

    If ``fault_after_fill`` is set, raise after that many TRADE_SETTLE
    records have been produced (T204d fault injection).
    """

    def handler(event: dict, world: dict, kernel: EventKernel) -> list[dict]:
        if event["event_type"] == "SNAPSHOT":
            return []
        if event["event_type"] != "ORDER_ARRIVAL":
            return []
        event.setdefault("origin", "AGENT")
        event.setdefault("trigger_ratio_bp", None)
        event.setdefault("liquidation_generation", None)
        event.setdefault("intent_id", "intent")
        event.setdefault("decision_event_id", "e0_0")
        event.setdefault("submitted_at", event["timestamp"])
        records = _handle_order_arrival(event, book)
        if fault_after_fill is not None:
            fill_count = sum(1 for r in records if r.get("event_type") == "TRADE_SETTLE")
            if fill_count >= fault_after_fill:
                raise RuntimeError("injected fault after fill")
        return records

    return handler


def _make_buy_order(order_id: str, agent_id: str, price: int, qty: int, t: int = 100) -> dict:
    return {
        "event_type": "ORDER_ARRIVAL",
        "timestamp": t,
        "agent_id": agent_id,
        "order_id": order_id,
        "action": "SUBMIT",
        "side": "BUY",
        "order_type": "LIMIT",
        "price_ticks": price,
        "quantity_units": qty,
    }


def _make_sell_order(order_id: str, agent_id: str, price: int, qty: int, t: int = 100) -> dict:
    return {
        "event_type": "ORDER_ARRIVAL",
        "timestamp": t,
        "agent_id": agent_id,
        "order_id": order_id,
        "action": "SUBMIT",
        "side": "SELL",
        "order_type": "LIMIT",
        "price_ticks": price,
        "quantity_units": qty,
    }


def _bootstrap_kernel(kernel: EventKernel) -> None:
    account = build_account_payload(
        [build_account_snapshot_entry("M", 1000000, 0, 0, 0, 0, "ACTIVE", 0)]
    )
    book = build_book_payload()
    kernel.bootstrap(account, book)


# --------------------------------------------------------------------------- #
# T204b: Queue events vs transaction records (OB-9a)
# --------------------------------------------------------------------------- #


class TestOB9aQueueVsTransactionRecords:
    """OB-9a: two buy orders at same timestamp; first eats 10000 level,
    second must fill at 10100.  If TRADE_SETTLE were enqueued, the second
    would see unconsumed 10000 and wrongly fill there."""

    def test_second_order_fills_at_10100_not_10000(self):
        kernel = EventKernel(run_id="ob9a")
        _bootstrap_kernel(kernel)
        book = _make_book()
        t = 100

        kernel.enqueue(_make_sell_order("s1", "M", 10000, 2000, t))
        kernel.enqueue(_make_sell_order("s2", "M", 10100, 2000, t))
        kernel.enqueue(_make_buy_order("A", "A", 10100, 2000, t))
        kernel.enqueue(_make_buy_order("B", "B", 10100, 2000, t))

        kernel.run(make_handler(book), {}, max_transactions=10)

        records = kernel.committed_records
        trades = [r for r in records if r["event_type"] == "TRADE_SETTLE"]
        assert len(trades) == 2
        # A fills at 10000 (eats s1), B fills at 10100 (eats s2)
        trade_a = trades[0]
        trade_b = trades[1]
        assert trade_a["price_ticks"] == 10000
        assert trade_a["maker_order_id"] == "s1"
        assert trade_b["price_ticks"] == 10100
        assert trade_b["maker_order_id"] == "s2"

    def test_transaction_records_never_enqueued(self):
        kernel = EventKernel(run_id="ob9a-records")
        _bootstrap_kernel(kernel)
        book = _make_book()
        t = 100
        kernel.enqueue(_make_sell_order("s1", "M", 10000, 2000, t))
        kernel.enqueue(_make_buy_order("A", "A", 10100, 2000, t))
        kernel.run(make_handler(book), {}, max_transactions=10)

        records = kernel.committed_records
        event_types = [r["event_type"] for r in records]
        # TRADE_SETTLE and MARKET_DATA_PUBLISH appear in the log but
        # were never enqueued -- they are transaction records.
        assert "TRADE_SETTLE" in event_types
        assert "MARKET_DATA_PUBLISH" in event_types
        # enqueue_seq is null for transaction records, non-null for queue events
        for r in records:
            if r["event_type"] in ("TRADE_SETTLE", "MARKET_DATA_PUBLISH"):
                assert r["enqueue_seq"] is None
            else:
                assert r["enqueue_seq"] is not None

    def test_log_keys_strictly_increasing(self):
        kernel = EventKernel(run_id="ob9a-keys")
        _bootstrap_kernel(kernel)
        book = _make_book()
        t = 100
        kernel.enqueue(_make_sell_order("s1", "M", 10000, 2000, t))
        kernel.enqueue(_make_sell_order("s2", "M", 10100, 2000, t))
        kernel.enqueue(_make_buy_order("A", "A", 10100, 2000, t))
        kernel.enqueue(_make_buy_order("B", "B", 10100, 2000, t))
        kernel.run(make_handler(book), {}, max_transactions=10)

        records = kernel.committed_records
        keys = [(r["timestamp"], r["transaction_seq"], r["record_index"]) for r in records]
        for i in range(1, len(keys)):
            assert keys[i] > keys[i - 1], (
                f"key {i} not strictly increasing: {keys[i]} <= {keys[i - 1]}"
            )

    def test_enqueue_rejects_transaction_record_types(self):
        kernel = EventKernel(run_id="ob9a-reject")
        _bootstrap_kernel(kernel)
        with pytest.raises(KernelAbort, match="non-queue event"):
            kernel.enqueue({"event_type": "TRADE_SETTLE", "timestamp": 100})


# --------------------------------------------------------------------------- #
# T204c: Transaction record order + buffered write
# --------------------------------------------------------------------------- #


class TestTransactionRecordOrder:
    def test_market_data_publish_always_last(self):
        kernel = EventKernel(run_id="t204c-mdp")
        _bootstrap_kernel(kernel)
        book = _make_book()
        kernel.enqueue(_make_sell_order("s1", "M", 10000, 2000, 100))
        kernel.enqueue(_make_buy_order("A", "A", 10100, 2000, 100))
        kernel.run(make_handler(book), {}, max_transactions=10)

        records = kernel.committed_records
        # Group by transaction_seq
        txns: dict[int, list[dict]] = {}
        for r in records:
            txns.setdefault(r["transaction_seq"], []).append(r)
        for txn_seq, txn_records in txns.items():
            if len(txn_records) <= 1:
                continue
            for r in txn_records[:-1]:
                assert r["event_type"] != "MARKET_DATA_PUBLISH", (
                    f"MARKET_DATA_PUBLISH not last in transaction {txn_seq}"
                )

    def test_accepted_false_transaction_has_only_r0(self):
        kernel = EventKernel(run_id="t204c-reject")
        _bootstrap_kernel(kernel)

        def reject_handler(event, world, kernel):
            if event["event_type"] == "SNAPSHOT":
                return []
            event["accepted"] = False
            event["reject_reason"] = "TICK_MISALIGNED"
            event["reserved_delta_units"] = 0
            event.setdefault("origin", "AGENT")
            event.setdefault("trigger_ratio_bp", None)
            event.setdefault("liquidation_generation", None)
            event.setdefault("intent_id", "intent")
            event.setdefault("decision_event_id", "e0_0")
            event.setdefault("submitted_at", event["timestamp"])
            return []

        kernel.enqueue(_make_buy_order("A", "A", 10000, 2000, 100))
        kernel.run(reject_handler, {}, max_transactions=10)

        records = kernel.committed_records
        biz = [r for r in records if r["transaction_seq"] > 2]
        assert len(biz) == 1
        assert biz[0]["event_type"] == "ORDER_ARRIVAL"
        assert biz[0]["accepted"] is False

    def test_no_book_change_no_market_data_publish(self):
        kernel = EventKernel(run_id="t204c-nochange")
        _bootstrap_kernel(kernel)

        def no_change_handler(event, world, kernel):
            if event["event_type"] == "SNAPSHOT":
                return []
            event["accepted"] = True
            event["reject_reason"] = None
            event["reserved_delta_units"] = 0
            event.setdefault("origin", "AGENT")
            event.setdefault("trigger_ratio_bp", None)
            event.setdefault("liquidation_generation", None)
            event.setdefault("intent_id", "intent")
            event.setdefault("decision_event_id", "e0_0")
            event.setdefault("submitted_at", event["timestamp"])
            # Simulate a transaction that doesn't change the book
            # (e.g. order that matches fully but book unchanged is still
            # a change; here we simulate a no-op)
            return []

        kernel.enqueue(_make_buy_order("A", "A", 10000, 2000, 100))
        kernel.run(no_change_handler, {}, max_transactions=10)

        records = kernel.committed_records
        biz = [r for r in records if r["transaction_seq"] > 2]
        assert len(biz) == 1
        assert biz[0]["event_type"] == "ORDER_ARRIVAL"
        assert not any(r["event_type"] == "MARKET_DATA_PUBLISH" for r in biz)

    def test_fill_count_backfilled_on_all_trades(self):
        """OB-4 scenario: 3 fills, all must carry fill_count=3."""
        kernel = EventKernel(run_id="t204c-fillcount")
        _bootstrap_kernel(kernel)
        book = _make_book()
        t = 100
        # Setup: 3 sell levels
        kernel.enqueue(_make_sell_order("a1", "M", 10000, 2000, t))
        kernel.enqueue(_make_sell_order("a2", "M", 10100, 2000, t))
        kernel.enqueue(_make_sell_order("a3", "M", 10200, 2000, t))
        # Taker buys 5000 (eats all 3 levels: 2000+2000+1000)
        kernel.enqueue(_make_buy_order("T", "T", 10200, 5000, t))
        kernel.run(make_handler(book), {}, max_transactions=10)

        records = kernel.committed_records
        trades = [r for r in records if r["event_type"] == "TRADE_SETTLE"]
        assert len(trades) == 3
        assert all(tr["fill_count"] == 3 for tr in trades)
        assert [tr["fill_index"] for tr in trades] == [0, 1, 2]
        assert [tr["price_ticks"] for tr in trades] == [10000, 10100, 10200]

    def test_committed_records_not_modified_after_write(self):
        """Written records must never be mutated after commit (§1.4)."""
        kernel = EventKernel(run_id="t204c-immut")
        _bootstrap_kernel(kernel)
        book = _make_book()
        kernel.enqueue(_make_sell_order("s1", "M", 10000, 2000, 100))
        kernel.enqueue(_make_buy_order("A", "A", 10100, 2000, 100))
        kernel.run(make_handler(book), {}, max_transactions=10)

        snapshot1 = copy.deepcopy(kernel.committed_records)
        # Run another transaction
        kernel.enqueue(_make_sell_order("s2", "M", 10000, 2000, 200))
        kernel.enqueue(_make_buy_order("B", "B", 10100, 2000, 200))
        kernel.run(make_handler(book), {}, max_transactions=20)

        snapshot2 = copy.deepcopy(kernel.committed_records)
        # The first run's records must be unchanged
        for i in range(len(snapshot1)):
            assert snapshot1[i] == snapshot2[i], f"record {i} was modified after commit"

    def test_r0_buffered_with_records(self):
        """r0 is buffered alongside transaction records and written atomically."""
        kernel = EventKernel(run_id="t204c-buffer")
        _bootstrap_kernel(kernel)
        book = _make_book()
        kernel.enqueue(_make_sell_order("s1", "M", 10000, 2000, 100))
        kernel.enqueue(_make_buy_order("A", "A", 10100, 2000, 100))
        kernel.run(make_handler(book), {}, max_transactions=10)

        records = kernel.committed_records
        # transaction_seq=3 is the sell (rests: r0 + MDP).
        # transaction_seq=4 is the buy (matches: r0 + TRADE_SETTLE + MDP).
        biz = [r for r in records if r["transaction_seq"] == 4]
        # r0 (ORDER_ARRIVAL) + TRADE_SETTLE + MARKET_DATA_PUBLISH
        assert len(biz) == 3
        assert biz[0]["event_type"] == "ORDER_ARRIVAL"
        assert biz[0]["record_index"] == 0
        assert biz[1]["event_type"] == "TRADE_SETTLE"
        assert biz[1]["record_index"] == 1
        assert biz[2]["event_type"] == "MARKET_DATA_PUBLISH"
        assert biz[2]["record_index"] == 2
        # All share the same transaction_seq
        assert all(r["transaction_seq"] == 4 for r in biz)


# --------------------------------------------------------------------------- #
# T204d: fail-stop semantics
# --------------------------------------------------------------------------- #


class TestFailStop:
    def _setup_ob4(self, kernel: EventKernel, book: dict, t: int = 100):
        kernel.enqueue(_make_sell_order("a1", "M", 10000, 2000, t))
        kernel.enqueue(_make_sell_order("a2", "M", 10100, 2000, t))
        kernel.enqueue(_make_sell_order("a3", "M", 10200, 2000, t))
        kernel.enqueue(_make_buy_order("T", "T", 10200, 5000, t))

    def test_run_terminates_on_exception(self):
        kernel = EventKernel(run_id="t204d-stop")
        _bootstrap_kernel(kernel)
        book = _make_book()
        self._setup_ob4(kernel, book)
        # Fault after 1st fill
        kernel.run(make_handler(book, fault_after_fill=1), {}, max_transactions=20)
        assert kernel.terminated == "ABORTED"

    def test_log_contains_no_records_of_failed_transaction(self):
        kernel = EventKernel(run_id="t204d-no-records")
        _bootstrap_kernel(kernel)
        book = _make_book()
        self._setup_ob4(kernel, book)
        kernel.run(make_handler(book, fault_after_fill=1), {}, max_transactions=20)

        records = kernel.committed_records
        # The failed transaction is the 4th (3 sells + 1 buy = transaction_seq 4-6, buy is 6)
        # Actually: bootstrap(1,2) + s1(3) + s2(4) + s3(5) + buy(6)
        # The buy (transaction_seq=6) fails -> no records with transaction_seq=6
        failed_seqs = {r["transaction_seq"] for r in records if r["transaction_seq"] == 6}
        assert len(failed_seqs) == 0, "failed transaction's records must not appear in log"

    def test_trailer_is_aborted_with_stable_code(self):
        kernel = EventKernel(run_id="t204d-code")
        _bootstrap_kernel(kernel)
        book = _make_book()
        self._setup_ob4(kernel, book)
        kernel.run(make_handler(book, fault_after_fill=1), {}, max_transactions=20)

        assert kernel.terminated == "ABORTED"
        assert kernel.abort_code == "INTERNAL"

    def test_verify_rejects_with_ti4(self):
        """T204d assertion ④: verify (T603/T204e2) rejects with TI-4."""
        kernel = EventKernel(run_id="t204d-ti4")
        _bootstrap_kernel(kernel)
        book = _make_book()
        self._setup_ob4(kernel, book)
        kernel.run(make_handler(book, fault_after_fill=1), {}, max_transactions=20)

        header = build_run_header(
            run_id="t204d-ti4",
            code_version="test",
            config_hash="0" * 64,
            master_seed=42,
            started_at_wall="2026-01-01T00:00:00Z",
            tick_size="0.01",
            min_quantity="0.001",
            cash_unit="0.01",
            mult=1000,
            fee_bps_cap=0,
            initial_price_ticks=10000,
            agent_initial_bp={},
        )
        log_bytes = serialize_log(header, kernel)
        assert classify_log(log_bytes.decode("utf-8")) == "TI-4"

    def test_last_committed_equals_max_transaction_seq_in_log(self):
        """T204d assertion ⑤⑥: last_committed_transaction_seq == max in log."""
        kernel = EventKernel(run_id="t204d-lastseq")
        _bootstrap_kernel(kernel)
        book = _make_book()
        self._setup_ob4(kernel, book)
        kernel.run(make_handler(book, fault_after_fill=1), {}, max_transactions=20)

        records = kernel.committed_records
        max_seq = max(r["transaction_seq"] for r in records)
        assert kernel.last_committed_transaction_seq == max_seq
        # The failed transaction's seq (6) must not appear
        assert 6 not in {r["transaction_seq"] for r in records}

    def test_kernel_abort_code_propagates(self):
        """KernelAbort with a specific abort_code is reflected in the trailer."""
        kernel = EventKernel(run_id="t204d-abortcode")
        _bootstrap_kernel(kernel)

        def conservation_breach_handler(event, world, kernel):
            if event["event_type"] == "SNAPSHOT":
                return []
            raise KernelAbort(abort_code="CONSERVATION_BREACH", detail="C1 violated")

        kernel.enqueue(_make_buy_order("A", "A", 10000, 2000, 100))
        kernel.run(conservation_breach_handler, {}, max_transactions=20)

        assert kernel.terminated == "ABORTED"
        assert kernel.abort_code == "CONSERVATION_BREACH"


# --------------------------------------------------------------------------- #
# T204e3: Bootstrap barrier (basic integration with runner)
# --------------------------------------------------------------------------- #


class TestBootstrapBarrier:
    def test_enqueue_before_bootstrap_raises_internal(self):
        """t=0 class 0 business event must be rejected by the barrier."""
        kernel = EventKernel(run_id="t204e3-barrier")
        with pytest.raises(KernelAbort, match="bootstrap") as exc:
            kernel.enqueue(_make_buy_order("A", "A", 10000, 2000, 0))
        assert exc.value.abort_code == "INTERNAL"

    def test_zero_business_transactions_completed(self):
        kernel = EventKernel(run_id="t204e3-zero")
        _bootstrap_kernel(kernel)
        kernel.run(lambda e, w, k: [], {}, max_transactions=2)

        assert kernel.terminated == "COMPLETED"
        assert kernel.last_committed_transaction_seq == 2
        records = kernel.committed_records
        assert len(records) == 2
        assert all(r["event_type"] == "SNAPSHOT" for r in records)
        assert records[0]["transaction_seq"] == 1
        assert records[0]["snapshot_type"] == "ACCOUNT"
        assert records[1]["transaction_seq"] == 2
        assert records[1]["snapshot_type"] == "BOOK"

    def test_second_snapshot_failure_aborts_with_seq_1(self):
        kernel = EventKernel(run_id="t204e3-fail2")
        _bootstrap_kernel(kernel)

        def fail_book_handler(event, world, kernel):
            if event.get("snapshot_type") == "BOOK":
                raise RuntimeError("BOOK snapshot write failed")
            return []

        kernel.run(fail_book_handler, {}, max_transactions=10)

        assert kernel.terminated == "ABORTED"
        assert kernel.last_committed_transaction_seq == 1
        records = kernel.committed_records
        assert len(records) == 1
        assert records[0]["snapshot_type"] == "ACCOUNT"
        assert records[0]["transaction_seq"] == 1

    def test_business_transactions_start_from_seq_3(self):
        kernel = EventKernel(run_id="t204e3-seq3")
        _bootstrap_kernel(kernel)
        book = _make_book()
        kernel.enqueue(_make_sell_order("s1", "M", 10000, 2000, 100))
        kernel.run(make_handler(book), {}, max_transactions=10)

        records = kernel.committed_records
        biz = [r for r in records if r["event_type"] == "ORDER_ARRIVAL" and r["timestamp"] > 0]
        assert all(r["transaction_seq"] >= 3 for r in biz)

    def test_bootstrap_counts_as_processed_transactions(self):
        kernel = EventKernel(run_id="t204e3-count")
        _bootstrap_kernel(kernel)
        kernel.run(lambda e, w, k: [], {}, max_transactions=2)
        assert kernel.processed_transactions == 2
