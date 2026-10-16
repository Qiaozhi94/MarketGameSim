"""0.4.2 T1122/T1123 skeleton（AC-601、AC-602、AC-606）。

strict-xfail 骨架：对应任务实现时替换为真实断言并摘除 xfail。规格见
docs/features/0.4/0.4.2-human-perturbation/spec.md §6。
"""

import pytest


@pytest.mark.xfail(strict=True, reason="T1122 not implemented yet")
def test_session_artifact_frozen_format_round_trips_and_rejects_invalid():
    """AC-601：按冻结格式落盘可重放；缺字段/错版本号被校验入口拒绝（正反两侧）"""
    pytest.fail("T1122 pending")


@pytest.mark.xfail(strict=True, reason="T1122 not implemented yet")
def test_action_journal_survives_termination_as_unsealed():
    """AC-602：
    头记录先于动作落盘；任意动作后终止进程不丢已取出动作、标 UNSEALED，
    未封口会话可校验、内容哈希稳定、种子与 roster_id 可读；
    空会话、多动作封口会话、未封口会话三种场景
    """
    pytest.fail("T1122 pending")


@pytest.mark.xfail(strict=True, reason="T1123 not implemented yet")
def test_judgement_profile_and_identity_fields_are_rejected():
    """AC-606：含对错判定/画像字段与直接身份信息的产物被拒，合法 artifact 不被误拒（正反两侧）"""
    pytest.fail("T1123 pending")
