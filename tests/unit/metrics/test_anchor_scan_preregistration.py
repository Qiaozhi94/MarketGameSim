"""0.4.3 T1109 skeleton（AC-708）：强度扫描的预注册守卫。

strict-xfail 骨架：T1109 实现时替换为真实断言并摘除 xfail。规格见
docs/features/0.4/0.4.3-exogenous-price-anchor/spec.md §6。
"""

import pytest


@pytest.mark.xfail(strict=True, reason="T1109 not implemented yet")
def test_scan_refuses_missing_or_tampered_preregistration():
    """AC-708：预注册文件缺失或哈希不符时 fail closed，一致时放行（正反两侧）"""
    pytest.fail("T1109 pending")
