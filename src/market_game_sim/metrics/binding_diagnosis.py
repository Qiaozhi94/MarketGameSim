"""0.4.1 C-1: which constraint actually binds?  Measure it, do not derive it.

This repository spent a day on the same mistake, five times: compute how much
some constraint is mis-scaled, conclude it drives the dynamics, then discover
the constraint was never reached.  ``max_position_units`` was patched twice --
once for the missing ``MULT``, once for a cash basis -- and both runs came out
**bit-identical** to the unpatched one.  design.md §9.2 records the rule that
came out of it: *"算得出放大系数" ≠ "该约束 binding"；先测 binding，再谈机制.*

This module is that rule, made repeatable.  The method is the one those three
in-memory patches used:

    perturb one constraint, re-run, compare the event stream bit for bit.
    Identical stream ⇒ that constraint was not binding.

Two things it refuses to do, because both would turn the tool into a nicer way
of making the same mistake:

* **It does not accept a silent patch.**  A perturbation that fails to install
  produces a bit-identical stream -- indistinguishable from a constraint that
  does not bind.  Every perturbation therefore carries a ``probe`` that must
  observe the change while it is installed and observe its absence afterwards;
  a probe that disagrees raises :class:`BindingDiagnosisError` instead of
  reporting ``NOT_BINDING``.
* **It does not call an unmoved stream "not binding" on its own.**  If no
  perturbation in the diagnosis moved the stream, the harness may simply be
  blind at this horizon (run too short, market inert), so every verdict
  degrades to ``INCONCLUSIVE``.  ``NOT_BINDING`` is only ever reported next to
  evidence that the same harness *did* detect a difference elsewhere.

A verdict is scoped to the assembly and horizon it was measured on, both of
which the artifact records: a constraint that never binds in 40 logical
seconds may well bind in 4000.

Stdlib only (KR-005).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import pathlib
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

SCHEMA_VERSION = 1

#: The stream moved when this constraint was perturbed: it binds.
BINDING = "BINDING"
#: The stream did not move, and the harness proved it can see movement.
NOT_BINDING = "NOT_BINDING"
#: The stream did not move and nothing else moved either -- no evidence either
#: way.  Never report this as "not binding"; it means the measurement failed.
INCONCLUSIVE = "INCONCLUSIVE"

#: Default horizon.  Long enough that the margin gate is exercised, short
#: enough that a full diagnosis stays in the seconds -- other sessions share
#: this machine.
DEFAULT_LOGICAL_SECONDS = 40
DEFAULT_WARMUP_SECONDS = 2


class BindingDiagnosisError(ValueError):
    """Diagnosis rejected; ``code`` is stable and safe to assert on."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


class DrivableMarket(Protocol):
    """Same contract as ``metrics.live_perf``: advance, and expose a kernel."""

    kernel: Any

    def advance(self) -> None: ...


MarketFactory = Callable[[], DrivableMarket]


# --------------------------------------------------------------------------- #
# Event stream digests
# --------------------------------------------------------------------------- #


