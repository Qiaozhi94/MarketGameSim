"""0.4.1 T961 (FR-505 / DR-502 / AC-504 / AC-505): MarketQualityReport schema.

Locks the frozen judging rules (thresholds, own family-A instance, Q-505
combination, Q-501 window) and the validator's fail-closed behaviour: a
tampered hash, missing/extra keys, a moved threshold, a flipped verdict or a
failure dropped from ``failed[]`` must all be rejected with a stable code.
"""

from __future__ import annotations

import copy
import json

import pytest

from market_game_sim.metrics import market_quality as mq
from market_game_sim.metrics import validation
from market_game_sim.metrics.market_quality import (
    FAIL,
    NOT_APPLICABLE,
    PASS,
    MarketQualityError,
    StylizedFactResult,
    build_report,
    combine_volatility_clustering,
    load_report,
    parse_report,
    save_report,
)

GOOD_QUALITY = {
    "trades_per_minute": 45.0,
    "two_sided_book_uptime": 0.995,
    "median_book_levels_per_side": 6.0,
    "median_effective_spread_bp": 12.0,
    "fill_to_order_ratio": 0.004,
    "wall_seconds_per_logical_second": 0.3,
}


def _facts(**overrides: StylizedFactResult) -> dict[str, StylizedFactResult]:
    facts = {
        mq.FAT_TAILS: StylizedFactResult(PASS, 4.2, 0.001),
        mq.RETURN_AUTOCORRELATION: StylizedFactResult(PASS, 0.01, None),
        mq.VOLATILITY_CLUSTERING: StylizedFactResult(PASS, 0.2, 0.002),
        mq.VOLUME_VOLATILITY_CORRELATION: StylizedFactResult(PASS, 0.3, 0.003),
        mq.ORDER_FLOW_LONG_MEMORY: StylizedFactResult(PASS, -0.4, 0.004),
    }
    facts.update(overrides)
    return facts


def _report(quality=None, facts=None, window_start=5_000_000_000):
    return build_report(
        run_id="run-1",
        roster_id="roster-abc",
        logical_seconds=600.0,
        window_start_logical_ns=window_start,
        quality=GOOD_QUALITY if quality is None else quality,
        stylized_facts=_facts() if facts is None else facts,
    )


def _payload(**kw) -> dict:
    return json.loads(_report(**kw).to_json())


def _code(payload) -> str:
    with pytest.raises(MarketQualityError) as exc:
        parse_report(payload)
    return exc.value.code


# --------------------------------------------------------------------------- #
# Frozen rules
# --------------------------------------------------------------------------- #


def test_quality_thresholds_match_spec_sc501() -> None:
    assert dict(mq.QUALITY_THRESHOLDS) == {
        "trades_per_minute": ("min", 30.0),
        "two_sided_book_uptime": ("min", 0.99),
        "median_book_levels_per_side": ("min", 5.0),
        "median_effective_spread_bp": ("max", 20.0),
        "fill_to_order_ratio": ("min", 0.001),
        "wall_seconds_per_logical_second": ("max", 0.5),
    }
    assert mq.STYLIZED_MIN_PASS == 3
    assert mq.ALPHA == validation.ALPHA
    assert mq.VOLUME_VOLATILITY_WINDOW == validation.VOL_WINDOW


def test_own_family_a_is_separate_from_kpi005_family() -> None:
    # KPI-005 group A must stay exactly the 0.1.2 protocol's members (AC-505 guard).
    assert validation._FAMILY_A == (
        "fat_tails",
        "volatility_clustering",
        "price_impact_nonlinearity",
        "spread_depth_regime",
    )
    assert mq.STYLIZED_FAMILY_A == (
        "fat_tails",
        "volatility_clustering",
        "volume_volatility_correlation",
        "order_flow_long_memory",
    )
    assert mq.STYLIZED_FAMILY_A is not validation._FAMILY_A
    assert mq.RETURN_AUTOCORRELATION not in mq.STYLIZED_FAMILY_A


def test_boundary_values_pass_and_just_outside_fails() -> None:
    at = {k: v for k, (_, v) in mq.QUALITY_THRESHOLDS.items()}
    assert set(_report(quality=at).verdicts["quality"].values()) == {PASS}
    outside = dict(at)
    outside["trades_per_minute"] = 29.999
    outside["median_effective_spread_bp"] = 20.001
    q = _report(quality=outside).verdicts["quality"]
    assert q["trades_per_minute"] == FAIL
    assert q["median_effective_spread_bp"] == FAIL


