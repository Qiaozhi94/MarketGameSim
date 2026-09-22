"""0.4.1 T960 (FR-501 / AC-501): the cold-start deadlock, locked as a red baseline.

Mechanism (ADR-011 背景): a goal-driven agent stays in EWMA warmup until it has
seen ``2 * ewma_half_life_trades`` public trades (``goal.py::_warmup``); while in
warmup its target position is 0, so it never orders.  The warmup samples come
from the public trade tape, and in a market whose only other participant is a
market maker nobody crosses the spread -- so the tape stays empty and warmup
never ends.

These tests pin both halves of that claim:

- with warmup on, a market with live two-sided quotes still produces zero
  trades and every goal-agent decision is ``EWMA_WARMUP`` with no intents;
- the *same* market with warmup off trades -- proving the deadlock is caused by
  warmup, not by the market set-up.  (Turning warmup off is the side-effect
  bypass FR-501 forbids as a fix; here it is only the control arm.)

The strict xfail is the gap T963 closes: a zero-trade market must produce a
first goal-agent order.  When T963 lands the anchor, rewrite that test to enable
it and drop the xfail; the "no anchor => deadlock" test stays as AC-501's
negative side.
"""

from __future__ import annotations

from collections import Counter

import pytest

from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.experiment.config import ExperimentConfig
from market_game_sim.experiment.runner import RunResult, run_one

GOAL_AGENTS = ("agent-0", "agent-1", "agent-2")
WARMUP_HALF_LIFE_TRADES = 5
MAX_TRANSACTIONS = 600


def _market_maker() -> AgentSpec:
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


def _goal_agent(agent_id: str, half_life_trades: int) -> AgentSpec:
    return AgentSpec(
        agent_id=agent_id,
        role="retail",
        observe_interval_ns=1_000_000_000,
        latency_ns=50_000_000,
        leverage_tier=10,
        initial_bp=1000,
        aggressiveness_bp=10_000,
        max_order_qty=10_000,
        goal_model_id="risk_budget_linear_v1",
        risk_appetite_x1000=2000,
        ewma_half_life_trades=half_life_trades,
    )


def _run(seed: int, half_life_trades: int) -> RunResult:
    # Opposite signals on purpose: buyers and sellers both exist, so a
    # zero-trade outcome cannot be blamed on everyone wanting the same side.
    signals = {aid: (10_000 if i % 2 == 0 else -10_000) for i, aid in enumerate(GOAL_AGENTS)}
    return run_one(
        ExperimentConfig(
            seed=seed,
            max_transactions=MAX_TRANSACTIONS,
            agent_specs=[_market_maker()]
            + [_goal_agent(aid, half_life_trades) for aid in GOAL_AGENTS],
            agent_signals=signals,
        )
    )


def _goal_orders(result: RunResult) -> Counter[str]:
    return Counter(
        e["agent_id"]
        for e in result.events
        if e["event_type"] == "ORDER_ARRIVAL" and e["agent_id"] in GOAL_AGENTS
    )


def _goal_decisions(result: RunResult) -> list[dict]:
    return [
        e
        for e in result.events
        if e["event_type"] == "AGENT_DECIDE" and e["agent_id"] in GOAL_AGENTS
    ]


def _trades(result: RunResult) -> int:
    return sum(1 for e in result.events if e["event_type"] == "TRADE_SETTLE")


@pytest.mark.parametrize("seed", [7, 11])
def test_warmup_deadlocks_a_quoted_market_with_zero_trades(seed: int) -> None:
    result = _run(seed, WARMUP_HALF_LIFE_TRADES)
    assert result.terminated == "COMPLETED"

    # The market maker really is quoting both sides -- the book is not empty.
    publishes = [e for e in result.events if e["event_type"] == "MARKET_DATA_PUBLISH"]
    assert any(e["best_bid"] is not None and e["best_ask"] is not None for e in publishes)

    assert _trades(result) == 0
    assert _goal_orders(result) == Counter()

    decisions = _goal_decisions(result)
    assert {d["agent_id"] for d in decisions} == set(GOAL_AGENTS)
    for d in decisions:
        assert d["internal_state"]["constraint_reason"] == "EWMA_WARMUP", d["event_id"]
        assert d["internal_state"]["desired_position_units"] == 0, d["event_id"]
        assert d["intents"] == [], d["event_id"]


@pytest.mark.parametrize("seed", [7, 11])
def test_same_market_trades_once_warmup_is_off(seed: int) -> None:
    result = _run(seed, half_life_trades=0)
    assert result.terminated == "COMPLETED"
    assert _trades(result) > 0
    assert set(_goal_orders(result)) == set(GOAL_AGENTS)
    assert all(
        d["internal_state"]["constraint_reason"] != "EWMA_WARMUP" for d in _goal_decisions(result)
    )


@pytest.mark.xfail(
    strict=True,
    reason="T963 冷启动锚尚未实现（FR-501 / AC-501）：零成交市场中目标代理产生不了首笔委托",
)
def test_zero_trade_market_produces_a_first_goal_agent_order() -> None:
    result = _run(7, WARMUP_HALF_LIFE_TRADES)
    assert _goal_orders(result)
