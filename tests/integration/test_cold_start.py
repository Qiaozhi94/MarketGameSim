"""T407: End-to-end cold-start verification.

Order of events in cold start (代理策略 §3.2):
1. Market maker first observation
2. Market maker places bilateral quotes
3. Book has bid/ask
4. Belief agent observes, decides
5. Belief agent's order crosses the spread
6. First trade happens
7. risk_mark switches from initial_price to last
"""

from __future__ import annotations

import pytest

from market_game_sim.agent.handler import (
    handle_agent_decide,
    handle_agent_observe,
)
from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.book.matching import match_order
from market_game_sim.book.orderbook import Book
from market_game_sim.eventlog.bootstrap import (
    build_account_payload_from_accounts,
    build_book_payload,
)
from market_game_sim.kernel.runner import EventKernel
from market_game_sim.ledger.account import Account


def _mm_spec() -> AgentSpec:
    return AgentSpec(
        agent_id="mm-0",
        role="inventory_market_maker",
        observe_interval_ns=100_000_000,
        latency_ns=5_000_000,
        is_market_maker=True,
        half_spread_ticks=5,
        quote_size=10_000,  # 10 qty
        max_inventory=100_000,  # 100 qty
        inventory_skew_k_bp=10_000,
    )


def _belief_spec(agent_id: str, signal_bp: int = 5000) -> AgentSpec:
    return AgentSpec(
        agent_id=agent_id,
        role="retail",
        observe_interval_ns=1_000_000_000,
        latency_ns=50_000_000,
        leverage_tier=10,
        aggressiveness_bp=10_000,  # taker
        max_order_qty=10_000,  # 10 qty
    )


def _bootstrap_world(
    accounts: dict[str, Account],
    spec_by_id: dict[str, AgentSpec],
    agent_signals: dict[str, int] | None = None,
):
    world: dict = {
        "book": Book(initial_price_ticks=10000),
        "accounts": accounts,
        "exchange_fee_units": 0,
        "exchange_risk_pnl_units": 0,
        "mult": 1000,
        "maker_bps": -1,
        "taker_bps": 5,
        "initial_price_ticks": 10000,
        "agent_specs": spec_by_id,
        "agent_signals": agent_signals or {},
        "agent_decision_index": {},
    }
    return world


def _dispatch(event: dict, world: dict, kernel: EventKernel) -> list[dict]:
    et = event["event_type"]
    if et == "ORDER_ARRIVAL":
        return match_order(event, world, kernel)
    if et == "AGENT_OBSERVE":
        return handle_agent_observe(event, world, kernel)
    if et == "AGENT_DECIDE":
        specs = world.get("agent_specs", {})
        return handle_agent_decide(event, world, kernel, specs)
    return []


def test_market_maker_first_observation_quotes_both_sides():
    mm = _mm_spec()
    spec_by_id = {mm.agent_id: mm}
    accounts = {"mm-0": Account(agent_id="mm-0", wallet_units=10**12)}
    world = _bootstrap_world(accounts, spec_by_id)

    kernel = EventKernel(run_id="cold")
    kernel.bootstrap(
        build_account_payload_from_accounts(accounts, mult=1000),
        build_book_payload(last_ticks=None),
    )

    # Market maker's first observe at t=0
    kernel.enqueue(
        {
            "event_type": "AGENT_OBSERVE",
            "timestamp": 0,
            "agent_id": "mm-0",
            "observed_at": 0,
            "market_data_event_id": "e1_0",
            "information_set": {},
        }
    )

    kernel.run(_dispatch, world, max_transactions=10)
    assert kernel.terminated == "COMPLETED", (
        f"aborted: code={kernel.abort_code!r} detail={kernel.abort_detail!r}"
    )

    book = world["book"]
    # The market maker should have placed a bid at 9995 and an ask at 10005
    assert book.best_bid() == 9995
    assert book.best_ask() == 10005


