"""T204e3: Forced initial snapshots (bootstrap barrier).

[事件 Schema §4.6.3] 强制初态快照

At t=0, two SNAPSHOT queue events are pre-enqueued (ACCOUNT enqueue_seq=0,
BOOK enqueue_seq=1); after popping they form transaction_seq=1 and 2;
business transactions start from 3.  Bootstrap barrier: any business
enqueue before both snapshots commit raises KernelAbort(INTERNAL).
ACCOUNT snapshot must include ALL accounts sorted by agent_id codepoint ascending.
"""

from __future__ import annotations

import pytest

from market_game_sim.eventlog.bootstrap import (
    build_account_payload,
    build_account_snapshot_entry,
    build_book_payload,
)
from market_game_sim.kernel.abort import KernelAbort
from market_game_sim.kernel.runner import EventKernel


class TestBootstrapBarrier:
    def test_enqueue_before_bootstrap_raises_internal(self):
        kernel = EventKernel(run_id="b1")
        with pytest.raises(KernelAbort, match="bootstrap") as exc:
            kernel.enqueue({"event_type": "ORDER_ARRIVAL", "timestamp": 0})
        assert exc.value.abort_code == "INTERNAL"

    def test_class0_event_at_t0_rejected_by_barrier(self):
        """t=0 class 0 business event must be rejected by the barrier,
        not allowed to sort before the class 5 snapshots."""
        kernel = EventKernel(run_id="b2")
        with pytest.raises(KernelAbort) as exc:
            kernel.enqueue(
                {
                    "event_type": "ORDER_ARRIVAL",
                    "timestamp": 0,
                    "agent_id": "A",
                    "order_id": "o1",
                    "action": "SUBMIT",
                    "side": "BUY",
                    "order_type": "LIMIT",
                    "price_ticks": 10000,
                    "quantity_units": 1000,
                }
            )
        assert exc.value.abort_code == "INTERNAL"

    def test_double_bootstrap_raises(self):
        kernel = EventKernel(run_id="b3")
        kernel.bootstrap(build_account_payload([]), build_book_payload())
        with pytest.raises(KernelAbort, match="already done"):
            kernel.bootstrap(build_account_payload([]), build_book_payload())


class TestBootstrapTransactionSequencing:
    def test_zero_business_transactions(self):
        """Vector 1: zero business transactions -> exactly 2 EVENTs,
        last_committed_transaction_seq=2, COMPLETED."""
        kernel = EventKernel(run_id="b4")
        kernel.bootstrap(
            build_account_payload(
                [build_account_snapshot_entry("A", 1000, 0, 0, 0, 0, "ACTIVE", 0)]
            ),
            build_book_payload(),
        )
        kernel.run(lambda e, w, k: [], {}, max_transactions=2)

        assert kernel.terminated == "COMPLETED"
        assert kernel.last_committed_transaction_seq == 2
        assert kernel.processed_transactions == 2
        records = kernel.committed_records
        assert len(records) == 2
        assert records[0]["event_type"] == "SNAPSHOT"
        assert records[0]["snapshot_type"] == "ACCOUNT"
        assert records[0]["transaction_seq"] == 1
        assert records[0]["record_index"] == 0
        assert records[1]["event_type"] == "SNAPSHOT"
        assert records[1]["snapshot_type"] == "BOOK"
        assert records[1]["transaction_seq"] == 2

    def test_second_snapshot_failure(self):
        """Vector 2: second snapshot write fails -> ABORTED,
        last_committed_transaction_seq=1 (not null)."""
        kernel = EventKernel(run_id="b5")

        def fail_book(event, world, kernel):
            if event.get("snapshot_type") == "BOOK":
                raise RuntimeError("BOOK snapshot failed")
            return []

        kernel.bootstrap(
            build_account_payload(
                [build_account_snapshot_entry("A", 1000, 0, 0, 0, 0, "ACTIVE", 0)]
            ),
            build_book_payload(),
        )
        kernel.run(fail_book, {}, max_transactions=10)

        assert kernel.terminated == "ABORTED"
        assert kernel.last_committed_transaction_seq == 1
        records = kernel.committed_records
        assert len(records) == 1
        assert records[0]["snapshot_type"] == "ACCOUNT"

    def test_business_transactions_start_from_seq_3(self):
        kernel = EventKernel(run_id="b6")
        kernel.bootstrap(
            build_account_payload(
                [build_account_snapshot_entry("A", 1000, 0, 0, 0, 0, "ACTIVE", 0)]
            ),
            build_book_payload(),
        )
        kernel.enqueue(
            {
                "event_type": "AGENT_OBSERVE",
                "timestamp": 100,
                "agent_id": "A",
                "observed_at": 100,
                "market_data_event_id": "e0",
                "information_set": {},
            }
        )
        kernel.run(lambda e, w, k: [], {}, max_transactions=10)

        records = kernel.committed_records
        biz = [r for r in records if r["transaction_seq"] >= 3]
        assert len(biz) >= 1
        assert all(r["transaction_seq"] >= 3 for r in biz)

    def test_snapshots_are_queue_events(self):
        """Bootstrap snapshots are real queue events with enqueue_seq."""
        kernel = EventKernel(run_id="b7")
        kernel.bootstrap(
            build_account_payload([]),
            build_book_payload(),
        )
        kernel.run(lambda e, w, k: [], {}, max_transactions=2)

        records = kernel.committed_records
        assert records[0]["enqueue_seq"] == 0
        assert records[1]["enqueue_seq"] == 1
        assert records[0]["priority_class"] == 5
        assert records[1]["priority_class"] == 5


