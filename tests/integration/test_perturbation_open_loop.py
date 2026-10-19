"""0.4.2 T1129（FR-602 / IR-601 / DR-601 / AC-610）：开环跨种子回放与正式配对入口。

规格见 docs/features/0.4/0.4.2-human-perturbation/spec.md FR-602、§3、§6；设计见 design.md §4。
短窗口驱动（窗口参数显式传入），不跑全窗口。
"""

from __future__ import annotations

import json

import pytest

from market_game_sim.experiment.h2.live_market import HUMAN_AGENT, LiveMarket
from market_game_sim.experiment.perturbation import carrier, paired, session
from market_game_sim.experiment.perturbation import preregistration as pr
from market_game_sim.metrics.stability_effect import METRIC_IDS, REPORTED

S = 1_000_000_000
START, END = 10 * S, 125 * S  # 含一个完整分钟（60—120 s），大波动频次才有分母


def _header(session_id="s-open"):
    return {
        "format_version": 1,
        "session_id": session_id,
        "arm": "human",
        "replay_mode": "original",
        "roster_id": carrier.carrier_roster(7).roster_id,
        "seed": 7,
        "engine_config_digest": "a" * 32,
        "evidence_class": "experiment-preview",
        "run_mode": "interactive",
    }


def _crafted(path):
    """两笔限价单：一笔远离盘口（会挂着），一笔越过对手价（会立即成交）；随后各撤一次。"""
    writer = session.SessionWriter.create(path, _header())
    for kind, payload, advance in (
        ("LIMIT", {"side": "BUY", "quantity_units": 2, "price_ticks": 9_000}, 20),
        ("LIMIT", {"side": "BUY", "quantity_units": 1, "price_ticks": 11_000}, 20),
        ("MARKET", {"side": "SELL", "quantity_units": 1}, 21),
        ("CANCEL", {"target_action_seq": 1}, 23),
        ("CANCEL", {"target_action_seq": 2}, 23),
    ):
        writer.append_action(advance_index=advance, kind=kind, payload=payload, wall_clock_ms=1)
    writer.close()
    return session.load_session(path)


def test_open_loop_replay_to_window_end_and_rebuildable_pairs(tmp_path):
    """AC-610：按 advance 序号投到预注册种子并推进到 5700 s，配对集合可由预注册与会话哈希重建"""
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    check = _crafted(sessions / "a.jsonl")
    base = paired.run_baseline(carrier.carrier_roster(8), window_start_ns=START, window_end_ns=END)
    run = paired.replay_open_loop(check, 8, window_start_ns=START, window_end_ns=END)
    assert run.replay_mode == paired.OPEN_LOOP_REPLAY and run.seed == 8
    assert run.logical_ns >= END, "推进到窗口终点"
    assert run.measurement is not None and base.measurement is not None
    assert run.event_digest != base.event_digest
    # 动作按序号投递：每条动作在本种子上都有一条 owner 观察，数量与顺序一致。
    assert [d["action_seq"] for d in run.observation_digests] == [1, 2, 3, 4, 5]

    # 正式配对：只读预注册；同一预注册 + 同一会话哈希重建出同一配对集合与报告。
    power = {
        "seeds": list(pr.POWER_SEEDS),
        "sigma_b": dict.fromkeys(METRIC_IDS, 0.05),
        "carrier": {
            "count": carrier.CARRIER_COUNT,
            "sensitivity_x1000": carrier.CARRIER_SENSITIVITY_X1000,
            "disclaimer": carrier.CARRIER_DISCLAIMER,
        },
    }
    power_path = tmp_path / "power.json"
    power_path.write_text(json.dumps(power))
    built = pr.build_preregistration(
        power,
        pr.file_sha256(power_path),
        pr.collect_sessions(sessions),
        dict.fromkeys(METRIC_IDS, 0.1),
        open_loop_seeds=[8, 9],
        min_valid_pairs=2,
    )
    prereg_path = tmp_path / "prereg.json"
    prereg_path.write_text(json.dumps(built))
    kwargs = {
        "preregistration_path": prereg_path,
        "pinned_sha256": pr.file_sha256(prereg_path),
        "power_report_path": power_path,
        "window_start_ns": START,
        "window_end_ns": END,
    }
    report = paired.run_pairing(sessions / "a.jsonl", **kwargs)
    again = paired.run_pairing(sessions / "a.jsonl", **kwargs)
    assert report["content_hash"] == again["content_hash"]
    assert report["pair_set_id"] == again["pair_set_id"]
    assert [p["seed"] for p in report["pairs"]] == [8, 9]
    assert {p["replay_mode"] for p in report["pairs"]} == {paired.OPEN_LOOP_REPLAY}
    assert report["treatment_session_hash"] == check.content_hash
    assert report["preregistration_sha256"] == kwargs["pinned_sha256"]
    assert report["label"] == paired.OPEN_LOOP_LABEL == "固定订单流扰动"
    assert report["verdict"] == REPORTED and report["valid_pairs"] == 2
    assert report["original_cases"] == [
        {
            "session_id": "s-open",
            "seed": 7,
            "replay": paired.SESSION_UNSEALED,
            "window_complete": False,
            "out_of_window_actions": 0,
        }
    ]

    # 反侧：预注册之后录的会话不在其中，配对入口拒绝。
    late = sessions / "late.jsonl"
    session.SessionWriter.create(late, _header("s-late")).close()
    with pytest.raises(pr.PreregistrationError) as exc:
        paired.run_pairing(late, **kwargs)
    assert exc.value.code == pr.TREATMENT_NOT_PREREGISTERED