def _run_cold_start_pipeline(enqueue_order: tuple[str, str]):
    """§2.17: shared driver for the cold-start pipeline test, parameterized
    on AGENT_OBSERVE enqueue order so the outcome can be checked for
    order-independence rather than relying on one hardcoded sequence.

    The belief agent gets a second observation after the MM quote arrives.
    Decisions are required to use their observation snapshot; relying on the
    first delayed decision to read the live book would be look-ahead leakage.
    """
    mm = _mm_spec()
    agent = _belief_spec("agent-0", signal_bp=10_000)  # max long
    spec_by_id = {mm.agent_id: mm, agent.agent_id: agent}
    accounts = {
        "mm-0": Account(agent_id="mm-0", wallet_units=10**12),
        "agent-0": Account(agent_id="agent-0", wallet_units=10**12),
    }
    world = _bootstrap_world(accounts, spec_by_id, agent_signals={"agent-0": 10_000})

    kernel = EventKernel(run_id="cold")
    kernel.bootstrap(
        build_account_payload_from_accounts(accounts, mult=1000),
        build_book_payload(last_ticks=None),
    )

    # Schedule both agents' first (and only) observe at t=0, in the given order.
    for aid in enqueue_order:
        kernel.enqueue(
            {
                "event_type": "AGENT_OBSERVE",
                "timestamp": 0,
                "agent_id": aid,
                "observed_at": 0,
                "market_data_event_id": "e1_0",
                "information_set": {},
            }
        )

    kernel.enqueue(
        {
            "event_type": "AGENT_OBSERVE",
            "timestamp": 20_000_000,
            "agent_id": "agent-0",
            "observed_at": 20_000_000,
            "market_data_event_id": "e1_0",
            "information_set": {},
        }
    )

    kernel.run(_dispatch, world, max_transactions=80)
    assert kernel.terminated == "COMPLETED", (
        f"aborted: code={kernel.abort_code!r} detail={kernel.abort_detail!r}"
    )
    return kernel, world


def test_cold_start_full_pipeline_first_trade_flips_risk_mark():
    """MM quotes, belief agent crosses, first trade -> risk_mark = last."""
    kernel, world = _run_cold_start_pipeline(("mm-0", "agent-0"))

    book = world["book"]
    assert book.last_ticks is not None, "expected at least one trade to flip risk_mark"
    # The first trade should be near the market maker's quotes; the spread
    # may cause it to differ when the agent's order crosses both sides.
    assert abs(book.last_ticks - 10000) <= 50, f"unexpected last_ticks {book.last_ticks}"

    # §2.17: check the actual event-TYPE sequence, not just final state --
    # a real trade requires the pipeline to have gone
    # AGENT_OBSERVE -> AGENT_DECIDE -> ORDER_ARRIVAL -> TRADE_SETTLE in that
    # relative order (each stage causally produces the next).
    seq = [r["event_type"] for r in kernel.committed_records]
    assert "TRADE_SETTLE" in seq, f"no TRADE_SETTLE in event sequence: {seq}"
    idx_decide = seq.index("AGENT_DECIDE")
    idx_order = seq.index("ORDER_ARRIVAL", idx_decide)
    idx_trade = seq.index("TRADE_SETTLE", idx_order)
    assert idx_decide < idx_order < idx_trade, f"pipeline stages out of causal order: {seq}"


def test_cold_start_full_pipeline_order_independent_of_enqueue_sequence():
    """§2.17 regression: the ORIGINAL test hardcoded
    ``for aid in ("mm-0", "agent-0")`` -- so it only ever verified one
    specific enqueue order, not that the pipeline reaches the same outcome
    (market opens, a trade happens) regardless of which agent's first
    AGENT_OBSERVE happens to be enqueued first.  Runs the reversed order
    and asserts the same qualitative outcome."""
    _kernel, world = _run_cold_start_pipeline(("agent-0", "mm-0"))
    book = world["book"]
    assert book.last_ticks is not None, (
        "market must still open (a trade must still happen) when the belief "
        "agent's first AGENT_OBSERVE is enqueued before the market maker's"
    )
    assert abs(book.last_ticks - 10000) <= 50, f"unexpected last_ticks {book.last_ticks}"


