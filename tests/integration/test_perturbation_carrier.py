"""0.4.2 T1125 skeleton（AC-608）。

strict-xfail 骨架：对应任务实现时替换为真实断言并摘除 xfail。规格见
docs/features/0.4/0.4.2-human-perturbation/spec.md §6。
"""

import pytest


@pytest.mark.xfail(strict=True, reason="T1125 not implemented yet")
def test_carrier_roster_hashes_to_id_with_value_family_params():
    """AC-608：载体清单内容哈希到 roster_id，价值族参数为 count 6 / sensitivity 150"""
    pytest.fail("T1125 pending")


@pytest.mark.xfail(strict=True, reason="T1125 not implemented yet")
def test_terminal_refuses_orders_until_warmup_reaches_window_start():
    """AC-608：预热到 W0 前拒单、之后开放；推进到 5700 s 仍未退出冷启动时拒绝开放（正反两侧）"""
    pytest.fail("T1125 pending")
