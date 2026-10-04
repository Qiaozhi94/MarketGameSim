"""0.4.3 T1109 (SC-704 / AC-708): the strength scan reads only its pre-registration.

T1107 found a cliff: ``sensitivity_x1000 <= 100`` lets the price run away,
``>= 1000`` pins it within 0.6%.  Whether a region exists where the market is
neither pinned nor diverging is what T1111 scans for -- and a scan whose grid
or criteria can move after the first result is a way of finding whatever one
was looking for (0.4.1 报告 §12, §15.4).  So:

* the grid, the seeds, the screening criteria and the qualification rule live
  in **one file**, ``docs/experiments/0.4.3-scan-preregistration.json``,
  committed before any scan run;
* the scan entry reads nothing else, records the file's sha256 when it starts,
  and :func:`verify_preregistration` fails closed if the file is missing or
  no longer hashes to what the scan recorded;
* the test suite pins that sha256 as well, so editing the file after the fact
  is a red build, not a quiet change.

:func:`screen` implements the two screening criteria of spec SC-704 with the
segment convention written there.  Stdlib only (KR-005).
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from collections.abc import Mapping, Sequence
from typing import Any

from market_game_sim.metrics.anchor_diagnostics import down_segments

SCHEMA_VERSION = 1
PREREGISTRATION_PATH = pathlib.Path("docs/experiments/0.4.3-scan-preregistration.json")

PASS = "PASS"
FAIL = "FAIL"

_REQUIRED_KEYS = frozenset(
    {
        "schema_version",
        "milestone",
        "registered_at",
        "decided_by",
        "base_roster_id",
        "value_family_params",
        "response_function",
        "window_seconds",
        "segment_seconds",
        "grid",
        "screening",
        "full_measurement",
        "qualification",
    }
)


class ScanPreregistrationError(ValueError):
    """Missing, malformed or altered pre-registration; ``code`` is stable."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def file_sha256(path: str | pathlib.Path) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def load_preregistration(path: str | pathlib.Path = PREREGISTRATION_PATH) -> dict[str, Any]:
    """Parse and validate the pre-registration; the scan's only source of parameters."""
    target = pathlib.Path(path)
    if not target.is_file():
        raise ScanPreregistrationError(
            "PREREGISTRATION_MISSING", f"{target.as_posix()} does not exist"
        )
    data = json.loads(target.read_text(encoding="utf-8"))
    missing = sorted(_REQUIRED_KEYS - set(data))
    if missing:
        raise ScanPreregistrationError("PREREGISTRATION_INVALID", f"missing keys {missing}")
    if data["schema_version"] != SCHEMA_VERSION:
        raise ScanPreregistrationError(
            "PREREGISTRATION_INVALID", f"schema_version {data['schema_version']!r}"
        )
    grid = data["grid"]
    points = [(int(p["count"]), int(p["sensitivity_x1000"])) for p in grid["points"]]
    expected = [(c, s) for c in grid["count"] for s in grid["sensitivity_x1000"]]
    if sorted(points) != sorted(expected) or len(set(points)) != len(points):
        raise ScanPreregistrationError(
            "PREREGISTRATION_INVALID", "grid.points must be exactly count × sensitivity_x1000"
        )
    if data["window_seconds"] % data["segment_seconds"]:
        raise ScanPreregistrationError(
            "PREREGISTRATION_INVALID", "window must be a whole number of segments"
        )
    return data


def begin_scan(path: str | pathlib.Path = PREREGISTRATION_PATH) -> dict[str, Any]:
    """What a scan records before its first run: the parameters and the file's hash."""
    data = load_preregistration(path)
    return {"preregistration_sha256": file_sha256(path), "preregistration": data}


def verify_preregistration(
    recorded_sha256: str, path: str | pathlib.Path = PREREGISTRATION_PATH
) -> dict[str, Any]:
    """Fail closed unless the file still hashes to what the scan recorded."""
    data = load_preregistration(path)
    actual = file_sha256(path)
    if actual != recorded_sha256:
        raise ScanPreregistrationError(
            "PREREGISTRATION_TAMPERED",
            f"recorded {recorded_sha256}, file now {actual}: the grid or criteria changed "
            "after the scan started",
        )
    return data


