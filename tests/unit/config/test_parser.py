"""T102 tests: YAML config parser with strict Decimal→int conversion.

ADR-001 §2: domain quantities in YAML must be quoted strings.  A bare float
(e.g. ``tick_size: 0.01``) is rejected immediately -- no ``str()`` fallback.
"""

from __future__ import annotations

import textwrap
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from market_game_sim.config.parser import (
    ConfigParseError,
    parse_config,
    parse_config_dict,
)

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


BENCH_001_PATH = Path(__file__).resolve().parents[3] / "benchmarks" / "BENCH-001.yaml"


@pytest.fixture
def bench_config():
    return parse_config(BENCH_001_PATH)


def _minimal_yaml(**overrides) -> str:
    """A minimal valid YAML with all required domain fields as strings."""
    market = {
        "symbol": "SYNTH-CRYPTO",
        "tick_size": '"0.01"',
        "min_quantity": '"0.001"',
        "cash_unit": '"1e-8"',
        "initial_price": '"100.00"',
        "spread_fallback": '"0.10"',
        "fees": {"maker_bps": '"-1.0"', "taker_bps": '"5.0"'},
    }
    margin = {
        "maint_bp": "500",
        "target_bp": "1000",
        "grace_ns": "0",
        "liquidation_latency_ns": "1000000",
        "funding_rate_bp": "0",
        "funding_interval_ns": "28800000000000",
        "leverage_tiers": "[1, 3, 10]",
    }
    termination = {"max_transactions": "100000"}
    random_ = {"master_seed": "20260731"}
    agents = [
        {
            "role": "retail",
            "count": "1",
            "initial_wallet": '"100000.0"',
            "initial_position": '"0"',
            "observe_interval_ns": "1000000000",
            "latency_ns": "50000000",
            "leverage_tier_distribution": '{"1": 10000}',
            "max_order_qty": '"50.0"',
        }
    ]

    sections = {
        "benchmark_id": "TEST-001",
        "config_schema_version": "1",
        "event_schema_version": "3",
        "regime": "crypto_perp_free",
        "market": market,
        "margin": margin,
        "termination": termination,
        "random": random_,
        "agents": agents,
    }
    sections.update(overrides)
    return _dict_to_yaml(sections)


