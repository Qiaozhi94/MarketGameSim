"""T604/T605 (方法论 §9.2/§10.2): paired-experiment statistics.

Round reviews found run_paired only returned raw n_completed/n_endpoint
counts -- no effect size, no confidence interval, no conditional-conclusion
text as required by 方法论 §10.2 ("有效/无效"这种形式不予接受).
"""

from __future__ import annotations

import pytest

from market_game_sim.experiment.stats import (
    ProportionDiffResult,
    bootstrap_proportion_diff,
    build_conditional_conclusion,
    holm_bonferroni,
)


class TestBootstrapProportionDiff:
    def test_deterministic_same_seed_same_result(self):
        control = [False, False, True, False, False]
        treatment = [True, True, False, True, True]
        r1 = bootstrap_proportion_diff(control, treatment, n_resamples=500, seed=7)
        r2 = bootstrap_proportion_diff(control, treatment, n_resamples=500, seed=7)
        assert r1 == r2

    def test_point_estimate_independent_of_bootstrap_seed(self):
        """diff/control_rate/treatment_rate are direct sample statistics,
        not resampled -- must be identical regardless of bootstrap seed."""
        control = [False, False, True, False, False, True, False, True]
        treatment = [True, True, False, True, True, False, True, True]
        r1 = bootstrap_proportion_diff(control, treatment, n_resamples=300, seed=1)
        r2 = bootstrap_proportion_diff(control, treatment, n_resamples=300, seed=2)
        assert r1.diff == r2.diff
        assert r1.control_rate == r2.control_rate
        assert r1.treatment_rate == r2.treatment_rate

    def test_large_clear_effect_ci_excludes_zero(self):
        control = [False] * 20
        treatment = [True] * 20
        result = bootstrap_proportion_diff(control, treatment, n_resamples=1000, seed=0)
        assert result.control_rate == 0.0
        assert result.treatment_rate == 1.0
        assert result.diff == 1.0
        assert result.ci_excludes_zero is True

    def test_no_effect_ci_includes_zero(self):
        control = [True, False, True, False, True, False, True, False]
        treatment = [False, True, False, True, False, True, False, True]
        result = bootstrap_proportion_diff(control, treatment, n_resamples=2000, seed=0)
        assert result.ci_excludes_zero is False

    def test_empty_group_raises(self):
        with pytest.raises(ValueError, match="at least one sample"):
            bootstrap_proportion_diff([], [True], n_resamples=10, seed=0)
        with pytest.raises(ValueError, match="at least one sample"):
            bootstrap_proportion_diff([True], [], n_resamples=10, seed=0)

    def test_invalid_ci_level_raises(self):
        with pytest.raises(ValueError, match="ci_level"):
            bootstrap_proportion_diff([True], [False], ci_level=1.5, seed=0)
        with pytest.raises(ValueError, match="ci_level"):
            bootstrap_proportion_diff([True], [False], ci_level=0.0, seed=0)


class TestHolmBonferroni:
    def test_single_significant(self):
        assert holm_bonferroni({"a": 0.001}, alpha=0.05) == {"a": True}

    def test_single_not_significant(self):
        assert holm_bonferroni({"a": 0.5}, alpha=0.05) == {"a": False}

    def test_step_down_rejects_after_first_failure(self):
        """Regression for the step-down property: once a hypothesis (in
        rank order) fails, everything with an equal-or-larger p-value must
        also fail -- EVEN IF it would pass its own naive per-rank
        threshold in isolation.  m=3, alpha=0.05 -> thresholds
        0.0167/0.025/0.05 for ranks 0/1/2: b's own p=0.03 fails its 0.025
        threshold, and c's own p=0.04 would PASS its 0.05 threshold in
        isolation -- but step-down must force c to False too, since it
        ranks after the first failure."""
        p_values = {"a": 0.001, "b": 0.03, "c": 0.04}
        result = holm_bonferroni(p_values, alpha=0.05)
        assert result["a"] is True
        assert result["b"] is False
        assert result["c"] is False

    def test_empty_input(self):
        assert holm_bonferroni({}, alpha=0.05) == {}

    def test_invalid_alpha_raises(self):
        with pytest.raises(ValueError, match="alpha"):
            holm_bonferroni({"a": 0.01}, alpha=0.0)


class TestBuildConditionalConclusion:
    def _result(self, ci_low: float, ci_high: float) -> ProportionDiffResult:
        return ProportionDiffResult(
            control_rate=0.1,
            treatment_rate=0.3,
            diff=0.2,
            ci_low=ci_low,
            ci_high=ci_high,
            ci_level=0.95,
            n_control=30,
            n_treatment=30,
            n_resamples=10_000,
            seed=0,
        )

    def test_includes_structure_range_n_effect_ci(self):
        text = build_conditional_conclusion(
            self._result(0.05, 0.35),
            structure_desc="1x market_maker, 1x retail",
            param_range_desc="leverage_tier in {1, 10}",
        )
        assert "1x market_maker, 1x retail" in text
        assert "leverage_tier in {1, 10}" in text
        assert "30" in text
        assert "0.2000" in text
        assert "0.05" in text or "0.0500" in text

    def test_significant_wording_when_ci_excludes_zero(self):
        text = build_conditional_conclusion(self._result(0.05, 0.35), "S", "R")
        assert "显著" in text
        assert "不显著" not in text

    def test_not_significant_wording_when_ci_includes_zero(self):
        text = build_conditional_conclusion(self._result(-0.1, 0.35), "S", "R")
        assert "不显著" in text

    def test_no_binary_valid_invalid_phrasing(self):
        """方法论 §10.2: "有效/无效"这种形式不予接受 -- the conclusion must
        never reduce to a bare binary verdict without the conditional
        structure/range/N/effect-size/CI form."""
        text = build_conditional_conclusion(self._result(0.05, 0.35), "S", "R")
        assert "在参与者结构" in text
        assert "CI" in text or "置信区间" in text

    def test_failure_condition_included_when_given(self):
        text = build_conditional_conclusion(
            self._result(0.05, 0.35), "S", "R", failure_condition_desc="市场深度低于10档"
        )
        assert "市场深度低于10档" in text
        assert "之外失效" in text

    def test_failure_condition_defaults_to_explicit_non_extrapolation_note(self):
        text = build_conditional_conclusion(self._result(0.05, 0.35), "S", "R")
        assert "未声明" in text
        assert "不得外推" in text
