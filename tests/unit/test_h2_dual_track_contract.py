"""Regression coverage for the H2 dual-track scope contract."""

from __future__ import annotations

import json
import re
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
REBASELINED_DOCS = ("spec.md", "design.md", "tasks.md")
# 旧的多人真人合同标记。重基线完成后它们只允许作为“已作废”的显式引用出现。
LEGACY_CONTRACT_MARKERS = (
    "Prolific",
    "$22.00",
    "$5,900",
    "$4,100",
    "招募 130",
)
# 把一行标注为作废引用的词；带这些词的行是在**禁止**旧合同，不是在使用它。
RETIREMENT_WORDS = ("作废", "superseded", "SUPERSEDED", "均为零", "不得", "方向重置")


def _live_legacy_lines(text: str) -> list[str]:
    """含旧合同标记、且没有被标注为作废的行——这些才是残留的可执行旧需求。"""
    live = []
    for line in text.splitlines():
        if not any(marker in line for marker in LEGACY_CONTRACT_MARKERS):
            continue
        if any(word in line for word in RETIREMENT_WORDS):
            continue
        live.append(line.strip())
    return live


def test_live_legacy_detector_separates_use_from_retirement():
    """检测器必须有牙，且必须分得清“使用旧合同”和“声明旧合同作废”。"""
    assert _live_legacy_lines("招募平台固定为 Prolific，按 42.8% 费率计算") == [
        "招募平台固定为 Prolific，按 42.8% 费率计算"
    ]
    assert _live_legacy_lines("旧的 Prolific 预算已随方向重置作废，只保留作审计") == []
    assert _live_legacy_lines("干净的重基线文本") == []


def test_no_live_legacy_contract_remains_in_the_milestone():
    """T901 重基线的收口判据：三件套里不得再有可执行的旧真人合同。

    这条原本带一个 draft 豁免分支（旧合同允许作为变更审计输入保留）。重基线完成后豁免
    被删除，改为无条件断言——这正是当初写反向断言要提醒的时刻。
    """
    residue = {}
    for name in REBASELINED_DOCS:
        lines = _live_legacy_lines((MILESTONE / name).read_text(encoding="utf-8"))
        if lines:
            residue[name] = lines
    assert residue == {}, f"三件套仍含可执行的旧真人合同：{residue}"


TESTS_ROOT = ROOT / "tests"
VERIFY_PATH = re.compile(r"`(tests/[^`]+)`")


def _declared_test_paths() -> set[str]:
    """tasks.md 的 verify 段里列出的全部 tests/ 路径。"""
    tasks = (MILESTONE / "tasks.md").read_text(encoding="utf-8")
    return {match.split("::", 1)[0] for match in VERIFY_PATH.findall(tasks)}


def test_declared_verify_paths_all_exist():
    """骨架先行规则的真正执法点。

    `spec_validation._check_ac_references` 只要求"**任一**覆盖任务的 verify 指向真实文件"，
    所以一条 AC 被多个任务覆盖时，漏建其中某个文件门禁不会说话——实测删掉
    tests/integration/test_h2_evidence_guard.py 后生命周期校验仍然通过。这条测试按
    **每一条**声明路径逐个核对，补上那个粒度差。
    """
    declared = _declared_test_paths()
    assert declared, "tasks.md 应至少声明一条 tests/ 路径"
    missing = sorted(path for path in declared if not (ROOT / path).is_file())
    assert missing == [], f"tasks.md 声明了不存在的测试文件：{missing}"
