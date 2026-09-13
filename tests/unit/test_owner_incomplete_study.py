"""V032-DOC-005 回归门：证据合同先于真实采集冻结，incomplete-study 有独立终态。

三组合同，任一被回退本组测试必须变红：
1. incomplete-study 出口可达（T941 允许 24 场完成或按冻结停止规则结束）；
2. schema/布局/validator 在 T929 先于任何真实采集冻结/实现，T942 只做采集后 index freeze；
3. spec 生命周期为 incomplete-study 保留独立终态，且不把提前结束写成 COMPLETED。
"""

from __future__ import annotations

import re
from pathlib import Path

MILESTONE = (
    Path(__file__).resolve().parents[2] / "docs" / "features" / "0.3" / "0.3.2-web-trading-terminal"
)
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


def test_incomplete_study_path_reachable_and_evidence_located():
    task_941 = _task_block("T941")
    assert "冻结停止规则" in task_941
    assert "incomplete-study" in task_941
    assert "tools/validate_owner_evidence.py" in TASKS
    assert "docs/experiments/owner-n-of-1/" in TASKS
    assert "tools/validate_owner_evidence.py" in DESIGN
    assert "docs/experiments/owner-n-of-1/" in DESIGN
    assert "非退化断言按完成状态条件化" in SPEC
    task_944 = _task_block("T944")
    assert "按实际样本数断言非退化" in task_944
    assert "零样本" in task_944


def test_evidence_contract_frozen_before_real_collection():
    # schema/布局/validator 必须在 T929（真实采集之前）冻结并实现
    task_929 = _task_block("T929")
    assert "证据包布局与 schema" in task_929
    assert "tools/validate_owner_evidence.py" in task_929
    # 采集后的 T942 只做 index freeze，不得再定义格式或实现 validator
    task_942 = _task_block("T942")
    assert "采集后" in task_942
    assert "实现机器校验入口" not in task_942
    # 顺序：冻结/实现所在任务必须早于真实采集任务 T939/T941（勾选状态无关）
    assert _task_pos("T929") < _task_pos("T939")
    assert _task_pos("T929") < _task_pos("T941")


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