def test_missing_cancel_target_records_reason_code(tmp_path):
    """AC-610：
    撤单按 target_action_seq 解析——原场撤掉的挂单在开环种子上仍挂着时照常撤掉，
    已成交或被拒时记录原因码而不跳过（正反两侧）
    """
    check = _crafted(tmp_path / "a.jsonl")
    run = paired.replay_open_loop(check, 9, window_start_ns=START, window_end_ns=END)
    assert run.cancel_outcomes == (
        {"action_seq": 4, "target_action_seq": 1, "outcome": paired.CANCELLED},
        {"action_seq": 5, "target_action_seq": 2, "outcome": paired.TARGET_NOT_ACTIVE},
    )
    # 两条撤单都进了内核：被撤目标是本次运行生成的 order_id，不是原场的编号。
    market = LiveMarket(roster=carrier.carrier_roster(9))
    market.schedule_actions(check.actions)
    for _ in range(26):
        market.advance()
    records = market.kernel.committed_records
    submits = [
        r["order_id"]
        for r in records
        if r["event_type"] == "ORDER_ARRIVAL"
        and r["agent_id"] == HUMAN_AGENT
        and r["action"] == "SUBMIT"
    ]
    cancels = [
        r["target_order_id"]
        for r in records
        if r["event_type"] == "ORDER_ARRIVAL"
        and r["agent_id"] == HUMAN_AGENT
        and r["action"] == "CANCEL"
    ]
    assert cancels == submits[:2]
    assert not market.view()["account"]["active_orders"]


def test_open_loop_failure_modes_are_recorded_not_skipped(tmp_path):
    check = _crafted(tmp_path / "a.jsonl")
    # 序号已过无法投递：该种子判失败并留原因码。
    late = session.SessionWriter.create(tmp_path / "b.jsonl", _header("s-b"))
    late.append_action(
        advance_index=0,
        kind="MARKET",
        payload={"side": "BUY", "quantity_units": 1},
        wall_clock_ms=1,
    )
    late.close()
    pair = paired._pair_seed((tmp_path / "b.jsonl", 8, START, END))
    assert pair["human"]["run_digest"] is not None, "序号 0 仍可投递"
    assert pair["baseline"]["measurement"] is not None
    # 窗口外动作如实计数：窗口起点晚于全部动作时它们都在窗口外。
    run = paired.replay_open_loop(check, 8, window_start_ns=40 * S, window_end_ns=END)
    assert run.out_of_window_actions == 5
    inside = paired.replay_open_loop(check, 8, window_start_ns=START, window_end_ns=END)
    assert inside.out_of_window_actions == 0
    with pytest.raises(paired.PairingError):
        paired.replay_open_loop(session.validate_session(b""), 8, window_start_ns=START)
