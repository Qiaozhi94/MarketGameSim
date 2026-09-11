"""T917：所有者会话客户端与内核外生决策缝。

覆盖三条主线：

* **缝的行为**：外生源接住 belief-0 的 decide、决定路由进 ``ORDER_ARRIVAL``、
  运行时界把观察周期截断在 60 窗；没有缝时一切照旧（既有 2546 条测试即反例）。
* **会话合同**：完成才准入（admitted）、训练永不准入、迟到输入进 ``late_rejected``
  且窗口落定 ``NO_ACTION``、冻结顺序不许挑、重复/并发开桌被拒。
* **解盲**：会话工件里没有任何结果字段；重放从记录的决定还原同一事件流。
"""

from __future__ import annotations

import io
import json
import time

import pytest

from market_game_sim.experiment.h2 import (
    artifacts,
    evidence_guard,
    owner_client,
    session,
)
from market_game_sim.experiment.runner import run_one

FORBIDDEN_OUTCOME_FIELDS = ("severity", "effect", "p_value", "ci_low", "holm")


@pytest.fixture(autouse=True)
def _clean_guard_ledger():
    evidence_guard.reset()
    yield
    evidence_guard.reset()


def _buy(qty: int) -> dict:
    return {"kind": "MARKET", "side": "buy", "quantity_units": qty}


@pytest.fixture(scope="module")
def assignments():
    return artifacts.load_assignments()


# --------------------------------------------------------------------------- #
# 正式会话：完成、准入、决定记录
# --------------------------------------------------------------------------- #


def test_formal_session_completes_admits_and_records(tmp_path, assignments):
    payload = owner_client.run_owner_scenario(
        "formal",
        0,
        owner_client.scripted_input([_buy(2)]),
        out_root=tmp_path,
        assignments=assignments,
    )
    assert payload["stage"] == "formal"
    assert payload["scenario_id"] == assignments["owner_scenario_order"][0]
    assert payload["seed"] == artifacts.ai_seed_for_scenario(assignments, payload["scenario_id"])
    assert payload["session"]["final_state"] == str(session.SessionState.COMPLETED)
    # 真实窗数由共享事务预算涌现（~32/33 < 名义 60），工件记录实际值。
    windows = payload["session"]["completed_windows"]
    assert 0 < windows < payload["window_contract"]["windows_per_scenario"]
    assert len(payload["session"]["decisions"]) == windows
    assert payload["admitted"] is True
    assert payload["session"]["late_rejected_total"] == 0
    first = payload["session"]["decisions"][0]
    assert first["submitted"] is True and first["side"] == "buy"
    assert payload["session"]["decisions"][1]["decision"] == session.NO_ACTION
    assert evidence_guard.admitted_count() == 1


def test_formal_artifact_is_blinded(tmp_path, assignments):
    payload = owner_client.run_owner_scenario(
        "formal",
        0,
        owner_client.scripted_input([_buy(1)]),
        out_root=tmp_path,
        assignments=assignments,
    )
    blob = json.dumps(payload, ensure_ascii=False)
    for field in FORBIDDEN_OUTCOME_FIELDS:
        assert field not in blob, f"会话工件泄漏了结果字段 {field}"


def test_owner_order_reaches_the_kernel(tmp_path, assignments):
    """缝的正向路径：belief-0 的 decide 带着窗口决定，订单真实进队。"""
    table = assignments
    scenario_id = table["owner_scenario_order"][0]
    seed = artifacts.ai_seed_for_scenario(table, scenario_id)
    driver = owner_client._SessionDriver(60, owner_client.scripted_input([_buy(2)]))
    result = run_one(
        owner_client._owner_config(seed),
        world_overrides={
            "external_decision_sources": {"belief-0": driver.source},
            "run_horizon_ns": 60_000_000_000,
        },
    )
    decides = [
        event
        for event in result.events
        if event.get("event_type") == "AGENT_DECIDE" and event.get("agent_id") == "belief-0"
    ]
    assert decides, "belief-0 的 decide 事件缺失"
    evidence = decides[0]["decision_evidence"]
    assert evidence["goal_model_id"] == "owner_manual_v1"
    assert evidence["trigger_provenance"] == "ENDOGENOUS_AGENT"
    arrivals = [
        event
        for event in result.events
        if event.get("event_type") == "ORDER_ARRIVAL" and event.get("intent_id") == "owner-w00"
    ]
    assert len(arrivals) == 1
    assert arrivals[0]["side"] == "BUY" and arrivals[0]["quantity_units"] == 2
    assert arrivals[0]["agent_id"] == "belief-0"


def test_run_horizon_and_budget_bound_the_scenario(tmp_path, assignments):
    """窗数上界的两条来源：共享事务预算先绑（~33 窗），运行时界兜底（60 窗）。

    观察周期绝不越过运行时界；实际窗数与驱动器记录、内核终止状态一致。
    """
    driver = owner_client._SessionDriver(60, owner_client.scripted_input([]))
    horizon_ns = 60_000_000_000
    result = run_one(
        owner_client._owner_config(40_000),
        world_overrides={
            "external_decision_sources": {"belief-0": driver.source},
            "run_horizon_ns": horizon_ns,
        },
    )
    observes = [
        event
        for event in result.events
        if event.get("event_type") == "AGENT_OBSERVE" and event.get("agent_id") == "belief-0"
    ]
    assert 0 < len(observes) <= 60
    assert all(event["timestamp"] < horizon_ns for event in observes)
    assert len(observes) == len(driver.records)
    assert result.terminated == "COMPLETED"


# --------------------------------------------------------------------------- #
# 迟到输入、训练隔离、前置条件
# --------------------------------------------------------------------------- #