# --------------------------------------------------------------------------- #
# Q-505: volatility clustering needs lag 1 and lag 50
# --------------------------------------------------------------------------- #


def test_volatility_clustering_both_lags_significant_passes_with_max_p() -> None:
    r = combine_volatility_clustering(0.3, 0.001, 0.1, 0.02)
    assert r.raw_verdict == PASS
    assert r.p_value == 0.02


@pytest.mark.parametrize(
    "args",
    [
        (0.3, 0.001, 0.1, 0.2),  # lag 50 not significant
        (0.3, 0.2, 0.1, 0.001),  # lag 1 not significant
        (0.3, 0.001, -0.1, 0.001),  # lag 50 negative
    ],
)
def test_volatility_clustering_one_lag_failing_fails(args) -> None:
    r = combine_volatility_clustering(*args)
    assert r.raw_verdict == FAIL
    assert r.p_value == max(args[1], args[3])


def test_volatility_clustering_missing_lag_not_applicable() -> None:
    r = combine_volatility_clustering(0.3, 0.001, None, None)
    assert r.raw_verdict == NOT_APPLICABLE
    assert r.p_value is None


# --------------------------------------------------------------------------- #
# Verdicts and failed[]
# --------------------------------------------------------------------------- #


def test_all_pass_report_has_empty_failed() -> None:
    report = _report()
    assert report.verdicts[mq.SC_501] == PASS
    assert report.verdicts[mq.SC_502] == PASS
    assert report.failed == []
    assert parse_report(json.loads(report.to_json())) == report


def test_multiple_failures_are_all_listed_at_top_level() -> None:
    quality = dict(GOOD_QUALITY, trades_per_minute=2.0, two_sided_book_uptime=0.4)
    quality["median_effective_spread_bp"] = None  # not measurable -> NOT_APPLICABLE
    facts = _facts(
        **{
            mq.FAT_TAILS: StylizedFactResult(FAIL, -0.1, 0.7),
            mq.ORDER_FLOW_LONG_MEMORY: StylizedFactResult(NOT_APPLICABLE, None, None),
            mq.VOLUME_VOLATILITY_CORRELATION: StylizedFactResult(FAIL, 0.0, 0.5),
        }
    )
    report = _report(quality=quality, facts=facts)
    assert report.verdicts["quality"]["median_effective_spread_bp"] == NOT_APPLICABLE
    assert report.failed == [
        mq.SC_501,
        mq.SC_502,
        "quality.trades_per_minute",
        "quality.two_sided_book_uptime",
        "quality.median_effective_spread_bp",
        "stylized_facts.fat_tails",
        "stylized_facts.volume_volatility_correlation",
        "stylized_facts.order_flow_long_memory",
    ]
    assert parse_report(json.loads(report.to_json())) == report


def test_three_of_five_stylized_facts_meets_sc502_but_misses_are_visible() -> None:
    facts = _facts(
        **{
            mq.FAT_TAILS: StylizedFactResult(FAIL, 0.1, 0.4),
            mq.ORDER_FLOW_LONG_MEMORY: StylizedFactResult(FAIL, 0.1, 0.4),
        }
    )
    report = _report(facts=facts)
    assert report.verdicts[mq.SC_502] == PASS
    assert report.failed == ["stylized_facts.fat_tails", "stylized_facts.order_flow_long_memory"]


def test_family_a_correction_downgrades_raw_pass() -> None:
    # Each p=0.04 passes raw alpha, but Holm over the 4-member family starts at
    # 0.05/4 = 0.0125, so every member is downgraded.
    facts = _facts(
        **{
            mq.FAT_TAILS: StylizedFactResult(PASS, 1.0, 0.04),
            mq.VOLATILITY_CLUSTERING: StylizedFactResult(PASS, 1.0, 0.04),
            mq.VOLUME_VOLATILITY_CORRELATION: StylizedFactResult(PASS, 1.0, 0.04),
            mq.ORDER_FLOW_LONG_MEMORY: StylizedFactResult(PASS, 1.0, 0.04),
        }
    )
    s = _report(facts=facts).verdicts["stylized_facts"]
    assert [s[k] for k in mq.STYLIZED_FAMILY_A] == [FAIL] * 4
    # Group-B fact 2 is outside family A and passes through unchanged.
    assert s[mq.RETURN_AUTOCORRELATION] == PASS


