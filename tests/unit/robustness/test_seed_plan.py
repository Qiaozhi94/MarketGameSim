"""T005 (KPI-010): seed-plan tests.

Positive + negative + multi-record cases per CLAUDE.md: backfill only on
technical failure; cap enforcement; "证据不足" when under-powered after
backfills; no single-run conclusion.
"""

from __future__ import annotations

import pytest

from market_game_sim.robustness.seed_plan import (
    RunTracker,
    SeedPlan,
    SeedPlanError,
)


def _plan(seed_count=5, min_pairs=3, max_backfills=2, backfill_list=None):
    return SeedPlan(
        pair_family="leverage_vs_control",
        planned_seed_count=seed_count,
        min_valid_pairs=min_pairs,
        max_technical_failure_backfills=max_backfills,
        backfill_seed_list=backfill_list or [101, 102, 103],
    )


class TestSeedPlanValidate:
    def test_valid_plan(self):
        assert _plan().validate() == []

    def test_single_seed_rejected(self):
        p = _plan(seed_count=1)
        assert any("planned_seed_count must be >= 2" in item for item in p.validate())

    def test_invalid_plan_raises_on_tracker(self):
        with pytest.raises(SeedPlanError, match="invalid seed plan"):
            RunTracker(_plan(seed_count=1))


class TestBackfill:
    def test_granted_on_technical_failure(self):
        t = RunTracker(_plan())
        d = t.request_backfill("TI-1")
        assert d.granted
        assert d.seed == 101
        assert t.backfills_used == 1

    def test_denied_on_non_technical_reason(self):
        t = RunTracker(_plan())
        d = t.request_backfill("effect_not_significant")
        assert not d.granted
        assert "not a technical failure" in d.reason

    def test_denied_on_effect_direction(self):
        t = RunTracker(_plan())
        assert not t.request_backfill("result_negative").granted

    def test_denied_when_cap_exhausted(self):
        t = RunTracker(_plan(max_backfills=1, backfill_list=[101, 102]))
        assert t.request_backfill("TI-1").granted
        d = t.request_backfill("TI-1")
        assert not d.granted
        assert "cap reached" in d.reason

    def test_denied_when_pool_exhausted(self):
        t = RunTracker(_plan(max_backfills=2, backfill_list=[101]))
        assert t.request_backfill("TI-1").granted
        d = t.request_backfill("TI-1")
        assert not d.granted
        assert "no backfill seeds left" in d.reason

    def test_uses_fixed_pool_in_order(self):
        t = RunTracker(_plan(backfill_list=[7, 8, 9]))
        assert t.request_backfill("TI-3").seed == 7
        assert t.request_backfill("TI-5").seed == 8


class TestConclusionEligibility:
    def test_eligible_when_min_reached(self):
        t = RunTracker(_plan(min_pairs=3))
        for _ in range(3):
            t.record_valid_pair()
        eligible, note = t.conclusion_eligible()
        assert eligible
        assert ">= min=" in note

    def test_insufficient_evidence_when_below_min(self):
        t = RunTracker(_plan(min_pairs=3))
        for _ in range(2):
            t.record_valid_pair()
        eligible, note = t.conclusion_eligible()
        assert not eligible
        assert "证据不足" in note

    def test_below_min_even_after_backfills(self):
        # only 2 valid from planning, 2 backfills but still < min 3 -> 证据不足
        t = RunTracker(_plan(min_pairs=3, max_backfills=2))
        for _ in range(2):
            t.record_valid_pair()
        t.request_backfill("TI-1")
        t.request_backfill("TI-1")
        eligible, note = t.conclusion_eligible()
        assert not eligible
        assert "证据不足" in note

    def test_no_single_run_conclusion(self):
        t = RunTracker(_plan(min_pairs=2))
        t.record_valid_pair()
        eligible, _ = t.conclusion_eligible()
        assert not eligible
