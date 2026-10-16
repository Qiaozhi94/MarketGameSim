"""0.4.2 T1126/T1130 skeleton（AC-603、AC-604）。

strict-xfail 骨架：对应任务实现时替换为真实断言并摘除 xfail。规格见
docs/features/0.4/0.4.2-human-perturbation/spec.md §6。
"""

import pytest


@pytest.mark.xfail(strict=True, reason="T1126 not implemented yet")
def test_baseline_arm_reproducible_point_by_point():
    """AC-603：同装配同种子的无人类基线逐点可复现"""
    pytest.fail("T1126 pending")


@pytest.mark.xfail(strict=True, reason="T1126 not implemented yet")
def test_same_seed_replay_matches_seal_and_detects_tampering():
    """AC-603：
    同种子重放到结束序号时事件摘要与封口逐位相同；篡改 advance 序号或载荷判 REPLAY_DIVERGED
    """
    pytest.fail("T1126 pending")


@pytest.mark.xfail(strict=True, reason="T1130 not implemented yet")
def test_owner_and_ai_orders_resolve_to_agent_decide_in_batch():
    """AC-604：
    多条记录并存时 owner 与 AI 委托的 decision_event_id 都解析到 AGENT_DECIDE，参与者类别可区分
    """
    pytest.fail("T1130 pending")
