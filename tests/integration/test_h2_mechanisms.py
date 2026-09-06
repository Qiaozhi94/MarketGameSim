"""AC-306：机制指标到事件链的端到端追溯（集成层）。

骨架状态：本文件是 `ready-for-development` 前置要求的 strict-xfail 占位（tasks §0）。
每条测试写的是**实现后应当为真**的断言，现在因为 H2 运行编排与机制分析 尚不存在而失败；
`strict=True` 保证一旦实现并通过，测试会 XPASS 报错，提醒删掉 xfail 标记。

冻结合同：`docs/experiments/H2-dual-track-contract.json`
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="T913 未实现：H2 运行编排尚不存在")
def test_ac306_every_mechanism_value_traces_back_to_event_ids():
    """每个机制值都能回溯到规范输入与 decision_event_id。"""
    from market_game_sim.experiment.h2 import mechanisms, runner

    table = mechanisms.build_table(runner.run_owner_scenario(scenario=0, stage="preview"))
    assert table
    for row in table:
        assert row.decision_event_id
        assert row.evidence_event_ids


@pytest.mark.xfail(strict=True, reason="T913 未实现：因果链缺失时的拒绝路径尚不存在")
def test_ac306_broken_causal_chain_rejects_the_sample():
    """反面：因果链断裂必须拒绝样本，而不是补猜。"""
    from market_game_sim.experiment.h2 import mechanisms, runner

    run = runner.run_owner_scenario(scenario=0, stage="preview", corrupt_chain=True)
    with pytest.raises(mechanisms.CausalChainBroken):
        mechanisms.build_table(run)
