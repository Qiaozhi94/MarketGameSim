"""T701-T703: end-to-end BENCH-001 runner tests.

Uses a small hand-built config (few agents, small ``max_transactions``) so
these run fast -- the real BENCH-001.yaml at its full scale is a genuine
performance benchmark, not a unit test fixture (benchmarks/README.md §4's
formal calibration is a separate, deliberate action; see
docs/reviews/2026-08-08j-... and the bench/calib.py module docstring).
"""

from __future__ import annotations

from market_game_sim.bench.runner import build_experiment_config, run_benchmark_config
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


def _small_config_dict(max_transactions: int = 200) -> dict:
    return {
        "benchmark_id": "TEST",
        "config_schema_version": 1,
        "event_schema_version": 2,
        "regime": "crypto_perp_free",
        "market": _MARKET,
        "margin": _MARGIN,
        "termination": {"max_transactions": max_transactions},
        "random": {"master_seed": 7},
        "agents": [
            {
                "role": "retail",
                "count": 4,
                "initial_wallet": "100000.0",
                "initial_position": "0",
                "observe_interval_ns": 1_000_000_000,
                "latency_ns": 50_000_000,
                "leverage_tier_distribution": {1: 6_000, 3: 3_000, 10: 1_000},
                "max_order_qty": "50.0",
            },
            {
                "role": "inventory_market_maker",
                "count": 1,
                "initial_wallet": "1000000.0",
                "initial_position": "0",
                "observe_interval_ns": 100_000_000,
                "latency_ns": 5_000_000,
                "leverage_tier_distribution": {1: 10_000},
                "max_inventory": "5000.0",
                "quote_size": "10.0",
                "half_spread": "0.05",
                "inventory_skew_k": "1.0",
            },
        ],
    }


class TestBuildExperimentConfig:
    def test_bridges_seed_and_termination(self):
        parsed = parse_config_dict(_small_config_dict(max_transactions=321))
        cfg = build_experiment_config(parsed)
        assert cfg.seed == 7
        assert cfg.max_transactions == 321

    def test_bridges_fees_and_margin(self):
        parsed = parse_config_dict(_small_config_dict())
        cfg = build_experiment_config(parsed)
        assert cfg.maker_bps == -1
        assert cfg.taker_bps == 5
        assert cfg.maint_bp == 500
        assert cfg.target_bp == 1000
        assert cfg.liquidation_latency_ns == 1_000_000

    def test_mult_matches_cash_unit_scaling_formula(self):
        parsed = parse_config_dict(_small_config_dict())
        cfg = build_experiment_config(parsed)
        # tick_size(0.01) * min_quantity(0.001) / cash_unit(1e-8) = 1000
        assert cfg.mult == 1000

    def test_population_size_matches_agent_group_counts(self):
        parsed = parse_config_dict(_small_config_dict())
        cfg = build_experiment_config(parsed)
        assert len(cfg.agent_specs) == 5  # 4 retail + 1 market maker


class TestRunBenchmarkConfig:
    def test_runs_to_completion_and_reports_positive_wall_time(self):
        parsed = parse_config_dict(_small_config_dict(max_transactions=200))
        result = run_benchmark_config(parsed)
        assert result.terminated == "COMPLETED"
        assert result.wall_seconds > 0
        assert result.max_transactions == 200

    def test_throughput_fields_are_positive(self):
        parsed = parse_config_dict(_small_config_dict(max_transactions=200))
        result = run_benchmark_config(parsed)
        assert result.transactions_per_second > 0
        assert result.event_record_count > 0
        assert result.event_records_per_second > 0

    def test_book_operation_count_is_nonzero_when_orders_are_placed(self):
        parsed = parse_config_dict(_small_config_dict(max_transactions=200))
        result = run_benchmark_config(parsed)
        assert result.book_operation_count > 0

    def test_small_run_fails_coverage_and_reports_which_dimensions(self):
        """A 200-transaction run with 5 agents is far too small to ever
        trigger a liquidation/chain/partial-fill -- confirms the coverage
        gate actually reports the shortfall rather than silently passing."""
        parsed = parse_config_dict(_small_config_dict(max_transactions=200))
        result = run_benchmark_config(parsed)
        assert result.coverage_valid is False
        assert any("min_liquidations" in f for f in result.coverage_failures)

    def test_as_dict_is_json_serializable_shape(self):
        import json

        parsed = parse_config_dict(_small_config_dict(max_transactions=200))
        result = run_benchmark_config(parsed)
        d = result.as_dict()
        json.dumps(d)  # must not raise -- proves no stray non-JSON types leaked in
        assert d["coverage_valid"] is result.coverage_valid
        assert set(d["coverage"]) == {
            "liquidations",
            "chained_liquidations",
            "partial_fills",
            "cancels",
            "one_sided_book_events",
        }
