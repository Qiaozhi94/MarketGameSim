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
    cfg = _base_config(run_family="SPONTANEOUS")
    cfg.seed_plan = {"n_seeds": 4}
    cfg.l_level = "low"
    cfg.m_level = "high"
    return cfg


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
    cfg = _base_config(run_family="STRESS")
    cfg.seed_plan = {"n_seeds": 4}
    cfg.l_level = "low"
    cfg.m_level = "high"
    with pytest.raises(RunFamilyError, match="stress_protocol"):
        run_one(cfg)


def test_legacy_config_without_family_still_runs():
    """run_family=None (legacy) skips the gate -- existing configs keep working."""
    cfg = _base_config()
    result = run_one(cfg)
    assert result.terminated == "COMPLETED"
