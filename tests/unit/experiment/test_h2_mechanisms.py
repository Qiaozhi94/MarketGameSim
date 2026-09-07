"""AC-306：机制指标的定义与缺失语义（单元层）。

T913 已实现，xfail 骨架相应摘除。核心不变量是缺失语义不能与零值互换：只有决策事件本身
无法解析才是缺失，决策已解析但没有相应订单/成交是真实的零观测——这条区分是本文件的
主线，逐个机制正反各测一遍。

冻结合同：`docs/experiments/H2-dual-track-contract.json`
"""

from __future__ import annotations

import pytest

from market_game_sim.experiment.h2 import mechanisms

MECHANISMS = mechanisms.MECHANISMS


# --------------------------------------------------------------------------- #
# 口径定义只引用指标字典
# --------------------------------------------------------------------------- #


def test_ac306_three_mechanisms_come_from_the_metrics_dictionary():
    """机制口径只能引用指标字典的版本与 ID，不得本地重定义。"""
    for name in MECHANISMS:
        spec = mechanisms.definition(name)
        assert spec.dictionary_version
        assert spec.formula_source == "docs/research/metrics-dictionary.md"
        assert spec.metric_id.startswith("H2-M-")


def test_unknown_mechanism_name_is_rejected():
    with pytest.raises(mechanisms.MechanismsError, match="未知机制指标"):
        mechanisms.definition("teleportation")


# --------------------------------------------------------------------------- #
# 缺失语义：只有决策事件本身无法解析才是缺失
# --------------------------------------------------------------------------- #


def test_ac306_untraceable_value_is_missing_not_imputed():
    """缺少决定事件引用时标记缺失，不推断也不手工补值。"""
    events, missing_id = mechanisms.sample_without_decision_event()
    value = mechanisms.compute(events, "aggressive_orders", missing_id)
    assert value.is_missing and value.imputed is False
    assert value.value is None


@pytest.mark.parametrize("mechanism", MECHANISMS)
def test_missing_decision_is_missing_for_every_mechanism(mechanism):
    """反面对照：缺失路径不是只对 aggressive_orders 生效，三个机制都要一致。"""
    events, missing_id = mechanisms.sample_without_decision_event()
    value = mechanisms.compute(events, mechanism, missing_id)
    assert value.is_missing is True
    assert value.value is None


def test_decision_with_no_intents_is_a_real_zero_not_missing():
    """反面：决策已解析但没有产生任何订单——这是"决定不动作"的真实观测，不是缺失。

    这条锁定了一个真实修过的 bug：早期实现把"零订单"也当成缺失，会让一个正常的
    "观察后不交易"决策在报告里凭空消失，而不是显示为一次没有激进行为的决策。
    """
    events = [
        {
            "event_type": "AGENT_DECIDE",
            "event_id": "d1",
            "agent_id": "belief-0",
            "timestamp": 0,
            "transaction_seq": 1,
            "record_index": 0,
        }
    ]
    for mechanism in MECHANISMS:
        value = mechanisms.compute(events, mechanism, "d1")
        assert value.is_missing is False
        assert value.value == 0.0


def test_unresolvable_decision_type_mismatch_is_missing():
    """decision_event_id 指向一个存在但类型不对的事件，同样算无法解析。"""
    events = [
        {
            "event_type": "MARKET_DATA_PUBLISH",
            "event_id": "not-a-decision",
            "timestamp": 0,
            "transaction_seq": 1,
            "record_index": 0,
        }
    ]
    value = mechanisms.compute(events, "risk_reduction", "not-a-decision")
    assert value.is_missing is True


def test_unknown_mechanism_in_compute_is_rejected():
    events, missing_id = mechanisms.sample_without_decision_event()
    with pytest.raises(mechanisms.MechanismsError, match="未知机制指标"):
        mechanisms.compute(events, "teleportation", missing_id)
