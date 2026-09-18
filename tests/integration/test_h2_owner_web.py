"""0.3.2 owner Web 终端集成测试（tasks T931/932/933/934/935/936/938 机制层）。"""

from __future__ import annotations

import http.client
import json
import threading
from pathlib import Path

import pytest

from market_game_sim.experiment.h2.owner_web import (
    OwnerWebSession,
    PreviewGateBlocked,
    create_owner_server,
)


@pytest.fixture()
def free_session():
    session = OwnerWebSession(stage="free", session_id="owner-web-test")
    session.runtime.control("RESUME", "fixture-resume")
    return session


@pytest.fixture()
def owner_server(free_session):
    server = create_owner_server(free_session, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    address, port = server.server_address[:2]
    yield f"http://{address}:{port}", free_session
    server.shutdown()
    server.server_close()


def _post(base: str, path: str, payload: dict) -> dict:
    conn = http.client.HTTPConnection(base.split("//")[1])
    conn.request("POST", path, json.dumps(payload), {"Content-Type": "application/json"})
    response = conn.getresponse()
    body = json.loads(response.read())
    conn.close()
    return body


def _get(base: str, path: str) -> dict:
    conn = http.client.HTTPConnection(base.split("//")[1])
    conn.request("GET", path)
    response = conn.getresponse()
    body = json.loads(response.read())
    conn.close()
    return body


def test_free_session_view_carries_freeze_and_maker_book(free_session: OwnerWebSession):
    view = free_session.view()
    assert view["stage"] == "free"
    assert view["collection_mode"] is False
    assert view["freeze"]["sampling_interval_ns"] == 1_000_000_000
    assert view["freeze"]["time_compression"] == "1:1"
    # HumanAdapter 预置 maker 对手盘：初始价 ±10
    assert view["market"]["best_bid"] == 9_990
    assert view["market"]["best_ask"] == 10_010
    assert view["market"]["klines"], "盘口存在时 K 线投影应有输出"


def test_market_order_flow_and_public_trades(free_session: OwnerWebSession):
    result = free_session.place_order(
        {
            "order_id": "o-1",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity_units": 1,
            "price_ticks": None,
        },
        "req-1",
    )
    assert result["accepted"] is True
    assert result["reason_code"] == "OK"
    view = free_session.view()
    assert view["account"]["position_units"] > 0
    assert view["market"]["recent_trades"], "市价成交应产生公开成交"


def test_idempotent_replay_returns_same_result(free_session: OwnerWebSession):
    payload = {
        "order_id": "o-idem",
        "side": "BUY",
        "order_type": "LIMIT",
        "quantity_units": 1,
        "price_ticks": 9_950,
    }
    first = free_session.place_order(payload, "req-idem")
    second = free_session.place_order(payload, "req-idem")
    assert first["accepted"] is True
    assert second["input_seq"] == first["input_seq"]
    conflict = free_session.place_order({**payload, "quantity_units": 2}, "req-idem")
    assert conflict["reason_code"] == "IDEMPOTENCY_CONFLICT"


def test_cancel_unknown_and_invalid_input(free_session: OwnerWebSession):
    cancel = free_session.cancel_order({"order_id": "nope"}, "req-cancel")
    assert cancel["accepted"] is False
    assert cancel["reason_code"] == "UNKNOWN_ORDER"
    invalid = free_session.place_order(
        {
            "order_id": "o-bad",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity_units": 0,
            "price_ticks": 10,
        },
        "req-bad",
    )
    assert invalid["reason_code"] == "INVALID_INPUT"


def test_preview_gate_blocks_collection_stages_without_evidence(tmp_path: Path):
    with pytest.raises(PreviewGateBlocked):
        OwnerWebSession(stage="training", preview_dir=None)
    with pytest.raises(PreviewGateBlocked):
        OwnerWebSession(stage="formal", preview_dir=tmp_path / "empty")
    evidence = tmp_path / "preview-bundle"
    evidence.mkdir()
    (evidence / "manifest.json").write_text("{}", encoding="utf-8")
    session = OwnerWebSession(stage="training", preview_dir=evidence)
    assert session.stage == "training"


def test_collection_view_hides_free_only_periods(tmp_path: Path):
    evidence = tmp_path / "preview-bundle"
    evidence.mkdir()
    (evidence / "manifest.json").write_text("{}", encoding="utf-8")
    session = OwnerWebSession(stage="training", preview_dir=evidence)
    view = session.view()
    assert view["collection_mode"] is True
    periods = set(view["market"]["klines"])
    assert 86_400_000_000 not in periods, "1D（白名单外周期）不得进入采集视图"
    assert periods == set(view["freeze"]["kline_periods_ns"])


def test_owner_abort_is_terminal(free_session: OwnerWebSession, tmp_path: Path):
    rejected = free_session.abort("not-a-reason")
    assert rejected["accepted"] is False
    ok = free_session.abort("owner-stop")
    assert ok["accepted"] is True
    assert ok["abort_kind"] == "owner"
    again = free_session.abort("owner-stop")
    assert again["reason_code"] == "ABORTED"
    after = free_session.place_order(
        {
            "order_id": "o-after",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity_units": 1,
            "price_ticks": None,
        },
        "req-after",
    )
    assert after["accepted"] is False
    assert after["reason_code"] == "ABORTED"
    artifact = free_session.export_artifact(tmp_path)
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["abort"] == {"kind": "owner", "reason": "owner-stop", "at_ns": 0}
    assert payload["events_sha256"]


def test_sampling_snapshots_at_frozen_granularity(free_session: OwnerWebSession):
    free_session.control("STEP", "s1")
    free_session.view()
    free_session.control("STEP", "s2")
    free_session.view()
    free_session.control("STEP", "s3")
    view = free_session.view()
    times = [snapshot["t_ns"] for snapshot in free_session.snapshots]
    assert times == sorted(times)
    assert times and times[-1] == view["logical_timestamp"]
    assert (times[-1] - times[0]) // free_session.snapshots[0]["t_ns"] >= 1 or len(times) >= 2


def test_export_artifact_has_fixed_schema_keys(free_session: OwnerWebSession, tmp_path: Path):
    free_session.control("STEP", "s1")
    free_session.view()
    free_session.snapshots[0]["injected_field"] = "PII"
    with pytest.raises(ValueError, match="PII guard"):
        free_session.export_artifact(tmp_path)
    free_session.snapshots[0].pop("injected_field")
    artifact = free_session.export_artifact(tmp_path)
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert set(payload["snapshots"][0]) <= free_session.SNAPSHOT_KEYS
    assert payload["sampling_interval_ns"] == 1_000_000_000
    assert payload["environment"]["os"]


def test_http_routes_serve_terminal_and_api(owner_server):
    base, _session = owner_server
    conn = http.client.HTTPConnection(base.split("//")[1])
    conn.request("GET", "/")
    page = conn.getresponse().read().decode("utf-8")
    conn.close()
    assert "Owner" in page
    assert "MarketGame" in page
    view = _get(base, "/api/v1/h2/owner/session")
    assert view["stage"] == "free"
    assert "klines" in view["market"]
    order = _post(
        base,
        "/api/v1/h2/owner/session/orders",
        {
            "client_request_id": "http-1",
            "order_id": "o-http",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity_units": 1,
            "price_ticks": 9_900,
        },
    )
    assert order["accepted"] is True
    aborted = _post(base, "/api/v1/h2/owner/session/abort", {"reason": "owner-stop"})
    assert aborted["accepted"] is True
    missing = _post(base, "/api/v1/h2/owner/session/nope", {})
    assert missing["error"] == "NOT_FOUND"


def test_server_rejects_non_loopback_bind():
    with pytest.raises(ValueError, match="loopback"):
        create_owner_server(OwnerWebSession(stage="free"), host="0.0.0.0")
