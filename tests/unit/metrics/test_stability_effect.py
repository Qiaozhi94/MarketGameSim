"""0.4.2 T1121/T1131 skeleton（AC-605）。

strict-xfail 骨架：对应任务实现时替换为真实断言并摘除 xfail。规格见
docs/features/0.4/0.4.2-human-perturbation/spec.md §6。
"""

import pytest


@pytest.mark.xfail(strict=True, reason="T1131 not implemented yet")
def test_effect_report_valid_degenerate_and_aborted_pairs():
    """AC-605：
    四指标逐种子差值、效应量与 90% 区间；退化配对与人类臂中止配对列入失效边界；
    有效配对低于下限时效应量缺省
    """
    pytest.fail("T1131 pending")


@pytest.mark.xfail(strict=True, reason="T1121 not implemented yet")
def test_drawdown_and_rise_reset_peak_at_window_start():
    """AC-605：最大回撤/最大涨幅在窗口起点重置峰值（窗口前跌幅不计入，正反两侧）"""
    pytest.fail("T1121 pending")


@pytest.mark.xfail(strict=True, reason="T1131 not implemented yet")
def test_underpowered_flag_when_observed_sd_exceeds_bound():
    """AC-605：实测 σ_d 超出 √2·σ_b 时报告带功效不足标注，未超出时不带"""
    pytest.fail("T1131 pending")
