"""0.4.1 T971 (FR-505 / SC-502 / AC-505): stylized facts 五项度量测试.

Every fact gets both sides on synthetic control series: a series that is known
to carry the feature must be judged PASS, and one that is known not to carry it
must be judged FAIL (or NOT_APPLICABLE when the sample cannot support the
test).  Two further guards protect the caliber itself:

* the Holm-Bonferroni family correction really downgrades a raw PASS
  (``test_family_correction_downgrades_marginal_passes``);
* KPI-005's frozen family (``validation._FAMILY_A``) is untouched by this
  milestone (AC-505's guard assertion).
"""

from __future__ import annotations

import math
import random

import pytest

from market_game_sim.metrics import market_quality as mq
from market_game_sim.metrics.sampling import MarketSample
from market_game_sim.metrics.validation import (
    _FAMILY_A,
    ALPHA,
    MAX_FILL_RATIO,
    MIN_SAMPLE_POINTS,
    abs_return_acf,
    build_stylized_facts,
    check_order_flow_long_memory,
    check_volatility_clustering_lags,
    check_volume_volatility_correlation,
)

N = 4000  # > MIN_SAMPLE_POINTS, and > ORDER_FLOW_MAX_LAG


# --------------------------------------------------------------------------- #
# Synthetic control series
# --------------------------------------------------------------------------- #


def _normal_returns(n: int = N, seed: int = 20260923) -> list[float]:
    """Independent normal returns: no fat tails, no clustering, no memory."""
    rng = random.Random(seed)
    return [rng.gauss(0.0, 0.01) for _ in range(n)]


def _fat_tailed_returns(n: int = N, seed: int = 11) -> list[float]:
    """Normal mixture: 5% of draws come from a 6x wider normal."""
    rng = random.Random(seed)
    return [rng.gauss(0.0, 0.06 if rng.random() < 0.05 else 0.01) for _ in range(n)]


def _clustered_returns(n: int = N, seed: int = 7) -> list[float]:
    """Slowly varying volatility (period 1000 >> lag 50) => |r| stays
    autocorrelated well past lag 50."""
    rng = random.Random(seed)
    return [
        rng.gauss(0.0, 0.01 * (1.0 + 0.9 * math.sin(2 * math.pi * t / 1000.0))) for t in range(n)
    ]


def _ar1_returns(n: int = N, seed: int = 5, phi: float = 0.3) -> list[float]:
    rng = random.Random(seed)
    out = [rng.gauss(0.0, 0.01)]
    for _ in range(n - 1):
        out.append(phi * out[-1] + rng.gauss(0.0, 0.01))
    return out


def _samples_from_returns(
    returns: list[float],
    volumes: list[int],
    *,
    trade_count: int = 1,
    start_ticks: int = 10_000,
) -> list[MarketSample]:
    """MarketSample series whose ``last_ticks`` reproduces ``returns``."""
    price = float(start_ticks)
    out: list[MarketSample] = []
    for i, (r, vol) in enumerate(zip(returns, volumes, strict=True)):
        price = max(2.0, price * math.exp(r))
        ticks = int(round(price))
        out.append(
            MarketSample(
                timestamp=i * 1_000_000,
                last_ticks=ticks,
                mid_ticks=ticks,
                spread_ticks=2,
                bid_depth_k=5,
                ask_depth_k=5,
                volume_since_last=vol,
                cancel_count_since_last=0,
                trade_count_since_last=trade_count,
            )
        )
    return out


def _volume_tracking_volatility(returns: list[float], seed: int = 3) -> list[int]:
    """Volume driven by the same slow volatility factor as ``returns``."""
    rng = random.Random(seed)
    return [max(1, int(200 * abs(r) / 0.01 + rng.uniform(0, 5))) for r in returns]


def _volume_independent(returns: list[float], seed: int = 4) -> list[int]:
    rng = random.Random(seed)
    return [max(1, int(rng.uniform(80, 120))) for _ in returns]


def _persistent_signs(n: int = N, period: int = 4000) -> list[int]:
    """Square wave: buys and sells arrive in long runs, so the sign ACF stays
    positive through lag 100 and decays like a power law in log-log."""
    return [1 if math.sin(2 * math.pi * t / period) >= 0 else -1 for t in range(n)]


