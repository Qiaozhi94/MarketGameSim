"""AC-303：两轨证据隔离与非正式数据拒绝。

T908 已实现，xfail 骨架摘除。

五把锁逐个变异——只测 `interactive` 被拒证明不了阶段锁、协议锁、pair 锁和排除锁也在
工作，而"多重闭锁"的全部价值就在于任意一把失效时其余仍然拦得住。

冻结合同：`docs/experiments/H2-dual-track-contract.json`
"""

from __future__ import annotations

import pytest

from market_game_sim.experiment.h2 import evidence_guard, protocol


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
