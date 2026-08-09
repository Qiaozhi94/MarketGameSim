"""T604 (KPI-007): final conditional conclusion tests.

Positive + negative + multi-record cases per CLAUDE.md: every required
element present in text/elements, no extrapolation.
"""

from __future__ import annotations

from market_game_sim.experiment.stats import ProportionDiffResult
from market_game_sim.robustness.final_conclusion import build_final_conclusion


def _result():
    return ProportionDiffResult(
        control_rate=0.1,
        treatment_rate=0.3,
        diff=0.2,
        ci_low=-0.05,
        ci_high=0.45,
        ci_level=0.95,
        n_control=5,
        n_treatment=5,
        n_resamples=1000,
        seed=0,
    )


class TestFinalConclusion:
    def test_all_elements_present(self):
        c = build_final_conclusion(
            _result(),
            structure_desc="2x做市商+20x散户",
            param_range_desc="leverage_tier 3x vs 10x",
            behavior_mapping_id="linear",
            model_family_id="belief_family@1.0",
            cross_verdict="同向成立",
            failure_boundary_desc="maint_bp 600-700 区间外失效",
        )
        assert "linear" in c.text
        assert "belief_family" in c.text
        assert "同向成立" in c.text
        assert c.elements["behavior_mapping_id"] == "linear"
        assert c.elements["model_family_id"] == "belief_family@1.0"
        assert c.elements["cross_verdict"] == "同向成立"
        assert c.elements["n_control_seeds"] == 5
        assert c.elements["effect_size"] == 0.2
        assert c.elements["extrapolation_forbidden"] is True

    def test_core_has_structure_range_seeds_ci(self):
        c = build_final_conclusion(
            _result(),
            structure_desc="S",
            param_range_desc="R",
            behavior_mapping_id="threshold",
            model_family_id="f1@1.0",
            cross_verdict="依赖边界",
        )
        for token in ("参与者结构 S", "参数区间 R", "5 个随机种子", "95% CI"):
            assert token in c.text

    def test_failure_boundary_wired(self):
        c = build_final_conclusion(
            _result(),
            structure_desc="S",
            param_range_desc="R",
            behavior_mapping_id="linear",
            model_family_id="f1@1.0",
            cross_verdict="同向成立",
            failure_boundary_desc="maint_bp > 700 失效",
        )
        assert "失效" in c.text
        assert c.elements["failure_boundary_desc"] == "maint_bp > 700 失效"

    def test_evidence_insufficient_verdict(self):
        c = build_final_conclusion(
            _result(),
            structure_desc="S",
            param_range_desc="R",
            behavior_mapping_id="linear",
            model_family_id="f1@1.0",
            cross_verdict="证据不足",
        )
        assert "证据不足" in c.text

    def test_no_extrapolation_clause(self):
        c = build_final_conclusion(
            _result(),
            structure_desc="S",
            param_range_desc="R",
            behavior_mapping_id="linear",
            model_family_id="f1@1.0",
            cross_verdict="同向成立",
        )
        assert "不得外推" in c.text
