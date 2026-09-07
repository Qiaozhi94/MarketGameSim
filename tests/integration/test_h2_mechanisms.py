"""AC-306：机制指标到事件链的端到端追溯（集成层）。

T913 已实现，xfail 骨架相应摘除。用真实配对 block 的事件链验证——机制值不是伪造样例，
每一条都能回溯到真实的 `TRADE_SETTLE`/`ORDER_CANCELLED` 事件 ID。所有者的真实执行
（T917）尚不存在，这里复用 AI 轨的真实策略决策作为等价的因果链结构：`decision_event_id`
到订单、成交、撤单的回溯对所有者和策略用的是同一套事件 schema。

冻结合同：`docs/experiments/H2-dual-track-contract.json`
"""

from __future__ import annotations

import pytest

from market_game_sim.experiment.h2 import mechanisms, runner

#: 已知在 belief-0 身上同时产生激进成交与撤单的真实 seed。
SAMPLE_SEED = 50_003
AGENT_ID = "belief-0"


@pytest.fixture(scope="module")
def result():
    block = runner.run_ai_block(SAMPLE_SEED)
    return next(r.result for r in block.runs if r.policy_id == runner.ARM_TO_POLICY["linear"])


# --------------------------------------------------------------------------- #
# 端到端追溯
# --------------------------------------------------------------------------- #


def test_ac306_every_mechanism_value_traces_back_to_event_ids(result):
    """每个机制值都能回溯到规范输入与 decision_event_id。"""
    table = mechanisms.build_table_from_result(result, agent_id=AGENT_ID)
    assert table
    for row in table:
        assert row.decision_event_id
        for value in row.values.values():
            assert value.is_missing is False  # 真实运行的完整日志不应有缺失
            if value.value:
                assert value.evidence_event_ids


def test_at_least_one_decision_shows_non_zero_aggressive_orders(result):
    """反面对照：不能所有值都恰好是 0——那样测试通过但没验证真实计算路径。"""
    table = mechanisms.build_table_from_result(result, agent_id=AGENT_ID)
    nonzero = [row for row in table if row.values["aggressive_orders"].value]
    assert nonzero
    sample = nonzero[0]
    assert sample.values["aggressive_orders"].evidence_event_ids


def test_evidence_event_ids_resolve_to_real_events_in_the_log(result):
    """机制值引用的 evidence_event_ids 必须能在原始日志里找到，不是编造的 ID。"""
    table = mechanisms.build_table_from_result(result, agent_id=AGENT_ID)
    real_ids = {e["event_id"] for e in result.events if e.get("event_id")}
    for row in table:
        for eid in row.evidence_event_ids:
            assert eid in real_ids


def test_rows_are_ordered_by_log_sequence(result):
    """批量场景：多条决策记录同时存在时，行序必须与日志顺序一致，不是任意顺序。"""
    table = mechanisms.build_table_from_result(result, agent_id=AGENT_ID)
    by_id = {e["event_id"]: e for e in result.events}
    keys = [
        (by_id[row.decision_event_id]["timestamp"], by_id[row.decision_event_id]["transaction_seq"])
        for row in table
    ]
    assert keys == sorted(keys)


# --------------------------------------------------------------------------- #
# 因果链断裂
# --------------------------------------------------------------------------- #


def test_ac306_broken_causal_chain_rejects_the_sample(result):
    """反面：因果链断裂必须拒绝整份样本，而不是补猜。"""
    corrupted = [dict(e) for e in result.events]
    for e in corrupted:
        if e.get("event_type") == "TRADE_SETTLE":
            e["caused_by_event_id"] = "e-does-not-exist"
            break
    with pytest.raises(mechanisms.CausalChainBroken):
        mechanisms.build_table(corrupted, agent_id=AGENT_ID)


def test_broken_chain_produces_no_partial_table(result):
    """反面：拒绝必须是原子的——不能先返回几行再报错，调用方不会去检查"半份表"。"""
    corrupted = [dict(e) for e in result.events]
    for e in corrupted:
        if e.get("event_type") == "ORDER_CANCELLED":
            e["caused_by_event_id"] = "e-also-does-not-exist"
            break
    try:
        mechanisms.build_table(corrupted, agent_id=AGENT_ID)
    except mechanisms.CausalChainBroken:
        pass
    else:
        pytest.fail("损坏的因果链必须抛出 CausalChainBroken，不能静默通过")
