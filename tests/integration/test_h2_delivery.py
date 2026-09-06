"""AC-307：从冻结 evidence index 单命令重建交付包。

骨架状态：本文件是 `ready-for-development` 前置要求的 strict-xfail 占位（tasks §0）。
每条测试写的是**实现后应当为真**的断言，现在因为 H2 交付入口 尚不存在而失败；
`strict=True` 保证一旦实现并通过，测试会 XPASS 报错，提醒删掉 xfail 标记。

冻结合同：`docs/experiments/H2-dual-track-contract.json`
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="T920/T921 未实现：H2 交付入口尚不存在")
def test_ac307_bundle_rebuilds_from_the_index_only():
    """新进程只读 evidence index 即可重建，机器结果内容哈希一致。"""
    from market_game_sim.experiment.h2 import delivery

    first = delivery.build_from_index(delivery.frozen_index_path())
    second = delivery.build_from_index(delivery.frozen_index_path())
    assert first.machine_results_sha256 == second.machine_results_sha256


@pytest.mark.xfail(strict=True, reason="T921 未实现：结论语法检查尚不存在")
def test_ac307_conclusion_syntax_forbids_the_human_effect_shorthand():
    """结论必须带三限定词，且禁用人类效应这一简称。"""
    from market_game_sim.experiment.h2 import delivery

    report = delivery.build_from_index(delivery.frozen_index_path()).report_text
    assert "人类效应" not in report
    for qualifier in ("模型族", "参数范围", "seed 分布"):
        assert qualifier in report


@pytest.mark.xfail(strict=True, reason="T921 未实现：轨道标注尚不存在")
def test_ac307_owner_track_results_are_marked_descriptive():
    """所有者轨交付包是 experiment-preview 且标注描述性。"""
    from market_game_sim.experiment.h2 import delivery

    bundle = delivery.build_owner_bundle()
    assert bundle.evidence_class == "experiment-preview"
    assert bundle.marked_descriptive is True
