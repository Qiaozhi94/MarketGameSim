"""T603 (方法论 §9.3/§10.1/§10.3): three-zone experiment protocol enforcement.

Round 14's design discussion confirmed the recommended defaults: frozen
fields = all ExperimentConfig/AgentSpec fields except a single declared
treatment_field; audit trail persisted to a JSON Lines file; belief-
experiment/calibration non-overlap checked only on the treatment
dimension's explored values.
"""

from __future__ import annotations

import json

import pytest

from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.experiment.config import ExperimentConfig
from market_game_sim.experiment.protocol import (
    ExperimentProtocol,
    ProtocolStage,
    ProtocolViolation,
)


def _agent(
    agent_id: str = "a1", leverage_tier: int = 1, aggressiveness_bp: int = 5000
) -> AgentSpec:
    return AgentSpec(
        agent_id=agent_id,
        role="retail",
        observe_interval_ns=1_000_000_000,
        latency_ns=50_000_000,
        leverage_tier=leverage_tier,
        aggressiveness_bp=aggressiveness_bp,
    )


def _config(leverage_tier: int = 1, taker_bps: int = 5, seed: int = 1) -> ExperimentConfig:
    return ExperimentConfig(
        seed=seed,
        max_transactions=60,
        taker_bps=taker_bps,
        agent_specs=[_agent(leverage_tier=leverage_tier)],
    )


def _protocol(tmp_path) -> ExperimentProtocol:
    return ExperimentProtocol(audit_log_path=tmp_path / "audit.jsonl")


class TestStageSequencing:
    def test_initial_stage_is_calibration(self, tmp_path):
        p = _protocol(tmp_path)
        assert p.stage is ProtocolStage.CALIBRATION

    def test_freeze_calibration_advances_stage(self, tmp_path):
        p = _protocol(tmp_path)
        p.freeze_calibration(_config())
        assert p.stage is ProtocolStage.FROZEN_VALIDATION

    def test_enter_belief_experiment_advances_stage(self, tmp_path):
        p = _protocol(tmp_path)
        p.freeze_calibration(_config())
        p.enter_belief_experiment([10, 50])
        assert p.stage is ProtocolStage.BELIEF_EXPERIMENT

    def test_cannot_freeze_twice(self, tmp_path):
        """Negative case: freezing again from FROZEN_VALIDATION (or later)
        must be rejected -- stage only moves forward."""
        p = _protocol(tmp_path)
        p.freeze_calibration(_config())
        with pytest.raises(ProtocolViolation, match="CALIBRATION"):
            p.freeze_calibration(_config())

    def test_cannot_skip_frozen_validation(self, tmp_path):
        """Negative case: entering belief-experiment straight from
        CALIBRATION (skipping FROZEN_VALIDATION) must be rejected."""
        p = _protocol(tmp_path)
        with pytest.raises(ProtocolViolation, match="FROZEN_VALIDATION"):
            p.enter_belief_experiment([10])

    def test_cannot_record_calibration_trial_after_freeze(self, tmp_path):
        p = _protocol(tmp_path)
        p.freeze_calibration(_config())
        with pytest.raises(ProtocolViolation, match="CALIBRATION"):
            p.record_calibration_trial(_config())


