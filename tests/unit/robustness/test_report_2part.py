"""T602 (退化 §4.2): two-part robustness report tests.

Positive + negative + multi-record cases per CLAUDE.md: endpoint part +
continuous part + technical-invalid rate + valid sample count all present.
"""

from __future__ import annotations

import pytest

from market_game_sim.metrics.liquidation import LiquidationMetrics, RunClassification
from market_game_sim.robustness.report_2part import build_robustness_report


def _classifications():
    return [
        RunClassification(is_economic_endpoint=True, breached=True),
        RunClassification(is_technical_invalid=True, technical_invalid_code="TI-4"),
        RunClassification(),
    ]


class TestTwoPartReport:
    def test_all_sections_present(self):
        r = build_robustness_report(
            _classifications(),
            metrics_list=[LiquidationMetrics()] * 3,
            valid_samples=[(1000, 500), (2000, None)],
            endpoint_samples=[(200, 8000)],
        )
        d = r.as_dict()
        assert "endpoint" in d
        assert "continuous" in d
        assert "technical_invalid_rate" in d
        assert "n_valid" in d

    def test_endpoint_rate_and_severity(self):
        r = build_robustness_report(
            _classifications(),
            metrics_list=[LiquidationMetrics()] * 3,
            valid_samples=[],
            endpoint_samples=[(200, 8000)],
        )
        assert r.endpoint["rate"] == pytest.approx(1 / 3)
        assert r.endpoint["breach_count"] == 1
        assert r.endpoint["n_samples"] == 1

    def test_continuous_conditional_on_no_endpoint(self):
        r = build_robustness_report(
            _classifications(),
            metrics_list=[LiquidationMetrics()] * 3,
            valid_samples=[(1000, 500), (2000, 700)],
        )
        # only the non-endpoint, non-invalid run contributes mean
        assert r.continuous["n_samples"] == 2
        assert r.continuous["mean_margin_ratio_bp"] == 1500.0

    def test_technical_invalid_rate_and_n_valid(self):
        r = build_robustness_report(
            _classifications(),
            metrics_list=[LiquidationMetrics()] * 3,
            valid_samples=[],
        )
        assert r.technical_invalid_rate == pytest.approx(1 / 3)
        assert r.n_runs == 3
        assert r.n_valid == 2

    def test_all_valid_no_invalid(self):
        r = build_robustness_report(
            [RunClassification()],
            metrics_list=[LiquidationMetrics()],
            valid_samples=[],
        )
        assert r.technical_invalid_rate == 0.0
        assert r.n_valid == 1
