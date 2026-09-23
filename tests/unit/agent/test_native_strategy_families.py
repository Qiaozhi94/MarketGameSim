"""0.4.1 T968/T969 (FR-503 / AC-503): the four native strategy families.

Every family is asserted on both sides: the market state its semantics say it
acts on, *and* the state where it must stay out (no signal / no history / no
budget / no mark).  A family that only had its "acts" side asserted could be
reduced to "always trade" without a test going red.

``market_maker_v2`` additionally has to disperse: the v1 makers all quoted the
same two ticks, which is the single-level book the quality gate fails on, so
dispersion is asserted explicitly rather than assumed from the draw.

The last block runs all four side by side on one market state -- multiple
families, multiple decisions in flight is where a shared-state or tier bug
shows up, not in single-family calls.
"""

from __future__ import annotations

import pytest

from market_game_sim.agent.goal import (
    AgentInternalStateV1,
    AgentPreferences,
    BookTop,
    CompletedBar,
    InformationSetV1,
    OwnAccountView,
    PublicTrade,
)
from market_game_sim.agent.strategy_layer.families import (
    NATIVE_FAMILY_IDS,
    MarketMakerV2,
    MeanReversion,
    SentimentNoise,
    TrendFollowing,
    build_native_families,
    register_native_families,
)
from market_game_sim.agent.strategy_layer.families.trend_following import TIME_SCALES
from market_game_sim.agent.strategy_layer.protocol import (
    ACTION_NO_ACTION,
    ACTION_ORDER_INTENT,
    ACTION_TARGET_POSITION,
    InformationTier,
    StrategyLayerError,
    crop_information_set,
)
from market_game_sim.agent.strategy_layer.registry import StrategyRegistry

MASTER_SEED = 4242
PREFS = AgentPreferences(risk_appetite_x1000=1000)


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #


def make_state(
    agent_id: str = "a-1",
    *,
    decision_index: int = 0,
    master_seed: int | None = MASTER_SEED,
    time_scale_index: int | None = None,
    drop_agent_id: bool = False,
) -> AgentInternalStateV1:
    bag: dict[str, object] = {}
    if master_seed is not None:
        bag["master_seed"] = master_seed
    if not drop_agent_id:
        bag["agent_id"] = agent_id
    bag["decision_index"] = decision_index
    if time_scale_index is not None:
        bag["time_scale_index"] = time_scale_index
    return AgentInternalStateV1(
        schema_version=1,
        last_seen_market_event_id="evt-0",
        ewma_value_units=None,
        ewma_sample_count=0,
        model_private_state=bag,
    )


def make_info(
    tier: InformationTier,
    *,
    best_bid: int | None = 99,
    best_ask: int | None = 101,
    wallet_units: int = 1_000_000,
    position_units: int = 0,
    trade_prices: tuple[int, ...] = (),
    bar_closes: tuple[int, ...] = (),
):
    """Crop a real ``InformationSetV1`` down to ``tier`` (the L2 seam)."""
    mark_half = None if best_bid is None or best_ask is None else best_bid + best_ask
    raw = InformationSetV1(
        schema_version=1,
        cursor_from_event_id="evt-0",
        cursor_to_event_id="evt-1",
        public_trades=tuple(
            PublicTrade(price_ticks=p, quantity_units=1, timestamp=i)
            for i, p in enumerate(trade_prices)
        ),
        completed_bars=tuple(
            CompletedBar(open=c, high=c, low=c, close=c, volume=1, trade_count=1)
            for c in bar_closes
        ),
        book_top=BookTop(best_bid=best_bid, best_ask=best_ask, valuation_mark_half_ticks=mark_half),
        own_account=OwnAccountView(
            wallet_units=wallet_units,
            position_units=position_units,
            entry_notional_units=0,
        ),
    )
    return crop_information_set(raw, tier, observed_at=1_000)


def rising_closes(n: int = 60) -> tuple[int, ...]:
    return tuple(100 + 2 * i for i in range(n))


