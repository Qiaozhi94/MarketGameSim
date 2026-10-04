"""0.4.3 T1107 (NFR-701 / SC-704): is the anchor's strength knob wired, and which way?

ADR-016 §4.1 names two ways a strength parameter can be dead: it does not bind
(change it, nothing happens), or it binds but does not move the market along
the dimension it is meant to control.  :mod:`.binding_diagnosis` answers the
first.  This module answers the second for the value-investor family's two
knobs (spec FR-702): ``sensitivity_x1000`` and the family ``count``.

The method is the one 0.4.1 used for every candidate it rejected (报告 §17.2,
§18): run the full measurement window at several levels of one knob, the rest
of the assembly fixed, and look at the price multiple.  The measured quantity
is **M** -- the largest ``|price / v_t - 1|`` over the 300-second segment-end
prices of the whole window.  A stronger anchor must not let M grow:

* ``MONOTONE``      -- M never increases with the knob, and the strongest level
  sits strictly below the weakest (a knob that moves nothing is not a knob);
* ``NOT_MONOTONE``  -- M increases somewhere along the levels;
* ``FLAT``          -- non-increasing, but the extremes are equal.

The levels and the verdict rule were fixed before the first measurement
(0.4.3 实验报告 §1); the verdict is recomputed from the stored levels on load,
so an exported report cannot carry a verdict its own data does not support.

A full-window measurement takes minutes per level, which is why it lives here
as a re-runnable tool with a committed artifact instead of inside the test
suite.  Stdlib only (KR-005).
"""

from __future__ import annotations

import copy
import json
import pathlib
import sys
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from typing import Any

SCHEMA_VERSION = 1

MONOTONE = "MONOTONE"
NOT_MONOTONE = "NOT_MONOTONE"
FLAT = "FLAT"

#: The measurement window of 0.4.1 spec §6 / 0.4.3 SC-704.
FULL_WINDOW_SECONDS = 5700
SEGMENT_SECONDS = 300

#: The pre-registered levels (0.4.3 实验报告 §1).  Each knob is varied with the
#: other one held at its middle value, so the two grids share one point.
SENSITIVITY_LEVELS: tuple[int, ...] = (10, 100, 1000, 10000)
SENSITIVITY_GRID_COUNT = 6
COUNT_LEVELS: tuple[int, ...] = (2, 6, 18)
COUNT_GRID_SENSITIVITY = 1000

#: The value family's agent-level parameters.  Copied from the two signal
#: families of the default roster (``trend_following`` / ``mean_reversion``) so
#: that nothing about the anchor except its two knobs is chosen for the anchor.
VALUE_FAMILY_PARAMS: Mapping[str, int] = {
    "leverage_tier": 5,
    "risk_appetite_x1000": 2000,
    "aggressiveness_bp": 8000,
    "max_order_qty": 10000,
    "ewma_half_life_trades": 5,
}


