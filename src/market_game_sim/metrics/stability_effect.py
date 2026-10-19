"""0.4.2 T1121（FR-603 / DR-602 / SC-603）：人类扰动配对的四个稳定性指标与退化判定。

口径唯一定义在 [`指标字典 §9`](../../../docs/research/metrics-dictionary.md)；本模块只引用
那里的指标 ID 与文档版本号，不另立第二份。复用 0.4.1 的既有实现，只加窗口：

* ``H2F-S-001`` 盘口可用率：``quality_run`` 的盘口网格与双边判定；
* ``H2F-S-002`` 大波动频次：``instability`` 的分钟收盘价与强平连锁扫描；
* ``H2F-S-003`` / ``H2F-S-004`` 最大回撤 / 最大涨幅：1 秒网格上的最新成交价，峰值（谷值）
  自窗口起点重置。

live 市场自带的 ``max_drawdown`` 与 ``big-move`` 是 0.4.1 终端的遗留诊断（累计峰值、
逐 advance），不是这里的指标。效应量、区间与报告由 T1131 在本模块之上实现。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from market_game_sim.metrics.instability import (
    CHAIN_DEPTH_THRESHOLD,
    MINUTE_MOVE_THRESHOLD,
    MINUTE_NS,
    minute_closes,
)
from market_game_sim.metrics.quality_run import (
    NS_PER_SECOND,
    SAMPLE_INTERVAL_NS,
    _book_state_grid,
    window_start_ns,
)

METRICS_DICTIONARY_VERSION = "0.3.0"

#: 统计窗口终点（spec SC-603：0.4.1 口径 [W0, 5700 s]）。
WINDOW_END_NS = 5700 * NS_PER_SECOND

BOOK_UPTIME = "H2F-S-001"
BIG_MOVE_FREQUENCY = "H2F-S-002"
MAX_DRAWDOWN = "H2F-S-003"
MAX_RISE = "H2F-S-004"
METRIC_IDS: tuple[str, ...] = (BOOK_UPTIME, BIG_MOVE_FREQUENCY, MAX_DRAWDOWN, MAX_RISE)

# 臂的退化原因码（指标字典 §9.3）。
WINDOW_NOT_ESTABLISHED = "WINDOW_NOT_ESTABLISHED"
KERNEL_ABORT = "KERNEL_ABORT"
NO_TRADES_IN_WINDOW = "NO_TRADES_IN_WINDOW"
NO_PRICE_AT_WINDOW_START = "NO_PRICE_AT_WINDOW_START"
NEVER_TWO_SIDED = "NEVER_TWO_SIDED"

# 配对状态。
VALID = "VALID"
DEGENERATE = "DEGENERATE"
ABORTED = "ABORTED"


@dataclass(frozen=True)
class ArmMeasurement:
    """一臂在配对窗口上的四个指标；``degenerate`` 非空时 ``metrics`` 不得进入效应量。"""

    window_start_ns: int
    window_end_ns: int
    metrics: Mapping[str, float | None]
    degenerate: tuple[str, ...]
    big_moves: int
    window_minutes: int


def pair_window_start(baseline_events: Sequence[Mapping[str, Any]]) -> int | None:
    """配对窗口起点 ``W0``：由基线臂求出、两臂共用；不成立时 ``None``（§9.1）。"""
    start = window_start_ns(baseline_events)
    if start is None or start >= WINDOW_END_NS:
        return None
    return start


def grid_times(start_ns: int, end_ns: int) -> list[int]:
    """与 0.4.1 盘口可用率同一套 1 秒网格：``W0 + j × 1 s``，不超过 ``end_ns``。"""
    return list(range(start_ns, end_ns + 1, SAMPLE_INTERVAL_NS))


def grid_prices(events: Sequence[Mapping[str, Any]], times: Sequence[int]) -> list[int | None]:
    """每个网格点上时间戳 ``≤ t`` 的最后一笔成交价（含窗口起点之前的成交）。"""
    trades = sorted(
        (
            (int(e["timestamp"]), int(e.get("transaction_seq", 0)), int(e["price_ticks"]))
            for e in events
            if e.get("event_type") == "TRADE_SETTLE"
        ),
    )
    prices: list[int | None] = []
    index = 0
    last: int | None = None
    for t in times:
        while index < len(trades) and trades[index][0] <= t:
            last = trades[index][2]
            index += 1
        prices.append(last)
    return prices


def max_drawdown(prices: Sequence[int]) -> float:
    """``max_j (1 − P_j / max_{i≤j} P_i)``；峰值从序列第一个点（窗口起点）开始。"""
    peak = prices[0]
    worst = 0.0
    for price in prices:
        peak = max(peak, price)
        worst = max(worst, 1 - price / peak)
    return worst


def max_rise(prices: Sequence[int]) -> float:
    """``max_j (P_j / min_{i≤j} P_i − 1)``；谷值从序列第一个点（窗口起点）开始。"""
    trough = prices[0]
    best = 0.0
    for price in prices:
        trough = min(trough, price)
        best = max(best, price / trough - 1)
    return best


def window_minutes(start_ns: int, end_ns: int) -> list[int]:
    """完整落在 ``[start_ns, end_ns]`` 里的逻辑分钟编号（``[m·60 s, (m+1)·60 s)``）。"""
    first = -(-start_ns // MINUTE_NS)
    last = end_ns // MINUTE_NS - 1
    return list(range(first, last + 1))


def big_move_count(events: Sequence[Mapping[str, Any]], start_ns: int, end_ns: int) -> int:
    """窗口内大波动事件数：两端分钟都在窗口内的分钟跳动 + 窗口内的强平连锁记录。"""
    minutes = set(window_minutes(start_ns, end_ns))
    closes = minute_closes(events)
    moves = 0
    for (prev_minute, prev_price), (minute, price) in zip(closes, closes[1:], strict=False):
        if prev_minute not in minutes or minute not in minutes or prev_price <= 0:
            continue
        if abs((price - prev_price) / prev_price) >= MINUTE_MOVE_THRESHOLD:
            moves += 1
    cascades = sum(
        1
        for e in events
        if e.get("event_type") == "MARGIN_CALL"
        and (e.get("chain_depth") or 0) >= CHAIN_DEPTH_THRESHOLD
        and start_ns <= int(e.get("timestamp", 0)) <= end_ns
    )
    return moves + cascades


def measure_arm(
    events: Sequence[Mapping[str, Any]],
    *,
    window_start: int,
    window_end: int = WINDOW_END_NS,
    aborted: bool = False,
) -> ArmMeasurement:
    """一臂在配对窗口 ``[window_start, window_end]`` 上的四个指标与退化原因码。"""
    times = grid_times(window_start, window_end)
    book = _book_state_grid(events, window_start, window_end)
    uptime = sum(1 for s in book if s[0] is not None and s[1] is not None) / len(book)
    minutes = window_minutes(window_start, window_end)
    moves = big_move_count(events, window_start, window_end)
    prices = grid_prices(events, times)
    in_window_trades = sum(
        1
        for e in events
        if e.get("event_type") == "TRADE_SETTLE"
        and window_start <= int(e.get("timestamp", 0)) <= window_end
    )

    degenerate: list[str] = []
    if aborted:
        degenerate.append(KERNEL_ABORT)
    if not minutes:
        degenerate.append(WINDOW_NOT_ESTABLISHED)
    if in_window_trades == 0:
        degenerate.append(NO_TRADES_IN_WINDOW)
    if prices[0] is None:
        degenerate.append(NO_PRICE_AT_WINDOW_START)
    if uptime == 0:
        degenerate.append(NEVER_TWO_SIDED)

    defined = prices[0] is not None
    series = [p for p in prices if p is not None] if defined else []
    return ArmMeasurement(
        window_start_ns=window_start,
        window_end_ns=window_end,
        metrics={
            BOOK_UPTIME: uptime,
            BIG_MOVE_FREQUENCY: moves * 60 / len(minutes) if minutes else None,
            MAX_DRAWDOWN: max_drawdown(series) if defined else None,
            MAX_RISE: max_rise(series) if defined else None,
        },
        degenerate=tuple(degenerate),
        big_moves=moves,
        window_minutes=len(minutes),
    )


def pair_status(baseline: ArmMeasurement | None, human: ArmMeasurement) -> str:
    """配对状态（§9.3）。

    基线臂窗口不成立（``None``）或退化 → 退化；否则人类臂中止 → 中止（扰动的结果，列入
    失效边界，不是退化）；否则人类臂退化 → 退化；否则有效。
    """
    if baseline is None or baseline.degenerate:
        return DEGENERATE
    if KERNEL_ABORT in human.degenerate:
        return ABORTED
    if human.degenerate:
        return DEGENERATE
    return VALID
