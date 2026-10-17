"""0.4.2 T1124 skeleton（AC-602、AC-603）。

strict-xfail 骨架：对应任务实现时替换为真实断言并摘除 xfail。规格见
docs/features/0.4/0.4.2-human-perturbation/spec.md §6。
"""

import pytest


@pytest.mark.xfail(strict=True, reason="T1124 not implemented yet")
def test_fields_assigned_at_drain_under_deterministic_interleaving():
    """AC-603：
    同一 advance 内多笔提交、提交恰在推进中途两类交错下，
    order_id、时间戳与 submitted_at 只由 advance 序号、动作序号与载荷决定且不重复
    """
    pytest.fail("T1124 pending")


@pytest.mark.xfail(strict=True, reason="T1124 not implemented yet")
def test_action_journal_appended_per_accepted_action():
    """AC-602：每受理一笔动作立即追加日志，记录取出它的 advance 序号"""
    pytest.fail("T1124 pending")


@pytest.mark.xfail(strict=True, reason="T1124 not implemented yet")
def test_invalid_cancel_found_after_enqueue_is_dropped_without_journal():
    """AC-602：
    入队后才判定的无效撤单（反查不到 order_id）被丢弃，不进内核、不入动作日志；
    同批里有效的动作照常处理
    """
    pytest.fail("T1124 pending")


@pytest.mark.xfail(strict=True, reason="T1124 not implemented yet")
def test_pure_ai_runs_keep_recorded_digests():
    """AC-603：注册 owner 代理规格后，纯 AI 运行的 0.4.1/0.4.3 入库摘要不变"""
    pytest.fail("T1124 pending")
