"""T809: loopback browser client and UI-state contract."""

import json
import threading
import urllib.request

import pytest

from market_game_sim.interactive.client import CLIENT_HTML, create_server
from market_game_sim.interactive.runtime import InteractiveRuntime


def test_client_contains_all_required_views_and_safety_notice() -> None:
    for label in (
        "市场",
        "价格",
        "K线",
        "账户",
        "仓位",
        "保证金",
        "活动订单",
        "限价",
        "市价",
        "撤单",
        "最近输入结果",
    ):
        assert label in CLIENT_HTML
    assert "合成市场 · 无真实资金 · 非交易建议" in CLIENT_HTML
    assert "setInterval(refresh,250)" in CLIENT_HTML


def test_loopback_http_maps_session_and_mutations() -> None:
    runtime = InteractiveRuntime()
    runtime.start()
    try:
        server = create_server(runtime, port=0)
    except PermissionError:
        pytest.skip("execution sandbox forbids loopback sockets")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/api/v1/session") as response:
            view = json.load(response)
        assert view["ui_state"] == "paused"
        body = json.dumps(
            {
                "client_request_id": "web",
                "order_id": "web-order",
                "side": "BUY",
                "order_type": "MARKET",
                "quantity_units": 1,
                "price_ticks": None,
            }
        ).encode()
        request = urllib.request.Request(
            base + "/api/v1/orders",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            result = json.load(response)
        assert result["accepted"] and result["reason_code"] == "OK"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_server_rejects_non_loopback_binding() -> None:
    with pytest.raises(ValueError, match="loopback"):
        create_server(InteractiveRuntime(), host="0.0.0.0")
