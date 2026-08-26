"""R018-C011 regression: the report/aggregation entrypoint enforces the
evidence-class permission (IR-502) -- a cross-family paired run is rejected
by run_paired itself, not bypassable by calling the aggregator directly.
"""

from __future__ import annotations

import pytest

from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.evidence.evidence_guard import EvidenceClassError
from market_game_sim.experiment.config import ExperimentConfig
from market_game_sim.experiment.runner import run_paired


def _cfg(run_family: str) -> ExperimentConfig:
    return ExperimentConfig(
        seed=1,
        max_transactions=60,
        run_family=run_family,
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


def test_run_paired_rejects_cross_family():
    control = _cfg("SPONTANEOUS")
    control.seed_plan = {"n_seeds": 4}
    control.l_level = "low"
    control.m_level = "high"
    treatment = _cfg("BENCHMARK")
    with pytest.raises(EvidenceClassError, match="cross-family"):
        run_paired(control, treatment, seeds=[1, 2, 3])


def test_run_paired_accepts_same_family():
    control = _cfg("BENCHMARK")
    treatment = _cfg("BENCHMARK")
    results = run_paired(control, treatment, seeds=[1, 2, 3])
    assert results
