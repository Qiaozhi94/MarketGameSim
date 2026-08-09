"""T205 (0.1.3 E2): failure-boundary localization tests.

Positive + negative + multi-record cases per CLAUDE.md: first crossing
located as an interval (no interpolation), no crossing reported as such.
"""

from __future__ import annotations

import pytest

from market_game_sim.robustness.boundary import BoundaryError, locate_failure_boundary


class TestLocateFailureBoundary:
    def test_first_crossing_above(self):
        b = locate_failure_boundary(
            [400, 500, 600], [0.1, 0.2, 0.9], 0.5, threshold_crossed_when="above"
        )
        assert b.threshold_crossed
        assert b.crossing_index == 2
        assert b.crossing_interval == (500, 600)
        assert b.resolution == 100

    def test_first_crossing_below(self):
        b = locate_failure_boundary(
            [400, 500, 600], [0.9, 0.2, 0.1], 0.5, threshold_crossed_when="below"
        )
        assert b.crossing_index == 1
        assert b.crossing_interval == (400, 500)

    def test_no_crossing(self):
        b = locate_failure_boundary(
            [400, 500, 600], [0.1, 0.2, 0.3], 0.5, threshold_crossed_when="above"
        )
        assert b.threshold_crossed is False
        assert b.crossing_index is None

    def test_first_point_crosses(self):
        b = locate_failure_boundary(
            [400, 500, 600], [0.9, 0.9, 0.9], 0.5, threshold_crossed_when="above"
        )
        assert b.crossing_index == 0
        assert b.crossing_interval == (400, 500)

    def test_does_not_interpolate_exact_value(self):
        # crossing between 500 and 600, but we never claim an exact critical
        # value -- only the bracketing interval is reported
        b = locate_failure_boundary(
            [400, 500, 600], [0.2, 0.2, 0.9], 0.5, threshold_crossed_when="above"
        )
        assert b.crossing_interval == (500, 600)
        assert b.resolution == 100  # grid resolution, not interpolated point

    def test_length_mismatch_fails(self):
        with pytest.raises(BoundaryError):
            locate_failure_boundary([400, 500], [0.1], 0.5)

    def test_bad_direction_fails(self):
        with pytest.raises(BoundaryError):
            locate_failure_boundary(
                [400, 500, 600], [0.1, 0.2, 0.9], 0.5, threshold_crossed_when="sideways"
            )
