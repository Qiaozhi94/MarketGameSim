"""AC-306：机制指标的定义与缺失语义（单元层）。

骨架状态：本文件是 `ready-for-development` 前置要求的 strict-xfail 占位（tasks §0）。
每条测试写的是**实现后应当为真**的断言，现在因为 `experiment/h2/mechanisms.py` 尚不存在而失败；
`strict=True` 保证一旦实现并通过，测试会 XPASS 报错，提醒删掉 xfail 标记。

冻结合同：`docs/experiments/H2-dual-track-contract.json`
"""

from __future__ import annotations

import pytest

MECHANISMS = ("aggressive_orders", "liquidity_withdrawal", "risk_reduction")


@pytest.mark.xfail(strict=True, reason="T913 未实现：experiment/h2/mechanisms.py 尚不存在")
def test_ac306_three_mechanisms_come_from_the_metrics_dictionary():
    """机制口径只能引用指标字典的版本与 ID，不得本地重定义。"""
    from market_game_sim.experiment.h2 import mechanisms

    for name in MECHANISMS:
        spec = mechanisms.definition(name)
        assert spec.dictionary_version
        assert spec.formula_source == "docs/research/metrics-dictionary.md"


@pytest.mark.xfail(strict=True, reason="T913 未实现：缺失语义尚未落地")
def test_ac306_untraceable_value_is_missing_not_imputed():
    """缺少决定事件引用时标记缺失，不推断也不手工补值。"""
    from market_game_sim.experiment.h2 import mechanisms

    value = mechanisms.compute(mechanisms.sample_without_decision_event(), "aggressive_orders")
    assert value.is_missing and value.imputed is False
