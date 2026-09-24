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
    # burn-in 注入短值：本组断言的是报告的诚实性（逐项判定、未通过项可见），
    # 不是市场是否达标；用冻结的 3660 秒会让每条断言都要跑一小时。
    report, diagnostics = quality_run.run_market_quality(
        logical_seconds=LOGICAL_SECONDS, burn_in_ns=5 * quality_run.NS_PER_SECOND
    )
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
    assert quality_run.window_start_ns(events, burn_in_ns=0) is None

    # b 也退出后，窗口起点是最后一个退出者的时刻。
    events.append(
        {"event_type": "AGENT_DECIDE", "agent_id": "b", "timestamp": 40, "internal_state": {}}
    )
    assert quality_run.window_start_ns(events, burn_in_ns=0) == 30

    # 无锚运行：冷启动这一半不设限（burn-in 仍另行把关）。
    assert quality_run.window_start_ns(events[1:2], burn_in_ns=0) == 0


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


# --------------------------------------------------------------------------- #
# AC-509 口径（owner 2026-09-24）：末段中位，不是全窗平均也不是逐秒峰值
# --------------------------------------------------------------------------- #


def test_tail_median_ignores_a_single_spike_but_catches_sustained_growth():
    """两种失效形态各一条：一次抖动不该判死，持续增长必须判死。"""
    steady = [(float(i + 1), 0.1) for i in range(100)]
    spiked = list(steady)
    spiked[50] = (51.0, 9.0)  # 一次 GC 抖动
    growing = [(float(i + 1), 0.02 + 0.008 * i) for i in range(100)]  # 单位成本单调上升

    assert quality_run._tail_median(steady) == pytest.approx(0.1)
    # 抖动落在窗口中部，末段中位不受影响；若口径是逐秒峰值，这条会被误判为超限。
    assert quality_run._tail_median(spiked) == pytest.approx(0.1)
    # 增长的运行末段远高于全窗平均：若口径是平均，这条会被放过。
    tail = quality_run._tail_median(growing)
    mean = sum(step for _, step in growing) / len(growing)
    assert tail > mean * 1.5
    assert tail > 0.5 > mean


def test_tail_median_degrades_to_the_whole_run_when_samples_are_few():
    assert quality_run._tail_median([(1.0, 0.2)]) == pytest.approx(0.2)
    assert quality_run._tail_median([]) is None


def test_step_rate_uses_the_logical_span_not_the_step_count():
    """advance 每步推进的逻辑时间不固定；单位必须是「每逻辑秒」而不是「每步」。"""
    two_seconds_per_step = [(2.0, 0.4), (4.0, 0.4)]
    assert quality_run._tail_median(two_seconds_per_step) == pytest.approx(0.2)


# --------------------------------------------------------------------------- #
# SC-502 #5 口径（owner 2026-09-24 修订）：主动成交方向，不是全部委托方向
# --------------------------------------------------------------------------- #


def _fill(ts: int, taker_delta: int) -> dict:
    return {
        "event_type": "TRADE_SETTLE",
        "timestamp": ts,
        "transaction_seq": ts,
        "price_ticks": 10_000,
        "postings": [
            {"role": "MAKER", "agent_id": "m", "position_delta_units": -taker_delta},
            {"role": "TAKER", "agent_id": "t", "position_delta_units": taker_delta},
        ],
    }


def test_order_flow_sign_comes_from_the_taker_side_of_a_fill():
    events = [_fill(1, 5), _fill(2, -3), _fill(3, 2)]
    assert quality_run._taker_signs(events, 0) == [1, -1, 1]


def test_quotes_no_longer_enter_the_order_flow_series():
    """修订前的失效形态：做市商占委托 95.9% 且机械交替，序列测的是报价机制。"""
    events = [
        {
            "event_type": "ORDER_ARRIVAL",
            "timestamp": 1,
            "transaction_seq": 1,
            "action": "SUBMIT",
            "agent_id": "market_maker_v2-0",
            "side": "BUY",
        },
        {
            "event_type": "ORDER_ARRIVAL",
            "timestamp": 2,
            "transaction_seq": 2,
            "action": "SUBMIT",
            "agent_id": "market_maker_v2-0",
            "side": "SELL",
        },
        _fill(3, 1),
    ]
    assert quality_run._taker_signs(events, 0) == [1]


def test_order_flow_series_respects_the_window_and_skips_undetermined_fills():
    events = [_fill(1, 1), _fill(5, -1)]
    assert quality_run._taker_signs(events, 3) == [-1]
    no_taker = {
        "event_type": "TRADE_SETTLE",
        "timestamp": 9,
        "transaction_seq": 9,
        "postings": [{"role": "MAKER", "agent_id": "m", "position_delta_units": 1}],
    }
    zero_delta = _fill(10, 0)
    assert quality_run._taker_signs([no_taker, zero_delta], 0) == []


# --------------------------------------------------------------------------- #
# 窗口起点 = max(冷启动退出, burn-in)（owner 2026-09-24 裁决，spec Q-501）
# --------------------------------------------------------------------------- #


def _decide(agent: str, ts: int, anchored: bool) -> dict:
    return {
        "event_type": "AGENT_DECIDE",
        "agent_id": agent,
        "timestamp": ts,
        "internal_state": {"bootstrap_anchor": "synthetic"} if anchored else {},
    }


def test_window_start_takes_the_later_of_anchor_exit_and_burn_in():
    """两者保护的不是同一件事，取较晚者才能同时堵住两个洞。"""
    # 冷启动退出晚于 burn-in：取冷启动退出
    late_anchor = [_decide("a", 900, True), _decide("a", 1000, False), _decide("a", 2000, False)]
    assert quality_run.window_start_ns(late_anchor, burn_in_ns=100) == 900
    # burn-in 晚于冷启动退出：取 burn-in
    assert quality_run.window_start_ns(late_anchor, burn_in_ns=1500) == 1500


def test_a_run_too_short_to_clear_burn_in_is_not_applicable():
    """0.4.1 首轮的实际失效形态：2200 秒的运行越不过 3660 秒的 burn-in。

    此时窗口内没有任何合格采样点，判定必须是「不适用」——拿无效样本给出 PASS/FAIL
    是更糟的结果，因为它看起来像一个结论。
    """
    events = [_decide("a", 10, True), _decide("a", 20, False)]
    assert quality_run.window_start_ns(events, burn_in_ns=quality_run.BURN_IN_NS) is None
    # 边界：起点必须严格早于运行末尾才算成立
    assert quality_run.window_start_ns(events, burn_in_ns=20) is None
    assert quality_run.window_start_ns(events, burn_in_ns=19) == 19


def test_default_burn_in_is_the_frozen_dictionary_value():
    """默认值就是指标字典 §2 的冻结值；注入参数只为测试驱动短窗口。"""
    assert quality_run.BURN_IN_NS == 61 * 60 * quality_run.NS_PER_SECOND
