"""AC-303：两轨证据隔离与非正式数据拒绝；技术中止、补跑与结果盲 adjudication（T914）。

T908/T914 已实现，xfail 骨架摘除。

五把锁逐个变异——只测 `interactive` 被拒证明不了阶段锁、协议锁、pair 锁和排除锁也在
工作，而"多重闭锁"的全部价值就在于任意一把失效时其余仍然拦得住。T914 的 adjudication
部分同样逐条变异五种终止路径（协议漂移/技术中止/所有者中止/pair 不完整/未完成），
外加批量场景（多条记录同时裁决）。

冻结合同：`docs/experiments/H2-dual-track-contract.json`
"""

from __future__ import annotations

import pytest

from market_game_sim.experiment.h2 import adjudication, assignment, evidence_guard, protocol


@pytest.fixture(autouse=True)
def _clean_ledger():
    evidence_guard.reset()
    yield
    evidence_guard.reset()


@pytest.fixture(scope="module")
def frozen_hash() -> str:
    return protocol.freeze(protocol.draft_from_contract()).protocol_hash


# --------------------------------------------------------------------------- #
# 正例：不先确认能放行，"全拒绝"也算门禁通过
# --------------------------------------------------------------------------- #


def test_frozen_formal_run_is_admitted(frozen_hash):
    assert evidence_guard.admit(
        run_mode=evidence_guard.AI_TRACK, stage="formal", protocol_hash=frozen_hash
    )


def test_owner_track_formal_run_is_admitted_into_its_own_index(frozen_hash):
    """所有者轨也有自己的正式证据，只是证据级别是 experiment-preview。"""
    assert evidence_guard.admit(
        run_mode=evidence_guard.OWNER_TRACK, stage="formal", protocol_hash=frozen_hash
    )


# --------------------------------------------------------------------------- #
# 五把锁逐个变异
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("run_mode", ["interactive", "unknown-mode", "", "AI-MECHANISM-EXPERIMENT"])
def test_lock_one_rejects_foreign_run_modes(run_mode):
    with pytest.raises(evidence_guard.EvidenceRejected):
        evidence_guard.admit(run_mode=run_mode, stage="formal")


@pytest.mark.parametrize("stage", ["training", "preview"])
def test_lock_two_rejects_non_formal_stages(stage):
    with pytest.raises(evidence_guard.EvidenceRejected, match="不得进入正式证据"):
        evidence_guard.admit(run_mode=evidence_guard.AI_TRACK, stage=stage)


def test_lock_two_rejects_unknown_stage():
    with pytest.raises(evidence_guard.EvidenceRejected, match="未知 sample_stage"):
        evidence_guard.admit(run_mode=evidence_guard.AI_TRACK, stage="pilot")


def test_lock_three_rejects_protocol_drift():
    with pytest.raises(evidence_guard.EvidenceRejected, match="协议哈希漂移"):
        evidence_guard.admit(
            run_mode=evidence_guard.AI_TRACK, stage="formal", protocol_hash="0" * 64
        )


def test_lock_four_rejects_incomplete_pair(frozen_hash):
    with pytest.raises(evidence_guard.EvidenceRejected, match="pair 不完整"):
        evidence_guard.admit(
            run_mode=evidence_guard.AI_TRACK,
            stage="formal",
            protocol_hash=frozen_hash,
            pair_complete=False,
        )


def test_lock_five_rejects_preregistered_exclusion(frozen_hash):
    with pytest.raises(evidence_guard.EvidenceRejected, match="排除条件"):
        evidence_guard.admit(
            run_mode=evidence_guard.AI_TRACK,
            stage="formal",
            protocol_hash=frozen_hash,
            excluded_reason="TECHNICAL_ABORT",
        )


# --------------------------------------------------------------------------- #
# 原子性
# --------------------------------------------------------------------------- #


def test_rejection_leaves_no_partial_output(frozen_hash):
    """每条拒绝路径都不得留下半截产物。"""
    rejections = [
        {"run_mode": "interactive", "stage": "formal"},
        {"run_mode": evidence_guard.AI_TRACK, "stage": "training"},
        {"run_mode": evidence_guard.AI_TRACK, "stage": "formal", "protocol_hash": "0" * 64},
        {
            "run_mode": evidence_guard.AI_TRACK,
            "stage": "formal",
            "protocol_hash": frozen_hash,
            "pair_complete": False,
        },
    ]
    for kwargs in rejections:
        with pytest.raises(evidence_guard.EvidenceRejected):
            evidence_guard.admit(**kwargs)
    assert evidence_guard.partial_writes() == []


# --------------------------------------------------------------------------- #
# 跨轨合并禁令
# --------------------------------------------------------------------------- #


def test_cross_track_merge_is_forbidden():
    with pytest.raises(evidence_guard.CrossTrackMerge, match="禁止跨轨合并"):
        evidence_guard.merge([evidence_guard.AI_TRACK, evidence_guard.OWNER_TRACK])


def test_same_track_aggregation_is_allowed():
    """反面：同轨聚合是正常操作，禁令不能宽到把它也挡了。"""
    evidence_guard.merge([evidence_guard.AI_TRACK, evidence_guard.AI_TRACK])
    evidence_guard.merge([evidence_guard.OWNER_TRACK])


def test_merge_rejects_unknown_track():
    with pytest.raises(evidence_guard.EvidenceRejected, match="未知 run_mode"):
        evidence_guard.merge([evidence_guard.AI_TRACK, "interactive"])


