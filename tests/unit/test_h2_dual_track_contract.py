"""Regression coverage for the H2 dual-track scope contract."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs" / "experiments" / "H2-dual-track-contract.json"


def _contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_h2_formal_ai_track_uses_paired_seed_blocks_not_ai_identities():
    contract = _contract()
    track = contract["formal_ai_track"]
    assert track["experimental_unit"] == "paired_seed_block"
    assert track["required_runs_per_block"] == 2
    assert track["human_population_inference_allowed"] is False
    # 旧真人计划的 130 是参与者数（约 936 个配对局），换单位后不得原样沿用。
    assert "target_blocks" not in track, "固定 target_blocks 已被下限 + 校准状态取代"
    assert track["minimum_blocks"] == 168
    assert track["block_count_status"] == "frozen_for_all_three_families"
    assert track["may_lower_minimum_blocks"] is False


def test_h2_owner_track_is_single_person_and_cannot_support_population_claims():
    contract = _contract()
    track = contract["owner_n_of_1_track"]
    assert track["human_participants"] == 1
    assert track["training_blocks"] == 6
    assert track["formal_paired_blocks"] == 24
    assert track["schedule"]["days"] * track["schedule"]["formal_blocks_per_day"] == 24
    assert track["human_population_inference_allowed"] is False


def test_h2_only_the_ai_track_may_carry_a_research_claim():
    """SOP §2 把样本量 1、有学习效应的运行排除在统计之外，n-of-1 不得建立研究声明。"""
    contract = _contract()
    assert contract["formal_ai_track"]["evidence_class"] == "formal-research"
    assert contract["formal_ai_track"]["research_claim_eligible"] is True
    owner = contract["owner_n_of_1_track"]
    assert owner["evidence_class"] == "experiment-preview"
    assert owner["research_claim_eligible"] is False
    assert owner["research_claim_exclusion_reason"]


def test_h2_owner_track_declares_experimenter_bias_and_unblinding_rule():
    """所有者同时是设计者与被试，这条偏倚只能声明，不能靠冻结 seed 消除。"""
    owner = _contract()["owner_n_of_1_track"]
    assert "experimenter and subject" in owner["known_uncontrollable_bias"]
    assert "24 formal blocks" in owner["unblinding_rule"]


def test_h2_external_recruitment_and_compensation_are_zero_and_tracks_are_isolated():
    contract = _contract()
    shared = contract["shared_constraints"]
    assert shared["external_human_recruitment"] == 0
    assert shared["participant_compensation_usd"] == 0
    assert shared["recruitment_platform"] is None
    assert shared["evidence_indices_must_be_separate"] is True
    assert shared["h1_free_play_is_formal_evidence"] is False


MILESTONE = ROOT / "docs" / "features" / "0.3" / "0.3.1-human-in-the-loop-experiment"
LEGACY_CONTRACT_MARKERS = (
    "Prolific",
    "$22.00",
    "$5,900",
    "$4,100",
    "招募 130",
)


def _milestone_status() -> str:
    text = (MILESTONE / "spec.md").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("status:"):
            return line.split(":", 1)[1].strip()
    raise AssertionError("0.3.1 spec 缺 frontmatter status")


def _legacy_markers_in(text: str) -> list[str]:
    return [marker for marker in LEGACY_CONTRACT_MARKERS if marker in text]


def test_legacy_marker_detector_actually_detects():
    """检测函数本身必须有牙：没有这条，下面的门禁可能永远返回空列表。"""
    assert _legacy_markers_in("招募平台固定为 Prolific") == ["Prolific"]
    assert _legacy_markers_in("干净的重基线文本") == []


def test_scope_reset_gate_blocks_promotion_while_legacy_contract_remains():
    """方向重置门不能只是散文：status 一旦离开 draft，旧真人合同必须已被逐项重基线。"""
    status = _milestone_status()
    found: list[str] = []
    for name in ("spec.md", "design.md"):
        found.extend(_legacy_markers_in((MILESTONE / name).read_text(encoding="utf-8")))
    if status != "draft":
        assert found == [], (
            f"0.3.1 status={status} 但 spec/design 仍含旧真人合同标记 {sorted(set(found))}；"
            "推进前必须按 H2-dual-track-contract 逐项重基线"
        )
    else:
        # draft 期间旧合同允许作为变更审计输入保留。这条反向断言保证：一旦真的清理干净，
        # 本豁免会失败并提醒把门禁改成无条件断言，而不是被无声遗忘。
        assert found, "spec/design 已无旧合同标记，请删除本 draft 豁免分支，改为无条件断言"
