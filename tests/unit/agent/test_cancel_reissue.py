"""代理策略 §6.2 全撤重报 regression.

Deep-dive while implementing T606 (KPI-005 market validation) found a real
100k-transaction BENCH-001 run produced **zero** cancels, liquidations, or
partial fills.  Root cause: nothing in agent/handler.py or agent/strategy.py
ever emitted a CANCEL action -- §6.2 explicitly requires "每次决策先撤销自己
全部未成交挂单，再按上述规则重新下单" for both belief agents and market
makers, but only new-order submission was ever wired.  ``_handle_cancel``
(book/matching.py) already implemented the CANCEL-processing side and had
its own unit tests, but no caller ever drove a live agent-submitted CANCEL
through the real ``match_order`` entry point -- which is exactly why a
second, unrelated bug (``_populate_r0_defaults`` crashing on a null
``quantity_units`` inside ``_pre_match``) went undetected until now.
"""

from __future__ import annotations

from market_game_sim.agent.handler import _cancel_stale_orders, handle_agent_decide
from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.book.matching import match_order
from market_game_sim.book.orderbook import Book
from market_game_sim.eventlog.bootstrap import (
    build_account_payload_from_accounts,
    build_book_payload,
)
from market_game_sim.kernel.runner import EventKernel
from market_game_sim.ledger.account import Account


class _FakeKernel:
    """Records ``enqueue`` calls without any real queueing/scheduling --
    ``_cancel_stale_orders`` only ever calls ``kernel.enqueue``."""

    def __init__(self):
        self.enqueued: list[dict] = []

    def enqueue(self, event: dict) -> None:
        self.enqueued.append(event)


def _spec(agent_id: str = "agent-0") -> AgentSpec:
    return AgentSpec(
        agent_id=agent_id,
        role="retail",
        observe_interval_ns=1_000_000_000,
        latency_ns=50_000_000,
        leverage_tier=1,
    )


class TestCancelStaleOrdersUnit:
    """Direct unit tests against ``_cancel_stale_orders`` (no kernel/book)."""

    def test_no_active_orders_enqueues_nothing(self):
        kernel = _FakeKernel()
        summaries = _cancel_stale_orders(
            _spec(), {}, kernel, "e1_0", 0, arrival_ts=100, submitted_at=0
        )
        assert summaries == []
        assert kernel.enqueued == []

    def test_active_orders_each_get_a_cancel_arrival(self):
        kernel = _FakeKernel()
        world = {
            "active_orders_by_agent": {
                "agent-0": {"o1": object(), "o2": object()},
                "agent-1": {"o3": object()},  # a different agent's orders must be untouched
            }
        }
        summaries = _cancel_stale_orders(
            _spec(), world, kernel, "e5_0", 3, arrival_ts=555, submitted_at=500
        )
        assert len(kernel.enqueued) == 2
        assert {e["target_order_id"] for e in kernel.enqueued} == {"o1", "o2"}
        for e in kernel.enqueued:
            assert e["event_type"] == "ORDER_ARRIVAL"
            assert e["action"] == "CANCEL"
            assert e["order_id"] == e["target_order_id"]
            assert e["agent_id"] == "agent-0"
            assert e["timestamp"] == 555
            assert e["submitted_at"] == 500
            assert e["decision_event_id"] == "e5_0"
            # §4.1: side/order_type/price_ticks/quantity_units must be null for CANCEL
            assert e["side"] is None
            assert e["order_type"] is None
            assert e["price_ticks"] is None
            assert e["quantity_units"] is None
        assert len(summaries) == 2
        assert all(s["action"] == "CANCEL" for s in summaries)

    def test_intent_ids_are_unique_per_cancelled_order(self):
        kernel = _FakeKernel()
        world = {"active_orders_by_agent": {"agent-0": {"o1": object(), "o2": object()}}}
        summaries = _cancel_stale_orders(
            _spec(), world, kernel, "e1_0", 0, arrival_ts=100, submitted_at=0
        )
        ids = [s["intent_id"] for s in summaries]
        assert len(ids) == len(set(ids))


