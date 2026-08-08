"""T402, T403: Five factors + signal -> intent."""

from __future__ import annotations

from decimal import Decimal

from market_game_sim.agent.factors import (
    belief_signal,
    book,
    herding,
    momentum,
    noise,
    reversion,
)
from market_game_sim.agent.observation import Bar, InformationSet
from market_game_sim.agent.strategy import (
    market_maker_intents,
    order_intent_from_signal,
    target_position,
)


def test_momentum_insufficient_history_zero():
    bars = [Bar(100, 100, 100, 100, 0, 0)]
    assert momentum(bars, 5) == 0


def test_momentum_positive_1pct():
    bars = [Bar(10000, 10000, 10000, c, 0, 0) for c in [10000, 10100]]
    m = momentum(bars, 1)
    assert Decimal("0.99") < m < Decimal("1.0")


def test_momentum_negative_1pct():
    bars = [Bar(10000, 10000, 10000, c, 0, 0) for c in [10100, 10000]]
    m = momentum(bars, 1)
    assert Decimal("-1.0") < m < Decimal("-0.99")


def test_reversion_no_last_zero():
    assert reversion(None, 10000) == 0


def test_reversion_above_anchor_negative():
    """(10000-10200)/10200 = -0.0196, /0.02 = -0.98, clipped to -0.98."""
    v = reversion(10200, 10000)
    assert v < 0 and v > Decimal("-1")


def test_reversion_below_anchor_positive():
    assert reversion(9800, 10000) == 1


def test_herding_zero_volume():
    assert herding([]) == 0


def test_book_both_empty_zero():
    iset = InformationSet(
        agent_id="a",
        observed_at=0,
        best_bid=None,
        best_ask=None,
        bid_depth_k=0,
        ask_depth_k=0,
        last_ticks=None,
    )
    assert book(iset) == 0


def test_book_single_sided():
    iset_bid = InformationSet(
        agent_id="a",
        observed_at=0,
        best_bid=10000,
        best_ask=None,
        bid_depth_k=10,
        ask_depth_k=0,
        last_ticks=10000,
    )
    iset_ask = InformationSet(
        agent_id="a",
        observed_at=0,
        best_bid=None,
        best_ask=10100,
        bid_depth_k=0,
        ask_depth_k=10,
        last_ticks=10100,
    )
    assert book(iset_bid) == 1
    assert book(iset_ask) == -1


def test_noise_clipped():
    assert noise(Decimal("0.5")) == Decimal("0.5")
    assert noise(Decimal("0.0")) == Decimal("0")
    assert noise(Decimal("2.0")) == Decimal("1")
    assert noise(Decimal("-3.0")) == Decimal("-1")


def test_belief_signal_quantized():
    weights = [Decimal("0.5"), Decimal("0.5")]
    factors = [Decimal(1), Decimal(1)]
    assert belief_signal(weights, factors) == 10000


def test_belief_signal_clipped_to_unit():
    weights = [Decimal("1.5"), Decimal("0.5")]
    factors = [Decimal(1), Decimal(1)]
    assert belief_signal(weights, factors) == 10000


def test_target_position_zero_when_no_equity():
    assert target_position(10000, 0, 10000, 1000, 1) == 0


def test_target_position_positive_signal():
    """Signal 10000 (max long) -> max_position.

    max_pos = floor(equity * 10000 / (initial_bp * valuation_mark))
            = 1e11 * 1e4 / (1000 * 10000) = 1e8
    """
    tp = target_position(10000, 100_000_000_000, 10000, 1000, 1)
    assert tp == 100_000_000


def test_target_position_trunc_toward_zero():
    """Signal 5000 (half) of max 1e8 -> target 5e7."""
    tp = target_position(5000, 100_000_000_000, 10000, 1000, 1)
    assert tp == 50_000_000


def test_order_intent_no_action_when_delta_below_min_qty():
    result = order_intent_from_signal(
        intent_id="i1",
        signal_bp=1,
        current_position=0,
        equity_units=100,
        valuation_mark_ticks=10000,
        leverage_tier=1,
        aggressiveness_bp=0,
        best_bid=10000,
        best_ask=10100,
        max_order_qty=100,
        min_qty=1000,
    )
    assert result is None


