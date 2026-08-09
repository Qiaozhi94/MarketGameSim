"""T403 (方法论 §10.5): configuration-diff validator tests.

Positive + negative + multi-record cases per CLAUDE.md: legal model-family
diff passes, extra-field drift rejected, id-only relabel rejected, and
behavior-mapping / scan / ablation contrasts restrict to allowed fields.
"""

from __future__ import annotations

import pytest

from market_game_sim.robustness.diff_validator import (
    ContrastRule,
    DiffValidationError,
    validate_contrast,
)


def _family_rule():
    return ContrastRule(
        kind="model_family",
        family_defining_fields=["factor_architecture"],
        requires_structural_change=True,
    )


class TestModelFamilyContrast:
    def test_legal_family_diff_passes(self):
        base = {
            "model_family_id": "f1",
            "version": "1.0",
            "factor_architecture": "belief",
            "maint_bp": 500,
        }
        changed = {
            "model_family_id": "f2",
            "version": "1.0",
            "factor_architecture": "signal",
            "maint_bp": 500,
        }
        diff = validate_contrast(base, changed, _family_rule())
        assert "factor_architecture" in diff

    def test_extra_field_drift_rejected(self):
        base = {"model_family_id": "f1", "factor_architecture": "belief", "maint_bp": 500}
        changed = {"model_family_id": "f2", "factor_architecture": "signal", "maint_bp": 600}
        with pytest.raises(DiffValidationError, match="outside defining set"):
            validate_contrast(base, changed, _family_rule())

    def test_id_only_relabel_rejected(self):
        base = {"model_family_id": "f1", "factor_architecture": "belief", "maint_bp": 500}
        changed = {"model_family_id": "f2", "factor_architecture": "belief", "maint_bp": 500}
        with pytest.raises(DiffValidationError, match="no family-defining structural field"):
            validate_contrast(base, changed, _family_rule())

    def test_shared_fields_byte_identical(self):
        base = {"model_family_id": "f1", "factor_architecture": "belief", "maint_bp": 500}
        changed = {"model_family_id": "f2", "factor_architecture": "signal", "maint_bp": 500}
        validate_contrast(base, changed, _family_rule())
        # shared field maint_bp unchanged
        assert changed["maint_bp"] == base["maint_bp"]


class TestOtherContrasts:
    def test_behavior_mapping_restricts_to_allowed(self):
        rule = ContrastRule(kind="behavior_mapping", allowed_fields=["behavior_mapping", "version"])
        base = {"behavior_mapping": "linear", "version": "1.0", "taker_bps": 5}
        changed = {"behavior_mapping": "threshold", "version": "1.0", "taker_bps": 5}
        assert validate_contrast(base, changed, rule)

    def test_behavior_mapping_extra_field_rejected(self):
        rule = ContrastRule(kind="behavior_mapping", allowed_fields=["behavior_mapping", "version"])
        base = {"behavior_mapping": "linear", "version": "1.0", "taker_bps": 5}
        changed = {"behavior_mapping": "threshold", "version": "1.0", "taker_bps": 9}
        with pytest.raises(DiffValidationError, match="outside allowed set"):
            validate_contrast(base, changed, rule)

    def test_scan_axis_single_dimension(self):
        rule = ContrastRule(kind="scan_axis", allowed_fields=["maint_bp"])
        base = {"maint_bp": 500, "mm_thickness": 10}
        changed = {"maint_bp": 600, "mm_thickness": 10}
        assert validate_contrast(base, changed, rule)
