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
* Measured headroom on the development machine is ~12x (median 0.042 s
  against a 0.5 s budget, 36 agents), so ordinary hardware variation cannot
  produce a false red; a red here means the market genuinely slowed down.

Baseline history, because the number only means something with its market:
the first measurement (median 0.027 s, trade/order 0.0012) was taken on an
assembly that barely traded -- ``market_maker_v2`` quoted one side at a time
and every maker moved in lockstep, so the book was single-sided at every
observation and no signal family could place an order.  With the quoting
phase dispersed per agent, the same 60 logical seconds settle 234 trades
instead of 12 (trade/order 0.0211) and the median rose to 0.037 s.  Roughly
17x the matching work for ~1.4x the wall clock: the clock gate was never the
binding constraint, the dead market was.  T973 then took the assembly to 12
market makers (SC-501 needs 5 book levels and 6 makers only reached 2), which
is the 36-agent baseline measured above: 300 trades per 60 logical seconds,
median 0.042 s.

What this gate still does **not** claim: that the market is economically
*healthy*.  Judging price discovery, spread and depth is T967's quality gate.
:func:`test_measurement_describes_a_live_market` only holds a floor against a
silently dead market, and the artifact carries ``trade_per_order`` so the
trading intensity is visible to whoever reads the number rather than buried.
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
    PerfReport,
    environment,
    export,
    measure,
    verdict,
)

#: Liveness floor for the timed window below (20 s), where the current
#: assembly settles 128 trades at trade-per-order 0.0135 (the ratio fell from
#: 0.0229 when T973 doubled the market makers -- more quotes in the
#: denominator, not a worse market).  Trading here is
#: deterministic -- keyed draws, no wall-clock input -- so the margin guards
#: against a behaviour regression, not against timing noise.
MIN_TRADES = 60
MIN_TRADE_PER_ORDER = 0.005

WARMUP_SECONDS = 5
TIMED_SECONDS = 20

#: DEFAULT_LIVE_ROSTER: 12 market_maker_v2 + 9 trend + 9 mean-reversion + 6 noise.
#: 0.4.1 T973 把做市商从 6 加到 12（并把报价分散从 ±3 放宽到 ±7）——6 个做市商的
#: 中位档位只有 2，达不到 SC-501 的 5 档门限。装配变了，本文件的期望值随之更新：
#: 这里钉住的是「性能门测的就是主装配」，不是某个具体数字。
EXPECTED_AGENTS = 36

