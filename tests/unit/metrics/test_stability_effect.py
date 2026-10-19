"""0.4.2 T1121 稳定性指标口径、T1131 效应量报告（AC-605）。

口径见 docs/research/metrics-dictionary.md §9，规格见
docs/features/0.4/0.4.2-human-perturbation/spec.md FR-603、SC-603、§6。
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


# --------------------------------------------------------------------------- #
# T1131：效应量报告
# --------------------------------------------------------------------------- #


def _measurement(base_value, codes=()):
    metrics = {m: base_value + 0.001 * k for k, m in enumerate(se.METRIC_IDS)}
    return se.ArmMeasurement(W0, W0 + 600 * S, metrics, tuple(codes), 0, 10)


def _arm_summary(measurement, *, aborted=None, sc501=None, digest="d"):
    return {
        "run_digest": digest,
        "aborted": aborted,
        "logical_ns": 5000 * S if aborted else 5700 * S,
        "measurement": measurement,
        "sc501_failed": sc501,
        "out_of_window_actions": 1,
        "cancel_outcomes": [{"action_seq": 3, "target_action_seq": 1, "outcome": "CANCELLED"}],
    }


def _pair(seed, base, human, **arm):
    return {
        "seed": seed,
        "replay_mode": "open_loop_replay",
        "baseline": _arm_summary(base, sc501=arm.pop("sc501", []), digest=f"b{seed}"),
        "human": _arm_summary(human, digest=f"h{seed}", **arm),
    }


def _prereg(floor=3, sigma_b=0.05):
    return {
        "min_valid_pairs": floor,
        "sigma_b": dict.fromkeys(se.METRIC_IDS, sigma_b),
        "statistics": {"ci_level": 0.90, "n_resamples": 2000, "bootstrap_seed": 0},
    }


def _pairs():
    return [
        _pair(2001, _measurement(0.10), _measurement(0.13)),
        _pair(2002, _measurement(0.20), _measurement(0.21), sc501=["trades_per_minute"]),
        _pair(2003, _measurement(0.30), _measurement(0.35)),
        _pair(2004, _measurement(0.10, ["NO_TRADES_IN_WINDOW"]), _measurement(0.2)),
        _pair(2005, _measurement(0.10), _measurement(0.4, ["KERNEL_ABORT"]), aborted="INTERNAL: x"),
        _pair(2006, _measurement(0.10), None),
    ]


def _report(pairs=None, **prereg):
    case = se.original_case(
        session_id="s-1",
        seed=7,
        replay_ok=True,
        replay_reason=None,
        baseline=_measurement(0.1),
        human=_measurement(0.15),
        out_of_window_actions=0,
    )
    return se.build_effect_report(
        pairs=_pairs() if pairs is None else pairs,
        original_cases=[case],
        preregistration=_prereg(**prereg),
        preregistration_sha256="p" * 64,
        treatment={"content_hash": "c" * 64, "session_id": "s-1"},
        label="固定订单流扰动",
        carrier_disclaimer="载体 C 只作载体",
    )


def _keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _keys(item)


def test_effect_report_valid_degenerate_and_aborted_pairs():
    """AC-605：
    四指标逐种子差值、效应量与 90% 区间；退化配对与人类臂中止配对列入失效边界；
    有效配对低于下限时效应量缺省
    """
    report = _report()
    assert report["verdict"] == se.REPORTED and report["valid_pairs"] == 3
    assert [p["status"] for p in report["pairs"]] == [
        se.VALID,
        se.VALID,
        se.VALID,
        se.DEGENERATE,
        se.ABORTED,
        se.DEGENERATE,
    ]
    for metric in se.METRIC_IDS:
        block = report["metrics"][metric]
        assert block["differences"] == pytest.approx([0.03, 0.01, 0.05])
        assert block["effect"] == pytest.approx(0.03)
        assert block["ci_low"] <= block["effect"] <= block["ci_high"]
    boundary = report["failure_boundary"]
    assert [d["seed"] for d in boundary["degenerate"]] == [2004, 2006]
    assert boundary["degenerate"][1]["human"] == [se.WINDOW_INCOMPLETE]
    assert boundary["aborted"] == [{"seed": 2005, "abort": "INTERNAL: x", "logical_ns": 5000 * S}]
    assert boundary["sc501_failed"] == [{"seed": 2002, "items": ["trades_per_minute"]}]
    assert report["original_cases"][0]["differences"][se.MAX_DRAWDOWN] == pytest.approx(0.05)
    assert report["out_of_window_actions"] == 6
    assert report["evidence_class"] == "experiment-preview" and report["run_mode"] == "interactive"
    assert report["label"] == "固定订单流扰动"
    body = {k: v for k, v in report.items() if k != "content_hash"}
    assert report["content_hash"] == se._digest(body)
    assert not [k for k in _keys(report) if "crash" in k.lower()], "不以崩盘与否作结论形态"

    # 有效配对数低于下限：整份报告退化，效应量字段缺省而不是填 0。
    short = _report(floor=4)
    assert short["verdict"] == se.DEGENERATE_REPORT
    for block in short["metrics"].values():
        assert not {"effect", "ci_low", "ci_high"} & set(block)
        assert block["differences"], "差值与失效边界照常给出"


def test_underpowered_flag_when_observed_sd_exceeds_bound():
    """AC-605：实测 σ_d 超出 √2·σ_b 时报告带功效不足标注，未超出时不带"""
    loose = _report(sigma_b=0.05)["metrics"][se.MAX_DRAWDOWN]
    assert loose["observed_sigma_d"] == pytest.approx(0.02)
    assert loose["sigma_d_bound"] == pytest.approx(0.05 * 2**0.5)
    assert loose["underpowered"] is False and "power_note" not in loose
    tight = _report(sigma_b=0.01)["metrics"][se.MAX_DRAWDOWN]
    assert tight["underpowered"] is True and tight["power_note"] == se.UNDERPOWERED_NOTE


def test_original_cases_are_listed_but_never_pooled():
    matched = se.original_case(
        session_id="s",
        seed=7,
        replay_ok=True,
        replay_reason=None,
        baseline=_measurement(0.1),
        human=None,
        out_of_window_actions=2,
    )
    assert matched["window_complete"] is False and "differences" not in matched
    diverged = se.original_case(
        session_id="s",
        seed=7,
        replay_ok=False,
        replay_reason="REPLAY_DIVERGED",
        baseline=_measurement(0.1),
        human=_measurement(0.2),
        out_of_window_actions=0,
    )
    assert diverged["replay"] == "REPLAY_DIVERGED" and "differences" not in diverged
    # 原场个案不进入主效应量：只有开环配对的差值。
    report = _report()
    assert report["metrics"][se.MAX_DRAWDOWN]["valid_pairs"] == 3
