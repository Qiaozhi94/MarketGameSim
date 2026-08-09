"""T602 (退化 §4.2): two-part robustness report wrapper.

Every robustness report keeps the two-part structure: economic-endpoint
incidence/severity (Part 1) plus continuous metrics conditional on no
endpoint (Part 2), together with the technical-invalid rate and the valid
sample count (T602 exit gate).

This wrapper reuses ``metrics.report.build_report`` (the 0.1.2 two-part
mechanism) and adds the explicit ``n_valid`` surface the robustness layer
needs -- a report that hides how many runs actually survived to support a
conclusion is not reportable under T602.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from market_game_sim.metrics.liquidation import LiquidationMetrics, RunClassification
from market_game_sim.metrics.report import build_report


@dataclass
class TwoPartRobustnessReport:
    endpoint: dict[str, Any]
    continuous: dict[str, Any]
    technical_invalid_rate: float
    n_runs: int
    n_valid: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "continuous": self.continuous,
            "technical_invalid_rate": self.technical_invalid_rate,
            "n_runs": self.n_runs,
            "n_valid": self.n_valid,
        }


def build_robustness_report(
    classifications: list[RunClassification],
    metrics_list: list[LiquidationMetrics],
    valid_samples: list[tuple[int | None, int | None]],
    endpoint_samples: list[tuple[int | None, int | None]] | None = None,
) -> TwoPartRobustnessReport:
    """Build the two-part report for a robustness result set.

    Part 1: economic-endpoint rate + severity (by_code/breach/volume ratio).
    Part 2: continuous metrics over runs without an endpoint.
    Plus technical-invalid rate and the number of valid (non-invalid) runs.
    """
    report = build_report(classifications, metrics_list, valid_samples, endpoint_samples)
    n_valid = sum(1 for c in classifications if not c.is_technical_invalid)
    return TwoPartRobustnessReport(
        endpoint={
            "rate": report.endpoint.rate,
            "by_code": dict(report.endpoint.by_code),
            "breach_count": report.endpoint.breach_count,
            "avg_liquidation_volume_ratio": report.endpoint.avg_liquidation_volume_ratio,
            "n_samples": report.endpoint.n_samples,
            "mean_margin_ratio_bp": report.endpoint.mean_margin_ratio_bp,
            "mean_leverage_bp": report.endpoint.mean_leverage_bp,
        },
        continuous={
            "n_samples": report.continuous.n_samples,
            "mean_margin_ratio_bp": report.continuous.mean_margin_ratio_bp,
            "mean_leverage_bp": report.continuous.mean_leverage_bp,
            "null_ratio_margin_ratio": report.continuous.null_ratio_margin_ratio,
            "null_ratio_leverage": report.continuous.null_ratio_leverage,
            "valid_sample_note": report.continuous.valid_sample_note,
        },
        technical_invalid_rate=report.technical_invalid_rate,
        n_runs=len(classifications),
        n_valid=n_valid,
    )