def falling_closes(n: int = 60) -> tuple[int, ...]:
    return tuple(300 - 2 * i for i in range(n))


# --------------------------------------------------------------------------- #
# T968: trend following
# --------------------------------------------------------------------------- #


def test_trend_following_goes_long_on_an_uptrend():
    family = TrendFollowing()
    info = make_info(InformationTier.I2, bar_closes=rising_closes())
    decision = family.decide(info, make_state(), PREFS)
    assert decision.action == ACTION_TARGET_POSITION
    assert decision.target_position_units > 0
    assert decision.family_id == "trend_following"
    assert decision.info_tier is InformationTier.I2


def test_trend_following_goes_short_on_a_downtrend():
    family = TrendFollowing()
    info = make_info(InformationTier.I2, bar_closes=falling_closes())
    decision = family.decide(info, make_state(), PREFS)
    assert decision.action == ACTION_TARGET_POSITION
    assert decision.target_position_units < 0


def test_trend_following_stays_out_when_the_averages_are_flat():
    family = TrendFollowing()
    info = make_info(InformationTier.I2, bar_closes=(150,) * 60)
    decision = family.decide(info, make_state(), PREFS)
    assert decision.action == ACTION_NO_ACTION
    assert decision.reason_code == "NO_SIGNAL"
    assert decision.target_position_units is None


def test_trend_following_needs_a_full_slow_window():
    family = TrendFollowing()
    info = make_info(InformationTier.I2, bar_closes=rising_closes(5))
    decision = family.decide(info, make_state(), PREFS)
    assert decision.action == ACTION_NO_ACTION
    assert decision.reason_code == "INSUFFICIENT_HISTORY"


def test_trend_following_time_scales_can_disagree_on_the_same_bars():
    """Short horizon long, long horizon short -- the point of multi time scale."""
    family = TrendFollowing()
    closes = tuple([300 - 2 * i for i in range(45)] + [210 + 3 * i for i in range(15)])
    info = make_info(InformationTier.I2, bar_closes=closes)
    fast = family.decide(info, make_state(time_scale_index=0), PREFS)
    slow = family.decide(info, make_state(time_scale_index=2), PREFS)
    assert fast.target_position_units > 0
    assert slow.target_position_units < 0


def test_trend_following_rejects_an_unknown_time_scale_index():
    family = TrendFollowing()
    info = make_info(InformationTier.I2, bar_closes=rising_closes())
    with pytest.raises(StrategyLayerError) as excinfo:
        family.decide(info, make_state(time_scale_index=len(TIME_SCALES)), PREFS)
    assert excinfo.value.code == "INVALID_TIME_SCALE"


def test_trend_following_skips_without_a_valuation_mark():
    family = TrendFollowing()
    info = make_info(InformationTier.I2, best_bid=None, best_ask=None, bar_closes=rising_closes())
    decision = family.decide(info, make_state(), PREFS)
    assert decision.action == ACTION_NO_ACTION
    assert decision.reason_code == "NO_VALUATION_MARK"


def test_trend_following_skips_without_a_risk_budget():
    family = TrendFollowing()
    info = make_info(InformationTier.I2, wallet_units=0, bar_closes=rising_closes())
    decision = family.decide(info, make_state(), PREFS)
    assert decision.action == ACTION_NO_ACTION
    assert decision.reason_code == "NO_RISK_BUDGET"


def test_trend_following_rejects_invalid_params():
    with pytest.raises(StrategyLayerError) as excinfo:
        TrendFollowing(entry_threshold_bp=0)
    assert excinfo.value.code == "INVALID_FAMILY_PARAMS"
    with pytest.raises(StrategyLayerError):
        TrendFollowing(k_x1000=1001)
    assert TrendFollowing(entry_threshold_bp=1, k_x1000=1000).k_x1000 == 1000


# --------------------------------------------------------------------------- #
# T968: mean reversion
# --------------------------------------------------------------------------- #


