"""T305 (0.1.3 E3): factor necessity classification tests.

Positive + negative + multi-record cases per CLAUDE.md: necessary /
non-necessary / substitutable / insufficient each reachable.
"""

from __future__ import annotations

from market_game_sim.robustness.necessity import Necessity, classify_necessity


class TestClassifyNecessity:
    def test_necessary_when_change_exceeds(self):
        v = classify_necessity(
            "momentum",
            baseline_effect=0.5,
            ablated_effect=0.1,
            ablated_ci_half_width=0.1,
            necessity_threshold=0.3,
        )
        assert v.verdict is Necessity.NECESSARY

    def test_non_necessary_when_change_small(self):
        v = classify_necessity(
            "book",
            baseline_effect=0.5,
            ablated_effect=0.48,
            ablated_ci_half_width=0.05,
            necessity_threshold=0.3,
        )
        assert v.verdict is Necessity.NON_NECESSARY

    def test_substitutable_when_high_corr(self):
        v = classify_necessity(
            "momentum",
            baseline_effect=0.5,
            ablated_effect=0.1,
            ablated_ci_half_width=0.1,
            necessity_threshold=0.3,
            high_corr_factor="reversion",
        )
        assert v.verdict is Necessity.SUBSTITUTABLE
        assert v.high_corr_with == "reversion"

    def test_insufficient_when_interval_wide(self):
        v = classify_necessity(
            "noise",
            baseline_effect=0.5,
            ablated_effect=0.2,
            ablated_ci_half_width=2.0,
            necessity_threshold=0.3,
            max_interval_half_width=1.0,
        )
        assert v.verdict is Necessity.INSUFFICIENT_EVIDENCE

    def test_reports_effect_size(self):
        v = classify_necessity(
            "momentum",
            baseline_effect=0.5,
            ablated_effect=0.1,
            ablated_ci_half_width=0.1,
            necessity_threshold=0.3,
        )
        assert v.effect_size == 0.1
        assert v.interval_half_width == 0.1

    def test_ablation_alone_does_not_imply_necessity(self):
        # large change but wide interval -> insufficient, NOT necessary
        v = classify_necessity(
            "momentum",
            baseline_effect=0.5,
            ablated_effect=0.0,
            ablated_ci_half_width=5.0,
            necessity_threshold=0.3,
            max_interval_half_width=1.0,
        )
        assert v.verdict is Necessity.INSUFFICIENT_EVIDENCE