# --------------------------------------------------------------------------- #
# T914：结果盲 adjudication
# --------------------------------------------------------------------------- #


def _record(**overrides) -> adjudication.TechnicalRecord:
    base = {
        "assignment_id": "h2-ai-50000",
        "session_state": "completed",
        "pair_complete": True,
        "protocol_hash": "abc",
        "expected_protocol_hash": "abc",
    }
    base.update(overrides)
    return adjudication.TechnicalRecord(**base)


def test_completed_pair_under_frozen_protocol_is_included():
    decision = adjudication.adjudicate(_record())
    assert decision.status is adjudication.AdjudicationStatus.INCLUDED
    assert decision.reason is None
    assert decision.rerun_required is False


@pytest.mark.parametrize(
    "overrides, expected_reason, expected_rerun",
    [
        ({"protocol_hash": "abc", "expected_protocol_hash": "xyz"}, "PROTOCOL_DRIFT", False),
        ({"session_state": "technical-abort"}, "TECHNICAL_ABORT", True),
        ({"session_state": "aborted"}, "OWNER_ABORT", False),
        ({"pair_complete": False}, "INCOMPLETE_PAIR", False),
        ({"session_state": "active-window"}, "INCOMPLETE_SESSION", False),
    ],
)
def test_every_exclusion_path_is_reached_by_a_distinct_mutation(
    overrides, expected_reason, expected_rerun
):
    """逐条终止路径变异：每条路径都要能独立触发，且只有技术中止要求补跑。"""
    decision = adjudication.adjudicate(_record(**overrides))
    assert decision.status is adjudication.AdjudicationStatus.EXCLUDED
    assert decision.reason.value == expected_reason
    assert decision.rerun_required is expected_rerun


def test_owner_abort_never_triggers_a_rerun():
    """反面对照：所有者主动中止不是技术故障，不得因此获得重跑机会（Q-305）。"""
    decision = adjudication.adjudicate(_record(session_state="aborted"))
    assert decision.rerun_required is False


def test_batch_adjudication_handles_multiple_records_independently():
    """批量场景：多条记录同时裁决，互不干扰、顺序对应。"""
    records = (
        _record(assignment_id="a1"),
        _record(assignment_id="a2", session_state="technical-abort"),
        _record(assignment_id="a3", pair_complete=False),
        _record(assignment_id="a4"),
    )
    decisions = adjudication.adjudicate_batch(records)
    assert [d.assignment_id for d in decisions] == ["a1", "a2", "a3", "a4"]
    assert [d.status for d in decisions] == [
        adjudication.AdjudicationStatus.INCLUDED,
        adjudication.AdjudicationStatus.EXCLUDED,
        adjudication.AdjudicationStatus.EXCLUDED,
        adjudication.AdjudicationStatus.INCLUDED,
    ]


def test_sample_flow_summary_counts_reasons_across_a_batch():
    records = (
        _record(assignment_id="a1"),
        _record(assignment_id="a2", session_state="technical-abort"),
        _record(assignment_id="a3", session_state="technical-abort"),
        _record(assignment_id="a4", pair_complete=False),
    )
    summary = adjudication.sample_flow_summary(adjudication.adjudicate_batch(records))
    assert summary["total"] == 4
    assert summary["included"] == 1
    assert summary["excluded"] == 3
    assert summary["excluded_by_reason"] == {"TECHNICAL_ABORT": 2, "INCOMPLETE_PAIR": 1}
    assert summary["reruns_required"] == 2


# --------------------------------------------------------------------------- #
# T914：补跑只能按冻结顺序消耗备用池
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def frozen_and_plan():
    frozen = protocol.freeze(protocol.draft_from_contract())
    return frozen, assignment.build_seed_plan(frozen)


def test_technical_abort_rerun_consumes_the_next_reserve_seed(frozen_and_plan):
    frozen, plan = frozen_and_plan
    original = assignment.issue(frozen)[0]
    decision = adjudication.adjudicate(_record(session_state="technical-abort"))
    rerun = adjudication.rerun_if_required(decision, original, plan=plan)
    assert rerun is not None
    assert rerun.seed == plan.reserve[0]
    assert rerun.superseded_by == original.assignment_id


def test_non_technical_exclusion_never_reruns(frozen_and_plan):
    """反面：协议漂移/所有者中止/pair 不完整的裁决不得触发补跑消耗备用池。"""
    frozen, plan = frozen_and_plan
    original = assignment.issue(frozen)[0]
    for overrides in (
        {"protocol_hash": "abc", "expected_protocol_hash": "xyz"},
        {"session_state": "aborted"},
        {"pair_complete": False},
    ):
        decision = adjudication.adjudicate(_record(**overrides))
        assert adjudication.rerun_if_required(decision, original, plan=plan) is None


def test_rerun_if_required_rejects_a_forged_rerun_flag(frozen_and_plan):
    """反面：即使有人手工构造一个 rerun_required=True 但 reason 不在闭集里的裁决，
    也必须被拒绝，而不是被静默执行——闭集检查在执行层再把一次关。
    """
    frozen, plan = frozen_and_plan
    original = assignment.issue(frozen)[0]
    forged = adjudication.AdjudicationDecision(
        assignment_id=original.assignment_id,
        status=adjudication.AdjudicationStatus.EXCLUDED,
        reason=adjudication.ExclusionReason.OWNER_ABORT,
        rerun_required=True,
    )
    with pytest.raises(adjudication.AdjudicationError, match="不在允许补跑的原因闭集"):
        adjudication.rerun_if_required(forged, original, plan=plan)
