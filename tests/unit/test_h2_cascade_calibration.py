"""Regression coverage for the H2 liquidation-cascade calibration.

Two things must not silently drift: the family's SESOI must stay tied to a real
measured paired SD (not borrowed from another family), and the two degeneracy
facts -- no observed ``chain_depth >= 1``, liquidations only in the HH cell --
must keep travelling with the number.

The full 256-block calibration takes ~65s, so the tests re-run a small probe and
assert the recorded evidence's structure and conclusions instead.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "h2_cascade_calibration.py"
EVIDENCE = ROOT / "docs" / "experiments" / "H2-cascade-calibration.json"
CONTRACT = ROOT / "docs" / "experiments" / "H2-dual-track-contract.json"

PROBE_SEEDS = 12


def _load_tool():
    spec = importlib.util.spec_from_file_location("h2_cascade_calibration", TOOL)
    assert spec and spec.loader, f"无法加载 {TOOL}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tool():
    return _load_tool()


@pytest.fixture(scope="module")
def recorded() -> dict:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def probe(tool) -> dict:
    """A short live re-run: proves the tool still executes the real market."""
    return tool.build_evidence(PROBE_SEEDS, include_probe=False)


def test_severity_endpoint_has_measured_variance(recorded):
    severity = recorded["severity"]
    assert recorded["paired_blocks"] >= 128
    assert severity["nonzero_paired_blocks"] > 0
    assert severity["paired_sd"] > 0.0
    assert severity["usable_as_primary_estimand"] is True


def test_spec_occurrence_condition_is_unsatisfiable_here(recorded):
    """depth>=1 从未出现，spec 的发生条件恒为假——与另两个家族同型退化。"""
    occurrence = recorded["spec_occurrence"]
    assert occurrence["nonzero_paired_blocks"] == 0
    assert occurrence["paired_difference_is_degenerate"] is True
    assert occurrence["usable_as_primary_estimand"] is False
    assert recorded["observed_chain_depths"] == [0]
    assert recorded["true_cascade_observed"] is False


def test_live_probe_reproduces_the_depth_zero_finding(tool, probe):
    """短程重跑仍必须看到同样的退化事实，否则记录的证据已经过期。"""
    assert probe["observed_chain_depths"] == [0]
    assert probe["true_cascade_observed"] is False
    assert probe["spec_occurrence"]["paired_difference_is_degenerate"] is True


def test_only_the_hh_cell_produces_liquidations(recorded):
    probe = recorded["cell_probe"]
    assert probe["HH"]["runs_with_liquidation"] > 0
    for cell in ("LL", "LH", "HL"):
        assert probe[cell]["runs_with_liquidation"] == 0, (
            f"{cell} 出现强平，场景分布假设已变，必须重跑校准"
        )


def test_sesoi_is_a_quarter_of_the_measured_sd(tool, recorded):
    assert recorded["sesoi"] == pytest.approx(
        recorded["severity"]["paired_sd"] * tool.SESOI_SD_FRACTION
    )
    assert recorded["blocks_required"] == tool.blocks_for(
        recorded["sesoi"], recorded["severity"]["paired_sd"]
    )


def test_contract_absorbed_the_cascade_calibration(recorded):
    """合同必须已经用实测值替换 null，并停止把该家族列为未校准。"""
    track = json.loads(CONTRACT.read_text(encoding="utf-8"))["formal_ai_track"]
    assert track["sesoi_by_family"]["liquidation_cascade"] == pytest.approx(recorded["sesoi"])
    assert track["uncalibrated_families"] == []
    assert track["minimum_blocks"] >= recorded["blocks_required"]
    assert track["cascade_calibration_evidence_id"] == recorded["evidence_id"]
    assert track["cascade_true_propagation_observed"] is False
