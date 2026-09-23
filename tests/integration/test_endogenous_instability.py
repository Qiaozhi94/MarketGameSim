"""0.4.1 T972 (FR-503 / SC-503 / AC-506): 内生不稳定事件的存在性判定。

SC-503 的两个方向都算达标，所以两条路径都要有断言：**出现**时记录触发条件与频次，
**未出现**时产出如实的「不存在」结论。阈值取自冻结常量——测试里不得就地改阈值，
那正是 SC-503 与 §5 不变量禁止的动作（为让结论翻面而动判据）。
"""

from __future__ import annotations

import json

import pytest

from market_game_sim.metrics import instability
from market_game_sim.metrics.instability import (
    CHAIN_DEPTH_THRESHOLD,
    MINUTE_MOVE_THRESHOLD,
    MINUTE_NS,
    NOT_OBSERVED,
    OCCURRED,
    build_existence_report,
    scan_run,
)


def _trade(minute: int, price: int) -> dict:
    return {
        "event_type": "TRADE_SETTLE",
        "timestamp": minute * MINUTE_NS + 1,
        "price_ticks": price,
        "quantity_units": 1,
    }


def _margin_call(depth: int, agent: str = "a-0") -> dict:
    return {
        "event_type": "MARGIN_CALL",
        "timestamp": 5 * MINUTE_NS,
        "agent_id": agent,
        "chain_id": f"mc-{agent}",
        "chain_depth": depth,
        "margin_ratio_bp": 120,
        "verdict": "PENDING_LIQUIDATION",
    }


# --------------------------------------------------------------------------- #
# 出现：记录触发条件与频次
# --------------------------------------------------------------------------- #


def test_minute_move_at_or_above_the_threshold_is_recorded_with_its_trigger():
    events = [_trade(0, 10_000), _trade(1, 10_300)]  # +3.0%
    scan = scan_run(events, seed=1, logical_seconds=120.0)
    assert scan.occurred
    [event] = scan.minute_moves
    assert event.kind == "minute_move"
    assert event.magnitude == pytest.approx(0.03)
    assert event.trigger["from_price_ticks"] == 10_000
    assert event.trigger["to_price_ticks"] == 10_300
    assert event.trigger["gap_minutes"] == 0


def test_liquidation_cascade_is_recorded_with_its_chain():
    events = [_trade(0, 10_000), _margin_call(depth=CHAIN_DEPTH_THRESHOLD)]
    scan = scan_run(events, seed=1, logical_seconds=60.0)
    [event] = scan.cascades
    assert event.kind == "liquidation_cascade"
    assert event.trigger["chain_id"] == "mc-a-0"
    assert event.trigger["chain_depth"] == CHAIN_DEPTH_THRESHOLD


def test_report_counts_frequency_across_seeds_when_events_occur():
    scans = [
        scan_run([_trade(0, 10_000), _trade(1, 10_400)], seed=1, logical_seconds=120.0),
        scan_run([_trade(0, 10_000), _margin_call(depth=2)], seed=2, logical_seconds=120.0),
    ]
    report = build_existence_report(scans)
    assert report["verdict"] == OCCURRED
    assert report["seeds_with_events"] == [1, 2]
    assert report["minute_move_count"] == 1
    assert report["cascade_count"] == 1
    assert report["frequency_per_logical_hour"] == pytest.approx(2 / 4 * 60)
    assert report["evidence_class"] == "engineering-demonstration"
    # 触发条件逐条留在报告里，不是只有计数。
    triggers = [e["trigger"] for seed in report["per_seed"] for e in seed["events"]]
    assert any("chain_id" in t for t in triggers)
    assert any("from_price_ticks" in t for t in triggers)


# --------------------------------------------------------------------------- #
# 未出现：如实的「不存在」结论
# --------------------------------------------------------------------------- #


def test_a_calm_market_yields_an_honest_not_observed_conclusion():
    events = [_trade(0, 10_000), _trade(1, 10_100), _margin_call(depth=0)]  # +1%，非连锁
    scan = scan_run(events, seed=7, logical_seconds=120.0)
    assert not scan.occurred
    report = build_existence_report([scan])
    assert report["verdict"] == NOT_OBSERVED
    assert report["minute_move_count"] == 0 and report["cascade_count"] == 0
    assert "不产生离散崩盘事件" in report["conclusion"]
    assert "不是工程失败" in report["conclusion"]


@pytest.mark.parametrize(
    ("price", "expected"),
    [(10_299, 0), (10_300, 1)],
    ids=["just-below-threshold", "exactly-at-threshold"],
)
def test_threshold_boundary_is_the_frozen_constant(price: int, expected: int):
    """边界两侧各一条：阈值是冻结常量，不是测试里可调的旋钮。"""
    assert MINUTE_MOVE_THRESHOLD == 0.03
    scan = scan_run([_trade(0, 10_000), _trade(1, price)], seed=1, logical_seconds=120.0)
    assert len(scan.minute_moves) == expected


def test_depth_zero_is_a_first_liquidation_not_a_cascade():
    scan = scan_run([_margin_call(depth=0)], seed=1, logical_seconds=60.0)
    assert scan.cascades == []


def test_moves_are_only_compared_between_adjacent_minutes():
    """中间没有成交的分钟没有收盘价；跨空档比较会把漂移算成一次跳动。"""
    events = [_trade(0, 10_000), _trade(9, 10_400)]  # 9 分钟内漂移 4%
    scan = scan_run(events, seed=1, logical_seconds=600.0)
    assert len(scan.minute_moves) == 1
    assert scan.minute_moves[0].trigger["gap_minutes"] == 8  # 空档如实记录


# --------------------------------------------------------------------------- #
# 真实跨种子运行（无注入）
# --------------------------------------------------------------------------- #


def test_cross_seed_study_runs_without_injection_and_reports_either_way(tmp_path):
    report = instability.run_existence_study(seeds=(7, 8), logical_seconds=90)
    assert report["seeds"] == [7, 8]
    assert report["verdict"] in {OCCURRED, NOT_OBSERVED}
    assert report["thresholds"] == {
        "minute_move": MINUTE_MOVE_THRESHOLD,
        "chain_depth": CHAIN_DEPTH_THRESHOLD,
        "minute_ns": MINUTE_NS,
    }
    assert len(report["per_seed"]) == 2
    assert report["conclusion"]
    path = instability.save_report(report, tmp_path / "instability.json")
    assert json.loads(path.read_text(encoding="utf-8"))["verdict"] == report["verdict"]
