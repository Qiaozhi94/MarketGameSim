"""0.4.1 T970 (NFR-501 / AC-509): the 1:1 real-time gate for the live market.

The assertion is a hard failure, never a warning.  CLAUDE.md records why:
``T503/KPI-009`` was once silently downgraded from ``assert`` to
``warnings.warn`` and nothing caught it for a full review cycle.  A budget
that only warns is a budget nobody is held to, so
:func:`test_live_assembly_meets_the_real_time_budget` fails red when the
market is too slow.

Flakiness design (a timing test in a shared suite has to earn its place):

* **Warmup is driven but not timed.**  A cold market spends its first seconds
  on bootstrap observes against an empty book; timing those reports a number
  the steady state never reproduces.
* **The verdict is the median of many timed seconds**, not the mean and not
  the max.  A GC pause or a scheduler preemption moves one sample and the
  median absorbs it; a real regression moves all of them.
* **The pass/fail logic is tested separately from the clock.**  The negative
  case judges a real measurement against an impossible budget, so "does the
  gate actually fail when over budget" is answered deterministically rather
  than by racing the machine.
* Measured headroom on the development machine is ~18x (median 0.027 s
  against a 0.5 s budget, 30 agents), so ordinary hardware variation cannot
  produce a false red; a red here means the market genuinely slowed down.

What this gate does **not** claim: that the market is economically alive.
The T966 assembly currently trades almost exclusively during the cold-start
anchor (measured trade/order = 0.0012 over 60 logical seconds, price still at
the initial tick), so the wall clock below describes a market whose strategy
families are not yet trading.  :func:`test_measurement_describes_a_live_market`
holds the floor that keeps a fully dead market from passing silently, and the
artifact carries ``trade_per_order`` so the idleness is visible to whoever
reads the number rather than buried.
"""

from __future__ import annotations

import json

import pytest

from market_game_sim.experiment.h2.live_market import DEFAULT_LIVE_ROSTER, LiveMarket
from market_game_sim.experiment.roster import parse_roster
from market_game_sim.kernel.runner import EventKernel
from market_game_sim.metrics.live_perf import (
    BUDGET_SECONDS_PER_LOGICAL_SECOND,
    FAIL,
    PASS,
    VERDICT_BUDGET,
    LivePerfError,
    environment,
    export,
    measure,
    verdict,
)

WARMUP_SECONDS = 5
TIMED_SECONDS = 20

#: DEFAULT_LIVE_ROSTER: 6 market_maker_v2 + 9 trend + 9 mean-reversion + 6 noise.
EXPECTED_AGENTS = 30

#: The assembly list T982 records beside the wall clock, in roster order.
EXPECTED_FAMILIES = (
    ("market_maker_v2", 6),
    ("trend_following", 9),
    ("mean_reversion", 9),
    ("sentiment_noise", 6),
)


class _RosterlessMarket:
    """A market driven without a roster -- the negative case for T982."""

    def __init__(self) -> None:
        self.kernel = EventKernel()

    def advance(self) -> None:
        return None


def _market() -> LiveMarket:
    return LiveMarket(roster=parse_roster(DEFAULT_LIVE_ROSTER))


@pytest.fixture(scope="module")
def report():
    """One measured run of the live assembly, shared by the assertions."""
    return measure(_market(), logical_seconds=TIMED_SECONDS, warmup_seconds=WARMUP_SECONDS)


# --------------------------------------------------------------------------- #
# The gate itself (NFR-501 / AC-509)
# --------------------------------------------------------------------------- #


def test_live_assembly_meets_the_real_time_budget(report):
    """Positive side: the live assembly runs 1:1 or better."""
    status, failed = verdict(report, budget_seconds=BUDGET_SECONDS_PER_LOGICAL_SECOND)
    assert report.agent_count == EXPECTED_AGENTS
    assert failed == []
    assert status == PASS, (
        f"NFR-501 breached: median {report.median_wall:.3f}s/logical-second exceeds "
        f"{BUDGET_SECONDS_PER_LOGICAL_SECOND}s on {report.environment}; "
        f"per-second samples {[round(v, 3) for v in report.wall_seconds]}"
    )


def test_gate_fails_when_the_budget_is_exceeded(report):
    """Negative side: an over-budget measurement is reported as FAIL.

    Judged against an impossible budget rather than a deliberately slowed
    market, so the assertion exercises the verdict path without depending on
    how fast the machine happens to be.
    """
    status, failed = verdict(report, budget_seconds=1e-9)
    assert status == FAIL
    assert failed == [VERDICT_BUDGET]


def test_budget_boundary_passes_at_equality_and_fails_just_under(report):
    median = report.median_wall
    assert verdict(report, budget_seconds=median)[0] == PASS
    assert verdict(report, budget_seconds=median * 0.99)[0] == FAIL


# --------------------------------------------------------------------------- #
# The measurement has to describe a market, not an empty loop
# --------------------------------------------------------------------------- #


