"""§1.5 regression: Dirichlet-drawn belief weights wired into production path.

Round 3-9 of the 0.1.2 implementation review found ``_compute_belief_signal``
(agent/handler.py) always used a hardcoded ``[Decimal("0.2")] * 5`` uniform
weight vector instead of drawing per-agent weights from
``rng.distributions.dirichlet_draw`` (代理策略 §4.2/§10.3.2), even though
``dirichlet_draw`` itself was already implemented and unit-tested -- an
"orphan module" never called from the production decision path.
"""

from __future__ import annotations

from decimal import Decimal

from market_game_sim.agent.factors import belief_signal
from market_game_sim.agent.factors import book as book_factor
from market_game_sim.agent.factors import herding as herding_factor
from market_game_sim.agent.factors import momentum as momentum_factor
from market_game_sim.agent.factors import noise as noise_factor
from market_game_sim.agent.factors import reversion as reversion_factor
from market_game_sim.agent.handler import _belief_weights, _compute_belief_signal
from market_game_sim.agent.observation import InformationSet
from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.rng.distributions import standard_normal


def _spec(agent_id: str) -> AgentSpec:
    return AgentSpec(
        agent_id=agent_id,
        role="retail",
        observe_interval_ns=1_000_000_000,
        latency_ns=50_000_000,
        leverage_tier=1,
    )


def test_belief_weights_matches_dirichlet_golden_vector():
    """代理策略 §10.3.4 golden vector: master_seed=42, agent-000,
    alpha=[1.0,1.0,0.8,0.8,1.5] -- proves handler.py wires the exact
    alpha/mechanism/decision_index the contract specifies, not just *some*
    Dirichlet draw."""
    world = {"experiment_seed": 42}
    weights = _belief_weights(_spec("agent-000"), world)
    expected = [
        Decimal("0.1263946241600740412702771089"),
        Decimal("0.2512845414401946144867249532"),
        Decimal("0.2279915631952186024773230701"),
        Decimal("0.01823517847453035830910800003"),
        Decimal("0.3760940927299823834565668676"),
    ]
    for i, (got, exp) in enumerate(zip(weights, expected, strict=True)):
        assert abs(got - exp) < Decimal("1e-25"), f"component {i}: {got} != {exp}"


def test_belief_weights_not_uniform():
    """Negative case: the fixed bug always returned exactly [0.2]*5;
    a real Dirichlet(1.0,1.0,0.8,0.8,1.5) draw must not coincide with it."""
    world = {"experiment_seed": 42}
    weights = _belief_weights(_spec("agent-000"), world)
    assert weights != [Decimal("0.2")] * 5


def test_belief_weights_differ_across_agents():
    """Different agents must draw different weight vectors (heterogeneity
    is the whole point of per-agent Dirichlet weights)."""
    world = {"experiment_seed": 42}
    w1 = _belief_weights(_spec("agent-a"), world)
    w2 = _belief_weights(_spec("agent-b"), world)
    assert w1 != w2


def test_belief_weights_fixed_for_run_via_cache():
    """代理策略 §4.2: weights are drawn once at position-opening and stay
    fixed for the rest of the run -- calling twice with the same world
    (same cache dict) must return the identical cached vector, not redraw."""
    world = {"experiment_seed": 42}
    w1 = _belief_weights(_spec("agent-000"), world)
    w2 = _belief_weights(_spec("agent-000"), world)
    assert w1 is w2


def test_compute_belief_signal_wires_golden_dirichlet_weights_end_to_end():
    """End-to-end: with no static agent_signals override, _compute_belief_
    signal's result must equal belief_signal() applied to the exact golden
    Dirichlet weight vector and the same five factors computed directly --
    pins down that the production path really uses dirichlet_draw's output,
    not just "some" weight vector that happens to differ from uniform."""
    iset = {
        "best_bid": 9990,
        "best_ask": 10010,
        "bid_depth_k": 5,
        "ask_depth_k": 0,
        "last_ticks": 10050,
        "initial_price_ticks": 10000,
    }
    world = {"experiment_seed": 42, "agent_signals": {}, "trade_history": {}}
    spec = _spec("agent-000")

    actual = _compute_belief_signal(spec, iset, world, decision_index=0)

    golden_weights = [
        Decimal("0.1263946241600740412702771089"),
        Decimal("0.2512845414401946144867249532"),
        Decimal("0.2279915631952186024773230701"),
        Decimal("0.01823517847453035830910800003"),
        Decimal("0.3760940927299823834565668676"),
    ]
    info = InformationSet(
        agent_id="agent-000",
        observed_at=0,
        best_bid=9990,
        best_ask=10010,
        bid_depth_k=5,
        ask_depth_k=0,
        last_ticks=10050,
    )
    z, _ = standard_normal(42, "agent-000", "noise_factor", 0, 0)
    expected = belief_signal(
        golden_weights,
        [
            momentum_factor([], lookback=5),
            reversion_factor(10050, 10000),
            herding_factor([]),
            book_factor(info),
            noise_factor(z),
        ],
    )
    assert actual == expected
