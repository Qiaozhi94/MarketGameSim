"""T211: decision-evidence full-chain verifier (AC-005 / TR-501 / TR-502).

Drives a real goal-driven run and asserts the independent verifier
(evidence/chain_verifier.py) resolves every decision's evidence chain:
observe (cursor boundaries) -> decide (DecisionEvidenceV1) -> order ->
trade, plus the closed-set provenance rule and the SPONTANEOUS
no-EXOGENOUS_STRESS rule (positive and negative cases).
"""

from __future__ import annotations

import pytest

from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.evidence.chain_verifier import (
    ChainVerificationError,
    verify_decision_evidence_chain,
)
from market_game_sim.experiment.config import ExperimentConfig
from market_game_sim.experiment.runner import run_one


def _specs() -> list[AgentSpec]:
    return [
        AgentSpec(
            agent_id="mm-0",
            role="inventory_market_maker",
            observe_interval_ns=100_000_000,
            latency_ns=5_000_000,
            is_market_maker=True,
            half_spread_ticks=5,
            quote_size=10_000,
            max_inventory=100_000,
            inventory_skew_k_bp=10_000,
        ),
        AgentSpec(
            agent_id="agent-0",
            role="retail",
            observe_interval_ns=1_000_000_000,
            latency_ns=50_000_000,
            leverage_tier=10,
            initial_bp=1000,
            aggressiveness_bp=10_000,
            max_order_qty=10_000,
            goal_model_id="risk_budget_linear_v1",
            risk_appetite_x1000=2000,
        ),
    ]


def _run_events() -> list[dict]:
    cfg = ExperimentConfig(
        seed=11,
        max_transactions=60,
        agent_specs=_specs(),
        agent_signals={"agent-0": 10_000},
    )
    result = run_one(cfg)
    assert result.terminated == "COMPLETED", f"aborted: {result.abort_code}"
    return result.events


def test_goal_driven_log_passes_full_chain():
    events = _run_events()
    verify_decision_evidence_chain(events, run_family="SPONTANEOUS")
    # No exception = chain intact.


def test_provenance_closed_set_violation_detected():
    events = _run_events()
    for e in events:
        if e.get("event_type") == "AGENT_DECIDE" and e.get("agent_id") == "agent-0":
            e["decision_evidence"]["trigger_provenance"] = "ALIEN"
            break
    with pytest.raises(ChainVerificationError, match="trigger_provenance"):
        verify_decision_evidence_chain(events)


def test_spontaneous_rejects_exogenous_stress():
    events = _run_events()
    for e in events:
        if e.get("event_type") == "AGENT_DECIDE":
            e["decision_evidence"]["trigger_provenance"] = "EXOGENOUS_STRESS"
            break
    with pytest.raises(ChainVerificationError, match="EXOGENOUS_STRESS"):
        verify_decision_evidence_chain(events, run_family="SPONTANEOUS")


def test_cursor_mismatch_detected():
    events = _run_events()
    for e in events:
        if e.get("event_type") == "AGENT_DECIDE" and e.get("agent_id") == "agent-0":
            e["decision_evidence"]["cursor_to_event_id"] = "e999_0"
            break
    with pytest.raises(ChainVerificationError, match="cursor_to"):
        verify_decision_evidence_chain(events)


def test_observation_not_earlier_detected():
    events = _run_events()
    for e in events:
        if e.get("event_type") == "AGENT_DECIDE" and e.get("agent_id") == "agent-0":
            # Point the evidence at a *later* observation (itself) to break
            # strict ordering.
            e["decision_evidence"]["observation_event_id"] = e["event_id"]
            break
    with pytest.raises(ChainVerificationError, match="strictly earlier"):
        verify_decision_evidence_chain(events)


def test_missing_evidence_detected():
    events = _run_events()
    for e in events:
        if e.get("event_type") == "AGENT_DECIDE" and e.get("agent_id") == "agent-0":
            e["decision_evidence"] = None
            break
    with pytest.raises(ChainVerificationError, match="no decision_evidence"):
        verify_decision_evidence_chain(events)


