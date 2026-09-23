"""0.4.1 perf: the completed-bar sequence is folded incrementally.

`_completed_bars_with_zero_fill` re-aggregated an agent's entire cumulative
trade history on every observation, so one observation cost O(all trades this
agent ever saw).  With 30 agents observing once per logical second that was the
dominant term of the live market's wall clock (profile: 76% of cumtime).  The
incremental aggregate makes one observation cost O(this interval's fills).

These tests assert the *behaviour*, not the wall clock, for the reason
``test_advance_never_copies_the_whole_log`` already records: a timing assertion
is machine-dependent and a short test need not go red on an O(n^2) path, so the
thing that must not happen is asserted directly.  The equivalence tests hold
the other half: a faster sequence that differs from the old one is not a
performance fix, it is a behaviour change.
"""

from __future__ import annotations

import random

import pytest

from market_game_sim.agent import handler as H

BAR_NS = 60_000_000_000


def _fill(ts: int, price: int, qty: int = 1) -> dict:
    return {"timestamp": ts, "price_ticks": price, "quantity_units": qty}


def _rebuild(history, up_to_ts):
    """The pre-0.4.1 implementation, kept in tree as the equivalence oracle."""
    return H._completed_bars_with_zero_fill(list(history), bar_ns=BAR_NS, up_to_ts=up_to_ts)


def _incremental(history, up_to_ts):
    state = H._extend_bar_state(None, history, bar_ns=BAR_NS)
    return H._completed_bars_from_state(state, bar_ns=BAR_NS, up_to_ts=up_to_ts)


# --------------------------------------------------------------------------- #
# Equivalence: the sequence must not change
# --------------------------------------------------------------------------- #


def test_incremental_bar_state_matches_full_rebuild():
    """Bar for bar, field for field, against the old implementation."""
    history = [
        _fill(0, 100, 10),
        _fill(30_000_000_000, 110, 5),
        _fill(4 * BAR_NS, 120, 7),
        _fill(4 * BAR_NS + 1, 90, 3),
    ]
    for up_to in (0, BAR_NS, 3 * BAR_NS, 5 * BAR_NS, 9 * BAR_NS):
        assert _incremental(history, up_to) == _rebuild(history, up_to), up_to


