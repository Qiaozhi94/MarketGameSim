"""T930 (FR-401): multi-period K-line projection (build_kline_set) tests."""

from __future__ import annotations

import pytest

from market_game_sim.replay.kline import (
    DEFAULT_BAR_NS,
    OWNER_KLINE_PERIODS_NS,
    build_kline_set,
    build_klines,
)


def _trade(ts: int, price: int, qty: int = 10) -> dict:
    return {
        "event_type": "TRADE_SETTLE",
        "timestamp": ts,
        "price_ticks": price,
        "quantity_units": qty,
    }


def _run_event(ts: int) -> dict:
    return {"event_type": "MARKET_DATA_PUBLISH", "timestamp": ts}


# --- 0.3.2 E1 frozen capture-period set ---


def test_owner_kline_periods_ns_is_frozen_set():
    """0.3.2 E1: owner capture periods are exactly 1m/5m/15m/1h/4h, ascending, no 1D."""
    assert OWNER_KLINE_PERIODS_NS == (
        60_000_000_000,  # 1m
        300_000_000_000,  # 5m
        900_000_000_000,  # 15m
        3_600_000_000_000,  # 1h
        14_400_000_000_000,  # 4h
    )
    assert tuple(sorted(OWNER_KLINE_PERIODS_NS)) == OWNER_KLINE_PERIODS_NS
    assert len(set(OWNER_KLINE_PERIODS_NS)) == len(OWNER_KLINE_PERIODS_NS)
    assert 86_400_000_000_000 not in OWNER_KLINE_PERIODS_NS  # 1D must not be included


# --- multi-period projection from one tape ---


def test_periods_returned_sorted_deduplicated():
    """Periods are deduplicated and the result is keyed in ascending order."""
    events = [_trade(150_000_000_000, 500), _run_event(700_000_000_000)]
    result = build_kline_set(
        events,
        periods_ns=[900_000_000_000, DEFAULT_BAR_NS, 300_000_000_000, DEFAULT_BAR_NS],
        initial_price_ticks=10000,
    )
    assert list(result) == [DEFAULT_BAR_NS, 300_000_000_000, 900_000_000_000]
    assert len(result) == 3


def test_multi_period_same_source_consistency():
    """A 5m bar aggregates the 1m bars inside it: open = first 1m open, close = last 1m close."""
    minute = DEFAULT_BAR_NS  # 60s
    five_min = 5 * minute
    # 6 minutes of trades at 100/110/120/130/140/150 -> 1m bars close at 150.
    events = [_trade(minute * k + 10_000_000_000, 100 + 10 * k) for k in range(6)]
    events.append(_run_event(6 * minute + 1_000_000_000))  # ends inside minute 6
    result = build_kline_set(
        events,
        periods_ns=[minute, five_min],
        initial_price_ticks=10000,
    )
    m1 = build_klines(events, period_ns=minute, initial_price_ticks=10000)
    m5 = result[five_min]
    assert result[minute] == m1
    # first completed 5m bar covers minutes 0-4 (trades 100..140); last 1m close is 140.
    assert len(m5) == 1
    covered = m1[:5]
    assert m5[0].open == covered[0].open == 100
    assert m5[0].close == covered[-1].close == 140
    assert m5[0].high == max(k.high for k in covered)
    assert m5[0].low == min(k.low for k in covered)
    assert m5[0].volume == sum(k.volume for k in covered)
    assert m5[0].trade_count == sum(k.trade_count for k in covered)


def test_each_period_matches_standalone_build_klines():
    """Every series in the set equals the standalone build_klines output."""
    events = [
        _trade(10_000_000_000, 100, 5),
        _trade(120_000_000_000, 110, 3),
        _run_event(400_000_000_000),
    ]
    result = build_kline_set(
        events,
        periods_ns=OWNER_KLINE_PERIODS_NS,
        initial_price_ticks=10000,
    )
    assert list(result) == list(OWNER_KLINE_PERIODS_NS)
    for period in OWNER_KLINE_PERIODS_NS:
        assert result[period] == build_klines(events, period_ns=period, initial_price_ticks=10000)


# --- empty events ---


def test_empty_events_yield_empty_list_per_period():
    result = build_kline_set([], periods_ns=OWNER_KLINE_PERIODS_NS, initial_price_ticks=10000)
    assert result == {period: [] for period in OWNER_KLINE_PERIODS_NS}


# --- invalid periods ---


@pytest.mark.parametrize(
    "periods",
    [
        [],
        (),
        [0],
        [-60_000_000_000],
        [DEFAULT_BAR_NS, 0],
        [DEFAULT_BAR_NS, -1],
    ],
)
def test_invalid_periods_raise_value_error(periods):
    events = [_trade(50_000_000_000, 100)]
    with pytest.raises(ValueError, match="periods_ns"):
        build_kline_set(events, periods_ns=periods, initial_price_ticks=10000)


def test_duplicate_periods_are_collapsed_not_rejected():
    """Duplicates in periods_ns are deduplicated rather than raising."""
    events = [_trade(150_000_000_000, 500), _run_event(700_000_000_000)]
    result = build_kline_set(
        events,
        periods_ns=[DEFAULT_BAR_NS, DEFAULT_BAR_NS],
        initial_price_ticks=10000,
    )
    assert list(result) == [DEFAULT_BAR_NS]


# --- determinism ---


def test_deterministic_same_input_same_output():
    events = [
        _trade(10_000_000_000, 100, 5),
        _trade(70_000_000_000, 90, 3),
        _trade(130_000_000_000, 110, 7),
        _run_event(400_000_000_000),
    ]
    first = build_kline_set(events, periods_ns=OWNER_KLINE_PERIODS_NS, initial_price_ticks=10000)
    second = build_kline_set(events, periods_ns=OWNER_KLINE_PERIODS_NS, initial_price_ticks=10000)
    assert first == second
    assert list(first) == list(second)
