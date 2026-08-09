"""T203 (方法论 §9.4): coarse/fine sweep refinement tests.

Positive + negative + multi-record cases per CLAUDE.md: regions generated
purely from rule + boundary (no human selection), budget/max-levels enforced.
"""

from __future__ import annotations

import pytest

from market_game_sim.robustness.refinement import (
    RefinementError,
    RefinementRule,
    generate_fine_sweep,
)


class TestGenerateFineSweep:
    def test_generates_levels_within_budget(self):
        rule = RefinementRule(trigger_threshold=0.5, max_levels=2, level_budget=4)
        regions = generate_fine_sweep(rule, (400, 500))
        assert len(regions) == 2
        assert all(r.level == i + 1 for i, r in enumerate(regions))
        # each region has level_budget-1 interior points
        assert len(regions[0].points) == 3

    def test_bisects_toward_boundary(self):
        rule = RefinementRule(trigger_threshold=0.5, max_levels=3, level_budget=4)
        regions = generate_fine_sweep(rule, (400, 500))
        # each level's interval narrows toward the boundary
        i0 = regions[0].interval
        i1 = regions[1].interval
        assert i0[0] <= i1[0] < i1[1] <= i0[1]

    def test_reversed_interval_normalized(self):
        rule = RefinementRule(trigger_threshold=0.5, max_levels=1, level_budget=4)
        regions = generate_fine_sweep(rule, (500, 400))
        assert regions[0].interval == (400, 500)

    def test_zero_span_fails(self):
        rule = RefinementRule(trigger_threshold=0.5, max_levels=1, level_budget=4)
        with pytest.raises(RefinementError, match="endpoints are equal"):
            generate_fine_sweep(rule, (400, 400))

    def test_invalid_rule_fails(self):
        with pytest.raises(RefinementError, match="invalid refinement rule"):
            generate_fine_sweep(RefinementRule(0.5, 0, 4), (400, 500))

    def test_deterministic(self):
        rule = RefinementRule(trigger_threshold=0.5, max_levels=2, level_budget=4)
        a = generate_fine_sweep(rule, (400, 500))
        b = generate_fine_sweep(rule, (400, 500))
        assert [r.points for r in a] == [r.points for r in b]
