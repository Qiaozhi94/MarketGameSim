"""0.4.3 T1110 skeleton（AC-705）：锚过强诊断字段。

strict-xfail 骨架：T1110 实现时替换为真实断言并摘除 xfail。规格见
docs/features/0.4/0.4.3-exogenous-price-anchor/spec.md §6。
"""

import pytest


@pytest.mark.xfail(strict=True, reason="T1110 not implemented yet")
def test_diagnostics_are_reported_but_do_not_change_verdict():
    """AC-705：诊断字段在报告顶部呈现，且不改变 SC-701/SC-702 的判定（正反两侧）"""
    pytest.fail("T1110 pending")