def _canonical(record: Mapping[str, Any]) -> bytes:
    return json.dumps(record, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")


def _record_digest(record: Mapping[str, Any]) -> str:
    return hashlib.blake2b(_canonical(record), digest_size=8).hexdigest()


@dataclass(frozen=True)
class EventStream:
    """Per-record digests of one run, plus the digest of the whole stream.

    Per-record digests rather than the records themselves: the comparison has
    to be exact, but it also has to name *where* two runs first parted, and
    holding two full record lists for a long run costs more memory than the
    diagnosis is worth.
    """

    record_digests: tuple[str, ...]
    trade_count: int
    logical_ns: int

    @property
    def record_count(self) -> int:
        return len(self.record_digests)

    @property
    def digest(self) -> str:
        acc = hashlib.blake2b(digest_size=16)
        for item in self.record_digests:
            acc.update(item.encode("ascii"))
        return acc.hexdigest()

    def first_divergence(self, other: EventStream) -> int | None:
        """Index of the first differing record, or ``None`` when identical.

        A run that is a strict prefix of the other diverges at the length of
        the shorter one: fewer records *is* a difference.
        """
        pairs = zip(self.record_digests, other.record_digests, strict=False)
        for index, (mine, theirs) in enumerate(pairs):
            if mine != theirs:
                return index
        if self.record_count != other.record_count:
            return min(self.record_count, other.record_count)
        return None


def drive(
    market: DrivableMarket,
    *,
    logical_seconds: int,
    warmup_seconds: int = 0,
) -> EventStream:
    """Drive a freshly built market and digest every committed record."""
    if type(logical_seconds) is not int or logical_seconds < 1:
        raise BindingDiagnosisError("INVALID_DURATION", "logical_seconds must be an int >= 1")
    if type(warmup_seconds) is not int or warmup_seconds < 0:
        raise BindingDiagnosisError("INVALID_WARMUP", "warmup_seconds must be an int >= 0")

    for _ in range(warmup_seconds + logical_seconds):
        market.advance()

    records = list(market.kernel.committed_records)
    trades = sum(1 for r in records if r.get("event_type") == "TRADE_SETTLE")
    return EventStream(
        record_digests=tuple(_record_digest(r) for r in records),
        trade_count=trades,
        logical_ns=int(getattr(market, "logical_ns", 0) or 0),
    )


# --------------------------------------------------------------------------- #
# Perturbations
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Perturbation:
    """One constraint, one way of loosening it, and a probe that proves it.

    ``install`` yields with the constraint loosened.  ``adjust`` gets a hook
    into each freshly built market for constraints that live in per-agent
    configuration rather than in module state.  ``probe`` reports what the
    constraint currently allows: the diagnosis calls it before, during and
    after ``install`` and refuses to proceed unless the value actually moved
    and then moved back.
    """

    constraint_id: str
    description: str
    install: Callable[[], contextlib.AbstractContextManager[None]]
    probe: Callable[[], Any]
    adjust: Callable[[Any], None] = lambda market: None
    factor: float | None = None

    def verify_installed(self) -> tuple[Any, Any]:
        """Return ``(before, during)`` probe values, raising if nothing moved."""
        before = self.probe()
        with self.install():
            during = self.probe()
            if during == before:
                raise BindingDiagnosisError(
                    "PERTURBATION_INERT",
                    f"{self.constraint_id}: probe unchanged while installed "
                    f"({before!r}) -- the patch did not take, and a patch that "
                    "did not take looks exactly like a constraint that does "
                    "not bind",
                )
        after = self.probe()
        if after != before:
            raise BindingDiagnosisError(
                "PERTURBATION_LEAKED",
                f"{self.constraint_id}: probe still {after!r} after the patch "
                f"was removed (was {before!r}) -- process state is dirty",
            )
        return before, during


@dataclass(frozen=True)
class ConstraintVerdict:
    constraint_id: str
    description: str
    factor: float | None
    verdict: str
    record_count: int
    trade_count: int
    stream_digest: str
    first_divergence: int | None
    probe_before: str
    probe_during: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "constraint_id": self.constraint_id,
            "description": self.description,
            "factor": self.factor,
            "verdict": self.verdict,
            "record_count": self.record_count,
            "trade_count": self.trade_count,
            "stream_digest": self.stream_digest,
            "first_divergence": self.first_divergence,
            "probe_before": self.probe_before,
            "probe_during": self.probe_during,
        }


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DiagnosisReport:
    roster_id: str | None
    agent_count: int
    logical_seconds: int
    warmup_seconds: int
    baseline_record_count: int
    baseline_trade_count: int
    baseline_digest: str
    verdicts: tuple[ConstraintVerdict, ...] = field(default_factory=tuple)

    @property
    def binding(self) -> list[str]:
        return [v.constraint_id for v in self.verdicts if v.verdict == BINDING]

    @property
    def not_binding(self) -> list[str]:
        return [v.constraint_id for v in self.verdicts if v.verdict == NOT_BINDING]

    @property
    def inconclusive(self) -> list[str]:
        return [v.constraint_id for v in self.verdicts if v.verdict == INCONCLUSIVE]

    def _hashed_body(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "roster_id": self.roster_id,
            "agent_count": self.agent_count,
            "logical_seconds": self.logical_seconds,
            "warmup_seconds": self.warmup_seconds,
            "baseline_record_count": self.baseline_record_count,
            "baseline_trade_count": self.baseline_trade_count,
            "baseline_digest": self.baseline_digest,
            "verdicts": [v.to_dict() for v in self.verdicts],
        }

    @property
    def content_hash(self) -> str:
        return hashlib.blake2b(
            json.dumps(self._hashed_body(), sort_keys=True, ensure_ascii=False).encode("utf-8"),
            digest_size=16,
        ).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        body = self._hashed_body()
        body["binding"] = self.binding
        body["not_binding"] = self.not_binding
        body["inconclusive"] = self.inconclusive
        body["content_hash"] = self.content_hash
        body["evidence_label"] = "engineering-demonstration"
        return body


TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "roster_id",
        "agent_count",
        "logical_seconds",
        "warmup_seconds",
        "baseline_record_count",
        "baseline_trade_count",
        "baseline_digest",
        "verdicts",
    }
)
DERIVED_KEYS = frozenset(
    {"binding", "not_binding", "inconclusive", "content_hash", "evidence_label"}
)


# --------------------------------------------------------------------------- #
# The diagnosis
# --------------------------------------------------------------------------- #


def diagnose(
    build_market: MarketFactory,
    perturbations: Sequence[Perturbation],
    *,
    logical_seconds: int = DEFAULT_LOGICAL_SECONDS,
    warmup_seconds: int = DEFAULT_WARMUP_SECONDS,
) -> DiagnosisReport:
    """Run the baseline, then each perturbation, and compare streams exactly.

    ``build_market`` must return a *fresh* market each call: comparing two
    horizons of the same market would compare two different points in time,
    not two different constraint settings.
    """
    if not perturbations:
        raise BindingDiagnosisError("NO_PERTURBATIONS", "at least one perturbation is required")
    seen = [p.constraint_id for p in perturbations]
    if len(set(seen)) != len(seen):
        raise BindingDiagnosisError("DUPLICATE_CONSTRAINT", f"constraint ids repeat: {seen}")

    baseline_market = build_market()
    baseline = drive(
        baseline_market, logical_seconds=logical_seconds, warmup_seconds=warmup_seconds
    )

    raw: list[tuple[Perturbation, EventStream, Any, Any]] = []
    for perturbation in perturbations:
        before, during = perturbation.verify_installed()
        with perturbation.install():
            market = build_market()
            perturbation.adjust(market)
            stream = drive(market, logical_seconds=logical_seconds, warmup_seconds=warmup_seconds)
        raw.append((perturbation, stream, before, during))

    # A stream that did not move only means "not binding" if this harness has
    # shown it can move a stream at all at this horizon.
    detector_live = any(stream.first_divergence(baseline) is not None for _, stream, _, _ in raw)

    verdicts: list[ConstraintVerdict] = []
    for perturbation, stream, before, during in raw:
        divergence = stream.first_divergence(baseline)
        if divergence is not None:
            verdict = BINDING
        elif detector_live:
            verdict = NOT_BINDING
        else:
            verdict = INCONCLUSIVE
        verdicts.append(
            ConstraintVerdict(
                constraint_id=perturbation.constraint_id,
                description=perturbation.description,
                factor=perturbation.factor,
                verdict=verdict,
                record_count=stream.record_count,
                trade_count=stream.trade_count,
                stream_digest=stream.digest,
                first_divergence=divergence,
                probe_before=repr(before),
                probe_during=repr(during),
            )
        )

    specs = getattr(baseline_market, "config", None)
    return DiagnosisReport(
        roster_id=getattr(baseline_market, "roster_id", None),
        agent_count=len(getattr(specs, "agent_specs", ()) or ()),
        logical_seconds=logical_seconds,
        warmup_seconds=warmup_seconds,
        baseline_record_count=baseline.record_count,
        baseline_trade_count=baseline.trade_count,
        baseline_digest=baseline.digest,
        verdicts=tuple(verdicts),
    )


