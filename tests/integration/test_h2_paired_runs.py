"""AC-304：配对运行的比较矩阵与双臂生成。

T907 已实现，对应 xfail 骨架摘除；仍属 T906 备用池编排的那条保留 xfail。

这里最要紧的两条不变量：**窗口调度必须在比较字段里**（否则"决策机会一致"只是文档
承诺），以及**严重度用 chain_size 而不是 chain_depth**（后者实测恒为 0，用它会让强平
连锁家族退回零方差终点）。

冻结合同：`docs/experiments/H2-dual-track-contract.json`
"""

from __future__ import annotations

import dataclasses

import pytest

from market_game_sim.experiment.h2 import runner

#: 在 H2 的 50000 seed 段里实测会产生强平连锁的 seed（另一些 seed 两臂都是 0）。
SEED_WITH_CASCADE = 50_003
SEED_PLAIN = 50_000


@pytest.fixture(scope="module")
def block() -> runner.PairedBlock:
    return runner.run_ai_block(SEED_PLAIN)


# --------------------------------------------------------------------------- #
# 双臂生成
# --------------------------------------------------------------------------- #


def test_ai_block_holds_both_policies_on_one_seed(block):
    assert {run.policy_id for run in block.runs} == {
        "risk_budget_linear_v1",
        "risk_budget_threshold_v1",
    }
    assert {run.seed for run in block.runs} == {SEED_PLAIN}


def test_unknown_arm_is_rejected():
    with pytest.raises(runner.PairError, match="未知 arm"):
        runner.build_config(SEED_PLAIN, "owner-typo")


def test_both_arms_run_under_the_owner_window_scheduler(block):
    """两条参照都必须按窗口合同的逻辑长度观察，不得用内核默认间隔。"""
    window_ns = runner.OWNER_WINDOW_CONTRACT["logical_ns_per_window"]
    for arm in runner.ARM_TO_POLICY:
        config = runner.build_config(SEED_PLAIN, arm)
        belief = next(spec for spec in config.agent_specs if spec.agent_id == "belief-0")
        assert belief.observe_interval_ns == window_ns
    for run in block.runs:
        assert run.window_schedule == runner.OWNER_WINDOW_CONTRACT


def test_window_contract_covers_all_three_arms():
    assert runner.OWNER_WINDOW_CONTRACT["applies_to"] == ["linear", "threshold", "owner"]
    assert runner.OWNER_WINDOW_CONTRACT["max_actions_per_window"] == 1
    assert runner.OWNER_WINDOW_CONTRACT["timeout_decision"] == "NO_ACTION"


# --------------------------------------------------------------------------- #
# pair validator
# --------------------------------------------------------------------------- #


def test_matrix_same_fields_are_identical_and_diffs_are_disclosed(block):
    report = runner.validate_pair(block)
    assert report.identical_fields == {
        "accounts",
        "initial_price_ticks",
        "information_set",
        "action_space",
        "window_schedule",
    }
    assert report.disclosed_differences["policy_id"] == (
        "risk_budget_linear_v1",
        "risk_budget_threshold_v1",
    )


def test_window_schedule_drift_fails_the_pair(block):
    """变异：只改一条运行的窗口调度，pair 必须拒绝。"""
    drifted = dataclasses.replace(
        block.runs[1], window_schedule={**block.runs[1].window_schedule, "windows_per_scenario": 30}
    )
    with pytest.raises(runner.PairError, match="window_schedule"):
        runner.validate_pair(runner.PairedBlock(seed=block.seed, runs=(block.runs[0], drifted)))


def test_information_set_drift_fails_the_pair(block):
    drifted = dataclasses.replace(block.runs[1], information_set="includes_future_path")
    with pytest.raises(runner.PairError, match="information_set"):
        runner.validate_pair(runner.PairedBlock(seed=block.seed, runs=(block.runs[0], drifted)))


def test_same_policy_twice_is_not_a_valid_pair(block):
    duplicated = dataclasses.replace(block.runs[1], policy_id=block.runs[0].policy_id)
    with pytest.raises(runner.PairError, match="不同策略"):
        runner.validate_pair(runner.PairedBlock(seed=block.seed, runs=(block.runs[0], duplicated)))


def test_cross_seed_runs_are_not_a_valid_pair(block):
    other = dataclasses.replace(block.runs[1], seed=block.seed + 1)
    with pytest.raises(runner.PairError, match="共享 seed"):
        runner.validate_pair(runner.PairedBlock(seed=block.seed, runs=(block.runs[0], other)))


def test_single_run_block_is_rejected(block):
    with pytest.raises(runner.PairError, match="两条运行"):
        runner.validate_pair(runner.PairedBlock(seed=block.seed, runs=(block.runs[0],)))


# --------------------------------------------------------------------------- #
# 严重度口径
# --------------------------------------------------------------------------- #


def test_cascade_severity_counts_accounts_not_chain_depth():
    """实测 chain_depth 恒为 0；严重度必须来自 chain_size，否则该家族零方差。"""
    block = runner.run_ai_block(SEED_WITH_CASCADE)
    severities = [runner.chain_severity(run) for run in block.runs]
    assert max(severities) >= 2, "该 seed 应产生至少两个账户的强平连锁"
    for run in block.runs:
        depths = run.result.liquidation_metrics.chain_depth_counts
        assert set(depths) <= {0}, "本模型族从未观察到 depth>=1 的传导"


def test_severity_is_zero_when_no_chain_occurs(block):
    """反面：没有连锁时严重度记 0，而不是缺失或异常。"""
    assert [runner.chain_severity(run) for run in block.runs] == [0, 0]


def test_paired_runs_are_deterministic():
    """同 seed 重跑必须得到相同严重度——配对差的随机性只来自 seed 抽样。"""
    first = [runner.chain_severity(r) for r in runner.run_ai_block(SEED_WITH_CASCADE).runs]
    second = [runner.chain_severity(r) for r in runner.run_ai_block(SEED_WITH_CASCADE).runs]
    assert first == second


def test_rerun_consumes_the_next_reserve_seed_in_frozen_order():
    """运行编排层必须接上冻结备用池，并保留原 session/pair 审计链。"""
    first, second = runner.reserve_pool()[:2]
    rerun = runner.rerun_after_abort(original_seed=SEED_PLAIN)
    next_rerun = runner.rerun_after_abort(
        original_seed=SEED_PLAIN,
        consumed=(rerun.seed,),
        original_session_id="session-original-50000",
    )
    assert rerun.seed == first and rerun.seed != second
    assert next_rerun.seed == second
    assert rerun.rerun_of_session_id
    assert rerun.supersedes_pair_id == f"h2-ai-{SEED_PLAIN}"
    assert next_rerun.rerun_of_session_id == "session-original-50000"
