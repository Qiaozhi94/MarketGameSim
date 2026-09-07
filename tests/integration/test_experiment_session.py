"""AC-302：所有者正式会话的有限窗口与无特权控制。

T910/T911 已实现，xfail 骨架相应摘除。除骨架自带的两条外，补的测试覆盖三类边界：
窗口机制（真正的迟到、读未关闭窗口报错、多窗口互不干扰、显式关闭幂等）、正式会话
状态机（submitted/no-action 两条路径都要出现、终止状态拒绝后续操作、技术中止与
所有者中止是两种不同终态）、倒计时（remaining_seconds 随时间递减、关闭后归零）。

冻结合同：`docs/experiments/H2-dual-track-contract.json`
"""

from __future__ import annotations

import time

import pytest

from market_game_sim.experiment.h2 import session


def test_ac302_window_accepts_exactly_one_action_and_rejects_late_input():
    """每个窗口至多一次最终动作；迟到输入稳定返回 WINDOW_CLOSED。"""
    window = session.open_window(index=0)
    assert session.submit(window, session.sample_order()) is session.ACCEPTED
    assert session.submit(window, session.sample_order()) is session.WINDOW_CLOSED
    session.close(window)
    assert session.submit(window, session.sample_order()) is session.WINDOW_CLOSED


def test_ac302_timeout_writes_no_action_without_wall_clock_wait():
    """窗口超时写预定义 NO_ACTION，市场不等待墙钟补录。"""
    window = session.open_window(index=1)
    session.close(window)
    assert session.recorded_decision(window) == "NO_ACTION"


def test_window_rejects_input_after_the_real_deadline_passes():
    """真正的迟到——不是"提交两次"的伪迟到，是等到窗口时限真的过去。

    沙盒环境的单调钟粒度粗到几十毫秒（远比生产 Windows 目标环境粗），所以窗口时长
    与等待时间都要留出安全余量，不能只靠 1ns/1ms 这种理论上"应该够了"的数字。
    """
    window = session.open_window(index=2, duration_ns=1_000_000)  # 1ms 窗口
    time.sleep(0.2)  # 远超观测到的最粗时钟粒度（约 60ms）
    assert session.submit(window, session.sample_order()) is session.WINDOW_CLOSED


def test_reading_an_open_window_raises_instead_of_guessing():
    """决定只有在 close() 之后才算落定；提前读不得静默返回 NO_ACTION 冒充结果。"""
    window = session.open_window(index=3)
    with pytest.raises(session.SessionError, match="尚未关闭"):
        session.recorded_decision(window)


def test_recorded_decision_returns_the_accepted_intent_id():
    """反面：被接受的订单必须能追溯到具体 intent_id（TR-302），不是笼统的"有决定"。"""
    window = session.open_window(index=4)
    order = session.sample_order()
    session.submit(window, order)
    session.close(window)
    assert session.recorded_decision(window) == order.intent_id


def test_close_is_idempotent_and_does_not_overwrite_an_accepted_decision():
    window = session.open_window(index=5)
    order = session.sample_order()
    session.submit(window, order)
    session.close(window)
    session.close(window)  # 第二次关闭不得把已接受的决定改写成 NO_ACTION
    assert session.recorded_decision(window) == order.intent_id


def test_multiple_windows_are_independent():
    """批量场景：多个窗口同时存在，互不污染彼此的占用状态。"""
    windows = [session.open_window(index=i) for i in range(5)]
    session.submit(windows[2], session.sample_order())
    for i, window in enumerate(windows):
        session.close(window)
        if i == 2:
            assert session.recorded_decision(window) != session.NO_ACTION
        else:
            assert session.recorded_decision(window) == session.NO_ACTION


# --------------------------------------------------------------------------- #
# T911：正式会话状态机、倒计时与阶段提示
# --------------------------------------------------------------------------- #


def test_formal_session_walks_through_submitted_and_no_action_windows():
    """批量场景：多个窗口依次跑完，submitted 与 no-action 两条路径都要出现。"""
    formal = session.FormalSession(total_windows=3)
    assert formal.state is session.SessionState.WAITING

    formal.open_next_window()
    assert formal.state is session.SessionState.ACTIVE_WINDOW
    assert formal.submit(session.sample_order()) is session.ACCEPTED
    assert formal.state is session.SessionState.SUBMITTED
    accepted_window = formal.current_window
    formal.close_current_window()
    assert session.recorded_decision(accepted_window) != session.NO_ACTION

    formal.open_next_window()
    formal.close_current_window()  # 本窗口未提交
    assert formal.state is session.SessionState.NO_ACTION

    formal.open_next_window()
    formal.submit(session.sample_order())
    formal.close_current_window()
    assert formal.state is session.SessionState.COMPLETED
    assert formal.completed_windows == 3


def test_formal_session_rejects_actions_after_completion():
    formal = session.FormalSession(total_windows=1)
    formal.open_next_window()
    formal.close_current_window()
    assert formal.state is session.SessionState.COMPLETED
    with pytest.raises(session.SessionError, match="终止状态"):
        formal.open_next_window()


def test_formal_session_technical_abort_and_owner_abort_are_distinct_terminal_states():
    technical = session.FormalSession(total_windows=5)
    technical.open_next_window()
    technical.abort(technical=True)
    assert technical.state is session.SessionState.TECHNICAL_ABORT
    with pytest.raises(session.SessionError, match="终止状态"):
        technical.abort(technical=False)

    owner_initiated = session.FormalSession(total_windows=5)
    owner_initiated.open_next_window()
    owner_initiated.abort(technical=False)
    assert owner_initiated.state is session.SessionState.ABORTED


def test_submit_without_an_open_window_is_a_usage_error():
    formal = session.FormalSession(total_windows=1)
    with pytest.raises(session.SessionError, match="没有开放中的窗口"):
        formal.submit(session.sample_order())


def test_remaining_seconds_counts_down_and_hits_zero_after_close():
    window = session.open_window(index=0, duration_ns=8_000_000_000)
    before = session.remaining_seconds(window)
    assert 0.0 < before <= 8.0
    session.close(window)
    assert session.remaining_seconds(window) == 0.0


def test_formal_client_controls_never_include_an_operator_proxy_submit():
    """UX-302：实验员不得通过界面替所有者提交市场动作——闭集里不能有这类动词。"""
    controls = session.formal_client_controls()
    for forbidden in ("submit_for_owner", "operator_submit", "proxy_submit"):
        assert forbidden not in controls


def test_ac302_formal_client_exposes_no_pause_step_or_reparameterisation():
    """正式客户端不得暴露暂停、单步、改参或未来信息。

    控制项闭集已由 T905 落地（`session.formal_client_controls`），故摘除 xfail；
    UI 层怎么渲染这个闭集仍属 T911。
    """
    controls = session.formal_client_controls()
    for forbidden in ("pause", "step", "set_param", "reveal_future"):
        assert forbidden not in controls
