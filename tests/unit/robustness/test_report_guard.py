"""T404/T405: report-guard tests.

Positive + negative + multi-record cases per CLAUDE.md: empty capability set
passes, unevidenced attribution rejected, and conclusion wording requires
adequate paired samples.
"""

from __future__ import annotations

import pytest

from market_game_sim.robustness.report_guard import (
    CapabilityAttribution,
    ReportGuardError,
    guard_capability_attributions,
    guard_conclusion,
    validate_capability_attributions,
)


def _full_evidence():
    return {
        "treatment_field_diff": {"leverage_tier": (3, 10)},
        "shared_random_path_audit": {"consistent": True},
        "paired_sample_size": 5,
        "effect_size": 0.0,
        "confidence_interval": [0.0, 0.0],
    }


class TestCapabilityGuard:
    def test_empty_set_passes(self):
        guard_capability_attributions([])  # no error

    def test_full_evidence_passes(self):
        guard_capability_attributions([CapabilityAttribution("execution", _full_evidence())])

    def test_missing_evidence_rejected(self):
        attr = CapabilityAttribution("information", {"paired_sample_size": 5})
        violations = validate_capability_attributions([attr])
        assert len(violations) == 1
        assert "missing evidence" in violations[0]
        with pytest.raises(ReportGuardError, match="capability attribution guard"):
            guard_capability_attributions([attr])

    def test_unknown_dimension_rejected(self):
        attr = CapabilityAttribution("alpha", _full_evidence())
        with pytest.raises(ReportGuardError, match="unknown capability dimension"):
            guard_capability_attributions([attr])

    def test_all_capabilities_must_be_evidenced(self):
        attrs = [
            CapabilityAttribution(d, _full_evidence())
            for d in ("funding", "information", "speed", "execution")
        ]
        guard_capability_attributions(attrs)  # all fully evidenced -> ok


class TestConclusionGuard:
    def test_adequate_samples_pass(self):
        guard_conclusion(
            n_seeds=5, n_paired_samples=5, min_paired_samples=3, conclusion_wording="..."
        )

    def test_single_run_rejected(self):
        with pytest.raises(ReportGuardError, match="no single-run"):
            guard_conclusion(
                n_seeds=1, n_paired_samples=1, min_paired_samples=3, conclusion_wording="..."
            )

    def test_below_min_paired_rejected(self):
        with pytest.raises(ReportGuardError, match="n_paired_samples"):
            guard_conclusion(
                n_seeds=5, n_paired_samples=2, min_paired_samples=3, conclusion_wording="..."
            )
