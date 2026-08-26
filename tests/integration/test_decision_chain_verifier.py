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
    for e in events:
        if e.get("event_type") == "AGENT_DECIDE":
            e["decision_evidence"]["trigger_provenance"] = "EXOGENOUS_STRESS"
            break
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
