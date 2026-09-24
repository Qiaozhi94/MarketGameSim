"""T606 (KPI-005): market validation matrix.

Implements the 0.1.2 pre-registered protocol
(``docs/experiments/0.1.2-market-validation-protocol.md``, T002) for the
6 features PRD §12 requires KPI-005 to declare PASS/FAIL/NOT_APPLICABLE for.

This is the reporting/statistics layer (ADR-001's no-float rule is scoped to
the domain kernel, not here) -- uses ``statistics.NormalDist`` for asymptotic
normal-approximation significance tests, no scipy dependency.

0.4.1 T971 (FR-505 / SC-502 / AC-505) extends this module with the stylized
facts of spec §6 SC-502: facts 1-3 **reuse** the frozen protocol checks above
(fat tails, return autocorrelation, ``|r|`` ACF) with only the lag-50
extension added, and facts 4-5 (volume-volatility correlation, order-flow long
memory) are new here because the 0.1.2 protocol does not cover them.  The
family-wise correction and the ``>= 3`` pass count live in
``metrics/market_quality.py`` (spec §6's caliber owner) and are *not*
duplicated here; ``_FAMILY_A`` below belongs to KPI-005 and must not gain the
new facts -- that would silently re-judge a frozen result (协议 §4).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import NormalDist

from market_game_sim.experiment.stats import holm_bonferroni
from market_game_sim.metrics.liquidation import LiquidationMetrics
from market_game_sim.metrics.market_quality import (
    FAT_TAILS,
    NOT_APPLICABLE,
    ORDER_FLOW_LONG_MEMORY,
    ORDER_FLOW_MAX_LAG,
    RETURN_AUTOCORRELATION,
    VOLATILITY_CLUSTERING,
    VOLATILITY_CLUSTERING_LAGS,
    VOLUME_VOLATILITY_CORRELATION,
    VOLUME_VOLATILITY_WINDOW,
    StylizedFactResult,
    combine_volatility_clustering,
)
from market_game_sim.metrics.sampling import ImpactSample, MarketSample

_NORMAL = NormalDist()

MIN_SAMPLE_POINTS = 2000  # 指标字典 §2
MAX_FILL_RATIO = 0.30  # 指标字典 §2
ACF_LAGS = 5  # 协议 §3.2
VOL_WINDOW = 30  # MD-002
ALPHA = 0.05  # 协议 §2
MIN_TAKER_ORDERS = 40  # 协议 §3.4
MAX_RELATIVE_SPREAD = 0.05  # 协议 §3.5
RANGE_COVERAGE = 0.95  # 协议 §3.5


def _two_sided_p(z: float) -> float:
    return 2 * (1 - _NORMAL.cdf(abs(z)))


def _one_sided_p(z: float) -> float:
    return 1 - _NORMAL.cdf(z)


@dataclass
class ValidationItem:
    """One row of the KPI-005 matrix (协议 §3.x)."""

    name: str
    verdict: str  # "PASS" | "FAIL" | "NOT_APPLICABLE"
    statistic: float | None
    p_value: float | None
    threshold_desc: str
    evidence: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "verdict": self.verdict,
            "statistic": self.statistic,
            "p_value": self.p_value,
            "threshold_desc": self.threshold_desc,
            "evidence": dict(self.evidence),
        }


@dataclass
class MarketValidationMatrix:
    items: dict[str, ValidationItem]
    fill_ratio: float
    fill_ratio_ok: bool
    alpha: float = ALPHA

    def as_dict(self) -> dict:
        return {
            "fill_ratio": self.fill_ratio,
            "fill_ratio_ok": self.fill_ratio_ok,
            "alpha": self.alpha,
            "items": {k: v.as_dict() for k, v in self.items.items()},
        }


def compute_log_returns(samples: list[MarketSample]) -> list[float]:
    """指标字典 §3.2: ``r_t = ln(P_t / P_{t-1})`` using each sample's
    ``last_ticks`` (成交价). Samples before the first trade (``last_ticks is
    None``) are skipped; afterwards ``last_ticks`` is forward-filled so the
    remaining samples stay equal-interval."""
    prices = [s.last_ticks for s in samples if s.last_ticks is not None]
    return [
        math.log(prices[i] / prices[i - 1])
        for i in range(1, len(prices))
        if prices[i - 1] > 0 and prices[i] > 0
    ]


def compute_fill_ratio(samples: list[MarketSample]) -> float:
    """指标字典 §2: fraction of samples with no trade in their interval
    (前值填充)."""
    if not samples:
        return 0.0
    filled = sum(1 for s in samples if s.trade_count_since_last == 0)
    return filled / len(samples)


def excess_kurtosis(values: list[float]) -> float:
    n = len(values)
    if n == 0:
        return 0.0
    mean = sum(values) / n
    m2 = sum((v - mean) ** 2 for v in values) / n
    m4 = sum((v - mean) ** 4 for v in values) / n
    if m2 == 0:
        return 0.0
    return m4 / (m2**2) - 3.0


def acf(values: list[float], lag: int) -> float:
    n = len(values)
    if lag <= 0 or lag >= n:
        raise ValueError(f"lag must be in [1, {n}), got {lag}")
    mean = sum(values) / n
    denom = sum((v - mean) ** 2 for v in values)
    if denom == 0:
        return 0.0
    numer = sum((values[t] - mean) * (values[t - lag] - mean) for t in range(lag, n))
    return numer / denom


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx < 1e-12 or syy < 1e-12:
        return 0.0
    return sxy / math.sqrt(sxx * syy)


def _aligned_log_returns(samples: list[MarketSample]) -> list[float | None]:
    out: list[float | None] = [None] * len(samples)
    prev: int | None = None
    for i, s in enumerate(samples):
        if s.last_ticks is not None and prev is not None and prev > 0:
            out[i] = math.log(s.last_ticks / prev)
        if s.last_ticks is not None:
            prev = s.last_ticks
    return out


def _rolling_volatility(returns: list[float | None], window: int) -> list[float | None]:
    out: list[float | None] = [None] * len(returns)
    min_points = max(2, window // 2)
    for i in range(len(returns)):
        chunk = [r for r in returns[max(0, i - window + 1) : i + 1] if r is not None]
        if len(chunk) >= min_points:
            mean = sum(chunk) / len(chunk)
            var = sum((r - mean) ** 2 for r in chunk) / (len(chunk) - 1)
            out[i] = math.sqrt(var)
    return out


def check_fat_tails(returns: list[float]) -> ValidationItem:
    n = len(returns)
    if n < MIN_SAMPLE_POINTS:
        return ValidationItem(
            "fat_tails", "NOT_APPLICABLE", None, None, f"n >= {MIN_SAMPLE_POINTS}", {"n": n}
        )
    k = excess_kurtosis(returns)
    z = k / math.sqrt(24 / n)
    p = _one_sided_p(z)
    verdict = "PASS" if (p < ALPHA and k > 0) else "FAIL"
    return ValidationItem(
        "fat_tails",
        verdict,
        z,
        p,
        "超额峰度>0显著 (one-sided, asymptotic SE=sqrt(24/n))",
        {"excess_kurtosis": k, "n": n},
    )


def check_return_autocorrelation(returns: list[float], lags: int = ACF_LAGS) -> ValidationItem:
    n = len(returns)
    if n < MIN_SAMPLE_POINTS:
        return ValidationItem(
            "return_autocorrelation",
            "NOT_APPLICABLE",
            None,
            None,
            f"n >= {MIN_SAMPLE_POINTS}",
            {"n": n},
        )
    se = 1 / math.sqrt(n)
    acf_values: dict[str, float] = {}
    p_values: dict[str, float] = {}
    for lag in range(1, lags + 1):
        r = acf(returns, lag)
        z = r / se
        acf_values[f"lag_{lag}"] = r
        p_values[f"lag_{lag}"] = _two_sided_p(z)
    significant = holm_bonferroni(p_values, alpha=ALPHA)
    any_significant = any(significant.values())
    verdict = "FAIL" if any_significant else "PASS"
    return ValidationItem(
        "return_autocorrelation",
        verdict,
        None,
        min(p_values.values()),
        "Holm-Bonferroni校正后lag 1-5均不显著 (Bartlett白噪声界 1/sqrt(n))",
        {"acf": acf_values, "p_values": p_values, "significant_lags": significant, "n": n},
    )


def check_volatility_clustering(returns: list[float]) -> ValidationItem:
    n = len(returns)
    if n < MIN_SAMPLE_POINTS:
        return ValidationItem(
            "volatility_clustering",
            "NOT_APPLICABLE",
            None,
            None,
            f"n >= {MIN_SAMPLE_POINTS}",
            {"n": n},
        )
    abs_returns = [abs(r) for r in returns]
    r1 = acf(abs_returns, 1)
    se = 1 / math.sqrt(n)
    z = r1 / se
    p = _one_sided_p(z)
    verdict = "PASS" if (p < ALPHA and r1 > 0) else "FAIL"
    return ValidationItem(
        "volatility_clustering",
        verdict,
        z,
        p,
        "|r_t| lag-1 ACF>0显著 (one-sided, asymptotic SE=1/sqrt(n))",
        {"acf_lag1_abs_returns": r1, "n": n},
    )


def check_price_impact_nonlinearity(impact_samples: list[ImpactSample]) -> ValidationItem:
    points = [
        (math.log(s.quantity_units), math.log(s.impact_bp))
        for s in impact_samples
        if s.quantity_units > 0 and s.impact_bp > 0
    ]
    n = len(points)
    if n < MIN_TAKER_ORDERS:
        return ValidationItem(
            "price_impact_nonlinearity",
            "NOT_APPLICABLE",
            None,
            None,
            f">= {MIN_TAKER_ORDERS} 笔有效taker订单",
            {"n_orders": n},
        )
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    sxx = sum((x - x_mean) ** 2 for x in xs)
    if sxx < 1e-12:  # 浮点下"全部相同"不一定精确等于0，用小量阈值判退化
        return ValidationItem(
            "price_impact_nonlinearity",
            "NOT_APPLICABLE",
            None,
            None,
            "全部订单规模相同，回归退化",
            {"n_orders": n},
        )
    sxy = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys, strict=True))
    gamma = sxy / sxx
    intercept = y_mean - gamma * x_mean
    dof = n - 2
    if dof <= 0:
        return ValidationItem(
            "price_impact_nonlinearity", "NOT_APPLICABLE", None, None, "自由度不足", {"n_orders": n}
        )
    sse = sum((y - (intercept + gamma * x)) ** 2 for x, y in zip(xs, ys, strict=True))
    sigma2 = sse / dof
    se_gamma = math.sqrt(sigma2 / sxx) if sxx > 0 else float("inf")
    t = (gamma - 1.0) / se_gamma if se_gamma > 0 else 0.0
    p = _two_sided_p(t)
    verdict = "PASS" if p < ALPHA else "FAIL"
    return ValidationItem(
        "price_impact_nonlinearity",
        verdict,
        gamma,
        p,
        "OLS ln(impact_bp)~ln(Q)，H0:γ=1，two-sided normal-approx",
        {"gamma": gamma, "se_gamma": se_gamma, "n_orders": n},
    )


def check_spread_depth_regime(
    samples: list[MarketSample], window: int = VOL_WINDOW
) -> ValidationItem:
    n_total = len(samples)
    if n_total < MIN_SAMPLE_POINTS:
        return ValidationItem(
            "spread_depth_regime",
            "NOT_APPLICABLE",
            None,
            None,
            f"n >= {MIN_SAMPLE_POINTS}",
            {"n": n_total},
        )
    with_spread = [s for s in samples if s.spread_ticks is not None and s.mid_ticks]
    if not with_spread:
        return ValidationItem(
            "spread_depth_regime",
            "NOT_APPLICABLE",
            None,
            None,
            "spread全程未定义（单边空簿）",
            {"n": n_total},
        )
    in_range = sum(
        1 for s in with_spread if 0 < s.spread_ticks / s.mid_ticks <= MAX_RELATIVE_SPREAD
    )
    range_ok = (in_range / len(with_spread)) >= RANGE_COVERAGE
    depth_ok = (
        sum(1 for s in samples if s.bid_depth_k > 0 and s.ask_depth_k > 0) / n_total
    ) >= RANGE_COVERAGE

    returns = _aligned_log_returns(samples)
    vols = _rolling_volatility(returns, window)
    pairs = [
        (vols[i], float(samples[i].spread_ticks))
        for i in range(n_total)
        if vols[i] is not None and samples[i].spread_ticks is not None
    ]
    if len(pairs) < MIN_SAMPLE_POINTS // 2:
        return ValidationItem(
            "spread_depth_regime",
            "NOT_APPLICABLE",
            None,
            None,
            "滚动波动率窗口后有效配对不足",
            {"n_pairs": len(pairs)},
        )
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    r = _pearson(xs, ys)
    n_pairs = len(pairs)
    denom = math.sqrt(max(1e-12, 1 - r * r))
    t = r * math.sqrt(n_pairs - 2) / denom
    p = _one_sided_p(t)
    corr_ok = p < ALPHA and r > 0
    verdict = "PASS" if (range_ok and depth_ok and corr_ok) else "FAIL"
    return ValidationItem(
        "spread_depth_regime",
        verdict,
        r,
        p,
        f"相对点差<={MAX_RELATIVE_SPREAD:.0%}且深度>0占比>={RANGE_COVERAGE:.0%}；"
        f"点差与滚动波动率(W={window})Pearson相关显著为正(one-sided)",
        {
            "range_ok": range_ok,
            "depth_ok": depth_ok,
            "corr": r,
            "n_pairs": n_pairs,
        },
    )


def check_liquidation_chain(metrics: LiquidationMetrics) -> ValidationItem:
    if metrics.total_liquidations == 0:
        return ValidationItem(
            "liquidation_chain",
            "NOT_APPLICABLE",
            None,
            None,
            "本运行无强平触发（未加杠杆或全程未触及维持保证金）",
            {"total_liquidations": 0},
        )
    ratio = metrics.liquidation_volume_ratio
    consistent = (
        0.0 <= ratio <= 1.0
        and metrics.liquidation_volume <= metrics.total_volume
        and all(depth >= 1 for depth in metrics.chain_depth_counts)
    )
    verdict = "PASS" if consistent else "FAIL"
    return ValidationItem(
        "liquidation_chain",
        verdict,
        None,
        None,
        "描述性报告：强平触发次数/连锁深度分布/强平成交量占比，内部一致性检查（非阈值检验）",
        {
            "total_liquidations": metrics.total_liquidations,
            "chain_depth_counts": dict(metrics.chain_depth_counts),
            "liquidation_volume_ratio": ratio,
            "bankruptcy_total": metrics.bankruptcy_total,
        },
    )


_FAMILY_A = (
    "fat_tails",
    "volatility_clustering",
    "price_impact_nonlinearity",
    "spread_depth_regime",
)


def apply_family_correction(
    items: dict[str, ValidationItem], family_names: tuple[str, ...] = _FAMILY_A
) -> dict[str, ValidationItem]:
    """Holm-Bonferroni family correction (协议 §2 组A) across ``family_names``:
    a raw ``PASS`` that does not survive the family-wise correction is
    downgraded to ``FAIL``. Items outside the family, or with verdict
    ``NOT_APPLICABLE``/no ``p_value``, pass through unchanged."""
    family_p = {
        name: items[name].p_value
        for name in family_names
        if name in items
        and items[name].verdict != "NOT_APPLICABLE"
        and items[name].p_value is not None
    }
    corrected = holm_bonferroni(family_p, alpha=ALPHA) if family_p else {}
    out = dict(items)
    for name, significant in corrected.items():
        item = out[name]
        if item.verdict == "PASS" and not significant:
            out[name] = ValidationItem(
                item.name,
                "FAIL",
                item.statistic,
                item.p_value,
                item.threshold_desc + "；未通过Holm-Bonferroni家族显著性校正",
                item.evidence,
            )
    return out


def build_market_validation_matrix(
    market_samples: list[MarketSample],
    impact_samples: list[ImpactSample],
    liquidation_metrics: LiquidationMetrics,
) -> MarketValidationMatrix:
    """T606 (KPI-005): assemble the 6-item PASS/FAIL/NOT_APPLICABLE matrix
    per ``docs/experiments/0.1.2-market-validation-protocol.md``."""
    fill_ratio = compute_fill_ratio(market_samples)
    fill_ratio_ok = fill_ratio <= MAX_FILL_RATIO

    if not fill_ratio_ok:
        note = f"前值填充比例{fill_ratio:.1%}超过30%，统计检验不可采信（协议§2）"
        fat_tails = ValidationItem(
            "fat_tails", "NOT_APPLICABLE", None, None, note, {"fill_ratio": fill_ratio}
        )
        return_ac = ValidationItem(
            "return_autocorrelation",
            "NOT_APPLICABLE",
            None,
            None,
            note,
            {"fill_ratio": fill_ratio},
        )
        vol_cluster = ValidationItem(
            "volatility_clustering", "NOT_APPLICABLE", None, None, note, {"fill_ratio": fill_ratio}
        )
        spread_depth = ValidationItem(
            "spread_depth_regime", "NOT_APPLICABLE", None, None, note, {"fill_ratio": fill_ratio}
        )
    else:
        returns = compute_log_returns(market_samples)
        fat_tails = check_fat_tails(returns)
        return_ac = check_return_autocorrelation(returns)
        vol_cluster = check_volatility_clustering(returns)
        spread_depth = check_spread_depth_regime(market_samples)

    impact_item = check_price_impact_nonlinearity(impact_samples)
    liquidation_item = check_liquidation_chain(liquidation_metrics)

    all_items = {
        "fat_tails": fat_tails,
        "return_autocorrelation": return_ac,
        "volatility_clustering": vol_cluster,
        "price_impact_nonlinearity": impact_item,
        "spread_depth_regime": spread_depth,
        "liquidation_chain": liquidation_item,
    }
    all_items = apply_family_correction(all_items)

    return MarketValidationMatrix(
        items=all_items, fill_ratio=fill_ratio, fill_ratio_ok=fill_ratio_ok
    )


# --------------------------------------------------------------------------- #
# 0.4.1 T971 (FR-505 / SC-502 / AC-505): stylized facts 五项
#
# Facts 1-3 reuse the checks above unchanged; this section only adds the lag-50
# extension (fact 3) and the two facts the 0.1.2 protocol does not cover.  The
# verdicts produced here are *raw* -- family-A correction and the ">= 3 pass"
# count belong to ``metrics/market_quality.py``.
# --------------------------------------------------------------------------- #


def _as_fact(item: ValidationItem) -> StylizedFactResult:
    """Carry a protocol :class:`ValidationItem` over unchanged."""
    return StylizedFactResult(item.verdict, item.statistic, item.p_value, dict(item.evidence))


def abs_return_acf(returns: list[float], lag: int) -> tuple[float | None, float | None]:
    """``|r|`` ACF at ``lag`` with its one-sided p value (协议 §3.3 caliber).

    Same estimator, same asymptotic ``SE = 1/sqrt(n)`` and same one-sided test
    as :func:`check_volatility_clustering`; only the lag is free, which is what
    spec §6 #3 means by "按同一标准误与同一单侧检验延伸到 lag 50".  Returns
    ``(None, None)`` when the sample cannot support the lag.
    """
    n = len(returns)
    if n < MIN_SAMPLE_POINTS or lag <= 0 or lag >= n:
        return None, None
    r = acf([abs(v) for v in returns], lag)
    return r, _one_sided_p(r / (1 / math.sqrt(n)))


#: Fact 3 的前置有效性条件（spec §6，owner 2026-09-24 裁决）：同号收益占比上限。
SINGLE_SIGN_MAX_SHARE = 0.95
#: 前置条件不成立时的稳定原因码。
SINGLE_SIGNED_RETURNS = "SINGLE_SIGNED_RETURNS"


def single_signed_returns(returns: list[float]) -> tuple[bool, dict[str, float | int]]:
    """收益是否（几乎）全部同号——Fact 3 的适用前提是否被违反。

    **这是数学恒等，不是经验调整**：收益全部同号时 ``|r|`` 是 ``r`` 的仿射函数，
    而 ACF 对仿射变换不变，于是 Fact 3 在定义上退化为 Fact 2（收益自相关），两者不再
    独立。实测证据：0.4.1 非锚定基线同一次运行中两者的 ACF lag1 **逐位相同**
    （``0.9761001725558393``，实验报告 §16.1）——一条单调上升的价格路径让每个逐秒收益
    都为正，`|r| ≡ r`。

    零收益不破坏这个恒等（``|0| = 0``），因此只按**非零**收益计数；全为零同样判退化
    （没有可供检验的变化）。
    """
    pos = sum(1 for v in returns if v > 0)
    neg = sum(1 for v in returns if v < 0)
    nonzero = pos + neg
    evidence: dict[str, float | int] = {"positive": pos, "negative": neg, "nonzero": nonzero}
    if nonzero == 0:
        evidence["dominant_share"] = 1.0
        return True, evidence
    share = max(pos, neg) / nonzero
    evidence["dominant_share"] = share
    return share >= SINGLE_SIGN_MAX_SHARE, evidence


def check_volatility_clustering_lags(
    returns: list[float], lags: tuple[int, ...] = VOLATILITY_CLUSTERING_LAGS
) -> StylizedFactResult:
    """Fact 3 (Q-505): ``|r|`` ACF significantly positive at **both** lags.

    The intersection-union rule itself lives in
    :func:`market_quality.combine_volatility_clustering` (spec §6 owns it);
    this function only measures the two lags.

    **前置有效性条件（spec §6，owner 2026-09-24 裁决）**：收益几乎全部同号时本检验
    退化为 Fact 2，故判 ``NOT_APPLICABLE`` 而非 PASS/FAIL，理由码
    ``SINGLE_SIGNED_RETURNS``（见 :func:`single_signed_returns`）。

    该判定**不缩小 SC-502 的分母**：SC-502 仍是「五项中至少 3 项」，``NOT_APPLICABLE``
    只是不计为通过——否则本条会从「让自己更难过门」翻转成「让自己更好过门」。
    """
    degenerate, evidence = single_signed_returns(returns)
    if degenerate:
        return StylizedFactResult(
            NOT_APPLICABLE, None, None, {**evidence, "reason_code": SINGLE_SIGNED_RETURNS}
        )
    lag_low, lag_high = lags
    acf_low, p_low = abs_return_acf(returns, lag_low)
    acf_high, p_high = abs_return_acf(returns, lag_high)
    return combine_volatility_clustering(acf_low, p_low, acf_high, p_high)


def check_volume_volatility_correlation(
    samples: list[MarketSample], window: int = VOLUME_VOLATILITY_WINDOW
) -> StylizedFactResult:
    """Fact 4 (spec §6 #4, new here): rolling realized volatility (MD-002,
    ``W = 30``) against the volume of the same sample -- Pearson ``r`` with
    ``t = r*sqrt(n-2)/sqrt(1-r^2)``, one-sided against ``H0: r <= 0``."""
    n_total = len(samples)
    if n_total < MIN_SAMPLE_POINTS:
        return StylizedFactResult(NOT_APPLICABLE, None, None, {"n": n_total})
    vols = _rolling_volatility(_aligned_log_returns(samples), window)
    pairs = [
        (vols[i], float(samples[i].volume_since_last))
        for i in range(n_total)
        if vols[i] is not None
    ]
    if len(pairs) < MIN_SAMPLE_POINTS // 2:
        return StylizedFactResult(NOT_APPLICABLE, None, None, {"n_pairs": len(pairs)})
    r = _pearson([p[0] for p in pairs], [p[1] for p in pairs])
    n_pairs = len(pairs)
    t = r * math.sqrt(n_pairs - 2) / math.sqrt(max(1e-12, 1 - r * r))
    p = _one_sided_p(t)
    verdict = "PASS" if (p < ALPHA and r > 0) else "FAIL"
    return StylizedFactResult(verdict, r, p, {"corr": r, "n_pairs": n_pairs, "window": window})


def check_order_flow_long_memory(
    order_signs: list[int], max_lag: int = ORDER_FLOW_MAX_LAG
) -> StylizedFactResult:
    """Fact 5 (spec §6 #5, new here): the order-direction series (buy ``+1`` /
    sell ``-1``) keeps a positive ACF over lags ``1..max_lag`` **and** its
    ``ln(ACF) ~ ln(lag)`` OLS slope is significantly negative (power-law decay).

    A non-positive ACF at any lag leaves the log-log regression undefined, so
    the fact fails with no statistic rather than being fitted on the positive
    lags only -- picking the lags would be a caliber the spec does not grant.
    """
    n = len(order_signs)
    if n < MIN_SAMPLE_POINTS or max_lag <= 1 or max_lag >= n:
        return StylizedFactResult(NOT_APPLICABLE, None, None, {"n": n, "max_lag": max_lag})
    values = [float(s) for s in order_signs]
    acfs = [acf(values, lag) for lag in range(1, max_lag + 1)]
    non_positive = [lag for lag, a in enumerate(acfs, start=1) if a <= 0]
    if non_positive:
        return StylizedFactResult(
            "FAIL",
            None,
            None,
            {"first_non_positive_lag": non_positive[0], "n_non_positive": len(non_positive)},
        )
    xs = [math.log(lag) for lag in range(1, max_lag + 1)]
    ys = [math.log(a) for a in acfs]
    m = len(xs)
    x_mean = sum(xs) / m
    y_mean = sum(ys) / m
    sxx = sum((x - x_mean) ** 2 for x in xs)
    sxy = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys, strict=True))
    slope = sxy / sxx
    intercept = y_mean - slope * x_mean
    sse = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys, strict=True))
    se_slope = math.sqrt((sse / (m - 2)) / sxx)
    # H0: slope >= 0 vs H1: slope < 0 -- the lower tail of the same normal
    # approximation the protocol uses elsewhere.
    t = slope / se_slope if se_slope > 0 else 0.0
    p = _one_sided_p(-t)
    verdict = "PASS" if (p < ALPHA and slope < 0) else "FAIL"
    return StylizedFactResult(
        verdict,
        slope,
        p,
        {"slope": slope, "se_slope": se_slope, "max_lag": max_lag, "acf_lag1": acfs[0]},
    )


def build_stylized_facts(
    market_samples: list[MarketSample],
    order_signs: list[int],
    window: int = VOLUME_VOLATILITY_WINDOW,
    max_lag: int = ORDER_FLOW_MAX_LAG,
) -> dict[str, StylizedFactResult]:
    """The five SC-502 facts of one run, **before** family-A correction.

    Feed the result straight into ``market_quality.build_report``; that module
    owns the family instance {1, 3, 4, 5} and the ``>= 3`` count.  A 前值填充
    ratio above 30% makes every price-based fact NOT_APPLICABLE (协议 §2) --
    the same gate ``build_market_validation_matrix`` applies to KPI-005; the
    order-flow fact reads no prices, so it is still measured.
    """
    fill_ratio = compute_fill_ratio(market_samples)
    order_flow = check_order_flow_long_memory(order_signs, max_lag)
    if fill_ratio > MAX_FILL_RATIO:
        unusable = StylizedFactResult(NOT_APPLICABLE, None, None, {"fill_ratio": fill_ratio})
        return {
            FAT_TAILS: unusable,
            RETURN_AUTOCORRELATION: unusable,
            VOLATILITY_CLUSTERING: unusable,
            VOLUME_VOLATILITY_CORRELATION: unusable,
            ORDER_FLOW_LONG_MEMORY: order_flow,
        }
    returns = compute_log_returns(market_samples)
    return {
        FAT_TAILS: _as_fact(check_fat_tails(returns)),
        RETURN_AUTOCORRELATION: _as_fact(check_return_autocorrelation(returns)),
        VOLATILITY_CLUSTERING: check_volatility_clustering_lags(returns),
        VOLUME_VOLATILITY_CORRELATION: check_volume_volatility_correlation(market_samples, window),
        ORDER_FLOW_LONG_MEMORY: order_flow,
    }