def screen(
    reference_ticks: int,
    segment_prices: Sequence[int],
    criteria: Mapping[str, Any],
) -> dict[str, Any]:
    """Spec SC-704's two screening criteria on one run's segment-end prices.

    ① every segment-end price below ``price_multiple_max × v_t`` (upper bound only,
    as registered); ② the share of down segments at least
    ``down_segment_ratio_min`` -- a segment is "down" when it ends below where it
    started, the first segment starting at ``v_t``.  A segment without trades
    carries the previous price, so it counts in the denominator and never as down.
    """
    if len(segment_prices) < 2:
        raise ScanPreregistrationError("INVALID_SERIES", "need at least two segments")
    ratio = criteria["down_segment_ratio_min"]
    numerator, denominator = int(ratio[0]), int(ratio[1])
    bound = float(criteria["price_multiple_max"]) * reference_ticks
    downs = down_segments(reference_ticks, segment_prices)
    segments = len(segment_prices)
    upper = PASS if all(p < bound for p in segment_prices) else FAIL
    # downs / segments >= numerator / denominator, in integers.
    two_way = PASS if downs * denominator >= numerator * segments else FAIL
    return {
        "price_multiple_below_max": upper,
        "down_segments": downs,
        "segments": segments,
        "down_segment_ratio": two_way,
        "passes_screening": PASS if upper == two_way == PASS else FAIL,
    }


def qualifies(per_seed: Mapping[int, Mapping[str, bool]], seeds: Sequence[int]) -> bool:
    """The registered rule: every full-measurement seed passes SC-501 *and* SC-502."""
    missing = [s for s in seeds if s not in per_seed]
    if missing:
        raise ScanPreregistrationError("INCOMPLETE_MEASUREMENT", f"seeds {missing} not measured")
    return all(per_seed[s]["sc_501"] and per_seed[s]["sc_502"] for s in seeds)


# --------------------------------------------------------------------------- #
# T1111: the scan itself
# --------------------------------------------------------------------------- #

QUALIFIED = "QUALIFIED"
UNQUALIFIED = "UNQUALIFIED"
SCAN_REPORT_PATH = pathlib.Path("docs/experiments/0.4.3-scan-report.json")
SCAN_SCHEMA_VERSION = 1


def config_roster(prereg: Mapping[str, Any], count: int, sensitivity_x1000: int, seed: int):
    """The roster of one grid point at one seed, built only from registered values."""
    from market_game_sim.experiment.roster import parse_roster
    from market_game_sim.metrics.anchor_strength import anchored_roster

    roster = anchored_roster(count, sensitivity_x1000)
    roster["families"][-1]["params"] = {
        **prereg["value_family_params"],
        "sensitivity_x1000": sensitivity_x1000,
    }
    roster["seed"] = seed
    if (
        parse_roster({**roster, "seed": 7, "families": roster["families"][:-1]}).roster_id
        != (prereg["base_roster_id"])
    ):
        raise ScanPreregistrationError(
            "BASE_ROSTER_DRIFT", "the default roster no longer matches the registered base"
        )
    return roster


def measure_point(args: tuple[dict[str, Any], int, int, int]) -> dict[str, Any]:
    """Full-window quality run of one (count, sensitivity, seed); diagnostics on top."""
    from market_game_sim.metrics.anchor_diagnostics import config_report
    from market_game_sim.metrics.quality_run import run_market_quality

    prereg, count, sensitivity_x1000, seed = args
    roster = config_roster(prereg, count, sensitivity_x1000, seed)
    report, diagnostics = run_market_quality(
        roster=roster,
        logical_seconds=int(prereg["window_seconds"]),
        segment_seconds=int(prereg["segment_seconds"]),
    )
    reference = int(roster["engine"]["initial_price_ticks"])
    built = config_report(reference, report, diagnostics)
    built["segment_prices"] = list(diagnostics["segment_prices"])
    built["reference_ticks"] = reference
    built["takers_by_family"] = dict(diagnostics["takers_by_family"])
    return {"count": count, "sensitivity_x1000": sensitivity_x1000, "seed": seed, **built}


