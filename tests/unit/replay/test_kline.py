"""T203 (AC-003): K-line view tests per metrics-dictionary §1.9/§1.9.1."""

from __future__ import annotations

import pytest

from market_game_sim.replay.generate import DEFAULT_KLINE_PERIOD_NS
from market_game_sim.replay.kline import DEFAULT_BAR_NS, build_klines

PERIOD = 100


def _trade(ts: int, price: int, qty: int = 10) -> dict:
    return {
        "event_type": "TRADE_SETTLE",
        "timestamp": ts,
        "price_ticks": price,
        "quantity_units": qty,
    }


def _run_event(ts: int) -> dict:
    return {"event_type": "MARKET_DATA_PUBLISH", "timestamp": ts}


def test_only_completed_bars_emitted():
    """A run ending at t=250 completes bars 0 ([0,100)) and 1 ([100,200)); bar 2 is still open."""
    events = [_trade(50, 100), _trade(150, 110), _run_event(250)]
    kl = build_klines(events, period_ns=PERIOD, initial_price_ticks=10000)
    assert [k.start_ns for k in kl] == [0, 100]
    assert len(kl) == 2


def test_run_shorter_than_period_has_no_completed_bar():
    events = [_trade(50, 100), _run_event(80)]
    kl = build_klines(events, period_ns=PERIOD, initial_price_ticks=10000)
    assert kl == []


def test_left_closed_right_open_boundary():
    """A trade exactly at timestamp == (k+1)*period belongs to bar k+1, not bar k."""
    events = [_trade(100, 120), _run_event(150)]
    kl = build_klines(events, period_ns=PERIOD, initial_price_ticks=10000)
    assert len(kl) == 1  # only bar 0 completed
    assert kl[0].start_ns == 0
    # the t=100 trade is NOT in bar 0 (it opens bar 1, still open)
    assert kl[0].trade_count == 0
    assert kl[0].close == 10000  # prev close / initial price


def test_empty_bar_uses_previous_close():
    """Bar 0 has no trade; bar 1 has a trade at 120 -> bar 0 uses initial_price."""
    events = [_trade(120, 500), _run_event(250)]
    kl = build_klines(events, period_ns=PERIOD, initial_price_ticks=10000)
    assert kl[0].close == 10000
    assert kl[0].volume == 0
    assert kl[0].trade_count == 0
    assert kl[1].open == 500
    assert kl[1].close == 500
    assert kl[1].trade_count == 1


def test_ohlc_and_volume_aggregation():
    events = [
        _trade(10, 100, 5),
        _trade(20, 90, 3),
        _trade(40, 110, 7),
        _run_event(150),
    ]
    kl = build_klines(events, period_ns=PERIOD, initial_price_ticks=10000)
    bar0 = kl[0]
    assert bar0.open == 100
    assert bar0.high == 110
    assert bar0.low == 90
    assert bar0.close == 110
    assert bar0.volume == 15
    assert bar0.trade_count == 3


def test_pre_first_trade_bars_use_initial_price():
    """Bars fully before the first trade carry initial_price with zero volume."""
    events = [_run_event(50), _run_event(90), _trade(150, 300), _run_event(250)]
    kl = build_klines(events, period_ns=PERIOD, initial_price_ticks=1234)
    assert kl[0].open == kl[0].high == kl[0].low == kl[0].close == 1234
    assert kl[0].volume == 0
    assert kl[1].open == 300  # bar containing the first trade uses actual price


# --- F3 regression tests ---


def test_default_kline_period_is_60s():
    """F3: DEFAULT_KLINE_PERIOD_NS must be 60s (DEFAULT_BAR_NS), not 5*60*60s."""
    assert DEFAULT_KLINE_PERIOD_NS == DEFAULT_BAR_NS
    assert DEFAULT_KLINE_PERIOD_NS == 60 * 10**9


def test_build_klines_with_60s_period_produces_correct_bars():
    """F3: build_klines with period_ns=DEFAULT_BAR_NS (60s) produces correct bars."""
    period = DEFAULT_BAR_NS
    events = [
        _trade(30 * 10**9, 100, 5),
        _trade(70 * 10**9, 110, 3),
        _run_event(130 * 10**9),
    ]
    kl = build_klines(events, period_ns=period, initial_price_ticks=10000)
    assert len(kl) == 2
    assert kl[0].start_ns == 0
    assert kl[1].start_ns == period
    assert kl[0].trade_count == 1
    assert kl[0].close == 100
    assert kl[1].trade_count == 1
    assert kl[1].close == 110


# --- F7 regression tests ---


def test_single_pass_binning_matches_expected_output():
    """F7: single-pass binning produces identical OHLCV to the expected values
    with multiple trades across multiple bars."""
    events = [
        _trade(10, 100, 5),
        _trade(20, 90, 3),
        _trade(40, 110, 7),
        _trade(110, 200, 2),
        _trade(130, 190, 4),
        _run_event(250),
    ]
    kl = build_klines(events, period_ns=PERIOD, initial_price_ticks=10000)
    assert len(kl) == 2
    assert kl[0].open == 100
    assert kl[0].high == 110
    assert kl[0].low == 90
    assert kl[0].close == 110
    assert kl[0].volume == 15
    assert kl[0].trade_count == 3
    assert kl[1].open == 200
    assert kl[1].high == 200
    assert kl[1].low == 190
    assert kl[1].close == 190
    assert kl[1].volume == 6
    assert kl[1].trade_count == 2


def test_single_pass_binning_with_empty_bars_between_trades():
    """F7: bars with no trades between two active bars carry previous close."""
    events = [
        _trade(10, 100, 5),
        _run_event(50),
        _run_event(150),
        _run_event(250),
        _trade(310, 300, 2),
        _run_event(410),
    ]
    kl = build_klines(events, period_ns=PERIOD, initial_price_ticks=10000)
    assert len(kl) == 4
    assert kl[0].trade_count == 1
    assert kl[0].close == 100
    assert kl[1].trade_count == 0
    assert kl[1].close == 100
    assert kl[2].trade_count == 0
    assert kl[2].close == 100
    assert kl[3].trade_count == 1
    assert kl[3].open == 300
    assert kl[3].close == 300


def test_rejects_zero_period():
    """F-F rejected: period_ns=0 must raise ValueError, not ZeroDivisionError."""
    events = [_trade(50, 100), _run_event(250)]
    with pytest.raises(ValueError, match="positive"):
        build_klines(events, period_ns=0, initial_price_ticks=10000)


def test_rejects_negative_period():
    """F-F rejected: period_ns=-5 must raise ValueError."""
    events = [_trade(50, 100), _run_event(250)]
    with pytest.raises(ValueError, match="positive"):
        build_klines(events, period_ns=-5, initial_price_ticks=10000)


def test_accepts_minimal_positive_period():
    """F-F accepted: period_ns=1 is valid and bins by single-nanosecond windows."""
    events = [_trade(0, 100), _trade(1, 110), _run_event(2)]
    kl = build_klines(events, period_ns=1, initial_price_ticks=10000)
    assert len(kl) == 2
    assert kl[0].trade_count == 1
    assert kl[0].open == 100
    assert kl[0].close == 100
    assert kl[1].trade_count == 1
    assert kl[1].open == 110
    assert kl[1].close == 110
