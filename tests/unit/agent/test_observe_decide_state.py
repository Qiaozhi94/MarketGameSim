"""§2.13 regression: information_set/internal_state carry real content.

Nine rounds of the 0.1.2 implementation review found AGENT_OBSERVE.
information_set and AGENT_DECIDE.internal_state were always the literal
``{}`` passed in at enqueue time -- handle_agent_observe never wrote back
what the agent actually saw, and handle_agent_decide never recorded why it
decided what it decided.  event-schema.md §4.4 calls information_set "KPI-006
追溯链的起点" (the start of the KPI-006 traceability chain) and §4.5 calls
internal_state "决策相关的内部状态" (decision-relevant internal state) --
neither can serve that purpose while always empty.
"""

from __future__ import annotations

from market_game_sim.agent.handler import handle_agent_decide, handle_agent_observe
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
        quote_size=10_000,
        max_inventory=100_000,
        inventory_skew_k_bp=10_000,
    )


def _belief_spec(agent_id: str) -> AgentSpec:
    return AgentSpec(
        agent_id=agent_id,
        role="retail",
        observe_interval_ns=1_000_000_000,
        latency_ns=50_000_000,
        leverage_tier=10,
        aggressiveness_bp=10_000,
        max_order_qty=10_000,
    )


def _dispatch(event: dict, world: dict, kernel: EventKernel) -> list[dict]:
    et = event["event_type"]
    if et == "ORDER_ARRIVAL":
        return match_order(event, world, kernel)
    if et == "AGENT_OBSERVE":
        return handle_agent_observe(event, world, kernel)
    if et == "AGENT_DECIDE":
        return handle_agent_decide(event, world, kernel, world.get("agent_specs", {}))
    return []


def _run(spec_by_id: dict[str, AgentSpec], accounts: dict[str, Account]) -> list[dict]:
    world = {
        "book": Book(initial_price_ticks=10000),
        "accounts": accounts,
        "exchange_fee_units": 0,
        "exchange_risk_pnl_units": 0,
        "mult": 1000,
        "maker_bps": -1,
        "taker_bps": 5,
        "initial_price_ticks": 10000,
        "agent_specs": spec_by_id,
        "agent_signals": {"agent-0": 10_000} if "agent-0" in spec_by_id else {},
        "agent_decision_index": {},
    }
    kernel = EventKernel(run_id="state")
    kernel.bootstrap(
        build_account_payload_from_accounts(accounts, mult=1000),
        build_book_payload(last_ticks=None),
    )
    for aid in spec_by_id:
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
    kernel.run(_dispatch, world, max_transactions=20)
    assert kernel.terminated == "COMPLETED", f"aborted: {kernel.abort_detail}"
    return kernel.committed_records


def test_agent_observe_information_set_is_populated_not_empty():
    mm = _mm_spec()
    accounts = {"mm-0": Account(agent_id="mm-0", wallet_units=10**12)}
    records = _run({"mm-0": mm}, accounts)
    observes = [r for r in records if r["event_type"] == "AGENT_OBSERVE"]
    assert observes
    for r in observes:
        assert r["information_set"] != {}
        assert "best_bid" in r["information_set"]
        assert "position_units" in r["information_set"]


def test_agent_observe_information_set_reflects_real_account_state():
    """Not just non-empty -- the recorded snapshot must match the actual
    account, not a stub/placeholder value."""
    mm = _mm_spec()
    accounts = {
        "mm-0": Account(
            agent_id="mm-0",
            wallet_units=10**12,
            position_units=12_345,
            entry_notional_units=999,
        )
    }
    records = _run({"mm-0": mm}, accounts)
    first_observe = next(r for r in records if r["event_type"] == "AGENT_OBSERVE")
    assert first_observe["information_set"]["position_units"] == 12_345
    assert first_observe["information_set"]["wallet_units"] == 10**12


def test_market_maker_internal_state_records_inventory_and_margin():
    mm = _mm_spec()
    accounts = {
        "mm-0": Account(
            agent_id="mm-0",
            wallet_units=10**12,
            position_units=500,
            entry_notional_units=500 * 10000 * 1000,
        )
    }
    records = _run({"mm-0": mm}, accounts)
    decides = [r for r in records if r["event_type"] == "AGENT_DECIDE"]
    assert decides
    for r in decides:
        assert r["internal_state"] != {}
        assert r["internal_state"]["inventory_units"] == 500


def test_belief_agent_internal_state_records_signal_bp():
    agent = _belief_spec("agent-0")
    accounts = {"agent-0": Account(agent_id="agent-0", wallet_units=10**12)}
    records = _run({"agent-0": agent}, accounts)
    decides = [r for r in records if r["event_type"] == "AGENT_DECIDE"]
    assert decides
    for r in decides:
        assert r["internal_state"] != {}
        assert r["internal_state"]["signal_bp"] == 10_000  # static agent_signals override


def test_internal_state_differs_by_agent_role():
    """Negative/contrast case: a market maker's internal_state and a belief
    agent's internal_state must NOT have the same shape -- proves each
    branch really records its own type-appropriate content rather than a
    shared generic stub."""
    mm = _mm_spec()
    agent = _belief_spec("agent-0")
    accounts = {
        "mm-0": Account(agent_id="mm-0", wallet_units=10**12),
        "agent-0": Account(agent_id="agent-0", wallet_units=10**12),
    }
    records = _run({"mm-0": mm, "agent-0": agent}, accounts)
    decides = {r["agent_id"]: r for r in records if r["event_type"] == "AGENT_DECIDE"}
    assert "inventory_units" in decides["mm-0"]["internal_state"]
    assert "signal_bp" not in decides["mm-0"]["internal_state"]
    assert "signal_bp" in decides["agent-0"]["internal_state"]
    assert "inventory_units" not in decides["agent-0"]["internal_state"]
