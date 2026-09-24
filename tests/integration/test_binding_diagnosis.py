"""0.4.1 C-1: the binding diagnosis has to answer two known cases correctly.

The known answers come from the milestone itself:

* ``trend_following`` / ``mean_reversion`` position ceiling -- **not binding**.
  ``max_position_units`` was patched twice (missing ``MULT``, then a cash
  basis) and both runs were bit-identical to the unpatched one.
* the ledger margin gate -- **binding**.  Every decision clips against
  ``MARGIN_LIMIT``.

The harness tests matter as much as the two known answers.  A tool that
silently fails to install its patch reports "not binding" for everything and
looks perfectly healthy while doing it, which is the exact failure mode this
whole module exists to prevent.
"""

from __future__ import annotations

import json

import pytest

from market_game_sim.metrics import binding_diagnosis as BD
from market_game_sim.metrics.binding_diagnosis import (
    BINDING,
    INCONCLUSIVE,
    NOT_BINDING,
    BindingDiagnosisError,
    DiagnosisReport,
    EventStream,
    Perturbation,
    default_market_factory,
    diagnose,
    drive,
    export,
    family_position_ceiling_perturbation,
    load_report,
    margin_gate_perturbation,
    max_order_qty_perturbation,
)

#: Short enough to keep the suite fast, long enough that the noise family has
#: placed its first sized order (the first divergence lands at record ~991).
SECONDS = 12
WARMUP = 2


@pytest.fixture(scope="module")
def build():
    return default_market_factory()


@pytest.fixture(scope="module")
def baseline(build):
    return drive(build(), logical_seconds=SECONDS, warmup_seconds=WARMUP)


# --------------------------------------------------------------------------- #
# The comparison itself has to be exact
# --------------------------------------------------------------------------- #


def test_the_same_assembly_replays_bit_for_bit(build, baseline):
    """Everything else rests on this: two fresh markets must agree exactly.

    If the baseline were not reproducible, every perturbation would "differ"
    and the tool would report BINDING for all of them -- a systematic false
    positive that looks like a confident answer.
    """
    again = drive(build(), logical_seconds=SECONDS, warmup_seconds=WARMUP)
    assert again.digest == baseline.digest
    assert again.first_divergence(baseline) is None
    assert again.record_count == baseline.record_count


def test_a_shorter_run_diverges_at_the_length_of_the_shorter_one(build, baseline):
    """Fewer records is a difference, not a prefix match."""
    shorter = drive(build(), logical_seconds=SECONDS - 4, warmup_seconds=WARMUP)
    assert shorter.record_count < baseline.record_count
    assert shorter.first_divergence(baseline) == shorter.record_count
    assert baseline.first_divergence(shorter) == shorter.record_count


# --------------------------------------------------------------------------- #
# The two known answers
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("family", ["trend_following", "mean_reversion"])
def test_position_ceiling_does_not_bind_for_the_slow_families(build, baseline, family):
    """Known NOT_BINDING: scaling the ceiling 1000x changes nothing at all."""
    perturbation = family_position_ceiling_perturbation(family)
    perturbation.verify_installed()
    with perturbation.install():
        stream = drive(build(), logical_seconds=SECONDS, warmup_seconds=WARMUP)
    assert stream.first_divergence(baseline) is None
    assert stream.digest == baseline.digest


def test_margin_gate_binds(build, baseline):
    """Known BINDING: granting the full new-open target moves the stream."""
    perturbation = margin_gate_perturbation()
    perturbation.verify_installed()
    with perturbation.install():
        stream = drive(build(), logical_seconds=SECONDS, warmup_seconds=WARMUP)
    assert stream.first_divergence(baseline) is not None
    assert stream.digest != baseline.digest


def test_noise_family_ceiling_binds_although_the_slow_families_do_not(build, baseline):
    """The per-family split earns its keep: one family out of three binds.

    Measured 2026-09-24.  The aggregate patch (all three families at once) is
    what the milestone actually tried; it reports BINDING, which is true and
    uninformative -- ``sentiment_noise`` alone accounts for it.
    """
    perturbation = family_position_ceiling_perturbation("sentiment_noise")
    with perturbation.install():
        stream = drive(build(), logical_seconds=SECONDS, warmup_seconds=WARMUP)
    assert stream.first_divergence(baseline) is not None


def test_record_and_trade_counts_alone_cannot_tell_the_two_apart(build, baseline):
    """Why the comparison is bit-exact and not a summary statistic.

    The binding perturbation above changes *which* orders are placed without
    changing how many records or trades the run produces.  Any comparison
    coarser than record-by-record reports "no difference" here.
    """
    perturbation = family_position_ceiling_perturbation("sentiment_noise")
    with perturbation.install():
        stream = drive(build(), logical_seconds=SECONDS, warmup_seconds=WARMUP)
    assert stream.first_divergence(baseline) is not None
    assert stream.record_count == baseline.record_count
    assert stream.trade_count == baseline.trade_count


