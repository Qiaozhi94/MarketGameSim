"""0.4.1 T967 (FR-501 / FR-505 / AC-501 / AC-504, 成果门 H2-E1): 实测市场质量。

`metrics/market_quality.py`（T961）拥有 schema、门限与判定；`metrics/validation.py`
（0.1.2 协议 + T971）拥有统计检验。本模块是中间缺的一段：**把一个按 StrategyRoster
装配的纯 AI 市场跑起来，从它的事件流里量出那十一个数**，再交给上面两者判定。

口径（本模块只实现，不重新定义）：

* 统计窗口起点 = 最后一个代理退出冷启动之后（spec Q-501，`WINDOW_RULE`）。判据是
  事件流里最后一条带 `bootstrap_anchor` 的决策：锚只在预热期发单，其后该代理已退出。
  运行结束时仍有代理没退出 → 窗口不成立，报告判「不适用」且 `window` 排在未通过项
  首位——**不截断窗口、不剔除代理来凑**（Q-501 明令）；
* 采样 Δt = MD-001 = 1 逻辑秒（指标字典 §2），与 0.1.2 协议同一口径；
* 有效价差按指标字典 §3.3：`2 × |P_trade − mid_before|`，任一侧为空的那笔不计入。
  日志里 `valuation_mark_before_half_ticks` 在单边时退化为 `last × 2`，无法自证是不是
  真的中间价，因此用成交所在事务**之前**最近一次 `MARKET_DATA_PUBLISH` 的双边状态
  做准入，未通过准入的成交计入 `excluded_fills` 一并报告，不静默丢弃。

本模块的产出一律是 `engineering-demonstration`：它不进任何 evidence index，也不
建立研究声明（spec NFR-503）。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
import time
from collections.abc import Mapping, Sequence
from typing import Any

from market_game_sim.metrics import validation
from market_game_sim.metrics.market_quality import (
    FAT_TAILS,
    ORDER_FLOW_LONG_MEMORY,
    RETURN_AUTOCORRELATION,
    VOLATILITY_CLUSTERING,
    VOLUME_VOLATILITY_CORRELATION,
    MarketQualityReport,
    StylizedFactResult,
    build_report,
    save_report,
)
from market_game_sim.metrics.sampling import MarketSample, sample_market_series

#: MD-001：采样间隔 1 逻辑秒（指标字典 §2，一经用于正式实验即冻结）。
SAMPLE_INTERVAL_NS = 1_000_000_000
NS_PER_SECOND = 1_000_000_000
NS_PER_MINUTE = 60 * NS_PER_SECOND


# --------------------------------------------------------------------------- #
# 窗口（spec Q-501）
# --------------------------------------------------------------------------- #


def window_start_ns(events: Sequence[Mapping[str, Any]]) -> int | None:
    """最后一个代理退出冷启动的时刻；仍有代理未退出时返回 ``None``。

    锚只在预热期生效，所以「带锚的决策」等价于「该代理仍在预热」。某个代理的
    **最后一条**决策仍带锚，说明它到运行结束都没退出——此时窗口不成立。
    """
    last_anchored: dict[str, int] = {}
    last_decision: dict[str, int] = {}
    for event in events:
        if event.get("event_type") != "AGENT_DECIDE":
            continue
        agent_id = event.get("agent_id", "")
        timestamp = int(event.get("timestamp", 0))
        last_decision[agent_id] = timestamp
        if "bootstrap_anchor" in (event.get("internal_state") or {}):
            last_anchored[agent_id] = timestamp
    if not last_anchored:
        return 0  # 无锚运行：整段都可统计
    for agent_id, anchored_at in last_anchored.items():
        if last_decision.get(agent_id, -1) <= anchored_at:
            return None  # 该代理到最后仍在预热
    return max(last_anchored.values())


# --------------------------------------------------------------------------- #
# 六项市场质量（spec §6 SC-501）
# --------------------------------------------------------------------------- #


def _book_state_grid(
    events: Sequence[Mapping[str, Any]], start_ns: int, end_ns: int
) -> list[tuple[int | None, int | None, int, int]]:
    """按 Δt 网格取「该时刻之前（含）最近一次行情发布」的盘口状态。

    不用 ``sampling.MarketSample``：它在单边发布时沿用上一次的双边深度（前值填充
    对价格是对的，对「当下是否双边」不是），会把可用率算高。
    """
    published = sorted(
        ((int(e["timestamp"]), e) for e in events if e.get("event_type") == "MARKET_DATA_PUBLISH"),
        key=lambda pair: pair[0],
    )
    grid: list[tuple[int | None, int | None, int, int]] = []
    index = 0
    state: tuple[int | None, int | None, int, int] = (None, None, 0, 0)
    t = start_ns
    while t <= end_ns:
        while index < len(published) and published[index][0] <= t:
            record = published[index][1]
            state = (
                record.get("best_bid"),
                record.get("best_ask"),
                int(record.get("bid_depth_k") or 0),
                int(record.get("ask_depth_k") or 0),
            )
            index += 1
        grid.append(state)
        t += SAMPLE_INTERVAL_NS
    return grid


def _effective_spreads_bp(
    events: Sequence[Mapping[str, Any]], start_ns: int
) -> tuple[list[float], int]:
    """每笔成交的有效价差（bp）与被排除的笔数（指标字典 §3.3）。"""
    ordered = sorted(
        events, key=lambda e: (int(e.get("timestamp", 0)), e.get("transaction_seq", 0))
    )
    two_sided = False
    spreads: list[float] = []
    excluded = 0
    for event in ordered:
        kind = event.get("event_type")
        if kind == "MARKET_DATA_PUBLISH":
            two_sided = event.get("best_bid") is not None and event.get("best_ask") is not None
            continue
        if kind != "TRADE_SETTLE" or int(event.get("timestamp", 0)) < start_ns:
            continue
        mark_half = event.get("valuation_mark_before_half_ticks")
        if not two_sided or not mark_half:
            excluded += 1
            continue
        price = int(event["price_ticks"])
        spreads.append(abs(2 * price - int(mark_half)) / int(mark_half) * 2 * 10_000)
    return spreads, excluded


def measure_quality(
    events: Sequence[Mapping[str, Any]],
    *,
    window_start: int,
    window_end: int,
    wall_seconds: float,
) -> dict[str, float | None]:
    """六项市场质量的实测值（判定由 market_quality.py 做）。"""
    logical_seconds = max((window_end - window_start) / NS_PER_SECOND, 0.0)
    in_window = [e for e in events if int(e.get("timestamp", 0)) >= window_start]
    trades = [e for e in in_window if e.get("event_type") == "TRADE_SETTLE"]
    submits = [
        e
        for e in in_window
        if e.get("event_type") == "ORDER_ARRIVAL"
        and e.get("action") == "SUBMIT"
        and e.get("accepted") is not False
    ]
    grid = _book_state_grid(events, window_start, window_end)
    two_sided = [s for s in grid if s[0] is not None and s[1] is not None]
    levels = [min(s[2], s[3]) for s in grid]
    spreads, _excluded = _effective_spreads_bp(events, window_start)
    minutes = logical_seconds / 60 if logical_seconds else 0.0
    return {
        "trades_per_minute": (len(trades) / minutes) if minutes else None,
        "two_sided_book_uptime": (len(two_sided) / len(grid)) if grid else None,
        "median_book_levels_per_side": float(statistics.median(levels)) if levels else None,
        "median_effective_spread_bp": float(statistics.median(spreads)) if spreads else None,
        "fill_to_order_ratio": (len(trades) / len(submits)) if submits else None,
        "wall_seconds_per_logical_second": (
            (wall_seconds / logical_seconds) if logical_seconds else None
        ),
    }


# --------------------------------------------------------------------------- #
# 五项 stylized facts（spec §6 SC-502 表，检验在 validation.py）
# --------------------------------------------------------------------------- #


def _order_signs(events: Sequence[Mapping[str, Any]], start_ns: int) -> list[int]:
    return [
        1 if e.get("side") == "BUY" else -1
        for e in sorted(
            events, key=lambda e: (int(e.get("timestamp", 0)), e.get("transaction_seq", 0))
        )
        if e.get("event_type") == "ORDER_ARRIVAL"
        and e.get("action") == "SUBMIT"
        and e.get("side") in ("BUY", "SELL")
        and int(e.get("timestamp", 0)) >= start_ns
    ]


def measure_stylized_facts(
    events: Sequence[Mapping[str, Any]], *, window_start: int, window_end: int
) -> dict[str, StylizedFactResult]:
    """五项实测值；前三项复用 0.1.2 协议的既有检验，不另建第二套口径。"""
    samples: list[MarketSample] = sample_market_series(
        list(events), SAMPLE_INTERVAL_NS, start_ns=window_start, end_ns=window_end
    )
    returns = validation.compute_log_returns(samples)
    return {
        FAT_TAILS: validation._as_fact(validation.check_fat_tails(returns)),
        RETURN_AUTOCORRELATION: validation._as_fact(
            validation.check_return_autocorrelation(returns)
        ),
        VOLATILITY_CLUSTERING: validation.check_volatility_clustering_lags(returns),
        VOLUME_VOLATILITY_CORRELATION: validation.check_volume_volatility_correlation(samples),
        ORDER_FLOW_LONG_MEMORY: validation.check_order_flow_long_memory(
            _order_signs(events, window_start)
        ),
    }


# --------------------------------------------------------------------------- #
# 跑一个纯 AI 市场并出报告
# --------------------------------------------------------------------------- #


def _span(per_second: list[tuple[float, float]], index: int) -> float:
    """第 ``index`` 步覆盖的逻辑秒数（advance 每步推进的逻辑时间不一定是 1 秒）。"""
    prev = per_second[index - 1][0] if index else 0.0
    return max(per_second[index][0] - prev, 1e-9)


def _tail_median(per_second: list[tuple[float, float]], fraction: float = 0.25) -> float | None:
    """末段（默认最后 25%）每逻辑秒墙钟的中位数。

    AC-509 的判定口径：既不是全窗平均（会掩盖增长），也不是逐秒峰值（会被抖动
    误伤）。样本不足以切出末段时退化为全体中位，并且这一点在诊断里可见。
    """
    if not per_second:
        return None
    rates = [step / _span(per_second, i) for i, (_, step) in enumerate(per_second)]
    cut = max(1, int(len(rates) * fraction))
    return round(statistics.median(rates[-cut:]), 6)


def run_market_quality(
    *,
    roster: Mapping[str, Any] | None = None,
    logical_seconds: int = 600,
    run_id: str | None = None,
) -> tuple[MarketQualityReport, dict[str, Any]]:
    """跑一个按 roster 装配的纯 AI 市场，返回（报告, 诊断）。

    诊断不进报告 schema，但会随 artifact 落盘：它记录被排除的成交笔数、各族的委托
    与成交构成——「哪一族在交易」是判断异质性是否成立的前提，报告本身只给指标。
    """
    from market_game_sim.experiment.h2.live_market import DEFAULT_LIVE_ROSTER, LiveMarket

    body = dict(roster or DEFAULT_LIVE_ROSTER)
    market = LiveMarket(roster=body)
    target_ns = logical_seconds * NS_PER_SECOND
    wall = 0.0
    per_second: list[tuple[float, float]] = []  # (logical_seconds_at_end, wall_of_this_step)
    while market.logical_ns < target_ns:
        started = time.perf_counter()
        market.advance()
        step = time.perf_counter() - started
        wall += step
        per_second.append((market.logical_ns / NS_PER_SECOND, step))
        if market.dead:
            break
    events = market.kernel.committed_records
    start = window_start_ns(events)
    # AC-509 口径（owner 2026-09-24 裁决）：末段中位，不是全窗平均也不是逐秒峰值。
    # 平均会掩盖「单位成本随运行增长」——一个要持续运行的市场，衰减比平均值致命；
    # 逐秒峰值又会被一次 GC 抖动误伤。末段中位正好区分这两件事。
    tail_wall = _tail_median(per_second)
    end = int(market.logical_ns)
    quality = (
        measure_quality(events, window_start=start, window_end=end, wall_seconds=wall)
        | {"wall_seconds_per_logical_second": tail_wall}
        if start is not None
        else dict.fromkeys(
            (
                "trades_per_minute",
                "two_sided_book_uptime",
                "median_book_levels_per_side",
                "median_effective_spread_bp",
                "fill_to_order_ratio",
                "wall_seconds_per_logical_second",
            ),
            None,
        )
    )
    facts = (
        measure_stylized_facts(events, window_start=start, window_end=end)
        if start is not None
        else {
            name: StylizedFactResult("NOT_APPLICABLE", None, None, {"reason": "window_not_open"})
            for name in (
                FAT_TAILS,
                RETURN_AUTOCORRELATION,
                VOLATILITY_CLUSTERING,
                VOLUME_VOLATILITY_CORRELATION,
                ORDER_FLOW_LONG_MEMORY,
            )
        }
    )
    report = build_report(
        run_id=run_id or f"quality-{market.session_id}-s{market.seed}",
        roster_id=market.roster_id or "",
        logical_seconds=end / NS_PER_SECOND,
        window_start_logical_ns=start,
        quality=quality,
        stylized_facts=facts,
    )
    _spreads, excluded = _effective_spreads_bp(events, start or 0)
    diagnostics = {
        "evidence_class": "engineering-demonstration",
        "wall_seconds_per_logical_second_window_mean": (
            round(wall / (end / NS_PER_SECOND), 6) if end else None
        ),
        "wall_seconds_per_logical_second_tail_median": tail_wall,
        "wall_seconds_per_logical_second_peak": (
            round(
                max(
                    (step / _span(per_second, i) for i, (_, step) in enumerate(per_second)),
                    default=0.0,
                ),
                6,
            )
            if per_second
            else None
        ),
        "boundary": "工程演示，不进 evidence index，不建立研究声明（spec NFR-503）",
        "wall_seconds": round(wall, 3),
        "excluded_fills_without_two_sided_quote": excluded,
        "takers_by_family": _by_family(events, market, "TRADE_SETTLE"),
        "submits_by_family": _by_family(events, market, "ORDER_ARRIVAL"),
    }
    return report, diagnostics


def _by_family(events, market, kind: str) -> dict[str, int]:
    family = {spec.agent_id: (spec.strategy_family_id or "?") for spec in market.config.agent_specs}
    counts: dict[str, int] = {}
    for event in events:
        if event.get("event_type") != kind:
            continue
        agent = event.get("taker_agent_id") if kind == "TRADE_SETTLE" else event.get("agent_id")
        if kind == "ORDER_ARRIVAL" and event.get("action") != "SUBMIT":
            continue
        name = family.get(agent, "human/other")
        counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items()))


def main(argv: list[str] | None = None) -> int:
    """``python -m market_game_sim.metrics.quality_run --seconds 600 --out DIR``."""
    parser = argparse.ArgumentParser(description="Run the pure AI market and report its quality")
    parser.add_argument("--seconds", type=int, default=600, help="逻辑秒（默认 600）")
    parser.add_argument("--out", default="artifacts/0.4.1/quality")
    args = parser.parse_args(argv)

    report, diagnostics = run_market_quality(logical_seconds=args.seconds)
    out = pathlib.Path(args.out)
    path = save_report(report, out)
    (out / f"{report.run_id}-diagnostics.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    # 未通过项必须在第一屏可见（spec DR-502 / FR-505）。
    print(f"MarketQualityReport {path}")
    print(f"  roster={report.roster_id} logical_seconds={report.logical_seconds:.1f}")
    print(f"  window_start_ns={report.window_start_logical_ns}")
    print(f"  FAILED ({len(report.failed)}): {report.failed or '无'}")
    for name, value in report.quality.items():
        verdict = report.verdicts["quality"][name]
        print(f"  {verdict:15s} {name} = {value}")
    for name in report.stylized_facts:
        print(f"  {report.verdicts['stylized_facts'][name]:15s} stylized.{name}")
    print(f"  takers_by_family={diagnostics['takers_by_family']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
