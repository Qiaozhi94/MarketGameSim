"""T304 (v0.1 / P-1): factor correlation matrix tests.

Positive + negative + multi-record cases per CLAUDE.md: correlated factors are
flagged, uncorrelated are not, matrix is symmetric.
"""

from __future__ import annotations

from market_game_sim.robustness.ablation_corr import factor_correlation


class TestFactorCorrelation:
    def test_highly_correlated_flagged(self):
        x = [float(i) for i in range(20)]
        series = {"momentum": x, "reversion": x, "book": [float(0)] * 20}
        fc = factor_correlation(series)
        # momentum vs reversion identical -> |rho| ~ 1
        assert ("momentum", "reversion") in [(a, b) for a, b, _ in fc.high_correlations]

    def test_uncorrelated_not_flagged(self):
        import random

        rng = random.Random(0)
        x = [rng.random() for _ in range(50)]
        y = [rng.random() for _ in range(50)]
        fc = factor_correlation({"momentum": x, "book": y})
        assert fc.high_correlations == []

    def test_matrix_symmetric(self):
        import random

        rng = random.Random(1)
        x = [rng.random() for _ in range(30)]
        y = [rng.random() for _ in range(30)]
        fc = factor_correlation({"momentum": x, "book": y})
        assert fc.matrix["momentum"]["book"] == fc.matrix["book"]["momentum"]

    def test_diagonal_is_one(self):
        x = [float(i) for i in range(10)]
        fc = factor_correlation({"momentum": x})
        assert fc.matrix["momentum"]["momentum"] == 1.0

    def test_short_series_zero(self):
        fc = factor_correlation({"momentum": [1.0], "book": [2.0]})
        assert fc.matrix["momentum"]["book"] == 0.0
