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
    path = [reference_ticks, *segment_prices]
    downs = sum(1 for a, b in zip(path, path[1:], strict=False) if b < a)
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


__all__ = [
    "FAIL",
    "PASS",
    "PREREGISTRATION_PATH",
    "ScanPreregistrationError",
    "begin_scan",
    "file_sha256",
    "load_preregistration",
    "qualifies",
    "screen",
    "verify_preregistration",
]
