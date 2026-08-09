"""T103 (代理策略 §7/§11): shared execution pipeline tests.

Positive + negative + multi-record cases per CLAUDE.md: the target->execution
pipeline (delta, side, price, admission) is identical across mappings; only
the target position input differs.
"""

from __future__ import annotations

from market_game_sim.agent.mapping import LinearMapping, ThresholdMapping
from market_game_sim.agent.strategy import order_intent_from_signal


def _order(signal_bp, current_position=0, mapping=None):
    return order_intent_from_signal(
        intent_id="i1",
        signal_bp=signal_bp,
        current_position=current_position,
        equity_units=1_000_000,
        valuation_mark_ticks=10000,
        leverage_tier=1,
        aggressiveness_bp=5000,
        best_bid=9900,
        best_ask=10000,
        max_order_qty=10000,
        min_qty=1,
        target_fn=mapping,
    )


class TestSharedPipeline:
    def test_linear_mapping_unchanged(self):
        # regression: with the linear mapping, order_intent_from_signal behaves
        # exactly as before (target = signal_proportional)
        o = _order(500, mapping=LinearMapping().target_position)
        assert o is not None
        assert o.side == "BUY"
        assert o.quantity_units > 0

    def test_threshold_dead_band_yields_no_order(self):
        # signal below threshold -> target 0 -> no actionable order (same
        # pipeline decision as linear returning target 0)
        o = _order(199, mapping=ThresholdMapping(dead_band_bp=200).target_position)
        assert o is None

    def test_threshold_active_yields_buy(self):
        o = _order(
            500, mapping=ThresholdMapping(dead_band_bp=200, step_fraction_bp=10_000).target_position
        )
        assert o is not None
        assert o.side == "BUY"

    def test_pipeline_price_identical_for_same_target(self):
        # both mappings produce target 0 at signal 0 -> both None (pipeline
        # identical at the same target input)
        assert _order(0, mapping=LinearMapping().target_position) is None
        assert _order(0, mapping=ThresholdMapping(dead_band_bp=200).target_position) is None

    def test_reduce_direction_for_negative_target(self):
        o = _order(-500, current_position=100, mapping=LinearMapping().target_position)
        assert o is not None
        assert o.side == "SELL"

    def test_max_order_qty_cap_applies_after_target(self):
        # target = 1000 (from signal 500 linear), but max_order_qty caps delta
        o = order_intent_from_signal(
            intent_id="i1",
            signal_bp=500,
            current_position=0,
            equity_units=1_000_000,
            valuation_mark_ticks=10000,
            leverage_tier=1,
            aggressiveness_bp=5000,
            best_bid=9900,
            best_ask=10000,
            max_order_qty=10,
            min_qty=1,
            target_fn=LinearMapping().target_position,
        )
        assert o.quantity_units <= 10
