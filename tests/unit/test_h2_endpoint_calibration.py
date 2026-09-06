"""Regression coverage for the H2 primary-endpoint calibration.

The failure this locks down: the dual-track contract inherited an *occurrence*
primary estimand whose paired difference is identically zero across v0.1.5's 128
measured blocks.  A degenerate endpoint cannot be rescued by more blocks, so the
contract must not name one as primary, and the calibration must keep saying so.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "h2_endpoint_calibration.py"
EVIDENCE = ROOT / "docs" / "experiments" / "H2-endpoint-calibration.json"
CONTRACT = ROOT / "docs" / "experiments" / "H2-dual-track-contract.json"


def _load_tool():
    spec = importlib.util.spec_from_file_location("h2_endpoint_calibration", TOOL)
    assert spec and spec.loader, f"无法加载 {TOOL}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tool():
    return _load_tool()


@pytest.fixture(scope="module")
def evidence(tool) -> dict:
    return tool.build_evidence()


def test_recorded_evidence_matches_the_calculation(tool, evidence):
    assert json.loads(EVIDENCE.read_text(encoding="utf-8")) == evidence


def test_occurrence_endpoint_is_measured_degenerate(evidence):
    occurrence = evidence["occurrence_endpoint"]
    assert occurrence["hypotheses"] > 0
    assert occurrence["hypotheses_with_any_nonzero_block"] == 0
    assert occurrence["total_nonzero_blocks"] == 0
    assert occurrence["paired_difference_is_degenerate"] is True
    assert occurrence["usable_as_primary_estimand"] is False


def test_severity_endpoint_has_variance_on_every_hypothesis(evidence):
    severity = evidence["severity_endpoint"]
    assert severity["hypotheses_with_any_nonzero_block"] == severity["hypotheses"]
    assert severity["min_nonzero_blocks"] > 0
    assert severity["usable_as_primary_estimand"] is True
    assert severity["median_implied_paired_sd"] > 0.0


def test_more_blocks_never_rescue_a_zero_variance_endpoint(tool):
    """零方差终点的所需 block 数是无穷：这条断言把「加样本量就行」的直觉钉死。"""
    with pytest.raises(ZeroDivisionError):
        tool.blocks_for(0.0, tool.median([1.0, 1.0]))
    assert tool.mde_at(158, 0.0) == 0.0, "零方差下 MDE 退化为 0，检验没有任何分辨力"


def test_block_requirement_falls_as_sesoi_grows(evidence):
    table = evidence["severity_endpoint"]["blocks_by_candidate_sesoi"]
    ordered = sorted(table.values(), key=lambda cell: cell["sesoi"])
    blocks = [cell["blocks"] for cell in ordered]
    assert blocks == sorted(blocks, reverse=True)
    assert blocks[-1] < blocks[0], "SESOI 越大所需 block 越少，表不能是常数"


def test_mde_at_the_contract_minimum_is_a_fraction_of_a_sd(evidence):
    severity = evidence["severity_endpoint"]
    mde = severity["minimum_detectable_effect"]["158"]
    assert mde / severity["median_implied_paired_sd"] < 0.5, (
        "合同下限 158 应能检测半个 SD 以内的效应，否则严重程度终点也需重新规划"
    )


def test_contract_primary_estimand_is_severity_not_occurrence():
    """合同必须已经吸收本校准：occurrence 不得再是主要 estimand。"""
    track = json.loads(CONTRACT.read_text(encoding="utf-8"))["formal_ai_track"]
    assert track["primary_estimand"] == "severity_paired_difference"
    assert track["occurrence_role"] == "descriptive_secondary"
    assert track["primary_estimand_calibration_evidence_id"] == "H2-endpoint-calibration-v1"
    assert track["degenerate_primary_estimand_forbidden"] is True
    assert "sesoi" not in track, "旧的 0.125 风险差 SESOI 必须随终点变更一并移除"


def test_frozen_sesoi_matches_the_measured_quarter_sd_scale(tool, evidence):
    """owner 选的是 0.25 SD 一档；冻结值必须等于校准算出的那个数，不能手抄近似。"""
    track = json.loads(CONTRACT.read_text(encoding="utf-8"))["formal_ai_track"]
    quarter = evidence["severity_endpoint"]["blocks_by_candidate_sesoi"]["0.25sd"]
    assert (
        track["measured_median_paired_sd"]
        == (evidence["severity_endpoint"]["median_implied_paired_sd"])
    )
    for family in ("price_crash", "liquidity_dry_up"):
        assert track["sesoi_by_family"][family] == quarter["sesoi"]
    assert track["minimum_blocks"] == quarter["blocks"]


def test_uncalibrated_family_has_no_borrowed_sesoi(tool):
    """v0.1.5 没有强平连锁的对应证据，它的 SESOI 不得借用另两个家族的值。"""
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    track = contract["formal_ai_track"]
    families = contract["shared_constraints"]["outcome_families"]
    by_family = track["sesoi_by_family"]
    assert set(by_family) == set(families), "每个结果家族都必须在 SESOI 表里有条目"

    uncalibrated = track["uncalibrated_families"]
    assert uncalibrated, "校准只覆盖两个家族，未覆盖的必须显式列出"
    calibrated_values = {value for family, value in by_family.items() if family not in uncalibrated}
    for family in uncalibrated:
        assert by_family[family] is None, f"{family} 未校准，SESOI 必须为 null"
        assert by_family[family] not in calibrated_values
