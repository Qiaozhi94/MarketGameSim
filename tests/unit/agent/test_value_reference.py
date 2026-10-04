"""0.4.3 T1105 skeleton（AC-701 / AC-706）：恒定价值参照 v_t 的派生与可见性。

strict-xfail 骨架：T1105 实现时替换为真实断言并摘除 xfail。规格见
docs/features/0.4/0.4.3-exogenous-price-anchor/spec.md §6。
"""

import pytest


@pytest.mark.xfail(strict=True, reason="T1105 not implemented yet")
def test_v_t_is_derived_from_initial_price_and_never_moves():
    """AC-701：v_t ≡ engine.initial_price_ticks，窗口内收益恒为 0（正反两侧）"""
    pytest.fail("T1105 pending")


@pytest.mark.xfail(strict=True, reason="T1105 not implemented yet")
def test_v_t_reaches_only_value_investor_private_params():
    """AC-706：只在价值族 strategy_private 中；其他族、分级信息集、人类载荷不含。

    同时断言 PROTOCOL_VERSION 仍为 1。
    """
    pytest.fail("T1105 pending")
