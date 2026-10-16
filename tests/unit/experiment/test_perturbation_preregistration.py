"""0.4.2 T1127 skeleton（AC-609）。

strict-xfail 骨架：对应任务实现时替换为真实断言并摘除 xfail。规格见
docs/features/0.4/0.4.2-human-perturbation/spec.md §6。
"""

import pytest


@pytest.mark.xfail(strict=True, reason="T1127 not implemented yet")
def test_pairing_refuses_missing_tampered_or_unlisted_treatment():
    """AC-609：
    预注册文件缺失、哈希不一致或处理会话不在其中时配对入口 fail closed，一致时放行（正反两侧）
    """
    pytest.fail("T1127 pending")
