"""0.4.3 T1108 (US-701 / NFR-702 / AC-707): the anchored market is a runnable carrier.

Outcome gate H2-E4: an assembly that contains the value family, its roster, and
evidence that the market built from it

* stays **bounded** -- every 300-second segment-end price within
  ``[v_t / 1.5, 1.5 * v_t]``;
* moves **both ways** -- at least one segment ends lower than it started and
  at least one ends higher (a monotone ramp is what 0.4.1 died of, a frozen
  price is not a market);
* is **still trading** in the last segment of the window;
* **replays bit for bit** -- two runs of the same roster and seed commit the
  same event stream.

The criteria were fixed before the first measurement (0.4.3 实验报告 §3).  They
say the carrier works; they do **not** say the market is good -- quality is
SC-701/SC-702, judged in T1111 on the pre-registered grid.

A full window takes minutes, so this is a re-runnable tool with a committed
artifact; on load the verdict is recomputed from the stored series.
Stdlib only (KR-005).
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = 1
EVIDENCE_CLASS = "engineering-demonstration"

FULL_WINDOW_SECONDS = 5700
SEGMENT_SECONDS = 300
#: Same bound as SC-704 ①, applied on both sides (US-701: "价格倍数有界").
PRICE_MULTIPLE_BOUND = 1.5

PASS = "PASS"
FAIL = "FAIL"


class AnchoredMarketError(ValueError):
    """Rejected input or artifact; ``code`` is stable and safe to assert on."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class AnchoredRun:
    roster_id: str
    seconds: int
    reference_ticks: int
    segment_prices: tuple[int, ...]
    segment_trades: tuple[int, ...]
    events_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "roster_id": self.roster_id,
            "seconds": self.seconds,
            "reference_ticks": self.reference_ticks,
            "segment_prices": list(self.segment_prices),
            "segment_trades": list(self.segment_trades),
            "events_digest": self.events_digest,
        }


def run(roster: Mapping[str, Any], seconds: int = FULL_WINDOW_SECONDS) -> AnchoredRun:
    """Drive the market ``roster`` assembles and digest every committed record."""
    from market_game_sim.experiment.h2.live_market import LiveMarket
    from market_game_sim.experiment.roster import parse_roster

    if type(seconds) is not int or seconds < SEGMENT_SECONDS or seconds % SEGMENT_SECONDS:
        raise AnchoredMarketError(
            "INVALID_DURATION", f"seconds must be a positive multiple of {SEGMENT_SECONDS}"
        )
    parsed = parse_roster(roster)
    reference = int(parsed.engine["initial_price_ticks"])
    market = LiveMarket(roster=parsed)
    digest = hashlib.blake2b(digest_size=16)
    seen = 0
    last_price = reference
    trades_in_segment = 0
    prices: list[int] = []
    trades: list[int] = []
    for second in range(1, seconds + 1):
        market.advance()
        total = market.kernel.committed_record_count
        if total > seen:
            for record in market.kernel.committed_records_tail(total - seen):
                digest.update(json.dumps(record, sort_keys=True, default=str).encode("utf-8"))
                if record.get("event_type") == "TRADE_SETTLE":
                    trades_in_segment += 1
                    last_price = int(record["price_ticks"])
            seen = total
        if second % SEGMENT_SECONDS == 0:
            prices.append(last_price)
            trades.append(trades_in_segment)
            trades_in_segment = 0
    return AnchoredRun(
        roster_id=parsed.roster_id,
        seconds=seconds,
        reference_ticks=reference,
        segment_prices=tuple(prices),
        segment_trades=tuple(trades),
        events_digest=digest.hexdigest(),
    )