def test_mean_reversion_fades_a_price_above_the_window_mean():
    family = MeanReversion()
    prices = tuple([100] * 19 + [130])
    info = make_info(InformationTier.I1, trade_prices=prices)
    decision = family.decide(info, make_state(), PREFS)
    assert decision.action == ACTION_TARGET_POSITION
    assert decision.target_position_units < 0
    assert decision.family_id == "mean_reversion"


def test_mean_reversion_buys_a_price_below_the_window_mean():
    family = MeanReversion()
    prices = tuple([100] * 19 + [70])
    info = make_info(InformationTier.I1, trade_prices=prices)
    decision = family.decide(info, make_state(), PREFS)
    assert decision.action == ACTION_TARGET_POSITION
    assert decision.target_position_units > 0


def test_mean_reversion_stays_out_inside_the_band():
    family = MeanReversion(entry_threshold_bp=300)
    prices = tuple([100] * 19 + [101])
    info = make_info(InformationTier.I1, trade_prices=prices)
    decision = family.decide(info, make_state(), PREFS)
    assert decision.action == ACTION_NO_ACTION
    assert decision.reason_code == "NO_SIGNAL"


def test_mean_reversion_needs_a_full_window():
    family = MeanReversion()
    info = make_info(InformationTier.I1, trade_prices=(100, 130))
    decision = family.decide(info, make_state(), PREFS)
    assert decision.action == ACTION_NO_ACTION
    assert decision.reason_code == "INSUFFICIENT_HISTORY"


def test_mean_reversion_rejects_invalid_params():
    with pytest.raises(StrategyLayerError) as excinfo:
        MeanReversion(window_trades=1)
    assert excinfo.value.code == "INVALID_FAMILY_PARAMS"
    assert MeanReversion(window_trades=2).window_trades == 2


# --------------------------------------------------------------------------- #
# T969: sentiment noise
# --------------------------------------------------------------------------- #


def test_sentiment_noise_is_deterministic_for_the_same_key():
    family = SentimentNoise()
    info = make_info(InformationTier.I0)
    first = family.decide(info, make_state("noise-1"), PREFS)
    second = family.decide(info, make_state("noise-1"), PREFS)
    assert first.action == second.action
    assert first.target_position_units == second.target_position_units


def test_sentiment_noise_disagrees_across_agents_and_decisions():
    family = SentimentNoise()
    moods = {family.mood_x1000(make_state(f"n-{i}")) for i in range(12)}
    assert len(moods) == 12, "each agent must draw its own mood"
    over_time = {family.mood_x1000(make_state("n-0", decision_index=d)) for d in range(8)}
    assert len(over_time) == 8, "the mood must move with decision_index"


def test_sentiment_noise_takes_both_sides_across_the_population():
    family = SentimentNoise()
    info = make_info(InformationTier.I0)
    targets = [
        family.decide(info, make_state(f"n-{i}"), PREFS).target_position_units for i in range(12)
    ]
    assert any(t is not None and t > 0 for t in targets)
    assert any(t is not None and t < 0 for t in targets)


def test_sentiment_noise_stays_out_inside_the_neutral_band():
    family = SentimentNoise(neutral_band_x1000=999)
    info = make_info(InformationTier.I0)
    decision = family.decide(info, make_state("n-0"), PREFS)
    assert decision.action == ACTION_NO_ACTION
    assert decision.reason_code == "NO_SIGNAL"


def test_sentiment_noise_skips_without_a_valuation_mark():
    family = SentimentNoise()
    info = make_info(InformationTier.I0, best_bid=None, best_ask=None)
    decision = family.decide(info, make_state("n-0"), PREFS)
    assert decision.action == ACTION_NO_ACTION
    assert decision.reason_code == "NO_VALUATION_MARK"