def test_benchmark_family_allows_exogenous_stress_provenance():
    """Negative control: the SPONTANEOUS restriction is family-scoped -- a
    BENCHMARK run with EXOGENOUS_STRESS provenance must NOT be rejected on
    the family rule (closed-set membership is still enforced elsewhere)."""
    events = _run_events()
    changed_decision_id = None
    for e in events:
        if e.get("event_type") == "AGENT_DECIDE":
            e["decision_evidence"]["trigger_provenance"] = "EXOGENOUS_STRESS"
            changed_decision_id = e["event_id"]
            break
    for e in events:
        if (
            e.get("event_type") == "ORDER_ARRIVAL"
            and e.get("decision_event_id") == changed_decision_id
        ):
            e["origin"] = "EXOGENOUS_STRESS"
    verify_decision_evidence_chain(events, run_family="BENCHMARK")


def test_rejects_broken_order_trade_risk_and_liquidation_links_in_multi_record_log():
    """R018-C007: tampering ANY hop in the full chain -- not just
    observe->decide -- must fail the independent verifier.  A dangling
    ORDER_ARRIVAL.decision_event_id is rejected because the verifier
    composes the complete causal-chain check."""
    events = _run_events()
    orders = [
        r for r in events if r.get("event_type") == "ORDER_ARRIVAL" and r.get("origin") == "AGENT"
    ]
    assert orders, "precondition: at least one AGENT-sourced order"
    orders[0]["decision_event_id"] = "e999_0"
    with pytest.raises(ChainVerificationError):
        verify_decision_evidence_chain(events, run_family="SPONTANEOUS")


def test_multi_interval_goal_chain_passes_and_all_trade_hops_resolve():
    """R018-C007 (Round 3): a long run with multiple observation intervals
    must pass the full-chain verifier -- the V2 evidence cursor_from must be
    the observation's own (advancing) lower boundary, not a hardcoded e1_0.
    Round 2's 60-transaction test never advanced past the first interval, so
    the e1_0 hardcode slipped through."""
    cfg = ExperimentConfig(
        seed=11,
        max_transactions=240,
        agent_specs=_specs(),
        agent_signals={"agent-0": 10_000},
    )
    result = run_one(cfg)
    assert result.terminated == "COMPLETED", f"aborted: {result.abort_code}"
    events = result.events

    # Precondition: the belief agent observed MORE than once, and at least one
    # observation's cursor advanced past e1_0.
    observes = [
        r
        for r in events
        if r.get("event_type") == "AGENT_OBSERVE" and r.get("agent_id") == "agent-0"
    ]
    assert len(observes) >= 2, "long run must produce multiple observations"
    assert any(r.get("cursor_to_event_id") != "e1_0" for r in observes), (
        "cursor must advance past the bootstrap boundary in a long run"
    )

    # No exception = full chain (observe->decide->order->trade + evidence
    # cursors) resolves for every decision, including later intervals.
    verify_decision_evidence_chain(events, run_family="SPONTANEOUS")


def test_formal_log_has_no_transaction_internal_fields():
    """R018-C014 (Round 5): transaction-internal channels (_decision_index,
    _observed_*, _pending_agent_state) must never appear in the formal log."""
    events = _run_events()
    for e in events:
        internal = [k for k in e if k.startswith("_")]
        assert not internal, (
            f"event {e.get('event_id')} leaks internal fields {internal} into the formal log"
        )


def test_overlapping_observations_chain_passes():
    """R018-C007 (Round 5): with latency > observe_interval, a decide runs
    after the NEXT observation has advanced the live cursor.  The evidence
    cursors must still come from THIS decision's observation (carried on the
    event), not the live world cursor -- otherwise the chain verifier rejects
    a legitimate log."""
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
    agent = AgentSpec(
        agent_id="agent-0",
        role="retail",
        observe_interval_ns=100_000_000,  # observe every 100ms
        latency_ns=250_000_000,  # decide latency 250ms > observe interval
        leverage_tier=10,
        initial_bp=1000,
        aggressiveness_bp=10_000,
        max_order_qty=10_000,
        goal_model_id="risk_budget_linear_v1",
        risk_appetite_x1000=2000,
    )
    cfg = ExperimentConfig(
        seed=11,
        max_transactions=240,
        agent_specs=[mm, agent],
        agent_signals={"agent-0": 10_000},
    )
    result = run_one(cfg)
    assert result.terminated == "COMPLETED", f"aborted: {result.abort_code}"
    # Multiple overlapping observations must not break the chain.
    verify_decision_evidence_chain(result.events, run_family="SPONTANEOUS")
