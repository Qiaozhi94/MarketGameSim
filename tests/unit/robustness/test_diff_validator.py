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

    def test_deleted_shared_field_rejected(self):
        """v013 regression (high): silently DELETING a shared config field
        must fail-closed -- the old diff only iterated ``changed`` keys, so a
        deletion passed validation."""
        rule = ContrastRule(kind="scan_axis", allowed_fields=["maint_bp"])
        base = {"maint_bp": 500, "mm_thickness": 10}
        changed = {"maint_bp": 600}  # mm_thickness deleted
        with pytest.raises(DiffValidationError, match="outside allowed set"):
            validate_contrast(base, changed, rule)

    def test_deleted_family_defining_field_rejected(self):
        rule = ContrastRule(
            kind="model_family",
            family_defining_fields=["factor_architecture"],
            requires_structural_change=True,
        )
        base = {"model_family_id": "f1", "factor_architecture": "belief", "maint_bp": 500}
        changed = {"model_family_id": "f2", "maint_bp": 500}  # defining field deleted
        with pytest.raises(DiffValidationError, match="deleted defining field"):
            validate_contrast(base, changed, rule)

    def test_deleted_treatment_field_rejected(self):
        """v013 round-2 regression (high): deleting the pre-registered
        treatment field ITSELF (maint_bp / behavior_mapping) must be rejected
        -- the treatment must still exist; a deletion is not a legal contrast
        (the old code treated a deleted allowed field as an allowed change)."""
        rule = ContrastRule(kind="scan_axis", allowed_fields=["maint_bp"])
        base = {"maint_bp": 500, "mm_thickness": 10}
        changed = {"mm_thickness": 10}  # maint_bp deleted entirely
        with pytest.raises(DiffValidationError, match="deleted treatment field"):
            validate_contrast(base, changed, rule)

    def test_deleted_behavior_mapping_rejected(self):
        rule = ContrastRule(kind="behavior_mapping", allowed_fields=["behavior_mapping", "version"])
        base = {"behavior_mapping": "linear", "version": "1.0", "taker_bps": 5}
        changed = {"version": "1.0", "taker_bps": 5}  # behavior_mapping deleted
        with pytest.raises(DiffValidationError, match="deleted treatment field"):
            validate_contrast(base, changed, rule)

    def test_nullable_value_change_is_not_deletion(self):
        """v013 round-3 regression (high): `disabled_factor: noise -> None` is
        a LEGAL value change (the ablation is turned off), NOT a deletion --
        the old diff marked both with None and rejected the legal case."""
        rule = ContrastRule(kind="ablation", allowed_fields=["disabled_factor"])
        base = {"disabled_factor": "noise", "taker_bps": 5}
        changed = {"disabled_factor": None, "taker_bps": 5}  # value set to None
        diff = validate_contrast(base, changed, rule)
        assert diff == {"disabled_factor": None}

    def test_zero_diff_contrast_rejected(self):
        """v013 round-3 regression (high): two IDENTICAL configs are not a
        valid contrast -- the target treatment must actually vary."""
        rule = ContrastRule(kind="scan_axis", allowed_fields=["maint_bp"])
        base = {"maint_bp": 500, "mm_thickness": 10}
        with pytest.raises(DiffValidationError, match="no change"):
            validate_contrast(base, dict(base), rule)

    def test_zero_diff_ablation_rejected(self):
        rule = ContrastRule(kind="ablation", allowed_fields=["disabled_factor"])
        base = {"disabled_factor": None, "taker_bps": 5}
        with pytest.raises(DiffValidationError, match="no change"):
            validate_contrast(base, dict(base), rule)
