"""0.4.3 T1107 (NFR-701 / SC-704 / AC-702): the anchor's strength knobs are wired.

ADR-016 §4.1: a strength parameter is dead if it does not bind, or if it binds
but does not move the market the right way.  Both are checked:

* **binding** -- ``sensitivity_x1000`` × 10 moves the event stream within a few
  logical seconds (measured here, in the suite).  ``count`` is not asked:
  adding agents always moves the stream, so its binding says nothing;
* **direction** -- over the full 5700-second window, M (the largest
  ``|price / v_t - 1|`` at segment ends) never grows as either knob grows, and
  the extremes differ.  That measurement takes minutes per level, so it is the
  committed artifact ``docs/experiments/0.4.3-anchor-strength.json``, produced by
  ``python -m market_game_sim.metrics.anchor_strength``; the suite checks the
  artifact (window, pre-registered levels, verdicts its own data support) and
  runs the tool end to end on a short window.

The verdict rule is tested from both sides on synthetic data, and a tampered
artifact must be refused.
"""

from __future__ import annotations

import json

import pytest

from market_game_sim.metrics import anchor_strength as AS
from market_game_sim.metrics.anchor_strength import (
    COUNT_LEVELS,
    FLAT,
    FULL_WINDOW_SECONDS,
    MONOTONE,
    NOT_MONOTONE,
    SENSITIVITY_LEVELS,
    AnchorStrengthError,
    load_report,
    monotone_verdict,
    run_level,
)
from market_game_sim.metrics.binding_diagnosis import (
    BindingDiagnosisError,
    anchored_market_factory,
    default_market_factory,
    drive,
    value_sensitivity_perturbation,
)

ARTIFACT = "docs/experiments/0.4.3-anchor-strength.json"
SECONDS = 12
WARMUP = 2


# --------------------------------------------------------------------------- #
# Binding
# --------------------------------------------------------------------------- #


def test_sensitivity_binds():
    build = anchored_market_factory()
    baseline = drive(build(), logical_seconds=SECONDS, warmup_seconds=WARMUP)
    perturbation = value_sensitivity_perturbation(10)
    perturbation.verify_installed()
    with perturbation.install():
        market = build()
        perturbation.adjust(market)
        stream = drive(market, logical_seconds=SECONDS, warmup_seconds=WARMUP)
    assert stream.first_divergence(baseline) is not None


def test_sensitivity_perturbation_is_inert_outside_its_context():
    perturbation = value_sensitivity_perturbation(10)
    market = anchored_market_factory()()
    before = [dict(s.strategy_private or {}) for s in market.config.agent_specs]
    perturbation.adjust(market)
    assert [dict(s.strategy_private or {}) for s in market.config.agent_specs] == before


def test_a_market_without_value_agents_is_a_harness_error_not_a_verdict():
    perturbation = value_sensitivity_perturbation(10)
    with perturbation.install(), pytest.raises(BindingDiagnosisError) as exc:
        perturbation.adjust(default_market_factory()())
    assert exc.value.code == "PERTURBATION_INERT"


# --------------------------------------------------------------------------- #
# Verdict rule, both sides
# --------------------------------------------------------------------------- #


def test_verdict_monotone():
    assert monotone_verdict([1.7, 1.5, 0.003, 0.002]) == MONOTONE
    assert monotone_verdict([0.006, 0.006, 0.002]) == MONOTONE


def test_verdict_not_monotone():
    """0.4.1 §17.2's ``max_order_qty`` shape: the middle level is the worst."""
    assert monotone_verdict([2.34, 2.86, 2.23]) == NOT_MONOTONE


def test_verdict_flat():
    """0.4.1 §17.5's shape upwards: the knob moved nothing."""
    assert monotone_verdict([2.86, 2.86]) == FLAT


def test_verdict_needs_two_levels():
    with pytest.raises(AnchorStrengthError) as exc:
        monotone_verdict([0.1])
    assert exc.value.code == "TOO_FEW_LEVELS"


# --------------------------------------------------------------------------- #
# The committed full-window measurement
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def artifact():
    return load_report(ARTIFACT)


def test_artifact_covers_the_full_window_at_the_preregistered_levels(artifact):
    assert artifact["seconds"] == FULL_WINDOW_SECONDS
    assert [lvl["sensitivity_x1000"] for lvl in artifact["sensitivity"]["levels"]] == list(
        SENSITIVITY_LEVELS
    )
    assert [lvl["count"] for lvl in artifact["count"]["levels"]] == list(COUNT_LEVELS)
    for knob in ("sensitivity", "count"):
        for level in artifact[knob]["levels"]:
            assert len(level["segment_prices"]) == FULL_WINDOW_SECONDS // 300


def test_both_knobs_are_monotone(artifact):
    assert artifact["sensitivity"]["verdict"] == MONOTONE
    assert artifact["count"]["verdict"] == MONOTONE


def test_the_unanchored_baseline_is_the_worst_case(artifact):
    worst_anchored = max(
        level["deviation_max"]
        for knob in ("sensitivity", "count")
        for level in artifact[knob]["levels"]
    )
    assert artifact["baseline"]["count"] == 0
    assert artifact["baseline"]["deviation_max"] > worst_anchored


def test_a_tampered_verdict_is_refused(artifact, tmp_path):
    forged = json.loads(json.dumps(artifact))
    forged["sensitivity"]["levels"][0]["deviation_max"] = 0.0
    path = tmp_path / "forged.json"
    path.write_text(json.dumps(forged), encoding="utf-8")
    with pytest.raises(AnchorStrengthError) as exc:
        load_report(path)
    assert exc.value.code == "VERDICT_MISMATCH"


# --------------------------------------------------------------------------- #
# The tool runs end to end (short window)
# --------------------------------------------------------------------------- #


def test_run_level_measures_a_short_window():
    result = run_level(6, 1000, seconds=300)
    assert result.seconds == 300
    assert len(result.segment_prices) == 1
    assert result.trades > 0
    assert result.deviation_max >= 0


def test_run_level_refuses_a_window_shorter_than_one_segment():
    with pytest.raises(AnchorStrengthError) as exc:
        run_level(6, 1000, seconds=100)
    assert exc.value.code == "INVALID_DURATION"


def test_unanchored_roster_is_the_default_roster():
    from market_game_sim.experiment.h2.live_market import DEFAULT_LIVE_ROSTER

    assert AS.anchored_roster(0, 0) == dict(DEFAULT_LIVE_ROSTER)
