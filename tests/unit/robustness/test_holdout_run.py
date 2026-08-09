"""T503/T504: one-shot holdout run + cross-zone comparison tests.

Positive + negative + multi-record cases per CLAUDE.md: technical-failure
re-run retained, non-technical re-run rejected, and honest replication
comparison.
"""

from __future__ import annotations

import pytest

from market_game_sim.robustness.holdout_run import (
    HoldoutRunError,
    HoldoutRunTracker,
    compare_zones,
)


class TestHoldoutRunTracker:
    def test_technical_failure_rerun_retained(self):
        t = HoldoutRunTracker(frozen_plan_id="p1")
        t.request_rerun("run1", "TI-1")
        t.request_rerun("run2", "TI-3")
        assert len(t.attempts) == 2
        assert t.attempts[0].run_id == "run1"

    def test_non_technical_rerun_rejected(self):
        t = HoldoutRunTracker(frozen_plan_id="p1")
        with pytest.raises(HoldoutRunError, match="not a technical failure"):
            t.request_rerun("run1", "effect_reversed")

    def test_completed_run_recorded(self):
        t = HoldoutRunTracker(frozen_plan_id="p1")
        t.mark_completed("run3")
        assert t.completed_run_id == "run3"


class TestCompareZones:
    def test_replication_passed(self):
        c = compare_zones(
            exploration_direction=1,
            holdout_direction=1,
            exploration_effect=0.4,
            holdout_effect=0.42,
            exploration_ci=(0.1, 0.7),
            holdout_ci=(0.15, 0.7),
            effect_tolerance=0.1,
        )
        assert c.replication_passed
        assert c.direction_consistent
        assert c.interval_overlap

    def test_direction_reversal_reported(self):
        c = compare_zones(
            exploration_direction=1,
            holdout_direction=-1,
            exploration_effect=0.4,
            holdout_effect=-0.4,
            exploration_ci=(0.1, 0.7),
            holdout_ci=(-0.7, -0.1),
        )
        assert not c.replication_passed
        assert c.direction_consistent is False
        assert "reported as-is" in c.note

    def test_effect_drift_reported(self):
        c = compare_zones(
            exploration_direction=1,
            holdout_direction=1,
            exploration_effect=0.1,
            holdout_effect=0.9,
            exploration_ci=(0.1, 0.3),
            holdout_ci=(0.7, 1.1),
            effect_tolerance=0.2,
        )
        assert not c.replication_passed

    def test_ci_disjoint_reported(self):
        c = compare_zones(
            exploration_direction=1,
            holdout_direction=1,
            exploration_effect=0.2,
            holdout_effect=0.8,
            exploration_ci=(0.1, 0.3),
            holdout_ci=(0.7, 0.9),
            effect_tolerance=0.5,
        )
        assert c.interval_overlap is False
        assert not c.replication_passed
