"""0.3.2 训练实验：owner Web 终端驱动真实 H2 训练场景（tasks T937/T939 机制层）。

ADR-006 自由连续交易模式：窗口按 1:1 墙钟节拍推进（每窗 = 1 逻辑秒 = 1 墙钟
秒），owner 的网页市价委托进入桥接队列；窗口判定点取队首一条作为该窗规范
决定（每窗至多一条，余单自动顺延后续窗口），空窗记 NO_ACTION。网页只展示
冻结观察子集 + 进度；「退出会话」= OWNER_ABORT（终态，写审计工件、不补跑、
不入 evidence index）。

市场与证据链全部复用 0.3.1 既有机制：``run_owner_scenario``（冻结协议 +
assignment 种子 + ``run_one`` 真实内核 + 事件哈希工件），本模块不新增证据面。
"""

from __future__ import annotations

import argparse
import json
import queue
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from market_game_sim.experiment.h2 import artifacts
from market_game_sim.experiment.h2.owner_client import OwnerAbort, run_owner_scenario

_EXPERIMENT_HTML = (Path(__file__).resolve().parent / "owner_experiment.html").read_text(
    encoding="utf-8"
)


class WebOrderBridge:
    """网页委托 → 决定缝 的线程安全桥：订单队列 + 中止标志 + 最新观察。"""

    def __init__(self) -> None:
        self._orders: queue.Queue[dict[str, Any]] = queue.Queue()
        self.abort_requested = False
        self.latest_info: dict[str, Any] = {}
        self.completed_windows = 0
        self.running = True
        self.done = False
        self.aborted = False
        self.error: str | None = None
        self.artifact: str | None = None

    def push_order(self, side: str, quantity_units: int) -> bool:
        normalized = side.strip().lower()
        if normalized not in {"buy", "sell"} or quantity_units <= 0:
            return False
        self._orders.put(
            {"kind": "MARKET", "side": normalized, "quantity_units": int(quantity_units)}
        )
        return True

    def pop_order(self) -> dict[str, Any] | None:
        try:
            return self._orders.get_nowait()
        except queue.Empty:
            return None


def web_decision_ask(bridge: WebOrderBridge, *, window_wall_seconds: float = 1.0):
    """ADR-006 自由连续交易的 Web 决定源。

    每窗按 1:1 墙钟节拍走满 ``window_wall_seconds``（时间压缩比 1:1，E1 冻结）；
    窗内 owner 委托实时入队，窗末判定点取队首一条（余单顺延），空窗 NO_ACTION；
    中止请求随时抬起 ``OwnerAbort``。
    """

    def _ask(window_index: int, info: dict[str, Any], window) -> dict[str, Any] | None:
        bridge.latest_info = dict(info)
        bridge.completed_windows = window_index
        deadline = time.monotonic() + window_wall_seconds
        decided: dict[str, Any] | None = None
        while True:
            if bridge.abort_requested:
                bridge.aborted = True
                raise OwnerAbort("owner 通过页面请求中止")
            if time.monotonic() >= deadline:
                break
            order = bridge.pop_order()
            if order is not None and decided is None:
                decided = order
            time.sleep(0.02)
        return decided

    return _ask


EXPERIMENT_ROUTES_PREFIX = "/api/v1/h2/owner/experiment"


def make_experiment_handler(bridge: WebOrderBridge) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/":
                self._send(_EXPERIMENT_HTML, "text/html; charset=utf-8")
            elif self.path == f"{EXPERIMENT_ROUTES_PREFIX}":
                self._json(
                    {
                        "running": bridge.running,
                        "done": bridge.done,
                        "aborted": bridge.aborted,
                        "error": bridge.error,
                        "completed_windows": bridge.completed_windows,
                        "latest_info": bridge.latest_info,
                        "artifact": bridge.artifact,
                    }
                )
            else:
                self._json({"error": "NOT_FOUND"}, HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            try:
                body = self._body()
                if self.path == f"{EXPERIMENT_ROUTES_PREFIX}/orders":
                    ok = bridge.push_order(
                        str(body.get("side", "")), int(body.get("quantity_units", 0))
                    )
                    self._json({"queued": ok})
                elif self.path == f"{EXPERIMENT_ROUTES_PREFIX}/abort":
                    bridge.abort_requested = True
                    self._json({"abort_requested": True})
                else:
                    self._json({"error": "NOT_FOUND"}, HTTPStatus.NOT_FOUND)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self._json({"error": "INVALID_INPUT", "detail": str(exc)}, HTTPStatus.BAD_REQUEST)

        def log_message(self, format: str, *args: Any) -> None:
            pass

        def _body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            value = json.loads(self.rfile.read(length))
            if not isinstance(value, dict):
                raise TypeError("request JSON must be an object")
            return value

        def _json(self, value: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            data = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _send(self, value: str, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
            data = value.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

    return Handler


def create_experiment_server(
    bridge: WebOrderBridge, host: str = "127.0.0.1", port: int = 8793
) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("experiment server may bind only to loopback")
    return ThreadingHTTPServer((host, port), make_experiment_handler(bridge))


def run_scenario_in_thread(
    bridge: WebOrderBridge,
    *,
    position: int,
    out_root: Path | None,
    window_wall_seconds: float,
) -> threading.Thread:
    def _run() -> None:
        try:
            artifact_path = (out_root or artifacts.DEFAULT_TRAINING_ROOT / "owner") / (
                f"training-{position:02d}.json"
            )
            run_owner_scenario(
                "training",
                position,
                web_decision_ask(bridge, window_wall_seconds=window_wall_seconds),
                out_root=out_root,
            )
            bridge.artifact = str(artifact_path)
            bridge.done = True
        except OwnerAbort:
            bridge.aborted = True
            bridge.done = True
        except Exception as exc:  # noqa: BLE001 — 页面可见的兜底错误通道
            bridge.error = f"{type(exc).__name__}: {exc}"
            bridge.done = True
        bridge.running = False

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread


def main(argv: list[str] | None = None) -> int:
    """训练实验入口：`python -m market_game_sim.experiment.h2.owner_experiment`。"""

    parser = argparse.ArgumentParser(prog="market-game owner-experiment")
    parser.add_argument("--position", type=int, default=0, help="训练场景位置（0..5）")
    parser.add_argument(
        "--window-seconds", type=float, default=1.0, help="每窗墙钟时长（1:1 实时压缩比，E1 冻结）"
    )
    parser.add_argument("--out-root", type=Path, default=None)
    parser.add_argument(
        "--preview-dir",
        type=Path,
        default=Path("artifacts/h2/preview"),
        help="E2 preview 证据目录（fail-closed）",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8793)
    args = parser.parse_args(argv)

    manifest = args.preview_dir / "manifest.json"
    if not manifest.is_file():
        print(f"OWNER_EXPERIMENT_PREVIEW_BLOCKED: 缺少 E2 preview 证据 {manifest}")
        return 2

    bridge = WebOrderBridge()
    thread = run_scenario_in_thread(
        bridge,
        position=args.position,
        out_root=args.out_root,
        window_wall_seconds=args.window_seconds,
    )
    server = create_experiment_server(bridge, args.host, args.port)
    address, port = server.server_address[:2]
    print(f"owner experiment (training #{args.position}): http://{address}:{port}")
    try:
        while thread.is_alive():
            server.handle_request()
            time.sleep(0.05)
    except KeyboardInterrupt:
        bridge.abort_requested = True
    finally:
        server.server_close()
        if bridge.artifact:
            print(f"工件：{bridge.artifact}")
        print(f"结束状态：done={bridge.done} aborted={bridge.aborted} error={bridge.error}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
