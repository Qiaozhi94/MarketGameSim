"""T201 (A-005): scan-axis validation tests.

Positive + negative + multi-record cases per CLAUDE.md: each axis validates
correct values and rejects each invalid boundary.
"""

from __future__ import annotations

from market_game_sim.robustness.scan import (
    LeverageDistributionAxis,
    MaintBpAxis,
    MmThicknessAxis,
)


class TestLeverageDistributionAxis:
    def test_valid_sums_to_10000(self):
        a = LeverageDistributionAxis(distribution={3: 5000, 10: 5000})
        assert a.validate() == []

    def test_bad_sum_fails(self):
        a = LeverageDistributionAxis(distribution={3: 3000, 10: 5000})
        assert any("sum to" in p for p in a.validate())

    def test_empty_fails(self):
        assert any("empty" in p for p in LeverageDistributionAxis(distribution=None).validate())

    def test_zero_tier_fails(self):
        a = LeverageDistributionAxis(distribution={0: 5000, 10: 5000})
        assert any("tiers must be >= 1" in p for p in a.validate())


class TestMaintBpAxis:
    def test_valid_range(self):
        a = MaintBpAxis(values=[400, 500], target_bp=1000, initial_bp=10000)
        assert a.validate() == []

    def test_maint_not_less_than_target_fails(self):
        a = MaintBpAxis(values=[1500], target_bp=1000, initial_bp=10000)
        assert any("violates maint_bp < target_bp" in p for p in a.validate())

    def test_maint_exceeds_initial_fails(self):
        a = MaintBpAxis(values=[20000], target_bp=1000, initial_bp=10000)
        assert any("violates maint_bp" in p for p in a.validate())

    def test_empty_fails(self):
        assert any("empty" in p for p in MaintBpAxis(values=None).validate())


class TestMmThicknessAxis:
    def test_valid_positive(self):
        assert MmThicknessAxis(values=[10, 20], min_thickness=0).validate() == []

    def test_nonpositive_fails(self):
        a = MmThicknessAxis(values=[0, 20], min_thickness=0)
        assert any("must be > 0" in p for p in a.validate())

    def test_empty_fails(self):
        assert any("empty" in p for p in MmThicknessAxis(values=None).validate())
