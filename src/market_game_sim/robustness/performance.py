"""T702 (NFR-003): scan cost / throughput tracking.

Tracks the total cost of a robustness scan, per-cell transaction throughput
(``transactions_per_second``, the README §3 reporting caliber) and the
relative regression vs. the 0.1.2 baseline (README §2 第三层: same-machine
regression must stay within 20%).

Performance optimization must never change the random path, sample set or
statistical caliber -- so every cost measurement is paired with a random-path
digest check (reusing ``verify.digest_events``): if the event digest changes
between a baseline run and an "optimized" run, the optimization is rejected
regardless of any speedup.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from market_game_sim.verify import digest_events

REGRESSION_TOLERANCE = 0.20  # README §2 第三层: <= 20% same-machine regression


class PerformanceError(RuntimeError):
    """Raised on an invalid performance measurement or a random-path change."""


@dataclass
class ScanCost:
    total_transactions: int
    total_wall_seconds: float
    n_cells: int
    baseline_tps: float | None = None

    @property
    def transactions_per_second(self) -> float:
        if self.total_wall_seconds <= 0:
            raise PerformanceError("total_wall_seconds must be > 0")
        return self.total_transactions / self.total_wall_seconds

    @property
    def per_cell_transactions_per_second(self) -> float:
        """Throughput per parameter cell: total tps divided by cell count
        (a scan over more cells costs proportionally more)."""
        if self.n_cells <= 0:
            raise PerformanceError("n_cells must be > 0")
        return self.transactions_per_second / self.n_cells

    @property
    def regression_vs_baseline(self) -> float:
        """Same-machine regression vs the 0.1.2 baseline tps: positive means
        slower (1.0 = 100% slower).  ``None`` baseline -> 0.0."""
        if self.baseline_tps is None:
            return 0.0
        return (self.baseline_tps - self.transactions_per_second) / self.baseline_tps

    @property
    def within_regression_tolerance(self) -> bool:
        return self.regression_vs_baseline <= REGRESSION_TOLERANCE

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_transactions": self.total_transactions,
            "total_wall_seconds": self.total_wall_seconds,
            "n_cells": self.n_cells,
            "transactions_per_second": self.transactions_per_second,
            "per_cell_transactions_per_second": self.per_cell_transactions_per_second,
            "baseline_tps": self.baseline_tps,
            "regression_vs_baseline": self.regression_vs_baseline,
            "within_regression_tolerance": self.within_regression_tolerance,
        }


def assert_random_path_unchanged(
    baseline_events: list[dict],
    optimized_events: list[dict],
) -> None:
    """Fail-closed: an "optimization" that changes the event stream (random
    path / sample set / statistical caliber) is rejected no matter the speedup
    (NFR-003: 性能优化不得改变随机路径、样本集合或统计口径)."""
    if digest_events(baseline_events) != digest_events(optimized_events):
        raise PerformanceError("performance optimization changed the random path / event stream")
