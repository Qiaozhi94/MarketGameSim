"""0.4.2 T1126 / T1130（AC-603、AC-604）：同种子两臂、同种子重放与人类/AI 并存的因果链。

规格见 docs/features/0.4/0.4.2-human-perturbation/spec.md FR-602、TR-601、§6；
设计见 design.md §4、§5。短窗口驱动：窗口参数显式传入，不跑全窗口。
"""

from __future__ import annotations

import json

import pytest

from market_game_sim.evidence.chain_verifier import (
    ChainVerificationError,
    verify_decision_evidence_chain,
)
from market_game_sim.experiment.h2.live_market import HUMAN_AGENT, LiveMarket, ReplayError
from market_game_sim.experiment.perturbation import carrier, paired, session

S = 1_000_000_000
SEED7 = "roster-e7c9bdeeb558c5b7ed849d73e0e33704"
WARM = 20


def _roster(seed=7):
    return carrier.carrier_roster(seed)


def _record(path):
    """在载体 C 种子 7 上录一段短会话：限价、市价、撤单、再限价，然后封口。"""
    market = LiveMarket(roster=_roster(), session_path=path, wall_clock_ms=lambda: 1)
    for _ in range(WARM):
        market.advance()
    bid = int(market.view()["market"]["best_bid"])
    market.push_order(
        {"side": "BUY", "order_type": "LIMIT", "quantity_units": 3, "price_ticks": bid - 30}
    )
    market.push_order(
        {"side": "SELL", "order_type": "MARKET", "quantity_units": 2, "price_ticks": None}
    )
    market.advance()
    market.advance()
    resting = market.view()["account"]["active_orders"]
    market.push_cancel(resting[0]["order_id"])
    market.push_order(
        {"side": "SELL", "order_type": "LIMIT", "quantity_units": 1, "price_ticks": bid + 40}
    )
    for _ in range(4):
        market.advance()
    market.seal_session()
    return market


@pytest.fixture(scope="module")
def recorded(tmp_path_factory):
    path = tmp_path_factory.mktemp("session") / "session.jsonl"
    market = _record(path)
    return path, market


def _rewrite(path, check, actions):
    """改动作行后按格式重算内容哈希（封口的事件摘要保持原样）：一份格式合法、内容不同的会话。"""
    header = check.header
    seal = {**check.seal, "content_hash": session.content_hash(header, actions)}
    path.write_bytes(b"".join(session.record_line(r) for r in [header, *actions, seal]))
    rewritten = session.load_session(path)
    assert rewritten.ok, rewritten
    return rewritten


def test_baseline_arm_reproducible_point_by_point():
    """AC-603：同装配同种子的无人类基线逐点可复现"""
    window = {"window_start_ns": 20 * S, "window_end_ns": 45 * S}
    first = paired.run_baseline(_roster(), **window)
    second = paired.run_baseline(_roster(), **window)
    assert first.event_digest == second.event_digest
    assert first.price_series_digest == second.price_series_digest
    assert first.measurement == second.measurement and first.measurement is not None
    assert first.arm == paired.BASELINE and first.actions == 0
    # 反侧：换种子，轨迹就不同——可复现不是因为什么都没跑。
    other = paired.run_baseline(_roster(8), **window)
    assert other.event_digest != first.event_digest


def test_same_seed_replay_matches_seal_and_detects_tampering(recorded, tmp_path):
    """AC-603：
    同种子重放到结束序号时事件摘要与封口逐位相同；篡改 advance 序号或载荷判 REPLAY_DIVERGED
    """
    path, _ = recorded
    check = session.load_session(path)
    assert check.ok and check.status == session.SEALED
    assert [a["kind"] for a in check.actions] == ["LIMIT", "MARKET", "CANCEL", "LIMIT"]

    result = paired.replay_same_seed(check)
    assert result.ok, result
    assert result.run.event_digest == check.seal["event_digest"]
    assert list(result.run.observation_digests) == check.seal["observation_digests"]
    assert result.run.advances == check.seal["end_advance_index"]
    assert [c["outcome"] for c in result.run.cancel_outcomes] == [paired.CANCELLED]
    # 重放到同一序号的基线臂摘要不同：人类动作确实进入了事件流。
    baseline = paired.run_arm(
        _roster(),
        arm=paired.BASELINE,
        replay_mode=paired.ORIGINAL,
        end_advance_index=check.seal["end_advance_index"],
    )
    assert baseline.event_digest != check.seal["event_digest"]

    actions = [dict(a) for a in check.actions]
    shifted = [*actions[:3], {**actions[3], "advance_index": actions[3]["advance_index"] + 1}]
    tampered = _rewrite(tmp_path / "shifted.jsonl", check, shifted)
    assert paired.replay_same_seed(tampered).reason_code == paired.REPLAY_DIVERGED

    # 只改封口的一种摘要：两道比对各自独立生效（封口行不在内容哈希里，格式仍合法）。
    for key, value in (
        ("event_digest", "0" * 64),
        ("observation_digests", check.seal["observation_digests"][:-1]),
    ):
        seal = {**check.seal, key: value}
        forged = tmp_path / f"seal-{key}.jsonl"
        forged.write_bytes(
            b"".join(session.record_line(r) for r in [check.header, *check.actions, seal])
        )
        forged_check = session.load_session(forged)
        assert forged_check.ok, forged_check
        assert paired.replay_same_seed(forged_check).reason_code == paired.REPLAY_DIVERGED, key

    payload = {**actions[1], "payload": {**actions[1]["payload"], "quantity_units": 3}}
    tampered = _rewrite(tmp_path / "payload.jsonl", check, [actions[0], payload, *actions[2:]])
    assert paired.replay_same_seed(tampered).reason_code == paired.REPLAY_DIVERGED


