"""T003 (0.1.3 §2): preregistration tests.

Positive + negative + multi-record cases per CLAUDE.md: a complete
preregistration freezes and validates; missing any required component
fails-closed.
"""

from __future__ import annotations

import json

import pytest

from market_game_sim.robustness.preregistration import (
    AblationFactor,
    EffectSizeSpec,
    ModelFamily,
    Preregistration,
    PreregistrationError,
    ScanAxis,
    freeze,
    prereg_id,
)


def _complete() -> Preregistration:
    return Preregistration(
        alternative_behavior_mappings=["threshold"],
        linear_baseline_mapping="linear",
        model_families=[
            ModelFamily(
                "belief_family", "1.0", "belief weights + linear target", ["belief_factors"]
            ),
            ModelFamily("signal_family", "1.0", "direct signal mapping", ["signal_direct"]),
        ],
        scan_axes=[
            ScanAxis(
                "leverage_tier_distribution",
                "leverage cap distribution",
                "leverage_tier_distribution",
                [3, 10],
            ),
            ScanAxis("maint_bp", "maintenance margin", "maint_bp", [400, 500]),
            ScanAxis("mm_thickness", "market maker thickness", "mm_thickness", [10, 20]),
        ],
        ablation_factors=[
            AblationFactor("momentum"),
            AblationFactor("reversion"),
            AblationFactor("herding"),
            AblationFactor("book"),
            AblationFactor("noise"),
        ],
        common_random_path_rule=(
            "paired runs use identical (mechanism,decision_index,draw_index) draws"
        ),
        holdout_zone="frozen zone disjoint from exploration scan zone",
        effect_size=EffectSizeSpec(),
        failure_boundary_definition="first parameter region crossing the preregistered threshold",
    )


class TestValidate:
    def test_complete_is_valid(self):
        assert _complete().validate() == []

    def test_missing_alternative_mapping_fails(self):
        p = _complete()
        p.alternative_behavior_mappings = []
        assert "no alternative behavior mappings preregistered" in p.validate()

    def test_linear_only_is_not_an_alternative(self):
        """v013 regression (high): a preregistration whose only mapping is
        ``linear`` must fail -- T003 requires at least one ALTERNATIVE mapping
        (the old condition only fired on an empty list)."""
        p = _complete()
        p.alternative_behavior_mappings = ["linear"]
        assert "no alternative behavior mappings preregistered" in p.validate()

    def test_fewer_than_two_families_fails(self):
        p = _complete()
        p.model_families = p.model_families[:1]
        assert "fewer than two model families preregistered" in p.validate()

    def test_missing_scan_axis_fails(self):
        p = _complete()
        p.scan_axes = [a for a in p.scan_axes if a.name != "maint_bp"]
        assert "missing maint_bp scan axis" in p.validate()

    def test_missing_rules_fail(self):
        p = _complete()
        p.common_random_path_rule = ""
        p.holdout_zone = ""
        p.failure_boundary_definition = ""
        problems = p.validate()
        assert "common_random_path_rule not set" in problems
        assert "holdout_zone not set" in problems
        assert "failure_boundary_definition not set" in problems


class TestPreregId:
    def test_stable_for_identical(self):
        assert prereg_id(_complete()) == prereg_id(_complete())

    def test_changes_on_content_change(self):
        a = _complete()
        b = _complete()
        b.alternative_behavior_mappings = ["step"]
        assert prereg_id(a) != prereg_id(b)


class TestFreeze:
    def test_writes_and_returns_id(self, tmp_path):
        p = _complete()
        path = tmp_path / "prereg.json"
        pid = freeze(p, path)
        assert pid == prereg_id(p)
        assert json.loads(path.read_text(encoding="utf-8"))["prereg_id"] == pid

    def test_incomplete_fails_closed(self, tmp_path):
        p = _complete()
        p.model_families = p.model_families[:1]
        with pytest.raises(PreregistrationError, match="incomplete"):
            freeze(p, tmp_path / "prereg.json")

    def test_refuses_overwrite_different(self, tmp_path):
        path = tmp_path / "prereg.json"
        freeze(_complete(), path)
        other = _complete()
        other.alternative_behavior_mappings = ["step"]
        with pytest.raises(PreregistrationError, match="refusing to overwrite"):
            freeze(other, path)

    def test_idempotent_same_content(self, tmp_path):
        path = tmp_path / "prereg.json"
        freeze(_complete(), path)
        freeze(_complete(), path)  # identical content -> ok
