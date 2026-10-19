"""0.4.2 T1121 稳定性指标口径（AC-605）；T1131 skeleton。

T1131 的 strict-xfail 骨架：实现时替换为真实断言并摘除 xfail。口径见
docs/research/metrics-dictionary.md §9，规格见
docs/features/0.4/0.4.2-human-perturbation/spec.md §6。
"""

import pathlib

import pytest

from market_game_sim.metrics import stability_effect as se
from market_game_sim.metrics.quality_run import measure_quality

S = 1_000_000_000
W0 = 3660 * S


def _trade(seconds, price, seq=0):
    return {
        "event_type": "TRADE_SETTLE",
        "timestamp": int(seconds * S),
        "transaction_seq": seq,
        "price_ticks": price,
    }


def _book(seconds, bid=9_999, ask=10_001):
    return {
        "event_type": "MARKET_DATA_PUBLISH",
        "timestamp": int(seconds * S),
        "best_bid": bid,
        "best_ask": ask,
        "bid_depth_k": 1,
        "ask_depth_k": 1,
    }


def _margin_call(seconds, depth):
    return {"event_type": "MARGIN_CALL", "timestamp": int(seconds * S), "chain_depth": depth}


def _arm(trades, *, start=W0, end=W0 + 600 * S, extra=(), aborted=False):
    events = [_book(0), *trades, *extra]
    return se.measure_arm(events, window_start=start, window_end=end, aborted=aborted)


@pytest.mark.xfail(strict=True, reason="T1131 not implemented yet")
def test_effect_report_valid_degenerate_and_aborted_pairs():
    """AC-605：
    四指标逐种子差值、效应量与 90% 区间；退化配对与人类臂中止配对列入失效边界；
    有效配对低于下限时效应量缺省
    """
    pytest.fail("T1131 pending")


def test_drawdown_and_rise_reset_peak_at_window_start():
    """AC-605：最大回撤/最大涨幅在窗口起点重置峰值（窗口前跌幅不计入，正反两侧）"""
    # 窗口前从 120 跌到 100（又从 80 涨回 100）；窗口内 100 → 90 → 110。
    before = [_trade(3000, 120), _trade(3300, 80, 1), _trade(3600, 100, 2)]
    inside = [_trade(3700, 90, 3), _trade(3800, 110, 4)]
    arm = _arm(before + inside)
    assert arm.metrics[se.MAX_DRAWDOWN] == pytest.approx(1 - 90 / 100)
    assert arm.metrics[se.MAX_RISE] == pytest.approx(110 / 90 - 1)

    # 反向：同样的跌幅发生在窗口内，就计入。
    moved = [_trade(3600, 100), _trade(3700, 120, 1), _trade(3750, 90, 2), _trade(3800, 100, 3)]
    arm = _arm(moved)
    assert arm.metrics[se.MAX_DRAWDOWN] == pytest.approx(1 - 90 / 120)
    assert arm.metrics[se.MAX_RISE] == pytest.approx(120 / 100 - 1)

    # 单调上涨无回撤，单调下跌无涨幅。
    assert _arm([_trade(3600, 100), _trade(3700, 130, 1)]).metrics[se.MAX_DRAWDOWN] == 0
    assert _arm([_trade(3600, 100), _trade(3700, 70, 1)]).metrics[se.MAX_RISE] == 0


def test_prices_are_sampled_on_the_one_second_grid():
    """owner 2026-10-19 裁决：P_t 取 1 秒网格上的最新成交价——秒内毛刺不计，跨过网格点的计入。"""
    spike = [_trade(3600, 100), _trade(3700.2, 50, 1), _trade(3700.7, 100, 2)]
    assert _arm(spike).metrics[se.MAX_DRAWDOWN] == 0
    held = [_trade(3600, 100), _trade(3700.2, 50, 1), _trade(3701.4, 100, 2)]
    assert _arm(held).metrics[se.MAX_DRAWDOWN] == pytest.approx(0.5)

    times = se.grid_times(W0, W0 + 3 * S)
    assert times == [W0, W0 + S, W0 + 2 * S, W0 + 3 * S]
    # 同一时间戳的多笔成交取事务序最大的一笔；网格点恰有成交时取该笔。
    events = [_trade(3659, 7), _trade(3661, 8, 2), _trade(3661, 9, 1), _trade(3663, 5, 3)]
    assert se.grid_prices(events, times) == [7, 8, 8, 5]
    assert se.grid_prices([], times) == [None] * 4


