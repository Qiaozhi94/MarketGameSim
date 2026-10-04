"""0.4.3 T1111 (SC-701 / SC-702 / AC-704): outcome gate H2-E5, the registered scan.

The scan screens every registered grid point at the screening seed, measures the
survivors at every full-measurement seed, and concludes ``QUALIFIED`` (some point
passes SC-501 *and* SC-502 at every seed) or ``UNQUALIFIED`` (the grid is
exhausted without one).  An unfinished scan concludes nothing.

These tests drive :func:`assemble` -- the pure part that turns measurements into
verdicts -- on both terminals, refuse a report whose verdicts its measurements
do not support or that points at another pre-registration, and check that a
resumed scan reuses finished runs instead of redoing them.
"""

from __future__ import annotations

import json

import pytest

from market_game_sim.metrics import anchor_scan as SCAN
from market_game_sim.metrics.anchor_scan import (
    FAIL,
    PASS,
    PREREGISTRATION_PATH,
    QUALIFIED,
    UNQUALIFIED,
    ScanPreregistrationError,
    assemble,
    config_roster,
    load_preregistration,
    load_scan_report,
)

V = 10_000


@pytest.fixture(scope="module")
def prereg():
    return load_preregistration()


@pytest.fixture(scope="module")
def sha():
    return SCAN.file_sha256(PREREGISTRATION_PATH)


def two_way() -> list[int]:
    """19 segment-end prices: bounded, 9 down segments -- passes screening."""
    return [10_010, 10_004, 10_022, 10_019, 10_003, 10_017, 10_030, 10_026, 10_010, 10_011] + [
        10_016,
        10_032,
        10_034,
        10_019,
        10_015,
        10_029,
        10_021,
        10_018,
        10_032,
    ]


def runaway() -> list[int]:
    return [V + 1_000 * (i + 1) for i in range(19)]


def measured(count, sens, seed, prices, sc_501=PASS, sc_502=PASS):
    return {
        "count": count,
        "sensitivity_x1000": sens,
        "seed": seed,
        "reference_ticks": V,
        "segment_prices": prices,
        "sc_501": sc_501,
        "sc_502": sc_502,
        "anchor_diagnostics": {"trend_following_takers": 0},
    }


def all_points(prereg):
    return [(int(p["count"]), int(p["sensitivity_x1000"])) for p in prereg["grid"]["points"]]


def results_where(prereg, survivor=None, survivor_seeds=None):
    """Every point screened at seed 7; only ``survivor`` passes screening."""
    out = {}
    for c, s in all_points(prereg):
        prices = two_way() if (c, s) == survivor else runaway()
        out[(c, s, 7)] = measured(c, s, 7, prices, **(survivor_seeds or {}).get(7, {}))
    if survivor:
        for seed in (8, 9):
            out[(*survivor, seed)] = measured(
                *survivor, seed, two_way(), **(survivor_seeds or {}).get(seed, {})
            )
    return out


# --------------------------------------------------------------------------- #
# Both terminals, and no terminal while unfinished
# --------------------------------------------------------------------------- #


def test_qualified_when_a_screened_point_passes_both_gates_at_every_seed(prereg, sha):
    report = assemble(prereg, sha, results_where(prereg, survivor=(2, 300)))
    assert report["complete"] is True
    assert report["terminal"] == QUALIFIED
    assert report["qualified_configs"] == [{"count": 2, "sensitivity_x1000": 300}]


def test_unqualified_when_the_grid_is_exhausted_without_one(prereg, sha):
    report = assemble(prereg, sha, results_where(prereg))
    assert report["terminal"] == UNQUALIFIED
    assert report["qualified_configs"] == []
    assert len(report["configs"]) == 15
    assert all(c["screening"]["passes_screening"] == FAIL for c in report["configs"])


def test_one_seed_failing_one_gate_keeps_the_grid_unqualified(prereg, sha):
    """T973's shape inside the scan: the survivor fails SC-502 at seed 8 only."""
    results = results_where(prereg, survivor=(2, 300), survivor_seeds={8: {"sc_502": FAIL}})
    report = assemble(prereg, sha, results)
    assert report["terminal"] == UNQUALIFIED


