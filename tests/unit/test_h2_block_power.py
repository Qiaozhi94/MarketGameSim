"""Regression coverage for the H2 paired-seed-block power baseline.

The failure this locks down is concrete: the retired human plan's ``130`` was a
*participant* count worth ~936 paired rounds, and it was carried into a contract
whose unit is a single paired block.  These tests assert the replacement basis
and that the recorded evidence file still matches the calculation.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "h2_block_power.py"
EVIDENCE = ROOT / "docs" / "experiments" / "H2-block-power-baseline.json"
CONTRACT = ROOT / "docs" / "experiments" / "H2-dual-track-contract.json"


def _load_tool():
    spec = importlib.util.spec_from_file_location("h2_block_power", TOOL)
    assert spec and spec.loader, f"无法加载 {TOOL}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tool():
    return _load_tool()


def test_recorded_evidence_matches_the_calculation(tool):
    recorded = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert recorded == tool.build_evidence()


def test_130_blocks_do_not_reach_target_power(tool):
    """The retired participant number is under-powered once the unit changes."""
    power = tool.block_power(130, tool.PAIRED_DISCORDANCE)
    assert power < tool.TARGET_POWER
    assert round(power, 3) == 0.709


def test_baseline_minimum_reaches_target_power(tool):
    minimum = tool.minimum_blocks(tool.PAIRED_DISCORDANCE)
    assert minimum == 158
    assert tool.block_power(minimum, tool.PAIRED_DISCORDANCE) >= tool.TARGET_POWER
    assert tool.block_power(minimum - 1, tool.PAIRED_DISCORDANCE) < tool.TARGET_POWER


def test_minimum_grows_with_paired_discordance(tool):
    minimums = [tool.minimum_blocks(q) for q in tool.DISCORDANCE_GRID]
    assert minimums == sorted(minimums)
    assert minimums[0] < minimums[-1], "q 越大所需 block 越多，敏感性表不能是常数"


def test_contract_block_target_is_not_below_the_baseline(tool):
    """合同不得把已废止的 130 或任何低于基线的值当成目标 block 数。"""
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    track = contract["formal_ai_track"]
    baseline = tool.minimum_blocks(tool.PAIRED_DISCORDANCE)
    assert track["minimum_blocks"] >= baseline
    assert track["minimum_blocks"] != tool.SUPERSEDED_PARTICIPANT_CAP
    assert track["block_count_status"] == "provisional_pending_paired_seed_calibration"
    assert track["may_lower_minimum_blocks"] is False
    assert track["power_basis_evidence_id"] == tool.EVIDENCE_ID


def test_superseded_unit_change_is_recorded(tool):
    evidence = tool.build_evidence()
    change = evidence["superseded_unit_change"]
    assert change["old_unit"] == "participant"
    assert change["new_unit"] == "paired_seed_block"
    assert change["old_paired_rounds_implied"] == pytest.approx(936.0)
