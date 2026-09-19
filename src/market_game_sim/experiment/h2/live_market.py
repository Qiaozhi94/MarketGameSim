"""0.3.2 转向：持续运行的 AI 市场生态 + 人类自由参与（ADR-007 方向）。

owner 2026-09-19 拍板的研究方向：不再做 60 逻辑秒的 N-of-1 配对对比，而是
**持续运行的 AI 市场**——0.3.1 冻结配置的真实 AI 代理家族（做市商、因子、
噪声/情绪）实时互相交易、市场无限演进；owner 通过 Web 终端随时进出、自由
下单（市价/限价/撤单），研究人类参与对市场稳定性的影响（波动、崩盘、暴涨）。

与既有机器的关系：
- 内核/代理/事件契约 100% 复用（``runner.build_config``/``_owner_config``/
  ``_dispatch_agents``/``EventKernel``），确定性由种子与队列全序保证——
  owner 的每次介入都会让轨迹分叉，这正是被研究的对象；
- 不走 0.3.1 正式配对协议（无 whitelist、无 N-of-1 场景序列、不入 evidence
  index）；观测产出为稳定性指标序列（价格/波动/回撤/事件标记）。
"""

from __future__ import annotations

import json
import queue
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from market_game_sim.book.orderbook import Book
from market_game_sim.experiment.h2 import runner as h2_runner
from market_game_sim.experiment.runner import _compute_initial_bp, _dispatch_agents
from market_game_sim.kernel.abort import KernelAbort
from market_game_sim.ledger.account import Account, margin_ratio_bp, risk_equity
from market_game_sim.replay.kline import build_kline_set

TERMINAL_HTML = (Path(__file__).resolve().parent / "owner_terminal.html").read_text(
    encoding="utf-8"
)

HUMAN_AGENT = "owner"  # 人类参与者账户（AI 生态之外的新增扰动源）
PRICE_PERIODS = (
    60_000_000_000,
    300_000_000_000,
    900_000_000_000,
    3_600_000_000_000,
    14_400_000_000_000,
)


