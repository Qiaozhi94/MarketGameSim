"""0.4.1 T970 (NFR-501 / AC-509): real-time budget measurement for live markets.

spec §7 freezes the order in which performance retreats may be taken, and it
freezes the *first* step as measurement: produce the transaction mix before
touching any knob.  This module is that step, and the artifact it exports is
what a retreat decision has to cite.

Two things it deliberately does **not** do:

* It does not own the 0.5 s/logical-second budget -- ``spec.md`` §6/NFR-501
  does.  ``BUDGET_SECONDS_PER_LOGICAL_SECOND`` here is a mirror, and
  :func:`verdict` takes the budget as an argument, so metrics code can never
  quietly loosen the gate.
* It does not assemble a market.  It measures anything satisfying
  :class:`DrivableMarket` -- since T966 that is ``LiveMarket(roster=...)``,
  whose ``DEFAULT_LIVE_ROSTER`` is the assembly NFR-501 is about.

Measurement fidelity note: this module reads only the *tail* of the committed
record list (``EventKernel.committed_records_tail``).  Reading the full list
per step would make the measuring tool itself O(total^2) -- which is exactly
the defect T970 found in the live drive loop, so a measurement built on the
full copy would report its own overhead as the market's cost.

Stdlib only (KR-005).
"""

from __future__ import annotations

import json
import os
import pathlib
import platform
import statistics
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Protocol

from market_game_sim.kernel.runner import EventKernel

#: Mirror of spec §6 / NFR-501.  The spec owns it; see module docstring.
BUDGET_SECONDS_PER_LOGICAL_SECOND = 0.5

#: Event types spec §7 names for the mix ("撤挂事务占绝大多数" is the claim
#: the artifact has to confirm or refute).
MIX_EVENT_TYPES = ("ORDER_ARRIVAL", "ORDER_CANCELLED", "TRADE_SETTLE")

PASS = "PASS"
FAIL = "FAIL"

VERDICT_BUDGET = "wall_clock_budget"

#: AC-509: the verdict reads the last quarter of the timed seconds.
TAIL_FRACTION = 0.25