def _cache_path(cache_dir: pathlib.Path, sha: str, count: int, sens: int, seed: int):
    return cache_dir / sha[:16] / f"c{count}-s{sens}-seed{seed}.json"


def _measure_all(
    prereg: Mapping[str, Any],
    sha: str,
    points: Sequence[tuple[int, int, int]],
    cache_dir: pathlib.Path,
    jobs: int,
) -> dict[tuple[int, int, int], dict[str, Any]]:
    """Measure every point, reusing finished ones from the cache (resumable)."""
    from concurrent.futures import ProcessPoolExecutor, as_completed

    results: dict[tuple[int, int, int], dict[str, Any]] = {}
    todo = []
    for point in points:
        cached = _cache_path(cache_dir, sha, *point)
        if cached.is_file():
            results[point] = json.loads(cached.read_text(encoding="utf-8"))
        else:
            todo.append(point)
    if todo:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            futures = {pool.submit(measure_point, (dict(prereg), *point)): point for point in todo}
            for future in as_completed(futures):
                point = futures[future]
                result = future.result()
                cached = _cache_path(cache_dir, sha, *point)
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
                results[point] = result
                print(
                    f"done c={point[0]} s={point[1]} seed={point[2]} "
                    f"501={result['sc_501']} 502={result['sc_502']}",
                    flush=True,
                )
    return results


def terminal(configs: Sequence[Mapping[str, Any]], complete: bool) -> str | None:
    """QUALIFIED / UNQUALIFIED once the grid is exhausted; ``None`` while it is not."""
    if not complete:
        return None
    return QUALIFIED if any(c["qualifies"] for c in configs) else UNQUALIFIED


def assemble(
    prereg: Mapping[str, Any], sha: str, results: Mapping[tuple[int, int, int], Mapping]
) -> dict[str, Any]:
    """Screen, qualify and conclude from measured points -- pure, no runs."""
    screen_seed = prereg["screening"]["seeds"][0]
    full_seeds = list(prereg["full_measurement"]["seeds"])
    criteria = prereg["screening"]["criteria"]
    configs = []
    complete = True
    for point in prereg["grid"]["points"]:
        count, sens = int(point["count"]), int(point["sensitivity_x1000"])
        first = results.get((count, sens, screen_seed))
        if first is None:
            complete = False
            continue
        screening = screen(first["reference_ticks"], first["segment_prices"], criteria)
        entry: dict[str, Any] = {
            "count": count,
            "sensitivity_x1000": sens,
            "anchor_diagnostics": first["anchor_diagnostics"],
            "screening": screening,
            "seeds": {screen_seed: first},
            "qualifies": False,
        }
        if screening["passes_screening"] == PASS:
            per_seed = {}
            for seed in full_seeds:
                measured = results.get((count, sens, seed))
                if measured is None:
                    complete = False
                    continue
                entry["seeds"][seed] = measured
                per_seed[seed] = {
                    "sc_501": measured["sc_501"] == PASS,
                    "sc_502": measured["sc_502"] == PASS,
                }
            if len(per_seed) == len(full_seeds):
                entry["qualifies"] = qualifies(per_seed, full_seeds)
        configs.append(entry)
    return {
        "schema_version": SCAN_SCHEMA_VERSION,
        "evidence_class": "engineering-demonstration",
        "gate": "H2-E5",
        "preregistration_sha256": sha,
        "complete": complete,
        "terminal": terminal(configs, complete),
        "qualified_configs": [
            {"count": c["count"], "sensitivity_x1000": c["sensitivity_x1000"]}
            for c in configs
            if c["qualifies"]
        ],
        "configs": configs,
    }


