"""T101/T102: behavior-mapping interface + mappings tests.

Positive + negative + multi-record cases per CLAUDE.md: linear baseline
reproduces target_position exactly; threshold dead band and step behavior
verified on both sides of every boundary.
"""

from __future__ import annotations

import pytest

from market_game_sim.agent.mapping import (
    LinearMapping,
    ThresholdMapping,
    get_mapping,
    register_mapping,
)
from market_game_sim.agent.strategy import target_position


class TestLinearMapping:
    def test_matches_baseline_target_position(self):
        m = LinearMapping()
        assert m.target_position(500, 1_000_000, 10000, 1000, 1) == target_position(
            500, 1_000_000, 10000, 1000, 1
        )
        assert m.target_position(-300, 1_000_000, 10000, 1000, 1) == target_position(
            -300, 1_000_000, 10000, 1000, 1
        )

    def test_zero_on_invalid_input(self):
        m = LinearMapping()
        assert m.target_position(500, 1_000_000, 0, 1000, 1) == 0
        assert m.target_position(500, 1_000_000, 10000, 0, 1) == 0


class TestThresholdMapping:
    def test_dead_band_zero(self):
        m = ThresholdMapping(dead_band_bp=200, step_fraction_bp=10_000)
        assert m.target_position(199, 1_000_000, 10000, 1000, 1) == 0
        assert m.target_position(-199, 1_000_000, 10000, 1000, 1) == 0

    def test_at_dead_band_is_active(self):
        m = ThresholdMapping(dead_band_bp=200, step_fraction_bp=10_000)
        assert m.target_position(200, 1_000_000, 10000, 1000, 1) > 0
        assert m.target_position(-200, 1_000_000, 10000, 1000, 1) < 0

    def test_full_step_fraction(self):
        # max_pos = 1e6*10000/(1000*10000)=1000; *1.0 = 1000
        m = ThresholdMapping(dead_band_bp=0, step_fraction_bp=10_000)
        assert m.target_position(500, 1_000_000, 10000, 1000, 1) == 1000
        assert m.target_position(-500, 1_000_000, 10000, 1000, 1) == -1000

    def test_partial_step_fraction(self):
        # max_pos=1000; *0.5 = 500
        m = ThresholdMapping(dead_band_bp=0, step_fraction_bp=5_000)
        assert m.target_position(500, 1_000_000, 10000, 1000, 1) == 500

    def test_min_qty_rounding(self):
        # max_pos=1000; step_fraction 0.3 -> 300; 300 is already a multiple of
        # min_qty=50, so truncation leaves it unchanged
        m = ThresholdMapping(dead_band_bp=0, step_fraction_bp=3_000)
        assert m.target_position(500, 1_000_000, 10000, 1000, 50) == 300

    def test_sign_preserved_for_negative(self):
        m = ThresholdMapping(dead_band_bp=0, step_fraction_bp=10_000)
        assert m.target_position(-500, 1_000_000, 10000, 1000, 1) == -1000

    def test_invalid_input_zero(self):
        m = ThresholdMapping()
        assert m.target_position(500, 1_000_000, 0, 1000, 1) == 0
        assert m.target_position(500, 1_000_000, 10000, 0, 1) == 0


class TestRegistry:
    def test_linear_registered(self):
        assert get_mapping("linear").id == "linear"

    def test_threshold_registered(self):
        assert get_mapping("threshold").id == "threshold"

    def test_unknown_mapping_raises(self):
        with pytest.raises(KeyError):
            get_mapping("nope")

    def test_register_custom(self):
        class M(LinearMapping):
            pass

        register_mapping(M())
        assert get_mapping("linear").id == "linear"