class TestAccountSnapshotCompleteness:
    """ACCOUNT snapshot must include ALL accounts, including never-traded ones,
    sorted by agent_id codepoint ascending."""

    def test_accounts_sorted_by_agent_id_codepoint(self):
        accounts = [
            build_account_snapshot_entry("B", 1000, 0, 0, 0, 0, "ACTIVE", 0),
            build_account_snapshot_entry("A", 2000, 0, 0, 0, 0, "ACTIVE", 0),
            build_account_snapshot_entry("C", 3000, 0, 0, 0, 0, "ACTIVE", 0),
        ]
        payload = build_account_payload(accounts)
        ids = [a["agent_id"] for a in payload["accounts"]]
        assert ids == ["A", "B", "C"]

    def test_never_traded_accounts_included(self):
        accounts = [
            build_account_snapshot_entry("trader", 1000, 10, 500, 0, 0, "ACTIVE", 0),
            build_account_snapshot_entry("passive", 5000, 0, 0, 0, 0, "ACTIVE", 0),
        ]
        payload = build_account_payload(accounts)
        ids = [a["agent_id"] for a in payload["accounts"]]
        assert "passive" in ids
        assert "trader" in ids

    def test_exchange_snapshot_included(self):
        payload = build_account_payload([], exchange_fee_cash_units=42, exchange_risk_pnl_units=-7)
        assert payload["exchange"]["fee_cash_units"] == 42
        assert payload["exchange"]["risk_pnl_units"] == -7

    def test_book_payload_last_ticks_null_before_first_trade(self):
        payload = build_book_payload()
        assert payload["last_ticks"] is None
        assert payload["bids"] == []
        assert payload["asks"] == []

    def test_unicode_agent_id_sorting(self):
        accounts = [
            build_account_snapshot_entry("z", 1, 0, 0, 0, 0, "ACTIVE", 0),
            build_account_snapshot_entry("A", 1, 0, 0, 0, 0, "ACTIVE", 0),
            build_account_snapshot_entry("中", 1, 0, 0, 0, 0, "ACTIVE", 0),
        ]
        payload = build_account_payload(accounts)
        ids = [a["agent_id"] for a in payload["accounts"]]
        assert ids == sorted(ids, key=lambda s: s.encode("utf-8"))
