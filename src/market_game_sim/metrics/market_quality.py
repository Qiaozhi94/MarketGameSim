"""0.4.1 T961 (FR-505 / DR-502 / AC-504 / AC-505): ``MarketQualityReport``.

This module freezes *how* a pure AI market run is judged, not how its raw
statistics are measured:

* the six market-quality items of spec §6 SC-501 and their thresholds;
* the five stylized facts of spec §6 SC-502, their family-wise correction and
  the ``>= 3`` pass count;
* the report schema, its derived fields and the machine validator.

Thresholds are copied from spec §6, which is their only owner; a report that
carries any other threshold block is rejected, so a threshold can only move by
editing spec §6 *and* this table in a reviewed commit.

Stylized facts 1–3 are measured by the frozen 0.1.2 protocol implementation
(``metrics/validation.py``); facts 4–5 are added by T971.  Callers hand in each
fact's *raw* result (verdict before family correction, p value, statistic);
this module applies **its own** family-A instance {1, 3, 4, 5} with
``holm_bonferroni`` -- never ``validation._FAMILY_A``, whose members belong to
KPI-005 and must not change (spec SC-502).

Derives-don't-store: ``thresholds``, ``verdicts``, ``failed`` and
``content_hash`` are re-derived on load and must match what the file records,
so a hand-edited verdict or a silently dropped failure is rejected with a
stable :class:`MarketQualityError` code.

Statistics window (spec Q-501): it starts when the *last* agent leaves the
cold start.  A run that ends with an agent still in cold start has no window
(``window_start_logical_ns = None``): every verdict is ``NOT_APPLICABLE`` and
``window`` heads ``failed`` -- the window is never truncated to make a report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from market_game_sim.experiment.stats import holm_bonferroni

SCHEMA_VERSION = 1

PASS = "PASS"
FAIL = "FAIL"
NOT_APPLICABLE = "NOT_APPLICABLE"
VERDICTS = frozenset({PASS, FAIL, NOT_APPLICABLE})

# --------------------------------------------------------------------------- #
# Frozen thresholds (owner: spec §6 SC-501 / SC-502)
# --------------------------------------------------------------------------- #

MIN = "min"  # measured >= threshold passes
MAX = "max"  # measured <= threshold passes

# SC-501 six items: id -> (direction, threshold).  Order is report order.
QUALITY_THRESHOLDS: Mapping[str, tuple[str, float]] = MappingProxyType(
    {
        "trades_per_minute": (MIN, 30.0),
        "two_sided_book_uptime": (MIN, 0.99),
        "median_book_levels_per_side": (MIN, 5.0),
        "median_effective_spread_bp": (MAX, 20.0),
        "fill_to_order_ratio": (MIN, 0.001),
        "wall_seconds_per_logical_second": (MAX, 0.5),
    }
)

# SC-502 five facts, in the spec table's order (#1..#5).
FAT_TAILS = "fat_tails"
RETURN_AUTOCORRELATION = "return_autocorrelation"
VOLATILITY_CLUSTERING = "volatility_clustering"
VOLUME_VOLATILITY_CORRELATION = "volume_volatility_correlation"
ORDER_FLOW_LONG_MEMORY = "order_flow_long_memory"
STYLIZED_FACTS = (
    FAT_TAILS,
    RETURN_AUTOCORRELATION,
    VOLATILITY_CLUSTERING,
    VOLUME_VOLATILITY_CORRELATION,
    ORDER_FLOW_LONG_MEMORY,
)
# This milestone's own group-A family ("reject H0 => pass").  Same size as
# KPI-005's _FAMILY_A but a different set; the two corrected p values are not
# comparable (spec SC-502).  Fact 2 stays group B, corrected inside its lags.
STYLIZED_FAMILY_A = (
    FAT_TAILS,
    VOLATILITY_CLUSTERING,
    VOLUME_VOLATILITY_CORRELATION,
    ORDER_FLOW_LONG_MEMORY,
)
ALPHA = 0.05  # 0.1.2 协议 §2
STYLIZED_MIN_PASS = 3  # SC-502 / Q-504: not adjustable
VOLATILITY_CLUSTERING_LAGS = (1, 50)  # Q-505: both must be significant
ORDER_FLOW_MAX_LAG = 100  # SC-502 #5
VOLUME_VOLATILITY_WINDOW = 30  # SC-502 #4, MD-002
WINDOW_RULE = "after_last_agent_bootstrap_exit"  # Q-501

SC_501 = "sc_501_all_quality"
SC_502 = "sc_502_min_stylized"
WINDOW = "window"


def frozen_thresholds() -> dict[str, Any]:
    """The only threshold block a valid report may carry."""
    return {
        "quality": {k: {"direction": d, "value": v} for k, (d, v) in QUALITY_THRESHOLDS.items()},
        "stylized_facts": {
            "alpha": ALPHA,
            "family_a": list(STYLIZED_FAMILY_A),
            "min_pass": STYLIZED_MIN_PASS,
            "volatility_clustering_lags": list(VOLATILITY_CLUSTERING_LAGS),
            "volume_volatility_window": VOLUME_VOLATILITY_WINDOW,
            "order_flow_max_lag": ORDER_FLOW_MAX_LAG,
        },
        "window_rule": WINDOW_RULE,
    }


class MarketQualityError(ValueError):
    """Report rejected; ``code`` is stable and safe to assert on."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