def _alternating_signs(n: int = N) -> list[int]:
    return [1 if t % 2 == 0 else -1 for t in range(n)]


# --------------------------------------------------------------------------- #
# Fact 1: fat tails (reuses check_fat_tails)
# --------------------------------------------------------------------------- #


def test_fat_tails_passes_on_a_known_fat_tailed_series():
    facts = build_stylized_facts(
        _samples_from_returns(_fat_tailed_returns(), _volume_independent(_fat_tailed_returns())),
        _persistent_signs(),
    )
    fact = facts[mq.FAT_TAILS]
    assert fact.raw_verdict == mq.PASS
    assert fact.p_value < ALPHA
    assert fact.evidence["excess_kurtosis"] > 0


def test_fat_tails_fails_on_independent_normal_returns():
    returns = _normal_returns()
    facts = build_stylized_facts(
        _samples_from_returns(returns, _volume_independent(returns)), _persistent_signs()
    )
    fact = facts[mq.FAT_TAILS]
    assert fact.raw_verdict == mq.FAIL
    assert fact.p_value >= ALPHA


# --------------------------------------------------------------------------- #
# Fact 2: no linear return autocorrelation (reuses check_return_autocorrelation)
# --------------------------------------------------------------------------- #


def test_return_autocorrelation_passes_on_independent_returns():
    returns = _normal_returns()
    facts = build_stylized_facts(
        _samples_from_returns(returns, _volume_independent(returns)), _persistent_signs()
    )
    assert facts[mq.RETURN_AUTOCORRELATION].raw_verdict == mq.PASS


def test_return_autocorrelation_fails_on_ar1_returns():
    returns = _ar1_returns()
    facts = build_stylized_facts(
        _samples_from_returns(returns, _volume_independent(returns)), _persistent_signs()
    )
    fact = facts[mq.RETURN_AUTOCORRELATION]
    assert fact.raw_verdict == mq.FAIL
    assert fact.evidence["acf"]["lag_1"] > 0


# --------------------------------------------------------------------------- #
# Fact 3: volatility clustering at lag 1 AND lag 50 (Q-505)
# --------------------------------------------------------------------------- #


def test_volatility_clustering_passes_when_both_lags_are_significant():
    fact = check_volatility_clustering_lags(_clustered_returns())
    assert fact.raw_verdict == mq.PASS
    assert fact.evidence["acf_lag1"] > 0
    assert fact.evidence["acf_lag50"] > 0
    # p entering family A is the *worse* of the two lags (Q-505).
    assert fact.p_value == max(fact.evidence["p_lag1"], fact.evidence["p_lag50"])


def test_volatility_clustering_fails_on_independent_returns():
    fact = check_volatility_clustering_lags(_normal_returns())
    assert fact.raw_verdict == mq.FAIL
    assert fact.p_value >= ALPHA


def test_volatility_clustering_lag50_alone_can_fail_the_fact():
    """Fast-mean-reverting volatility: lag 1 is significant, lag 50 is not, so
    the intersection rule fails the fact even though 0.1.2's lag-1-only check
    would pass it."""
    rng = random.Random(99)
    returns = [
        rng.gauss(0.0, 0.01 * (1.0 + 0.9 * math.sin(2 * math.pi * t / 6.0))) for t in range(N)
    ]
    acf1, p1 = abs_return_acf(returns, 1)
    acf50, p50 = abs_return_acf(returns, 50)
    assert p1 < ALPHA and acf1 > 0  # lag 1 alone would pass
    fact = check_volatility_clustering_lags(returns)
    assert fact.raw_verdict == mq.FAIL
    assert p50 >= ALPHA or acf50 <= 0


def test_volatility_clustering_is_not_applicable_below_min_sample():
    short = _clustered_returns(n=MIN_SAMPLE_POINTS - 1)
    assert abs_return_acf(short, 1) == (None, None)
    assert check_volatility_clustering_lags(short).raw_verdict == mq.NOT_APPLICABLE


# --------------------------------------------------------------------------- #
# Fact 4: volume-volatility correlation (new)
# --------------------------------------------------------------------------- #