class AnchorStrengthError(ValueError):
    """Rejected input or report; ``code`` is stable and safe to assert on."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def anchored_roster(
    count: int, sensitivity_x1000: int, base: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """The default live roster plus a value family; ``count=0`` returns the base unchanged."""
    if base is None:
        from market_game_sim.experiment.h2.live_market import DEFAULT_LIVE_ROSTER

        base = DEFAULT_LIVE_ROSTER
    roster = copy.deepcopy(dict(base))
    if count:
        roster["families"] = [
            *roster["families"],
            {
                "family_id": "value_investor",
                "count": count,
                "observe_interval_ns": 1_000_000_000,
                "latency_ns": 1_000_000,
                "params": {**VALUE_FAMILY_PARAMS, "sensitivity_x1000": sensitivity_x1000},
            },
        ]
    return roster


@dataclass(frozen=True)
class LevelResult:
    """One knob setting, run for the whole window."""

    count: int
    sensitivity_x1000: int
    seconds: int
    deviation_max: float
    trades: int
    last_trading_segment_s: int
    segment_prices: tuple[int, ...]

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "segment_prices": list(self.segment_prices)}


def run_level(
    count: int, sensitivity_x1000: int, seconds: int = FULL_WINDOW_SECONDS
) -> LevelResult:
    """Drive one anchored market for ``seconds`` logical seconds and measure M."""
    from market_game_sim.experiment.h2.live_market import LiveMarket
    from market_game_sim.experiment.roster import parse_roster

    if type(seconds) is not int or seconds < SEGMENT_SECONDS:
        raise AnchorStrengthError("INVALID_DURATION", f"seconds must be >= {SEGMENT_SECONDS}")
    roster = anchored_roster(count, sensitivity_x1000)
    reference = int(roster["engine"]["initial_price_ticks"])
    market = LiveMarket(roster=parse_roster(roster))
    seen = trades = 0
    last_price = reference
    prices: list[int] = []
    trades_at: list[int] = []
    for second in range(1, seconds + 1):
        market.advance()
        count_now = market.kernel.committed_record_count
        if count_now > seen:
            for record in market.kernel.committed_records_tail(count_now - seen):
                if record.get("event_type") == "TRADE_SETTLE":
                    trades += 1
                    last_price = int(record["price_ticks"])
            seen = count_now
        if second % SEGMENT_SECONDS == 0:
            prices.append(last_price)
            trades_at.append(trades)
    last_trading = 0
    previous = 0
    for index, total in enumerate(trades_at):
        if total > previous:
            last_trading = (index + 1) * SEGMENT_SECONDS
        previous = total
    return LevelResult(
        count=count,
        sensitivity_x1000=sensitivity_x1000,
        seconds=seconds,
        deviation_max=max(abs(p / reference - 1) for p in prices),
        trades=trades,
        last_trading_segment_s=last_trading,
        segment_prices=tuple(prices),
    )


def monotone_verdict(deviations: Sequence[float]) -> str:
    """Verdict for M along increasing knob levels (stronger anchor -> later)."""
    if len(deviations) < 2:
        raise AnchorStrengthError("TOO_FEW_LEVELS", "a direction needs at least two levels")
    if any(b > a for a, b in zip(deviations, deviations[1:], strict=False)):
        return NOT_MONOTONE
    if not deviations[-1] < deviations[0]:
        return FLAT
    return MONOTONE


@dataclass(frozen=True)
class StrengthReport:
    seconds: int
    baseline: LevelResult
    sensitivity: tuple[LevelResult, ...]
    count: tuple[LevelResult, ...]

    @property
    def sensitivity_verdict(self) -> str:
        return monotone_verdict([r.deviation_max for r in self.sensitivity])

    @property
    def count_verdict(self) -> str:
        return monotone_verdict([r.deviation_max for r in self.count])

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "seconds": self.seconds,
            "segment_seconds": SEGMENT_SECONDS,
            "value_family_params": dict(VALUE_FAMILY_PARAMS),
            "baseline": self.baseline.to_dict(),
            "sensitivity": {
                "count": SENSITIVITY_GRID_COUNT,
                "levels": [r.to_dict() for r in self.sensitivity],
                "verdict": self.sensitivity_verdict,
            },
            "count": {
                "sensitivity_x1000": COUNT_GRID_SENSITIVITY,
                "levels": [r.to_dict() for r in self.count],
                "verdict": self.count_verdict,
            },
        }


def _run(args: tuple[int, int, int]) -> LevelResult:
    return run_level(*args)


def measure(
    seconds: int = FULL_WINDOW_SECONDS,
    *,
    sensitivity_levels: Sequence[int] = SENSITIVITY_LEVELS,
    count_levels: Sequence[int] = COUNT_LEVELS,
    jobs: int = 1,
) -> StrengthReport:
    """Run the baseline and both grids; shared points are run once."""
    points = {(0, 0)}
    points |= {(SENSITIVITY_GRID_COUNT, s) for s in sensitivity_levels}
    points |= {(c, COUNT_GRID_SENSITIVITY) for c in count_levels}
    ordered = sorted(points)
    work = [(c, s, seconds) for c, s in ordered]
    if jobs > 1:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            results = list(pool.map(_run, work))
    else:
        results = [_run(w) for w in work]
    by_point = dict(zip(ordered, results, strict=True))
    return StrengthReport(
        seconds=seconds,
        baseline=by_point[(0, 0)],
        sensitivity=tuple(by_point[(SENSITIVITY_GRID_COUNT, s)] for s in sensitivity_levels),
        count=tuple(by_point[(c, COUNT_GRID_SENSITIVITY)] for c in count_levels),
    )


def export(report: StrengthReport, path: str | pathlib.Path) -> pathlib.Path:
    out = pathlib.Path(path)
    out.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    return out


def load_report(path: str | pathlib.Path) -> dict[str, Any]:
    """Load an exported report and refuse one whose verdicts its own levels do not support."""
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise AnchorStrengthError("SCHEMA_VERSION_UNSUPPORTED", repr(data.get("schema_version")))
    for knob in ("sensitivity", "count"):
        levels = data[knob]["levels"]
        recomputed = monotone_verdict([level["deviation_max"] for level in levels])
        if recomputed != data[knob]["verdict"]:
            raise AnchorStrengthError(
                "VERDICT_MISMATCH",
                f"{knob}: stored {data[knob]['verdict']!r}, levels say {recomputed!r}",
            )
    return data


def main(argv: list[str] | None = None) -> int:
    """``python -m market_game_sim.metrics.anchor_strength --out report.json``."""
    import argparse

    parser = argparse.ArgumentParser(prog="market-game anchor-strength")
    parser.add_argument("--seconds", type=int, default=FULL_WINDOW_SECONDS)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    report = measure(args.seconds, jobs=args.jobs)
    export(report, args.out)
    print(
        f"sensitivity: {report.sensitivity_verdict}  count: {report.count_verdict}  -> {args.out}"
    )
    return 0 if MONOTONE == report.sensitivity_verdict == report.count_verdict else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
