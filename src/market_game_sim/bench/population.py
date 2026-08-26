"""T701/T702: build an AgentSpec population from a parsed BENCH-001 config.

Draws are made once per agent at population-build time (not per-decision),
using the same seeded/keyed primitives as the rest of the codebase (KR-004:
each draw is keyed by ``(master_seed, agent_id, mechanism, decision_index,
draw_index)`` so it is reproducible independent of build/iteration order).
"""

from __future__ import annotations

from decimal import Decimal

from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.config.parser import ParsedConfig
from market_game_sim.ledger.account import initial_margin_bp_for_tier
from market_game_sim.rng.distributions import discrete_choice, lognormal_draw, uniform_range

_MARKET_MAKER_ROLE = "inventory_market_maker"


def build_population(config: ParsedConfig) -> list[AgentSpec]:
    """Expand each ``config.agents`` group's ``count`` into individual
    ``AgentSpec`` instances. ``leverage_tier`` is drawn per agent from the
    group's ``leverage_tier_distribution``; belief-agent ``aggressiveness_bp``
    is drawn per agent from a uniform [0, 10000] distribution (BENCH-001.yaml's
    ``aggressiveness: {distribution: uniform, low: 0.0, high: 1.0}``, scaled to
    bp). Market makers have no aggressiveness/leverage-choice distribution in
    the config beyond a single fixed tier, so they only draw ``leverage_tier``
    (present for schema uniformity; BENCH-001.yaml's market-maker group has a
    degenerate ``{"1": 10000}`` distribution).

    Five-factor belief weights are NOT drawn here: ``agent/handler.py::
    _belief_weights`` already draws them lazily per agent_id/master_seed on
    first decision (代理策略 §4.2/§10.1), so nothing to wire at population
    time.
    """
    specs: list[AgentSpec] = []
    seed = config.random.master_seed
    for group in config.agents:
        is_mm = group.role == _MARKET_MAKER_ROLE
        for i in range(group.count):
            agent_id = f"{group.role}-{i}"
            leverage_tier, _ = discrete_choice(
                group.leverage_tier_distribution, seed, agent_id, "bench_leverage_tier", 0, 0
            )
            initial_bp = initial_margin_bp_for_tier(leverage_tier)
            if is_mm:
                specs.append(
                    AgentSpec(
                        agent_id=agent_id,
                        role=group.role,
                        observe_interval_ns=group.observe_interval_ns,
                        latency_ns=group.latency_ns,
                        leverage_tier=leverage_tier,
                        initial_bp=initial_bp,
                        is_market_maker=True,
                        half_spread_ticks=group.half_spread_ticks or 0,
                        quote_size=group.quote_size_units or 0,
                        max_inventory=group.max_inventory_units or 0,
                        inventory_skew_k_bp=group.inventory_skew_k or 0,
                    )
                )
            else:
                agg, _ = uniform_range(
                    Decimal(0), Decimal(10_000), seed, agent_id, "bench_aggressiveness", 0, 0
                )
                # risk_appetite_x1000: drawn once per run via a NEW mechanism
                # string (KR-004: reusing noise_factor/belief_weights breaks
                # determinism).  Bounds [500, 20000] x1000, independent of tier.
                appetite, _ = uniform_range(
                    Decimal(500), Decimal(20_000), seed, agent_id, "risk_appetite", 0, 0
                )
                # EWMA half-life (代理策略 §2): lognormal per agent, in fills.
                half_life_dec, _ = lognormal_draw(
                    center=20,
                    dispersion=Decimal("0.5"),
                    master_seed=seed,
                    agent_id=agent_id,
                    mechanism="ewma_half_life",
                    decision_index=0,
                    draw_index=0,
                )
                half_life = max(int(half_life_dec), 1)
                specs.append(
                    AgentSpec(
                        agent_id=agent_id,
                        role=group.role,
                        observe_interval_ns=group.observe_interval_ns,
                        latency_ns=group.latency_ns,
                        leverage_tier=leverage_tier,
                        initial_bp=initial_bp,
                        aggressiveness_bp=int(agg),
                        max_order_qty=group.max_order_qty_units or 0,
                        goal_model_id=group.goal_model_id,
                        risk_appetite_x1000=int(appetite),
                        ewma_half_life_trades=half_life,
                    )
                )
    return specs