class TestFrozenFieldLock:
    def test_check_config_passes_when_unchanged(self, tmp_path):
        p = _protocol(tmp_path)
        base = _config(taker_bps=5)
        p.freeze_calibration(base)
        p.check_config(_config(taker_bps=5, seed=2))  # different seed is fine

    def test_check_config_raises_when_frozen_field_changed(self, tmp_path):
        p = _protocol(tmp_path)
        p.freeze_calibration(_config(taker_bps=5))
        with pytest.raises(ProtocolViolation, match="taker_bps"):
            p.check_config(_config(taker_bps=8))

    def test_check_config_allows_treatment_field_to_vary_in_frozen_validation(self, tmp_path):
        """The declared treatment_field (leverage_tier) is exempt from the
        frozen snapshot -- FROZEN_VALIDATION doesn't yet have a
        pre-registered range for it (that only exists once
        enter_belief_experiment has run)."""
        p = _protocol(tmp_path)
        p.freeze_calibration(_config(leverage_tier=1))
        p.check_config(_config(leverage_tier=99))  # must not raise

    def test_check_config_raises_when_agentspec_field_changed(self, tmp_path):
        p = _protocol(tmp_path)
        p.freeze_calibration(_config())
        drifted = _config()
        drifted.agent_specs[0].aggressiveness_bp = 9999
        with pytest.raises(ProtocolViolation, match="aggressiveness_bp"):
            p.check_config(drifted)


class TestCalibrationOverlapCheck:
    def test_disjoint_values_pass(self, tmp_path):
        p = _protocol(tmp_path)
        p.record_calibration_trial(_config(leverage_tier=1))
        p.record_calibration_trial(_config(leverage_tier=2))
        p.freeze_calibration(_config(leverage_tier=1))
        p.enter_belief_experiment([10, 50])  # must not raise

    def test_overlap_with_calibration_trial_raises(self, tmp_path):
        """Positive case for the non-overlap requirement: if calibration
        happened to try leverage_tier=10 (even incidentally, while tuning
        something else), the belief-experiment zone must not reuse it."""
        p = _protocol(tmp_path)
        p.record_calibration_trial(_config(leverage_tier=1))
        p.record_calibration_trial(_config(leverage_tier=10))
        p.freeze_calibration(_config(leverage_tier=1))
        with pytest.raises(ProtocolViolation, match="10"):
            p.enter_belief_experiment([10, 50])
        assert p.stage is ProtocolStage.FROZEN_VALIDATION  # unchanged on failure


class TestBeliefExperimentRangeEnforcement:
    def test_registered_value_passes(self, tmp_path):
        p = _protocol(tmp_path)
        p.freeze_calibration(_config(leverage_tier=1))
        p.enter_belief_experiment([10, 50])
        p.check_config(_config(leverage_tier=10))  # must not raise

    def test_unregistered_value_raises(self, tmp_path):
        p = _protocol(tmp_path)
        p.freeze_calibration(_config(leverage_tier=1))
        p.enter_belief_experiment([10, 50])
        with pytest.raises(ProtocolViolation, match="99"):
            p.check_config(_config(leverage_tier=99))


class TestAuditLog:
    def test_violation_appends_jsonl_entry(self, tmp_path):
        p = _protocol(tmp_path)
        p.freeze_calibration(_config(taker_bps=5))
        with pytest.raises(ProtocolViolation):
            p.check_config(_config(taker_bps=8))
        lines = p.audit_log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["stage"] == "FROZEN_VALIDATION"
        assert entry["field"] == "taker_bps"
        assert entry["frozen_value"] == 5
        assert entry["attempted_value"] == 8
        assert "timestamp_utc" in entry

    def test_multiple_violations_append_not_overwrite(self, tmp_path):
        p = _protocol(tmp_path)
        p.freeze_calibration(_config(taker_bps=5))
        for _ in range(2):
            with pytest.raises(ProtocolViolation):
                p.check_config(_config(taker_bps=8))
        lines = p.audit_log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2

    def test_audit_log_creates_parent_directory(self, tmp_path):
        p = ExperimentProtocol(audit_log_path=tmp_path / "nested" / "dir" / "audit.jsonl")
        p.freeze_calibration(_config(taker_bps=5))
        with pytest.raises(ProtocolViolation):
            p.check_config(_config(taker_bps=8))
        assert p.audit_log_path.exists()

    def test_no_audit_entry_when_no_violation(self, tmp_path):
        p = _protocol(tmp_path)
        p.freeze_calibration(_config(taker_bps=5))
        p.check_config(_config(taker_bps=5, seed=99))
        assert not p.audit_log_path.exists()
