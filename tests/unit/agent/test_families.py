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
