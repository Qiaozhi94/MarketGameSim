"""AC-304：配对运行的比较矩阵与双臂生成。

骨架状态：本文件是 `ready-for-development` 前置要求的 strict-xfail 占位（tasks §0）。
每条测试写的是**实现后应当为真**的断言，现在因为 H2 assignment 与配对运行编排 尚不存在而失败；
`strict=True` 保证一旦实现并通过，测试会 XPASS 报错，提醒删掉 xfail 标记。

冻结合同：`docs/experiments/H2-dual-track-contract.json`
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="T906/T907 未实现：H2 配对运行编排尚不存在")
def test_ac304_ai_block_holds_both_policies_on_one_seed():
    """AI 轨每个 block 恰含同 seed 的两条冻结策略运行。"""
    from market_game_sim.experiment.h2 import runner

    block = runner.run_ai_block(seed=40_000)
    policies = {run.policy_id for run in block.runs}
    assert policies == {"risk_budget_linear_v1", "risk_budget_threshold_v1"}
    assert len({run.seed for run in block.runs}) == 1


@pytest.mark.xfail(strict=True, reason="T907 未实现：pair validator 尚不存在")
def test_ac304_matrix_same_fields_are_identical_and_diffs_are_disclosed():
    """标为相同的字段逐字段一致；标为不同的字段完整披露。"""
    from market_game_sim.experiment.h2 import runner

    report = runner.validate_pair(runner.run_ai_block(seed=40_000))
    assert report.identical_fields >= {
        "accounts",
        "initial_funds",
        "information_set",
        "action_space",
        "window_schedule",
    }
    assert report.disclosed_differences and "policy_id" in report.disclosed_differences


@pytest.mark.xfail(strict=True, reason="T907 未实现：窗口调度匹配尚未落地")
def test_ac304_policy_references_run_under_the_owner_window_scheduler():
    """两条策略参照必须跑同一有限窗口调度器，不得按内核默认逐次调度。"""
    from market_game_sim.experiment.h2 import runner

    block = runner.run_ai_block(seed=40_000)
    for run in block.runs:
        assert run.window_schedule == runner.OWNER_WINDOW_CONTRACT


@pytest.mark.xfail(strict=True, reason="T906 未实现：备用 seed 池尚不存在")
def test_ac304_rerun_consumes_the_next_reserve_seed_in_frozen_order():
    """技术补跑只能按冻结顺序取用备用 seed，并保留原中止审计链。"""
    from market_game_sim.experiment.h2 import runner

    first, second = runner.reserve_pool()[:2]
    rerun = runner.rerun_after_abort(original_seed=40_000)
    assert rerun.seed == first and rerun.seed != second
    assert rerun.rerun_of_session_id