@pytest.mark.parametrize("kwargs", [{"master_seed": None}, {"drop_agent_id": True}])
def test_sentiment_noise_fails_closed_without_a_draw_context(kwargs):
    family = SentimentNoise()
    info = make_info(InformationTier.I0)
    with pytest.raises(StrategyLayerError) as excinfo:
        family.decide(info, make_state("n-0", **kwargs), PREFS)
    assert excinfo.value.code == "MISSING_DRAW_CONTEXT"


# --------------------------------------------------------------------------- #
# T969: market maker v2
# --------------------------------------------------------------------------- #


def test_market_maker_quotes_a_limit_order_on_the_parity_side():
    family = MarketMakerV2()
    info = make_info(InformationTier.I0)
    buy = family.decide(info, make_state("mm-1", decision_index=0), PREFS)
    sell = family.decide(info, make_state("mm-1", decision_index=1), PREFS)
    assert buy.action == ACTION_ORDER_INTENT
    assert buy.order_intent.side == "BUY"
    assert buy.order_intent.order_type == "LIMIT"
    assert sell.order_intent.side == "SELL"
    assert buy.order_intent.price_ticks < sell.order_intent.price_ticks


def test_market_maker_quotes_are_dispersed_across_agents():
    """The v1 failure mode: every maker on the same tick -> single-level book."""
    family = MarketMakerV2()
    info = make_info(InformationTier.I0)
    prices = [
        family.decide(info, make_state(f"mm-{i}", decision_index=0), PREFS).order_intent.price_ticks
        for i in range(12)
    ]
    sizes = [
        family.decide(
            info, make_state(f"mm-{i}", decision_index=0), PREFS
        ).order_intent.quantity_units
        for i in range(12)
    ]
    assert len(set(prices)) >= 3, f"bids collapsed onto {sorted(set(prices))}"
    assert len(set(sizes)) >= 2, f"sizes collapsed onto {sorted(set(sizes))}"


def test_market_maker_dispersion_is_stable_for_one_agent():
    family = MarketMakerV2()
    info = make_info(InformationTier.I0)
    first = family.decide(info, make_state("mm-3", decision_index=0), PREFS)
    later = family.decide(info, make_state("mm-3", decision_index=2), PREFS)
    assert first.order_intent.price_ticks == later.order_intent.price_ticks
    assert first.order_intent.quantity_units == later.order_intent.quantity_units


def test_market_maker_inventory_cap_overrides_the_parity_side():
    family = MarketMakerV2(max_inventory=10)
    long_info = make_info(InformationTier.I0, position_units=10)
    short_info = make_info(InformationTier.I0, position_units=-10)
    # decision_index 0 is the BUY parity; inventory must override both ways.
    assert family.decide(long_info, make_state("mm-1"), PREFS).order_intent.side == "SELL"
    assert (
        family.decide(short_info, make_state("mm-1", decision_index=1), PREFS).order_intent.side
        == "BUY"
    )


def test_market_maker_skews_quotes_against_its_inventory():
    family = MarketMakerV2()
    flat = make_info(InformationTier.I0, position_units=0)
    long_book = make_info(InformationTier.I0, position_units=8)
    flat_ask = family.decide(flat, make_state("mm-2", decision_index=1), PREFS)
    long_ask = family.decide(long_book, make_state("mm-2", decision_index=1), PREFS)
    assert long_ask.order_intent.price_ticks < flat_ask.order_intent.price_ticks


def test_market_maker_skips_without_a_valuation_mark():
    family = MarketMakerV2()
    info = make_info(InformationTier.I0, best_bid=None, best_ask=None)
    decision = family.decide(info, make_state("mm-1"), PREFS)
    assert decision.action == ACTION_NO_ACTION
    assert decision.reason_code == "NO_VALUATION_MARK"
    assert decision.order_intent is None