def export(report: DiagnosisReport, path: str | pathlib.Path) -> pathlib.Path:
    out = pathlib.Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def load_report(path: str | pathlib.Path) -> dict[str, Any]:
    """Read an artifact back, re-deriving the hash rather than trusting it."""
    payload = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise BindingDiagnosisError("MALFORMED", "artifact must be a JSON object")
    keys = set(payload)
    missing = TOP_LEVEL_KEYS - keys
    if missing:
        raise BindingDiagnosisError("MISSING_KEYS", f"missing {sorted(missing)}")
    unknown = keys - TOP_LEVEL_KEYS - DERIVED_KEYS
    if unknown:
        raise BindingDiagnosisError("UNKNOWN_KEYS", f"unknown {sorted(unknown)}")
    report = DiagnosisReport(
        roster_id=payload["roster_id"],
        agent_count=payload["agent_count"],
        logical_seconds=payload["logical_seconds"],
        warmup_seconds=payload["warmup_seconds"],
        baseline_record_count=payload["baseline_record_count"],
        baseline_trade_count=payload["baseline_trade_count"],
        baseline_digest=payload["baseline_digest"],
        verdicts=tuple(ConstraintVerdict(**v) for v in payload["verdicts"]),
    )
    if payload.get("content_hash") != report.content_hash:
        raise BindingDiagnosisError(
            "CONTENT_HASH_MISMATCH",
            f"recorded {payload.get('content_hash')!r} != derived {report.content_hash!r}",
        )
    return payload


# --------------------------------------------------------------------------- #
# The three candidates 0.4.1 actually argued about
# --------------------------------------------------------------------------- #


@contextlib.contextmanager
def _patched_attrs(targets: Sequence[tuple[Any, str, Any]]) -> Iterator[None]:
    """Set ``module.name = value`` for each target, restoring on exit."""
    saved = [(obj, name, getattr(obj, name)) for obj, name, _ in targets]
    try:
        for obj, name, value in targets:
            setattr(obj, name, value)
        yield
    finally:
        for obj, name, original in saved:
            setattr(obj, name, original)


def _family_modules() -> dict[str, Any]:
    """Every module that bound ``max_position_units`` at import time.

    The families do ``from ._common import max_position_units``, so patching
    ``_common`` alone would leave the families on the original function -- an
    inert patch, which is precisely what ``verify_installed`` exists to catch.
    """
    from market_game_sim.agent.strategy_layer.families import (
        mean_reversion,
        sentiment_noise,
        trend_following,
    )

    return {
        "trend_following": trend_following,
        "mean_reversion": mean_reversion,
        "sentiment_noise": sentiment_noise,
    }


def family_position_ceiling_perturbation(
    family_id: str | None = None, factor: int = 1000
) -> Perturbation:
    """Scale the family-level position ceiling (``max_position_units``).

    ``factor=1000`` reproduces the "missing MULT" correction that was patched
    in twice during 0.4.1 and came out bit-identical both times.

    ``family_id=None`` patches every family at once, which is how that
    correction was originally tried -- and why it is not the default here.  On
    the current assembly the aggregate answer is ``BINDING``, but it binds for
    exactly one family out of three (``sentiment_noise``); lumping the three
    together reports a true verdict that hides the only interesting part of it.
    """
    modules = _family_modules()
    if family_id is not None and family_id not in modules:
        raise BindingDiagnosisError("UNKNOWN_FAMILY", f"{family_id!r} not in {sorted(modules)}")
    targets = modules if family_id is None else {family_id: modules[family_id]}
    original = next(iter(modules.values())).max_position_units

    def scaled(*args: Any, **kwargs: Any) -> int:
        return original(*args, **kwargs) * factor

    def install() -> contextlib.AbstractContextManager[None]:
        return _patched_attrs([(m, "max_position_units", scaled) for m in targets.values()])

    def probe() -> tuple[str, ...]:
        return tuple(m.max_position_units.__qualname__ for m in targets.values())

    scope = "every strategy family" if family_id is None else family_id
    return Perturbation(
        constraint_id=(
            "family_position_ceiling"
            if family_id is None
            else f"family_position_ceiling:{family_id}"
        ),
        description=f"max_position_units × {factor} in {scope}",
        install=install,
        probe=probe,
        factor=float(factor),
    )


