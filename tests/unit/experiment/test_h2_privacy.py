"""AC-308：隐私边界、阶段可辨识与解盲规则。

骨架状态：本文件是 `ready-for-development` 前置要求的 strict-xfail 占位（tasks §0）。
每条测试写的是**实现后应当为真**的断言，现在因为 H2 会话与交付模块 尚不存在而失败；
`strict=True` 保证一旦实现并通过，测试会 XPASS 报错，提醒删掉 xfail 标记。

冻结合同：`docs/experiments/H2-dual-track-contract.json`
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="T905 未实现：所有者会话与交付包尚不存在")
def test_ac308_delivery_bundle_contains_no_direct_identifiers():
    """成果包只允许出现所有者研究假名。"""
    from market_game_sim.experiment.h2 import delivery

    bundle = delivery.build_owner_bundle()
    assert delivery.scan_for_pii(bundle) == []
    assert bundle.owner_id.startswith("owner-")


@pytest.mark.xfail(strict=True, reason="T905 未实现：阶段标识尚未落地")
def test_ac308_training_and_formal_stages_are_distinguishable():
    """训练与正式阶段必须在 manifest 与界面状态里都能分辨。"""
    from market_game_sim.experiment.h2 import session

    assert session.stage_of(session.start_training()) == "training"
    assert session.stage_of(session.start_formal()) == "formal"


@pytest.mark.xfail(strict=True, reason="T905 未实现：解盲规则尚未落地")
def test_ac308_results_stay_blinded_until_all_formal_scenarios_finish():
    """24 个正式场景全部完成前，任何已完成场景的结果都不可读取。"""
    from market_game_sim.experiment.h2 import session

    with pytest.raises(session.StillBlinded):
        session.read_results(session.owner_progress(completed=23))
    assert session.read_results(session.owner_progress(completed=24)) is not None
