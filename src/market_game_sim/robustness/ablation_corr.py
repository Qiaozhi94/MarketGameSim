"""T304 (v0.1 / P-1): factor correlation matrix and high-correlation alert.

Outputs the Pearson correlation matrix of the five belief factors across a
run's decision samples, and flags any factor pair with sustained |rho| > 0.8.
Ablation results must disclose such highly-correlated factors so a
substitutable component is never mislabeled as a necessary one (T305).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from market_game_sim.robustness.ablation import FACTOR_ORDER

HIGH_CORR_THRESHOLD = 0.8


class CorrelationError(RuntimeError):
    """Raised when a correlation matrix cannot be computed."""


@dataclass
class FactorCorrelation:
    matrix: dict[str, dict[str, float]] = field(default_factory=dict)
    high_correlations: list[tuple[str, str, float]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "matrix": self.matrix,
            "high_correlations": self.high_correlations,
        }


def _pearson(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or len(a) < 2:
        return 0.0
    n = len(a)
    ma = sum(a) / n
    mb = sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b, strict=True))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    if da == 0 or db == 0:
        return 0.0
    return num / (da * db)


def factor_correlation(factor_series: dict[str, list[float]]) -> FactorCorrelation:
    """Compute the Pearson correlation matrix over the given factor series.

    ``factor_series`` maps factor name -> per-sample values.  Only factors in
    FACTOR_ORDER are considered.  Pairs with sustained |rho| > 0.8 are flagged.
    """
    names = [n for n in FACTOR_ORDER if n in factor_series]
    matrix: dict[str, dict[str, float]] = {}
    high: list[tuple[str, str, float]] = []
    for a in names:
        matrix[a] = {}
        for b in names:
            rho = _pearson(factor_series[a], factor_series[b])
            matrix[a][b] = round(rho, 4)
            if a < b and abs(rho) > HIGH_CORR_THRESHOLD:
                high.append((a, b, round(rho, 4)))
    high.sort()
    return FactorCorrelation(matrix=matrix, high_correlations=high)
