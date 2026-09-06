"""AC-303：两轨证据隔离与非正式数据拒绝。

骨架状态：本文件是 `ready-for-development` 前置要求的 strict-xfail 占位（tasks §0）。
每条测试写的是**实现后应当为真**的断言，现在因为 H2 evidence guard 尚不存在而失败；
`strict=True` 保证一旦实现并通过，测试会 XPASS 报错，提醒删掉 xfail 标记。

冻结合同：`docs/experiments/H2-dual-track-contract.json`
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="T908 未实现：H2 evidence guard 尚不存在")
def test_ac303_interactive_and_non_formal_stages_are_rejected_atomically():
    """H1 交互、训练、preview、未知模式一律原子拒绝，不写部分输出。"""
    from market_game_sim.experiment.h2 import evidence_guard

    rejected = (
        ("interactive", "formal"),
        ("ai-mechanism-experiment", "training"),
        ("ai-mechanism-experiment", "preview"),
        ("unknown-mode", "formal"),
    )
    for run_mode, stage in rejected:
        with pytest.raises(evidence_guard.EvidenceRejected):
            evidence_guard.admit(run_mode=run_mode, stage=stage)
    assert evidence_guard.partial_writes() == []


@pytest.mark.xfail(strict=True, reason="T908 未实现：跨轨合并禁令尚未落地")
def test_ac303_cross_track_merge_is_forbidden():
    """两轨 evidence index 不得合并样本量或不确定性。"""
    from market_game_sim.experiment.h2 import evidence_guard

    with pytest.raises(evidence_guard.CrossTrackMerge):
        evidence_guard.merge(["ai-mechanism-experiment", "owner-n-of-1"])


@pytest.mark.xfail(strict=True, reason="T908 未实现：正例准入路径尚不存在")
def test_ac303_frozen_formal_run_is_admitted():
    """反面：绑定冻结协议的正式运行必须被接受，否则门禁只是拒绝一切。"""
    from market_game_sim.experiment.h2 import evidence_guard

    assert evidence_guard.admit(run_mode="ai-mechanism-experiment", stage="formal")