def test_order_intent_no_action_when_no_book():
    result = order_intent_from_signal(
        intent_id="i1",
        signal_bp=10000,
        current_position=0,
        equity_units=100_000_000_000,
        valuation_mark_ticks=10000,
        leverage_tier=1,
        aggressiveness_bp=0,
        best_bid=None,
        best_ask=None,
        max_order_qty=100,
        min_qty=1,
    )
    assert result is None


def test_order_intent_buy_at_bid_when_aggressive_zero():
    """aggressiveness=0 -> limit bid price = best_bid (maker)."""
    result = order_intent_from_signal(
        intent_id="i1",
        signal_bp=10000,
        current_position=0,
        equity_units=100_000_000_000,
        valuation_mark_ticks=10000,
        leverage_tier=1,
        aggressiveness_bp=0,
        best_bid=10000,
        best_ask=10100,
        max_order_qty=1_000_000,
        min_qty=1,
    )
    assert result is not None
    assert result.side == "BUY"
    assert result.price_ticks == 10000


def test_market_maker_intents_both_sides():
    intents = market_maker_intents(
        agent_id="mm",
        inventory=0,
        max_inventory=1000,
        half_spread_ticks=5,
        quote_size=10,
        inventory_skew_k_bp=10_000,
        valuation_mark_ticks=10000,
        best_bid=9995,
        best_ask=10005,
    )
    assert len(intents) == 2
    assert intents[0].side == "BUY"
    assert intents[0].price_ticks == 9995
    assert intents[1].side == "SELL"
    assert intents[1].price_ticks == 10005


def test_market_maker_intents_skews_on_inventory():
    """Positive inventory at full cap -> bid suppressed, only ask emitted at lower price.

    inventory=1000, max_inventory=1000 -> inv_ratio=1.0
    skew_ticks = 10000 * 10 * 1.0 / 10000 = 10
    ask = 10000 + 10 - 10 = 10000
    bid = 10000 - 10 - 10 = 9980 (suppressed because inventory == max)
    """
    intents = market_maker_intents(
        agent_id="mm",
        inventory=1000,
        max_inventory=1000,
        half_spread_ticks=10,
        quote_size=10,
        inventory_skew_k_bp=10_000,
        valuation_mark_ticks=10000,
        best_bid=9990,
        best_ask=10010,
    )
    assert len(intents) == 1
    assert intents[0].side == "SELL"
    assert intents[0].price_ticks == 10000


def test_market_maker_intents_margin_warning_long_only_quotes_reducing_side():
    """代理策略 §8: margin_ratio_bp < maint_bp -> only the position-reducing side quotes.

    Long inventory (500) + margin_ratio_bp(400) < maint_bp(500) -> only SELL
    (reduces the long) is emitted, BUY is suppressed even though inventory is
    well under max_inventory.
    """
    intents = market_maker_intents(
        agent_id="mm",
        inventory=500,
        max_inventory=1000,
        half_spread_ticks=5,
        quote_size=10,
        inventory_skew_k_bp=0,
        valuation_mark_ticks=10000,
        best_bid=9995,
        best_ask=10005,
        margin_ratio_bp=400,
        maint_bp=500,
    )
    assert len(intents) == 1
    assert intents[0].side == "SELL"


def test_market_maker_intents_margin_warning_short_only_quotes_reducing_side():
    """Short inventory (-500) + margin_ratio_bp(400) < maint_bp(500) -> only BUY
    (reduces the short) is emitted, SELL is suppressed."""
    intents = market_maker_intents(
        agent_id="mm",
        inventory=-500,
        max_inventory=1000,
        half_spread_ticks=5,
        quote_size=10,
        inventory_skew_k_bp=0,
        valuation_mark_ticks=10000,
        best_bid=9995,
        best_ask=10005,
        margin_ratio_bp=400,
        maint_bp=500,
    )
    assert len(intents) == 1
    assert intents[0].side == "BUY"


def test_market_maker_intents_margin_ratio_above_maint_quotes_both_sides():
    """margin_ratio_bp(600) >= maint_bp(500) -> no warning, both sides still quote
    even with non-zero inventory (negative control for the two tests above)."""
    intents = market_maker_intents(
        agent_id="mm",
        inventory=500,
        max_inventory=1000,
        half_spread_ticks=5,
        quote_size=10,
        inventory_skew_k_bp=0,
        valuation_mark_ticks=10000,
        best_bid=9995,
        best_ask=10005,
        margin_ratio_bp=600,
        maint_bp=500,
    )
    assert len(intents) == 2
    assert {i.side for i in intents} == {"BUY", "SELL"}
