"""T006 (0.1.3 §1): model-family difference-boundary tests.

Positive + negative + multi-record cases per CLAUDE.md: same-family variant
passes, family-defining change is a new family, and id/version-only relabel
is rejected.
"""

from __future__ import annotations

import pytest

from market_game_sim.robustness.model_family import (
    ModelFamily,
    ModelFamilyError,
    ModelFamilyRegistry,
    family_id_hash,
)


def _belief_family() -> ModelFamily:
    return ModelFamily(
        family_id="belief_family",
        version="1.0",
        description="belief-weight signal family",
        shared_mechanisms=["belief_weights", "factor_mix"],
        family_defining_fields=["factor_architecture"],
    )


def _signal_family() -> ModelFamily:
    return ModelFamily(
        family_id="signal_family",
        version="1.0",
        description="direct signal family",
        shared_mechanisms=["factor_mix"],
        family_defining_fields=["signal_architecture"],
    )


class TestRegistry:
    def test_register_and_get(self):
        reg = ModelFamilyRegistry()
        reg.register(_belief_family())
        reg.register(_signal_family())
        assert reg.get("belief_family@1.0").family_id == "belief_family"
        assert len(reg.families()) == 2

    def test_redefine_same_id_different_fields_fails(self):
        reg = ModelFamilyRegistry()
        reg.register(_belief_family())
        changed = _belief_family()
        changed.family_defining_fields = ["other"]
        with pytest.raises(ModelFamilyError, match="different defining fields"):
            reg.register(changed)

    def test_unknown_family_fails(self):
        reg = ModelFamilyRegistry()
        with pytest.raises(ModelFamilyError, match="unknown"):
            reg.get("nope@1.0")


class TestVariantVsFamily:
    BASE = {"factor_architecture": "belief"}

    def test_param_variant_same_family(self):
        fam = _belief_family()
        candidate = {"factor_architecture": "belief", "maint_bp": 700}  # scan axis only
        is_same, _ = ModelFamilyRegistry().classify(fam, candidate)
        assert is_same
        assert ModelFamilyRegistry().requires_new_family(fam, self.BASE, candidate) is None

    def test_family_defining_change_is_new_family(self):
        fam = _belief_family()
        candidate = {"factor_architecture": "signal"}  # defining field changed
        reason = ModelFamilyRegistry().requires_new_family(fam, self.BASE, candidate)
        assert reason is not None
        assert "family-defining field" in reason

    def test_id_version_only_relabel_fails_classify(self):
        # no defining field present -> cannot establish same-family identity
        is_same, reason = ModelFamilyRegistry().classify(_belief_family(), {})
        assert not is_same
        assert "no family-defining field present" in reason

    def test_relabel_without_structure_not_new_family(self):
        # requires_new_family: no defining field changed -> None (no new family
        # from a bare relabel, T403)
        fam = _belief_family()
        assert ModelFamilyRegistry().requires_new_family(fam, self.BASE, {"unrelated": 1}) is None


class TestFamilyIdHash:
    def test_distinct_families_differ(self):
        fam = _belief_family()
        h1 = family_id_hash(fam, {"factor_architecture": "belief"})
        h2 = family_id_hash(fam, {"factor_architecture": "signal"})
        assert h1 != h2

    def test_variant_in_family_same_id(self):
        fam = _belief_family()
        assert family_id_hash(fam, {"factor_architecture": "belief", "maint_bp": 400}) == (
            family_id_hash(fam, {"factor_architecture": "belief", "maint_bp": 900})
        )

    def test_qualified_id(self):
        assert _belief_family().qualified_id() == "belief_family@1.0"