# --------------------------------------------------------------------------- #
# Stylized fact inputs
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class StylizedFactResult:
    """One fact's result *before* this milestone's family-A correction.

    ``raw_verdict`` for fact 2 is already group-B corrected (0.1.2 协议 §3.2).
    ``evidence`` is free-form audit detail and is hashed but not interpreted.
    """

    raw_verdict: str
    statistic: float | None
    p_value: float | None
    # default_factory: Python 3.11 拒绝把 mappingproxy 当 dataclass 默认值
    # （3.13+ 接受），CI 的 pytest 3.11 job 会在导入期就红。
    evidence: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


def combine_volatility_clustering(
    acf_lag1: float | None,
    p_lag1: float | None,
    acf_lag50: float | None,
    p_lag50: float | None,
) -> StylizedFactResult:
    """Q-505 intersection-union rule for fact 3.

    Passes only if ``|r|`` ACF is significantly positive at **both** lag 1 and
    lag 50; the p value entering family A is ``max(p_lag1, p_lag50)``.  A
    missing lag (sample too short) makes the fact ``NOT_APPLICABLE``.
    """
    evidence = {"acf_lag1": acf_lag1, "p_lag1": p_lag1, "acf_lag50": acf_lag50, "p_lag50": p_lag50}
    if None in (acf_lag1, p_lag1, acf_lag50, p_lag50):
        return StylizedFactResult(NOT_APPLICABLE, None, None, MappingProxyType(evidence))
    p = max(p_lag1, p_lag50)
    positive = acf_lag1 > 0 and acf_lag50 > 0
    verdict = PASS if positive and p < ALPHA else FAIL
    return StylizedFactResult(verdict, min(acf_lag1, acf_lag50), p, MappingProxyType(evidence))


# --------------------------------------------------------------------------- #
# Verdict derivation
# --------------------------------------------------------------------------- #


def _quality_verdict(item: str, measured: float | None) -> str:
    if measured is None:
        return NOT_APPLICABLE
    direction, threshold = QUALITY_THRESHOLDS[item]
    ok = measured >= threshold if direction == MIN else measured <= threshold
    return PASS if ok else FAIL


def _stylized_verdicts(facts: Mapping[str, StylizedFactResult]) -> dict[str, str]:
    out = {name: facts[name].raw_verdict for name in STYLIZED_FACTS}
    family_p = {
        name: facts[name].p_value
        for name in STYLIZED_FAMILY_A
        if facts[name].raw_verdict != NOT_APPLICABLE and facts[name].p_value is not None
    }
    corrected = holm_bonferroni(family_p, alpha=ALPHA) if family_p else {}
    for name, significant in corrected.items():
        if out[name] == PASS and not significant:
            out[name] = FAIL
    return out


def _derive(
    window_start: int | None,
    quality: Mapping[str, float | None],
    facts: Mapping[str, StylizedFactResult],
) -> tuple[dict[str, Any], list[str]]:
    if window_start is None:
        verdicts: dict[str, Any] = {
            "quality": {k: NOT_APPLICABLE for k in QUALITY_THRESHOLDS},
            "stylized_facts": {k: NOT_APPLICABLE for k in STYLIZED_FACTS},
            SC_501: NOT_APPLICABLE,
            SC_502: NOT_APPLICABLE,
        }
    else:
        q = {k: _quality_verdict(k, quality[k]) for k in QUALITY_THRESHOLDS}
        s = _stylized_verdicts(facts)
        passed = sum(1 for v in s.values() if v == PASS)
        verdicts = {
            "quality": q,
            "stylized_facts": s,
            SC_501: PASS if all(v == PASS for v in q.values()) else FAIL,
            SC_502: PASS if passed >= STYLIZED_MIN_PASS else FAIL,
        }
    # Everything that did not pass is listed -- NOT_APPLICABLE is not a pass.
    failed = [] if window_start is not None else [WINDOW]
    failed += [s for s in (SC_501, SC_502) if verdicts[s] != PASS]
    failed += [f"quality.{k}" for k, v in verdicts["quality"].items() if v != PASS]
    failed += [f"stylized_facts.{k}" for k, v in verdicts["stylized_facts"].items() if v != PASS]
    return verdicts, failed