def max_order_qty_perturbation(factor: int = 1000) -> Perturbation:
    """Scale every agent's single-order cap (``AgentSpec.max_order_qty``).

    This one lives in per-agent configuration, not module state, so it is
    applied through ``adjust`` on each freshly built market.  Its probe is a
    module-level flag: the perturbation is "installed" for the duration of the
    context, and ``adjust`` refuses to act outside it.
    """
    state = {"active": False}

    @contextlib.contextmanager
    def install() -> Iterator[None]:
        state["active"] = True
        try:
            yield
        finally:
            state["active"] = False

    def adjust(market: Any) -> None:
        if not state["active"]:
            return
        for spec in getattr(getattr(market, "config", None), "agent_specs", ()) or ():
            spec.max_order_qty = int(spec.max_order_qty) * factor

    return Perturbation(
        constraint_id="max_order_qty",
        description=f"AgentSpec.max_order_qty × {factor} for every agent",
        install=install,
        probe=lambda: state["active"],
        adjust=adjust,
        factor=float(factor),
    )


def margin_gate_perturbation() -> Perturbation:
    """Relax the ledger margin gate: grant the full requested new-open size.

    Not a scale factor -- the gate is a feasibility search, so the way to ask
    "does it bind" is to let everything through and see whether anything
    changes.
    """
    from market_game_sim.agent import constraint as constraint_module

    def relaxed(position: int, desired: int, account: Any, active_orders: Any, policy: Any) -> int:
        return constraint_module.new_open_target(position, desired)

    def install() -> contextlib.AbstractContextManager[None]:
        return _patched_attrs([(constraint_module, "_judge_feasible_new_open", relaxed)])

    def probe() -> str:
        return constraint_module._judge_feasible_new_open.__qualname__

    return Perturbation(
        constraint_id="margin_gate",
        description="_judge_feasible_new_open grants the full new-open target",
        install=install,
        probe=probe,
    )


def default_perturbations() -> list[Perturbation]:
    """The constraints 0.4.1 argued about, at the resolution that answers them.

    The position ceiling is split per family on purpose: the aggregate patch
    is what was tried during the milestone, and it answers a question nobody
    asked ("does *some* family's ceiling bind").
    """
    return [
        *(family_position_ceiling_perturbation(family) for family in _family_modules()),
        max_order_qty_perturbation(),
        margin_gate_perturbation(),
    ]


def default_market_factory() -> MarketFactory:
    """A fresh ``LiveMarket`` on ``DEFAULT_LIVE_ROSTER`` for every call."""
    from market_game_sim.experiment.h2.live_market import DEFAULT_LIVE_ROSTER, LiveMarket
    from market_game_sim.experiment.roster import parse_roster

    def build() -> DrivableMarket:
        return LiveMarket(roster=parse_roster(DEFAULT_LIVE_ROSTER))

    return build


def main(argv: list[str] | None = None) -> int:
    """``python -m market_game_sim.metrics.binding_diagnosis --seconds 40``."""
    import argparse

    parser = argparse.ArgumentParser(prog="market-game binding-diagnosis")
    parser.add_argument("--seconds", type=int, default=DEFAULT_LOGICAL_SECONDS)
    parser.add_argument("--warmup", type=int, default=DEFAULT_WARMUP_SECONDS)
    parser.add_argument("--out", default="artifacts/binding-diagnosis.json")
    args = parser.parse_args(argv)

    report = diagnose(
        default_market_factory(),
        default_perturbations(),
        logical_seconds=args.seconds,
        warmup_seconds=args.warmup,
    )
    out = export(report, args.out)
    print(f"roster={report.roster_id} agents={report.agent_count} seconds={args.seconds}")
    print(f"baseline records={report.baseline_record_count} trades={report.baseline_trade_count}")
    for verdict in report.verdicts:
        where = "" if verdict.first_divergence is None else f" @record {verdict.first_divergence}"
        print(f"  {verdict.constraint_id:26s} {verdict.verdict:14s}{where}")
    print(f"-> {out}")
    return 0


__all__ = [
    "BINDING",
    "DEFAULT_LOGICAL_SECONDS",
    "DEFAULT_WARMUP_SECONDS",
    "INCONCLUSIVE",
    "NOT_BINDING",
    "SCHEMA_VERSION",
    "BindingDiagnosisError",
    "ConstraintVerdict",
    "DiagnosisReport",
    "DrivableMarket",
    "EventStream",
    "Perturbation",
    "default_market_factory",
    "default_perturbations",
    "diagnose",
    "drive",
    "export",
    "family_position_ceiling_perturbation",
    "load_report",
    "main",
    "margin_gate_perturbation",
    "max_order_qty_perturbation",
]


if __name__ == "__main__":
    sys.exit(main())
