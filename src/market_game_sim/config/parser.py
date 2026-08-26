"""T102: YAML config parser with strict Decimal->int conversion (ADR-001 §2).

Domain quantities in YAML must be quoted strings (e.g. ``tick_size: "0.01"``).
A bare float is rejected immediately -- no ``str()`` fallback, because that
would silently introduce a binary rounding step.

Integer fields (counts, nanoseconds, basis-point margins) carry no precision
risk and are read as plain ints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml


class ConfigParseError(Exception):
    """Raised when the YAML config violates ADR-001 §2 parsing rules."""


# --------------------------------------------------------------------------- #
# Parsed config structures
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class FeesConfig:
    maker_bps: int
    taker_bps: int


@dataclass(frozen=True)
class MarketConfig:
    symbol: str
    tick_size: Decimal
    min_quantity: Decimal
    cash_unit: Decimal
    initial_price_ticks: int
    spread_fallback_ticks: int
    fees: FeesConfig


@dataclass(frozen=True)
class MarginConfig:
    maint_bp: int
    target_bp: int
    grace_ns: int
    liquidation_latency_ns: int
    funding_rate_bp: int
    funding_interval_ns: int
    leverage_tiers: tuple[int, ...]


@dataclass(frozen=True)
class TerminationConfig:
    max_transactions: int


@dataclass(frozen=True)
class RandomConfig:
    master_seed: int


@dataclass(frozen=True)
class AgentConfig:
    role: str
    count: int
    initial_wallet_units: int
    initial_position_units: int
    observe_interval_ns: int
    latency_ns: int
    leverage_tier_distribution: dict[int, int]
    max_order_qty_units: int | None = None
    max_inventory_units: int | None = None
    quote_size_units: int | None = None
    half_spread_ticks: int | None = None
    inventory_skew_k: int | None = None
    goal_model_id: str | None = None


@dataclass(frozen=True)
class ParsedConfig:
    benchmark_id: str
    config_schema_version: int
    event_schema_version: int
    regime: str
    market: MarketConfig
    margin: MarginConfig
    termination: TerminationConfig
    random: RandomConfig
    agents: tuple[AgentConfig, ...]
    raw: dict[str, Any] = field(repr=False, compare=False)


# --------------------------------------------------------------------------- #
# Parsing primitives
# --------------------------------------------------------------------------- #


def _require_key(raw: dict, key: str, path: str) -> Any:
    if key not in raw:
        raise ConfigParseError(f"Missing required field '{path}'")
    return raw[key]


def _require_str(value: Any, path: str) -> str:
    """Domain quantity must arrive as a YAML string, not a float."""
    if isinstance(value, float):
        raise ConfigParseError(
            f"Domain quantity '{path}' is a float ({value!r}); "
            f"must be a quoted string per ADR-001 §2 -- no str() fallback"
        )
    if not isinstance(value, str):
        raise ConfigParseError(
            f"Domain quantity '{path}' must be a string, got {type(value).__name__}"
        )
    return value


def _to_decimal(value: Any, path: str) -> Decimal:
    s = _require_str(value, path)
    try:
        return Decimal(s)
    except InvalidOperation as exc:
        raise ConfigParseError(f"Cannot parse '{path}' value {s!r} as Decimal") from exc


def _to_int_via_decimal(value: Any, path: str) -> int:
    """Parse a string domain quantity to int via Decimal, rejecting non-integral."""
    d = _to_decimal(value, path)
    if d != d.to_integral_value():
        raise ConfigParseError(f"Value at '{path}' ({d}) does not resolve to integer")
    return int(d)


def _convert_units(value: Any, unit: Decimal, path: str) -> int:
    """Convert a string domain quantity to int via Decimal division.

    ``result = Decimal(value) / unit``; raises if not integral.
    """
    d = _to_decimal(value, path)
    if unit == 0:
        raise ConfigParseError(f"Unit for '{path}' is zero")
    quotient = d / unit
    if quotient != quotient.to_integral_value():
        raise ConfigParseError(
            f"Value at '{path}' ({d} / {unit} = {quotient}) does not resolve to integer"
        )
    return int(quotient)


def _require_int(value: Any, path: str) -> int:
    """Integer domain field (counts, ns, bp margins) -- read as plain int."""
    if isinstance(value, bool):
        raise ConfigParseError(f"Field '{path}' must be int, got bool")
    if isinstance(value, float):
        raise ConfigParseError(f"Field '{path}' is a float ({value!r}); must be an integer")
    if not isinstance(value, int):
        raise ConfigParseError(f"Field '{path}' must be int, got {type(value).__name__}")
    return value


# --------------------------------------------------------------------------- #
# Section parsers
# --------------------------------------------------------------------------- #


def _parse_market(raw: dict[str, Any]) -> MarketConfig:
    tick = _to_decimal(_require_key(raw, "tick_size", "market.tick_size"), "market.tick_size")
    min_qty = _to_decimal(
        _require_key(raw, "min_quantity", "market.min_quantity"), "market.min_quantity"
    )
    cash_unit = _to_decimal(_require_key(raw, "cash_unit", "market.cash_unit"), "market.cash_unit")
    initial_price_ticks = _convert_units(
        _require_key(raw, "initial_price", "market.initial_price"),
        tick,
        "market.initial_price",
    )
    spread_fallback_ticks = _convert_units(
        _require_key(raw, "spread_fallback", "market.spread_fallback"),
        tick,
        "market.spread_fallback",
    )
    fees_raw = _require_key(raw, "fees", "market.fees")
    if not isinstance(fees_raw, dict):
        raise ConfigParseError("market.fees must be a mapping")
    maker_bps = _to_int_via_decimal(
        _require_key(fees_raw, "maker_bps", "market.fees.maker_bps"),
        "market.fees.maker_bps",
    )
    taker_bps = _to_int_via_decimal(
        _require_key(fees_raw, "taker_bps", "market.fees.taker_bps"),
        "market.fees.taker_bps",
    )
    return MarketConfig(
        symbol=_require_key(raw, "symbol", "market.symbol"),
        tick_size=tick,
        min_quantity=min_qty,
        cash_unit=cash_unit,
        initial_price_ticks=initial_price_ticks,
        spread_fallback_ticks=spread_fallback_ticks,
        fees=FeesConfig(maker_bps=maker_bps, taker_bps=taker_bps),
    )


def _parse_margin(raw: dict[str, Any]) -> MarginConfig:
    return MarginConfig(
        maint_bp=_require_int(_require_key(raw, "maint_bp", "margin.maint_bp"), "margin.maint_bp"),
        target_bp=_require_int(
            _require_key(raw, "target_bp", "margin.target_bp"), "margin.target_bp"
        ),
        grace_ns=_require_int(_require_key(raw, "grace_ns", "margin.grace_ns"), "margin.grace_ns"),
        liquidation_latency_ns=_require_int(
            _require_key(raw, "liquidation_latency_ns", "margin.liquidation_latency_ns"),
            "margin.liquidation_latency_ns",
        ),
        funding_rate_bp=_require_int(
            _require_key(raw, "funding_rate_bp", "margin.funding_rate_bp"),
            "margin.funding_rate_bp",
        ),
        funding_interval_ns=_require_int(
            _require_key(raw, "funding_interval_ns", "margin.funding_interval_ns"),
            "margin.funding_interval_ns",
        ),
        leverage_tiers=tuple(
            _require_int(t, "margin.leverage_tiers[]")
            for t in _require_key(raw, "leverage_tiers", "margin.leverage_tiers")
        ),
    )


def _parse_termination(raw: dict[str, Any]) -> TerminationConfig:
    return TerminationConfig(
        max_transactions=_require_int(
            _require_key(raw, "max_transactions", "termination.max_transactions"),
            "termination.max_transactions",
        )
    )


def _parse_random(raw: dict[str, Any]) -> RandomConfig:
    return RandomConfig(
        master_seed=_require_int(
            _require_key(raw, "master_seed", "random.master_seed"),
            "random.master_seed",
        )
    )


def _parse_leverage_tier_distribution(raw: Any, path: str) -> dict[int, int]:
    if not isinstance(raw, dict):
        raise ConfigParseError(f"'{path}' must be a mapping")
    result: dict[int, int] = {}
    for k, v in raw.items():
        tier = int(k)
        result[tier] = _require_int(v, f"{path}['{k}']")
    return result


def _parse_agent(raw: dict[str, Any], market: MarketConfig) -> AgentConfig:
    role = _require_key(raw, "role", "agents[].role")
    count = _require_int(_require_key(raw, "count", "agents[].count"), "agents[].count")
    initial_wallet_units = _convert_units(
        _require_key(raw, "initial_wallet", "agents[].initial_wallet"),
        market.cash_unit,
        "agents[].initial_wallet",
    )
    initial_position_units = _convert_units(
        _require_key(raw, "initial_position", "agents[].initial_position"),
        market.min_quantity,
        "agents[].initial_position",
    )
    observe_interval_ns = _require_int(
        _require_key(raw, "observe_interval_ns", "agents[].observe_interval_ns"),
        "agents[].observe_interval_ns",
    )
    latency_ns = _require_int(
        _require_key(raw, "latency_ns", "agents[].latency_ns"),
        "agents[].latency_ns",
    )
    ltd = _parse_leverage_tier_distribution(
        _require_key(raw, "leverage_tier_distribution", "agents[].leverage_tier_distribution"),
        "agents[].leverage_tier_distribution",
    )

    max_order_qty_units: int | None = None
    max_inventory_units: int | None = None
    quote_size_units: int | None = None
    half_spread_ticks: int | None = None
    inventory_skew_k: int | None = None

    if "max_order_qty" in raw:
        max_order_qty_units = _convert_units(
            raw["max_order_qty"], market.min_quantity, "agents[].max_order_qty"
        )
    if "max_inventory" in raw:
        max_inventory_units = _convert_units(
            raw["max_inventory"], market.min_quantity, "agents[].max_inventory"
        )
    if "quote_size" in raw:
        quote_size_units = _convert_units(
            raw["quote_size"], market.min_quantity, "agents[].quote_size"
        )
    if "half_spread" in raw:
        half_spread_ticks = _convert_units(
            raw["half_spread"], market.tick_size, "agents[].half_spread"
        )
    if "inventory_skew_k" in raw:
        inventory_skew_k = _to_int_via_decimal(raw["inventory_skew_k"], "agents[].inventory_skew_k")

    goal_model_id: str | None = raw.get("goal_model_id")

    return AgentConfig(
        role=role,
        count=count,
        initial_wallet_units=initial_wallet_units,
        initial_position_units=initial_position_units,
        observe_interval_ns=observe_interval_ns,
        latency_ns=latency_ns,
        leverage_tier_distribution=ltd,
        max_order_qty_units=max_order_qty_units,
        max_inventory_units=max_inventory_units,
        quote_size_units=quote_size_units,
        half_spread_ticks=half_spread_ticks,
        inventory_skew_k=inventory_skew_k,
        goal_model_id=goal_model_id,
    )


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def parse_config_dict(raw: dict[str, Any]) -> ParsedConfig:
    """Build a :class:`ParsedConfig` from a raw YAML mapping."""
    if not isinstance(raw, dict):
        raise ConfigParseError("Top-level YAML must be a mapping")

    market = _parse_market(_require_key(raw, "market", "market"))
    margin = _parse_margin(_require_key(raw, "margin", "margin"))
    termination = _parse_termination(_require_key(raw, "termination", "termination"))
    random_cfg = _parse_random(_require_key(raw, "random", "random"))

    agents_raw = _require_key(raw, "agents", "agents")
    if not isinstance(agents_raw, list):
        raise ConfigParseError("'agents' must be a list")
    agents = tuple(_parse_agent(a, market) for a in agents_raw)

    return ParsedConfig(
        benchmark_id=_require_key(raw, "benchmark_id", "benchmark_id"),
        config_schema_version=_require_int(
            _require_key(raw, "config_schema_version", "config_schema_version"),
            "config_schema_version",
        ),
        event_schema_version=_require_int(
            _require_key(raw, "event_schema_version", "event_schema_version"),
            "event_schema_version",
        ),
        regime=_require_key(raw, "regime", "regime"),
        market=market,
        margin=margin,
        termination=termination,
        random=random_cfg,
        agents=agents,
        raw=raw,
    )


def parse_config(path: str | Path) -> ParsedConfig:
    """Read a YAML config file and return a :class:`ParsedConfig`."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    raw = yaml.safe_load(text)
    if raw is None:
        raise ConfigParseError(f"Config file {p} is empty")
    return parse_config_dict(raw)
