"""T606 (KPI-005): market validation matrix tests.

Covers every branch of ``metrics/validation.py`` with a positive (expected
verdict reached) and a negative (opposite verdict/NOT_APPLICABLE) case, per
CLAUDE.md's regression-test rule.
"""

from __future__ import annotations

import math
import random

from market_game_sim.metrics.liquidation import LiquidationMetrics
from market_game_sim.metrics.sampling import ImpactSample, MarketSample
from market_game_sim.metrics.validation import (
    MAX_FILL_RATIO,
    MIN_SAMPLE_POINTS,
    MIN_TAKER_ORDERS,
    ValidationItem,
    _pearson,
    acf,
    apply_family_correction,
    build_market_validation_matrix,
    check_fat_tails,
    check_liquidation_chain,
    check_price_impact_nonlinearity,
    check_return_autocorrelation,
    check_spread_depth_regime,
    check_volatility_clustering,
    compute_fill_ratio,
    compute_log_returns,
    excess_kurtosis,
)


def _samples(
    n: int,
    last_ticks: list[int | None] | None = None,
    spread_ticks: int | None = 2,
    mid_ticks: int | None = None,
    bid_depth_k: int = 5,
    ask_depth_k: int = 5,
    trade_count: int = 1,
) -> list[MarketSample]:
    out = []
    for i in range(n):
        lt = last_ticks[i] if last_ticks is not None else 10_000
        out.append(
            MarketSample(
                timestamp=i * 1_000_000_000,
                last_ticks=lt,
                mid_ticks=mid_ticks if mid_ticks is not None else lt,
                spread_ticks=spread_ticks,
                bid_depth_k=bid_depth_k,
                ask_depth_k=ask_depth_k,
                volume_since_last=1,
                cancel_count_since_last=0,
                trade_count_since_last=trade_count,
            )
        )
    return out


def _price_path(n: int, returns: list[float], start: int = 10_000) -> list[int]:
    prices = [start]
    p = float(start)
    for r in returns[: n - 1]:
        p *= math.exp(r)
        prices.append(max(1, round(p)))
    return prices


# ---------------------------------------------------------------------------
# excess_kurtosis / acf / _pearson -- basic sanity
# ---------------------------------------------------------------------------


def test_excess_kurtosis_of_uniform_is_negative():
    rng = random.Random(1)
    values = [rng.uniform(-1, 1) for _ in range(5000)]
    assert excess_kurtosis(values) < 0


def test_excess_kurtosis_empty_is_zero():
    assert excess_kurtosis([]) == 0.0


def test_acf_perfectly_alternating_series_is_strongly_negative_at_lag1():
    values = [1.0, -1.0] * 500
    assert acf(values, 1) < -0.9


def test_acf_rejects_out_of_range_lag():
    try:
        acf([1.0, 2.0, 3.0], 3)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_pearson_perfect_positive_correlation():
    xs = [float(i) for i in range(100)]
    ys = [2.0 * x + 1.0 for x in xs]
    assert _pearson(xs, ys) > 0.999


