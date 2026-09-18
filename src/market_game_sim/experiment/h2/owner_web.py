"""0.3.2 owner Web 终端：loopback-only HTTP 服务（tasks T931/932/933/934/935/936）。

复用 0.2.1 交互运行时（``InteractiveRuntime``：幂等收件箱 + 真实撮合/账本/风控路径）
与 0.3.2 E1 冻结参数（``owner_freeze``），为项目所有者提供本地 Web 交易终端：

- ``GET  /``                                 定稿终端页（结构承自 interaction-design.html）
- ``GET  /api/v1/h2/owner/session``          owner 观察视图（采集态仅含冻结观察白名单字段）
- ``POST /api/v1/h2/owner/session/orders``   canonical 委托（client_request_id 幂等）
- ``POST /api/v1/h2/owner/session/cancels``  撤单
- ``POST /api/v1/h2/owner/session/control``  PAUSE/RESUME/STEP/END
- ``POST /api/v1/h2/owner/session/abort``    OWNER_ABORT 主动中止（终态、不补跑）

preview fail-closed（E2）：``stage`` 为 training/formal 时必须提供含 ``manifest.json``
的 preview 证据目录，否则拒绝创建会话——页面缺陷不得消耗真实采集（US-403）。
"""

from __future__ import annotations

import hashlib
import json
import platform
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from market_game_sim.experiment.h2.owner_freeze import (
    SAMPLING_INTERVAL_NS,
    TIME_COMPRESSION,
    owner_freeze_contract,
    owner_freeze_hash,
)
from market_game_sim.interactive.runtime import InteractiveRuntime
from market_game_sim.interactive.types import InputAction
from market_game_sim.replay.kline import build_kline_set

# 自由模拟专用追加周期（1D）：采集态不得下发（spec §5 白名单外周期）。
FREE_ONLY_EXTRA_PERIOD_NS = 86_400_000_000

STAGES = ("free", "training", "formal")
COLLECTION_STAGES = ("training", "formal")

OWNER_ABORT_REASONS = ("owner-stop",)


class PreviewGateBlocked(RuntimeError):
    """preview 证据缺失时拒绝进入 training/formal（US-403 / E2 fail-closed）。"""


@dataclass(slots=True)
class _AbortRecord:
    kind: str
    reason: str
    at_ns: int