def _dict_to_yaml(d, indent=0) -> str:
    """Serialize a nested dict/list/scalar to a minimal YAML string."""
    lines = []
    pad = "  " * indent
    for k, v in d.items():
        if isinstance(v, dict):
            lines.append(f"{pad}{k}:")
            lines.append(_dict_to_yaml(v, indent + 1))
        elif isinstance(v, list):
            lines.append(f"{pad}{k}:")
            for item in v:
                if isinstance(item, dict):
                    lines.append(f"{pad}-")
                    lines.append(_dict_to_yaml(item, indent + 1))
                else:
                    lines.append(f"{pad}- {item}")
        else:
            lines.append(f"{pad}{k}: {v}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# BENCH-001 parsing
# --------------------------------------------------------------------------- #


class TestBench001Parsing:
    def test_parses_without_error(self, bench_config):
        assert bench_config is not None

    def test_market_unit_decimals(self, bench_config):
        m = bench_config.market
        assert m.tick_size == Decimal("0.01")
        assert m.min_quantity == Decimal("0.001")
        assert m.cash_unit == Decimal("1e-8")

    def test_initial_price_in_ticks(self, bench_config):
        assert bench_config.market.initial_price_ticks == 10_000

    def test_spread_fallback_in_ticks(self, bench_config):
        assert bench_config.market.spread_fallback_ticks == 10

    def test_fees_as_int_bps(self, bench_config):
        assert bench_config.market.fees.maker_bps == -1
        assert bench_config.market.fees.taker_bps == 5

    def test_margin_fields(self, bench_config):
        mg = bench_config.margin
        assert mg.maint_bp == 500
        assert mg.target_bp == 1000
        assert mg.grace_ns == 0
        assert mg.liquidation_latency_ns == 1_000_000
        assert mg.funding_rate_bp == 0
        assert mg.leverage_tiers == (1, 3, 10)

    def test_termination(self, bench_config):
        assert bench_config.termination.max_transactions == 100_000

    def test_retail_agent_wallet_in_cash_units(self, bench_config):
        retail = bench_config.agents[0]
        assert retail.initial_wallet_units == 10_000_000_000_000

    def test_retail_agent_position_in_qty_units(self, bench_config):
        retail = bench_config.agents[0]
        assert retail.initial_position_units == 0

    def test_retail_latency_ns(self, bench_config):
        retail = bench_config.agents[0]
        assert retail.latency_ns == 50_000_000

    def test_retail_leverage_distribution(self, bench_config):
        retail = bench_config.agents[0]
        assert retail.leverage_tier_distribution == {1: 6000, 3: 3000, 10: 1000}

    def test_market_maker_wallet(self, bench_config):
        mm = bench_config.agents[1]
        assert mm.initial_wallet_units == 100_000_000_000_000

    def test_market_maker_quote_size(self, bench_config):
        mm = bench_config.agents[1]
        assert mm.quote_size_units == 10_000

    def test_market_maker_half_spread(self, bench_config):
        mm = bench_config.agents[1]
        assert mm.half_spread_ticks == 5

    def test_market_maker_max_inventory(self, bench_config):
        mm = bench_config.agents[1]
        assert mm.max_inventory_units == 5_000_000

    def test_event_schema_version(self, bench_config):
        assert bench_config.event_schema_version == 3


# --------------------------------------------------------------------------- #
# Float rejection (ADR-001 §2 - no str() fallback)
# --------------------------------------------------------------------------- #


class TestFloatRejection:
    _BASE_YAML = textwrap.dedent("""
    benchmark_id: T
    config_schema_version: 1
    event_schema_version: 3
    regime: crypto_perp_free
    market:
      symbol: S
      tick_size: "0.01"
      min_quantity: "0.001"
      cash_unit: "1e-8"
      initial_price: "100.00"
      spread_fallback: "0.10"
      fees:
        maker_bps: "-1.0"
        taker_bps: "5.0"
    margin:
      maint_bp: 500
      target_bp: 1000
      grace_ns: 0
      liquidation_latency_ns: 1000000
      funding_rate_bp: 0
      funding_interval_ns: 28800000000000
      leverage_tiers: [1, 3, 10]
    termination:
      max_transactions: 100
    random:
      master_seed: 1
    agents:
      - role: retail
        count: 1
        initial_wallet: "100.0"
        initial_position: "0"
        observe_interval_ns: 1000000000
        latency_ns: 50000000
        leverage_tier_distribution: {"1": 10000}
    """)

    def _load(self, yaml_text):
        import yaml

        return parse_config_dict(yaml.safe_load(yaml_text))

    def test_rejects_float_tick_size(self):
        with pytest.raises(ConfigParseError, match="float"):
            self._load(self._BASE_YAML.replace('tick_size: "0.01"', "tick_size: 0.01"))

    def test_rejects_float_min_quantity(self):
        with pytest.raises(ConfigParseError, match="float"):
            self._load(self._BASE_YAML.replace('min_quantity: "0.001"', "min_quantity: 0.001"))

    def test_rejects_float_cash_unit(self):
        with pytest.raises(ConfigParseError, match="float"):
            self._load(self._BASE_YAML.replace('cash_unit: "1e-8"', "cash_unit: 0.00000001"))

    def test_rejects_float_initial_price(self):
        with pytest.raises(ConfigParseError, match="float"):
            self._load(self._BASE_YAML.replace('initial_price: "100.00"', "initial_price: 100.00"))

    def test_rejects_float_maker_bps(self):
        with pytest.raises(ConfigParseError, match="float"):
            self._load(self._BASE_YAML.replace('maker_bps: "-1.0"', "maker_bps: -1.0"))

    def test_rejects_float_taker_bps(self):
        with pytest.raises(ConfigParseError, match="float"):
            self._load(self._BASE_YAML.replace('taker_bps: "5.0"', "taker_bps: 5.0"))

    def test_rejects_float_initial_wallet(self):
        with pytest.raises(ConfigParseError, match="float"):
            self._load(self._BASE_YAML.replace('initial_wallet: "100.0"', "initial_wallet: 100.0"))

    def test_rejects_float_spread_fallback(self):
        with pytest.raises(ConfigParseError, match="float"):
            self._load(self._BASE_YAML.replace('spread_fallback: "0.10"', "spread_fallback: 0.10"))

    def test_rejects_float_initial_position(self):
        with pytest.raises(ConfigParseError, match="float"):
            self._load(self._BASE_YAML.replace('initial_position: "0"', "initial_position: 0.0"))


# --------------------------------------------------------------------------- #
# Unit conversion correctness
# --------------------------------------------------------------------------- #


class TestUnitConversion:
    def test_price_conversion(self):
        yaml_text = _minimal_yaml()
        yaml_text = yaml_text.replace('initial_price: "100.00"', 'initial_price: "100.00"')
        cfg = parse_config_dict(yaml.safe_load(yaml_text))
        assert cfg.market.initial_price_ticks == 10_000

    def test_price_conversion_non_integer_rejected(self):
        """tick_size=0.01, initial_price=100.005 -> 10000.5 ticks -> not integer."""
        yaml_text = _minimal_yaml()
        yaml_text = yaml_text.replace('initial_price: "100.00"', 'initial_price: "100.005"')
        with pytest.raises(ConfigParseError, match="integer"):
            parse_config_dict(yaml.safe_load(yaml_text))

    def test_quantity_conversion(self):
        yaml_text = _minimal_yaml()
        cfg = parse_config_dict(yaml.safe_load(yaml_text))
        assert cfg.agents[0].max_order_qty_units == 50_000

    def test_cash_conversion(self):
        yaml_text = _minimal_yaml()
        cfg = parse_config_dict(yaml.safe_load(yaml_text))
        assert cfg.agents[0].initial_wallet_units == 10_000_000_000_000

    def test_cash_conversion_non_integer_rejected(self):
        """cash_unit=1e-8, initial_wallet=100.0000000005 -> not integer."""
        yaml_text = _minimal_yaml()
        yaml_text = yaml_text.replace(
            'initial_wallet: "100000.0"', 'initial_wallet: "100.0000000005"'
        )
        with pytest.raises(ConfigParseError, match="integer"):
            parse_config_dict(yaml.safe_load(yaml_text))

    def test_bps_conversion_strips_decimal(self):
        yaml_text = _minimal_yaml()
        cfg = parse_config_dict(yaml.safe_load(yaml_text))
        assert cfg.market.fees.maker_bps == -1
        assert cfg.market.fees.taker_bps == 5

    def test_bps_non_integer_rejected(self):
        yaml_text = _minimal_yaml()
        yaml_text = yaml_text.replace('taker_bps: "5.0"', 'taker_bps: "5.5"')
        with pytest.raises(ConfigParseError, match="integer"):
            parse_config_dict(yaml.safe_load(yaml_text))


# --------------------------------------------------------------------------- #
# Scientific notation in strings
# --------------------------------------------------------------------------- #


class TestScientificNotation:
    def test_cash_unit_scientific_notation(self):
        yaml_text = _minimal_yaml()
        cfg = parse_config_dict(yaml.safe_load(yaml_text))
        assert cfg.market.cash_unit == Decimal("1e-8")


# --------------------------------------------------------------------------- #
# Integer fields stay as ints (not strings)
# --------------------------------------------------------------------------- #


class TestIntegerFieldParsing:
    def test_maint_bp_is_int(self):
        yaml_text = _minimal_yaml()
        cfg = parse_config_dict(yaml.safe_load(yaml_text))
        assert isinstance(cfg.margin.maint_bp, int)
        assert cfg.margin.maint_bp == 500

    def test_target_bp_is_int(self):
        yaml_text = _minimal_yaml()
        cfg = parse_config_dict(yaml.safe_load(yaml_text))
        assert isinstance(cfg.margin.target_bp, int)
        assert cfg.margin.target_bp == 1000

    def test_grace_ns_is_int(self):
        yaml_text = _minimal_yaml()
        cfg = parse_config_dict(yaml.safe_load(yaml_text))
        assert isinstance(cfg.margin.grace_ns, int)
        assert cfg.margin.grace_ns == 0

    def test_max_transactions_is_int(self):
        yaml_text = _minimal_yaml()
        cfg = parse_config_dict(yaml.safe_load(yaml_text))
        assert isinstance(cfg.termination.max_transactions, int)

    def test_latency_ns_is_int(self):
        yaml_text = _minimal_yaml()
        cfg = parse_config_dict(yaml.safe_load(yaml_text))
        assert isinstance(cfg.agents[0].latency_ns, int)

    def test_leverage_tiers_are_ints(self):
        yaml_text = _minimal_yaml()
        cfg = parse_config_dict(yaml.safe_load(yaml_text))
        assert all(isinstance(t, int) for t in cfg.margin.leverage_tiers)

    def test_leverage_tier_distribution_values_are_ints(self):
        yaml_text = _minimal_yaml()
        cfg = parse_config_dict(yaml.safe_load(yaml_text))
        for v in cfg.agents[0].leverage_tier_distribution.values():
            assert isinstance(v, int)


# --------------------------------------------------------------------------- #
# Missing required fields
# --------------------------------------------------------------------------- #


class TestMissingFields:
    def test_missing_market_raises(self):
        with pytest.raises(ConfigParseError):
            parse_config_dict({"termination": {"max_transactions": 10}})

    def test_missing_tick_size_raises(self):
        yaml_text = _minimal_yaml()
        yaml_text = yaml_text.replace('  tick_size: "0.01"\n', "")
        with pytest.raises(ConfigParseError, match="tick_size"):
            parse_config_dict(yaml.safe_load(yaml_text))
