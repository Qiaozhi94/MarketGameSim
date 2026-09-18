"""0.3.2 自由模拟合成历史 K 线生成器的回归门（tasks T932 年线视图）。"""

from market_game_sim.experiment.h2.owner_history import (
    HISTORY_DEPTHS,
    generate_history,
)


def test_history_depths_and_determinism():
    a = generate_history(10_000)
    b = generate_history(10_000)
    assert a == b, "同 seed 必须确定性"
    assert len(a[86_400_000_000_000]) == 365, "1D 必须覆盖全年 365 根"
    assert len(a[60_000_000_000]) == 3 * 24 * 60, "1m 深度 3 天"


def test_history_seam_and_ordering():
    bars = generate_history(10_000)[60_000_000_000]
    assert bars[-1]["close"] == 10_000, "末根收盘必须衔接引擎初始价"
    starts = [bar["start_ns"] for bar in bars]
    assert all(start < 0 for start in starts), "历史 bar 全部位于会话 t=0 之前"
    assert starts == sorted(starts), "bar 必须按时间升序"
    assert bars[1]["open"] == bars[0]["close"], "相邻 bar 开盘衔接前收"


def test_history_no_whitelist_leak_periods():
    assert 86_400_000_000_000 in HISTORY_DEPTHS, "1D 属自由模拟演示周期"
    assert set(HISTORY_DEPTHS) >= set(HISTORY_DEPTHS)
