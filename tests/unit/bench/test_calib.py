"""T702: CALIB-001 microbenchmark tests."""

from __future__ import annotations

import pytest

from market_game_sim.bench.calib import CalibrationRatio, run_calib_001


class TestRunCalib001:
    def test_returns_a_positive_duration(self):
        elapsed = run_calib_001(n=1_000)
        assert elapsed > 0

    def test_larger_n_does_not_return_zero_or_negative(self):
        """Not a strict monotonicity assertion (wall-clock noise), just a
        sanity floor -- a bug that made the workload a no-op (e.g. loop body
        removed) would tend to collapse this near zero or throw."""
        elapsed = run_calib_001(n=5_000)
        assert elapsed > 0

    def test_default_n_is_the_frozen_op_count(self):
        from market_game_sim.bench.calib import CALIB_001_OPS

        assert CALIB_001_OPS == 200_000


class TestCalibrationRatio:
    def test_speed_ratio_faster_local_machine_gt_1(self):
        ratio = CalibrationRatio(reference_seconds=10.0, local_seconds=5.0)
        assert ratio.speed_ratio == 2.0

    def test_speed_ratio_slower_local_machine_lt_1(self):
        ratio = CalibrationRatio(reference_seconds=10.0, local_seconds=20.0)
        assert ratio.speed_ratio == 0.5

    def test_normalize_scales_measured_time_by_speed_ratio(self):
        ratio = CalibrationRatio(reference_seconds=10.0, local_seconds=5.0)
        assert ratio.normalize(3.0) == 6.0  # 2x faster machine -> folded back to 2x the time

    def test_zero_local_seconds_raises(self):
        ratio = CalibrationRatio(reference_seconds=10.0, local_seconds=0.0)
        with pytest.raises(ValueError):
            _ = ratio.speed_ratio
