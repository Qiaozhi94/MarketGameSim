"""0.4.3 T1106 skeleton（AC-702）：value_investor 族的响应函数与参数校验。

strict-xfail 骨架：T1106 实现时替换为真实断言并摘除 xfail。规格见
docs/features/0.4/0.4.3-exogenous-price-anchor/spec.md §6。
"""

import pytest


@pytest.mark.xfail(strict=True, reason="T1106 not implemented yet")
def test_target_position_opposes_deviation_and_is_monotone():
    """AC-702：目标仓位方向与偏离相反、幅度随偏离单调不减、以仓位上限封顶（正反两侧）"""
    pytest.fail("T1106 pending")