def _dispatch(event: dict, world: dict, kernel: EventKernel) -> list[dict]:
    et = event["event_type"]
    if et == "ORDER_ARRIVAL":
        return match_order(event, world, kernel)
    if et == "AGENT_DECIDE":
        return handle_agent_decide(event, world, kernel, world.get("agent_specs", {}))
    return []


class TestCancelReissueWiredEndToEnd:
    """Drives two AGENT_DECIDE cycles for the same market maker directly
    (no AGENT_OBSERVE/rescheduling machinery -- that's runner.py's concern,
    tested elsewhere) and confirms the second cycle actually cancels the
    first cycle's resting orders through the real match_order/_handle_cancel
    path, not just that _cancel_stale_orders was called."""

    def _world(self) -> tuple[dict, EventKernel, AgentSpec]:
        mm = AgentSpec(
            agent_id="mm-0",
            role="inventory_market_maker",
            observe_interval_ns=100_000_000,
            latency_ns=5_000_000,
            is_market_maker=True,
            half_spread_ticks=5,
            quote_size=10_000,
            max_inventory=100_000,
            inventory_skew_k_bp=10_000,
        )
        accounts = {"mm-0": Account(agent_id="mm-0", wallet_units=10**14)}
        kernel = EventKernel(run_id="cancel-reissue-test")
        kernel.bootstrap(
            build_account_payload_from_accounts(accounts, mult=1000),
            build_book_payload(last_ticks=None),
        )
        world = {
            "book": Book(initial_price_ticks=10000),
            "accounts": accounts,
            "exchange_fee_units": 0,
            "exchange_risk_pnl_units": 0,
            "mult": 1000,
            "maker_bps": -1,
            "taker_bps": 5,
            "initial_price_ticks": 10000,
            "maint_bp": 500,
            "target_bp": 1000,
            "agent_specs": {"mm-0": mm},
            "agent_signals": {},
            "agent_decision_index": {},
            "agent_initial_bp": {"mm-0": 10000},
        }
        return world, kernel, mm

    def test_second_decision_cancels_first_decisions_resting_orders(self):
        world, kernel, mm = self._world()
        kernel.enqueue(
            {
                "event_type": "AGENT_DECIDE",
                "timestamp": 0,
                "agent_id": "mm-0",
                "_decision_index": 0,
                "decision_event_id": "d0",
            }
        )
        kernel.run(_dispatch, world, max_transactions=10)
        assert kernel.terminated == "COMPLETED", f"abort: {kernel.abort_code}"
        first_round_active_ids = set(world["active_orders_by_agent"].get("mm-0", {}).keys())
        assert len(first_round_active_ids) == 2  # bid + ask quotes

        kernel.enqueue(
            {
                "event_type": "AGENT_DECIDE",
                "timestamp": kernel.committed_records[-1]["timestamp"] + 1,
                "agent_id": "mm-0",
                "_decision_index": 1,
                "decision_event_id": "d1",
            }
        )
        kernel.run(_dispatch, world, max_transactions=20)
        assert kernel.terminated == "COMPLETED", f"abort: {kernel.abort_code}"

        cancel_records = [
            e
            for e in kernel.committed_records
            if e.get("event_type") == "ORDER_CANCELLED" and e.get("reason") == "AGENT_REQUEST"
        ]
        assert {c["order_id"] for c in cancel_records} == first_round_active_ids

        second_round_active_ids = set(world["active_orders_by_agent"].get("mm-0", {}).keys())
        # Negative half: if §6.2 were not wired, the first round's order ids
        # would still be resting alongside the second round's -- this would
        # fail (non-empty intersection, and total count 4 not 2) exactly the
        # way the pre-fix code did.
        assert second_round_active_ids.isdisjoint(first_round_active_ids)
        assert len(second_round_active_ids) == 2  # requoted bid + ask