def judge(
    reference_ticks: int,
    segment_prices: Sequence[int],
    segment_trades: Sequence[int],
    digests: Sequence[str],
) -> dict[str, str]:
    """The four AC-707 criteria, each PASS/FAIL, plus the overall verdict."""
    if len(segment_prices) < 2 or len(segment_prices) != len(segment_trades):
        raise AnchoredMarketError("INVALID_SERIES", "need >= 2 aligned segments")
    if len(digests) < 2:
        raise AnchoredMarketError("NO_REPLAY", "reproducibility needs two runs")
    low = reference_ticks / PRICE_MULTIPLE_BOUND
    high = reference_ticks * PRICE_MULTIPLE_BOUND
    path = [reference_ticks, *segment_prices]
    steps = [b - a for a, b in zip(path, path[1:], strict=False)]
    verdicts = {
        "bounded": PASS if all(low <= p <= high for p in segment_prices) else FAIL,
        "two_way": PASS if any(s < 0 for s in steps) and any(s > 0 for s in steps) else FAIL,
        "trading_at_window_end": PASS if segment_trades[-1] > 0 else FAIL,
        "replays_bit_for_bit": PASS if len(set(digests)) == 1 else FAIL,
    }
    verdicts["overall"] = PASS if all(v == PASS for v in verdicts.values()) else FAIL
    return verdicts


def _run(args: tuple[dict[str, Any], int]) -> AnchoredRun:
    return run(*args)


def measure(roster: Mapping[str, Any], seconds: int = FULL_WINDOW_SECONDS) -> dict[str, Any]:
    """Run the roster twice (in parallel) and build the H2-E4 artifact."""
    payload = dict(roster)
    with ProcessPoolExecutor(max_workers=2) as pool:
        first, second = pool.map(_run, [(payload, seconds), (payload, seconds)])
    verdicts = judge(
        first.reference_ticks,
        first.segment_prices,
        first.segment_trades,
        [first.events_digest, second.events_digest],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_class": EVIDENCE_CLASS,
        "gate": "H2-E4",
        "roster_id": first.roster_id,
        "seconds": seconds,
        "segment_seconds": SEGMENT_SECONDS,
        "price_multiple_bound": PRICE_MULTIPLE_BOUND,
        "run": first.to_dict(),
        "replay_events_digest": second.events_digest,
        "verdicts": verdicts,
    }


def load_artifact(path: str | pathlib.Path) -> dict[str, Any]:
    """Load the artifact and refuse verdicts its own series do not support."""
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise AnchoredMarketError("SCHEMA_VERSION_UNSUPPORTED", repr(data.get("schema_version")))
    if data.get("evidence_class") != EVIDENCE_CLASS:
        raise AnchoredMarketError("EVIDENCE_CLASS", repr(data.get("evidence_class")))
    run_data = data["run"]
    recomputed = judge(
        run_data["reference_ticks"],
        run_data["segment_prices"],
        run_data["segment_trades"],
        [run_data["events_digest"], data["replay_events_digest"]],
    )
    if recomputed != data["verdicts"]:
        raise AnchoredMarketError(
            "VERDICT_MISMATCH", f"stored {data['verdicts']!r}, series say {recomputed!r}"
        )
    return data


def main(argv: list[str] | None = None) -> int:
    """``python -m market_game_sim.metrics.anchored_market --roster-file R --out A``."""
    import argparse

    from market_game_sim.experiment.roster import load_roster

    parser = argparse.ArgumentParser(prog="market-game anchored-market")
    parser.add_argument("--roster-file", required=True)
    parser.add_argument("--seconds", type=int, default=FULL_WINDOW_SECONDS)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    roster_path = pathlib.Path(args.roster_file)
    roster = load_roster(roster_path.parent, roster_path.stem)
    artifact = measure(json.loads(roster.to_json()), args.seconds)
    pathlib.Path(args.out).write_text(
        json.dumps(artifact, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(
        f"{artifact['gate']} {artifact['verdicts']['overall']} {artifact['verdicts']} -> {args.out}"
    )
    return 0 if artifact["verdicts"]["overall"] == PASS else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
