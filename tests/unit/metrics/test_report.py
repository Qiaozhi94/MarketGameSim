"""§2.6 regression: endpoint_samples must participate in the report stats.

Round reviews found experiment/runner.py::build_study_report collected
``endpoint_samples`` (margin_ratio_bp, leverage_bp) at the moment each run
hit an economic endpoint, but only ever used their COUNT
(``n_endpoint_samples``) -- the actual values were computed and discarded,
so Part 1 (endpoint severity) had no margin/leverage characterization
analogous to what Part 2 already provides for the continuous regime.
"""

from __future__ import annotations

from market_game_sim.metrics.liquidation import RunClassification
from market_game_sim.metrics.report import (
    _sample_stats,
    build_endpoint_part,
    build_report,
)


def test_sample_stats_empty_list():
    n, mean_m, null_m, mean_l, null_l = _sample_stats([])
    assert (n, mean_m, null_m, mean_l, null_l) == (0, 0.0, 0.0, 0.0, 0.0)


def test_sample_stats_computes_mean_and_null_ratio():
    samples = [(1000, 500), (2000, None), (None, 700)]
    n, mean_m, null_m, mean_l, null_l = _sample_stats(samples)
    assert n == 3
    assert mean_m == 1500.0  # (1000+2000)/2, None excluded
    assert null_m == 1 / 3
    assert mean_l == 600.0  # (500+700)/2
    assert null_l == 1 / 3


def test_sample_stats_all_none_gives_zero_means_full_null():
    samples = [(None, None), (None, None)]
    n, mean_m, null_m, mean_l, null_l = _sample_stats(samples)
    assert n == 2
    assert mean_m == 0.0
    assert null_m == 1.0
    assert mean_l == 0.0
    assert null_l == 1.0


def test_build_endpoint_part_uses_endpoint_samples_for_margin_and_leverage():
    """Positive case: real endpoint_samples must flow through to
    mean_margin_ratio_bp/mean_leverage_bp on the returned EndpointPart."""
    classifications = [RunClassification(is_economic_endpoint=True, breached=True)]
    endpoint_samples = [(200, 8000), (400, 6000)]
    part = build_endpoint_part(classifications, metrics_list=[], endpoint_samples=endpoint_samples)
    assert part.n_samples == 2
    assert part.mean_margin_ratio_bp == 300.0
    assert part.mean_leverage_bp == 7000.0


def test_build_endpoint_part_no_samples_defaults_to_zero():
    """Negative/contrast case: omitting endpoint_samples (or passing an
    empty list) must not crash and must report zeroed-out stats, not
    silently reuse stale/wrong values."""
    classifications = [RunClassification(is_economic_endpoint=False)]
    part = build_endpoint_part(classifications, metrics_list=[])
    assert part.n_samples == 0
    assert part.mean_margin_ratio_bp == 0.0
    assert part.mean_leverage_bp == 0.0


def test_build_report_wires_endpoint_samples_through():
    classifications = [RunClassification(is_economic_endpoint=True, breached=False)]
    endpoint_samples = [(100, 9000)]
    report = build_report(
        classifications, metrics_list=[], valid_samples=[], endpoint_samples=endpoint_samples
    )
    assert report.endpoint.n_samples == 1
    assert report.endpoint.mean_margin_ratio_bp == 100.0
    assert report.endpoint.mean_leverage_bp == 9000.0