def test_late_input_is_rejected_and_window_settles_no_action(tmp_path, assignments):
    """窗 0 给 1ms 窗口、5ms 才回答：WINDOW_CLOSED，窗口落定 NO_ACTION。"""

    def slow_buy(window_index, info, window):
        if window_index == 0:
            time.sleep(0.005)
            return _buy(1)
        return None

    payload = owner_client.run_owner_scenario(
        "formal",
        0,
        slow_buy,
        out_root=tmp_path,
        window_duration_ns=1_000_000,
        assignments=assignments,
    )
    first = payload["session"]["decisions"][0]
    assert first["submitted"] is False
    assert first["decision"] == session.NO_ACTION
    assert first["late_rejected"] == ["owner-w00"]
    assert payload["session"]["late_rejected_total"] == 1
    assert payload["session"]["final_state"] == str(session.SessionState.COMPLETED)


def test_training_stays_out_of_formal_evidence(tmp_path):
    before = evidence_guard.admitted_count()
    payload = owner_client.run_owner_scenario(
        "training",
        0,
        owner_client.scripted_input([_buy(1)]),
        out_root=tmp_path,
    )
    assert payload["stage"] == "training"
    assert payload["seed"] == owner_client.TRAINING_SEED_BASE
    assert payload["admitted"] is False
    assert payload["references_digests"] is None
    assert evidence_guard.admitted_count() == before, "训练会话不得进入正式证据账本"


def test_frozen_order_cannot_be_skipped(tmp_path, assignments):
    with pytest.raises(owner_client.OwnerClientError, match="冻结顺序被跳过"):
        owner_client.run_owner_scenario(
            "formal",
            1,
            owner_client.scripted_input([]),
            out_root=tmp_path,
            assignments=assignments,
        )


def test_formal_scenario_cannot_be_replayed_as_new(tmp_path, assignments):
    owner_client.run_owner_scenario(
        "formal",
        0,
        owner_client.scripted_input([]),
        out_root=tmp_path,
        assignments=assignments,
    )
    with pytest.raises(owner_client.OwnerClientError, match="不得重打"):
        owner_client.run_owner_scenario(
            "formal",
            0,
            owner_client.scripted_input([]),
            out_root=tmp_path,
            assignments=assignments,
        )


def test_concurrent_session_is_locked_out(tmp_path, assignments):
    (tmp_path / ".scenario-00.lock").touch()
    with pytest.raises(owner_client.OwnerClientError, match="活动会话"):
        owner_client.run_owner_scenario(
            "formal",
            0,
            owner_client.scripted_input([]),
            out_root=tmp_path,
            assignments=assignments,
        )


def test_protocol_hash_drift_is_fail_closed(tmp_path, assignments):
    drifted = dict(assignments)
    drifted["protocol_hash"] = "0" * 64
    with pytest.raises(ValueError, match="分配表协议哈希与冻结归档不一致"):
        owner_client.run_owner_scenario(
            "formal",
            0,
            owner_client.scripted_input([]),
            out_root=tmp_path,
            assignments=drifted,
        )
    assert evidence_guard.partial_writes() == []
    assert not list(tmp_path.rglob("scenario-*.json"))


def test_owner_abort_keeps_audit_artifact_without_admission(tmp_path, assignments):
    def aborter(window_index, info, window):
        if window_index == 3:
            raise owner_client.OwnerAbort("测试中止")
        return None

    payload = owner_client.run_owner_scenario(
        "formal",
        0,
        aborter,
        out_root=tmp_path,
        assignments=assignments,
    )
    assert payload["session"]["final_state"] == str(session.SessionState.ABORTED)
    assert payload["admitted"] is False
    assert payload["market_run"]["terminated"] == "ABORTED"
    assert len(payload["session"]["decisions"]) == 3


# --------------------------------------------------------------------------- #
# 重放与交互输入
# --------------------------------------------------------------------------- #


def test_replay_reproduces_recorded_run(tmp_path, assignments):
    payload = owner_client.run_owner_scenario(
        "formal",
        0,
        owner_client.scripted_input(
            [_buy(2), None, {"kind": "MARKET", "side": "sell", "quantity_units": 1}]
        ),
        out_root=tmp_path,
        assignments=assignments,
    )
    assert owner_client.replay_owner_scenario(payload) is True


def test_interactive_input_parses_and_aborts():
    stream = io.StringIO("b 3\n\nq\n")
    seen: list[str] = []
    ask = owner_client.InteractiveInput(stream, render=seen.append)
    window = session.open_window(0, duration_ns=2_000_000_000)
    assert ask(0, {}, window) == {"kind": "MARKET", "side": "buy", "quantity_units": 3}
    window = session.open_window(1, duration_ns=2_000_000_000)
    assert ask(1, {}, window) == {"kind": "NO_ACTION"}
    window = session.open_window(2, duration_ns=2_000_000_000)
    with pytest.raises(owner_client.OwnerAbort):
        ask(2, {}, window)


def test_interactive_input_rejects_garbage_then_parses():
    stream = io.StringIO("x 9\nsell 0\ns 4\n")
    ask = owner_client.InteractiveInput(stream, render=lambda *_: None)
    window = session.open_window(0, duration_ns=2_000_000_000)
    assert ask(0, {}, window) == {"kind": "MARKET", "side": "sell", "quantity_units": 4}


def test_parse_order_rejects_bad_input():
    assert owner_client._parse_order("b") is None
    assert owner_client._parse_order("b x") is None
    assert owner_client._parse_order("b 0") is None
    assert owner_client._parse_order("x 5") is None
    assert owner_client._parse_order("b 5") == {
        "kind": "MARKET",
        "side": "buy",
        "quantity_units": 5,
    }
