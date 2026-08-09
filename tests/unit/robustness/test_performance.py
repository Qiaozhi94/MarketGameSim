"""T702 (NFR-003): scan cost / throughput tests.

Positive + negative + multi-record cases per CLAUDE.md: throughput computed
with README §3 caliber, 20% regression tolerance enforced, random-path change
rejected.
"""

from __future__ import annotations

import pytest

from market_game_sim.robustness.performance import (
    PerformanceError,
    ScanCost,
    assert_random_path_unchanged,
)


class TestScanCost:
    def test_transactions_per_second(self):
        c = ScanCost(total_transactions=100_000, total_wall_seconds=10.0, n_cells=1)
        assert c.transactions_per_second == pytest.approx(10_000.0)

    def test_per_cell_throughput(self):
        c = ScanCost(total_transactions=100_000, total_wall_seconds=10.0, n_cells=5)
        assert c.per_cell_transactions_per_second == pytest.approx(2_000.0)

    def test_zero_wall_seconds_fails(self):
        with pytest.raises(PerformanceError, match="total_wall_seconds"):
            _ = ScanCost(100, 0.0, 1).transactions_per_second

    def test_zero_cells_fails(self):
        with pytest.raises(PerformanceError, match="n_cells"):
            _ = ScanCost(100, 1.0, 0).per_cell_transactions_per_second


class TestRegression:
    def test_no_baseline_no_regression(self):
        c = ScanCost(100, 1.0, 1)
        assert c.regression_vs_baseline == 0.0
        assert c.within_regression_tolerance

    def test_within_tolerance(self):
        c = ScanCost(100, 1.0, 1, baseline_tps=110.0)  # 100 vs 110 -> 9% slower
        assert c.regression_vs_baseline == pytest.approx(0.0909, rel=1e-3)
        assert c.within_regression_tolerance

    def test_exceeds_tolerance(self):
        c = ScanCost(100, 1.0, 1, baseline_tps=200.0)  # 50% slower
        assert c.regression_vs_baseline == pytest.approx(0.5)
        assert not c.within_regression_tolerance

    def test_faster_than_baseline_ok(self):
        c = ScanCost(200, 1.0, 1, baseline_tps=100.0)  # 2x faster -> negative regression
        assert c.regression_vs_baseline == pytest.approx(-1.0)
        assert c.within_regression_tolerance


class TestRandomPathGuard:
    def test_identical_events_pass(self):
        events = [
            {
                "record_kind": "EVENT",
                "event_type": "TRADE_SETTLE",
                "price_ticks": 10000,
                "transaction_seq": 0,
            }
        ]
        assert_random_path_unchanged(events, list(events))  # no error

    def test_changed_events_rejected(self):
        base = [
            {
                "record_kind": "EVENT",
                "event_type": "TRADE_SETTLE",
                "price_ticks": 10000,
                "transaction_seq": 0,
            }
        ]
        changed = [
            {
                "record_kind": "EVENT",
                "event_type": "TRADE_SETTLE",
                "price_ticks": 10001,
                "transaction_seq": 0,
            }
        ]
        with pytest.raises(PerformanceError, match="random path"):
            assert_random_path_unchanged(base, changed)
