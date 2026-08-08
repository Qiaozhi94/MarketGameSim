"""T505: Two-part report (退化状态 §4.0).

Part 1: economic endpoint rate and severity.
Part 2: continuous metrics conditional on no endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from market_game_sim.metrics.liquidation import LiquidationMetrics, RunClassification


@dataclass
class EndpointPart:
    total_runs: int
    runs_with_endpoint: int
    rate: float
    by_code: dict[str, int] = field(default_factory=dict)
    breach_count: int = 0
    avg_liquidation_volume_ratio: float = 0.0
    n_samples: int = 0
    mean_margin_ratio_bp: float = 0.0
    null_ratio_margin_ratio: float = 0.0
    mean_leverage_bp: float = 0.0
    null_ratio_leverage: float = 0.0


@dataclass
class ContinuousPart:
    n_samples: int
    mean_margin_ratio_bp: float
    null_ratio_margin_ratio: float
    mean_leverage_bp: float
    null_ratio_leverage: float
    valid_sample_note: str = ""


@dataclass
class TwoPartReport:
    endpoint: EndpointPart
    continuous: ContinuousPart
    technical_invalid_rate: float = 0.0


def _sample_stats(
    samples: list[tuple[int | None, int | None]],
) -> tuple[int, float, float, float, float]:
    """Shared descriptive stats over ``(margin_ratio_bp, leverage_bp)``
    samples: ``(n, mean_margin, null_ratio_margin, mean_leverage,
    null_ratio_leverage)``.  ``None`` means "undefined at this point"
    (指标字典 §4.2) and is excluded from the mean but counted in the null
    ratio."""
    n = len(samples)
    if n == 0:
        return 0, 0.0, 0.0, 0.0, 0.0
    margin_vals = [m for m, _ in samples if m is not None]
    leverage_vals = [lev for _, lev in samples if lev is not None]
    margin_null = (n - len(margin_vals)) / n
    leverage_null = (n - len(leverage_vals)) / n
    mean_m = sum(margin_vals) / len(margin_vals) if margin_vals else 0.0
    mean_l = sum(leverage_vals) / len(leverage_vals) if leverage_vals else 0.0
    return n, mean_m, margin_null, mean_l, leverage_null


def build_endpoint_part(
    classifications: list[RunClassification],
    metrics_list: list[LiquidationMetrics],
    endpoint_samples: list[tuple[int | None, int | None]] | None = None,
) -> EndpointPart:
    """Build Part 1: economic endpoint rate + severity.

    ``endpoint_samples`` are ``(margin_ratio_bp, leverage_bp)`` pairs drawn
    from runs that hit an economic endpoint (指标字典 §4.1/§4.2) -- they
    characterize account state AT the endpoint, the Part-1 analogue of Part
    2's continuous-regime stats.
    """
    n = len(classifications)
    n_endpoint = sum(1 for c in classifications if c.is_economic_endpoint)
    code_counts: dict[str, int] = {}
    breach = 0
    for c in classifications:
        for code in c.economic_endpoint_codes:
            code_counts[code] = code_counts.get(code, 0) + 1
        if c.breached:
            breach += 1
    ratios = [m.liquidation_volume_ratio for m in metrics_list if m.total_volume > 0]
    avg_ratio = sum(ratios) / len(ratios) if ratios else 0.0
    n_s, mean_m, margin_null, mean_l, leverage_null = _sample_stats(endpoint_samples or [])
    return EndpointPart(
        total_runs=n,
        runs_with_endpoint=n_endpoint,
        rate=n_endpoint / n if n > 0 else 0.0,
        by_code=code_counts,
        breach_count=breach,
        avg_liquidation_volume_ratio=avg_ratio,
        n_samples=n_s,
        mean_margin_ratio_bp=mean_m,
        null_ratio_margin_ratio=margin_null,
        mean_leverage_bp=mean_l,
        null_ratio_leverage=leverage_null,
    )


def build_continuous_part(
    valid_samples: list[tuple[int, int | None, int | None]],
) -> ContinuousPart:
    """Build Part 2: continuous metrics over the survivors.

    Each sample is ``(margin_ratio_bp, leverage_bp)``.  ``None`` means
    "undefined at this point" (指标字典 §4.2).
    """
    n, mean_m, margin_null, mean_l, leverage_null = _sample_stats(valid_samples)
    if n == 0:
        return ContinuousPart(
            n_samples=0,
            mean_margin_ratio_bp=0.0,
            null_ratio_margin_ratio=0.0,
            mean_leverage_bp=0.0,
            null_ratio_leverage=0.0,
            valid_sample_note="no valid samples",
        )
    note = ""
    if margin_null > 0.3:
        note += "margin_ratio null > 30%; "
    if leverage_null > 0.3:
        note += "leverage null > 30%; "
    return ContinuousPart(
        n_samples=n,
        mean_margin_ratio_bp=mean_m,
        null_ratio_margin_ratio=margin_null,
        mean_leverage_bp=mean_l,
        null_ratio_leverage=leverage_null,
        valid_sample_note=note,
    )


def build_report(
    classifications: list[RunClassification],
    metrics_list: list[LiquidationMetrics],
    valid_samples: list[tuple[int | None, int | None]],
    endpoint_samples: list[tuple[int | None, int | None]] | None = None,
) -> TwoPartReport:
    """Build the two-part report from a list of runs."""
    n = len(classifications)
    n_ti = sum(1 for c in classifications if c.is_technical_invalid)
    return TwoPartReport(
        endpoint=build_endpoint_part(classifications, metrics_list, endpoint_samples),
        continuous=build_continuous_part(valid_samples),
        technical_invalid_rate=n_ti / n if n > 0 else 0.0,
    )
