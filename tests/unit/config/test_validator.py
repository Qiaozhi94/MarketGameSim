"""T103 tests: config validation (ADR-001 §2, v0.1 spec).

Validates semantic constraints that go beyond parsing:
  - tick_size × min_quantity is an integer multiple of cash_unit
  - latency_ns ≥ 1 (KR-006)
  - leverage_tier_distribution sums to 10 000
  - max_transactions ≥ 2
  - no pre-configured initial resting orders
  - grace_ns == 0 (v0.1 mandatory)
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from market_game_sim.config.parser import parse_config, parse_config_dict
from market_game_sim.config.validator import (
    validate_config,
)

BENCH_001_PATH = Path(__file__).resolve().parents[3] / "benchmarks" / "BENCH-001.yaml"


@pytest.fixture
def bench_config():
    return parse_config(BENCH_001_PATH)


@pytest.fixture
def bench_raw():
    return yaml.safe_load(BENCH_001_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# BENCH-001 passes validation
# --------------------------------------------------------------------------- #


class TestBench001Valid:
    def test_bench_001_passes_validation(self, bench_config):
        errors = validate_config(bench_config)
        assert errors == []


# --------------------------------------------------------------------------- #
# tick_size × min_quantity must be integer multiple of cash_unit
# --------------------------------------------------------------------------- #


class TestTickMinQuantityCashUnit:
    def test_valid_bench_001(self, bench_config):
        errors = validate_config(bench_config)
        assert not any("cash_unit" in e for e in errors)

    def test_violates_divisibility_via_cash_unit(self, bench_config):
        bad_market = dataclasses.replace(bench_config.market, cash_unit=Decimal("3e-8"))
        bad_config = dataclasses.replace(bench_config, market=bad_market)
        errors = validate_config(bad_config)
        assert any("cash_unit" in e or "integer" in e for e in errors)

    def test_violates_divisibility_via_tick_size(self, bench_config):
        bad_market = dataclasses.replace(bench_config.market, tick_size=Decimal("0.000015"))
        bad_config = dataclasses.replace(bench_config, market=bad_market)
        errors = validate_config(bad_config)
        assert any("cash_unit" in e or "integer" in e for e in errors)


# --------------------------------------------------------------------------- #
# latency_ns ≥ 1 (KR-006)
# --------------------------------------------------------------------------- #


class TestLatencyNs:
    def test_zero_latency_rejected(self, bench_raw):
        bench_raw["agents"][0]["latency_ns"] = 0
        cfg = parse_config_dict(bench_raw)
        errors = validate_config(cfg)
        assert any("latency" in e.lower() for e in errors)

    def test_negative_latency_rejected(self, bench_raw):
        bench_raw["agents"][0]["latency_ns"] = -1
        cfg = parse_config_dict(bench_raw)
        errors = validate_config(cfg)
        assert any("latency" in e.lower() for e in errors)

    def test_one_latency_accepted(self, bench_raw):
        bench_raw["agents"][0]["latency_ns"] = 1
        cfg = parse_config_dict(bench_raw)
        errors = validate_config(cfg)
        assert not any("latency" in e.lower() for e in errors)

    def test_all_agents_checked(self, bench_raw):
        bench_raw["agents"][1]["latency_ns"] = 0
        cfg = parse_config_dict(bench_raw)
        errors = validate_config(cfg)
        assert any("latency" in e.lower() for e in errors)


# --------------------------------------------------------------------------- #
# leverage_tier_distribution sums to 10000
# --------------------------------------------------------------------------- #


class TestLeverageTierDistribution:
    def test_valid_sum_10000(self, bench_config):
        errors = validate_config(bench_config)
        assert not any("leverage_tier" in e for e in errors)

    def test_sum_not_10000(self, bench_raw):
        bench_raw["agents"][0]["leverage_tier_distribution"]["1"] = 5000
        cfg = parse_config_dict(bench_raw)
        errors = validate_config(cfg)
        assert any("leverage_tier" in e or "10000" in e for e in errors)

    def test_all_agents_checked(self, bench_raw):
        bench_raw["agents"][1]["leverage_tier_distribution"]["1"] = 9999
        cfg = parse_config_dict(bench_raw)
        errors = validate_config(cfg)
        assert any("leverage_tier" in e or "10000" in e for e in errors)


# --------------------------------------------------------------------------- #
# max_transactions ≥ 2
# --------------------------------------------------------------------------- #


class TestMaxTransactions:
    def test_valid_large(self, bench_config):
        errors = validate_config(bench_config)
        assert not any("max_transactions" in e for e in errors)

    def test_rejects_one(self, bench_raw):
        bench_raw["termination"]["max_transactions"] = 1
        cfg = parse_config_dict(bench_raw)
        errors = validate_config(cfg)
        assert any("max_transactions" in e for e in errors)

    def test_rejects_zero(self, bench_raw):
        bench_raw["termination"]["max_transactions"] = 0
        cfg = parse_config_dict(bench_raw)
        errors = validate_config(cfg)
        assert any("max_transactions" in e for e in errors)

    def test_accepts_two(self, bench_raw):
        bench_raw["termination"]["max_transactions"] = 2
        cfg = parse_config_dict(bench_raw)
        errors = validate_config(cfg)
        assert not any("max_transactions" in e for e in errors)


# --------------------------------------------------------------------------- #
# Reject pre-configured initial resting orders
# --------------------------------------------------------------------------- #


class TestNoInitialOrders:
    def test_bench_001_has_no_initial_orders(self, bench_raw):
        assert "initial_orders" not in bench_raw
        assert "initial_book" not in bench_raw

    def test_rejects_initial_orders_field(self, bench_raw):
        bench_raw["initial_orders"] = []
        cfg = parse_config_dict(bench_raw)
        errors = validate_config(cfg)
        assert any("initial" in e.lower() and "order" in e.lower() for e in errors)

    def test_rejects_initial_book_field(self, bench_raw):
        bench_raw["initial_book"] = {"bids": [], "asks": []}
        cfg = parse_config_dict(bench_raw)
        errors = validate_config(cfg)
        assert any("initial" in e.lower() for e in errors)

    def test_rejects_resting_orders_field(self, bench_raw):
        bench_raw["resting_orders"] = []
        cfg = parse_config_dict(bench_raw)
        errors = validate_config(cfg)
        assert any("resting" in e.lower() or "initial" in e.lower() for e in errors)


# --------------------------------------------------------------------------- #
# grace_ns == 0 (v0.1 mandatory)
# --------------------------------------------------------------------------- #


class TestGraceNs:
    def test_zero_accepted(self, bench_config):
        errors = validate_config(bench_config)
        assert not any("grace" in e.lower() for e in errors)

    def test_nonzero_rejected(self, bench_raw):
        bench_raw["margin"]["grace_ns"] = 1000
        cfg = parse_config_dict(bench_raw)
        errors = validate_config(cfg)
        assert any("grace" in e.lower() for e in errors)

    def test_negative_rejected(self, bench_raw):
        bench_raw["margin"]["grace_ns"] = -1
        cfg = parse_config_dict(bench_raw)
        errors = validate_config(cfg)
        assert any("grace" in e.lower() for e in errors)


# --------------------------------------------------------------------------- #
# liquidation_latency_ns ≥ 1 (must cross time for class 1->0 jump)
# --------------------------------------------------------------------------- #


class TestLiquidationLatency:
    def test_zero_rejected(self, bench_raw):
        bench_raw["margin"]["liquidation_latency_ns"] = 0
        cfg = parse_config_dict(bench_raw)
        errors = validate_config(cfg)
        assert any("liquidation_latency" in e.lower() for e in errors)

    def test_one_accepted(self, bench_raw):
        bench_raw["margin"]["liquidation_latency_ns"] = 1
        cfg = parse_config_dict(bench_raw)
        errors = validate_config(cfg)
        assert not any("liquidation_latency" in e.lower() for e in errors)


# --------------------------------------------------------------------------- #
# Collects all errors (not fail-fast)
# --------------------------------------------------------------------------- #


class TestMultipleErrors:
    def test_reports_multiple_errors(self, bench_raw):
        bench_raw["termination"]["max_transactions"] = 1
        bench_raw["margin"]["grace_ns"] = 5
        bench_raw["agents"][0]["latency_ns"] = 0
        cfg = parse_config_dict(bench_raw)
        errors = validate_config(cfg)
        assert len(errors) >= 3
