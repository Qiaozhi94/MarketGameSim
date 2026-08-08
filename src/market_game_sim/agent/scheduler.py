"""T406, T404, T405: Agent scheduler (观察/决策调度).

Each agent has an ``observe_interval_ns`` (decide cadence) and a
``latency_ns`` (decide -> order arrival delay).  The scheduler enqueues
``AGENT_OBSERVE`` for each agent, then ``AGENT_DECIDE`` after observe.
``AGENT_DECIDE`` is a class 4 queue event; ``AGENT_OBSERVE`` is class 3.
The order ``OBSERVE -> DECIDE`` is the only legitimate class 3 -> 4 jump
(事件 Schema §1.2).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AgentSpec:
    """One agent's static configuration for scheduling."""

    agent_id: str
    role: str
    observe_interval_ns: int
    latency_ns: int
    first_observe_at_ns: int = 0
    leverage_tier: int = 1
    initial_bp: int = 10000
    aggressiveness_bp: int = 0
    max_order_qty: int = 0
    is_market_maker: bool = False
    half_spread_ticks: int = 0
    quote_size: int = 0
    max_inventory: int = 0
    inventory_skew_k_bp: int = 0


def initial_observe_events(agents: list[AgentSpec]) -> list[dict]:
    """Build the first AGENT_OBSERVE event for each agent.

    All events are at timestamp 0 -- they get enqueued in class 3
    (after bootstrap snapshots) and execute in their own transactions.
    """
    out: list[dict] = []
    for spec in agents:
        out.append(
            {
                "event_type": "AGENT_OBSERVE",
                "timestamp": spec.first_observe_at_ns,
                "agent_id": spec.agent_id,
                "observed_at": spec.first_observe_at_ns,
                "market_data_event_id": "e1_0",  # bootstrap ACCOUNT snapshot's r0
                "information_set": {},
            }
        )
    return out


def next_observe_events(
    agents: list[AgentSpec],
    current_observe_ts: int,
    last_md_event_id: str,
) -> list[dict]:
    """Build the next AGENT_OBSERVE batch for each agent.

    Each agent's next observation is at ``current_observe_ts + observe_interval_ns``.
    """
    out: list[dict] = []
    for spec in agents:
        next_ts = current_observe_ts + spec.observe_interval_ns
        out.append(
            {
                "event_type": "AGENT_OBSERVE",
                "timestamp": next_ts,
                "agent_id": spec.agent_id,
                "observed_at": next_ts,
                "market_data_event_id": last_md_event_id,
                "information_set": {},
            }
        )
    return out


def decide_event(
    spec: AgentSpec,
    observe_ts: int,
    observe_event_id: str,
    decision_index: int,
) -> dict:
    """Build an AGENT_DECIDE event delayed by latency_ns after observation."""
    return {
        "event_type": "AGENT_DECIDE",
        "timestamp": observe_ts + spec.latency_ns,
        "agent_id": spec.agent_id,
        "observation_event_id": observe_event_id,
        "rule_id": "default",
        "intents": [],
        "internal_state": {},
        "_decision_index": decision_index,
    }