def test_volume_volatility_correlation_passes_when_volume_tracks_volatility():
    returns = _clustered_returns()
    samples = _samples_from_returns(returns, _volume_tracking_volatility(returns))
    fact = check_volume_volatility_correlation(samples)
    assert fact.raw_verdict == mq.PASS
    assert fact.statistic > 0
    assert fact.p_value < ALPHA
    assert fact.evidence["window"] == mq.VOLUME_VOLATILITY_WINDOW


def test_volume_volatility_correlation_fails_when_volume_is_independent():
    returns = _clustered_returns()
    samples = _samples_from_returns(returns, _volume_independent(returns))
    fact = check_volume_volatility_correlation(samples)
    assert fact.raw_verdict == mq.FAIL
    assert fact.p_value >= ALPHA


def test_volume_volatility_correlation_is_not_applicable_below_min_sample():
    returns = _clustered_returns(n=MIN_SAMPLE_POINTS - 1)
    samples = _samples_from_returns(returns, _volume_tracking_volatility(returns))
    fact = check_volume_volatility_correlation(samples)
    assert fact.raw_verdict == mq.NOT_APPLICABLE
    assert fact.p_value is None


# --------------------------------------------------------------------------- #
# Fact 5: order-flow long memory (new)
# --------------------------------------------------------------------------- #


def test_order_flow_long_memory_passes_on_persistent_signs():
    fact = check_order_flow_long_memory(_persistent_signs())
    assert fact.raw_verdict == mq.PASS
    assert fact.statistic < 0  # ln(ACF) ~ ln(lag) slope
    assert fact.p_value < ALPHA
    assert fact.evidence["max_lag"] == mq.ORDER_FLOW_MAX_LAG


def test_order_flow_long_memory_fails_on_alternating_signs():
    fact = check_order_flow_long_memory(_alternating_signs())
    assert fact.raw_verdict == mq.FAIL
    assert fact.evidence["first_non_positive_lag"] == 1
    assert fact.statistic is None


def test_order_flow_long_memory_fails_on_independent_signs():
    rng = random.Random(21)
    fact = check_order_flow_long_memory([rng.choice((-1, 1)) for _ in range(N)])
    assert fact.raw_verdict == mq.FAIL


def test_order_flow_long_memory_fails_when_positive_acf_does_not_decay(monkeypatch):
    """All 100 lags positive but no power-law decay: the slope is not
    significantly negative, so the fact fails.  The ACF vector is injected
    because a sign series with a *flat* positive ACF at every lag out to 100 is
    not constructible from a plain random draw -- the branch under test is the
    verdict rule, not the series generator."""
    flat = [0.2 + (0.01 if lag % 2 else -0.01) for lag in range(1, mq.ORDER_FLOW_MAX_LAG + 1)]
    monkeypatch.setattr("market_game_sim.metrics.validation.acf", lambda values, lag: flat[lag - 1])
    fact = check_order_flow_long_memory(_persistent_signs())
    assert fact.raw_verdict == mq.FAIL
    assert fact.p_value >= ALPHA  # 斜率不显著为负
    assert fact.evidence["slope"] is not None


def test_order_flow_long_memory_is_not_applicable_when_series_is_short():
    fact = check_order_flow_long_memory(_persistent_signs(n=MIN_SAMPLE_POINTS - 1))
    assert fact.raw_verdict == mq.NOT_APPLICABLE
    assert fact.p_value is None


# --------------------------------------------------------------------------- #
# build_stylized_facts: the five-fact bundle
# --------------------------------------------------------------------------- #


def test_build_stylized_facts_returns_exactly_the_five_sc502_facts():
    returns = _clustered_returns()
    facts = build_stylized_facts(
        _samples_from_returns(returns, _volume_tracking_volatility(returns)), _persistent_signs()
    )
    assert tuple(facts) == mq.STYLIZED_FACTS
    assert all(f.raw_verdict in mq.VERDICTS for f in facts.values())