def test_measurement_describes_a_live_market(report):
    """A market that never trades at all would pass the clock gate trivially.

    This is the floor, not a liveness claim: the assembly currently trades
    only during the cold-start anchor (see module docstring).  Raising this
    floor belongs to T967's quality gate, which judges the market itself.
    """
    assert report.mix.get("TRADE_SETTLE", 0) > 0
    assert report.trade_per_order > 0
    assert report.mix.get("ORDER_ARRIVAL", 0) > 0


def test_transaction_mix_is_reported_for_every_spec_named_type(report):
    """spec §7 step 1: the mix is the artifact a retreat decision cites."""
    for event_type in ("ORDER_ARRIVAL", "ORDER_CANCELLED", "TRADE_SETTLE"):
        assert event_type in report.mix
        assert report.share(event_type) > 0
    assert report.total_records == sum(report.mix.values())


def test_cancel_share_is_reported_rather_than_assumed(report):
    """ADR-011 predicted a cancel-dominated mix; the artifact has to show it.

    No threshold is asserted -- spec §7 owns the retreat trigger, and pinning
    a share here would silently create a second gate.
    """
    assert report.share("ORDER_CANCELLED") > 0
    assert report.share("ORDER_ARRIVAL") > report.share("TRADE_SETTLE")


def test_environment_is_recorded_for_ac509(report):
    env = report.environment
    for key in ("os", "python", "machine", "cpu_count"):
        assert env.get(key) is not None
    assert environment()["python"] == env["python"]


def test_assembly_list_is_recorded_for_ac509(report):
    """T982: the number is worthless without the assembly it was measured on."""
    assert report.roster_id is not None
    assert report.roster_families == EXPECTED_FAMILIES
    assert sum(count for _, count in report.roster_families) == EXPECTED_AGENTS


def test_assembly_list_is_none_when_the_market_has_no_roster():
    """A rosterless market records ``None``, never an empty assembly."""
    report = measure(_RosterlessMarket(), logical_seconds=1)
    assert report.roster_families is None
    assert report.to_dict()["roster_families"] is None


def test_artifact_round_trips_with_verdict_and_boundary(report, tmp_path):
    out = export(report, tmp_path / "live-perf.json")
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["verdict"] in {PASS, FAIL}
    assert payload["evidence_label"] == "engineering-demonstration"
    assert payload["budget_seconds_per_logical_second"] == BUDGET_SECONDS_PER_LOGICAL_SECOND
    assert payload["agent_count"] == EXPECTED_AGENTS
    assert payload["roster_id"] == report.roster_id
    assert payload["roster_families"] == dict(EXPECTED_FAMILIES)
    assert len(payload["wall_seconds"]) == TIMED_SECONDS
    assert payload["environment"]["python"] == report.environment["python"]


def test_export_records_failure_when_over_budget(report, tmp_path):
    out = export(report, tmp_path / "over.json", budget_seconds=1e-9)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["verdict"] == FAIL
    assert payload["failed"] == [VERDICT_BUDGET]


# --------------------------------------------------------------------------- #
# Fail closed
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"logical_seconds": 0}, "INVALID_DURATION"),
        ({"logical_seconds": -1}, "INVALID_DURATION"),
        ({"logical_seconds": 1.5}, "INVALID_DURATION"),
        ({"logical_seconds": 1, "warmup_seconds": -1}, "INVALID_WARMUP"),
        ({"logical_seconds": 1, "warmup_seconds": 1.5}, "INVALID_WARMUP"),
    ],
)
def test_measure_rejects_invalid_durations(kwargs, code):
    with pytest.raises(LivePerfError) as exc:
        measure(_market(), **kwargs)
    assert exc.value.code == code


@pytest.mark.parametrize("budget", [0, -1, -0.5, True, "0.5"])
def test_verdict_rejects_invalid_budget(report, budget):
    with pytest.raises(LivePerfError) as exc:
        verdict(report, budget_seconds=budget)
    assert exc.value.code == "INVALID_BUDGET"


# --------------------------------------------------------------------------- #
# The kernel tail accessor the measurement depends on
# --------------------------------------------------------------------------- #


def test_tail_accessor_matches_the_full_copy():
    """``committed_records_tail`` must be the tail of ``committed_records``.

    The measurement reads the tail because the full copy is O(total) per
    call; if the two ever disagree the measurement silently stops describing
    the market it is timing.
    """
    market = _market()
    for _ in range(3):
        market.advance()
    full = market.kernel.committed_records
    assert market.kernel.committed_record_count == len(full)
    assert market.kernel.committed_records_tail(0) == []
    assert market.kernel.committed_records_tail(5) == full[-5:]
    assert market.kernel.committed_records_tail(len(full) + 100) == full


def test_tail_accessor_returns_defensive_copies():
    """Mutating the returned tail must not corrupt kernel state."""
    market = _market()
    market.advance()
    tail = market.kernel.committed_records_tail(4)
    assert tail
    tail[0]["event_type"] = "TAMPERED"
    assert market.kernel.committed_records_tail(4)[0]["event_type"] != "TAMPERED"


@pytest.mark.parametrize("count", [-1, 1.5, "4"])
def test_tail_accessor_rejects_invalid_counts(count):
    kernel = EventKernel(run_id="t970-guard")
    with pytest.raises(ValueError):
        kernel.committed_records_tail(count)
