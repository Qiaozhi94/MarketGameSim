"""T701/T702: build_population regression tests."""

from __future__ import annotations

from market_game_sim.bench.population import build_population
from market_game_sim.config.parser import parse_config_dict

_MARKET = {
    "symbol": "SYNTH",
    "tick_size": "0.01",
    "min_quantity": "0.001",
    "cash_unit": "1e-8",
    "initial_price": "100.00",
    "spread_fallback": "0.10",
    "fees": {"maker_bps": "-1.0", "taker_bps": "5.0"},
}
_MARGIN = {
    "maint_bp": 500,
    "target_bp": 1000,
    "grace_ns": 0,
    "liquidation_latency_ns": 1_000_000,
    "funding_rate_bp": 0,
    "funding_interval_ns": 28_800_000_000_000,
    "leverage_tiers": [1, 3, 10],
}


def _config_dict(agents: list[dict], master_seed: int = 42) -> dict:
    return {
        "benchmark_id": "TEST",
        "config_schema_version": 1,
        "event_schema_version": 2,
        "regime": "crypto_perp_free",
        "market": _MARKET,
        "margin": _MARGIN,
        "termination": {"max_transactions": 1000},
        "random": {"master_seed": master_seed},
        "agents": agents,
    }


def _retail_group(count: int, leverage_tier_distribution: dict) -> dict:
    return {
        "role": "retail",
        "count": count,
        "initial_wallet": "100000.0",
        "initial_position": "0",
        "observe_interval_ns": 1_000_000_000,
        "latency_ns": 50_000_000,
        "leverage_tier_distribution": leverage_tier_distribution,
        "max_order_qty": "50.0",
    }


def _mm_group(count: int) -> dict:
    return {
        "role": "inventory_market_maker",
        "count": count,
        "initial_wallet": "1000000.0",
        "initial_position": "0",
        "observe_interval_ns": 100_000_000,
        "latency_ns": 5_000_000,
        "leverage_tier_distribution": {"1": 10000},
        "max_inventory": "5000.0",
        "quote_size": "10.0",
        "half_spread": "0.05",
        "inventory_skew_k": "1.0",
    }


class TestPopulationSize:
    def test_expands_count_into_individual_specs(self):
        parsed = parse_config_dict(_config_dict([_retail_group(5, {1: 10_000})]))
        pop = build_population(parsed)
        assert len(pop) == 5
        assert len({p.agent_id for p in pop}) == 5

    def test_multiple_groups_all_expand(self):
        parsed = parse_config_dict(_config_dict([_retail_group(3, {1: 10_000}), _mm_group(2)]))
        pop = build_population(parsed)
        assert len(pop) == 5
        assert sum(1 for p in pop if p.is_market_maker) == 2
        assert sum(1 for p in pop if not p.is_market_maker) == 3


class TestLeverageTierDraw:
    def test_degenerate_distribution_all_agents_get_the_same_tier(self):
        parsed = parse_config_dict(_config_dict([_retail_group(20, {3: 10_000})]))
        pop = build_population(parsed)
        assert {p.leverage_tier for p in pop} == {3}

    def test_leverage_tiers_stay_within_distribution_keys(self):
        parsed = parse_config_dict(
            _config_dict([_retail_group(50, {1: 6_000, 3: 3_000, 10: 1_000})])
        )
        pop = build_population(parsed)
        assert set(p.leverage_tier for p in pop) <= {1, 3, 10}
        # a 50-agent draw from a non-degenerate distribution should not
        # collapse onto a single tier (negative case for the draw itself).
        assert len(set(p.leverage_tier for p in pop)) > 1

    def test_initial_bp_matches_leverage_tier(self):
        parsed = parse_config_dict(_config_dict([_retail_group(10, {3: 10_000})]))
        pop = build_population(parsed)
        assert all(p.initial_bp == 3334 for p in pop)  # ceil(10000/3)


class TestMarketMakerFields:
    def test_market_maker_gets_quoting_fields_from_group_config(self):
        parsed = parse_config_dict(_config_dict([_mm_group(1)]))
        [mm] = build_population(parsed)
        assert mm.is_market_maker is True
        assert mm.half_spread_ticks == 5  # 0.05 / tick_size(0.01)
        assert mm.quote_size == 10_000  # 10.0 / min_quantity(0.001)
        assert mm.max_inventory == 5_000_000  # 5000.0 / min_quantity
        assert mm.inventory_skew_k_bp == 1

    def test_market_maker_does_not_draw_aggressiveness(self):
        parsed = parse_config_dict(_config_dict([_mm_group(5)]))
        pop = build_population(parsed)
        assert all(p.aggressiveness_bp == 0 for p in pop)


class TestBeliefAgentFields:
    def test_retail_gets_aggressiveness_in_valid_bp_range(self):
        parsed = parse_config_dict(_config_dict([_retail_group(30, {1: 10_000})]))
        pop = build_population(parsed)
        assert all(0 <= p.aggressiveness_bp <= 10_000 for p in pop)

    def test_retail_aggressiveness_is_not_constant(self):
        """Negative case: a real uniform draw across 30 agents must not all
        land on the same value (would indicate the draw was never wired and
        a constant/default slipped through)."""
        parsed = parse_config_dict(_config_dict([_retail_group(30, {1: 10_000})]))
        pop = build_population(parsed)
        assert len({p.aggressiveness_bp for p in pop}) > 1

    def test_max_order_qty_copied_from_group(self):
        parsed = parse_config_dict(_config_dict([_retail_group(3, {1: 10_000})]))
        pop = build_population(parsed)
        assert all(p.max_order_qty == 50_000 for p in pop)  # 50.0 / min_quantity


class TestDeterminism:
    def test_same_seed_produces_identical_population(self):
        cfg_dict = _config_dict(
            [_retail_group(10, {1: 6_000, 3: 3_000, 10: 1_000}), _mm_group(2)], master_seed=7
        )
        pop_a = build_population(parse_config_dict(cfg_dict))
        pop_b = build_population(parse_config_dict(cfg_dict))
        assert pop_a == pop_b

    def test_different_seed_changes_the_draws(self):
        agents = [_retail_group(10, {1: 6_000, 3: 3_000, 10: 1_000})]
        pop_a = build_population(parse_config_dict(_config_dict(agents, master_seed=7)))
        pop_b = build_population(parse_config_dict(_config_dict(agents, master_seed=8)))
        assert [p.leverage_tier for p in pop_a] != [p.leverage_tier for p in pop_b] or [
            p.aggressiveness_bp for p in pop_a
        ] != [p.aggressiveness_bp for p in pop_b]
