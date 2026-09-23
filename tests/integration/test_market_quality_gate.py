"""0.4.1 T967（成果门 H2-E1，FR-501 / FR-505 / AC-501 / AC-504 / E6）：质量门。

E6 的判定口径是**逐项如实判定 + 未通过项顶层可见**，不是「六项全达标」——价格发现
来自策略族异质（ADR-011 §决策 3），异质策略族在 Phase 2 才齐备，Phase 1 达标在机制上
不成立。所以这里断言的是**报告的诚实性**：

* 冷启动之后市场自发成交、盘口双边；
* 六项逐项判定，未达标项出现在 `failed` 顶层，且不被 `NOT_APPLICABLE` 混过去；
* 窗口不成立时整份报告判不适用，`window` 排在首位（Q-501：不截断、不剔除代理）；
* 统计特征样本量不足时判不适用，而不是拿短序列硬算。
"""

from __future__ import annotations

import json

import pytest

from market_game_sim.metrics import quality_run
from market_game_sim.metrics.market_quality import (
    NOT_APPLICABLE,
    PASS,
    QUALITY_THRESHOLDS,
    STYLIZED_FACTS,
    StylizedFactResult,
    load_report,
    save_report,
)

LOGICAL_SECONDS = 180


@pytest.fixture(scope="module")
def measured():
    report, diagnostics = quality_run.run_market_quality(logical_seconds=LOGICAL_SECONDS)
    return report, diagnostics


def test_cold_start_leads_to_a_market_that_trades_on_its_own(measured):
    """AC-501 / E6 的正面判据：窗口成立，且窗口内自发成交、盘口双边。"""
    report, _ = measured
    assert report.window_start_logical_ns is not None, "窗口未开：仍有代理没退出冷启动"
    assert report.roster_id.startswith("roster-")
    assert report.quality["trades_per_minute"] and report.quality["trades_per_minute"] > 0
    assert report.quality["two_sided_book_uptime"] and report.quality["two_sided_book_uptime"] > 0.5
    # 锚只在预热期发单；窗口起点之后仍在成交，说明交易不是锚撑出来的。
    assert report.verdicts["quality"]["trades_per_minute"] == PASS


def test_every_quality_item_is_judged_and_failures_are_top_level(measured):
    """AC-504：六项逐项判定；未通过项在顶层 `failed` 里，不靠读者自己比对门限。"""
    report, _ = measured
    assert set(report.verdicts["quality"]) == set(QUALITY_THRESHOLDS)
    assert set(report.verdicts["stylized_facts"]) == set(STYLIZED_FACTS)
    for name, verdict in report.verdicts["quality"].items():
        assert verdict != PASS or f"quality.{name}" not in report.failed
        if verdict != PASS:
            assert f"quality.{name}" in report.failed, name
    for name, verdict in report.verdicts["stylized_facts"].items():
        if verdict != PASS:
            assert f"stylized_facts.{name}" in report.failed, name
    # NOT_APPLICABLE 不是通过：它同样进 failed。
    not_applicable = [
        name
        for name, verdict in report.verdicts["stylized_facts"].items()
        if verdict == NOT_APPLICABLE
    ]
    for name in not_applicable:
        assert f"stylized_facts.{name}" in report.failed


def test_report_round_trips_and_is_content_addressed(measured, tmp_path):
    report, _ = measured
    path = save_report(report, tmp_path)
    reloaded = load_report(path)
    assert reloaded.content_hash == report.content_hash
    assert reloaded.failed == report.failed
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["failed"] == report.failed  # 顶层可见，不用解析 verdicts 才知道
    assert payload["content_hash"] == report.content_hash


def test_diagnostics_name_the_evidence_class_and_who_actually_traded(measured):
    """E6 证据标签；以及「哪一族在交易」——异质性是否成立的前提事实。"""
    _, diagnostics = measured
    assert diagnostics["evidence_class"] == "engineering-demonstration"
    assert diagnostics["takers_by_family"], "没有任何成交方记录"
    assert sum(diagnostics["takers_by_family"].values()) > 0


def test_window_does_not_open_while_an_agent_is_still_warming_up():
    """Q-501 反面：某代理到最后仍在预热 → 窗口不成立，不得截断凑出窗口。"""
    events = [
        {
            "event_type": "AGENT_DECIDE",
            "agent_id": "a",
            "timestamp": 10,
            "internal_state": {"bootstrap_anchor": "synthetic"},
        },
        {"event_type": "AGENT_DECIDE", "agent_id": "a", "timestamp": 20, "internal_state": {}},
        {
            "event_type": "AGENT_DECIDE",
            "agent_id": "b",
            "timestamp": 30,
            "internal_state": {"bootstrap_anchor": "synthetic"},
        },
    ]
    assert quality_run.window_start_ns(events) is None

    # b 也退出后，窗口起点是最后一个退出者的时刻。
    events.append(
        {"event_type": "AGENT_DECIDE", "agent_id": "b", "timestamp": 40, "internal_state": {}}
    )
    assert quality_run.window_start_ns(events) == 30

    # 无锚运行：整段可统计。
    assert quality_run.window_start_ns(events[1:2]) == 0


def test_an_unopened_window_makes_the_whole_report_not_applicable():
    from market_game_sim.metrics.market_quality import WINDOW, build_report

    report = build_report(
        run_id="r",
        roster_id="roster-x",
        logical_seconds=100.0,
        window_start_logical_ns=None,
        quality=dict.fromkeys(QUALITY_THRESHOLDS),
        stylized_facts={
            name: StylizedFactResult(NOT_APPLICABLE, None, None, {}) for name in STYLIZED_FACTS
        },
    )
    assert report.failed[0] == WINDOW
    assert all(v == NOT_APPLICABLE for v in report.verdicts["quality"].values())


def test_effective_spread_excludes_fills_without_a_two_sided_quote():
    """指标字典 §3.3：单边簿的那笔不计入，且排除数如实报告，不静默丢弃。"""
    events = [
        {"event_type": "MARKET_DATA_PUBLISH", "timestamp": 1, "best_bid": None, "best_ask": 100},
        {
            "event_type": "TRADE_SETTLE",
            "timestamp": 2,
            "price_ticks": 100,
            "valuation_mark_before_half_ticks": 200,
        },
        {"event_type": "MARKET_DATA_PUBLISH", "timestamp": 3, "best_bid": 99, "best_ask": 101},
        {
            "event_type": "TRADE_SETTLE",
            "timestamp": 4,
            "price_ticks": 101,
            "valuation_mark_before_half_ticks": 200,
        },
    ]
    spreads, excluded = quality_run._effective_spreads_bp(events, 0)
    assert excluded == 1
    assert len(spreads) == 1
    assert spreads[0] == pytest.approx(2 * abs(2 * 101 - 200) / 200 * 10_000)
