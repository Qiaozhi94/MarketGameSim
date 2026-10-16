"""0.4.2 T1129 skeleton（AC-610）。

strict-xfail 骨架：对应任务实现时替换为真实断言并摘除 xfail。规格见
docs/features/0.4/0.4.2-human-perturbation/spec.md §6。
"""

import pytest


@pytest.mark.xfail(strict=True, reason="T1129 not implemented yet")
def test_open_loop_replay_to_window_end_and_rebuildable_pairs():
    """AC-610：按 advance 序号投到预注册种子并推进到 5700 s，配对集合可由预注册与会话哈希重建"""
    pytest.fail("T1129 pending")


@pytest.mark.xfail(strict=True, reason="T1129 not implemented yet")
def test_missing_cancel_target_records_reason_code():
    """AC-610：撤单目标在该种子上不存在时记录原因码而不跳过（正反两侧）"""
    pytest.fail("T1129 pending")