@dataclass(slots=True)
class OwnerWebSession:
    """单个 owner 终端会话：运行时 + 阶段 + 采样快照 + 中止裁决。"""

    stage: str = "free"
    session_id: str = "owner-web-1"
    preview_dir: Path | None = None
    initial_price_ticks: int = 10_000
    runtime: InteractiveRuntime = field(init=False)
    owner_aborted: bool = False
    abort_record: _AbortRecord | None = None
    snapshots: list[dict[str, Any]] = field(default_factory=list)
    _last_sample_ns: int = field(default=-1, repr=False)

    def __post_init__(self) -> None:
        if self.stage not in STAGES:
            raise ValueError(f"未知 stage：{self.stage}")
        if self.stage in COLLECTION_STAGES:
            self._require_preview_evidence()
        self.runtime = InteractiveRuntime(session_id=self.session_id)
        self.runtime.start()

    def _require_preview_evidence(self) -> None:
        if self.preview_dir is None:
            raise PreviewGateBlocked("training/formal 需要 preview 证据目录（E2 fail-closed）")
        manifest = Path(self.preview_dir) / "manifest.json"
        if not manifest.is_file():
            raise PreviewGateBlocked(f"preview 证据目录缺少 manifest.json：{self.preview_dir}")

    # ---------- 观察视图 ----------

    def view(self) -> dict[str, Any]:
        base = self.runtime.view()
        collection = self.stage in COLLECTION_STAGES
        periods = list(owner_freeze_contract()["kline_periods_ns"])
        if not collection:
            periods.append(FREE_ONLY_EXTRA_PERIOD_NS)
        events = self.runtime.adapter.records
        klines = build_kline_set(
            events, periods_ns=periods, initial_price_ticks=self.initial_price_ticks
        )
        view: dict[str, Any] = {
            "schema_version": 1,
            "stage": self.stage,
            "collection_mode": collection,
            "owner_aborted": self.owner_aborted,
            "freeze": owner_freeze_contract(),
            "freeze_hash": owner_freeze_hash(),
            "market": {
                "last_ticks": base["market"]["last_ticks"],
                "best_bid": base["market"]["best_bid"],
                "best_ask": base["market"]["best_ask"],
                "bids": base["market"]["bids"],
                "asks": base["market"]["asks"],
                "recent_trades": self._recent_trades(events),
                "klines": {
                    period: [
                        {
                            "start_ns": bar.start_ns,
                            "open": bar.open,
                            "high": bar.high,
                            "low": bar.low,
                            "close": bar.close,
                            "volume": bar.volume,
                        }
                        for bar in bars
                    ]
                    for period, bars in klines.items()
                },
            },
            "account": base["account"],
            "recent_input_results": base["recent_input_results"],
            "session_state": "OWNER_ABORTED" if self.owner_aborted else base["session_state"],
            "ui_state": base["ui_state"],
            "snapshot_revision": base["snapshot_revision"],
            "logical_timestamp": base["logical_timestamp"],
            "error_code": base["error_code"],
            "boundary_notice": "合成市场 · 无真实资金 · 非交易建议",
        }
        self._sample(view)
        return view

    @staticmethod
    def _recent_trades(events: list[dict[str, Any]], limit: int = 16) -> list[dict[str, Any]]:
        trades = [item for item in events if item.get("event_type") == "TRADE_SETTLE"]
        return [
            {
                "timestamp": int(item["timestamp"]),
                "price_ticks": int(item["price_ticks"]),
                "quantity_units": int(item["quantity_units"]),
                "taker_side": str(item.get("taker_side", "")),
            }
            for item in reversed(trades[-limit:])
        ]

    # ---------- 委托 / 撤单 / 控制 / 中止 ----------

    def place_order(self, payload: dict[str, Any], client_request_id: str) -> dict[str, Any]:
        return self._result(
            self.runtime.place_order({**payload, "client_request_id": client_request_id})
        )

    def cancel_order(self, payload: dict[str, Any], client_request_id: str) -> dict[str, Any]:
        return self._result(
            self.runtime.cancel_order({**payload, "client_request_id": client_request_id})
        )

    def control(self, action: str, client_request_id: str) -> dict[str, Any]:
        return self._result(self.runtime.control(InputAction(action), client_request_id))

    def abort(self, reason: str = "owner-stop") -> dict[str, Any]:
        """OWNER_ABORT：所有者主动中止，进入终态、不补跑、不入 evidence index。"""

        if reason not in OWNER_ABORT_REASONS:
            return {"accepted": False, "reason_code": "INVALID_INPUT"}
        if self.owner_aborted:
            return {"accepted": False, "reason_code": "ABORTED"}
        self.owner_aborted = True
        self.abort_record = _AbortRecord("owner", reason, self.runtime.logical_timestamp)
        self.runtime.disconnect()
        self._sample(self.view(), force=True)
        return {"accepted": True, "reason_code": "OK", "abort_kind": "owner", "reason": reason}

    def _result(self, result: Any) -> dict[str, Any]:
        if self.owner_aborted:
            return {"accepted": False, "reason_code": "ABORTED"}
        return {
            "accepted": result.accepted,
            "reason_code": result.reason_code.value,
            "input_seq": result.input_seq,
            "snapshot_revision": result.snapshot_revision,
        }

    # ---------- 逻辑时点采样（T938 机制；粒度=E1 冻结值） ----------

    def _sample(self, view: dict[str, Any], *, force: bool = False) -> None:
        t_ns = int(view["logical_timestamp"])
        if not force and t_ns - self._last_sample_ns < SAMPLING_INTERVAL_NS:
            return
        if self._last_sample_ns < 0 and not force and t_ns == 0:
            return
        account = view["account"]
        self.snapshots.append(
            {
                "t_ns": t_ns,
                "last_ticks": view["market"]["last_ticks"],
                "best_bid": view["market"]["best_bid"],
                "best_ask": view["market"]["best_ask"],
                "equity_units": account["equity_units"],
                "position_units": account["position_units"],
                "reserved_units": account["reserved_units"],
                "margin_ratio_bp": account["margin_ratio_bp"],
                "active_orders": len(account["active_orders"]),
            }
        )
        self._last_sample_ns = t_ns

    # ---------- 证据导出（固定 schema，PII guard：仅白名单键） ----------

    SNAPSHOT_KEYS = frozenset(
        {
            "t_ns",
            "last_ticks",
            "best_bid",
            "best_ask",
            "equity_units",
            "position_units",
            "reserved_units",
            "margin_ratio_bp",
            "active_orders",
        }
    )

    def export_artifact(self, out_dir: Path) -> Path:
        """导出 owner-session artifact（固定键集合；不收任何自由文本）。"""

        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        for snapshot in self.snapshots:
            if set(snapshot) - self.SNAPSHOT_KEYS:
                raise ValueError("采样快照出现 schema 外字段（PII guard）")
        payload = {
            "schema_version": 1,
            "session_id": self.session_id,
            "stage": self.stage,
            "freeze_hash": owner_freeze_hash(),
            "time_compression": TIME_COMPRESSION,
            "sampling_interval_ns": SAMPLING_INTERVAL_NS,
            "snapshot_count": len(self.snapshots),
            "snapshots": self.snapshots,
            "abort": (
                {
                    "kind": self.abort_record.kind,
                    "reason": self.abort_record.reason,
                    "at_ns": self.abort_record.at_ns,
                }
                if self.abort_record
                else None
            ),
            "events_sha256": self._events_sha256(),
            "environment": {
                "os": platform.platform(),
                "python": platform.python_version(),
                "command": "market_game_sim h2 owner-web",
                "recorded_at": datetime.now(UTC).isoformat(),
            },
        }
        path = out_dir / f"owner-session-{self.session_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def _events_sha256(self) -> str:
        payload = json.dumps(
            [
                {key: item.get(key) for key in sorted(item) if key != "decision_evidence"}
                for item in self.runtime.adapter.records
            ],
            sort_keys=True,
            separators=(",", ":"),
            default=str,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def create_owner_server(
    session: OwnerWebSession, host: str = "127.0.0.1", port: int = 8791
) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("owner web terminal may bind only to loopback")
    if type(port) is not int or not 0 <= port <= 65_535:
        raise ValueError("port must be an integer from 0 to 65535")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/":
                self._send(TERMINAL_HTML, "text/html; charset=utf-8")
            elif self.path == "/api/v1/h2/owner/session":
                self._json(session.view())
            else:
                self._json({"error": "NOT_FOUND"}, HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            try:
                body = self._body()
                if self.path == "/api/v1/h2/owner/session/orders":
                    payload = {
                        key: value for key, value in body.items() if key != "client_request_id"
                    }
                    self._json(session.place_order(payload, body.get("client_request_id")))
                elif self.path == "/api/v1/h2/owner/session/cancels":
                    payload = {
                        key: value for key, value in body.items() if key != "client_request_id"
                    }
                    self._json(session.cancel_order(payload, body.get("client_request_id")))
                elif self.path == "/api/v1/h2/owner/session/control":
                    self._json(session.control(body.get("action"), body.get("client_request_id")))
                elif self.path == "/api/v1/h2/owner/session/abort":
                    self._json(session.abort(body.get("reason", "owner-stop")))
                else:
                    self._json({"error": "NOT_FOUND"}, HTTPStatus.NOT_FOUND)
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

    return ThreadingHTTPServer((host, port), Handler)


TERMINAL_HTML = (Path(__file__).resolve().parent / "owner_terminal.html").read_text(
    encoding="utf-8"
)


def main(argv: list[str] | None = None) -> int:
    """owner 终端入口：`python -m market_game_sim.experiment.h2.owner_web --stage free`。"""

    import argparse

    parser = argparse.ArgumentParser(prog="market-game owner-web")
    parser.add_argument("--stage", choices=STAGES, default="free")
    parser.add_argument("--preview-dir", type=Path, default=None, help="E2 preview 证据目录")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8791)
    parser.add_argument("--session-id", default="owner-web-1")
    args = parser.parse_args(argv)
    try:
        session = OwnerWebSession(
            stage=args.stage, preview_dir=args.preview_dir, session_id=args.session_id
        )
    except PreviewGateBlocked as exc:
        print(f"OWNER_WEB_PREVIEW_BLOCKED: {exc}")
        return 2
    server = create_owner_server(session, args.host, args.port)
    address, port = server.server_address[:2]
    print(f"owner web terminal: http://{address}:{port} (stage={args.stage})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
