"""0.4.1 T972 (FR-503 / SC-503 / AC-506): 内生不稳定事件的**存在性判定**。

SC-503 的两个方向都算达标：出现即记录触发条件与频次；未出现则结论是「该市场结构在
冻结参数下不产生离散崩盘事件」——这是一个如实的研究发现，不是工程失败。所以本模块
不提供任何「让它出现」的旋钮：阈值是模块级冻结常量，跨种子运行不注入任何冲击，
判定函数对两种结果走同一条路径，只是把观测到的数量如实填进报告。

背景（spec §6 SC-503）：v0.1 的 128 个 paired block 里，全部 `occurrence` 假设的
`nonzero_block_counts` 均为 0——离散崩盘事件在当时的代理构成下从未出现过。本模块
就是为了让「这次出现了没有」这个问题有一个可重复运行的答案。

两类事件（口径由 spec §6 SC-503 拥有，本模块只实现）：

* **分钟级跳动**：相邻分钟收盘价的相对变化绝对值 ≥ :data:`MINUTE_MOVE_THRESHOLD`；
* **强平连锁**：`MARGIN_CALL` 记录的 `chain_depth ≥` :data:`CHAIN_DEPTH_THRESHOLD`
  ——深度 ≥1 意味着这次强平是**上一次强平的价格冲击**造成的，即连锁本身。
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

#: spec §6 SC-503：≥3% 的分钟级跳动。改这个数必须留 git 痕迹与理由（§5 不变量）。
MINUTE_MOVE_THRESHOLD = 0.03
#: spec §6 SC-503：`chain_depth >= 1` 即连锁（深度 0 是首次强平，不是连锁）。
CHAIN_DEPTH_THRESHOLD = 1
#: 分钟级的定义：1 逻辑分钟。
MINUTE_NS = 60_000_000_000

OCCURRED = "OCCURRED"
NOT_OBSERVED = "NOT_OBSERVED"

#: 未出现时的结论文本。写成常量而不是即兴措辞：它是一个研究结论，不是日志。
NOT_OBSERVED_CONCLUSION = (
    "该市场结构在冻结参数下不产生离散崩盘事件（分钟级跳动 < {move:.0%}，"
    "无 chain_depth >= {depth} 的强平连锁）。这是如实的观测结果，不是工程失败；"
    "不得通过调低阈值或注入冲击来制造「出现」（spec §6 SC-503）。"
)


@dataclass(frozen=True)
class InstabilityEvent:
    """一次不稳定事件及其触发条件。"""

    kind: str  # "minute_move" | "liquidation_cascade"
    timestamp_ns: int
    magnitude: float  # 跳动幅度，或连锁深度
    trigger: Mapping[str, Any]


@dataclass
class SeedScan:
    seed: int
    logical_seconds: float
    minute_moves: list[InstabilityEvent] = field(default_factory=list)
    cascades: list[InstabilityEvent] = field(default_factory=list)

    @property
    def occurred(self) -> bool:
        return bool(self.minute_moves or self.cascades)

    def as_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "logical_seconds": round(self.logical_seconds, 3),
            "occurred": self.occurred,
            "minute_move_count": len(self.minute_moves),
            "cascade_count": len(self.cascades),
            "events": [
                {
                    "kind": e.kind,
                    "timestamp_ns": e.timestamp_ns,
                    "magnitude": e.magnitude,
                    "trigger": dict(e.trigger),
                }
                for e in (*self.minute_moves, *self.cascades)
            ],
        }


def minute_closes(events: Sequence[Mapping[str, Any]]) -> list[tuple[int, int]]:
    """每个逻辑分钟的收盘价 ``(minute_index, last_price_ticks)``。"""
    closes: dict[int, int] = {}
    for event in events:
        if event.get("event_type") != "TRADE_SETTLE":
            continue
        minute = int(event.get("timestamp", 0)) // MINUTE_NS
        closes[minute] = int(event["price_ticks"])
    return sorted(closes.items())


def scan_minute_moves(events: Sequence[Mapping[str, Any]]) -> list[InstabilityEvent]:
    """相邻分钟收盘价的相对变化 ≥ 阈值的那些分钟。

    只比较**相邻**分钟：中间没有成交的分钟没有收盘价，跨过空档比较会把若干分钟
    的漂移算成一次跳动。空档本身由 `gap_minutes` 如实记录在触发条件里。
    """
    out: list[InstabilityEvent] = []
    closes = minute_closes(events)
    for (prev_minute, prev_price), (minute, price) in zip(closes, closes[1:], strict=False):
        if prev_price <= 0:
            continue
        move = (price - prev_price) / prev_price
        if abs(move) >= MINUTE_MOVE_THRESHOLD:
            out.append(
                InstabilityEvent(
                    kind="minute_move",
                    timestamp_ns=minute * MINUTE_NS,
                    magnitude=round(move, 6),
                    trigger={
                        "from_minute": prev_minute,
                        "to_minute": minute,
                        "gap_minutes": minute - prev_minute - 1,
                        "from_price_ticks": prev_price,
                        "to_price_ticks": price,
                    },
                )
            )
    return out


def scan_cascades(events: Sequence[Mapping[str, Any]]) -> list[InstabilityEvent]:
    """``chain_depth >= CHAIN_DEPTH_THRESHOLD`` 的强平记录及其链标识。"""
    out: list[InstabilityEvent] = []
    for event in events:
        if event.get("event_type") != "MARGIN_CALL":
            continue
        depth = event.get("chain_depth") or 0
        if depth < CHAIN_DEPTH_THRESHOLD:
            continue
        out.append(
            InstabilityEvent(
                kind="liquidation_cascade",
                timestamp_ns=int(event.get("timestamp", 0)),
                magnitude=float(depth),
                trigger={
                    "agent_id": event.get("agent_id"),
                    "chain_id": event.get("chain_id"),
                    "chain_depth": depth,
                    "margin_ratio_bp": event.get("margin_ratio_bp"),
                    "verdict": event.get("verdict"),
                },
            )
        )
    return out


def scan_run(events: Sequence[Mapping[str, Any]], *, seed: int, logical_seconds: float) -> SeedScan:
    return SeedScan(
        seed=seed,
        logical_seconds=logical_seconds,
        minute_moves=scan_minute_moves(events),
        cascades=scan_cascades(events),
    )


def build_existence_report(scans: Sequence[SeedScan]) -> dict[str, Any]:
    """存在性判定报告。两个方向走同一条路径，只是数字不同。"""
    if not scans:
        raise ValueError("existence verdict needs at least one seed")
    occurred = [s for s in scans if s.occurred]
    verdict = OCCURRED if occurred else NOT_OBSERVED
    moves = sum(len(s.minute_moves) for s in scans)
    cascades = sum(len(s.cascades) for s in scans)
    logical_minutes = sum(s.logical_seconds for s in scans) / 60
    report: dict[str, Any] = {
        "schema_version": 1,
        "evidence_class": "engineering-demonstration",
        "thresholds": {
            "minute_move": MINUTE_MOVE_THRESHOLD,
            "chain_depth": CHAIN_DEPTH_THRESHOLD,
            "minute_ns": MINUTE_NS,
        },
        "seeds": [s.seed for s in scans],
        "verdict": verdict,
        "seeds_with_events": [s.seed for s in occurred],
        "minute_move_count": moves,
        "cascade_count": cascades,
        "total_logical_minutes": round(logical_minutes, 3),
        "frequency_per_logical_hour": (
            round((moves + cascades) / logical_minutes * 60, 4) if logical_minutes else None
        ),
        "per_seed": [s.as_dict() for s in scans],
    }
    if verdict == NOT_OBSERVED:
        report["conclusion"] = NOT_OBSERVED_CONCLUSION.format(
            move=MINUTE_MOVE_THRESHOLD, depth=CHAIN_DEPTH_THRESHOLD
        )
    else:
        report["conclusion"] = (
            f"跨 {len(scans)} 个种子观测到 {moves} 次分钟级跳动与 {cascades} 次强平连锁；"
            "触发条件逐条记录在 per_seed.events 内。"
        )
    return report


def run_existence_study(
    *,
    seeds: Sequence[int],
    logical_seconds: int = 600,
    roster: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """跨种子跑纯 AI 市场并做存在性判定（**不注入任何冲击**）。"""
    import copy

    from market_game_sim.experiment.h2.live_market import DEFAULT_LIVE_ROSTER, LiveMarket

    body = copy.deepcopy(dict(roster or DEFAULT_LIVE_ROSTER))
    scans: list[SeedScan] = []
    for seed in seeds:
        body["seed"] = seed
        market = LiveMarket(roster=body)
        target = logical_seconds * 1_000_000_000
        while market.logical_ns < target and not market.dead:
            market.advance()
        scans.append(
            scan_run(
                market.kernel.committed_records,
                seed=seed,
                logical_seconds=market.logical_ns / 1_000_000_000,
            )
        )
    return build_existence_report(scans)


def save_report(report: Mapping[str, Any], path: str | pathlib.Path) -> pathlib.Path:
    out = pathlib.Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return out
