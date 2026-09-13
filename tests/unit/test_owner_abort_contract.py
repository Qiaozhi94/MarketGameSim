"""V032-DOC-003 回归门：Web abort 只表达 owner 主动中止。

`TECHNICAL_ABORT` 只能由服务端故障路径内部生成，客户端不得提交该分类（否则用户可选择
是否消耗备用池，破坏结果盲裁决）。恢复「客户端可选 technical」的旧措辞时本测试必须变红。
"""

from __future__ import annotations

from pathlib import Path

MILESTONE = (
    Path(__file__).resolve().parents[2] / "docs" / "features" / "0.3" / "0.3.2-web-trading-terminal"
)
DESIGN = (MILESTONE / "design.md").read_text(encoding="utf-8")
SPEC = (MILESTONE / "spec.md").read_text(encoding="utf-8")


def test_web_abort_is_owner_initiated_only():
    assert "只表达 owner 主动中止" in DESIGN
    assert "Web 请求不得提交该分类" in DESIGN
    assert "客户端不得提交" in SPEC
    assert "客户端只能触发 owner 主动中止" in SPEC
    # 旧合同：客户端可选择会消耗备用池的 technical 分类，必须已删除
    assert "`abort_kind=technical` 才走冻结" not in DESIGN