def test_no_window_marks_everything_not_applicable() -> None:
    report = _report(window_start=None)
    assert report.verdicts[mq.SC_501] == NOT_APPLICABLE
    assert set(report.verdicts["quality"].values()) == {NOT_APPLICABLE}
    assert report.failed[0] == mq.WINDOW
    assert len(report.failed) == 1 + 2 + 6 + 5
    assert parse_report(json.loads(report.to_json())) == report


# --------------------------------------------------------------------------- #
# Validator: fail closed with stable codes
# --------------------------------------------------------------------------- #


def test_tampered_hash_rejected() -> None:
    p = _payload()
    p["content_hash"] = "0" * 32
    assert _code(p) == "HASH_MISMATCH"


def test_tampered_measurement_rejected_by_hash() -> None:
    p = _payload()
    p["logical_seconds"] = 601.0
    assert _code(p) == "HASH_MISMATCH"


def test_dropping_a_failure_from_failed_rejected() -> None:
    p = _payload(quality=dict(GOOD_QUALITY, trades_per_minute=1.0))
    assert "quality.trades_per_minute" in p["failed"]
    p["failed"] = [f for f in p["failed"] if f != "quality.trades_per_minute"]
    assert _code(p) == "FAILED_MISMATCH"


def test_flipped_verdict_rejected() -> None:
    p = _payload(quality=dict(GOOD_QUALITY, trades_per_minute=1.0))
    p["verdicts"]["quality"]["trades_per_minute"] = PASS
    assert _code(p) == "VERDICT_MISMATCH"


def test_moved_threshold_rejected() -> None:
    p = _payload()
    p["thresholds"]["quality"]["trades_per_minute"]["value"] = 1.0
    assert _code(p) == "THRESHOLD_MISMATCH"


@pytest.mark.parametrize(
    "path",
    [("run_id",), ("content_hash",), ("quality", "fill_to_order_ratio"), ("failed",)],
)
def test_missing_key_rejected(path) -> None:
    p = _payload()
    target = p
    for key in path[:-1]:
        target = target[key]
    del target[path[-1]]
    assert _code(p) == "MISSING_FIELD"


@pytest.mark.parametrize("where", [(), ("quality",), ("stylized_facts", "fat_tails")])
def test_extra_key_rejected(where) -> None:
    p = _payload()
    target = p
    for key in where:
        target = target[key]
    target["surprise"] = 1
    assert _code(p) == "UNKNOWN_FIELD"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.__setitem__("schema_version", 2),
        lambda p: p["quality"].__setitem__("trades_per_minute", "fast"),
        lambda p: p["stylized_facts"]["fat_tails"].__setitem__("raw_verdict", "MAYBE"),
        lambda p: p["stylized_facts"]["fat_tails"].__setitem__("p_value", None),
        lambda p: p.__setitem__("window_start_logical_ns", -1),
        lambda p: p.__setitem__("logical_seconds", 0),
    ],
)
def test_invalid_values_rejected(mutate) -> None:
    p = _payload()
    mutate(p)
    assert _code(p) in {"INVALID_VALUE", "UNKNOWN_SCHEMA_VERSION"}


def test_build_rejects_missing_fact() -> None:
    facts = _facts()
    del facts[mq.ORDER_FLOW_LONG_MEMORY]
    with pytest.raises(MarketQualityError) as exc:
        _report(facts=facts)
    assert exc.value.code == "MISSING_FIELD"


def test_save_load_roundtrip_and_cli(tmp_path, capsys) -> None:
    report = _report(quality=dict(GOOD_QUALITY, fill_to_order_ratio=0.0002))
    path = save_report(report, tmp_path)
    assert load_report(path) == report
    assert mq.main([str(path)]) == 0
    assert "quality.fill_to_order_ratio" in capsys.readouterr().out

    bad = copy.deepcopy(json.loads(path.read_text(encoding="utf-8")))
    bad["failed"] = []
    bad_path = tmp_path / "bad.quality.json"
    bad_path.write_text(json.dumps(bad), encoding="utf-8")
    assert mq.main([str(path), str(bad_path)]) == 1
    assert "FAILED_MISMATCH" in capsys.readouterr().err

    with pytest.raises(MarketQualityError) as exc:
        load_report(tmp_path / "absent.json")
    assert exc.value.code == "REPORT_NOT_FOUND"
