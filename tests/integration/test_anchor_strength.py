"""0.4.3 T1107 skeleton（AC-702）：锚强度参数的 binding 与单调性实测。

strict-xfail 骨架：T1107 实现时替换为真实断言并摘除 xfail。规格见
docs/features/0.4/0.4.3-exogenous-price-anchor/spec.md §6。
"""

import pytest


@pytest.mark.xfail(strict=True, reason="T1107 not implemented yet")
def test_sensitivity_is_binding_and_monotone():
    """AC-702：sensitivity_x1000 binding 且沿价格倍数单调，不满足即 fail closed"""
    pytest.fail("T1107 pending")


@pytest.mark.xfail(strict=True, reason="T1107 not implemented yet")
def test_count_is_monotone():
    """AC-702：count 只做单调性断言（binding 构造上恒真）"""
    pytest.fail("T1107 pending")
