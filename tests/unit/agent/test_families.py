"""T006/E1: model-family implementation tests.

Positive + negative + multi-record cases per CLAUDE.md: both families produce
signals in [-10000,10000], differ structurally, unknown family fails-closed.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from market_game_sim.agent.families import (
    ModelFamilyError,
    belief_family_signal,
    family_signal,
    signal_family_signal,
)


def _factors():
    return [Decimal("0.5"), Decimal("-0.3"), Decimal("0.2"), Decimal("0.1"), Decimal("0.1")]


def _weights():
    return [Decimal("0.2")] * 5


class TestFamilies:
    def test_belief_family_in_range(self):
        s = belief_family_signal(_factors(), _weights())
        assert -10000 <= s <= 10000

    def test_signal_family_in_range(self):
        s = signal_family_signal(_factors(), _weights())
        assert -10000 <= s <= 10000

    def test_families_structurally_differ(self):
        # same factors/weights -> different families can give different signals
        a = belief_family_signal(_factors(), _weights())
        b = signal_family_signal(_factors(), _weights())
        assert a != b

    def test_signal_family_ignores_weights(self):
        w1 = [Decimal("0.2")] * 5
        w2 = [Decimal("0.8"), Decimal("0.05"), Decimal("0.05"), Decimal("0.05"), Decimal("0.05")]
        assert signal_family_signal(_factors(), w1) == signal_family_signal(_factors(), w2)

    def test_belief_family_uses_weights(self):
        w1 = [Decimal("0.2")] * 5
        w2 = [Decimal("0.8"), Decimal("0.05"), Decimal("0.05"), Decimal("0.05"), Decimal("0.05")]
        assert belief_family_signal(_factors(), w1) != belief_family_signal(_factors(), w2)

    def test_family_signal_dispatch(self):
        assert family_signal("belief_family", _factors(), _weights()) == belief_family_signal(
            _factors(), _weights()
        )
        assert family_signal("signal_family", _factors(), _weights()) == signal_family_signal(
            _factors(), _weights()
        )

    def test_unknown_family_fails(self):
        with pytest.raises(ModelFamilyError, match="unknown model family"):
            family_signal("nope", _factors(), _weights())


class TestSignalFamilyAblationNameBinding:
    """v013 regression (high): after ablation the list is shortened; signal
    family must select factors BY NAME, never by original position (which
    would silently consume the wrong factor)."""

    def test_ablate_other_factor_keeps_momentum_book(self):
        # remove noise: momentum+book remain, order preserved
        from market_game_sim.agent.families import apply_ablation_named

        values, w, names = apply_ablation_named(_factors(), _weights(), "noise")
        s = signal_family_signal(values, w, names)
        # must equal signal computed from original momentum+book directly
        expected = signal_family_signal(
            [_factors()[0], _factors()[3]], _weights(), ("momentum", "book")
        )
        assert s == expected

    def test_ablate_book_renormalizes_to_momentum(self):
        # v013 round-2 regression (high): leave-one-out on the family's own
        # required factor (book) must NOT fail -- T301 removes one factor and
        # renormalizes; signal_family falls back to the remaining momentum.
        from market_game_sim.agent.families import apply_ablation_named

        values, w, names = apply_ablation_named(_factors(), _weights(), "book")
        s = signal_family_signal(values, w, names)
        # equals a pure-momentum signal (single factor, weight normalized to 1)
        expected = signal_family_signal([_factors()[0]], _weights(), ("momentum",))
        assert s == expected

    def test_ablate_momentum_renormalizes_to_book(self):
        from market_game_sim.agent.families import apply_ablation_named

        values, w, names = apply_ablation_named(_factors(), _weights(), "momentum")
        s = signal_family_signal(values, w, names)
        expected = signal_family_signal([_factors()[3]], _weights(), ("book",))
        assert s == expected

    def test_no_family_factor_left_fails_closed(self):
        # removing BOTH momentum and book leaves no family factor -> fail
        from market_game_sim.agent.families import apply_ablation_named

        values, w, names = apply_ablation_named(_factors(), _weights(), "momentum")
        values, w, names = apply_ablation_named(values, w, "book", names)
        with pytest.raises(ModelFamilyError, match="no enabled factors"):
            signal_family_signal(values, w, names)

    def test_name_value_length_mismatch_fails(self):
        with pytest.raises(ModelFamilyError, match="length mismatch"):
            signal_family_signal([_factors()[0]], _weights(), ("momentum", "book"))
