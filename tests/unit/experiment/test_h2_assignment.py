"""T906：预签发 assignment、场景顺序与备用 seed 池（FR-301 / NFR-303 / AC-304）。

这里守三条容易被悄悄放松的约束：备用 seed 必须**按冻结顺序**消耗（能挑就等于能换掉
不喜欢的结果）、seed 段必须与既有证据不重叠、补跑必须留下指向原记录的引用。

冻结合同：`docs/experiments/H2-dual-track-contract.json`
"""

from __future__ import annotations

import pytest

from market_game_sim.experiment.h2 import assignment, protocol


@pytest.fixture(scope="module")
def frozen() -> protocol.FrozenProtocol:
    return protocol.freeze(protocol.draft_from_contract())


@pytest.fixture(scope="module")
def plan(frozen) -> assignment.SeedPlan:
    return assignment.build_seed_plan(frozen)


# --------------------------------------------------------------------------- #
# seed 计划
# --------------------------------------------------------------------------- #


def test_planned_seeds_match_the_frozen_block_count(frozen, plan):
    assert len(plan.planned) == frozen.minimum_blocks == 168


def test_reserve_pool_is_ten_percent_and_disjoint(plan):
    assert len(plan.reserve) == 17  # ceil(168 * 0.10)
    assert not set(plan.planned) & set(plan.reserve)


def test_h2_seed_segment_does_not_collide_with_existing_evidence(plan):
    """40000 段属于 v0.1.5、30000 段属于更早运行；重叠会让证据归属需要靠回忆。"""
    pool = set(plan.planned) | set(plan.reserve)
    assert min(pool) >= 50_000
    assert not pool & set(range(30_000, 40_200))


def test_seed_plan_rejects_overlap():
    bad = assignment.SeedPlan(planned=(1, 2), reserve=(2, 3))
    with pytest.raises(assignment.AssignmentError, match="不得重叠"):
        bad.validate()


def test_seed_plan_rejects_empty_planned():
    with pytest.raises(assignment.AssignmentError, match="不能为空"):
        assignment.SeedPlan(planned=(), reserve=(1,)).validate()


# --------------------------------------------------------------------------- #
# 预签发
# --------------------------------------------------------------------------- #


def test_issue_covers_every_planned_seed_with_both_policy_arms(frozen, plan):
    issued = assignment.issue(frozen)
    assert len(issued) == len(plan.planned)
    assert [a.seed for a in issued] == list(plan.planned)
    for record in issued:
        assert record.arms == ("linear", "threshold")
        assert record.protocol_hash == frozen.protocol_hash
        assert record.superseded_by is None


def test_issued_assignments_are_bound_to_one_protocol_version(frozen):
    """协议内容一变，旧 assignment 不再被接受（spec §5）。"""
    issued = assignment.issue(frozen)
    other = protocol.freeze(protocol.draft_from_contract(minimum_blocks=200))
    assert protocol.accepts_assignment(frozen, issued_under=issued[0].protocol_hash)
    assert not protocol.accepts_assignment(other, issued_under=issued[0].protocol_hash)


# --------------------------------------------------------------------------- #
# 场景顺序
# --------------------------------------------------------------------------- #


def test_scenario_order_is_a_deterministic_permutation(frozen):
    order = assignment.scenario_order(frozen, audit_seed=7)
    assert sorted(order) == list(range(24))
    assert order == assignment.scenario_order(frozen, audit_seed=7)


def test_scenario_order_depends_on_the_audit_seed(frozen):
    """审计种子不同则顺序不同，否则"随机化"只是个说法。"""
    assert assignment.scenario_order(frozen, audit_seed=7) != assignment.scenario_order(
        frozen, audit_seed=8
    )


# --------------------------------------------------------------------------- #
# 补跑与备用池
# --------------------------------------------------------------------------- #


def test_rerun_consumes_the_next_reserve_seed_in_frozen_order(frozen, plan):
    issued = assignment.issue(frozen)
    first = assignment.rerun_assignment(issued[0], plan=plan)
    assert first.seed == plan.reserve[0]
    second = assignment.rerun_assignment(issued[1], plan=plan, consumed=(first.seed,))
    assert second.seed == plan.reserve[1]


def test_rerun_keeps_an_audit_link_to_the_original(frozen, plan):
    issued = assignment.issue(frozen)
    rerun = assignment.rerun_assignment(issued[3], plan=plan)
    assert rerun.superseded_by == issued[3].assignment_id
    assert rerun.assignment_id != issued[3].assignment_id
    assert rerun.seed not in plan.planned


def test_reserve_pool_exhaustion_is_a_hard_stop(frozen, plan):
    """备用池用尽必须报错，不能回头去借 planned seed。"""
    issued = assignment.issue(frozen)
    with pytest.raises(assignment.ReservePoolExhausted):
        assignment.rerun_assignment(issued[0], plan=plan, consumed=plan.reserve)


def test_sample_flow_records_aborts_and_reruns(frozen, plan):
    """多条记录同时存在：一次中止 + 一次补跑必须都出现在样本流里。"""
    issued = assignment.issue(frozen)
    rerun = assignment.rerun_assignment(issued[0], plan=plan)
    flow = assignment.sample_flow(issued + (rerun,), aborted=(issued[0].assignment_id,))
    assert flow["issued"] == len(issued) + 1
    assert flow["aborted"] == [issued[0].assignment_id]
    assert flow["reruns"] == [
        {"assignment_id": rerun.assignment_id, "supersedes": issued[0].assignment_id}
    ]