class LiveMarket:
    """持续运行的 AI 市场：增量内核驱动 + 人类委托直通 + 稳定性指标。"""

    def __init__(
        self,
        *,
        seed: int = 7,
        arm: str = "linear",
        session_id: str = "live-market-1",
        initial_price_ticks: int = 10_000,
    ) -> None:
        self.session_id = session_id
        self.seed = seed
        self.initial_price_ticks = initial_price_ticks
        self.config = h2_runner.build_config(seed, arm)
        self.logical_ns = 0
        self._tx_budget = 0
        self._seq = 0
        self._prev_last: int | None = None
        self._peak: int | None = None
        self._max_drawdown = 0.0
        self._epoch_ms: int | None = None
        self.orders: queue.Queue[dict[str, Any]] = queue.Queue()
        self.snapshots: list[dict[str, Any]] = []
        self.price_series: list[dict[str, Any]] = []
        self.stability_events: list[dict[str, Any]] = []
        self.lock = threading.RLock()
        self._max_event_ts = 0
        self.dead: str | None = None

        # live 生态调参：mm 报价量 10M→300，让 owner 的订单能产生真实价格冲击
        # （原量级用于 60 逻辑秒配对实验的零冲击假设；本方向研究人类扰动的
        # 价格影响，报价必须可被吃穿。仅改本模块构造，不动冻结配置文件。）
        import dataclasses

        def _tuned(spec: Any) -> Any:
            if not spec.agent_id.startswith("mm"):
                return spec
            # live 生态：报价量 300（可被吃穿）+ 库存上限放宽（持续报价）
            return dataclasses.replace(spec, quote_size=300, max_inventory=spec.max_inventory * 20)

        tuned_specs = [_tuned(spec) for spec in self.config.agent_specs]
        self.accounts: dict[str, Account] = {
            spec.agent_id: Account(agent_id=spec.agent_id, wallet_units=10**14)
            for spec in tuned_specs
        }
        for agent_id, wallet_units in self.config.extra_accounts.items():
            self.accounts[agent_id] = Account(agent_id=agent_id, wallet_units=wallet_units)
        # 人类参与者：独立账户，随时进出（研究 AI 市场的人类扰动）
        self.accounts["owner"] = Account(agent_id="owner", wallet_units=10_000_000_000)

        from market_game_sim.eventlog.bootstrap import (
            build_account_payload_from_accounts,
            build_book_payload,
        )
        from market_game_sim.kernel.runner import EventKernel

        self.kernel = EventKernel(run_id=f"live-s{seed}")
        self.kernel.bootstrap(
            build_account_payload_from_accounts(self.accounts, mult=self.config.mult),
            build_book_payload(last_ticks=None),
        )
        self.world: dict[str, Any] = {
            "book": Book(initial_price_ticks=self.initial_price_ticks),
            "accounts": self.accounts,
            "exchange_fee_units": 0,
            "exchange_risk_pnl_units": 0,
            "mult": self.config.mult,
            "maker_bps": self.config.maker_bps,
            "taker_bps": self.config.taker_bps,
            "initial_price_ticks": initial_price_ticks,
            "maint_bp": self.config.maint_bp,
            "target_bp": self.config.target_bp,
            "liquidation_latency_ns": self.config.liquidation_latency_ns,
            "agent_specs": {s.agent_id: s for s in tuned_specs},
            "agent_signals": self.config.agent_signals,
            "agent_decision_index": {},
            "experiment_seed": seed,
            "trade_history": {},
            "public_tape": [],
            "agent_cursors": {},
            "agent_ewma": {},
            "agent_initial_bp": {
                s.agent_id: _compute_initial_bp(s.leverage_tier) for s in self.config.agent_specs
            },
            "model_family": self.config.model_family,
            "behavior_mapping": None,
        }
        for spec in self.config.agent_specs:
            self.kernel.enqueue(
                {
                    "event_type": "AGENT_OBSERVE",
                    "timestamp": 0,
                    "agent_id": spec.agent_id,
                    "observed_at": 0,
                    "market_data_event_id": "e1_0",
                    "information_set": {},
                }
            )

    # ---------- 人类委托 ----------

    def _enqueue(self, event: dict[str, Any]) -> None:
        """带水位追踪的入队：人类委托的时间戳必须严格晚于调度器水位。"""

        ts = int(event.get("timestamp", 0))
        self._max_event_ts = max(self._max_event_ts, ts)
        self.kernel.enqueue(event)

    def _safe_ts(self) -> int:
        """严格晚于（已提交尾部、已弹出水位、待处理队列尾部）的时间戳。"""

        floor = max(self.logical_ns, self._max_event_ts)
        popped = getattr(self.kernel, "_last_popped_key", None)
        if popped is not None:
            floor = max(floor, int(popped.timestamp))
        pending = getattr(self.kernel, "_queue", None)
        if pending:
            floor = max(floor, max(int(item[0].timestamp) for item in pending))
        return floor + 1_000_000

    def push_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        order_id = f"owner-{self._seq + 1}"
        event = self._validate(payload, order_id)
        if isinstance(event, str):
            return {"accepted": False, "reason_code": event}
        self._seq += 1
        self.orders.put(event)
        return {"accepted": True, "reason_code": "OK", "order_id": order_id}

    def push_cancel(self, order_id: str) -> dict[str, Any]:
        if not order_id:
            return {"accepted": False, "reason_code": "INVALID_INPUT"}
        self._seq += 1
        self.orders.put(
            {
                "event_type": "ORDER_ARRIVAL",
                "timestamp": self._safe_ts(),
                "agent_id": HUMAN_AGENT,
                "order_id": f"owner-cancel-{self._seq}",
                "action": "CANCEL",
                "target_order_id": order_id,
                "side": None,
                "order_type": None,
                "price_ticks": None,
                "quantity_units": None,
                "origin": "AGENT",
                "intent_id": f"owner-cancel-{self._seq}",
                "decision_event_id": f"owner-cancel-d-{self._seq}",
                "submitted_at": self.logical_ns,
            }
        )
        return {"accepted": True, "reason_code": "OK"}

    def _validate(self, payload: dict[str, Any], order_id: str) -> dict[str, Any] | str:
        side = payload.get("side")
        order_type = payload.get("order_type", "MARKET")
        qty = payload.get("quantity_units")
        price = payload.get("price_ticks")
        if side not in {"BUY", "SELL"} or order_type not in {"MARKET", "LIMIT"}:
            return "INVALID_INPUT"
        if not isinstance(qty, int) or not 1 <= qty <= 1000:
            return "INVALID_INPUT"
        if order_type == "MARKET" and price is not None:
            return "INVALID_INPUT"
        if order_type == "LIMIT" and (not isinstance(price, int) or price <= 0):
            return "INVALID_INPUT"
        return {
            "event_type": "ORDER_ARRIVAL",
            "timestamp": self._safe_ts(),
            "agent_id": HUMAN_AGENT,
            "order_id": order_id,
            "action": "SUBMIT",
            "side": side,
            "order_type": order_type,
            "price_ticks": price,
            "quantity_units": qty,
            "origin": "AGENT",
            "intent_id": f"owner-intent-{order_id}",
            "decision_event_id": f"owner-decision-{order_id}",
            "submitted_at": self.logical_ns,
        }

    # ---------- 驱动 ----------

    def advance(self, *, batch: int = 400) -> None:
        """推进一个逻辑秒：注入人类委托 → 内核批量处理 → 采样与稳定性指标。"""

        with self.lock:
            if self.dead:
                return
            while True:
                try:
                    event = self.orders.get_nowait()
                except queue.Empty:
                    break
                event["timestamp"] = max(int(event.get("timestamp", 0)), self._safe_ts())
                self._max_event_ts = max(self._max_event_ts, int(event["timestamp"]))
                self.kernel.enqueue(event)
            target_logical = self.logical_ns + 1_000_000_000
            # 噪声流（live-only 工程演示）：温和双向市价单维持市场活性
            if (self.logical_ns // 1_000_000_000) % 3 == 0:
                side = "BUY" if (self.logical_ns // 1) % 2 == 0 else "SELL"
                self.kernel.enqueue(
                    {
                        "event_type": "ORDER_ARRIVAL",
                        "timestamp": self._safe_ts(),
                        "agent_id": "noise-flow",
                        "order_id": f"noise-{self.logical_ns}",
                        "action": "SUBMIT",
                        "side": side,
                        "order_type": "MARKET",
                        "price_ticks": None,
                        "quantity_units": 1 + (self.logical_ns // 1_000_000_000) % 3,
                        "origin": "AGENT",
                        "intent_id": f"noise-{self.logical_ns}",
                        "decision_event_id": f"noise-d-{self.logical_ns}",
                        "submitted_at": self.logical_ns,
                    }
                )
                if "noise-flow" not in self.accounts:
                    from market_game_sim.ledger.account import Account as _Acc

                    self.accounts["noise-flow"] = _Acc(agent_id="noise-flow", wallet_units=10**14)
            for _ in range(32):
                if self.logical_ns >= target_logical:
                    break
                self._tx_budget += batch
                try:
                    self.kernel.run(_dispatch_agents, self.world, max_transactions=self._tx_budget)
                except KernelAbort as exc:
                    self.dead = f"{exc.abort_code}: {exc}"
                    self.stability_events.append(
                        {"t_ns": self.logical_ns, "kind": "kernel-abort", "detail": self.dead}
                    )
                    return
                newest = self._newest_timestamp()
                if newest is not None:
                    self.logical_ns = max(self.logical_ns, newest)
            self.logical_ns = max(self.logical_ns, target_logical)
            self._snapshot()

    def _newest_timestamp(self) -> int | None:
        records = self.kernel.committed_records
        if not records:
            return None
        return max(int(item.get("timestamp", 0)) for item in records[-64:])

    # ---------- 观察视图与指标 ----------

    def view(self) -> dict[str, Any]:
        with self.lock:
            records = self.kernel.committed_records
            book = self.world["book"]
            account = self.accounts["owner"]
            mult = self.world["mult"]
            mark = book.last_ticks or self.initial_price_ticks
            klines = {
                str(period): [
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
                for period, bars in build_kline_set(
                    records,
                    periods_ns=PRICE_PERIODS,
                    initial_price_ticks=self.initial_price_ticks,
                ).items()
            }
            forming = self._forming_bar(records)
            trades = [
                {
                    "timestamp": int(item["timestamp"]),
                    "price_ticks": int(item["price_ticks"]),
                    "quantity_units": int(item["quantity_units"]),
                    "taker_side": str(item.get("taker_side", "")),
                }
                for item in records
                if item.get("event_type") == "TRADE_SETTLE"
            ]
            return {
                "schema_version": 1,
                "stage": "live",
                "collection_mode": False,
                "epoch_ms": self._epoch_ms,
                "history_available": False,
                "freeze": {},
                "market": {
                    "last_ticks": book.last_ticks,
                    "best_bid": book.best_bid(),
                    "best_ask": book.best_ask(),
                    "bids": [[p, q] for p, q in book.bid_levels()[:10]],
                    "asks": [[p, q] for p, q in book.ask_levels()[:10]],
                    "recent_trades": list(reversed(trades[-16:])),
                    "klines": klines,
                    "forming": {60_000_000_000: forming},
                },
                "account": {
                    "wallet_units": account.wallet_units,
                    "equity_units": risk_equity(account, mark, mult),
                    "position_units": account.position_units,
                    "entry_notional_units": account.entry_notional_units,
                    "reserved_units": account.reserved_units,
                    "margin_ratio_bp": margin_ratio_bp(account, mark, mult),
                    "state": account.state.value,
                    "active_orders": self._active_orders(),
                },
                "recent_input_results": [],
                "session_state": "RUNNING",
                "ui_state": None,
                "snapshot_revision": len(self.snapshots),
                "logical_timestamp": self.logical_ns,
                "error_code": None,
                "boundary_notice": "持续 AI 市场 · 无真实资金 · 人类参与稳定性研究",
            }

    def _forming_bar(self, records: list[dict[str, Any]]) -> dict[str, Any] | None:
        cutoff = (self.logical_ns // 60_000_000_000) * 60_000_000_000
        trades = [
            (int(item["timestamp"]), int(item["price_ticks"]), int(item["quantity_units"]))
            for item in records
            if item.get("event_type") == "TRADE_SETTLE" and int(item["timestamp"]) >= cutoff
        ]
        if not trades:
            return None
        prices = [t[1] for t in trades]
        return {
            "start_ns": cutoff,
            "open": prices[0],
            "high": max(prices),
            "low": min(prices),
            "close": prices[-1],
            "volume": sum(t[2] for t in trades),
            "forming": True,
        }

    def _active_orders(self) -> list[dict[str, Any]]:
        book = self.world["book"]
        orders = []
        for side in ("BUY", "SELL"):
            for _, levels in book._side_refs(side)[0].items():  # type: ignore[attr-defined]
                for order in levels:
                    if order.agent_id == HUMAN_AGENT and order.quantity_units > 0:
                        orders.append(
                            {
                                "order_id": order.order_id,
                                "side": order.side,
                                "price_ticks": order.price_ticks,
                                "quantity_units": order.quantity_units,
                            }
                        )
        return sorted(orders, key=lambda item: item["order_id"])

    def _snapshot(self) -> None:
        book = self.world["book"]
        last = book.last_ticks
        if last is None:
            return
        entry: dict[str, Any] = {"t_ns": self.logical_ns, "last": last}
        if self._prev_last:
            ret = (last - self._prev_last) / self._prev_last
            entry["return"] = round(ret, 6)
            if abs(ret) >= 0.03:
                self.stability_events.append(
                    {"t_ns": self.logical_ns, "kind": "big-move", "return": round(ret, 6)}
                )
        self._prev_last = last
        self._peak = max(self._peak or last, last)
        self._max_drawdown = min(self._max_drawdown, last / self._peak - 1)
        self.price_series.append(entry)

    # ---------- 指标导出 ----------

    def export_metrics(self, out: Path) -> Path:
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "session_id": self.session_id,
            "seed": self.seed,
            "max_drawdown": round(self._max_drawdown, 6),
            "price_series": self.price_series,
            "stability_events": self.stability_events,
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return out


def create_live_server(
    market: LiveMarket, host: str = "127.0.0.1", port: int = 8791
) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("live market server may bind only to loopback")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/":
                self._send(TERMINAL_HTML, "text/html; charset=utf-8")
            elif self.path == "/api/v1/h2/owner/session":
                self._json(market.view())
            else:
                self._json({"error": "NOT_FOUND"}, HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            try:
                body = self._body()
                if self.path == "/api/v1/h2/owner/session/orders":
                    payload = {
                        key: value for key, value in body.items() if key != "client_request_id"
                    }
                    self._json(market.push_order(payload))
                elif self.path == "/api/v1/h2/owner/session/cancels":
                    self._json(market.push_cancel(str(body.get("order_id", ""))))
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

    return ThreadingHTTPServer((host, port), Handler)


def main(argv: list[str] | None = None) -> int:
    import argparse
    import time as _time

    parser = argparse.ArgumentParser(prog="market-game live-market")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--port", type=int, default=8791)
    parser.add_argument(
        "--tick-seconds", type=float, default=1.0, help="每个逻辑秒的墙钟时长（1:1 实时）"
    )
    args = parser.parse_args(argv)

    market = LiveMarket(seed=args.seed)
    market._epoch_ms = int(_time.time() * 1000)
    server = create_live_server(market, port=args.port)
    print(f"live AI market: http://127.0.0.1:{args.port} (seed={args.seed})")

    stop = threading.Event()

    def _loop() -> None:
        while not stop.is_set():
            market.advance()
            stop.wait(args.tick_seconds)

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
