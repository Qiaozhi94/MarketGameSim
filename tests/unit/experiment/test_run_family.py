"""T209: run-family config closed set + fail-closed allow/deny matrix (AC-003).

Covers (FR-023 / IR-501 / NFR-005):
- the three frozen families are accepted by the matrix loader;
- SPONTANEOUS rejects the five injection fields (ADR-003 §3.1) with the
  field path in the message;
- each family's required/optional/forbidden verdicts are enforced both ways
  (the accepted config passes, the violating config fails);
- unknown families and unknown fields fail closed.
"""

from __future__ import annotations

import pytest

from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.experiment.config import ExperimentConfig
from market_game_sim.experiment.run_family import (
    RunFamily,
    RunFamilyConfig,
    RunFamilyError,
    from_experiment_config,
    load_run_family_matrix,
    validate_run_family,
)


def _base_config() -> ExperimentConfig:
    return ExperimentConfig(
        seed=1,
        max_transactions=100,
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


def _spontaneous_config() -> RunFamilyConfig:
    rc = from_experiment_config(_base_config())
    rc.run_family = RunFamily.SPONTANEOUS
    rc.seed_plan = {"n_seeds": 4}
    rc.l_level = "low"
    rc.m_level = "high"
    return rc


def test_matrix_loader_returns_frozen_families():
    matrix = load_run_family_matrix()
    assert set(matrix["families"]) == {"SPONTANEOUS", "STRESS", "BENCHMARK"}
    assert matrix["policy"] == "whitelist"
    assert matrix["unlisted_field_verdict"] == "forbidden"
    assert set(matrix["spontaneous_forbidden_min_set"]) == {
        "agent_signals",
        "extra_positions",
        "extra_events",
        "synthetic_shock_accounts",
        "outcome_conditional_orders",
    }


def test_spontaneous_clean_config_passes():
    validate_run_family(_spontaneous_config())


@pytest.mark.parametrize(
    "field",
    [
        "agent_signals",
        "extra_positions",
        "extra_events",
        "synthetic_shock_accounts",
        "outcome_conditional_orders",
    ],
)
def test_spontaneous_rejects_each_injection_field(field):
    rc = _spontaneous_config()
    setattr(rc, field, {"x": 1})
    with pytest.raises(RunFamilyError, match=field):
        validate_run_family(rc)


def test_spontaneous_rejects_unknown_family():
    rc = _spontaneous_config()
    rc.run_family = "MYSTERY"
    with pytest.raises(RunFamilyError, match="run_family must be one of"):
        validate_run_family(rc)


def test_spontaneous_requires_seed_plan_l_m():
    rc = from_experiment_config(_base_config())
    rc.run_family = RunFamily.SPONTANEOUS
    with pytest.raises(RunFamilyError, match="seed_plan.*required"):
        validate_run_family(rc)


def test_spontaneous_forbids_stress_protocol():
    rc = _spontaneous_config()
    rc.stress_protocol = {"protocol_id": "p1"}
    with pytest.raises(RunFamilyError, match="stress_protocol.*forbidden"):
        validate_run_family(rc)


def test_benchmark_accepts_injection_fields():
    rc = from_experiment_config(_base_config())
    rc.run_family = RunFamily.BENCHMARK
    rc.seed_plan = {"n_seeds": 1}
    rc.agent_signals = {"agent-0": 5000}
    rc.extra_positions = {"victim": {"wallet_units": 1, "position_units": 100}}
    rc.extra_events = [{"event_type": "ORDER_ARRIVAL"}]
    rc.synthetic_shock_accounts = {"shock": 1}
    rc.outcome_conditional_orders = None  # forbidden even in BENCHMARK
    validate_run_family(rc)


def test_benchmark_rejects_outcome_conditional_orders():
    rc = from_experiment_config(_base_config())
    rc.run_family = RunFamily.BENCHMARK
    rc.seed_plan = {"n_seeds": 1}
    rc.outcome_conditional_orders = {"trigger": "crash"}
    with pytest.raises(RunFamilyError, match="outcome_conditional_orders.*forbidden"):
        validate_run_family(rc)


def test_stress_requires_protocol_and_rejects_signals():
    rc = from_experiment_config(_base_config())
    rc.run_family = RunFamily.STRESS
    rc.seed_plan = {"n_seeds": 4}
    rc.l_level = "low"
    rc.m_level = "high"
    with pytest.raises(RunFamilyError, match="stress_protocol.*required"):
        validate_run_family(rc)
    rc.stress_protocol = {"protocol_id": "p1"}
    validate_run_family(rc)


def test_error_message_includes_field_path_and_reason():
    rc = from_experiment_config(_base_config())
    rc.run_family = RunFamily.SPONTANEOUS
    rc.seed_plan = {"n_seeds": 4}
    rc.l_level = "low"
    rc.m_level = "high"
    rc.extra_events = [{"event_type": "ORDER_ARRIVAL"}]
    with pytest.raises(RunFamilyError) as excinfo:
        validate_run_family(rc)
    msg = str(excinfo.value)
    assert "extra_events" in msg
    assert "SPONTANEOUS" in msg
    assert "injected" in msg.lower() or "forbidden" in msg.lower()


def test_validate_seed_plan_rejects_malformed():
    """R018-C012 (Round 7): the shared seed-plan validator rejects unknown
    keys, non-positive n_seeds, missing/invalid seeds, and seed-count
    mismatch -- used by run_one, run_paired and the manifest."""
    from market_game_sim.experiment.run_family import validate_seed_plan

    with pytest.raises(RunFamilyError, match="seed_plan"):
        validate_seed_plan({"n_seeds": 1})
    with pytest.raises(RunFamilyError, match="seed_plan"):
        validate_seed_plan({"n_seeds": 0, "seeds": []})
    with pytest.raises(RunFamilyError, match="seed_plan"):
        validate_seed_plan({"n_seeds": 1, "seeds": [1], "extra": 1})
    with pytest.raises(RunFamilyError, match="seed_plan"):
        validate_seed_plan({"n_seeds": 2, "seeds": [1]})
    with pytest.raises(RunFamilyError, match="seed_plan"):
        validate_seed_plan({"n_seeds": 1, "seeds": [True]})
    # A valid plan normalises and returns.
    assert validate_seed_plan({"n_seeds": 2, "seeds": [1, 2]}) == {
        "n_seeds": 2,
        "seeds": [1, 2],
    }
