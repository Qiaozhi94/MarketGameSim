"""Loopback-only HTTP adapter and dependency-free browser client."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from market_game_sim.interactive.runtime import InputResult, InteractiveRuntime
from market_game_sim.interactive.types import InputAction

CLIENT_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>MarketGameSim 本地交易沙盒</title><style>
body{font:15px system-ui;margin:0;background:#10141c;color:#e8edf5}
header,main{max-width:1100px;margin:auto;padding:16px}
.notice{background:#46380c;padding:10px}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}
section{background:#1b2230;padding:14px;border-radius:8px}
button,input,select{margin:4px;padding:7px}
table{width:100%;border-collapse:collapse}
td,th{padding:5px;text-align:left;border-bottom:1px solid #344}
@media(max-width:700px){.grid{grid-template-columns:1fr}}</style></head>
<body><div class="notice">合成市场 · 无真实资金 · 非交易建议</div>
<header><h1>Interactive Market Sandbox</h1>
<div id="session">loading</div><button onclick="control('STEP')">单步</button>
<button onclick="control('RESUME')">继续</button>
<button onclick="control('PAUSE')">暂停</button>
<button onclick="control('END')">结束</button></header>
<main class="grid"><section><h2>市场 / 价格 / K线</h2><pre id="market"></pre></section>
<section><h2>账户 / 仓位 / 保证金</h2><pre id="account"></pre></section>
<section><h2>限价/市价下单</h2><input id="oid" placeholder="订单 ID"><select id="side">
<option>BUY</option><option>SELL</option></select>
<select id="otype"><option>LIMIT</option><option>MARKET</option></select>
<input id="qty" type="number" value="1" min="1" max="1000">
<input id="price" type="number" value="10000"><button onclick="order()">提交</button></section>
<section><h2>活动订单 / 撤单</h2><pre id="orders"></pre>
<input id="cancel" placeholder="订单 ID"><button onclick="cancelOrder()">撤单</button></section>
<section><h2>最近输入结果</h2><pre id="results"></pre></section></main><script>
let n=0; const rid=()=>`web-${Date.now()}-${n++}`;
async function post(path,body){let r=await fetch(path,{method:'POST',
headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
await refresh();return r.json()}
async function refresh(){let v=await fetch('/api/v1/session').then(r=>r.json());
session.textContent=`${v.session_state} · UI: ${v.ui_state||'normal'}`;
market.textContent=JSON.stringify(v.market,null,2);
account.textContent=JSON.stringify(v.account,null,2);
orders.textContent=JSON.stringify(v.account.active_orders,null,2);
results.textContent=JSON.stringify(v.recent_input_results,null,2)}
function control(action){post('/api/v1/control',{action,client_request_id:rid()})}
function order(){let t=otype.value;post('/api/v1/orders',{client_request_id:rid(),
order_id:oid.value,side:side.value,order_type:t,quantity_units:Number(qty.value),
price_ticks:t==='MARKET'?null:Number(price.value)})}
function cancelOrder(){post('/api/v1/cancels',
{client_request_id:rid(),order_id:cancel.value})} refresh();setInterval(refresh,250);
</script></body></html>"""


def make_handler(runtime: InteractiveRuntime) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/":
                self._send(CLIENT_HTML, "text/html; charset=utf-8")
            elif self.path.startswith("/api/v1/session"):
                self._json(runtime.view())
            else:
                self._json({"error": "NOT_FOUND"}, HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            try:
                body = self._body()
                if self.path == "/api/v1/start":
                    self._json(runtime.start())
                    return
                if self.path == "/api/v1/orders":
                    result = runtime.place_order(body)
                elif self.path == "/api/v1/cancels":
                    result = runtime.cancel_order(body)
                elif self.path == "/api/v1/control":
                    result = runtime.control(
                        InputAction(body.get("action")), body.get("client_request_id")
                    )
                elif self.path == "/api/v1/disconnect":
                    runtime.disconnect()
                    self._json(runtime.view())
                    return
                else:
                    self._json({"error": "NOT_FOUND"}, HTTPStatus.NOT_FOUND)
                    return
                self._json(_result_json(result))
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self._json(
                    {"accepted": False, "reason_code": "INVALID_INPUT", "detail": str(exc)},
                    HTTPStatus.BAD_REQUEST,
                )

        def log_message(self, format: str, *args: Any) -> None:
            pass

        def _body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            value = json.loads(self.rfile.read(length))
            if not isinstance(value, dict):
                raise TypeError("request JSON must be an object")
            return value

        def _json(self, value: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            self._send(json.dumps(value, ensure_ascii=False), "application/json", status)

        def _send(self, value: str, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
            data = value.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

    return Handler


def _result_json(result: InputResult) -> dict[str, Any]:
    value = asdict(result)
    value["reason_code"] = result.reason_code.value
    value["event_ids"] = list(result.event_ids)
    return value


def create_server(
    runtime: InteractiveRuntime, host: str = "127.0.0.1", port: int = 8765
) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("interactive client may bind only to loopback")
    if type(port) is not int or not 0 <= port <= 65_535:
        raise ValueError("port must be an integer from 0 to 65535")
    return ThreadingHTTPServer((host, port), make_handler(runtime))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    runtime = InteractiveRuntime()
    runtime.start()
    server = create_server(runtime, args.host, args.port)
    address, port = server.server_address[:2]
    print(f"MarketGameSim interactive client: http://{address}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
