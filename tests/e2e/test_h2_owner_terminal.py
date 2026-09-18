"""0.3.2 [TEST] 层 2 旅程验收轨（tasks T949-T952）。

编写早、执行晚：夹具随 T932 立起（本文件即红灯夹具载体），收尾全量执行作为
E2 验收。交互语义已由原型行为门（tests/unit/test_terminal_prototype_behavior.py）
锁定；本轨将其提升为真实现终端（HTTP + 引擎路径）上的旅程断言。

T951/T952 中依赖真人训练/正式场景的部分由 owner 四天采集完成（tasks T939-T941），
本文件锁定其机制层：preview fail-closed、采集白名单、OWNER_ABORT 终态、
证据导出与机器校验闭环。
"""

from __future__ import annotations

import http.client
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from market_game_sim.experiment.h2.owner_web import (
    OwnerWebSession,
    PreviewGateBlocked,
    create_owner_server,
)


def _start_server(session: OwnerWebSession) -> tuple[str, threading.Thread, ThreadingHTTPServer]:
    server = create_owner_server(session, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    address, port = server.server_address[:2]
    return f"http://{address}:{port}", thread, server


def _get(base: str, path: str) -> dict:
    conn = http.client.HTTPConnection(base.split("//")[1])
    conn.request("GET", path)
    body = json.loads(conn.getresponse().read())
    conn.close()
    return body


def _post(base: str, path: str, payload: dict) -> dict:
    conn = http.client.HTTPConnection(base.split("//")[1])
    conn.request("POST", path, json.dumps(payload), {"Content-Type": "application/json"})
    body = json.loads(conn.getresponse().read())
    conn.close()
    return body


def _order(order_id: str, side: str, order_type: str, qty: int, price: int | None) -> dict:
    return {
        "client_request_id": f"journey-{order_id}",
        "order_id": order_id,
        "side": side,
        "order_type": order_type,
        "quantity_units": qty,
        "price_ticks": price,
    }


def test_journey_market_visibility(tmp_path: Path):
    """旅程一：新进程打开 loopback 页面（无外部网络）→ 行情可见 → 周期切换有数据。"""

    session = OwnerWebSession(stage="free", session_id="jt-401")
    base, _thread, server = _start_server(session)
    try:
        conn = http.client.HTTPConnection(base.split("//")[1])
        conn.request("GET", "/")
        response = conn.getresponse()
        page = response.read().decode("utf-8")
        assert response.status == 200
        assert "Owner" in page and "MarketGame" in page
        conn.close()

        view = _get(base, "/api/v1/h2/owner/session")
        assert view["market"]["best_bid"] is not None
        assert view["market"]["best_ask"] is not None
        kline_keys = {int(key) for key in view["market"]["klines"]}
        assert kline_keys == set(view["freeze"]["kline_periods_ns"]) | {86_400_000_000}

        # 未成交前 K 线可以无完成 bar（空态不造假：页面显示数据不足而非占位蜡烛）
        pre_trade_bars = view["market"]["klines"]["60000000000"]
        session.place_order(_order("jt-401-o1", "BUY", "MARKET", 1, None), "jt-401-r1")
        view_after = _get(base, "/api/v1/h2/owner/session")
        post_trade_bars = view_after["market"]["klines"]["60000000000"]
        assert len(post_trade_bars) >= len(pre_trade_bars)
        assert view_after["market"]["recent_trades"]
    finally:
        server.shutdown()
        server.server_close()


def test_journey_free_trading():
    """旅程二：市价成交 → 限价挂单 → 撤单 → 非法拒绝 → 幂等不重复。"""

    session = OwnerWebSession(stage="free", session_id="jt-402")
    base, _thread, server = _start_server(session)
    try:
        filled = _post(
            base, "/api/v1/h2/owner/session/orders", _order("o1", "BUY", "MARKET", 2, None)
        )
        assert filled["accepted"] is True
        view = _get(base, "/api/v1/h2/owner/session")
        assert view["account"]["position_units"] > 0

        resting = _post(
            base, "/api/v1/h2/owner/session/orders", _order("o2", "BUY", "LIMIT", 1, 9_000)
        )
        assert resting["accepted"] is True
        view = _get(base, "/api/v1/h2/owner/session")
        assert any(o["order_id"] == "o2" for o in view["account"]["active_orders"])

        cancelled = _post(
            base,
            "/api/v1/h2/owner/session/cancels",
            {"client_request_id": "jt-402-c1", "order_id": "o2"},
        )
        assert cancelled["accepted"] is True
        unknown = _post(
            base,
            "/api/v1/h2/owner/session/cancels",
            {"client_request_id": "jt-402-c2", "order_id": "o2"},
        )
        assert unknown["reason_code"] == "UNKNOWN_ORDER"

        invalid = _post(
            base, "/api/v1/h2/owner/session/orders", _order("o3", "BUY", "LIMIT", 0, 9_000)
        )
        assert invalid["reason_code"] == "INVALID_INPUT"

        replay_a = _post(
            base, "/api/v1/h2/owner/session/orders", _order("o4", "BUY", "MARKET", 1, None)
        )
        replay_b = _post(
            base, "/api/v1/h2/owner/session/orders", _order("o4", "BUY", "MARKET", 1, None)
        )
        assert replay_a["accepted"] and replay_b["accepted"]
        assert replay_b["input_seq"] == replay_a["input_seq"], "幂等重放不得重复成交"
    finally:
        server.shutdown()
        server.server_close()


def test_journey_gating_and_collection(tmp_path: Path):
    """旅程三：preview 未过拒绝采集入口 → 通过后采集态白名单隐藏 → OWNER_ABORT 终态。"""

    with pytest.raises(PreviewGateBlocked):
        OwnerWebSession(stage="training", preview_dir=None)

    evidence = tmp_path / "preview-bundle"
    evidence.mkdir()
    (evidence / "manifest.json").write_text("{}", encoding="utf-8")
    session = OwnerWebSession(stage="training", preview_dir=evidence, session_id="jt-403")
    base, _thread, server = _start_server(session)
    try:
        view = _get(base, "/api/v1/h2/owner/session")
        assert view["collection_mode"] is True
        kline_keys = {int(key) for key in view["market"]["klines"]}
        assert 86_400_000_000 not in kline_keys, "1D 不得进入采集视图"
        assert kline_keys == set(view["freeze"]["kline_periods_ns"])
        order = _post(
            base, "/api/v1/h2/owner/session/orders", _order("jt-o1", "BUY", "MARKET", 1, None)
        )
        assert order["accepted"] is True, "采集模式仍是自由连续交易，不限制下单节奏"

        aborted = _post(base, "/api/v1/h2/owner/session/abort", {"reason": "owner-stop"})
        assert aborted["accepted"] is True
        late = _post(
            base, "/api/v1/h2/owner/session/orders", _order("jt-o2", "BUY", "MARKET", 1, None)
        )
        assert late["reason_code"] == "ABORTED"
    finally:
        server.shutdown()
        server.server_close()
    artifact_dir = tmp_path / "artifacts"
    session.export_artifact(artifact_dir)
    payload = json.loads((artifact_dir / "owner-session-jt-403.json").read_text(encoding="utf-8"))
    assert payload["abort"]["kind"] == "owner"


def test_journey_rebuild_evidence(tmp_path: Path):
    """旅程四：会话 artifact 导出 → 证据目录装配 → 机器校验入口闭环。

    自由模拟永不进入证据索引（spec §5 不变量）；本旅程用 training 会话的
    artifact 装配零样本证据目录（stop_reason 文档化）并跑机器校验入口。
    """

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "validate_owner_evidence", Path("tools/validate_owner_evidence.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    validate_main = module.main

    evidence = tmp_path / "preview-bundle"
    evidence.mkdir()
    (evidence / "manifest.json").write_text("{}", encoding="utf-8")
    session = OwnerWebSession(stage="training", preview_dir=evidence, session_id="jt-404")
    session.control("STEP", "jt-404-s1")
    session.view()
    artifact_dir = tmp_path / "artifacts"
    session.export_artifact(artifact_dir)
    session_artifact = (artifact_dir / "owner-session-jt-404.json").read_text(encoding="utf-8")

    evidence_dir = tmp_path / "owner-n-of-1"
    evidence_dir.mkdir()
    (evidence_dir / "environment.json").write_text(
        json.dumps(
            {"os": "test", "python": "3.11", "command": "test", "recorded_at": "2026-09-18"}
        ),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "sessions": [
            {
                "session_id": "jt-404",
                "stage": "training",
                "scenario_id": "training-01",
                "status": "complete",
                "seed": 0,
                "started_at": "2026-09-18T00:00:00Z",
                "ended_at": "2026-09-18T00:01:00Z",
                "events_sha256": json.loads(session_artifact)["events_sha256"],
            }
        ],
    }
    manifest_bytes = json.dumps(manifest, ensure_ascii=False)
    (evidence_dir / "owner-session-manifest.json").write_text(manifest_bytes, encoding="utf-8")
    import hashlib

    (evidence_dir / "owner-evidence-index.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "study_status": "zero-sample",
                "stop_reason": "engineering preview before owner training",
                "sessions_total": 1,
                "training_total": 1,
                "formal_total": 0,
                "manifest_sha256": hashlib.sha256(manifest_bytes.encode("utf-8")).hexdigest(),
                "sessions": [
                    {
                        "session_id": "jt-404",
                        "stage": "training",
                        "status": "complete",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    assert validate_main(["--dir", str(evidence_dir)]) == 0
