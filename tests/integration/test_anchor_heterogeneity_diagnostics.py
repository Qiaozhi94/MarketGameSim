"""0.4.3 T1110 (AC-705): anchor-too-strong diagnostics are shown, never judged.

Each configuration's report opens with ``anchor_diagnostics`` -- taker share by
family, ``trend_following`` takers, the in-window trade price range and the
down-segment count -- and its SC-501/SC-502 verdicts come from the quality
report alone.  Both sides: a pinned-looking diagnostic block leaves the verdict
where the gate put it, and so does a healthy-looking one.  The quality run
itself is unchanged unless the new ``segment_seconds`` option is passed.
"""

from __future__ import annotations

import pytest

from market_game_sim.metrics.anchor_diagnostics import (
    anchor_diagnostics,
    config_report,
    down_segments,
)
from market_game_sim.metrics.anchor_strength import anchored_roster
from market_game_sim.metrics.market_quality import SC_501, SC_502
from market_game_sim.metrics.quality_run import _price_path, run_market_quality

V = 10_000
SHORT = {"logical_seconds": 600, "burn_in_ns": 300 * 10**9}


@pytest.fixture(scope="module")
def anchored_run():
    return run_market_quality(roster=anchored_roster(6, 1000), segment_seconds=300, **SHORT)


@pytest.fixture(scope="module")
def plain_run():
    return run_market_quality(roster=anchored_roster(6, 1000), **SHORT)


# --------------------------------------------------------------------------- #
# The quality run: additive option only
# --------------------------------------------------------------------------- #


def test_without_the_option_the_quality_run_is_unchanged(plain_run, anchored_run):
    plain_report, plain_diag = plain_run
    report, diag = anchored_run
    assert "segment_prices" not in plain_diag
    assert "window_trade_price_range" not in plain_diag
    assert plain_report.verdicts == report.verdicts
    assert plain_report.quality.keys() == report.quality.keys()
    for key in plain_diag:
        if not key.startswith("wall_seconds"):
            assert plain_diag[key] == diag[key], key


def test_the_option_adds_segment_prices_and_window_range(anchored_run):
    _, diag = anchored_run
    assert diag["segment_seconds"] == 300
    assert len(diag["segment_prices"]) == 2
    low, high = diag["window_trade_price_range"]
    assert 0 < low <= high


def test_a_segment_without_trades_carries_the_previous_price():
    s = 10**9
    events = [
        {"event_type": "TRADE_SETTLE", "timestamp": 10 * s, "price_ticks": 10_020},
        {"event_type": "TRADE_SETTLE", "timestamp": 700 * s, "price_ticks": 9_990},
    ]
    path = _price_path(
        events, initial_price_ticks=V, segment_ns=300 * s, end_ns=900 * s, window_start_ns=600 * s
    )
    assert path["segment_prices"] == [10_020, 10_020, 9_990]
    assert path["window_trade_price_range"] == [9_990, 9_990]


def test_no_trades_in_window_gives_no_range():
    path = _price_path([], initial_price_ticks=V, segment_ns=300, end_ns=600, window_start_ns=0)
    assert path["segment_prices"] == [V, V]
    assert path["window_trade_price_range"] is None


# --------------------------------------------------------------------------- #
# The diagnostic block
# --------------------------------------------------------------------------- #


def test_report_opens_with_the_diagnostics(anchored_run):
    report, diag = anchored_run
    built = config_report(V, report, diag)
    assert next(iter(built)) == "anchor_diagnostics"
    fields = built["anchor_diagnostics"]
    assert set(fields) >= {
        "taker_share_by_family",
        "trend_following_takers",
        "window_trade_price_range",
        "down_segments",
    }
    assert abs(sum(fields["taker_share_by_family"].values()) - 1) < 1e-5


def test_fields_are_computed_from_the_run():
    diag = {
        "takers_by_family": {"trend_following": 4, "sentiment_noise": 96},
        "segment_prices": [10_010, 10_004, 10_022, 10_019],
        "window_trade_price_range": [9_995, 10_050],
    }
    fields = anchor_diagnostics(V, diag)
    assert fields["trend_following_takers"] == 4
    assert fields["taker_share_by_family"] == {"sentiment_noise": 0.96, "trend_following": 0.04}
    assert fields["window_trade_price_range_pct"] == 0.55
    assert fields["down_segments"] == 2


def test_down_segments_start_from_the_reference():
    assert down_segments(V, [9_999]) == 1
    assert down_segments(V, [V, V]) == 0


# --------------------------------------------------------------------------- #
# Diagnostics never change the verdict (both sides)
# --------------------------------------------------------------------------- #

PINNED = {
    "takers_by_family": {"trend_following": 0, "sentiment_noise": 1000},
    "segment_prices": [V] * 19,
    "window_trade_price_range": [V, V],
}
HEALTHY = {
    "takers_by_family": {"trend_following": 900, "mean_reversion": 800, "sentiment_noise": 700},
    "segment_prices": [10_100, 9_900, 10_200, 9_800] * 4 + [10_000] * 3,
    "window_trade_price_range": [9_500, 10_600],
}


@pytest.mark.parametrize("diag", [PINNED, HEALTHY], ids=["pinned", "healthy"])
def test_verdicts_come_from_the_gate_alone(anchored_run, diag):
    report, _ = anchored_run
    built = config_report(V, report, diag)
    assert built["sc_501"] == report.verdicts[SC_501]
    assert built["sc_502"] == report.verdicts[SC_502]
    assert built["failed"] == list(report.failed)
