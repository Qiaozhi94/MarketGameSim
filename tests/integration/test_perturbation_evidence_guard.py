"""0.4.2 T1131 skeleton（AC-607）。

strict-xfail 骨架：对应任务实现时替换为真实断言并摘除 xfail。规格见
docs/features/0.4/0.4.2-human-perturbation/spec.md §6。
"""

import pytest


@pytest.mark.xfail(strict=True, reason="T1131 not implemented yet")
def test_perturbation_products_rejected_by_evidence_index():
    """AC-607：
    带 experiment-preview 与 run_mode interactive 的 artifact/报告交给 evidence index 构建入口被拒；
    合规 SPONTANEOUS + formal-research 输入不受影响
    """
    pytest.fail("T1131 pending")
