"""0.4.1: public-tape interval consumption must not scan the whole tape.

``tape_interval`` is called once per agent per observation, and the tape grows
with every fill of the run.  A full scan therefore makes the per-observation
cost grow with the number of trades so far -- the same defect class already
found in ``live_market.py::_newest_timestamp`` (whole-log copy per advance).
Measured before the fix: 30 agents, work per logical second flat (635.8 ->
637.6 events/s), wall clock per event +22% over 60 logical seconds on a busy
machine and +42% on a quiet one; at 2200 logical seconds the live market broke
the NFR-501 budget at 0.549 s per logical second.

The assertions here deliberately do **not** measure wall clock.  A timing
budget is machine-dependent and an O(n) scan stays comfortably fast at the
tape sizes a unit test can build, so a wall-clock test would pass while the
defect is present.  Instead they count how many tape entries the function
touches -- the behaviour itself -- the way
``test_advance_never_copies_the_whole_log`` does for the kernel log.
"""

from __future__ import annotations

import random

import pytest

from market_game_sim.agent.tape import INITIAL_CURSOR_EVENT_ID, event_id_rank, tape_interval


class _CountingFill(dict):
    """A tape entry that records every ``event_id`` read."""

    def __init__(self, event_id: str, reads: list[str]) -> None:
        super().__init__(event_id=event_id)
        self._reads = reads

    def __getitem__(self, key: str):
        value = super().__getitem__(key)
        if key == "event_id":
            self._reads.append(value)
        return value


def _counting_tape(size: int) -> tuple[list[dict], list[str]]:
    """A sorted tape of ``size`` fills plus the shared read log."""
    reads: list[str] = []
    tape = [_CountingFill(f"e{i + 2}_0", reads) for i in range(size)]
    return tape, reads


def _brute(tape: list[dict], cursor_from: str, cursor_to: str) -> list[dict]:
    """The pre-fix implementation, kept as the correctness oracle."""
    from_rank = event_id_rank(cursor_from)
    to_rank = event_id_rank(cursor_to)
    return [fill for fill in tape if from_rank < event_id_rank(fill["event_id"]) <= to_rank]


# --------------------------------------------------------------------------- #
# The behaviour under test: consumption touches the interval, not the tape
# --------------------------------------------------------------------------- #


def test_interval_consumption_does_not_touch_the_whole_tape():
    """The defect this locks: one observation reading every fill ever made."""
    size = 4096
    tape, reads = _counting_tape(size)
    # A one-fill interval in the middle of a long tape.
    got = tape_interval(tape, "e2000_0", "e2001_0")

    assert [f["event_id"] for f in got] == ["e2001_0"]
    # Reads made by the assertion above are counted too, so compare against a
    # bound that is still far below a full scan rather than an exact number.
    assert len(reads) < size // 8, f"touched {len(reads)} of {size} entries"


def test_touched_entries_grow_logarithmically_not_linearly():
    """Doubling the tape must not double the work of one observation.

    This is the load-bearing assertion: a constant-factor speed-up would keep
    the linear growth and still pass the bound above on a small tape.
    """
    small_tape, small_reads = _counting_tape(1024)
    large_tape, large_reads = _counting_tape(8192)

    tape_interval(small_tape, "e500_0", "e501_0")
    tape_interval(large_tape, "e500_0", "e501_0")

    # 8x the tape; a linear scan would read 8x as many entries.  Binary search
    # adds log2(8) == 3 probes per endpoint, so a handful either way.
    assert len(large_reads) <= len(small_reads) + 10, (
        f"{len(small_reads)} reads at 1024 entries vs {len(large_reads)} at 8192"
    )


def test_cost_follows_the_interval_size():
    """A larger interval legitimately costs more -- the fills are consumed."""
    tape, reads = _counting_tape(4096)
    tape_interval(tape, "e2000_0", "e2200_0")
    wide = len(reads)

    tape, reads = _counting_tape(4096)
    tape_interval(tape, "e2000_0", "e2001_0")
    narrow = len(reads)

    assert wide > narrow
    assert wide < 4096 // 4


# --------------------------------------------------------------------------- #
# Correctness is unchanged: the slice equals the former full scan
# --------------------------------------------------------------------------- #


def test_matches_the_former_full_scan_on_randomised_tapes():
    """Positive side: same answer as the pre-fix implementation, 500 cases."""
    rng = random.Random(20260923)
    for _ in range(500):
        ranks = sorted({(rng.randint(1, 25), rng.randint(0, 4)) for _ in range(rng.randint(0, 40))})
        tape = [{"event_id": f"e{txn}_{idx}"} for txn, idx in ranks]
        cursor_from = f"e{rng.randint(0, 26)}_{rng.randint(0, 5)}"
        cursor_to = f"e{rng.randint(0, 26)}_{rng.randint(0, 5)}"
        assert tape_interval(tape, cursor_from, cursor_to) == _brute(tape, cursor_from, cursor_to)


def test_half_open_boundaries_and_genesis_cursor():
    """``from`` exclusive, ``to`` inclusive, genesis takes everything."""
    tape = [{"event_id": "e2_0"}, {"event_id": "e3_1"}, {"event_id": "e4_0"}]

    assert [f["event_id"] for f in tape_interval(tape, "e2_0", "e4_0")] == ["e3_1", "e4_0"]
    assert tape_interval(tape, "e4_0", "e4_0") == []
    assert len(tape_interval(tape, INITIAL_CURSOR_EVENT_ID, "e9_0")) == 3
    assert tape_interval([], "e1_0", "e9_0") == []


# --------------------------------------------------------------------------- #
# Fail-closed: the narrowed scan must not narrow the safety net
# --------------------------------------------------------------------------- #


def test_malformed_fill_inside_the_interval_still_raises():
    """The observe rollback path depends on a corrupt fill aborting the txn.

    Negative side of the scan narrowing: binary search only probes O(log n)
    entries, so the returned slice is validated entry by entry to keep this
    behaviour (tests/integration/test_tape_cursor.py rolls back on it).
    """
    tape = [{"event_id": "e2_0"}, {"price_ticks": 100}, {"event_id": "e4_0"}]
    with pytest.raises(KeyError):
        tape_interval(tape, "e1_0", "e9_0")


def test_out_of_order_tape_raises_instead_of_returning_a_wrong_slice():
    """An unsorted tape breaks the slice's premise -- fail loudly, not quietly."""
    tape = [{"event_id": "e9_0"}, {"event_id": "e2_0"}, {"event_id": "e3_0"}]
    with pytest.raises(ValueError, match="out of order"):
        tape_interval(tape, "e1_0", "e5_0")
