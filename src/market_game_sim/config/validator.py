"""T103: Config validation (ADR-001 §2, v0.1 spec).

Checks semantic constraints that the parser cannot enforce on its own:
  - ``tick_size × min_quantity`` must be an integer multiple of ``cash_unit``
    (ensures notional amounts are exact integers, no rounding on trades).
  - ``latency_ns ≥ 1`` for every agent (KR-006: events must advance time).
  - ``leverage_tier_distribution`` values sum to 10 000 per agent.
  - ``max_transactions ≥ 2`` (bootstrap snapshots are transactions 1 and 2).
  - No pre-configured initial resting orders (v0.1 initial book is empty).
  - ``grace_ns == 0`` (v0.1 mandatory; non-zero is rejected).
  - ``liquidation_latency_ns ≥ 1`` (class 1→0 jump must cross time).

Returns a list of error strings; an empty list means the config is valid.
"""

from __future__ import annotations

from market_game_sim.config.parser import ParsedConfig


class ConfigValidationError(Exception):
    """Raised when :func:`validate_config_or_raise` finds violations."""


_INITIAL_ORDER_FIELDS = frozenset(
    {
        "initial_orders",
        "initial_book",
        "resting_orders",
        "initial_resting_orders",
    }
)


def validate_config(config: ParsedConfig) -> list[str]:
    """Return a list of validation error strings (empty if valid)."""
    errors: list[str] = []

    _check_tick_min_quantity_cash_unit(config, errors)
    _check_agent_latencies(config, errors)
    _check_leverage_tier_distribution(config, errors)
    _check_max_transactions(config, errors)
    _check_no_initial_orders(config, errors)
    _check_grace_ns(config, errors)
    _check_liquidation_latency(config, errors)

    return errors


def validate_config_or_raise(config: ParsedConfig) -> None:
    """Validate, raising :class:`ConfigValidationError` on any violation."""
    errors = validate_config(config)
    if errors:
        raise ConfigValidationError(
            f"Config validation failed with {len(errors)} error(s):\n  " + "\n  ".join(errors)
        )


# --------------------------------------------------------------------------- #
# Individual checks
# --------------------------------------------------------------------------- #


def _check_tick_min_quantity_cash_unit(config: ParsedConfig, errors: list[str]) -> None:
    m = config.market
    product = m.tick_size * m.min_quantity
    if m.cash_unit == 0:
        errors.append("market.cash_unit is zero")
        return
    ratio = product / m.cash_unit
    if ratio != ratio.to_integral_value():
        errors.append(
            f"tick_size × min_quantity ({product}) is not an integer multiple "
            f"of cash_unit ({m.cash_unit}); ratio = {ratio}"
        )


def _check_agent_latencies(config: ParsedConfig, errors: list[str]) -> None:
    for i, agent in enumerate(config.agents):
        if agent.latency_ns < 1:
            errors.append(
                f"agents[{i}].latency_ns = {agent.latency_ns} < 1 (KR-006 requires latency_ns ≥ 1)"
            )


def _check_leverage_tier_distribution(config: ParsedConfig, errors: list[str]) -> None:
    for i, agent in enumerate(config.agents):
        total = sum(agent.leverage_tier_distribution.values())
        if total != 10_000:
            errors.append(f"agents[{i}].leverage_tier_distribution sums to {total}, not 10000")


def _check_max_transactions(config: ParsedConfig, errors: list[str]) -> None:
    mt = config.termination.max_transactions
    if mt < 2:
        errors.append(
            f"termination.max_transactions = {mt} < 2 "
            f"(bootstrap snapshots are transactions 1 and 2)"
        )


def _check_no_initial_orders(config: ParsedConfig, errors: list[str]) -> None:
    for field in _INITIAL_ORDER_FIELDS:
        if field in config.raw:
            errors.append(
                f"'{field}' is present but v0.1 requires an empty initial book "
                f"(pre-configured resting orders cannot be replayed by an "
                f"independent verifier)"
            )


def _check_grace_ns(config: ParsedConfig, errors: list[str]) -> None:
    if config.margin.grace_ns != 0:
        errors.append(
            f"margin.grace_ns = {config.margin.grace_ns} ≠ 0 (v0.1 mandates grace_ns == 0)"
        )


def _check_liquidation_latency(config: ParsedConfig, errors: list[str]) -> None:
    if config.margin.liquidation_latency_ns < 1:
        errors.append(
            f"margin.liquidation_latency_ns = "
            f"{config.margin.liquidation_latency_ns} < 1 "
            f"(class 1→0 jump must cross ≥ 1 ns)"
        )
