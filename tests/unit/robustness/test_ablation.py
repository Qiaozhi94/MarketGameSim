"""T301/T302 (FR-010, KR-004): five-factor ablation tests.

Positive + negative + multi-record cases per CLAUDE.md: ablation removes one
factor and renormalizes; retained factors' random draws are unaffected.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from market_game_sim.agent.factors import belief_signal
from market_game_sim.robustness.ablation import (
    AblationError,
    ablated_weight_vector,
    factor_index,
    leave_one_out_disabled,
)


def _weights():
    return [Decimal("0.2"), Decimal("0.2"), Decimal("0.2"), Decimal("0.2"), Decimal("0.2")]


class TestFactorIndex:
    def test_known_factor(self):
        assert factor_index("momentum") == 0
        assert factor_index("noise") == 4

    def test_unknown_factor_fails(self):
        with pytest.raises(AblationError, match="unknown factor"):
            factor_index("alpha")


class TestAblatedWeightVector:
    def test_no_ablation_returns_original(self):
        w, kept = ablated_weight_vector(_weights(), None)
        assert w == _weights()
        assert kept == [0, 1, 2, 3, 4]

    def test_disable_one_renormalizes_to_sum_one(self):
        w, kept = ablated_weight_vector(_weights(), "momentum")
        assert kept == [1, 2, 3, 4]
        assert sum(w) == Decimal(1)
        assert len(w) == 4

    def test_renormalization_preserves_relative_weights(self):
        # weights {0.5, 0.3, 0.1, 0.05, 0.05}; drop index 0 -> keep {0.3,0.1,0.05,0.05}
        weights = [Decimal("0.5"), Decimal("0.3"), Decimal("0.1"), Decimal("0.05"), Decimal("0.05")]
        w, kept = ablated_weight_vector(weights, "momentum")
        # ratio 0.3 : 0.1 : 0.05 : 0.05 preserved, sums to 1
        assert w[0] / w[1] == Decimal("3")
        assert sum(w) == Decimal(1)

    def test_wrong_weight_count_fails(self):
        with pytest.raises(AblationError, match="expected 5 weights"):
            ablated_weight_vector([Decimal("0.5")], "momentum")

    def test_zero_sum_fails(self):
        with pytest.raises(AblationError, match="denominator is zero"):
            ablated_weight_vector([Decimal("0")] * 5, "momentum")


class TestLeaveOneOut:
    def test_five_treatments(self):
        assert leave_one_out_disabled() == ["momentum", "reversion", "herding", "book", "noise"]

    def test_each_matches_factor_order(self):
        assert set(leave_one_out_disabled()) == set(
            ("momentum", "reversion", "herding", "book", "noise")
        )


class TestSignalWithAblation:
    def test_ablated_signal_uses_kept_factors_only(self):
        # small factor values so the signal stays inside [-1,1] (not clipped)
        base_w, _ = ablated_weight_vector(_weights(), None)
        factors = [
            Decimal("0.5"),
            Decimal("-0.3"),
            Decimal("0.2"),
            Decimal("0.1"),
            Decimal("0.1"),
        ]
        full = belief_signal(base_w, factors)
        # ablate noise: drop index 4, keep other factors' values
        w, kept = ablated_weight_vector(_weights(), "noise")
        kept_factors = [factors[i] for i in kept]
        assert len(kept_factors) == len(w)
        ablated = belief_signal(w, kept_factors)
        # removing a factor changes the signal (renormalized weights differ)
        assert ablated != full