def run_scan(
    path: str | pathlib.Path = PREREGISTRATION_PATH,
    *,
    cache_dir: str | pathlib.Path = "artifacts/0.4.3-scan",
    jobs: int = 2,
) -> dict[str, Any]:
    """Screen the registered grid at the screening seed, then measure survivors at every seed."""
    started = begin_scan(path)
    sha = started["preregistration_sha256"]
    prereg = started["preregistration"]
    cache = pathlib.Path(cache_dir)
    screen_seed = prereg["screening"]["seeds"][0]
    grid = [(int(p["count"]), int(p["sensitivity_x1000"])) for p in prereg["grid"]["points"]]
    results = _measure_all(prereg, sha, [(c, s, screen_seed) for c, s in grid], cache, jobs)
    survivors = [
        (c, s)
        for c, s in grid
        if screen(
            results[(c, s, screen_seed)]["reference_ticks"],
            results[(c, s, screen_seed)]["segment_prices"],
            prereg["screening"]["criteria"],
        )["passes_screening"]
        == PASS
    ]
    extra = [
        (c, s, seed)
        for c, s in survivors
        for seed in prereg["full_measurement"]["seeds"]
        if seed != screen_seed
    ]
    results |= _measure_all(prereg, sha, extra, cache, jobs)
    verify_preregistration(sha, path)  # the file must not have moved under the scan
    return assemble(prereg, sha, results)


def load_scan_report(
    path: str | pathlib.Path = SCAN_REPORT_PATH,
    preregistration: str | pathlib.Path = PREREGISTRATION_PATH,
) -> dict[str, Any]:
    """Load the scan report; refuse one tied to another pre-registration or whose
    screening, qualification or terminal its own measurements do not support."""
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != SCAN_SCHEMA_VERSION:
        raise ScanPreregistrationError("SCAN_SCHEMA", repr(data.get("schema_version")))
    prereg = verify_preregistration(data["preregistration_sha256"], preregistration)
    results = {}
    for config in data["configs"]:
        for seed, measured in config["seeds"].items():
            results[(config["count"], config["sensitivity_x1000"], int(seed))] = measured
    rebuilt = assemble(prereg, data["preregistration_sha256"], results)
    for key in ("complete", "terminal", "qualified_configs"):
        if rebuilt[key] != data[key]:
            raise ScanPreregistrationError(
                "SCAN_VERDICT_MISMATCH", f"{key}: stored {data[key]!r}, rebuilt {rebuilt[key]!r}"
            )
    for stored, again in zip(data["configs"], rebuilt["configs"], strict=True):
        if stored["screening"] != again["screening"] or stored["qualifies"] != again["qualifies"]:
            raise ScanPreregistrationError(
                "SCAN_VERDICT_MISMATCH",
                f"c={stored['count']} s={stored['sensitivity_x1000']}: screening/qualification",
            )
    return data


def main(argv: list[str] | None = None) -> int:
    """``python -m market_game_sim.metrics.anchor_scan --jobs 2``."""
    import argparse

    parser = argparse.ArgumentParser(prog="market-game anchor-scan")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--cache-dir", default="artifacts/0.4.3-scan")
    parser.add_argument("--out", default=SCAN_REPORT_PATH.as_posix())
    args = parser.parse_args(argv)
    report = run_scan(cache_dir=args.cache_dir, jobs=args.jobs)
    pathlib.Path(args.out).write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"H2-E5 terminal={report['terminal']} qualified={report['qualified_configs']}")
    return 0


__all__ = [
    "FAIL",
    "PASS",
    "QUALIFIED",
    "UNQUALIFIED",
    "assemble",
    "config_roster",
    "load_scan_report",
    "measure_point",
    "run_scan",
    "terminal",
    "PREREGISTRATION_PATH",
    "ScanPreregistrationError",
    "begin_scan",
    "file_sha256",
    "load_preregistration",
    "qualifies",
    "screen",
    "verify_preregistration",
]


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.exit(main())
