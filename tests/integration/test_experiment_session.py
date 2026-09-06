"""AC-302：所有者正式会话的有限窗口与无特权控制。

骨架状态：本文件是 `ready-for-development` 前置要求的 strict-xfail 占位（tasks §0）。
每条测试写的是**实现后应当为真**的断言，现在因为 H2 会话控制器 尚不存在而失败；
`strict=True` 保证一旦实现并通过，测试会 XPASS 报错，提醒删掉 xfail 标记。

冻结合同：`docs/experiments/H2-dual-track-contract.json`
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="T910 未实现：H2 会话控制器尚不存在")
def test_ac302_window_accepts_exactly_one_action_and_rejects_late_input():
    """每个窗口至多一次最终动作；迟到输入稳定返回 WINDOW_CLOSED。"""
    from market_game_sim.experiment.h2 import session

    window = session.open_window(index=0)
    assert session.submit(window, session.sample_order()) is session.ACCEPTED
    assert session.submit(window, session.sample_order()) is session.WINDOW_CLOSED
    session.close(window)
    assert session.submit(window, session.sample_order()) is session.WINDOW_CLOSED


@pytest.mark.xfail(strict=True, reason="T910 未实现：NO_ACTION 路径尚不存在")
def test_ac302_timeout_writes_no_action_without_wall_clock_wait():
    """窗口超时写预定义 NO_ACTION，市场不等待墙钟补录。"""
    from market_game_sim.experiment.h2 import session

    window = session.open_window(index=1)
    session.close(window)
    assert session.recorded_decision(window) == "NO_ACTION"


def test_ac302_formal_client_exposes_no_pause_step_or_reparameterisation():
    """正式客户端不得暴露暂停、单步、改参或未来信息。

    控制项闭集已由 T905 落地（`session.formal_client_controls`），故摘除 xfail；
    UI 层怎么渲染这个闭集仍属 T911。
    """
    from market_game_sim.experiment.h2 import session

    controls = session.formal_client_controls()
    for forbidden in ("pause", "step", "set_param", "reveal_future"):
        assert forbidden not in controls