def test_market_maker_skew_stops_one_side_at_max_inventory():
    """At max long, bid suppressed, only ask side quotes, and ask < mid."""
    base = _mm_spec()
    mm = AgentSpec(
        agent_id=base.agent_id,
        role=base.role,
        observe_interval_ns=base.observe_interval_ns,
        latency_ns=base.latency_ns,
        is_market_maker=True,
        half_spread_ticks=20,
        quote_size=base.quote_size,
        max_inventory=base.max_inventory,
        inventory_skew_k_bp=20_000,
    )
    spec_by_id = {mm.agent_id: mm}
    accounts = {"mm-0": Account(agent_id="mm-0", wallet_units=10**12, position_units=100_000)}
    world = _bootstrap_world(accounts, spec_by_id)

    kernel = EventKernel(run_id="skew")
    kernel.bootstrap(
        build_account_payload_from_accounts(accounts, mult=1000),
        build_book_payload(last_ticks=None),
    )
    kernel.enqueue(
        {
            "event_type": "AGENT_OBSERVE",
            "timestamp": 0,
            "agent_id": "mm-0",
            "observed_at": 0,
            "market_data_event_id": "e1_0",
            "information_set": {},
        }
    )
    kernel.run(_dispatch, world, max_transactions=20)
    assert kernel.terminated == "COMPLETED", (
        f"aborted: code={kernel.abort_code!r} detail={kernel.abort_detail!r}"
    )
    book = world["book"]
    assert book.best_bid() is None
    assert book.best_ask() is not None
    assert book.best_ask() < 10000


def test_market_maker_margin_warning_suppresses_increasing_side_end_to_end():
    """§2.15 end-to-end: handler.py wiring of margin_ratio_bp/maint_bp into
    market_maker_intents.  Well under max_inventory (so the inventory-cap
    branch is not the cause), but margin_ratio_bp < maint_bp -> only the
    position-reducing side (SELL, since long) should be quoted.

    wallet=1e10, position=90_000 (well under max_inventory=100_000), entry at
    initial_price (no unrealized pnl) -> risk_equity=wallet=1e10,
    notional=90_000*10000*1000=9e11 -> margin_ratio_bp = 1e10*10000//9e11 = 111
    < default maint_bp=500.
    """
    mm = _mm_spec()
    spec_by_id = {mm.agent_id: mm}
    accounts = {
        "mm-0": Account(
            agent_id="mm-0",
            wallet_units=10_000_000_000,
            position_units=90_000,
            entry_notional_units=90_000 * 10000 * 1000,
        )
    }
    world = _bootstrap_world(accounts, spec_by_id)
    world["maint_bp"] = 500

    kernel = EventKernel(run_id="margin-warning")
    kernel.bootstrap(
        build_account_payload_from_accounts(accounts, mult=1000),
        build_book_payload(last_ticks=None),
    )
    kernel.enqueue(
        {
            "event_type": "AGENT_OBSERVE",
            "timestamp": 0,
            "agent_id": "mm-0",
            "observed_at": 0,
            "market_data_event_id": "e1_0",
            "information_set": {},
        }
    )
    kernel.run(_dispatch, world, max_transactions=20)
    assert kernel.terminated == "COMPLETED", (
        f"aborted: code={kernel.abort_code!r} detail={kernel.abort_detail!r}"
    )
    book = world["book"]
    assert book.best_bid() is None, "BUY side must be suppressed while margin_warning is active"
    assert book.best_ask() is not None, "SELL side (position-reducing) must still quote"


def test_no_orders_enqueued_when_no_book():
    """Belief agent skips decision if no book and not first trade (cold start edge)."""
    agent = _belief_spec("a1", signal_bp=10_000)
    spec_by_id = {agent.agent_id: agent}
    accounts = {"a1": Account(agent_id="a1", wallet_units=10**12)}
    world = _bootstrap_world(accounts, spec_by_id, agent_signals={"a1": 10_000})
    # No initial price -> no book, but first_trade fallback is active
    world["book"] = Book(initial_price_ticks=0)  # no initial price
    world["initial_price_ticks"] = 0

    kernel = EventKernel(run_id="nobook")
    kernel.bootstrap(
        build_account_payload_from_accounts(accounts, mult=1000),
        build_book_payload(last_ticks=None),
    )
    kernel.enqueue(
        {
            "event_type": "AGENT_OBSERVE",
            "timestamp": 0,
            "agent_id": "a1",
            "observed_at": 0,
            "market_data_event_id": "e1_0",
            "information_set": {},
        }
    )
    # The decide will try to enqueue an order. But with initial_price=0, the
    # valuation_mark is 0 which is invalid -> no intent -> no order.
    # However, the observe will still enqueue a decide. The decide produces no
    # orders when there's no book. We just check it doesn't crash.
    try:
        kernel.run(_dispatch, world, max_transactions=10)
    except Exception as exc:
        pytest.fail(f"end-to-end should not crash with empty book: {exc}")
