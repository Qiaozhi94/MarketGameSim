"""0.3.2 自由模拟终端的合成历史 K 线（工程演示；采集态不提供，spec §5 白名单外）。

按 bar 粒度确定性生成"过去一年"的历史蜡烛：以 1m 为母粒度随机游走（blake2b
计数器模式），聚合出 5m/15m/1h/4h/1D；各周期保留深度上限（1D 全年 365 根，
越小周期截断越近）。历史 bar 的 ``start_ns`` 为负值（会话 t=0 之前），最后
一根的收盘价等于引擎 ``initial_price_ticks``——与实时行情无缝衔接。

仅自由模拟使用：``OwnerWebSession`` 对 training/formal 不提供该端点
（采集场景市场跨度为冻结的 60 逻辑秒，不存在年线；观察白名单不受影响）。
"""

from __future__ import annotations

import hashlib
from typing import Any

# 各周期保留的历史深度（bar 数）
HISTORY_DEPTHS: dict[int, int] = {
    60_000_000_000: 3 * 24 * 60,  # 1m × 3 天
    300_000_000_000: 7 * 288,  # 5m × 7 天
    900_000_000_000: 14 * 96,  # 15m × 14 天
    3_600_000_000_000: 60 * 24,  # 1h × 60 天
    14_400_000_000_000: 180 * 6,  # 4h × 180 天
    86_400_000_000_000: 365,  # 1D × 一年
}

_MINUTE_NS = 60_000_000_000


def _draw(seed: str) -> float:
    digest = hashlib.blake2b(seed.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") / 2**64


def generate_history(initial_price_ticks: int, *, seed: int = 7) -> dict[int, list[dict[str, Any]]]:
    """生成全部周期的历史蜡烛；最后一根 1m 收盘 == initial_price_ticks。"""

    # 母游走总长 = 各周期深度反推的最大分钟数（1D×365 → 一年 = 525,600 分钟）
    total_minutes = max(depth * (period // _MINUTE_NS) for period, depth in HISTORY_DEPTHS.items())

    # 1m 母随机游走：从 initial_price_ticks 反向生成，保证末根收盘无缝衔接。
    # closes[i] = 第 i 分钟收盘；closes[total_minutes] = initial_price_ticks。
    closes = [initial_price_ticks]
    for i in range(total_minutes - 1, -1, -1):
        step = int(round((_draw(f"{seed}:h1m:{i}") - 0.5) * 2 * 14))
        closes.append(max(1, closes[-1] - step))
    closes.reverse()

    def minute_bar(i: int) -> dict[str, Any]:
        open_p = closes[i]
        close_p = closes[i + 1]
        wick = 2 + int(_draw(f"{seed}:hw:{i}") * 8)
        return {
            "start_ns": -(total_minutes - i) * _MINUTE_NS,
            "open": open_p,
            "high": max(open_p, close_p) + wick,
            "low": max(1, min(open_p, close_p) - wick),
            "close": close_p,
            "volume": 50 + int(_draw(f"{seed}:vol:{i}") * 450),
        }

    # 2) 各周期：按 floor 分桶聚合（负时间戳同样对齐 t=0 边界）+ 深度截断
    out: dict[int, list[dict[str, Any]]] = {}
    for period, depth in HISTORY_DEPTHS.items():
        minutes_per_bar = period // _MINUTE_NS
        first_minute = total_minutes - depth * minutes_per_bar
        agg: list[dict[str, Any]] = []
        bucket: list[dict[str, Any]] = []
        bucket_key: int | None = None
        for i in range(first_minute, total_minutes):
            bar = minute_bar(i)
            key = bar["start_ns"] // period
            if bucket_key is None:
                bucket_key = key
            if key != bucket_key:
                agg.append(_aggregate(bucket_key * period, bucket))
                bucket = []
                bucket_key = key
            bucket.append(bar)
        if bucket:
            agg.append(_aggregate(bucket_key * period, bucket))
        out[period] = agg
    return out


def _aggregate(start_ns: int, group: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "start_ns": start_ns,
        "open": group[0]["open"],
        "high": max(b["high"] for b in group),
        "low": min(b["low"] for b in group),
        "close": group[-1]["close"],
        "volume": sum(b["volume"] for b in group),
    }
