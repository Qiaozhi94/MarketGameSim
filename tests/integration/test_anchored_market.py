"""0.4.3 T1108 (US-701 / NFR-702 / AC-707): outcome gate H2-E4, the anchored market.

The gate's artifact is ``docs/experiments/0.4.3-anchored-market.json``: the
roster in ``docs/experiments/0.4.3-rosters/`` run for the full 5700-second
window, twice.  The suite checks the artifact (its verdicts are recomputed on
load), checks every criterion's rule from both sides on synthetic series,
replays the roster for a short window to keep determinism under CI, and drives
the live-market CLI's roster loading -- including refusing a roster file whose
content no longer hashes to its name.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from market_game_sim.experiment.h2.live_market import build_market
from market_game_sim.experiment.roster import RosterError, load_roster
from market_game_sim.metrics.anchored_market import (
    EVIDENCE_CLASS,
    FAIL,
    FULL_WINDOW_SECONDS,
    PASS,
    AnchoredMarketError,
    judge,
    load_artifact,
    run,
)

ARTIFACT = pathlib.Path("docs/experiments/0.4.3-anchored-market.json")
ROSTER_DIR = pathlib.Path("docs/experiments/0.4.3-rosters")
V = 10_000


@pytest.fixture(scope="module")
def artifact():
    return load_artifact(ARTIFACT)


@pytest.fixture(scope="module")
def roster_file(artifact):
    return ROSTER_DIR / f"{artifact['roster_id']}.json"


# --------------------------------------------------------------------------- #
# The committed gate artifact
# --------------------------------------------------------------------------- #


def test_artifact_is_the_full_window_gate(artifact):
    assert artifact["gate"] == "H2-E4"
    assert artifact["evidence_class"] == EVIDENCE_CLASS == "engineering-demonstration"
    assert artifact["seconds"] == FULL_WINDOW_SECONDS
    assert len(artifact["run"]["segment_prices"]) == FULL_WINDOW_SECONDS // 300


def test_every_criterion_passes(artifact):
    assert artifact["verdicts"] == {
        "bounded": PASS,
        "two_way": PASS,
        "trading_at_window_end": PASS,
        "replays_bit_for_bit": PASS,
        "overall": PASS,
    }
    assert artifact["run"]["events_digest"] == artifact["replay_events_digest"]


def test_the_roster_is_committed_and_contains_the_value_family(roster_file):
    roster = load_roster(roster_file.parent, roster_file.stem)
    assert "value_investor" in [f.family_id for f in roster.families]


def test_a_tampered_artifact_is_refused(artifact, tmp_path):
    forged = json.loads(json.dumps(artifact))
    forged["run"]["segment_prices"][3] = 3 * V
    path = tmp_path / "forged.json"
    path.write_text(json.dumps(forged), encoding="utf-8")
    with pytest.raises(AnchoredMarketError) as exc:
        load_artifact(path)
    assert exc.value.code == "VERDICT_MISMATCH"


def test_an_artifact_claiming_a_research_class_is_refused(artifact, tmp_path):
    forged = {**artifact, "evidence_class": "formal-research"}
    path = tmp_path / "forged.json"
    path.write_text(json.dumps(forged), encoding="utf-8")
    with pytest.raises(AnchoredMarketError) as exc:
        load_artifact(path)
    assert exc.value.code == "EVIDENCE_CLASS"


# --------------------------------------------------------------------------- #
# Each rule from both sides
# --------------------------------------------------------------------------- #

GOOD_PRICES = [10_010, 10_030, 10_004, 10_022, 9_990, 10_015]
GOOD_TRADES = [400, 380, 410, 395, 402, 388]
SAME = ["d", "d"]


def test_a_healthy_series_passes():
    assert judge(V, GOOD_PRICES, GOOD_TRADES, SAME)["overall"] == PASS


def test_divergence_fails_bounded():
    """0.4.1's shape: the price runs to 2.86x."""
    verdicts = judge(V, [*GOOD_PRICES[:-1], 28_600], GOOD_TRADES, SAME)
    assert verdicts["bounded"] == FAIL and verdicts["overall"] == FAIL


def test_a_crash_fails_bounded_too():
    verdicts = judge(V, [*GOOD_PRICES[:-1], 6_000], GOOD_TRADES, SAME)
    assert verdicts["bounded"] == FAIL


def test_a_monotone_ramp_fails_two_way():
    verdicts = judge(V, [10_010, 10_020, 10_030, 10_040], [1, 1, 1, 1], SAME)
    assert verdicts["bounded"] == PASS
    assert verdicts["two_way"] == FAIL


def test_a_frozen_price_fails_two_way():
    verdicts = judge(V, [V, V, V, V], [5, 5, 5, 5], SAME)
    assert verdicts["two_way"] == FAIL


def test_a_dead_market_fails_trading_at_window_end():
    verdicts = judge(V, GOOD_PRICES, [*GOOD_TRADES[:-1], 0], SAME)
    assert verdicts["trading_at_window_end"] == FAIL


def test_diverging_replays_fail_reproducibility():
    verdicts = judge(V, GOOD_PRICES, GOOD_TRADES, ["a", "b"])
    assert verdicts["replays_bit_for_bit"] == FAIL


def test_a_single_run_cannot_claim_reproducibility():
    with pytest.raises(AnchoredMarketError) as exc:
        judge(V, GOOD_PRICES, GOOD_TRADES, ["a"])
    assert exc.value.code == "NO_REPLAY"


# --------------------------------------------------------------------------- #
# Determinism under CI and the CLI's roster loading
# --------------------------------------------------------------------------- #


def test_the_roster_replays_bit_for_bit_on_a_short_window(roster_file):
    payload = json.loads(roster_file.read_text(encoding="utf-8"))
    first = run(payload, seconds=300)
    second = run(payload, seconds=300)
    assert first.events_digest == second.events_digest
    assert first.segment_trades[0] > 0


def test_run_refuses_a_partial_segment(roster_file):
    payload = json.loads(roster_file.read_text(encoding="utf-8"))
    with pytest.raises(AnchoredMarketError) as exc:
        run(payload, seconds=450)
    assert exc.value.code == "INVALID_DURATION"


def test_cli_builds_the_anchored_market_from_the_roster_file(roster_file):
    market = build_market(7, str(roster_file))
    assert market.roster_id == roster_file.stem
    assert any(s.strategy_family_id == "value_investor" for s in market.config.agent_specs)


def test_cli_without_a_roster_keeps_the_existing_market():
    assert build_market(7).roster_id is None


def test_cli_refuses_a_roster_file_whose_content_changed(roster_file, tmp_path):
    payload = json.loads(roster_file.read_text(encoding="utf-8"))
    payload["seed"] = payload["seed"] + 1
    forged = tmp_path / roster_file.name
    forged.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RosterError) as exc:
        build_market(7, str(forged))
    assert exc.value.code == "ROSTER_ID_MISMATCH"
