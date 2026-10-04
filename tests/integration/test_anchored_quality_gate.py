"""0.4.3 T1111 skeleton（AC-704）：成果门 H2-E5：达标与未达标两条终点。

strict-xfail 骨架：T1111 实现时替换为真实断言并摘除 xfail。规格见
docs/features/0.4/0.4.3-exogenous-price-anchor/spec.md §6。
"""

import pytest


@pytest.mark.xfail(strict=True, reason="T1111 not implemented yet")
def test_qualified_when_a_preregistered_config_passes():
    """AC-704：存在达标配置时判 QUALIFIED"""
    pytest.fail("T1111 pending")


@pytest.mark.xfail(strict=True, reason="T1111 not implemented yet")
def test_unqualified_with_per_cell_report_when_grid_exhausted():
    """AC-704：网格扫完无达标配置时产出逐格未通过报告并判 UNQUALIFIED"""
    pytest.fail("T1111 pending")


@pytest.mark.xfail(strict=True, reason="T1111 not implemented yet")
def test_no_terminal_verdict_before_scan_completes():
    """AC-704：扫描未完成时不得判任何终点"""
    pytest.fail("T1111 pending")