# --------------------------------------------------------------------------- #
# A patch that does not take must never be reported as "not binding"
# --------------------------------------------------------------------------- #


def test_inert_perturbation_is_rejected_rather_than_called_not_binding():
    """The failure mode this module exists to prevent."""
    inert = Perturbation(
        constraint_id="inert",
        description="a patch that forgets to patch",
        install=lambda: _nullcontext(),
        probe=lambda: "always the same",
    )
    with pytest.raises(BindingDiagnosisError) as excinfo:
        inert.verify_installed()
    assert excinfo.value.code == "PERTURBATION_INERT"


def test_leaking_perturbation_is_rejected():
    """Process state must be clean afterwards, or later runs are contaminated."""
    state = {"value": 0}

    def install():
        state["value"] += 1
        return _nullcontext()

    leaky = Perturbation(
        constraint_id="leaky",
        description="never restores",
        install=install,
        probe=lambda: state["value"],
    )
    with pytest.raises(BindingDiagnosisError) as excinfo:
        leaky.verify_installed()
    assert excinfo.value.code == "PERTURBATION_LEAKED"


def test_real_perturbations_restore_module_state():
    for perturbation in (
        family_position_ceiling_perturbation("trend_following"),
        margin_gate_perturbation(),
        max_order_qty_perturbation(),
    ):
        before, during = perturbation.verify_installed()
        assert before != during
        assert perturbation.probe() == before


def test_max_order_qty_adjust_refuses_to_act_outside_its_context(build):
    """``adjust`` mutates a live market; outside the context it must no-op."""
    perturbation = max_order_qty_perturbation()
    market = build()
    before = [spec.max_order_qty for spec in market.config.agent_specs]
    perturbation.adjust(market)
    assert [spec.max_order_qty for spec in market.config.agent_specs] == before
    with perturbation.install():
        perturbation.adjust(market)
    after = [spec.max_order_qty for spec in market.config.agent_specs]
    assert after == [value * 1000 for value in before]


# --------------------------------------------------------------------------- #
# Verdict logic, on synthetic streams (no market, no clock)
# --------------------------------------------------------------------------- #


def _stream(digests, trades=0):
    return EventStream(record_digests=tuple(digests), trade_count=trades, logical_ns=0)


def _nullcontext():
    import contextlib

    return contextlib.nullcontext()


def _fake_perturbation(constraint_id, state, marker):
    """A perturbation whose probe moves and whose effect is caller-controlled."""

    import contextlib

    @contextlib.contextmanager
    def install():
        state["active"] = marker
        try:
            yield
        finally:
            state["active"] = None

    return Perturbation(
        constraint_id=constraint_id,
        description=constraint_id,
        install=install,
        probe=lambda: state["active"],
    )


class _ScriptedMarket:
    """A market whose record stream depends on the active perturbation."""

    class _Kernel:
        def __init__(self, records):
            self.committed_records = records

    def __init__(self, state, effects):
        marker = state["active"]
        self.logical_ns = 0
        self.kernel = self._Kernel(effects.get(marker, effects[None]))
        self.config = None
        self.roster_id = "scripted"

    def advance(self):
        return None


def test_unmoved_stream_is_inconclusive_when_nothing_else_moved():
    """No perturbation moved anything: the harness may simply be blind.

    Reporting NOT_BINDING here would be the tool making exactly the claim it
    was built to stop people from making without evidence.
    """
    state = {"active": None}
    effects = {None: [{"e": 1}], "a": [{"e": 1}], "b": [{"e": 1}]}
    report = diagnose(
        lambda: _ScriptedMarket(state, effects),
        [_fake_perturbation("a", state, "a"), _fake_perturbation("b", state, "b")],
        logical_seconds=1,
        warmup_seconds=0,
    )
    assert [v.verdict for v in report.verdicts] == [INCONCLUSIVE, INCONCLUSIVE]
    assert report.not_binding == []
    assert report.inconclusive == ["a", "b"]


def test_unmoved_stream_is_not_binding_once_something_else_moved():
    state = {"active": None}
    effects = {None: [{"e": 1}], "a": [{"e": 1}], "b": [{"e": 2}]}
    report = diagnose(
        lambda: _ScriptedMarket(state, effects),
        [_fake_perturbation("a", state, "a"), _fake_perturbation("b", state, "b")],
        logical_seconds=1,
        warmup_seconds=0,
    )
    assert report.not_binding == ["a"]
    assert report.binding == ["b"]
    assert report.inconclusive == []


def test_first_divergence_is_reported_for_a_binding_constraint():
    state = {"active": None}
    effects = {
        None: [{"e": 1}, {"e": 2}, {"e": 3}],
        "b": [{"e": 1}, {"e": 2}, {"e": 99}],
    }
    report = diagnose(
        lambda: _ScriptedMarket(state, effects),
        [_fake_perturbation("b", state, "b")],
        logical_seconds=1,
        warmup_seconds=0,
    )
    assert report.verdicts[0].verdict == BINDING
    assert report.verdicts[0].first_divergence == 2


