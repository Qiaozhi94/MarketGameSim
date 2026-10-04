"""0.4.3 T1109 (SC-704 / AC-708): the scan's pre-registration and its guard.

What has to hold before T1111 runs a single configuration:

* the pre-registration is one committed file carrying the owner's three
  decisions (15-point grid, all-seeds qualification, seed-7 screening);
* its sha256 is pinned here -- editing the grid or a criterion after the fact
  is a red build, not a silent change (spec §5 invariant);
* the scan guard fails closed on a missing file and on a file that no longer
  hashes to what the scan recorded;
* the screening rule and the qualification rule each hold from both sides.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from market_game_sim.experiment.h2.live_market import DEFAULT_LIVE_ROSTER
from market_game_sim.experiment.roster import parse_roster
from market_game_sim.metrics.anchor_scan import (
    FAIL,
    PASS,
    PREREGISTRATION_PATH,
    ScanPreregistrationError,
    begin_scan,
    file_sha256,
    load_preregistration,
    qualifies,
    screen,
    verify_preregistration,
)
from market_game_sim.metrics.anchor_strength import VALUE_FAMILY_PARAMS

#: Pinned at registration (2026-10-04).  Changing it requires a new, explicit
#: decision recorded in the experiment report -- never a quiet re-pin.
REGISTERED_SHA256 = "1c3862b78aed57379a2981859e14a70b1d6cf1ddbb1f310b3cc3ce37fc0c7ac5"
V = 10_000


@pytest.fixture(scope="module")
def prereg():
    return load_preregistration()


# --------------------------------------------------------------------------- #
# The registered content
# --------------------------------------------------------------------------- #


def test_the_file_is_pinned():
    assert file_sha256(PREREGISTRATION_PATH) == REGISTERED_SHA256


def test_the_file_is_committed():
    if shutil.which("git") is None:
        pytest.skip("git not available")
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", PREREGISTRATION_PATH.as_posix()],
        capture_output=True,
        text=True,
    )
    assert tracked.returncode == 0, "the pre-registration must be committed before any scan"


def test_owner_decisions_are_what_was_registered(prereg):
    assert prereg["grid"]["count"] == [1, 2, 6]
    assert prereg["grid"]["sensitivity_x1000"] == [150, 200, 300, 500, 700]
    assert len(prereg["grid"]["points"]) == 15
    assert prereg["screening"]["seeds"] == [7]
    assert prereg["full_measurement"]["seeds"] == [7, 8, 9]
    assert prereg["qualification"]["rule"] == "all_seeds_pass_sc501_and_sc502"


def test_screening_criteria_match_spec_sc_704(prereg):
    criteria = prereg["screening"]["criteria"]
    assert criteria == {"price_multiple_max": 1.5, "down_segment_ratio_min": [4, 13]}
    assert prereg["window_seconds"] == 5700 and prereg["segment_seconds"] == 300


def test_heterogeneity_is_diagnostic_only(prereg):
    assert "trend_following" not in json.dumps(prereg["screening"]["criteria"])
    assert any("trend_following" in d for d in prereg["screening"]["diagnostic_only"])


def test_base_roster_and_value_params_are_the_t1107_ones(prereg):
    assert prereg["base_roster_id"] == parse_roster(DEFAULT_LIVE_ROSTER).roster_id
    assert prereg["value_family_params"] == dict(VALUE_FAMILY_PARAMS)
    assert prereg["response_function"]["id"] == "linear_saturating_v1"
    assert prereg["response_function"]["attempt"] == 1


# --------------------------------------------------------------------------- #
# The guard (AC-708), both sides
# --------------------------------------------------------------------------- #


def test_scan_starts_from_the_file_and_records_its_hash():
    started = begin_scan()
    assert started["preregistration_sha256"] == REGISTERED_SHA256
    assert verify_preregistration(started["preregistration_sha256"])["grid"]


def test_missing_file_fails_closed(tmp_path):
    with pytest.raises(ScanPreregistrationError) as exc:
        begin_scan(tmp_path / "absent.json")
    assert exc.value.code == "PREREGISTRATION_MISSING"


def test_a_file_changed_after_the_scan_started_fails_closed(tmp_path):
    copy = tmp_path / "prereg.json"
    copy.write_bytes(PREREGISTRATION_PATH.read_bytes())
    recorded = begin_scan(copy)["preregistration_sha256"]
    data = json.loads(copy.read_text(encoding="utf-8"))
    data["grid"]["sensitivity_x1000"].append(400)
    data["grid"]["points"] += [
        {"count": c, "sensitivity_x1000": 400} for c in data["grid"]["count"]
    ]
    copy.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with pytest.raises(ScanPreregistrationError) as exc:
        verify_preregistration(recorded, copy)
    assert exc.value.code == "PREREGISTRATION_TAMPERED"


def test_a_grid_that_is_not_the_full_product_is_invalid(tmp_path):
    data = json.loads(PREREGISTRATION_PATH.read_text(encoding="utf-8"))
    data["grid"]["points"] = data["grid"]["points"][:-1]
    path = tmp_path / "prereg.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ScanPreregistrationError) as exc:
        load_preregistration(path)
    assert exc.value.code == "PREREGISTRATION_INVALID"


# --------------------------------------------------------------------------- #
# Screening (SC-704 ① ②), both sides
# --------------------------------------------------------------------------- #

CRITERIA = {"price_multiple_max": 1.5, "down_segment_ratio_min": [4, 13]}


def series(downs: int, segments: int = 19, top: int = 10_400) -> list[int]:
    """``downs`` falling segments among ``segments``, never above ``top``."""
    prices, price = [], V
    for i in range(segments):
        price = price - 20 if i < downs else min(top, price + 30)
        prices.append(price)
    return prices


def test_a_bounded_two_way_run_passes():
    verdict = screen(V, series(downs=6), CRITERIA)
    assert verdict["down_segments"] == 6 and verdict["segments"] == 19
    assert verdict["passes_screening"] == PASS


def test_one_segment_at_or_above_one_and_a_half_fails_criterion_one():
    prices = series(downs=8)
    prices[10] = 15_000
    verdict = screen(V, prices, CRITERIA)
    assert verdict["price_multiple_below_max"] == FAIL
    assert verdict["passes_screening"] == FAIL


def test_five_down_segments_of_nineteen_fail_criterion_two():
    """4/13 of 19 is 5.85: six down segments pass, five do not."""
    assert screen(V, series(downs=5), CRITERIA)["down_segment_ratio"] == FAIL
    assert screen(V, series(downs=6), CRITERIA)["down_segment_ratio"] == PASS


def test_a_segment_without_trades_counts_but_is_not_down():
    flat = [V] * 19
    verdict = screen(V, flat, CRITERIA)
    assert verdict["down_segments"] == 0
    assert verdict["passes_screening"] == FAIL


def test_a_crash_is_not_screened_out_by_criterion_one():
    """① has an upper bound only (as registered); a crash is SC-501/502's to judge."""
    prices = series(downs=10)
    prices[-1] = 4_000
    assert screen(V, prices, CRITERIA)["price_multiple_below_max"] == PASS


# --------------------------------------------------------------------------- #
# Qualification (all seeds, both gates), both sides
# --------------------------------------------------------------------------- #

OK = {"sc_501": True, "sc_502": True}


def test_all_seeds_passing_both_qualifies():
    assert qualifies({7: OK, 8: OK, 9: OK}, [7, 8, 9])


def test_one_seed_failing_either_gate_does_not_qualify():
    """0.4.1 T973's shape: each seed failed a different gate."""
    assert not qualifies({7: OK, 8: {"sc_501": True, "sc_502": False}, 9: OK}, [7, 8, 9])
    assert not qualifies({7: {"sc_501": False, "sc_502": True}, 8: OK, 9: OK}, [7, 8, 9])


def test_an_unmeasured_seed_is_an_error_not_a_pass():
    with pytest.raises(ScanPreregistrationError) as exc:
        qualifies({7: OK, 8: OK}, [7, 8, 9])
    assert exc.value.code == "INCOMPLETE_MEASUREMENT"
