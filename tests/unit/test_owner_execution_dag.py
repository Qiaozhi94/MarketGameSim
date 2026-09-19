"""V032-DOC-004 回归门：0.3.2 执行 DAG 必须 fork/join 且成果门认领 preview 门控。

T929 之后 T930/T931 并行、T932 汇合；T936 成果门之后交付 T938；H2-D1 成果门 T936 必须
显式引用 AC-403。把 DAG 改回串行、或让成果门漏掉门控验收时，本测试必须变红。

2026-09-20（ADR-010）：原断言 ``T938 -> T939`` 随 N-of-1 采集轨归档失效——T939（6 个
训练场景）已从 tasks.md 移除，是范围裁决而非未完成。改为断言 ``T936 -> T938``，并新增
负向断言锁住「归档轨不得无声复活」：DAG 中不应再出现指向 T939—T944 的边。
"""

from __future__ import annotations

import re
from pathlib import Path

TASKS = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "features"
    / "0.3"
    / "0.3.2-web-trading-terminal"
    / "tasks.md"
).read_text(encoding="utf-8")


def _task_block(task_id: str) -> str:
    match = re.search(
        rf"^- \[[ x]\] {task_id}\b.*?(?=^- \[[ x]\] T|\Z)",
        TASKS,
        re.MULTILINE | re.DOTALL,
    )
    assert match, f"tasks.md 找不到任务 {task_id}"
    return match.group(0)


def test_execution_dag_forks_and_gate_claims_preview_ac():
    assert "T929 -> T930 [P]" in TASKS
    assert "T929 -> T931 [P]" in TASKS
    assert "T930, T931 -> T932" in TASKS
    assert "T936 -> T938" in TASKS
    # ADR-010：已归档的 N-of-1 采集任务不得无声回到执行 DAG
    for archived in ("T937", "T939", "T940", "T941", "T942", "T943", "T944", "T946"):
        assert f"-> {archived}" not in TASKS, f"{archived} 已随 ADR-010 归档，不应回到 DAG"
    # 不得同时声明串行链与并行
    assert "T929 -> T930 -> T931 -> T932" not in TASKS
    # H2-D1 成果门必须显式认领 preview fail-closed 的 AC-403
    assert "AC-403" in _task_block("T936")