#: The assembly list T982 records beside the wall clock, in roster order.
EXPECTED_FAMILIES = (
    ("market_maker_v2", 12),
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


def test_verdict_divides_by_logical_time_not_by_advance_calls():
    """AC-509 的分母是逻辑秒，不是 advance 次数。

    `LiveMarket.advance()` 目标是 +1 逻辑秒，但收尾把逻辑时钟拉到最新事件时间戳，
    事件跑在前面时会超调——实测平均 1.54 秒/步。按调用次数归一会把「墙钟/逻辑秒」
    系统性报高 1.5 倍；方向上保守，但口径错了就无法与质量报告对账。
    """
    overshooting = PerfReport(
        agent_count=1,
        logical_seconds=4,
        warmup_seconds=0,
        wall_seconds=(0.6, 0.6, 0.6, 0.6),
        logical_spans=(2.0, 2.0, 2.0, 2.0),
        mix={},
        total_records=0,
    )
    assert overshooting.wall_per_logical_second == (0.3, 0.3, 0.3, 0.3)
    assert overshooting.tail_median_wall == pytest.approx(0.3)
    assert overshooting.logical_seconds_elapsed == pytest.approx(8.0)
    assert verdict(overshooting, budget_seconds=0.5) == (PASS, [])

    no_clock = PerfReport(
        agent_count=1,
        logical_seconds=4,
        warmup_seconds=0,
        wall_seconds=(0.6, 0.6, 0.6, 0.6),
        mix={},
        total_records=0,
    )
    assert no_clock.tail_median_wall == pytest.approx(0.6)
    assert verdict(no_clock, budget_seconds=0.5) == (FAIL, [VERDICT_BUDGET])


def test_measurement_records_real_logical_time(report):
    """实测装配下 advance 次数与逻辑秒不是 1:1，记录必须把两者都留下。"""
    assert len(report.logical_spans) == len(report.wall_seconds)
    assert report.logical_seconds_elapsed > report.logical_seconds
    payload = report.to_dict()
    assert payload["advance_calls"] == TIMED_SECONDS
    assert payload["logical_seconds_elapsed"] > payload["advance_calls"]


def test_verdict_reads_the_tail_not_the_whole_window():
    """AC-509 口径：末段中位。全窗中位会把「越跑越慢」判成通过。

    这条用的是合成序列，不是实测——判据本身必须能脱离机器速度被验证。同一条
    序列下全窗中位 0.10 < 0.5 而末段中位 0.90 > 0.5：如果判据取全窗，一次末段
    衰减的运行会在性能门判绿、在质量报告判红，仓库里同一命题就有了两个答案。
    """
    growing = PerfReport(
        agent_count=1,
        logical_seconds=8,
        warmup_seconds=0,
        wall_seconds=(0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.9, 0.9),
        mix={},
        total_records=0,
    )
    assert growing.median_wall == pytest.approx(0.1)
    assert growing.tail_median_wall == pytest.approx(0.9)
    assert verdict(growing, budget_seconds=0.5) == (FAIL, [VERDICT_BUDGET])

    flat = PerfReport(
        agent_count=1,
        logical_seconds=8,
        warmup_seconds=0,
        wall_seconds=(0.1,) * 8,
        mix={},
        total_records=0,
    )
    assert verdict(flat, budget_seconds=0.5) == (PASS, [])


def test_tail_median_matches_the_quality_report_caliber():
    """与 metrics/quality_run.py::_tail_median 同一口径，不得各算各的。"""
    from market_game_sim.metrics.quality_run import _tail_median

    walls = (0.10, 0.12, 0.14, 0.16, 0.30, 0.32, 0.34, 0.36)
    report = PerfReport(
        agent_count=1,
        logical_seconds=len(walls),
        warmup_seconds=0,
        wall_seconds=walls,
        mix={},
        total_records=0,
    )
    per_second = [(float(i + 1), w) for i, w in enumerate(walls)]
    assert report.tail_median_wall == pytest.approx(_tail_median(per_second))


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
    """边界判定读的必须是 AC-509 口径（末段中位），不是全窗中位。"""
    tail = report.tail_median_wall
    assert verdict(report, budget_seconds=tail)[0] == PASS
    assert verdict(report, budget_seconds=tail * 0.99)[0] == FAIL


# --------------------------------------------------------------------------- #
# The measurement has to describe a market, not an empty loop
# --------------------------------------------------------------------------- #


def test_measurement_describes_a_live_market(report):
    """A market that never trades at all would pass the clock gate trivially.

    The floor sits well below the measured baseline (128 trades /
    trade-per-order 0.0135 in this 20 s window) and well above the
    pre-phase-fix assembly (0.0012): it catches a regression that
    kills trading -- the single-sided-book deadlock this suite already lived
    through -- without turning ordinary variation red.  Judging whether the
    trading that happens is *good* remains T967's quality gate.
    """
    assert report.mix.get("TRADE_SETTLE", 0) >= MIN_TRADES
    assert report.trade_per_order >= MIN_TRADE_PER_ORDER
    assert report.mix.get("ORDER_ARRIVAL", 0) > 0


def test_unit_cost_series_separates_a_busier_market_from_a_slower_one(report):
    """Wall clock alone cannot tell the two apart; wall/event can.

    A rising per-second wall time is only a defect if the work per second
    stayed flat.  This series is what the next O(n^2) hunt reads, so it has to
    line up with ``wall_seconds`` second by second and carry real counts.
    """
    assert len(report.events_per_second) == len(report.wall_seconds)
    assert sum(report.events_per_second) > 0
    assert all(count >= 0 for count in report.events_per_second)
    costs = [c for c in report.wall_per_event if c is not None]
    assert len(costs) == sum(1 for c in report.events_per_second if c > 0)
    assert all(c > 0 for c in costs)


def test_idle_seconds_report_no_unit_cost_instead_of_zero():
    """An idle second has no unit cost; 0.0 would flatten the growth curve."""
    report = measure(_RosterlessMarket(), logical_seconds=3)
    assert report.events_per_second == (0, 0, 0)
    assert report.wall_per_event == (None, None, None)
    assert report.to_dict()["wall_per_event_seconds"] == [None, None, None]


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
