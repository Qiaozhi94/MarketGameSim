"""T607 (0.1.3 E1-E5): evidence-matrix tests.

Positive + negative + multi-record cases per CLAUDE.md: complete matrix
passes, missing artifact rejected, and capability column always validated.
"""

from __future__ import annotations

import pytest

from market_game_sim.robustness.evidence_matrix import (
    EvidenceMatrix,
    EvidenceMatrixError,
    EvidenceRow,
)
from market_game_sim.robustness.report_guard import CapabilityAttribution


def _row(family="f1", mapping="linear", capability=None):
    return EvidenceRow(
        family_id=family,
        mapping_id=mapping,
        behavior_mapping_artifact="bm.json",
        parameter_boundary_artifact="boundary.json",
        ablation_artifact="ablation.json",
        holdout_artifact="holdout.json",
        kpi009_artifact="bridge.json",
        capability_attributions=capability or [],
    )


class TestEvidenceMatrix:
    def test_complete_matrix_passes(self):
        m = EvidenceMatrix(rows=[_row(), _row("f2", "threshold")])
        m.validate()  # no error

    def test_missing_artifact_rejected(self):
        row = _row()
        row.holdout_artifact = ""
        m = EvidenceMatrix(rows=[row])
        with pytest.raises(EvidenceMatrixError, match="missing artifacts"):
            m.validate()

    def test_capability_empty_set_allowed(self):
        # 0.1.3 capability set is empty -> allowed
        m = EvidenceMatrix(rows=[_row()])
        m.validate()

    def test_unevidenced_capability_rejected(self):
        row = _row(capability=[CapabilityAttribution("execution", {"paired_sample_size": 5})])
        m = EvidenceMatrix(rows=[row])
        with pytest.raises(EvidenceMatrixError, match="capability attribution"):
            m.validate()

    def test_fully_evidenced_capability_allowed(self):
        evidence = {
            "treatment_field_diff": {"x": (1, 2)},
            "shared_random_path_audit": {"ok": True},
            "paired_sample_size": 5,
            "effect_size": 0.0,
            "confidence_interval": [0.0, 0.0],
        }
        row = _row(capability=[CapabilityAttribution("execution", evidence)])
        m = EvidenceMatrix(rows=[row])
        m.validate()

    def test_as_dict(self):
        m = EvidenceMatrix(rows=[_row()])
        d = m.as_dict()
        assert len(d["rows"]) == 1
        assert d["rows"][0]["family_id"] == "f1"
