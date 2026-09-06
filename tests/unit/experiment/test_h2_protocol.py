"""AC-301：H2 协议冻结与漂移拒绝。

T904 已实现，xfail 骨架相应摘除。这里的负向用例逐个字段地删冻结项——只测一个字段
无法证明 ``REQUIRED_FIELDS`` 里其余项也在被检查，而"完整性"恰恰是那种少检一项就
静默失效的门。

冻结合同：`docs/experiments/H2-dual-track-contract.json`
"""

from __future__ import annotations

import json

import pytest

from market_game_sim.experiment.h2 import protocol


@pytest.fixture
def draft() -> dict:
    return protocol.draft_from_contract()


# --------------------------------------------------------------------------- #
# 正面：合同派生的完整草案可以冻结
# --------------------------------------------------------------------------- #


def test_contract_draft_freezes_and_is_content_addressed(draft):
    frozen = protocol.freeze(draft)
    assert len(frozen.protocol_hash) == 64
    assert frozen.contract_id == draft["contract_id"]
    assert frozen.minimum_blocks == 168
    frozen.verify()


def test_freeze_is_deterministic_across_key_order(draft):
    """canonical JSON：键序不同不得改变哈希，否则同一份协议会有两个身份。"""
    shuffled = dict(reversed(list(draft.items())))
    assert protocol.freeze(shuffled).protocol_hash == protocol.freeze(draft).protocol_hash


def test_control_arm_enum_is_the_single_source():
    """CLI 与协议 schema 共用同一个 control_arm 闭集（DQ-302）。"""
    assert protocol.CONTROL_ARMS == ("linear", "threshold", "owner")
    assert protocol.draft_from_contract()["control_arms"] == list(protocol.CONTROL_ARMS)


# --------------------------------------------------------------------------- #
# 负面：缺项、漂移与合同违反
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("field", protocol.REQUIRED_FIELDS)
def test_every_required_field_blocks_the_freeze(draft, field):
    """逐字段变异：任一冻结项缺失都不得产生哈希。"""
    del draft[field]
    with pytest.raises(protocol.ProtocolIncomplete):
        protocol.freeze(draft)


def test_uncalibrated_sesoi_blocks_the_freeze(draft):
    """校准前的 null SESOI 不得冻结——否则会拿一个没有依据的阈值去采样。"""
    draft["sesoi_by_family"]["liquidation_cascade"] = None
    with pytest.raises(protocol.ProtocolIncomplete, match="尚未校准"):
        protocol.freeze(draft)


def test_missing_family_in_sesoi_table_blocks_the_freeze(draft):
    draft["sesoi_by_family"].pop("price_crash")
    with pytest.raises(protocol.ProtocolIncomplete, match="SESOI 条目"):
        protocol.freeze(draft)


def test_occurrence_cannot_be_the_primary_estimand(draft):
    """发生指标实测为零方差，改回主要终点等于把功效归零。"""
    draft["primary_estimand"] = "occurrence_risk_difference"
    with pytest.raises(protocol.ProtocolIncomplete, match="严重程度"):
        protocol.freeze(draft)


def test_two_policies_must_differ(draft):
    draft["policies"] = ["risk_budget_linear_v1", "risk_budget_linear_v1"]
    with pytest.raises(protocol.ProtocolIncomplete, match="两条互不相同"):
        protocol.freeze(draft)


def test_control_arms_cannot_drift_from_the_frozen_enum(draft):
    draft["control_arms"] = ["window-matched", "goal"]
    with pytest.raises(protocol.ProtocolIncomplete, match="闭集"):
        protocol.freeze(draft)


def test_block_count_cannot_go_below_the_contract_floor(draft):
    """合同声明 may_lower_minimum_blocks=false；下调必须在冻结处被挡住。"""
    lowered = protocol.draft_from_contract(minimum_blocks=130)
    with pytest.raises(protocol.ProtocolIncomplete, match="不得低于合同下限"):
        protocol.freeze(lowered)
    # 反面：上调是允许的（校准可能要求更多 block）。
    assert protocol.freeze(protocol.draft_from_contract(minimum_blocks=200)).minimum_blocks == 200


def test_owner_track_cannot_claim_research_eligibility(draft):
    """SOP 原则 3：n=1 自我实验不得承担研究声明。"""
    draft["tracks"]["owner_n_of_1"]["research_claim_eligible"] = True
    with pytest.raises(protocol.ProtocolIncomplete, match="研究声明"):
        protocol.freeze(draft)


# --------------------------------------------------------------------------- #
# 冻结后的不可变性与 assignment 绑定
# --------------------------------------------------------------------------- #


def test_frozen_payload_is_read_only(draft):
    frozen = protocol.freeze(draft)
    with pytest.raises(TypeError):
        frozen.payload["minimum_blocks"] = 1


def test_content_change_produces_a_new_hash_and_invalidates_old_assignments(draft):
    frozen = protocol.freeze(draft)
    drifted = protocol.freeze(protocol.draft_from_contract(minimum_blocks=200))
    assert drifted.protocol_hash != frozen.protocol_hash
    assert protocol.accepts_assignment(frozen, issued_under=frozen.protocol_hash)
    assert not protocol.accepts_assignment(drifted, issued_under=frozen.protocol_hash)


def test_verify_detects_a_tampered_payload(draft):
    """绕过 dataclass 直接改内容时，verify() 必须报漂移。"""
    frozen = protocol.freeze(draft)
    tampered = protocol.FrozenProtocol(
        protocol_hash=frozen.protocol_hash,
        payload=protocol.MappingProxyType({**dict(frozen.payload), "minimum_blocks": 1}),
    )
    with pytest.raises(protocol.ProtocolDrift):
        tampered.verify()


def test_draft_tracks_the_contract_not_a_local_copy(tmp_path, draft):
    """合同是唯一真源：改合同就该改草案，代码里不得另存一份样本量。"""
    contract = json.loads(protocol.CONTRACT_PATH.read_text(encoding="utf-8"))
    contract["formal_ai_track"]["minimum_blocks"] = 999
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")
    assert protocol.draft_from_contract(contract_path=path)["minimum_blocks"] == 999