# --------------------------------------------------------------------------- #
# Canonical form
# --------------------------------------------------------------------------- #


def _canonical(payload: Any) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _digest(payload: Any) -> str:
    return hashlib.blake2b(_canonical(payload), digest_size=16).hexdigest()


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: _thaw(v) for k, v in value.items()}
    if isinstance(value, tuple | list):
        return [_thaw(v) for v in value]
    return value


TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "run_id",
        "roster_id",
        "logical_seconds",
        "window_start_logical_ns",
        "quality",
        "stylized_facts",
    }
)
DERIVED_KEYS = frozenset({"thresholds", "verdicts", "failed", "content_hash"})
FACT_KEYS = frozenset({"raw_verdict", "statistic", "p_value", "evidence"})


@dataclass(frozen=True)
class MarketQualityReport:
    run_id: str
    roster_id: str
    logical_seconds: float
    window_start_logical_ns: int | None
    quality: Mapping[str, float | None]
    stylized_facts: Mapping[str, StylizedFactResult]

    @property
    def thresholds(self) -> dict[str, Any]:
        return frozen_thresholds()

    @property
    def verdicts(self) -> dict[str, Any]:
        return _derive(self.window_start_logical_ns, self.quality, self.stylized_facts)[0]

    @property
    def failed(self) -> list[str]:
        return _derive(self.window_start_logical_ns, self.quality, self.stylized_facts)[1]

    def _hashed_body(self) -> dict[str, Any]:
        verdicts, failed = _derive(self.window_start_logical_ns, self.quality, self.stylized_facts)
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "roster_id": self.roster_id,
            "logical_seconds": self.logical_seconds,
            "window_start_logical_ns": self.window_start_logical_ns,
            "quality": {k: self.quality[k] for k in QUALITY_THRESHOLDS},
            "stylized_facts": {
                k: {
                    "raw_verdict": f.raw_verdict,
                    "statistic": f.statistic,
                    "p_value": f.p_value,
                    "evidence": _thaw(f.evidence),
                }
                for k, f in ((k, self.stylized_facts[k]) for k in STYLIZED_FACTS)
            },
            "thresholds": frozen_thresholds(),
            "verdicts": verdicts,
            "failed": failed,
        }

    @property
    def content_hash(self) -> str:
        return _digest(self._hashed_body())

    def to_dict(self) -> dict[str, Any]:
        body = self._hashed_body()
        body["content_hash"] = _digest(body)
        return body

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=2, ensure_ascii=False) + "\n"


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #


def _require_keys(obj: Any, allowed: frozenset[str], where: str) -> None:
    if not isinstance(obj, Mapping):
        raise MarketQualityError("INVALID_VALUE", f"{where} must be an object")
    unknown = sorted(set(obj) - allowed)
    if unknown:
        raise MarketQualityError("UNKNOWN_FIELD", f"{where} has unknown fields {unknown}")
    missing = sorted(allowed - set(obj))
    if missing:
        raise MarketQualityError("MISSING_FIELD", f"{where} is missing {missing}")


def _number(value: Any, where: str, *, nullable: bool = True) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise MarketQualityError("INVALID_VALUE", f"{where} must be a finite number, got {value!r}")
    return float(value)


def _str(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise MarketQualityError("INVALID_VALUE", f"{where} must be a non-empty string")
    return value


def _parse_fact(name: str, raw: Any) -> StylizedFactResult:
    where = f"stylized_facts.{name}"
    _require_keys(raw, FACT_KEYS, where)
    verdict = raw["raw_verdict"]
    if verdict not in VERDICTS:
        raise MarketQualityError("INVALID_VALUE", f"{where}.raw_verdict {verdict!r}")
    p = _number(raw["p_value"], f"{where}.p_value")
    if p is not None and not 0.0 <= p <= 1.0:
        raise MarketQualityError("INVALID_VALUE", f"{where}.p_value {p} not in [0, 1]")
    if name in STYLIZED_FAMILY_A and verdict == PASS and p is None:
        raise MarketQualityError("INVALID_VALUE", f"{where}: a family-A PASS needs a p_value")
    if not isinstance(raw["evidence"], Mapping):
        raise MarketQualityError("INVALID_VALUE", f"{where}.evidence must be an object")
    return StylizedFactResult(
        verdict,
        _number(raw["statistic"], f"{where}.statistic"),
        p,
        MappingProxyType(dict(raw["evidence"])),
    )


def build_report(
    *,
    run_id: str,
    roster_id: str,
    logical_seconds: float,
    window_start_logical_ns: int | None,
    quality: Mapping[str, float | None],
    stylized_facts: Mapping[str, StylizedFactResult],
) -> MarketQualityReport:
    """Build a report from measured values; verdicts are always derived."""
    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "roster_id": roster_id,
        "logical_seconds": logical_seconds,
        "window_start_logical_ns": window_start_logical_ns,
        "quality": dict(quality),
        "stylized_facts": {
            k: {
                "raw_verdict": f.raw_verdict,
                "statistic": f.statistic,
                "p_value": f.p_value,
                "evidence": _thaw(f.evidence),
            }
            for k, f in stylized_facts.items()
        },
    }
    return _parse_body(payload)