def test_replay_preconditions_fail_closed(recorded, tmp_path):
    path, _ = recorded
    check = session.load_session(path)
    lines = path.read_bytes().split(b"\n")
    unsealed = tmp_path / "unsealed.jsonl"
    unsealed.write_bytes(b"\n".join(lines[:-2]) + b"\n")
    assert paired.replay_same_seed(session.load_session(unsealed)).reason_code == (
        paired.SESSION_UNSEALED
    )
    broken = tmp_path / "broken.jsonl"
    broken.write_bytes(path.read_bytes().replace(b'"seed":7', b'"seed":7.0', 1))
    assert paired.replay_same_seed(session.load_session(broken)).reason_code == (
        paired.SESSION_INVALID
    )
    with pytest.raises(paired.PairingError) as exc:
        paired.load_treatment(broken)
    assert exc.value.code == paired.SESSION_INVALID

    header = {**check.header, "seed": 8}
    seal = {**check.seal, "content_hash": session.content_hash(header, check.actions)}
    wrong_seed = tmp_path / "seed.jsonl"
    wrong_seed.write_bytes(b"".join(session.record_line(r) for r in [header, *check.actions, seal]))
    assert paired.replay_same_seed(session.load_session(wrong_seed)).reason_code == (
        paired.ROSTER_MISMATCH
    )


def test_actions_due_before_the_current_advance_cannot_be_delivered(recorded):
    """动作序号已过即判失败并给稳定原因码，不跳过动作、不改写时点。"""
    path, _ = recorded
    check = session.load_session(path)
    market = LiveMarket(roster=_roster())
    for _ in range(WARM + 1):
        market.advance()
    with pytest.raises(ReplayError) as exc:
        market.schedule_actions(check.actions)
    assert exc.value.code == "REPLAY_ACTION_LATE"


def test_owner_and_ai_orders_resolve_to_agent_decide_in_batch(recorded):
    """AC-604：
    多条记录并存时 chain_verifier 对含 owner 下单与撤单的事件流通过，
    owner 与 AI 委托的 decision_event_id 都解析到 AGENT_DECIDE，参与者类别可区分
    """
    _, market = recorded
    records = market.kernel.committed_records
    verify_decision_evidence_chain(records)
    by_id = {r["event_id"]: r for r in records}
    arrivals = [
        r for r in records if r["event_type"] == "ORDER_ARRIVAL" and r.get("origin") == "AGENT"
    ]
    owner = [r for r in arrivals if r["agent_id"] == HUMAN_AGENT]
    ai = [r for r in arrivals if r["agent_id"] != HUMAN_AGENT]
    assert [r["action"] for r in owner] == ["SUBMIT", "SUBMIT", "CANCEL", "SUBMIT"]
    assert len({r["agent_id"] for r in ai}) > 10, "批量场景：多个 AI 代理同时下单"
    window = (owner[0]["timestamp"], owner[-1]["timestamp"])
    assert any(window[0] <= r["timestamp"] <= window[1] for r in ai), "人类与 AI 委托交错并存"
    for arrival in arrivals:
        decide = by_id[arrival["decision_event_id"]]
        assert decide["event_type"] == "AGENT_DECIDE"
        assert decide["agent_id"] == arrival["agent_id"]
        observe = by_id[decide["observation_event_id"]]
        assert observe["event_type"] == "AGENT_OBSERVE"
        participant = decide["internal_state"].get("participant_class")
        if arrival["agent_id"] == HUMAN_AGENT:
            assert participant == "human"
        else:
            assert participant is None and decide["internal_state"].get("strategy_family_id")
    # 撮合路径一致：owner 的市价单与 AI 委托在同一撮合里成交。
    owner_trades = [
        r
        for r in records
        if r["event_type"] == "TRADE_SETTLE"
        and HUMAN_AGENT in (r["taker_agent_id"], r["maker_agent_id"])
    ]
    assert owner_trades and all(
        {r["taker_agent_id"], r["maker_agent_id"]} - {HUMAN_AGENT} for r in owner_trades
    )

    # 反侧：owner 委托的决策外键被改坏，因果链校验即失败。
    broken = [dict(r) for r in records]
    target = next(i for i, r in enumerate(broken) if r["event_id"] == owner[2]["event_id"])
    broken[target]["decision_event_id"] = "e0_0"
    with pytest.raises(ChainVerificationError):
        verify_decision_evidence_chain(broken)


def test_cli_replay_and_pair(recorded, tmp_path):
    """CLI：replay 输出与封口比对的结果；pair 在没有钉住的预注册时 fail closed。"""
    from market_game_sim.experiment.perturbation import preregistration as pr

    path, _ = recorded
    out = tmp_path / "replay.json"
    assert paired.main(["replay", "--session", str(path), "--out", str(out)]) == 0
    payload = json.loads(out.read_text())
    assert payload["ok"] is True and payload["run"]["replay_mode"] == paired.SAME_SEED_REPLAY
    assert payload["run"]["evidence_class"] == "experiment-preview"

    forged = tmp_path / "forged.jsonl"
    check = session.load_session(path)
    seal = {**check.seal, "event_digest": "0" * 64}
    forged.write_bytes(
        b"".join(session.record_line(r) for r in [check.header, *check.actions, seal])
    )
    assert paired.main(["replay", "--session", str(forged), "--out", str(out)]) == 1
    assert json.loads(out.read_text())["reason_code"] == paired.REPLAY_DIVERGED

    if pr.PREREGISTRATION_SHA256 is None:
        with pytest.raises(pr.PreregistrationError):
            paired.main(["pair", "--session", str(path), "--out", str(tmp_path / "e.json")])
