"""0.3.2 转向（ADR-010）：持续运行的 AI 市场生态 + 人类自由参与。

0.3.1 冻结配置的真实 AI 代理家族（做市商 + 因子策略）在增量驱动的内核里实时
互相交易，市场无限演进；owner 通过 Web 终端随时进出、市价/限价/撤单直通内核
撮合路径。逐逻辑秒记录价格序列、收益、大波动事件与最大回撤（稳定性研究仪表）。

与 0.3.1 机器的关系：内核/代理/事件契约 100% 复用（``h2_runner.build_config``/
``_dispatch_agents``/``EventKernel``），确定性由种子与队列全序保证——人类的每次
介入都会让轨迹分叉，这正是被研究的对象。本模块不入 evidence index（ADR-010
将 N-of-1 配对轨归档；受控对照问题复活时可启用归档机械）。

0.4.2 T1124（FR-601 / NFR-601 / TR-601）：owner 动作的注入是确定性的。HTTP 线程只做
格式校验并把载荷放进队列，不读内核状态、不分配任何序号或标识；``advance()`` 持锁取出
时分配会话内动作序号、追加会话动作行，并入队一条 owner 的 ``AGENT_OBSERVE``——决策
记录与委托由内核经 观察 → 决策 → 委托 链派生（``experiment/runner.py`` 的 owner 分支
与 ``_handle_external_decide``），所以事件流里的 owner 字段只由 ``advance`` 序号、动作
序号与载荷决定，与墙钟到达时间、HTTP 线程调度无关。
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import queue
import threading
import time
from collections.abc import Mapping
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from market_game_sim.agent.anchor import resolve_for_agents
from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.book.orderbook import Book
from market_game_sim.config.serialization import canonical_serialize
from market_game_sim.eventlog.digest import rolling_digest_hex
from market_game_sim.experiment.h2 import runner as h2_runner
from market_game_sim.experiment.perturbation.session import SessionWriter
from market_game_sim.experiment.roster import (
    StrategyRoster,
    build_experiment_config,
    load_roster,
    parse_roster,
)
from market_game_sim.experiment.runner import _compute_initial_bp, _dispatch_agents
from market_game_sim.kernel.abort import KernelAbort
from market_game_sim.ledger.account import Account, margin_ratio_bp, risk_equity
from market_game_sim.replay.kline import build_kline_set
from market_game_sim.schema.registry import get_registry

TERMINAL_HTML = (Path(__file__).resolve().parent / "owner_terminal.html").read_text(
    encoding="utf-8"
)

HUMAN_AGENT = "owner"

#: 0.4.2 T1125（FR-605）：开放终端前的预热快进。窗口起点 ``W0 = max(冷启动退出, burn-in)``
#: 沿用 0.4.1 口径（``metrics/quality_run.py::window_start_ns``、指标字典 §2 的
#: ``61 × 60`` 逻辑秒）；推进到 5700 逻辑秒仍有代理处于冷启动锚即判窗口不成立、拒绝开放。
WARMUP_BURN_IN_NS = 61 * 60 * 1_000_000_000
WARMUP_CAP_NS = 5700 * 1_000_000_000

#: 终端阶段：预热中拒单；开放后受理；窗口不成立时永不开放。
TERMINAL_WARMING_UP = "WARMING_UP"
TERMINAL_OPEN = "OPEN"
TERMINAL_NOT_APPLICABLE = "NOT_APPLICABLE"

#: 0.4.2 T1124：owner 的代理规格。只注册进运行时 ``world["agent_specs"]``（外部决策接缝
#: 要它的 ``latency_ns``），不进 ``config.agent_specs``——后者会在 t=0 给 owner 排观察并
#: 周期重排，改变纯 AI 运行的事件流。``latency_ns`` 必须 ≥ 1：决策（类 4）→ 委托（类 0）
#: 是优先级类回退，调度白名单要求时间戳至少前进 1 ns（``kernel/scheduling.py``）。
#: ``observe_interval_ns`` 不被使用：owner 没有周期观察。
OWNER_SPEC = AgentSpec(
    agent_id=HUMAN_AGENT,
    role="human",
    observe_interval_ns=1_000_000_000,
    latency_ns=1_000_000,
)

#: 0.4.1 T966 (FR-503): the default assembly of the pure AI market -- a quoting
#: family plus three signal families, so price formation comes from strategy
#: heterogeneity rather than from one template sampled many times
#: (ADR-011 §决策 3).  The anchor breaks the cold-start deadlock (spec Q-501).
DEFAULT_LIVE_ROSTER: dict[str, Any] = {
    "schema_version": 1,
    "seed": 7,
    "engine": {
        "initial_price_ticks": 10_000,
        "mult": 1000,
        "maker_bps": -1,
        "taker_bps": 5,
        "maint_bp": 500,
        "target_bp": 1000,
        "liquidation_latency_ns": 1_000_000,
    },
    "bootstrap_anchor": {
        "source": "synthetic",
        "quantity_units": 1,
        "direction": "family_parity",
        "pricing": "best_opposite_else_initial_limit",
    },
    "families": [
        {
            "family_id": "market_maker_v2",
            # T973 实测：6 个做市商、分散 ±3 时中位档位只有 2（门限 5）——报价全挤在
            # 同一条窄价带里，加数量是次线性的（6→18 只把档位从 2 抬到 4）。12 个 + 分散
            # ±7 达到 5.0，价差 2.92bp 仍远低于 20bp 门限。
            "count": 12,
            "observe_interval_ns": 100_000_000,
            "latency_ns": 5_000_000,
            "params": {
                "leverage_tier": 1,
                # 族默认值；装配清单可调，用于加深盘口（T973 探测）。
                "base_half_spread_ticks": 8,
                "half_spread_dispersion_ticks": 7,
            },
        },
        {
            "family_id": "trend_following",
            "count": 9,
            "observe_interval_ns": 1_000_000_000,
            "latency_ns": 50_000_000,
            "params": {
                "leverage_tier": 5,
                "risk_appetite_x1000": 2000,
                "aggressiveness_bp": 8_000,
                "max_order_qty": 10_000,
                "ewma_half_life_trades": 5,
            },
        },
        {
            "family_id": "mean_reversion",
            "count": 9,
            # 2026-09-24：10 秒 -> 1 秒，与 trend_following 对齐。
            #
            # 原值 10 秒是 T973 为补偿一个已被修掉的缺陷而设的：当时该族的参照是
            # 「上次游标以来的新增成交」，1 秒间隔下每次只看到中位 3 笔，凑不满
            # 20 笔窗口，永远 INSUFFICIENT_HISTORY，于是把间隔拉长到 10 秒去凑样本。
            # 该族的参照现已改为最近 12 根 K 线收盘均值（families/mean_reversion.py），
            # 不再需要「一个观察间隔内凑够 N 笔成交」，**这个补偿因此过期**。
            #
            # 而它过期后是有害的：同样 9 个代理，趋势族每秒出手、本族每 10 秒才出手
            # 一次，形成 10:1 的行动频率不对称，唯一的逆势方在数量上被压制。实测
            # （种子 7，4200 逻辑秒，仅改本字段）：3600 秒价格 58155 -> 25391
            # （失真 5.8 倍 -> 2.5 倍），累计成交 14651 -> 25019，4200 秒本段成交
            # +490 -> +1077。详见实验报告 §10。
            "observe_interval_ns": 1_000_000_000,
            "latency_ns": 50_000_000,
            "params": {
                "leverage_tier": 5,
                "risk_appetite_x1000": 2000,
                "aggressiveness_bp": 8_000,
                "max_order_qty": 10_000,
                "ewma_half_life_trades": 5,
            },
        },
        {
            "family_id": "sentiment_noise",
            "count": 6,
            "observe_interval_ns": 1_000_000_000,
            "latency_ns": 50_000_000,
            "params": {
                "leverage_tier": 3,
                "risk_appetite_x1000": 1500,
                "aggressiveness_bp": 10_000,
                "max_order_qty": 5_000,
                "ewma_half_life_trades": 5,
            },
        },
    ],
}
PRICE_PERIODS = (
    60_000_000_000,
    300_000_000_000,
    900_000_000_000,
    3_600_000_000_000,
    14_400_000_000_000,
)


def _tuned_specs(specs: list[Any]) -> list[Any]:
    """live 生态调参：mm 报价量 10M→300（可被吃穿）+ 库存上限 ×20（持续双边）。"""

    import dataclasses as dc

    return [
        (
            dc.replace(spec, quote_size=300, max_inventory=spec.max_inventory * 20)
            if spec.agent_id.startswith("mm")
            else spec
        )
        for spec in specs
    ]


class LiveMarket:
    """持续运行的 AI 市场：增量内核驱动 + 人类委托直通 + 稳定性指标。"""

    def __init__(
        self,
        *,
        seed: int = 7,
        arm: str = "linear",
        session_id: str = "live-market-1",
        initial_price_ticks: int = 10_000,
        roster: StrategyRoster | Mapping[str, Any] | None = None,
        session_path: str | Path | None = None,
        wall_clock_ms: Any = None,
        warmup: bool = False,
        warmup_burn_in_ns: int = WARMUP_BURN_IN_NS,
        warmup_cap_ns: int = WARMUP_CAP_NS,
    ) -> None:
        self.session_id = session_id
        self.seed = seed
        self.initial_price_ticks = initial_price_ticks
        # 0.4.1 T966: a roster assembles the market (families, counts, time
        # scales, anchor, engine); ``roster=None`` keeps the 0.3.1 two-agent
        # configuration so the existing owner-terminal path is unaffected.
        self.roster: StrategyRoster | None = None
        self.roster_id: str | None = None
        if roster is not None:
            self.roster = roster if isinstance(roster, StrategyRoster) else parse_roster(roster)
            self.roster_id = self.roster.roster_id
            self.seed = seed = self.roster.seed
            self.initial_price_ticks = initial_price_ticks = self.roster.engine[
                "initial_price_ticks"
            ]
            # max_transactions is a batch budget here, not a stopping rule: the
            # live market advances forever, so the assembled config only lends
            # its engine block and agents.
            self.config = build_experiment_config(self.roster, max_transactions=1)
        else:
            base_config = h2_runner.build_config(seed, arm)
            self.config = dataclasses.replace(
                base_config, agent_specs=_tuned_specs(base_config.agent_specs)
            )
        self.logical_ns = 0
        self._tx_budget = 0
        #: 已开始的 ``advance()`` 次数；一次 advance 取出的动作记它开始时的值。
        self.advance_index = 0
        self._action_seq = 0
        #: 会话内动作序号 -> (kind, 载荷)，owner 决策源按序号取。
        self._owner_actions: dict[int, tuple[str, dict[str, Any]]] = {}
        #: 本次运行的 action_seq <-> order_id（只登记 owner 新下的委托）。
        self._owner_order_ids: dict[int, str] = {}
        self._owner_action_by_order: dict[str, int] = {}
        self._wall_clock_ms = wall_clock_ms or (lambda: int(time.time() * 1000))
        # 预热（T1125）：``warmup=False`` 时终端一开始就开放，0.4.1/0.4.3 的既有用法不变。
        self.terminal = TERMINAL_WARMING_UP if warmup else TERMINAL_OPEN
        self.terminal_reason: str | None = None
        self.window_start_ns: int | None = None
        self._warmup_burn_in_ns = warmup_burn_in_ns
        self._warmup_cap_ns = warmup_cap_ns
        self._warmup_seen = 0
        self._last_decision: dict[str, int] = {}
        self._last_anchored: dict[str, int] = {}
        self._prev_last: int | None = None
        self._peak: int | None = None
        self._max_drawdown = 0.0
        self._epoch_ms: int | None = None
        self._max_event_ts = 0
        self.dead: str | None = None
        self.orders: queue.Queue[dict[str, Any]] = queue.Queue()
        self.snapshots: list[dict[str, Any]] = []
        self.price_series: list[dict[str, Any]] = []
        self.stability_events: list[dict[str, Any]] = []
        self.lock = threading.RLock()

        self.accounts: dict[str, Account] = {
            spec.agent_id: Account(agent_id=spec.agent_id, wallet_units=10**14)
            for spec in self.config.agent_specs
        }
        for agent_id, wallet_units in self.config.extra_accounts.items():
            self.accounts[agent_id] = Account(agent_id=agent_id, wallet_units=wallet_units)
        # 人类参与者：独立账户，随时进出（研究 AI 市场的人类扰动）
        self.accounts[HUMAN_AGENT] = Account(agent_id=HUMAN_AGENT, wallet_units=10_000_000_000)

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
            "initial_price_ticks": self.initial_price_ticks,
            "maint_bp": self.config.maint_bp,
            "target_bp": self.config.target_bp,
            "liquidation_latency_ns": self.config.liquidation_latency_ns,
            "agent_specs": {s.agent_id: s for s in self.config.agent_specs}
            | {HUMAN_AGENT: OWNER_SPEC},
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
            "external_decision_sources": {HUMAN_AGENT: _OwnerSource(self)},
        }
        if self.config.bootstrap_anchor is not None:
            # 与 run_one 同口径：锚按族内奇偶解析到每个代理（spec Q-501 / T963）。
            self.world["bootstrap_anchor"] = resolve_for_agents(
                self.config.bootstrap_anchor, self.config.agent_specs
            )
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
        self.session: SessionWriter | None = None
        self._session_path = None if session_path is None else Path(session_path)
        if self._session_path is not None:
            if self.roster is None:
                raise ValueError("a perturbation session needs a roster (roster_id, seed)")
            if self._session_path.exists():
                # 预热要几分钟：已落盘的会话不被改写，这一点在开始预热前就该失败。
                raise FileExistsError(self._session_path)
        if self.terminal == TERMINAL_OPEN:
            self._open_session()

    def _open_session(self) -> None:
        """会话随终端开放而建立：先落盘头记录，之后才可能有动作。"""
        if self._session_path is not None and self.session is None:
            assert self.roster is not None
            self.session = SessionWriter.create(
                self._session_path,
                {
                    "format_version": 1,
                    "session_id": self.session_id,
                    "arm": "human",
                    "replay_mode": "original",
                    "roster_id": self.roster.roster_id,
                    "seed": self.seed,
                    "engine_config_digest": session_engine_config_digest(self.roster),
                    "evidence_class": "experiment-preview",
                    "run_mode": "interactive",
                },
            )

    # ---------- 预热（T1125）----------

    def warm_up(self, stop: threading.Event | None = None) -> str:
        """不等墙钟连续推进，直到终端开放或窗口不成立（或 ``stop`` 被置位）；返回终端阶段。"""
        while self.terminal == TERMINAL_WARMING_UP and not (stop is not None and stop.is_set()):
            self.advance()
        return self.terminal

    def _track_warmup(self) -> None:
        total = self.kernel.committed_record_count
        for record in self.kernel.committed_records_tail(total - self._warmup_seen):
            if record.get("event_type") != "AGENT_DECIDE":
                continue
            agent_id = record.get("agent_id", "")
            timestamp = int(record.get("timestamp", 0))
            self._last_decision[agent_id] = timestamp
            if "bootstrap_anchor" in (record.get("internal_state") or {}):
                self._last_anchored[agent_id] = timestamp
        self._warmup_seen = total
        # 与 window_start_ns 同一判据：某代理的最后一条决策仍带锚，说明它还在冷启动。
        exited = all(
            self._last_decision[agent] > anchored for agent, anchored in self._last_anchored.items()
        )
        start = max(max(self._last_anchored.values(), default=0), self._warmup_burn_in_ns)
        if exited and start < self._warmup_cap_ns and self.logical_ns >= start:
            self.window_start_ns = start
            self.terminal = TERMINAL_OPEN
            self._open_session()
        elif self.logical_ns >= self._warmup_cap_ns:
            self.terminal = TERMINAL_NOT_APPLICABLE
            self.terminal_reason = "COLD_START_NOT_EXITED"

    # ---------- 人类委托 ----------

    def _enqueue(self, event: dict[str, Any]) -> None:
        """带水位追踪的入队：人类事件必须严格晚于调度器水位。"""

        ts = int(event.get("timestamp", 0))
        self._max_event_ts = max(self._max_event_ts, ts)
        self.kernel.enqueue(event)

    def _safe_ts(self) -> int:
        floor = max(self.logical_ns, self._max_event_ts)
        popped = getattr(self.kernel, "_last_popped_key", None)
        if popped is not None:
            floor = max(floor, int(popped.timestamp))
        pending = getattr(self.kernel, "_queue", None)
        if pending:
            floor = max(floor, max(int(item[0].timestamp) for item in pending))
        return floor + 1_000_000

    def push_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        """HTTP 线程：格式校验后原样入队，返回「已入队」；``order_id`` 由内核在决策事务里生成。"""
        if self.terminal != TERMINAL_OPEN:
            return {"accepted": False, "reason_code": self.terminal}
        item = _validate_order(payload)
        if isinstance(item, str):
            return {"accepted": False, "reason_code": item}
        self.orders.put(item)
        return {"accepted": True, "reason_code": "QUEUED"}

    def push_cancel(self, order_id: str) -> dict[str, Any]:
        """HTTP 线程：原样入队。

        ``order_id`` 能否反查成 owner 的挂单，要等 ``advance()`` 取出时判定。
        """
        if self.terminal != TERMINAL_OPEN:
            return {"accepted": False, "reason_code": self.terminal}
        if not order_id:
            return {"accepted": False, "reason_code": "INVALID_INPUT"}
        self.orders.put({"kind": "CANCEL", "order_id": order_id})
        return {"accepted": True, "reason_code": "QUEUED"}

    def _drain_owner_actions(self, advance_index: int) -> None:
        """持锁取出全部已入队的 owner 载荷：分配动作序号、追加动作行、入队 owner 观察。"""
        while True:
            try:
                item = self.orders.get_nowait()
            except queue.Empty:
                return
            if item["kind"] == "CANCEL":
                target = self._owner_action_by_order.get(item["order_id"])
                if target is None or self._owner_actions[target][0] != "LIMIT":
                    # 入队后才判定的无效撤单（spec §3 边界场景）：不是 owner 的挂单或编号
                    # 不存在——不是市场动作，丢弃，不进内核、不入动作日志。
                    continue
                kind, payload = "CANCEL", {"target_action_seq": target}
            else:
                kind = item["kind"]
                payload = {key: value for key, value in item.items() if key != "kind"}
            self._accept_owner_action(advance_index, kind, payload)

    def _accept_owner_action(self, advance_index: int, kind: str, payload: dict[str, Any]) -> int:
        # 先落盘再入队：进程在两者之间被终止时，日志里多一条内核没来得及处理的动作，
        # 而不是内核里有一条日志没有的动作。
        if self.session is not None:
            seq = self.session.append_action(
                advance_index=advance_index,
                kind=kind,
                payload=payload,
                wall_clock_ms=self._wall_clock_ms(),
            )["action_seq"]
        else:
            seq = self._action_seq + 1
        self._action_seq = seq
        self._owner_actions[seq] = (kind, payload)
        ts = self._safe_ts()
        self._enqueue(
            {
                "event_type": "AGENT_OBSERVE",
                "timestamp": ts,
                "agent_id": HUMAN_AGENT,
                "observed_at": ts,
                "market_data_event_id": "e1_0",
                "information_set": {},
                "_owner_action_seq": seq,
            }
        )
        return seq

    def seal_session(self) -> dict[str, Any] | None:
        """进程正常结束时封口：结束序号、该时点的事件摘要与 owner 观察摘要。"""
        with self.lock:
            if self.session is None or self.session.sealed:
                return None
            records = self.kernel.committed_records
            observations = [
                {
                    "action_seq": r["information_set"]["owner_action_seq"],
                    "digest": hashlib.blake2b(
                        canonical_serialize(r["information_set"]), digest_size=32
                    ).hexdigest(),
                }
                for r in records
                if r.get("event_type") == "AGENT_OBSERVE" and r.get("agent_id") == HUMAN_AGENT
            ]
            return self.session.seal(
                end_advance_index=self.advance_index,
                event_digest=rolling_digest_hex(records, get_registry()),
                observation_digests=observations,
            )

    # ---------- 驱动 ----------

    def advance(self, *, batch: int = 400) -> None:
        """推进一个逻辑秒：注入人类委托 → 内核批量处理 → 采样与稳定性指标。"""

        with self.lock:
            if self.dead:
                return
            advance_index = self.advance_index
            self.advance_index += 1
            self._drain_owner_actions(advance_index)
            target_logical = self.logical_ns + 1_000_000_000
            for _ in range(32):
                if self.logical_ns >= target_logical:
                    break
                self._tx_budget += batch
                try:
                    self.kernel.run(_dispatch_agents, self.world, max_transactions=self._tx_budget)
                except KernelAbort as exc:
                    self.dead = f"{exc.abort_code}: {exc}"
                    if self.terminal == TERMINAL_WARMING_UP:
                        self.terminal = TERMINAL_NOT_APPLICABLE
                        self.terminal_reason = "KERNEL_ABORT"
                    self.stability_events.append(
                        {"t_ns": self.logical_ns, "kind": "kernel-abort", "detail": self.dead}
                    )
                    return
                newest = self._newest_timestamp()
                if newest is not None:
                    self.logical_ns = max(self.logical_ns, newest)
            self.logical_ns = max(self.logical_ns, target_logical)
            self._snapshot()
            if self.terminal == TERMINAL_WARMING_UP:
                self._track_warmup()

    #: 推进循环每逻辑秒最多读 32 次尾部，只为取最新时间戳。
    _NEWEST_TAIL = 64

    def _newest_timestamp(self) -> int | None:
        # 0.4.1 T970：只读尾部。``committed_records`` 每次访问复制全部记录，
        # 每秒工作量恒定时墙钟仍随记录数增长（O(n²)）。
        records = self.kernel.committed_records_tail(self._NEWEST_TAIL)
        if not records:
            return None
        return max(int(item.get("timestamp", 0)) for item in records)

    # ---------- 观察视图 ----------

    def view(self) -> dict[str, Any]:
        with self.lock:
            records = self.kernel.committed_records
            book = self.world["book"]
            account = self.accounts[HUMAN_AGENT]
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
                    "forming": {60_000_000_000: forming} if forming else {},
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
                "terminal": {
                    "phase": self.terminal,
                    "reason_code": self.terminal_reason,
                    "window_start_ns": self.window_start_ns,
                    "warmup_target_ns": self._warmup_burn_in_ns,
                },
                "session_state": "RUNNING",
                "ui_state": None,
                "snapshot_revision": len(self.snapshots),
                "logical_timestamp": self.logical_ns,
                "error_code": self.dead,
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

    # ---------- 稳定性采样 ----------

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

    def export_metrics(self, out: Path) -> Path:
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "session_id": self.session_id,
            "seed": self.seed,
            # DR-501: the assembly travels with the artifact, so a report can be
            # traced back to who was in the market.
            "strategy_roster_id": self.roster_id,
            "bootstrap_anchor": dict(self.roster.bootstrap_anchor) if self.roster else None,
            "max_drawdown": round(self._max_drawdown, 6),
            "price_series": self.price_series,
            "stability_events": self.stability_events,
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return out


class _OwnerSource:
    """owner 的外部决策源：按观察携带的动作序号取载荷，撤单经本次运行的映射解析。"""

    def __init__(self, market: LiveMarket) -> None:
        self._market = market

    def __call__(self, event: dict[str, Any], world: dict[str, Any]) -> dict[str, Any]:
        seq = event["_owner_action_seq"]
        kind, payload = self._market._owner_actions[seq]
        tags = {
            "decision_source": "live_owner_terminal",
            "participant_class": "human",
            "owner_action_seq": seq,
        }
        intent_id = f"owner-a{seq}"
        if kind == "CANCEL":
            order_id = self._market._owner_order_ids.get(payload["target_action_seq"])
            if order_id is None:
                # 目标在本次运行里没有生成委托：按既有语义不动作，留原因码。
                return {
                    "kind": "NO_ACTION",
                    "reason_code": "CANCEL_TARGET_UNRESOLVED",
                    "internal_state": tags,
                }
            return {
                "kind": "CANCEL",
                "target_order_id": order_id,
                "intent_id": intent_id,
                "internal_state": tags,
            }
        return {"kind": kind, **payload, "intent_id": intent_id, "internal_state": tags}

    def orders_submitted(self, event: dict[str, Any], order_ids: list[str]) -> None:
        seq = event["_owner_action_seq"]
        for order_id in order_ids:
            self._market._owner_order_ids[seq] = order_id
            self._market._owner_action_by_order[order_id] = seq


def _validate_order(payload: dict[str, Any]) -> dict[str, Any] | str:
    """终端入口的格式校验：不通过的载荷不是市场动作，当场拒绝、不入队、不入日志。"""
    side = payload.get("side")
    order_type = payload.get("order_type", "MARKET")
    qty = payload.get("quantity_units")
    price = payload.get("price_ticks")
    if side not in {"BUY", "SELL"} or order_type not in {"MARKET", "LIMIT"}:
        return "INVALID_INPUT"
    if not isinstance(qty, int) or isinstance(qty, bool) or not 1 <= qty <= 1000:
        return "INVALID_INPUT"
    if order_type == "MARKET":
        if price is not None:
            return "INVALID_INPUT"
        return {"kind": "MARKET", "side": side, "quantity_units": qty}
    if not isinstance(price, int) or isinstance(price, bool) or price <= 0:
        return "INVALID_INPUT"
    return {"kind": "LIMIT", "side": side, "quantity_units": qty, "price_ticks": price}


def session_engine_config_digest(roster: StrategyRoster) -> str:
    """会话头记录的引擎配置指纹：roster 的引擎块 + owner 代理规格（两臂都注入，design §4）。"""
    body = {
        "engine": json.loads(json.dumps(dict(roster.engine))),
        "owner_spec": dataclasses.asdict(OWNER_SPEC),
    }
    return hashlib.blake2b(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8"), digest_size=16
    ).hexdigest()


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


def build_market(
    seed: int, roster_file: str | None = None, session_out: str | None = None
) -> LiveMarket:
    """The CLI's market: the 0.3.1 configuration, or the one a saved roster assembles.

    0.4.3 T1108: a roster file is loaded through :func:`load_roster`, so a file
    whose content no longer hashes to its name is refused instead of run.
    """
    if roster_file is None:
        if session_out is not None:
            raise ValueError("--session-out requires --roster-file")
        return LiveMarket(seed=seed)
    path = Path(roster_file)
    # 按清单启动的市场一律先预热（T1125）：owner 进入的是已在运行、已过窗口起点的市场。
    return LiveMarket(
        roster=load_roster(path.parent, path.stem), session_path=session_out, warmup=True
    )


def main(argv: list[str] | None = None) -> int:
    import argparse
    import time as _time

    parser = argparse.ArgumentParser(prog="market-game live-market")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--port", type=int, default=8791)
    parser.add_argument(
        "--tick-seconds",
        type=float,
        default=1.0,
        help=(
            "两次 advance 之间的墙钟间隔（秒）。每次 advance 至少推进 1 逻辑秒、实际推进量随事件"
            "而变，所以这不是 1:1 实时；预热阶段不等待这个间隔"
        ),
    )
    parser.add_argument(
        "--roster-file",
        help="按装配清单启动（<roster_id>.json，内容须仍哈希到该 id）；给出时 --seed 由清单决定",
    )
    parser.add_argument(
        "--session-out",
        help="0.4.2 会话 artifact 路径（JSONL，须不存在）；需同时给 --roster-file，正常退出时封口",
    )
    args = parser.parse_args(argv)

    market = build_market(args.seed, args.roster_file, args.session_out)
    market._epoch_ms = int(_time.time() * 1000)
    server = create_live_server(market, port=args.port)
    label = f"roster={market.roster_id}" if market.roster_id else f"seed={args.seed}"
    print(f"live AI market: http://127.0.0.1:{args.port} ({label})")

    stop = threading.Event()

    def _loop() -> None:
        if market.terminal == TERMINAL_WARMING_UP:
            print("warming up to the window start (orders refused until then) ...")
            phase = market.warm_up(stop)
            if phase == TERMINAL_WARMING_UP:
                return  # 预热中途被 Ctrl-C
            if phase != TERMINAL_OPEN:
                print(f"window not established ({market.terminal_reason}); terminal stays closed")
                server.shutdown()
                return
            print(f"terminal open at t={market.logical_ns // 1_000_000_000}s")
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
        thread.join()
        server.server_close()
        market.seal_session()
    return 0 if market.terminal == TERMINAL_OPEN else 2


if __name__ == "__main__":
    import sys

    sys.exit(main())