def test_big_moves_count_only_minute_pairs_inside_the_window():
    """owner 2026-10-19 裁决：分钟变动对两端都完整落在窗口内才计；残缺分钟不计。"""
    start, end = 3690 * S, 3960 * S  # 窗口起点不在整分钟上：分钟 61 残缺
    assert se.window_minutes(start, end) == [62, 63, 64, 65]
    trades = [
        _trade(3610, 100),  # 分钟 60
        _trade(3670, 106, 1),  # 分钟 61（残缺）：60→61 跳 6%，不计
        _trade(3730, 100, 2),  # 分钟 62：61→62 跌 5.7%，61 不在窗口内，不计
        _trade(3790, 104, 3),  # 分钟 63：62→63 涨 4%，计入
        _trade(3850, 105, 4),  # 分钟 64：不足 3%
        _trade(3970, 120, 5),  # 分钟 66：越过窗口终点，64→66 不计
    ]
    extra = [_margin_call(3700, 1), _margin_call(3700, 0), _margin_call(3650, 2)]
    arm = _arm(trades, start=start, end=end, extra=extra)
    assert arm.big_moves == 2  # 一次分钟跳动 + 一条窗口内深度 ≥ 1 的强平
    assert arm.window_minutes == 4
    assert arm.metrics[se.BIG_MOVE_FREQUENCY] == pytest.approx(2 * 60 / 4)

    # 中间无成交的分钟不打断「相邻」（与 0.4.1 相同）。
    gap = [_trade(3730, 100), _trade(3850, 104, 1)]
    assert _arm(gap, start=start, end=end).big_moves == 1


def test_book_uptime_is_the_0_4_1_definition_on_the_pair_window():
    events = [_book(0), _book(3700, ask=None), _book(3710), _trade(3600, 100), _trade(3705, 99, 1)]
    end = W0 + 120 * S
    arm = se.measure_arm(events, window_start=W0, window_end=end)
    expected = measure_quality(events, window_start=W0, window_end=end, wall_seconds=1.0)
    assert arm.metrics[se.BOOK_UPTIME] == expected["two_sided_book_uptime"]
    assert 0 < arm.metrics[se.BOOK_UPTIME] < 1


def test_degeneracy_codes_and_pair_status():
    good = _arm([_trade(3600, 100), _trade(3700, 101, 1)])
    assert good.degenerate == ()
    assert set(good.metrics) == set(se.METRIC_IDS)

    no_trades = _arm([_trade(3600, 100)])
    assert no_trades.degenerate == (se.NO_TRADES_IN_WINDOW,)
    no_price = _arm([_trade(3700, 100)])
    assert no_price.degenerate == (se.NO_PRICE_AT_WINDOW_START,)
    assert no_price.metrics[se.MAX_DRAWDOWN] is None and no_price.metrics[se.MAX_RISE] is None
    one_sided = se.measure_arm(
        [_book(0, ask=None), _trade(3600, 100), _trade(3700, 101, 1)],
        window_start=W0,
        window_end=W0 + 600 * S,
    )
    assert one_sided.degenerate == (se.NEVER_TWO_SIDED,)
    short = _arm([_trade(3600, 100), _trade(3661, 101, 1)], end=W0 + 30 * S)
    assert short.degenerate == (se.WINDOW_NOT_ESTABLISHED,)
    assert short.metrics[se.BIG_MOVE_FREQUENCY] is None
    aborted = _arm([_trade(3600, 100), _trade(3700, 101, 1)], aborted=True)
    assert aborted.degenerate == (se.KERNEL_ABORT,)

    assert se.pair_status(good, good) == se.VALID
    assert se.pair_status(good, aborted) == se.ABORTED
    assert se.pair_status(good, no_trades) == se.DEGENERATE
    assert se.pair_status(aborted, good) == se.DEGENERATE, "基线臂中止是退化"
    assert se.pair_status(no_trades, aborted) == se.DEGENERATE, "基线退化优先于人类臂中止"
    assert se.pair_status(None, good) == se.DEGENERATE


def test_pair_window_start_comes_from_the_baseline_arm():
    def decide(seconds, anchored=False):
        state = {"bootstrap_anchor": {}} if anchored else {}
        return {
            "event_type": "AGENT_DECIDE",
            "timestamp": int(seconds * S),
            "agent_id": "a",
            "internal_state": state,
        }

    assert se.pair_window_start([decide(10), decide(4000)]) == W0
    late_exit = [decide(10, True), decide(4100, True), decide(4200)]
    assert se.pair_window_start(late_exit) == 4100 * S
    assert se.pair_window_start([decide(10, True), decide(4000, True)]) is None, "到最后仍在预热"
    stuck = [decide(10, True), decide(5800, True), decide(5900)]
    assert se.pair_window_start(stuck) is None, "W0 不早于 5700 s 即窗口不成立"


def test_metric_ids_and_version_live_in_the_dictionary():
    text = pathlib.Path("docs/research/metrics-dictionary.md").read_text(encoding="utf-8")
    assert f"**文档版本**：{se.METRICS_DICTIONARY_VERSION}" in text
    section = text[text.index("## 9. 人类扰动稳定性指标") :]
    for metric_id in se.METRIC_IDS:
        assert f"`{metric_id}`" in section
    for code in (
        se.KERNEL_ABORT,
        se.WINDOW_NOT_ESTABLISHED,
        se.NO_TRADES_IN_WINDOW,
        se.NO_PRICE_AT_WINDOW_START,
        se.NEVER_TWO_SIDED,
    ):
        assert f"`{code}`" in section


@pytest.mark.xfail(strict=True, reason="T1131 not implemented yet")
def test_underpowered_flag_when_observed_sd_exceeds_bound():
    """AC-605：实测 σ_d 超出 √2·σ_b 时报告带功效不足标注，未超出时不带"""
    pytest.fail("T1131 pending")