def test_a_screened_out_point_is_never_measured_further(prereg, sha):
    report = assemble(prereg, sha, results_where(prereg, survivor=(2, 300)))
    for config in report["configs"]:
        expected = {7, 8, 9} if (config["count"], config["sensitivity_x1000"]) == (2, 300) else {7}
        assert set(config["seeds"]) == expected


def test_an_unfinished_screen_concludes_nothing(prereg, sha):
    results = results_where(prereg)
    results.pop(next(iter(results)))
    report = assemble(prereg, sha, results)
    assert report["complete"] is False
    assert report["terminal"] is None


def test_a_survivor_missing_a_seed_concludes_nothing(prereg, sha):
    results = results_where(prereg, survivor=(2, 300))
    results.pop((2, 300, 9))
    report = assemble(prereg, sha, results)
    assert report["complete"] is False
    assert report["terminal"] is None


# --------------------------------------------------------------------------- #
# The report file
# --------------------------------------------------------------------------- #


def write(tmp_path, report):
    path = tmp_path / "scan.json"
    path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    return path


def test_a_consistent_report_loads(prereg, sha, tmp_path):
    report = assemble(prereg, sha, results_where(prereg, survivor=(2, 300)))
    assert load_scan_report(write(tmp_path, report))["terminal"] == QUALIFIED


def test_a_report_with_a_forged_terminal_is_refused(prereg, sha, tmp_path):
    report = assemble(prereg, sha, results_where(prereg))
    report["terminal"] = QUALIFIED
    with pytest.raises(ScanPreregistrationError) as exc:
        load_scan_report(write(tmp_path, report))
    assert exc.value.code == "SCAN_VERDICT_MISMATCH"


def test_a_report_with_a_forged_screening_is_refused(prereg, sha, tmp_path):
    report = assemble(prereg, sha, results_where(prereg))
    report["configs"][0]["screening"]["passes_screening"] = PASS
    with pytest.raises(ScanPreregistrationError) as exc:
        load_scan_report(write(tmp_path, report))
    assert exc.value.code == "SCAN_VERDICT_MISMATCH"


def test_a_report_tied_to_another_preregistration_is_refused(prereg, tmp_path):
    report = assemble(prereg, "0" * 64, results_where(prereg))
    with pytest.raises(ScanPreregistrationError) as exc:
        load_scan_report(write(tmp_path, report))
    assert exc.value.code == "PREREGISTRATION_TAMPERED"


# --------------------------------------------------------------------------- #
# Rosters come from the registration; a resumed scan reuses finished runs
# --------------------------------------------------------------------------- #


def test_config_roster_is_built_from_registered_values(prereg):
    roster = config_roster(prereg, 2, 300, 8)
    assert roster["seed"] == 8
    value = roster["families"][-1]
    assert value["family_id"] == "value_investor" and value["count"] == 2
    assert value["params"] == {**prereg["value_family_params"], "sensitivity_x1000": 300}


def test_config_roster_refuses_a_drifted_base(prereg):
    drifted = {**prereg, "base_roster_id": "roster-0000"}
    with pytest.raises(ScanPreregistrationError) as exc:
        config_roster(drifted, 2, 300, 7)
    assert exc.value.code == "BASE_ROSTER_DRIFT"


def test_a_resumed_scan_reuses_every_finished_run(prereg, sha, tmp_path, monkeypatch):
    """With every point cached, the scan runs nothing and still concludes."""
    results = results_where(prereg, survivor=(6, 500))
    for (c, s, seed), value in results.items():
        cached = SCAN._cache_path(tmp_path, sha, c, s, seed)
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(value), encoding="utf-8")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("a cached point was measured again")

    monkeypatch.setattr(SCAN, "measure_point", forbidden)
    report = SCAN.run_scan(cache_dir=tmp_path, jobs=1)
    assert report["terminal"] == QUALIFIED
    assert report["qualified_configs"] == [{"count": 6, "sensitivity_x1000": 500}]