def test_pearson_degenerate_zero_variance_returns_zero():
    assert _pearson([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) == 0.0


# ---------------------------------------------------------------------------
# compute_log_returns / compute_fill_ratio
# ---------------------------------------------------------------------------


def test_compute_log_returns_skips_pre_trade_none_and_matches_formula():
    samples = _samples(3, last_ticks=[None, 10_000, 10_100])
    returns = compute_log_returns(samples)
    assert returns == [math.log(10_100 / 10_000)]


def test_compute_fill_ratio_all_filled_vs_none_filled():
    filled = _samples(10, trade_count=0)
    assert compute_fill_ratio(filled) == 1.0
    not_filled = _samples(10, trade_count=1)
    assert compute_fill_ratio(not_filled) == 0.0


# ---------------------------------------------------------------------------
# check_fat_tails
# ---------------------------------------------------------------------------


def test_check_fat_tails_pass_on_leptokurtic_mixture():
    rng = random.Random(42)
    returns = []
    for _ in range(2500):
        if rng.random() < 0.02:
            returns.append(rng.uniform(-0.05, 0.05))
        else:
            returns.append(rng.uniform(-0.0005, 0.0005))
    item = check_fat_tails(returns)
    assert item.verdict == "PASS"
    assert item.evidence["excess_kurtosis"] > 0


def test_check_fat_tails_fail_on_uniform_returns():
    rng = random.Random(7)
    returns = [rng.uniform(-0.001, 0.001) for _ in range(2500)]
    item = check_fat_tails(returns)
    assert item.verdict == "FAIL"


def test_check_fat_tails_not_applicable_below_min_sample():
    item = check_fat_tails([0.01] * (MIN_SAMPLE_POINTS - 1))
    assert item.verdict == "NOT_APPLICABLE"


# ---------------------------------------------------------------------------
# check_return_autocorrelation
# ---------------------------------------------------------------------------


def test_check_return_autocorrelation_pass_on_white_noise():
    rng = random.Random(11)
    returns = [rng.uniform(-0.001, 0.001) for _ in range(2500)]
    item = check_return_autocorrelation(returns)
    assert item.verdict == "PASS"


def test_check_return_autocorrelation_fail_on_ar1_process():
    rng = random.Random(11)
    returns = [0.0]
    for _ in range(2499):
        eps = rng.uniform(-0.001, 0.001)
        returns.append(0.5 * returns[-1] + eps)
    item = check_return_autocorrelation(returns)
    assert item.verdict == "FAIL"
    assert item.evidence["significant_lags"]["lag_1"] is True


def test_check_return_autocorrelation_not_applicable_below_min_sample():
    item = check_return_autocorrelation([0.001] * (MIN_SAMPLE_POINTS - 1))
    assert item.verdict == "NOT_APPLICABLE"


# ---------------------------------------------------------------------------
# check_volatility_clustering
# ---------------------------------------------------------------------------


def test_check_volatility_clustering_pass_on_regime_switching_scale():
    rng = random.Random(5)
    returns = []
    block = 50
    for i in range(2500):
        scale = 0.02 if (i // block) % 2 == 0 else 0.0002
        returns.append(rng.uniform(-scale, scale))
    item = check_volatility_clustering(returns)
    assert item.verdict == "PASS"
    assert item.evidence["acf_lag1_abs_returns"] > 0


def test_check_volatility_clustering_fail_on_constant_scale_noise():
    rng = random.Random(11)
    returns = [rng.uniform(-0.001, 0.001) for _ in range(2500)]
    item = check_volatility_clustering(returns)
    assert item.verdict == "FAIL"


def test_check_volatility_clustering_not_applicable_below_min_sample():
    item = check_volatility_clustering([0.001] * (MIN_SAMPLE_POINTS - 1))
    assert item.verdict == "NOT_APPLICABLE"


# ---------------------------------------------------------------------------
# check_price_impact_nonlinearity
# ---------------------------------------------------------------------------


def _impact_samples(
    n: int, gamma: float, rng: random.Random, scale: float = 1000.0
) -> list[ImpactSample]:
    out = []
    for i in range(1, n + 1):
        q = i
        noise = 1.0 + rng.uniform(-0.05, 0.05)
        impact_bp = max(1, round(scale * (q**gamma) * noise))
        out.append(
            ImpactSample(
                order_id=f"o{i}",
                agent_id="a1",
                side="BUY",
                quantity_units=q,
                mid_before_ticks=10_000,
                vwap_num_ticks_qty=0,
                impact_bp=impact_bp,
                slippage_cash_units=0,
            )
        )
    return out


def test_check_price_impact_nonlinearity_pass_on_concave_impact():
    rng = random.Random(3)
    samples = _impact_samples(120, gamma=0.5, rng=rng)
    item = check_price_impact_nonlinearity(samples)
    assert item.verdict == "PASS"
    assert item.statistic < 0.9  # gamma estimate should sit well below 1


def test_check_price_impact_nonlinearity_fail_on_linear_impact():
    rng = random.Random(3)
    samples = _impact_samples(120, gamma=1.0, rng=rng)
    item = check_price_impact_nonlinearity(samples)
    assert item.verdict == "FAIL"


def test_check_price_impact_nonlinearity_not_applicable_below_min_orders():
    rng = random.Random(3)
    samples = _impact_samples(MIN_TAKER_ORDERS - 1, gamma=0.5, rng=rng)
    item = check_price_impact_nonlinearity(samples)
    assert item.verdict == "NOT_APPLICABLE"


def test_check_price_impact_nonlinearity_not_applicable_when_degenerate_quantity():
    samples = [
        ImpactSample(
            order_id=f"o{i}",
            agent_id="a1",
            side="BUY",
            quantity_units=10,
            mid_before_ticks=10_000,
            vwap_num_ticks_qty=0,
            impact_bp=5,
            slippage_cash_units=0,
        )
        for i in range(MIN_TAKER_ORDERS + 5)
    ]
    item = check_price_impact_nonlinearity(samples)
    assert item.verdict == "NOT_APPLICABLE"


# ---------------------------------------------------------------------------
# check_spread_depth_regime
# ---------------------------------------------------------------------------


def _regime_switch_prices(n: int, rng: random.Random) -> list[int]:
    prices = [10_000]
    for i in range(1, n):
        low_vol = i < n // 2
        step = rng.randint(-1, 1) if low_vol else rng.choice([-1, 1]) * rng.randint(20, 50)
        prices.append(max(1, prices[-1] + step))
    return prices


def test_check_spread_depth_regime_pass_when_spread_tracks_volatility():
    rng = random.Random(9)
    n = 2500
    prices = _regime_switch_prices(n, rng)
    spreads = [2 if i < n // 2 else 40 for i in range(n)]
    samples = [
        MarketSample(
            timestamp=i * 1_000_000_000,
            last_ticks=prices[i],
            mid_ticks=prices[i],
            spread_ticks=spreads[i],
            bid_depth_k=5,
            ask_depth_k=5,
            volume_since_last=1,
            cancel_count_since_last=0,
            trade_count_since_last=1,
        )
        for i in range(n)
    ]
    item = check_spread_depth_regime(samples)
    assert item.verdict == "PASS"
    assert item.evidence["range_ok"] is True
    assert item.evidence["depth_ok"] is True


def test_check_spread_depth_regime_fail_when_spread_out_of_range():
    rng = random.Random(9)
    n = 2500
    prices = _regime_switch_prices(n, rng)
    samples = [
        MarketSample(
            timestamp=i * 1_000_000_000,
            last_ticks=prices[i],
            mid_ticks=prices[i],
            spread_ticks=800,  # 8% of mid 10_000, exceeds 5% cap
            bid_depth_k=5,
            ask_depth_k=5,
            volume_since_last=1,
            cancel_count_since_last=0,
            trade_count_since_last=1,
        )
        for i in range(n)
    ]
    item = check_spread_depth_regime(samples)
    assert item.verdict == "FAIL"
    assert item.evidence["range_ok"] is False


def test_check_spread_depth_regime_fail_when_depth_empty():
    samples = _samples(2500, ask_depth_k=0)
    item = check_spread_depth_regime(samples)
    assert item.verdict == "FAIL"
    assert item.evidence["depth_ok"] is False


def test_check_spread_depth_regime_fail_when_spread_uncorrelated_with_volatility():
    rng = random.Random(9)
    n = 2500
    prices = _regime_switch_prices(n, rng)
    samples = [
        MarketSample(
            timestamp=i * 1_000_000_000,
            last_ticks=prices[i],
            mid_ticks=prices[i],
            spread_ticks=2,  # constant regardless of the volatility regime switch
            bid_depth_k=5,
            ask_depth_k=5,
            volume_since_last=1,
            cancel_count_since_last=0,
            trade_count_since_last=1,
        )
        for i in range(n)
    ]
    item = check_spread_depth_regime(samples)
    assert item.verdict == "FAIL"
    assert item.evidence["corr"] is not None


def test_check_spread_depth_regime_not_applicable_below_min_sample():
    item = check_spread_depth_regime(_samples(MIN_SAMPLE_POINTS - 1))
    assert item.verdict == "NOT_APPLICABLE"


def test_check_spread_depth_regime_not_applicable_when_spread_never_defined():
    item = check_spread_depth_regime(_samples(2500, spread_ticks=None))
    assert item.verdict == "NOT_APPLICABLE"


# ---------------------------------------------------------------------------
# check_liquidation_chain
# ---------------------------------------------------------------------------


def test_check_liquidation_chain_pass_on_consistent_metrics():
    metrics = LiquidationMetrics(
        total_liquidations=3,
        total_volume=200,
        liquidation_volume=50,
        chain_depth_counts={1: 2, 2: 1},
        bankruptcy_total=1,
    )
    item = check_liquidation_chain(metrics)
    assert item.verdict == "PASS"


def test_check_liquidation_chain_fail_on_inconsistent_chain_depth():
    metrics = LiquidationMetrics(
        total_liquidations=1,
        total_volume=200,
        liquidation_volume=50,
        chain_depth_counts={0: 1},  # depth 0 is not a valid chain
        bankruptcy_total=0,
    )
    item = check_liquidation_chain(metrics)
    assert item.verdict == "FAIL"


def test_check_liquidation_chain_fail_when_liquidation_volume_exceeds_total():
    metrics = LiquidationMetrics(
        total_liquidations=1,
        total_volume=10,
        liquidation_volume=50,
        chain_depth_counts={1: 1},
        bankruptcy_total=0,
    )
    item = check_liquidation_chain(metrics)
    assert item.verdict == "FAIL"


def test_check_liquidation_chain_not_applicable_when_no_liquidations():
    item = check_liquidation_chain(LiquidationMetrics())
    assert item.verdict == "NOT_APPLICABLE"


# ---------------------------------------------------------------------------
# apply_family_correction
# ---------------------------------------------------------------------------


def _item(name: str, verdict: str, p_value: float | None) -> ValidationItem:
    return ValidationItem(name, verdict, 2.0, p_value, "desc", {})


def test_apply_family_correction_downgrades_marginal_items_but_keeps_strongest():
    items = {
        "fat_tails": _item("fat_tails", "PASS", 0.04),
        "volatility_clustering": _item("volatility_clustering", "PASS", 0.03),
        "price_impact_nonlinearity": _item("price_impact_nonlinearity", "PASS", 0.02),
        "spread_depth_regime": _item("spread_depth_regime", "PASS", 0.01),
        "return_autocorrelation": _item("return_autocorrelation", "PASS", 0.001),
        "liquidation_chain": _item("liquidation_chain", "PASS", None),
    }
    corrected = apply_family_correction(items)
    assert corrected["spread_depth_regime"].verdict == "PASS"  # smallest p, survives step-down
    assert corrected["price_impact_nonlinearity"].verdict == "FAIL"
    assert corrected["volatility_clustering"].verdict == "FAIL"
    assert corrected["fat_tails"].verdict == "FAIL"
    assert "Holm-Bonferroni" in corrected["fat_tails"].threshold_desc


def test_apply_family_correction_leaves_non_family_and_non_pass_items_untouched():
    items = {
        "fat_tails": _item("fat_tails", "FAIL", 0.001),  # already FAIL, must not be "upgraded"
        "volatility_clustering": _item("volatility_clustering", "NOT_APPLICABLE", None),
        "price_impact_nonlinearity": _item("price_impact_nonlinearity", "PASS", 0.9),
        "spread_depth_regime": _item("spread_depth_regime", "PASS", 0.8),
        "return_autocorrelation": _item("return_autocorrelation", "PASS", 0.0001),
    }
    corrected = apply_family_correction(items)
    assert corrected["fat_tails"].verdict == "FAIL"
    assert corrected["volatility_clustering"].verdict == "NOT_APPLICABLE"
    # return_autocorrelation sits outside the family: its tiny p-value must not
    # affect anything nor be touched itself, despite being the smallest p overall.
    assert corrected["return_autocorrelation"].verdict == "PASS"


# ---------------------------------------------------------------------------
# build_market_validation_matrix
# ---------------------------------------------------------------------------


def test_build_market_validation_matrix_fill_ratio_gate_marks_return_items_not_applicable():
    n = 2500
    samples = [
        MarketSample(
            timestamp=i * 1_000_000_000,
            last_ticks=10_000 + i,
            mid_ticks=10_000 + i,
            spread_ticks=2,
            bid_depth_k=5,
            ask_depth_k=5,
            volume_since_last=1,
            cancel_count_since_last=0,
            trade_count_since_last=0 if i % 2 == 0 else 1,  # 50% forward-filled > 30% cap
        )
        for i in range(n)
    ]
    matrix = build_market_validation_matrix(samples, [], LiquidationMetrics())
    assert matrix.fill_ratio_ok is False
    assert matrix.fill_ratio > MAX_FILL_RATIO
    for name in (
        "fat_tails",
        "return_autocorrelation",
        "volatility_clustering",
        "spread_depth_regime",
    ):
        assert matrix.items[name].verdict == "NOT_APPLICABLE"
        assert "填充比例" in matrix.items[name].threshold_desc


def test_build_market_validation_matrix_computes_items_when_fill_ratio_ok():
    rng = random.Random(42)
    returns = []
    for _ in range(2500):
        if rng.random() < 0.02:
            returns.append(rng.uniform(-0.05, 0.05))
        else:
            returns.append(rng.uniform(-0.0005, 0.0005))
    prices = _price_path(2500, returns)
    samples = [
        MarketSample(
            timestamp=i * 1_000_000_000,
            last_ticks=prices[i],
            mid_ticks=prices[i],
            spread_ticks=2,
            bid_depth_k=5,
            ask_depth_k=5,
            volume_since_last=1,
            cancel_count_since_last=0,
            trade_count_since_last=1,
        )
        for i in range(2500)
    ]
    matrix = build_market_validation_matrix(samples, [], LiquidationMetrics())
    assert matrix.fill_ratio_ok is True
    assert matrix.items["fat_tails"].verdict in ("PASS", "FAIL")
    assert matrix.items["price_impact_nonlinearity"].verdict == "NOT_APPLICABLE"
    assert matrix.items["liquidation_chain"].verdict == "NOT_APPLICABLE"


def test_market_validation_matrix_as_dict_round_trips_item_fields():
    matrix = build_market_validation_matrix(_samples(10), [], LiquidationMetrics())
    d = matrix.as_dict()
    assert set(d["items"]) == {
        "fat_tails",
        "return_autocorrelation",
        "volatility_clustering",
        "price_impact_nonlinearity",
        "spread_depth_regime",
        "liquidation_chain",
    }
    assert d["items"]["fat_tails"]["verdict"] == "NOT_APPLICABLE"