class LivePerfError(ValueError):
    """Measurement rejected; ``code`` is stable and safe to assert on."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


class DrivableMarket(Protocol):
    """What :func:`measure` needs: advance one logical second, expose a kernel."""

    kernel: EventKernel

    def advance(self) -> None: ...


def environment() -> dict[str, Any]:
    """The target environment AC-509/T982 has to record alongside the number."""
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "cpu_count": os.cpu_count(),
        "drive_note": "single-threaded drive loop; no kernel parallelism",
    }


@dataclass(frozen=True)
class PerfReport:
    """One measured run: per-second wall clock plus the §7 transaction mix."""

    agent_count: int
    logical_seconds: int
    warmup_seconds: int
    wall_seconds: tuple[float, ...]
    mix: dict[str, int]
    total_records: int
    #: New committed records per timed second, aligned with ``wall_seconds``.
    #: Wall clock alone cannot tell a busier market from a slower one: a rising
    #: per-second wall time means either more work per second (fine, that is an
    #: active market) or the same work getting slower (an O(n^2) read path, the
    #: defect class already found once in ``_newest_timestamp``).  Dividing the
    #: two separates the cases.
    events_per_second: tuple[int, ...] = ()
    #: 每步实际推进的逻辑秒数。`LiveMarket.advance()` 目标是 +1 秒，但收尾会把
    #: 逻辑时钟拉到最新事件时间戳，事件跑在前面时会**超调**（实测平均 1.54 秒/步）。
    #: AC-509 的分母是逻辑秒，不是 advance 次数，所以判定必须按这个跨度归一——
    #: 与 `metrics/quality_run.py::_tail_median` 的 `_span` 处理同源。
    #: 空元组或 NaN 表示市场没有逻辑时钟，此时退化为「一步一秒」。
    logical_spans: tuple[float, ...] = ()
    roster_id: str | None = None
    #: AC-509/T982: the assembly the number was measured on, family by family.
    #: ``None`` means the market exposed no roster -- never an empty dict, so a
    #: report cannot silently claim "measured on nothing" as a valid assembly.
    roster_families: tuple[tuple[str, int], ...] | None = None
    environment: dict[str, Any] = field(default_factory=environment)

    @property
    def wall_per_logical_second(self) -> tuple[float, ...]:
        """逐步的「墙钟秒 / 逻辑秒」——AC-509 判定读的就是这个序列。"""
        if len(self.logical_spans) != len(self.wall_seconds):
            return self.wall_seconds
        rates: list[float] = []
        for wall, span in zip(self.wall_seconds, self.logical_spans, strict=True):
            usable = span if span == span and span > 0 else 1.0
            rates.append(wall / usable)
        return tuple(rates)

    @property
    def logical_seconds_elapsed(self) -> float:
        """本次测量实际覆盖的逻辑秒数（≠ advance 次数）。"""
        if not self.logical_spans:
            return float(self.logical_seconds)
        total = sum(v for v in self.logical_spans if v == v)
        return total or float(self.logical_seconds)

    @property
    def tail_median_wall(self) -> float:
        """AC-509 的判定口径：末段（最后 25%）逐秒墙钟的中位数。

        不是全窗中位/平均（会掩盖「单位成本随运行增长」这件事，而这个仓库已经
        连查出三处这类缺陷），也不是逐秒峰值（会被 GC 抖动误伤）。与
        ``metrics/quality_run.py::_tail_median`` 同一口径——同一命题只能有一个
        判据，否则同一次运行会出现「性能门绿、质量报告红」而无人知道该信哪个。
        样本不足以切出末段时退化为全体中位。
        """
        rates = self.wall_per_logical_second
        cut = max(1, int(len(rates) * TAIL_FRACTION))
        return statistics.median(rates[-cut:])

    @property
    def median_wall(self) -> float:
        return statistics.median(self.wall_seconds)

    @property
    def max_wall(self) -> float:
        return max(self.wall_seconds)

    @property
    def wall_per_event(self) -> tuple[float | None, ...]:
        """Per-second wall clock divided by that second's new records.

        ``None`` for a second that committed nothing -- an idle second has no
        unit cost, and reporting 0.0 would flatten a growth curve that is the
        whole point of this series.
        """
        if len(self.events_per_second) != len(self.wall_seconds):
            return ()
        return tuple(
            (wall / count) if count > 0 else None
            for wall, count in zip(self.wall_seconds, self.events_per_second, strict=True)
        )

    @property
    def trade_per_order(self) -> float:
        arrivals = self.mix.get("ORDER_ARRIVAL", 0)
        if arrivals == 0:
            return 0.0
        return self.mix.get("TRADE_SETTLE", 0) / arrivals

    def share(self, event_type: str) -> float:
        if self.total_records == 0:
            return 0.0
        return self.mix.get(event_type, 0) / self.total_records

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "roster_id": self.roster_id,
            "roster_families": (
                None if self.roster_families is None else dict(self.roster_families)
            ),
            "agent_count": self.agent_count,
            "logical_seconds": self.logical_seconds,
            "warmup_seconds": self.warmup_seconds,
            "wall_seconds": [round(v, 6) for v in self.wall_seconds],
            "tail_median_wall_seconds": round(self.tail_median_wall, 6),
            "logical_seconds_elapsed": round(self.logical_seconds_elapsed, 6),
            "advance_calls": self.logical_seconds,
            "median_wall_seconds": round(self.median_wall, 6),
            "mean_wall_seconds": round(statistics.fmean(self.wall_seconds), 6),
            "max_wall_seconds": round(self.max_wall, 6),
            "events_per_second": list(self.events_per_second),
            "wall_per_event_seconds": [
                None if v is None else round(v, 9) for v in self.wall_per_event
            ],
            "mix": dict(sorted(self.mix.items())),
            "mix_share": {et: round(self.share(et), 6) for et in MIX_EVENT_TYPES if et in self.mix},
            "total_records": self.total_records,
            "trade_per_order": round(self.trade_per_order, 6),
            "environment": self.environment,
        }


def measure(
    market: DrivableMarket,
    *,
    logical_seconds: int,
    warmup_seconds: int = 0,
) -> PerfReport:
    """Drive ``market`` and time each logical second after the warmup.

    The warmup seconds are driven but not timed: a cold market spends its
    first seconds on bootstrap observes against an empty book, and timing
    those reports a number the steady state never reproduces.
    """
    if type(logical_seconds) is not int or logical_seconds < 1:
        raise LivePerfError("INVALID_DURATION", "logical_seconds must be an int >= 1")
    if type(warmup_seconds) is not int or warmup_seconds < 0:
        raise LivePerfError("INVALID_WARMUP", "warmup_seconds must be an int >= 0")

    for _ in range(warmup_seconds):
        market.advance()

    walls: list[float] = []
    events: list[int] = []
    spans: list[float] = []
    before = market.kernel.committed_record_count
    clock_before = _logical_seconds_now(market)
    for _ in range(logical_seconds):
        started = time.perf_counter()
        market.advance()
        walls.append(time.perf_counter() - started)
        after = market.kernel.committed_record_count
        events.append(after - before)
        before = after
        clock_after = _logical_seconds_now(market)
        spans.append(max(clock_after - clock_before, 0.0))
        clock_before = clock_after

    kernel = market.kernel
    mix = Counter(r.get("event_type") for r in kernel.committed_records)
    specs = getattr(market, "config", None)
    agent_count = len(getattr(specs, "agent_specs", ()) or ())
    return PerfReport(
        agent_count=agent_count,
        logical_seconds=logical_seconds,
        warmup_seconds=warmup_seconds,
        wall_seconds=tuple(walls),
        logical_spans=tuple(spans),
        events_per_second=tuple(events),
        mix={str(k): int(v) for k, v in mix.items() if k is not None},
        total_records=kernel.committed_record_count,
        roster_id=getattr(market, "roster_id", None),
        roster_families=_roster_families(market),
    )


def _logical_seconds_now(market: object) -> float:
    """市场当前的逻辑时钟（秒）。没有逻辑时钟的市场按「一步一秒」处理。"""
    logical_ns = getattr(market, "logical_ns", None)
    if logical_ns is None:
        return float("nan")
    return int(logical_ns) / 1e9


def _roster_families(market: object) -> tuple[tuple[str, int], ...] | None:
    """The assembly list AC-509 has to record beside the wall clock (T982)."""
    roster = getattr(market, "roster", None)
    families = getattr(roster, "families", None)
    if not families:
        return None
    return tuple((str(f.family_id), int(f.count)) for f in families)


def verdict(
    report: PerfReport,
    *,
    budget_seconds: float = BUDGET_SECONDS_PER_LOGICAL_SECOND,
) -> tuple[str, list[str]]:
    """Judge a report against the budget.  Returns ``(verdict, failed)``.

    The budget is an argument, not a constant read from this module, so that
    a caller cannot relax NFR-501 by editing metrics code -- the gate test
    passes spec's value explicitly.
    """
    if not isinstance(budget_seconds, (int, float)) or isinstance(budget_seconds, bool):
        raise LivePerfError("INVALID_BUDGET", "budget_seconds must be a number")
    if budget_seconds <= 0:
        raise LivePerfError("INVALID_BUDGET", "budget_seconds must be positive")
    failed: list[str] = []
    if report.tail_median_wall > budget_seconds:
        failed.append(VERDICT_BUDGET)
    return (FAIL if failed else PASS, failed)


def export(
    report: PerfReport,
    path: str | pathlib.Path,
    *,
    budget_seconds: float = BUDGET_SECONDS_PER_LOGICAL_SECOND,
) -> pathlib.Path:
    """Write the consumable artifact spec §7 requires before any retreat."""
    status, failed = verdict(report, budget_seconds=budget_seconds)
    payload = {
        **report.to_dict(),
        "budget_seconds_per_logical_second": budget_seconds,
        "verdict": status,
        "failed": failed,
        "evidence_label": "engineering-demonstration",
    }
    out = pathlib.Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    """``python -m market_game_sim.metrics.live_perf --seconds 60``."""
    import argparse

    from market_game_sim.experiment.h2.live_market import DEFAULT_LIVE_ROSTER, LiveMarket
    from market_game_sim.experiment.roster import parse_roster

    parser = argparse.ArgumentParser(prog="market-game live-perf")
    parser.add_argument("--roster", default=None, help="StrategyRoster JSON (default: live roster)")
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--out", default="artifacts/live-perf.json")
    args = parser.parse_args(argv)

    body = (
        json.loads(pathlib.Path(args.roster).read_text(encoding="utf-8"))
        if args.roster
        else DEFAULT_LIVE_ROSTER
    )
    market = LiveMarket(roster=parse_roster(body))
    report = measure(market, logical_seconds=args.seconds, warmup_seconds=args.warmup)
    out = export(report, args.out)
    status, failed = verdict(report)
    print(f"roster={report.roster_id} agents={report.agent_count}")
    print(
        f"tail_median={report.tail_median_wall:.3f}s "
        f"median={report.median_wall:.3f}s max={report.max_wall:.3f}s"
    )
    print(f"trade/order={report.trade_per_order:.5f} records={report.total_records}")
    for et in MIX_EVENT_TYPES:
        print(f"  {et:18s} {report.mix.get(et, 0):8d}  {100 * report.share(et):5.1f}%")
    print(f"verdict={status} failed={failed} -> {out}")
    return 0 if status == PASS else 1


__all__ = [
    "BUDGET_SECONDS_PER_LOGICAL_SECOND",
    "FAIL",
    "MIX_EVENT_TYPES",
    "PASS",
    "VERDICT_BUDGET",
    "DrivableMarket",
    "LivePerfError",
    "PerfReport",
    "environment",
    "export",
    "main",
    "measure",
    "verdict",
]


if __name__ == "__main__":
    sys.exit(main())