def test_incremental_matches_rebuild_on_random_histories():
    """500 random histories -- open/close depend on within-bar order, so a
    fold that reordered anything would show up here."""
    rng = random.Random(0x0401)
    for case in range(500):
        n = rng.randint(1, 40)
        history = []
        ts = rng.randrange(0, 3 * BAR_NS)
        for _ in range(n):
            ts += rng.randrange(0, BAR_NS // 2)
            history.append(_fill(ts, rng.randint(1, 5000), rng.randint(1, 50)))
        up_to = ts + rng.randrange(0, 6 * BAR_NS)
        assert _incremental(history, up_to) == _rebuild(history, up_to), case


def test_folding_in_two_steps_matches_folding_in_one():
    """The state chain folds interval by interval; that must equal one fold of
    the concatenation, or a resumed agent would see a different history."""
    first = [_fill(0, 100, 10), _fill(10_000_000_000, 105, 2)]
    second = [_fill(BAR_NS + 5, 108, 4), _fill(3 * BAR_NS, 99, 1)]
    stepwise = H._extend_bar_state(
        H._extend_bar_state(None, first, bar_ns=BAR_NS), second, bar_ns=BAR_NS
    )
    at_once = H._extend_bar_state(None, first + second, bar_ns=BAR_NS)
    assert stepwise == at_once
    up_to = 5 * BAR_NS
    assert H._completed_bars_from_state(stepwise, bar_ns=BAR_NS, up_to_ts=up_to) == _rebuild(
        first + second, up_to
    )


def test_rebuild_from_history_recovers_a_missing_aggregate():
    """Legacy worlds and tests seed ``agent_bars`` without an aggregate; the
    fail-safe direction is to rebuild it, never to start empty."""
    history = [_fill(0, 100, 10), _fill(2 * BAR_NS, 120, 4)]
    recovered = H._bar_state_from_history(history, bar_ns=BAR_NS)
    assert recovered == H._extend_bar_state(None, history, bar_ns=BAR_NS)
    assert H._completed_bars_from_state(recovered, bar_ns=BAR_NS, up_to_ts=4 * BAR_NS) == _rebuild(
        history, 4 * BAR_NS
    )


# --------------------------------------------------------------------------- #
# Zero fill, both directions
# --------------------------------------------------------------------------- #


def test_empty_bars_inherit_the_previous_close_with_zero_volume():
    """代理策略 §3.1, the positive case."""
    history = [_fill(0, 100, 10), _fill(3 * BAR_NS, 110, 5)]
    bars = _incremental(history, 4 * BAR_NS)
    assert [b.trade_count for b in bars] == [1, 0, 0, 1]
    assert [b.volume for b in bars] == [10, 0, 0, 5]
    assert [b.close for b in bars] == [100, 100, 100, 110]
    assert bars[1].open == bars[1].high == bars[1].low == 100


def test_traded_bars_are_not_zero_filled():
    """The negative case: a bar with trades keeps its own OHLC, never the
    previous close -- the bug a one-sided zero-fill test would not catch."""
    history = [_fill(0, 100, 10), _fill(BAR_NS + 1, 130, 2), _fill(BAR_NS + 2, 90, 3)]
    bars = _incremental(history, 2 * BAR_NS)
    assert [b.trade_count for b in bars] == [1, 2]
    assert (bars[1].open, bars[1].high, bars[1].low, bars[1].close) == (130, 130, 90, 90)
    assert bars[1].volume == 5


def test_in_progress_bar_is_never_visible():
    """A trade at t=0 observed at 30s yields nothing; at 90s yields bar 0."""
    history = [_fill(0, 100, 10)]
    assert _incremental(history, 30_000_000_000) == []
    assert _incremental(history, 90_000_000_000) == _rebuild(history, 90_000_000_000)


def test_empty_history_yields_no_bars():
    state = H._extend_bar_state(None, [], bar_ns=BAR_NS)
    assert state["first_bar"] is None
    assert H._completed_bars_from_state(state, bar_ns=BAR_NS, up_to_ts=9 * BAR_NS) == []


# --------------------------------------------------------------------------- #
# The growth itself
# --------------------------------------------------------------------------- #


def _touched(prior_history, interval):
    """Per-fill field reads during one fold, counted at ``_fill_fields``."""
    calls = 0
    real = H._fill_fields

    def counting(fill):
        nonlocal calls
        calls += 1
        return real(fill)

    state = H._extend_bar_state(None, prior_history, bar_ns=BAR_NS)
    H._fill_fields = counting
    try:
        H._extend_bar_state(state, interval, bar_ns=BAR_NS)
    finally:
        H._fill_fields = real
    return calls


def test_one_observation_touches_only_its_own_interval():
    """The defect restated: an observation must not re-read the history."""
    interval = [_fill(100 * BAR_NS + i, 100 + i) for i in range(5)]
    small = [_fill(i, 100 + i) for i in range(10)]
    assert _touched(small, interval) == len(interval)


def test_touched_work_does_not_grow_with_history():
    """Eight times the history, same work -- this is what makes it a
    complexity fix rather than a constant-factor one."""
    interval = [_fill(500 * BAR_NS + i, 100 + i) for i in range(5)]
    small = [_fill(i * 1_000_000, 100 + (i % 7)) for i in range(200)]
    big = [_fill(i * 1_000_000, 100 + (i % 7)) for i in range(1600)]
    assert len(big) == 8 * len(small)
    assert _touched(big, interval) == _touched(small, interval)


def test_rendering_cost_follows_bars_not_trades():
    """The sequence length is inherent to the contract; the trade count is not.
    Same span, 100x the trades -> the same number of bars rendered."""
    span = 6 * BAR_NS
    sparse = [_fill(k * BAR_NS, 100 + k) for k in range(6)]
    dense = [_fill(k * BAR_NS + j, 100 + k) for k in range(6) for j in range(100)]
    thin = H._extend_bar_state(None, sparse, bar_ns=BAR_NS)
    thick = H._extend_bar_state(None, dense, bar_ns=BAR_NS)
    assert len(thick["bars"]) == len(thin["bars"])
    assert len(H._completed_bars_from_state(thick, bar_ns=BAR_NS, up_to_ts=span)) == len(
        H._completed_bars_from_state(thin, bar_ns=BAR_NS, up_to_ts=span)
    )


@pytest.mark.parametrize("bad", [{"first_bar": None, "bars": {}}])
def test_state_without_bars_renders_nothing(bad):
    """An aggregate that saw no trade renders nothing rather than guessing."""
    assert H._completed_bars_from_state(bad, bar_ns=BAR_NS, up_to_ts=9 * BAR_NS) == []