def test_build_stylized_facts_feeds_a_valid_report_with_three_passes():
    """A market carrying clustering, volume-volatility and order-flow memory
    reaches SC-502's >= 3 threshold end to end."""
    returns = _clustered_returns()
    facts = build_stylized_facts(
        _samples_from_returns(returns, _volume_tracking_volatility(returns)), _persistent_signs()
    )
    report = mq.build_report(
        run_id="t971-pass",
        roster_id="roster-t971",
        logical_seconds=600.0,
        window_start_logical_ns=0,
        quality=dict.fromkeys(mq.QUALITY_THRESHOLDS, None),
        stylized_facts=facts,
    )
    passed = sum(1 for v in report.verdicts["stylized_facts"].values() if v == mq.PASS)
    assert passed >= mq.STYLIZED_MIN_PASS
    assert report.verdicts[mq.SC_502] == mq.PASS
    assert mq.parse_report(report.to_dict()) == report


def test_build_stylized_facts_marks_price_facts_not_applicable_when_fill_ratio_is_high():
    """协议 §2: >30% 前值填充 makes the return-based facts unusable, but the
    order-flow fact reads no prices and is still measured."""
    returns = _clustered_returns()
    samples = _samples_from_returns(returns, _volume_tracking_volatility(returns), trade_count=0)
    facts = build_stylized_facts(samples, _persistent_signs())
    assert facts[mq.FAT_TAILS].raw_verdict == mq.NOT_APPLICABLE
    assert facts[mq.RETURN_AUTOCORRELATION].raw_verdict == mq.NOT_APPLICABLE
    assert facts[mq.VOLATILITY_CLUSTERING].raw_verdict == mq.NOT_APPLICABLE
    assert facts[mq.VOLUME_VOLATILITY_CORRELATION].raw_verdict == mq.NOT_APPLICABLE
    assert facts[mq.FAT_TAILS].evidence["fill_ratio"] > MAX_FILL_RATIO  # 记录实测填充比
    assert facts[mq.ORDER_FLOW_LONG_MEMORY].raw_verdict == mq.PASS


# --------------------------------------------------------------------------- #
# Caliber guards
# --------------------------------------------------------------------------- #


def test_family_correction_downgrades_marginal_passes():
    """Four raw PASSes at p = 0.04 all fall to FAIL under Holm-Bonferroni
    (threshold 0.05/4 = 0.0125); the same facts at p = 0.001 survive.  Without
    the correction both cases would read 4 passes."""

    def _facts(p: float) -> dict[str, mq.StylizedFactResult]:
        out = {name: mq.StylizedFactResult(mq.PASS, 1.0, p) for name in mq.STYLIZED_FAMILY_A}
        out[mq.RETURN_AUTOCORRELATION] = mq.StylizedFactResult(mq.FAIL, None, 0.5)
        return {name: out[name] for name in mq.STYLIZED_FACTS}

    marginal = mq.build_report(
        run_id="t971-marginal",
        roster_id="roster-t971",
        logical_seconds=600.0,
        window_start_logical_ns=0,
        quality=dict.fromkeys(mq.QUALITY_THRESHOLDS, None),
        stylized_facts=_facts(0.04),
    )
    strong = mq.build_report(
        run_id="t971-strong",
        roster_id="roster-t971",
        logical_seconds=600.0,
        window_start_logical_ns=0,
        quality=dict.fromkeys(mq.QUALITY_THRESHOLDS, None),
        stylized_facts=_facts(0.001),
    )
    assert all(v == mq.FAIL for v in marginal.verdicts["stylized_facts"].values())
    assert marginal.verdicts[mq.SC_502] == mq.FAIL
    assert sum(1 for v in strong.verdicts["stylized_facts"].values() if v == mq.PASS) == 4
    assert strong.verdicts[mq.SC_502] == mq.PASS


def test_kpi005_family_a_is_untouched_by_this_milestone():
    """AC-505 guard: 0.1.2's group A owns KPI-005's judgement and must not gain
    this milestone's facts; the two families are different sets (spec SC-502),
    so their corrected p values are not comparable."""
    assert _FAMILY_A == (
        "fat_tails",
        "volatility_clustering",
        "price_impact_nonlinearity",
        "spread_depth_regime",
    )
    assert set(mq.STYLIZED_FAMILY_A) != set(_FAMILY_A)
    assert mq.VOLUME_VOLATILITY_CORRELATION not in _FAMILY_A
    assert mq.ORDER_FLOW_LONG_MEMORY not in _FAMILY_A


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("alpha", 0.05),
        ("min_pass", 3),
        ("order_flow_max_lag", 100),
        ("volume_volatility_window", 30),
    ],
)
def test_thresholds_come_from_the_frozen_table(name, expected):
    """The measures read spec §6's constants; a test never sets its own."""
    assert mq.frozen_thresholds()["stylized_facts"][name] == expected


