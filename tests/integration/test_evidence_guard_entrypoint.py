"""R018-C011 regression: the report/aggregation entrypoint enforces the
evidence-class permission (IR-502) -- a cross-family paired run is rejected
by run_paired itself, the report's actual evidence_class must be authorized
for the declared family, and legacy (None) is its own family that cannot
mix with a declared one (Round 3: the guard hardcoded engineering-demo and
let None + declared mix through).
"""

from __future__ import annotations

import pytest

from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.evidence.evidence_guard import EvidenceClassError
from market_game_sim.experiment.config import ExperimentConfig
from market_game_sim.experiment.runner import run_paired


def _cfg(run_family: str | None) -> ExperimentConfig:
    cfg = ExperimentConfig(
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
    if run_family is not None:
        # Declared families require seed_plan (C005: the gate now actually
        # enforces the matrix, so valid configs must carry it).
        cfg.seed_plan = {"n_seeds": 3, "seeds": [1, 2, 3]}
    return cfg


def test_run_paired_rejects_cross_family():
    control = _cfg("SPONTANEOUS")
    control.seed_plan = {"n_seeds": 3, "seeds": [1, 2, 3]}
    control.l_level = "low"
    control.m_level = "high"
    treatment = _cfg("BENCHMARK")
    with pytest.raises(EvidenceClassError, match="cross-family"):
        run_paired(control, treatment, seeds=[1, 2, 3])


def test_run_paired_requires_evidence_class_for_declared_family():
    """R018-C011 (Round 3): a declared family without the report's
    evidence_class is rejected -- no implicit downgrade."""
    control = _cfg("BENCHMARK")
    treatment = _cfg("BENCHMARK")
    with pytest.raises(EvidenceClassError, match="evidence_class"):
        run_paired(control, treatment, seeds=[1, 2, 3])


def test_run_paired_accepts_same_family_with_authorized_class():
    control = _cfg("BENCHMARK")
    treatment = _cfg("BENCHMARK")
    results = run_paired(
        control, treatment, seeds=[1, 2, 3], evidence_class="engineering-demonstration"
    )
    assert results


def test_run_paired_rejects_unauthorized_evidence_class():
    control = _cfg("BENCHMARK")
    treatment = _cfg("BENCHMARK")
    with pytest.raises(EvidenceClassError, match="not allowed"):
        run_paired(control, treatment, seeds=[1, 2, 3], evidence_class="formal-research")


def test_run_paired_rejects_legacy_and_declared_mix():
    """R018-C011 (Round 3): legacy (None) is its own family -- mixing it with
    a declared family is cross-family aggregation."""
    control = _cfg(None)
    treatment = _cfg("BENCHMARK")
    with pytest.raises(EvidenceClassError, match="cross-family"):
        run_paired(control, treatment, seeds=[1, 2, 3])


def test_run_paired_accepts_legacy_pair():
    control = _cfg(None)
    treatment = _cfg(None)
    results = run_paired(control, treatment, seeds=[1, 2, 3])
    assert results


def test_unpreregistered_formal_research_rejected():
    """R018-C011 (Round 5): formal-research requires a frozen preregistration
    -- an unpreregistered SPONTANEOUS pair must not emit a formal conclusion."""
    control = _cfg("SPONTANEOUS")
    control.seed_plan = {"n_seeds": 3, "seeds": [1, 2, 3]}
    control.l_level = "low"
    control.m_level = "high"
    treatment = _cfg("SPONTANEOUS")
    treatment.seed_plan = {"n_seeds": 3, "seeds": [1, 2, 3]}
    treatment.l_level = "low"
    treatment.m_level = "high"
    with pytest.raises(EvidenceClassError, match="preregistration"):
        run_paired(control, treatment, seeds=[1, 2, 3], evidence_class="formal-research")


def test_preregistered_formal_research_accepted_and_recorded():
    """R018-C011 (Round 5): a preregistered SPONTANEOUS pair may emit
    formal-research, and the report records the evidence_class."""
    control = _cfg("SPONTANEOUS")
    control.seed_plan = {"n_seeds": 3, "seeds": [1, 2, 3]}
    control.l_level = "low"
    control.m_level = "high"
    treatment = _cfg("SPONTANEOUS")
    treatment.seed_plan = {"n_seeds": 3, "seeds": [1, 2, 3]}
    treatment.l_level = "low"
    treatment.m_level = "high"
    _, _, comparison = run_paired(
        control,
        treatment,
        seeds=[1, 2, 3],
        evidence_class="formal-research",
        preregistration="prereg-2026-08-27-v1",
    )
    assert comparison["evidence_class"] == "formal-research"
    assert comparison["run_family"] == "SPONTANEOUS"
    assert comparison["preregistration"] == "prereg-2026-08-27-v1"


def test_declared_seed_plan_must_match_actual_seeds():
    """R018-C005 (Round 7): a seed plan declaring seeds=[11,12,13,14] but a
    run using [1] must be rejected, not silently under-powered."""
    control = _cfg("SPONTANEOUS")
    control.seed_plan = {"n_seeds": 4, "seeds": [11, 12, 13, 14]}
    control.l_level = "low"
    control.m_level = "high"
    treatment = _cfg("SPONTANEOUS")
    treatment.seed_plan = {"n_seeds": 4, "seeds": [11, 12, 13, 14]}
    treatment.l_level = "low"
    treatment.m_level = "high"
    with pytest.raises(ValueError, match="seed plan"):
        run_paired(control, treatment, seeds=[1], evidence_class="experiment-preview")