def test_market_maker_fails_closed_without_a_draw_context():
    family = MarketMakerV2()
    info = make_info(InformationTier.I0)
    with pytest.raises(StrategyLayerError) as excinfo:
        family.decide(info, make_state("mm-1", master_seed=None), PREFS)
    assert excinfo.value.code == "MISSING_DRAW_CONTEXT"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"base_half_spread_ticks": 0},
        {"half_spread_dispersion_ticks": 4},  # >= base_half_spread_ticks (4)
        {"base_quote_size": 0},
        {"quote_size_dispersion": 2},  # >= base_quote_size (2)
        {"max_inventory": 0},
        {"inventory_skew_k_bp": -1},
    ],
)
def test_market_maker_rejects_invalid_params(kwargs):
    with pytest.raises(StrategyLayerError) as excinfo:
        MarketMakerV2(**kwargs)
    assert excinfo.value.code == "INVALID_FAMILY_PARAMS"


def test_market_maker_accepts_the_dispersion_boundary():
    family = MarketMakerV2(base_half_spread_ticks=4, half_spread_dispersion_ticks=3)
    assert family.half_spread_dispersion_ticks == 3


# --------------------------------------------------------------------------- #
# Registration and the four families side by side
# --------------------------------------------------------------------------- #


def test_register_native_families_registers_all_four():
    registry = register_native_families(StrategyRegistry())
    assert set(registry.family_ids()) == set(NATIVE_FAMILY_IDS)


def test_registering_twice_into_one_registry_fails_closed():
    registry = register_native_families(StrategyRegistry())
    with pytest.raises(StrategyLayerError) as excinfo:
        register_native_families(registry)
    assert excinfo.value.code == "DUPLICATE_STRATEGY_FAMILY"


def test_every_family_declares_the_tier_it_reads():
    tiers = {s.family_id: s.info_tier for s in build_native_families()}
    assert tiers == {
        "trend_following": InformationTier.I2,
        "mean_reversion": InformationTier.I1,
        "sentiment_noise": InformationTier.I0,
        "market_maker_v2": InformationTier.I0,
    }


def test_four_families_decide_side_by_side_without_cross_talk():
    """Multi-family batch: same market, four decisions, no shared state."""
    registry = register_native_families(StrategyRegistry())
    closes = rising_closes()
    prices = tuple([100] * 19 + [130])
    infos = {
        "trend_following": make_info(InformationTier.I2, bar_closes=closes, trade_prices=prices),
        "mean_reversion": make_info(InformationTier.I1, trade_prices=prices),
        "sentiment_noise": make_info(InformationTier.I0),
        "market_maker_v2": make_info(InformationTier.I0),
    }
    decisions = {
        family_id: registry.decide(family_id, infos[family_id], make_state(f"{family_id}-1"), PREFS)
        for family_id in NATIVE_FAMILY_IDS
    }
    for family_id, decision in decisions.items():
        assert decision.family_id == family_id
        assert decision.info_tier is infos[family_id].tier
    # The informed families disagree on this state: trend is long, the
    # reversion family fades the spike.  That disagreement is the point.
    assert decisions["trend_following"].target_position_units > 0
    assert decisions["mean_reversion"].target_position_units < 0
    assert decisions["market_maker_v2"].action == ACTION_ORDER_INTENT

    # Re-running the batch reproduces it point for point (NFR-502).
    again = {
        family_id: registry.decide(family_id, infos[family_id], make_state(f"{family_id}-1"), PREFS)
        for family_id in NATIVE_FAMILY_IDS
    }
    assert {f: d.target_position_units for f, d in again.items()} == {
        f: d.target_position_units for f, d in decisions.items()
    }
    assert again["market_maker_v2"].order_intent == decisions["market_maker_v2"].order_intent


def test_registry_rejects_an_information_set_above_the_declared_tier():
    registry = register_native_families(StrategyRegistry())
    too_rich = make_info(InformationTier.I2, bar_closes=rising_closes())
    with pytest.raises(StrategyLayerError) as excinfo:
        registry.decide("sentiment_noise", too_rich, make_state("n-0"), PREFS)
    assert excinfo.value.code == "INFO_TIER_MISMATCH"
