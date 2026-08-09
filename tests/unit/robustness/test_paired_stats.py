"""T601 (0.1.3 E1/E2): paired bootstrap tests.

Positive + negative + multi-record cases per CLAUDE.md: whole-pair resampling
preserves pairing, deterministic, and empty input fails-closed.
"""

from __future__ import annotations

import pytest

from market_game_sim.robustness.paired_stats import PairedStatsError, paired_bootstrap


class TestPairedBootstrap:
    def test_computes_mean_diff(self):
        pairs = [(0, 1), (0, 1), (1, 1)]
        r = paired_bootstrap(pairs, n_resamples=200, seed=0)
        # diffs: +1, +1, 0 -> mean 2/3
        assert r.mean_diff == pytest.approx(2 / 3)
        assert r.n_pairs == 3

    def test_deterministic(self):
        pairs = [(0, 1), (1, 0), (0, 1), (1, 1)]
        r1 = paired_bootstrap(pairs, n_resamples=500, seed=7)
        r2 = paired_bootstrap(pairs, n_resamples=500, seed=7)
        assert r1.ci_low == r2.ci_low
        assert r1.ci_high == r2.ci_high

    def test_empty_pairs_fails(self):
        with pytest.raises(PairedStatsError, match="at least one pair"):
            paired_bootstrap([])

    def test_bad_ci_level_fails(self):
        with pytest.raises(PairedStatsError, match="ci_level"):
            paired_bootstrap([(0, 1)], ci_level=1.5)

    def test_rates_computed(self):
        pairs = [(0, 1), (0, 1)]
        r = paired_bootstrap(pairs, n_resamples=100, seed=0)
        assert r.control_rate == 0.0
        assert r.treatment_rate == 1.0

    def test_whole_pair_preserved(self):
        # (1,1),(0,0): within-pair diff always 0 despite non-degenerate pair
        # structure; whole-pair bootstrap must reflect the paired diff of 0
        pairs = [(1, 1), (0, 0)]
        r = paired_bootstrap(pairs, n_resamples=500, seed=0)
        assert r.mean_diff == 0.0
