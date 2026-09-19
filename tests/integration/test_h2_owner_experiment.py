"""0.3.2 训练实验端到端：Web 委托桥接驱动真实 H2 训练场景（tasks T937/T939 机制层）。

真实链路：``run_owner_scenario("training", ...)``（冻结协议 + assignment 种子 +
``run_one`` 真实内核 + 事件哈希工件），owner 委托经 :class:`WebOrderBridge` 从
HTTP 层进入决策缝。窗口按 ADR-006 自由连续交易：1:1 节拍、非阻塞队列、
余单顺延、OWNER_ABORT 终态。
"""

from __future__ import annotations

import http.client
import json
import threading
import time
from pathlib import Path

from market_game_sim.experiment.h2.owner_experiment import (
    WebOrderBridge,
    create_experiment_server,
    run_scenario_in_thread,
    web_decision_ask,
)


def _wait_done(bridge: WebOrderBridge, timeout: float = 120.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if bridge.done:
            return
        time.sleep(0.1)
    raise AssertionError("场景超时未完成")


def test_web_orders_drive_real_training_scenario(tmp_path: Path):
    bridge = WebOrderBridge(wait_start=False)
    run_scenario_in_thread(bridge, position=0, out_root=tmp_path, window_wall_seconds=0.02)
    time.sleep(0.1)
    bridge.push_order("buy", 2)
    time.sleep(0.05)
    bridge.push_order("sell", 1)
    _wait_done(bridge)

    assert bridge.error is None, bridge.error
    artifact = Path(bridge.artifact)
    assert artifact.is_file(), bridge.artifact
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["stage"] == "training"
    assert payload["session"]["final_state"] == "completed"
    submitted = [d for d in payload["session"]["decisions"] if d["submitted"]]
    assert len(submitted) >= 2, "至少两条 Web 委托应映射为规范决定"
    windows = [d["window_index"] for d in submitted]
    assert windows == sorted(set(windows)), "余单必须顺延到不同窗口，不得同窗重复"
    assert payload["market_run"]["events_sha256"]


def test_abort_writes_audit_artifact(tmp_path: Path):
    bridge = WebOrderBridge(wait_start=False)
    run_scenario_in_thread(bridge, position=1, out_root=tmp_path, window_wall_seconds=0.02)
    time.sleep(0.3)
    bridge.abort_requested = True
    _wait_done(bridge)

    assert bridge.aborted is True
    artifact = Path(bridge.artifact)
    assert artifact.is_file(), "中止会话必须写审计工件"
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["session"]["final_state"] == "aborted"
    assert payload["admitted"] is False, "中止/训练会话永不准入"


def test_experiment_http_smoke(tmp_path: Path):
    bridge = WebOrderBridge()
    server = create_experiment_server(bridge, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    address, port = server.server_address[:2]
    try:
        conn = http.client.HTTPConnection(address, port)
        conn.request("GET", "/")
        response = conn.getresponse()
        page = response.read().decode("utf-8")
        assert response.status == 200 and "训练实验" in page
        conn.close()

        conn = http.client.HTTPConnection(address, port)
        conn.request(
            "POST",
            "/api/v1/h2/owner/experiment/orders",
            json.dumps({"side": "buy", "quantity_units": 3}),
            {"Content-Type": "application/json"},
        )
        body = json.loads(conn.getresponse().read())
        conn.close()
        assert body["queued"] is True
        assert bridge.pop_order() == {"kind": "MARKET", "side": "buy", "quantity_units": 3}

        conn = http.client.HTTPConnection(address, port)
        conn.request(
            "POST",
            "/api/v1/h2/owner/experiment/orders",
            json.dumps({"side": "sideways", "quantity_units": 1}),
            {"Content-Type": "application/json"},
        )
        body = json.loads(conn.getresponse().read())
        conn.close()
        assert body["queued"] is False, "非法方向不得入队"
    finally:
        server.shutdown()
        server.server_close()


def test_web_ask_respects_slot_pacing():
    """1:1 节拍：窗内无委托时 ask 应走满窗时长；委托入队则提前收口。"""

    bridge = WebOrderBridge()
    ask = web_decision_ask(bridge, window_wall_seconds=0.2)
    assert bridge.wait_start is True, "构造默认应等待开始（就绪门）"
    bridge.wait_start = False
    start = time.monotonic()
    assert ask(0, {}, None) is None
    elapsed = time.monotonic() - start
    assert elapsed >= 0.18, "空窗必须走满节拍（1:1 压缩比）"

    bridge.push_order("sell", 2)
    start = time.monotonic()
    decision = ask(1, {}, None)
    assert time.monotonic() - start <= 0.25
    assert decision == {"kind": "MARKET", "side": "sell", "quantity_units": 2}


def test_bridge_observes_book_depth_and_snapshots(tmp_path: Path):
    """每窗回调应从内核 world 取盘口（≤10 档）并落采样快照。"""

    bridge = WebOrderBridge(wait_start=False)
    run_scenario_in_thread(bridge, position=0, out_root=tmp_path, window_wall_seconds=0.02)
    time.sleep(0.3)
    bridge.push_order("buy", 2)
    _wait_done(bridge)

    assert bridge.snapshots, "应有逐窗采样快照"
    assert bridge.depth["bids"] and bridge.depth["asks"], "盘口深度缺失"
    assert all(len(lv) == 2 for lv in bridge.depth["bids"][:3])
    assert bridge.snapshots[0]["window"] == 1, "快照必须从窗口 1 开始编号"
