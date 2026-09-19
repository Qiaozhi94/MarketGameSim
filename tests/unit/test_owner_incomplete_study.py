"""V032-DOC-005 回归门：证据合同已冻结，且归档的 incomplete-study 机械不得被静默删除。

2026-09-20（ADR-010）：N-of-1 采集轨整体归档，T939—T944 已从 tasks.md 移除（范围裁决，
非未完成）。原先靠「T929 早于 T939/T941」这条任务顺序来保证「证据合同先于真实采集冻结」
的断言随之失效——真实采集不会发生了。本组测试据此改为守两件仍然有效的事：

1. 证据合同（布局/schema/validator）确实已在 T929 冻结并实现；
2. ADR-010 承诺「机械与证据链保留在仓库、受控对照问题出现时可复活」——`validate_owner_evidence.py`、
   `docs/experiments/owner-n-of-1/` 布局与 `INCOMPLETE_STUDY` 独立终态语义必须仍在，
   任何一处被顺手删掉，本组测试必须变红。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MILESTONE = REPO / "docs" / "features" / "0.3" / "0.3.2-web-trading-terminal"
SPEC = (MILESTONE / "spec.md").read_text(encoding="utf-8")
DESIGN = (MILESTONE / "design.md").read_text(encoding="utf-8")
TASKS = (MILESTONE / "tasks.md").read_text(encoding="utf-8")


def _task_block(task_id: str) -> str:
    match = re.search(
        rf"^- \[[ x]\] {task_id}\b.*?(?=^- \[[ x]\] T|\Z)",
        TASKS,
        re.MULTILINE | re.DOTALL,
    )
    assert match, f"tasks.md 找不到任务 {task_id}"
    return match.group(0)


def _task_pos(task_id: str) -> int:
    """任务声明在文档中的位置；`[ ]`/`[x]` 都接受，勾选完成后门禁不得误红。"""
    match = re.search(rf"^- \[[ x]\] {task_id}\b", TASKS, re.MULTILINE)
    assert match, f"tasks.md 找不到任务 {task_id}"
    return match.start()


def test_archived_owner_evidence_machinery_is_retained():
    """ADR-010 的归档承诺：机械保留，不是删除。"""
    assert (REPO / "tools" / "validate_owner_evidence.py").is_file()
    assert "tools/validate_owner_evidence.py" in TASKS
    assert "docs/experiments/owner-n-of-1/" in TASKS
    assert "tools/validate_owner_evidence.py" in DESIGN
    assert "docs/experiments/owner-n-of-1/" in DESIGN
    assert "非退化断言按完成状态条件化" in SPEC


def test_archival_is_declared_as_scope_decision_not_incompletion():
    """归档必须写明是范围裁决；否则「删掉任务」与「偷偷没做」在文档上无法区分。"""
    assert "ADR-010" in TASKS
    assert "不是未完成" in TASKS
    for archived in ("T939", "T941", "T942", "T944"):
        assert not re.search(rf"^- \[[ x]\] {archived}\b", TASKS, re.MULTILINE), (
            f"{archived} 已随 ADR-010 归档，不应作为任务复活"
        )


def test_evidence_contract_frozen_before_real_collection():
    # schema/布局/validator 必须在 T929（真实采集之前）冻结并实现
    task_929 = _task_block("T929")
    assert "证据包布局与 schema" in task_929
    assert "tools/validate_owner_evidence.py" in task_929
    # T929 必须在任何实现任务之前（原「早于真实采集 T939/T941」的顺序断言随采集轨归档失效，
    # 改为守「合同冻结早于 Phase 1 第一项实现任务」这条仍然成立的顺序）
    assert _task_pos("T929") < _task_pos("T930")


def test_incomplete_study_has_distinct_terminal_state():
    assert "FORMAL_RUNNING -> INCOMPLETE_STUDY" in SPEC
    assert "INCOMPLETE_STUDY" in SPEC
    # 提前结束不得再被映射为 COMPLETED
    assert "24 个场景完成或按冻结规则结束" not in SPEC
    assert "不得写成 `COMPLETED`" in SPEC


def test_e1_exit_includes_evidence_contract_freeze():
    e1_rows = [line for line in SPEC.splitlines() if line.startswith("| E1 |")]
    assert e1_rows, "spec 缺 E1 退出条件行"
    assert "证据包布局/schema" in e1_rows[0]
    assert "机器校验入口" in e1_rows[0]
    assert "validator" in e1_rows[0]