# --------------------------------------------------------------------------- #
# Fact 3 的前置有效性条件（spec §6，owner 2026-09-24 裁决）
# --------------------------------------------------------------------------- #


def _monotone_returns(n: int = N, seed: int = 5) -> list[float]:
    """单调上涨：每个收益都为正——实测过的退化形态（实验报告 §16）。"""
    rng = random.Random(seed)
    return [abs(rng.gauss(0.0, 0.01)) + 1e-4 for _ in range(n)]


def test_volatility_clustering_is_not_applicable_when_returns_are_single_signed():
    """反面：收益全同号时本检验退化为 Fact 2，必须判不适用而非 PASS/FAIL。

    这是数学恒等：|r| 此时是 r 的仿射函数，而 ACF 对仿射变换不变。实测中这条
    退化让一个单调暴涨 7 倍、最终停止成交的市场把波动聚集判成了 PASS。
    """
    fact = check_volatility_clustering_lags(_monotone_returns())
    assert fact.raw_verdict == mq.NOT_APPLICABLE
    assert fact.evidence["reason_code"] == "SINGLE_SIGNED_RETURNS"
    assert fact.evidence["dominant_share"] == 1.0


def test_volatility_clustering_still_judges_a_two_sided_market():
    """正面：收益双向时前置条件不拦截，PASS/FAIL 照常给出。"""
    fact = check_volatility_clustering_lags(_clustered_returns())
    assert fact.raw_verdict == mq.PASS
    assert fact.evidence["acf_lag1"] > 0


def test_all_zero_returns_are_degenerate_too():
    """全零收益没有可检验的变化，同样判不适用。"""
    fact = check_volatility_clustering_lags([0.0] * N)
    assert fact.raw_verdict == mq.NOT_APPLICABLE
    assert fact.evidence["nonzero"] == 0


def test_the_threshold_is_a_share_not_an_all_or_nothing_rule():
    """94% 同号仍然判定，96% 同号判不适用——阈值是 95%，两侧都要断言。"""
    base = _clustered_returns()
    n = len(base)

    def with_share(share: float) -> list[float]:
        flip = int(n * (1 - share))
        return [abs(v) if i >= flip else -abs(v) for i, v in enumerate(base)]

    assert check_volatility_clustering_lags(with_share(0.94)).raw_verdict != mq.NOT_APPLICABLE
    assert check_volatility_clustering_lags(with_share(0.96)).raw_verdict == mq.NOT_APPLICABLE


def test_not_applicable_does_not_shrink_the_sc_502_denominator():
    """必须钉死：SC-502 仍是「五项中至少 3 项」，不得变成「三项中至少 3 项」。

    否则本前置条件会从「让自己更难过门」翻转成「让自己更好过门」——那正是
    「发现指标不利于是改判定规则」的形态。
    """
    facts = {
        "fat_tails": mq.StylizedFactResult(mq.PASS, 1.0, 0.001),
        "return_autocorrelation": mq.StylizedFactResult(mq.PASS, 1.0, 0.001),
        "volatility_clustering": mq.StylizedFactResult(mq.NOT_APPLICABLE, None, None),
        "volume_volatility_correlation": mq.StylizedFactResult(mq.NOT_APPLICABLE, None, None),
        "order_flow_long_memory": mq.StylizedFactResult(mq.NOT_APPLICABLE, None, None),
    }
    verdicts, _failed = mq._derive(0, {k: None for k in mq.QUALITY_THRESHOLDS}, facts)
    # 2 项通过、3 项不适用：若分母被缩小成「2/2」，这里会变成 PASS。
    assert verdicts[mq.SC_502] == mq.FAIL
