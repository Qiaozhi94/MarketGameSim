"""AC-301：H2 协议冻结与漂移拒绝。

骨架状态：本文件是 `ready-for-development` 前置要求的 strict-xfail 占位（tasks §0）。
每条测试写的是**实现后应当为真**的断言，现在因为 `experiment/h2/protocol.py` 尚不存在而失败；
`strict=True` 保证一旦实现并通过，测试会 XPASS 报错，提醒删掉 xfail 标记。

冻结合同：`docs/experiments/H2-dual-track-contract.json`
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="T904 未实现：experiment/h2/protocol.py 尚不存在")
def test_ac301_incomplete_protocol_cannot_freeze():
    """缺任一冻结项的协议不得产生哈希。"""
    from market_game_sim.experiment.h2 import protocol

    draft = protocol.draft_from_contract()
    del draft["sesoi_by_family"]
    with pytest.raises(protocol.ProtocolIncomplete):
        protocol.freeze(draft)


@pytest.mark.xfail(strict=True, reason="T904 未实现：experiment/h2/protocol.py 尚不存在")
def test_ac301_complete_protocol_freezes_and_is_content_addressed():
    """完整协议可冻结；内容变化产生新哈希，旧 assignment 不可复用。"""
    from market_game_sim.experiment.h2 import protocol

    frozen = protocol.freeze(protocol.draft_from_contract())
    assert frozen.protocol_hash
    drifted = protocol.freeze(protocol.draft_from_contract(minimum_blocks=200))
    assert drifted.protocol_hash != frozen.protocol_hash
    assert not protocol.accepts_assignment(drifted, issued_under=frozen.protocol_hash)


@pytest.mark.xfail(strict=True, reason="T904 未实现：control_arm 枚举尚未落地")
def test_ac301_control_arm_enum_is_the_single_source():
    """CLI 与协议 schema 共用同一个 control_arm 闭集（DQ-302）。"""
    from market_game_sim.experiment.h2 import protocol

    assert protocol.CONTROL_ARMS == ("linear", "threshold", "owner")
