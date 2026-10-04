"""0.4.3 T1108 skeleton（AC-707）：成果门 H2-E4：锚定市场全窗口运行。

strict-xfail 骨架：T1108 实现时替换为真实断言并摘除 xfail。规格见
docs/features/0.4/0.4.3-exogenous-price-anchor/spec.md §6。
"""

import pytest


@pytest.mark.xfail(strict=True, reason="T1108 not implemented yet")
def test_anchored_market_does_not_diverge_and_keeps_trading():
    """AC-707：5700 逻辑秒价格不单调发散、窗口末仍有成交"""
    pytest.fail("T1108 pending")


@pytest.mark.xfail(strict=True, reason="T1108 not implemented yet")
def test_anchored_market_replays_bit_identically():
    """AC-707：同 roster 同种子价格序列逐点一致"""
    pytest.fail("T1108 pending")
