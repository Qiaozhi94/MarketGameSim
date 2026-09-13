"""V032-DOC-005 回归门：incomplete-study 退出路径可达，真实证据有机器入口。

T941 必须允许「24 场完成」或「按冻结停止规则结束并生成 incomplete-study」，否则 gate v1
的 done（要求全部任务完成）与 T944 的 incomplete-study 交付自相矛盾。环境记录与真实
manifest/index 必须有固定布局与校验入口。把任一修复回退时本测试必须变红。
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