def _parse_body(payload: Mapping[str, Any]) -> MarketQualityReport:
    _require_keys(payload, TOP_LEVEL_KEYS, "report")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise MarketQualityError(
            "UNKNOWN_SCHEMA_VERSION", f"schema_version {payload['schema_version']!r}"
        )
    logical_seconds = _number(payload["logical_seconds"], "logical_seconds", nullable=False)
    if logical_seconds <= 0:
        raise MarketQualityError("INVALID_VALUE", "logical_seconds must be > 0")
    start = payload["window_start_logical_ns"]
    if start is not None and (isinstance(start, bool) or not isinstance(start, int) or start < 0):
        raise MarketQualityError(
            "INVALID_VALUE", f"window_start_logical_ns must be null or an int >= 0, got {start!r}"
        )
    _require_keys(payload["quality"], frozenset(QUALITY_THRESHOLDS), "quality")
    quality = {k: _number(payload["quality"][k], f"quality.{k}") for k in QUALITY_THRESHOLDS}
    _require_keys(payload["stylized_facts"], frozenset(STYLIZED_FACTS), "stylized_facts")
    facts = {k: _parse_fact(k, payload["stylized_facts"][k]) for k in STYLIZED_FACTS}
    return MarketQualityReport(
        run_id=_str(payload["run_id"], "run_id"),
        roster_id=_str(payload["roster_id"], "roster_id"),
        logical_seconds=logical_seconds,
        window_start_logical_ns=start,
        quality=MappingProxyType(quality),
        stylized_facts=MappingProxyType(facts),
    )


def parse_report(payload: Mapping[str, Any]) -> MarketQualityReport:
    """Validate a persisted report: closed keys + every derived field re-derived."""
    if not isinstance(payload, Mapping):
        raise MarketQualityError("INVALID_VALUE", "report must be an object")
    missing = sorted(DERIVED_KEYS - set(payload))
    if missing:
        raise MarketQualityError("MISSING_FIELD", f"report is missing {missing}")
    report = _parse_body({k: v for k, v in payload.items() if k not in DERIVED_KEYS})
    if payload["thresholds"] != frozen_thresholds():
        raise MarketQualityError(
            "THRESHOLD_MISMATCH", "thresholds differ from the frozen spec §6 table"
        )
    verdicts, failed = _derive(
        report.window_start_logical_ns, report.quality, report.stylized_facts
    )
    if payload["verdicts"] != verdicts:
        raise MarketQualityError("VERDICT_MISMATCH", "recorded verdicts differ from derived ones")
    if payload["failed"] != failed:
        raise MarketQualityError(
            "FAILED_MISMATCH", f"recorded failed {payload['failed']!r} != derived {failed!r}"
        )
    if payload["content_hash"] != report.content_hash:
        raise MarketQualityError(
            "HASH_MISMATCH",
            f"recorded {payload['content_hash']!r} != derived {report.content_hash!r}",
        )
    return report


def save_report(report: MarketQualityReport, directory: str | pathlib.Path) -> pathlib.Path:
    """Write ``<directory>/<run_id>.quality.json``."""
    out = pathlib.Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{report.run_id}.quality.json"
    path.write_text(report.to_json(), encoding="utf-8")
    return path


def load_report(path: str | pathlib.Path) -> MarketQualityReport:
    p = pathlib.Path(path)
    if not p.is_file():
        raise MarketQualityError("REPORT_NOT_FOUND", f"{p.as_posix()} does not exist")
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MarketQualityError("INVALID_JSON", f"{p.name}: {exc}") from exc
    return parse_report(payload)


def main(argv: list[str] | None = None) -> int:
    """Machine validator: ``python -m market_game_sim.metrics.market_quality FILE...``.

    Exit 0 only if every file is a valid report; the verdicts themselves
    (pass/fail of the market) do not affect the exit code.
    """
    parser = argparse.ArgumentParser(description="Validate MarketQualityReport files")
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args(argv)
    status = 0
    for path in args.paths:
        try:
            report = load_report(path)
        except MarketQualityError as exc:
            print(f"INVALID {path}: {exc}", file=sys.stderr)
            status = 1
            continue
        print(f"OK {path} failed={report.failed}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
