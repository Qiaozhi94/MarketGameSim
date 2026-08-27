"""R018-C005 regression: the run-family matrix is enforced at the run_one
entrypoint BEFORE simulator construction (FR-023 / IR-501 fail-closed).

A config that declares a family and violates its allow/deny matrix must be
rejected by run_one itself -- not silently accepted because the validator
was never wired to the entrypoint.
"""

from __future__ import annotations

import pytest

from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.experiment.config import ExperimentConfig
from market_game_sim.experiment.run_family import RunFamilyError
from market_game_sim.experiment.runner import run_one


def _base_config(**overrides) -> ExperimentConfig:
    defaults = dict(
        seed=1,
        max_transactions=60,
        agent_specs=[
            AgentSpec(
                agent_id="agent-0",
                role="retail",
                observe_interval_ns=1_000_000_000,
                latency_ns=50_000_000,
                goal_model_id="risk_budget_linear_v1",
            )
        ],
    )
    defaults.update(overrides)
    return ExperimentConfig(**defaults)


def _spontaneous_config() -> ExperimentConfig:
    # R018-C005 (Round 3): matrix fields are FIRST-CLASS constructor args,
    # not test-injected dynamic properties.
    return _base_config(
        run_family="SPONTANEOUS",
        seed_plan={"n_seeds": 3, "seeds": [1, 2, 3]},
        l_level="low",
        m_level="high",
    )


def test_run_one_rejects_spontaneous_with_injection_fields():
    cfg = _spontaneous_config()
    cfg.agent_signals = {"agent-0": 5000}  # forbidden in SPONTANEOUS
    with pytest.raises(RunFamilyError, match="agent_signals"):
        run_one(cfg)


def test_run_one_rejects_spontaneous_missing_required():
    cfg = _base_config(run_family="SPONTANEOUS")  # missing seed_plan / l_level / m_level
    with pytest.raises(RunFamilyError, match="seed_plan"):
        run_one(cfg)


def test_run_one_accepts_valid_spontaneous():
    cfg = _spontaneous_config()
    result = run_one(cfg)
    assert result.terminated == "COMPLETED"


def test_run_one_rejects_stress_without_protocol():
    cfg = _base_config(
        run_family="STRESS",
        seed_plan={"n_seeds": 3, "seeds": [1, 2, 3]},
        l_level="low",
        m_level="high",
    )
    with pytest.raises(RunFamilyError, match="stress_protocol"):
        run_one(cfg)


def test_unknown_field_rejected_by_constructor():
    """R018-C005 (Round 3): a config carrying a field outside the frozen
    matrix must fail closed at construction -- the dataclass constructor
    rejects unknown kwargs rather than silently carrying an injection."""
    with pytest.raises(TypeError, match="unknown_field"):
        ExperimentConfig(seed=1, max_transactions=10, unknown_field=1)


def test_legacy_config_without_family_still_runs():
    """run_family=None (legacy) skips the gate -- existing configs keep working."""
    cfg = _base_config()
    result = run_one(cfg)
    assert result.terminated == "COMPLETED"


def test_multi_seed_clone_preserves_run_family_fields():
    """R018-C005 (Round 5): run_multi_seed's per-seed clone must preserve the
    run-family fields -- the old hand-rolled reconstruction dropped them,
    letting the family gate be bypassed at the per-seed level."""
    from dataclasses import replace

    cfg = _base_config(run_family="BENCHMARK", seed_plan={"n_seeds": 3, "seeds": [1, 2, 3]})
    clone = replace(cfg, seed=2)
    assert clone.run_family == "BENCHMARK"
    assert clone.seed_plan == {"n_seeds": 3, "seeds": [1, 2, 3]}
    # The clone must still pass the family validator (family gate intact).
    from market_game_sim.experiment.run_family import (
        from_experiment_config,
        validate_run_family,
    )

    rc = from_experiment_config(clone)
    rc.run_family = "BENCHMARK"
    validate_run_family(rc)


def test_stress_protocol_events_are_executed():
    """R018-C006 (Round 5/7): a declared STRESS protocol must actually be
    executed as EXOGENOUS_STRESS orders (legal origin), produce trades, and
    NOT yield a technical-invalid run (Round 7: origin=EXOGENOUS_STRESS was
    added to the ORDER_ARRIVAL enum; before that the run was TI-3)."""
    from market_game_sim.experiment.stress_protocol import StressEvent, StressProtocolV1

    proto = StressProtocolV1(
        protocol_id="p1",
        events=(
            StressEvent(
                "MARKET_ORDER",
                # Late enough that the MM has already posted quotes (its first
                # decide lands ~5ms after t=0) -- an earlier shock would find
                # an empty book and its MARKET order would be IOC-cancelled.
                timestamp_ns=10_000_000_000,
                params={"side": "SELL", "quantity_units": 100},
            ),
        ),
    )
    cfg = _base_config(
        run_family="STRESS",
        seed_plan={"n_seeds": 3, "seeds": [1, 2, 3]},
        l_level="low",
        m_level="high",
        # Enough transactions for the 10s stress order to be reached (the MM
        # re-quotes every 100ms, consuming ~6 transactions per cycle).
        max_transactions=2000,
    )
    cfg.stress_protocol = proto
    # Add a market maker so the shock SELL order has a resting counterparty
    # to fill against (without one the book is empty and the trade never happens).
    cfg.agent_specs = [
        *cfg.agent_specs,
        AgentSpec(
            agent_id="mm-0",
            role="inventory_market_maker",
            observe_interval_ns=100_000_000,
            latency_ns=5_000_000,
            is_market_maker=True,
            half_spread_ticks=5,
            quote_size=10_000,
            max_inventory=100_000,
            inventory_skew_k_bp=10_000,
        ),
    ]
    result = run_one(cfg)
    assert result.terminated == "COMPLETED"
    # Not technically invalid: the EXOGENOUS_STRESS origin must be schema-legal.
    assert result.classification.technical_invalid_code is None, (
        f"STRESS run must not be technical-invalid, got "
        f"{result.classification.technical_invalid_code}"
    )
    stress_orders = [e for e in result.events if e.get("origin") == "EXOGENOUS_STRESS"]
    assert len(stress_orders) == 1, "stress protocol event must be executed"
    # The shock must actually trade (synthetic account exists as counterparty).
    assert any(e.get("event_type") == "TRADE_SETTLE" for e in result.events), (
        "stress order must produce a trade"
    )