def test_diagnose_rejects_empty_and_duplicate_candidates():
    state = {"active": None}
    effects = {None: [{"e": 1}], "a": [{"e": 1}]}
    factory = lambda: _ScriptedMarket(state, effects)  # noqa: E731
    with pytest.raises(BindingDiagnosisError) as empty:
        diagnose(factory, [], logical_seconds=1)
    assert empty.value.code == "NO_PERTURBATIONS"
    with pytest.raises(BindingDiagnosisError) as dupe:
        diagnose(
            factory,
            [_fake_perturbation("a", state, "a"), _fake_perturbation("a", state, "a")],
            logical_seconds=1,
        )
    assert dupe.value.code == "DUPLICATE_CONSTRAINT"


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"logical_seconds": 0}, "INVALID_DURATION"),
        ({"logical_seconds": 1.5}, "INVALID_DURATION"),
        ({"logical_seconds": 1, "warmup_seconds": -1}, "INVALID_WARMUP"),
    ],
)
def test_drive_rejects_invalid_horizons(kwargs, code):
    state = {"active": None}
    market = _ScriptedMarket(state, {None: []})
    with pytest.raises(BindingDiagnosisError) as excinfo:
        drive(market, **kwargs)
    assert excinfo.value.code == code


def test_a_market_that_raises_mid_run_propagates_rather_than_reporting_a_verdict():
    """An aborted perturbed run must not be silently read as 'no difference'."""

    class _Exploding(_ScriptedMarket):
        def advance(self):
            raise RuntimeError("kernel abort")

    state = {"active": None}
    with pytest.raises(RuntimeError, match="kernel abort"):
        drive(_Exploding(state, {None: []}), logical_seconds=1)


def test_unknown_family_is_rejected():
    with pytest.raises(BindingDiagnosisError) as excinfo:
        family_position_ceiling_perturbation("value_investor")
    assert excinfo.value.code == "UNKNOWN_FAMILY"


# --------------------------------------------------------------------------- #
# Artifact
# --------------------------------------------------------------------------- #


def _synthetic_report():
    state = {"active": None}
    effects = {None: [{"e": 1}], "a": [{"e": 1}], "b": [{"e": 2}]}
    return diagnose(
        lambda: _ScriptedMarket(state, effects),
        [_fake_perturbation("a", state, "a"), _fake_perturbation("b", state, "b")],
        logical_seconds=1,
        warmup_seconds=0,
    )


def test_artifact_round_trips_and_carries_the_scope_of_the_claim(tmp_path):
    report = _synthetic_report()
    out = export(report, tmp_path / "binding.json")
    payload = load_report(out)
    assert payload["content_hash"] == report.content_hash
    assert payload["evidence_label"] == "engineering-demonstration"
    # A verdict without its horizon is not a claim anyone can check.
    assert payload["logical_seconds"] == 1
    assert payload["baseline_digest"] == report.baseline_digest
    assert {v["constraint_id"] for v in payload["verdicts"]} == {"a", "b"}
    assert all("probe_before" in v and "probe_during" in v for v in payload["verdicts"])


def test_tampered_artifact_is_rejected(tmp_path):
    report = _synthetic_report()
    out = export(report, tmp_path / "binding.json")
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["verdicts"][0]["verdict"] = BINDING
    out.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(BindingDiagnosisError) as excinfo:
        load_report(out)
    assert excinfo.value.code == "CONTENT_HASH_MISMATCH"


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda p: p.pop("baseline_digest"), "MISSING_KEYS"),
        (lambda p: p.update({"extra": 1}), "UNKNOWN_KEYS"),
    ],
)
def test_artifact_key_set_is_closed(tmp_path, mutate, code):
    report = _synthetic_report()
    out = export(report, tmp_path / "binding.json")
    payload = json.loads(out.read_text(encoding="utf-8"))
    mutate(payload)
    out.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(BindingDiagnosisError) as excinfo:
        load_report(out)
    assert excinfo.value.code == code


def test_report_partitions_every_candidate_into_exactly_one_bucket():
    report = _synthetic_report()
    ids = [v.constraint_id for v in report.verdicts]
    buckets = report.binding + report.not_binding + report.inconclusive
    assert sorted(buckets) == sorted(ids)
    assert len(buckets) == len(set(buckets))


def test_content_hash_covers_the_verdicts():
    report = _synthetic_report()
    flipped = DiagnosisReport(
        roster_id=report.roster_id,
        agent_count=report.agent_count,
        logical_seconds=report.logical_seconds,
        warmup_seconds=report.warmup_seconds,
        baseline_record_count=report.baseline_record_count,
        baseline_trade_count=report.baseline_trade_count,
        baseline_digest=report.baseline_digest,
        verdicts=tuple(
            BD.ConstraintVerdict(**{**v.to_dict(), "verdict": NOT_BINDING}) for v in report.verdicts
        ),
    )
    assert flipped.content_hash != report.content_hash
