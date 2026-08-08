"""T606 (KPI-005): market validation matrix.

Implements the 0.1.2 pre-registered protocol
(``docs/experiments/0.1.2-market-validation-protocol.md``, T002) for the
6 features PRD §12 requires KPI-005 to declare PASS/FAIL/NOT_APPLICABLE for.

This is the reporting/statistics layer (ADR-001's no-float rule is scoped to
the domain kernel, not here) -- uses ``statistics.NormalDist`` for asymptotic
normal-approximation significance tests, no scipy dependency.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import NormalDist

from market_game_sim.experiment.stats import holm_bonferroni
from market_game_sim.metrics.liquidation import LiquidationMetrics
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
