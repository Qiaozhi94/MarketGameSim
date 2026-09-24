"""0.4.1 perf (4th growth point): what the world keeps per agent, and why.

Two structures grew with the run and were read on every observation:

* ``world["agent_bars"][agent_id]`` held the agent's private copy of every
  public fill it had ever consumed -- 36 agents x the whole tape (measured:
  78768 fill dicts after 500 logical seconds against a 2196-fill tape).
* ``world["trade_history"][agent_id]`` was ``deepcopy``-ed onto every
  observation, i.e. O(trades the agent has ever settled) per observation, ~136
  observations per logical second.

Neither is a wall-clock test.  The three previous rounds of this hunt all
showed the same thing: a timing budget cannot see O(n^2) in a short run, so
these assert the *behaviour* -- nothing per-agent grows with the trade count,
and the cheap snapshot equals the copy it replaced.  The timing gate lives in
``tests/performance/test_live_market_realtime.py``.
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from market_game_sim.agent import handler as H
from market_game_sim.experiment.h2.live_market import DEFAULT_LIVE_ROSTER, LiveMarket
from market_game_sim.experiment.roster import parse_roster
from market_game_sim.kernel.runner import EventKernel

#: Long enough for bars to close and histories to diverge in length, short
#: enough to stay a test.
LOGICAL_SECONDS = 40

COMPACT_KEYS = {"count", "cursor_from", "cursor_to"}


def _market() -> LiveMarket:
    return LiveMarket(roster=parse_roster(DEFAULT_LIVE_ROSTER))


def _drive(market, seconds=LOGICAL_SECONDS):
    for _ in range(seconds):
        market.advance()
    return market


# --------------------------------------------------------------------------- #
# The committed shape keeps no fills
# --------------------------------------------------------------------------- #


def test_stored_history_keeps_a_count_not_the_fills():
    """Positive: the count grows with the tape, the stored record does not."""
    market = _drive(_market())
    world = market.world
    stored = world["agent_bars"]

    assert stored, "no agent recorded a history -- the run proves nothing"
    counted = sum(H._history_count(entry) for entry in stored.values())
    assert counted > 0, "agents must have consumed fills, or this proves nothing"

    for agent_id, entry in stored.items():
        assert isinstance(entry, dict), f"{agent_id} still stores a fill container"
        assert set(entry) == COMPACT_KEYS, f"{agent_id} stores {sorted(entry)}"
        # The record is three scalars no matter how many fills it counts.
        assert isinstance(entry["count"], int)
        assert not any(isinstance(value, (list, dict)) for value in entry.values())


def test_stored_record_size_is_flat_while_the_history_grows():
    """The point of the change: per-agent state must not track the tape.

    Recorded at two points in the same run, so "flat" is measured against a
    history that demonstrably grew rather than asserted in the abstract.
    """
    market = _market()
    _drive(market, LOGICAL_SECONDS // 2)
    world = market.world
    early_counted = sum(H._history_count(e) for e in world["agent_bars"].values())
    early_stored = sum(len(e) for e in world["agent_bars"].values())

    _drive(market, LOGICAL_SECONDS // 2)
    late_counted = sum(H._history_count(e) for e in world["agent_bars"].values())
    late_stored = sum(len(e) for e in world["agent_bars"].values())

    assert late_counted > early_counted > 0, "history must grow, or this proves nothing"
    # Same number of agents -> same number of stored fields, whatever the count.
    assert late_stored == early_stored


# --------------------------------------------------------------------------- #
# The compact record still reproduces the history exactly
# --------------------------------------------------------------------------- #


def test_derived_history_matches_the_fills_the_agent_consumed():
    """The cursor range must derive exactly the fills, in order.

    Recorded from the observations themselves: each one's interval is what the
    agent consumed, so their concatenation is the history the old shape stored.

    **Staged vs committed (2026-09-24).**  ``recording`` books an observation at
    ``enqueue`` time, i.e. when it is *staged*; ``world["agent_bars"]`` only ever
    holds *committed* state.  An agent whose newest observation is still in
    flight when the drive stops therefore has one more interval in ``consumed``
    than in the world, and comparing the two would be comparing two different
    points in time -- not a defect in the compact record.  Those agents are
    skipped here and asserted to be exactly the ones with a pending state, so
    the exclusion cannot quietly grow to cover a real mismatch.

    This surfaced when ``mean_reversion``'s observe interval was aligned to 1 s
    (T1004): at 10 s almost every observation had committed by the time the
    drive stopped, at 1 s six agents always have one in flight.
    """
    consumed: dict[str, list] = {}
    real_enqueue = EventKernel.enqueue

    def recording(self, event):
        pending = event.get("_pending_agent_state")
        if pending is not None and "agent_history_base" in pending:
            agent_id = pending["agent_id"]
            prior = consumed.get(agent_id, [])
            consumed[agent_id] = prior[: pending["agent_history_base"]] + [
                dict(f) for f in pending["agent_history_extend"]
            ]
        return real_enqueue(self, event)

    market = _market()
    market.kernel.enqueue = recording.__get__(market.kernel, EventKernel)
    _drive(market)

    world = market.world
    assert consumed, "no observation staged a history -- the run proves nothing"
    checked = 0
    skipped = set()
    for agent_id, expected in consumed.items():
        if market.kernel.latest_pending_agent_state(agent_id) is not None:
            # Newest observation staged but not committed -- see the docstring.
            skipped.add(agent_id)
            continue
        entry = world["agent_bars"].get(agent_id)
        derived = H._history_fills(entry, world, H._history_count(entry))
        assert H._history_count(entry) == len(expected), agent_id
        assert derived == expected, agent_id
        checked += 1
    assert checked > 0
    assert max(len(v) for v in consumed.values()) > 0

    # The skip must stay honest: for an agent with an observation in flight the
    # committed history has to be a *prefix* of what was staged -- same fills,
    # same order, just short by the uncommitted tail.  A real divergence in the
    # compact record would break this even though the count check was skipped.
    for agent_id in skipped:
        expected = consumed[agent_id]
        entry = world["agent_bars"].get(agent_id)
        count = H._history_count(entry)
        assert count < len(expected), f"{agent_id}: 有在途观察却没有短于暂存期望"
        assert H._history_fills(entry, world, count) == expected[:count], agent_id


def test_derivation_is_wrong_when_the_cursor_range_is_wrong():
    """Negative control: the range is load-bearing, not decoration.

    Without this, a record that stored the right count and a meaningless range
    would pass every assertion above.
    """
    market = _drive(_market())
    world = market.world
    agent_id, entry = next(
        (a, e) for a, e in world["agent_bars"].items() if H._history_count(e) > 1
    )
    count = H._history_count(entry)
    good = H._history_fills(entry, world, count)
    assert len(good) == count

    truncated_range = dict(entry, cursor_to=entry["cursor_from"])
    assert H._history_fills(truncated_range, world, count) == []
    assert H._history_fills(entry, world, count - 1) == good[: count - 1]
    assert agent_id


# --------------------------------------------------------------------------- #
# The own-trade snapshot: a length, not a deep copy
# --------------------------------------------------------------------------- #


def test_observation_stages_a_length_not_a_copied_trade_history():
    """Shape guard.  Restoring the deep copy would change no result at all --
    the decide path still honours the legacy key -- so only a shape assertion
    catches it; the wall clock would just quietly grow again."""
    staged: list[dict] = []
    real_enqueue = EventKernel.enqueue

    def recording(self, event):
        if event.get("event_type") == "AGENT_DECIDE":
            staged.append(event)
        return real_enqueue(self, event)

    market = _market()
    market.kernel.enqueue = recording.__get__(market.kernel, EventKernel)
    _drive(market)

    assert staged, "no decision was staged -- the run proves nothing"
    with_len = [e for e in staged if "_observed_trade_history_len" in e]
    assert with_len, "observations no longer stage the length snapshot"
    assert all("_observed_trade_history" not in e for e in staged)
    assert all(isinstance(e["_observed_trade_history_len"], int) for e in with_len)
    # The market must actually have settled trades, or "no copy" is trivial.
    assert sum(len(v) for v in market.world.get("trade_history", {}).values()) > 0


def test_length_snapshot_equals_the_copy_it_replaced(monkeypatch):
    """Equivalence: prefix-of-length-n is the deep copy taken at observe time.

    The copy is recorded as the observation runs and compared against what the
    decide path reconstructs later, after further trades have been appended --
    which is exactly the case the prefix has to get right.
    """
    from market_game_sim.experiment import runner as R

    market = _market()
    world = market.world
    real_observe = R.handle_agent_observe
    snapshots: list[tuple[dict, list]] = []

    def observing(event, w, kernel, *args, **kwargs):
        agent_id = event["agent_id"]
        before = deepcopy(w.get("trade_history", {}).get(agent_id, []))
        result = real_observe(event, w, kernel, *args, **kwargs)
        pending = [
            e
            for _, _, e in kernel._queue
            if e.get("event_type") == "AGENT_DECIDE" and e.get("agent_id") == agent_id
        ]
        if pending:
            snapshots.append((pending[-1], before))
        return result

    monkeypatch.setattr(R, "handle_agent_observe", observing)
    _drive(market)

    assert snapshots, "no observation was captured -- the run proves nothing"
    non_empty = 0
    for event, copied in snapshots:
        rebuilt = H._observed_own_trades(event, world, event["agent_id"])
        assert rebuilt == copied, event["agent_id"]
        non_empty += 1 if copied else 0
    assert non_empty > 0, "every snapshot was empty -- the comparison is vacuous"


def test_legacy_event_with_a_materialised_history_still_wins():
    """Hand-built and legacy events carry the list; it must take precedence."""
    world = {"trade_history": {"a": [{"price_ticks": 1}, {"price_ticks": 2}]}}
    legacy = {"_observed_trade_history": [{"price_ticks": 99}]}
    assert H._observed_own_trades(legacy, world, "a") == [{"price_ticks": 99}]

    by_length = {"_observed_trade_history_len": 1}
    assert H._observed_own_trades(by_length, world, "a") == [{"price_ticks": 1}]

    # Neither key: fall back to the live history (pre-existing behaviour).
    assert H._observed_own_trades({}, world, "a") is None


# --------------------------------------------------------------------------- #
# Shapes accepted on read
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        (None, 0),
        ([], 0),
        ([{"price_ticks": 1}, {"price_ticks": 2}], 2),
        ({"count": 7, "cursor_from": "e1_0", "cursor_to": "e9_0"}, 7),
    ],
)
def test_history_count_reads_both_shapes(entry, expected):
    assert H._history_count(entry) == expected


def test_history_fills_reads_the_legacy_list_shape():
    """Legacy worlds seed the fills directly; the aggregate rebuild needs them."""
    fills = [{"timestamp": 0, "price_ticks": 10, "quantity_units": 1}]
    assert H._history_fills(fills, {}, 1) == fills
    assert H._history_fills(fills, {}, 0) == []


def test_legacy_list_world_keeps_its_shape_across_a_commit():
    """A world seeded with materialised fills must not silently switch shape.

    Switching would strand the fills already stored there: the compact record
    derives from a cursor range, and a seeded list has no range to derive from.
    """
    world = {
        "agent_bars": {"a": [{"timestamp": 0, "price_ticks": 10, "quantity_units": 1}]},
    }
    pending = {
        "agent_id": "a",
        "cursor": "e9_0",
        "ewma_value": None,
        "ewma_count": 0,
        "agent_history_base": 1,
        "agent_history_extend": [{"timestamp": 1, "price_ticks": 11, "quantity_units": 2}],
        "agent_history_len": 2,
        "agent_history_cursor_from": "e5_0",
        "agent_history_cursor_to": "e9_0",
    }
    kernel = EventKernel(run_id="legacy-shape")
    kernel._apply_pending_agent_state(pending, world)

    stored = world["agent_bars"]["a"]
    assert isinstance(stored, list)
    assert [f["price_ticks"] for f in stored] == [10, 11]


def test_fresh_world_commits_the_compact_record_and_truncates_on_retry():
    """Positive + retry: the compact write reproduces truncate-then-extend."""
    world: dict = {}
    kernel = EventKernel(run_id="compact-shape")

    first = {
        "agent_id": "a",
        "cursor": "e5_0",
        "ewma_value": None,
        "ewma_count": 0,
        "agent_history_base": 0,
        "agent_history_extend": [{"timestamp": 0, "price_ticks": 10, "quantity_units": 1}],
        "agent_history_len": 1,
        "agent_history_cursor_from": "e1_0",
        "agent_history_cursor_to": "e5_0",
    }
    kernel._apply_pending_agent_state(first, world)
    assert world["agent_bars"]["a"] == {"count": 1, "cursor_from": "e1_0", "cursor_to": "e5_0"}

    second = dict(
        first,
        cursor="e9_0",
        agent_history_base=1,
        agent_history_extend=[{"timestamp": 1, "price_ticks": 11, "quantity_units": 2}],
        agent_history_len=2,
        agent_history_cursor_from="e5_0",
        agent_history_cursor_to="e9_0",
    )
    kernel._apply_pending_agent_state(second, world)
    # cursor_from stays at the range's left edge; the count covers both fills.
    assert world["agent_bars"]["a"] == {"count": 2, "cursor_from": "e1_0", "cursor_to": "e9_0"}

    # A retry carries the same base and must land in the same place.
    kernel._apply_pending_agent_state(second, world)
    assert world["agent_bars"]["a"] == {"count": 2, "cursor_from": "e1_0", "cursor_to": "e9_0"}

    # An observation that resets the history (base 0) resets the left edge too.
    reset = dict(second, agent_history_base=0, agent_history_len=1)
    kernel._apply_pending_agent_state(reset, world)
    assert world["agent_bars"]["a"] == {"count": 1, "cursor_from": "e5_0", "cursor_to": "e9_0"}
