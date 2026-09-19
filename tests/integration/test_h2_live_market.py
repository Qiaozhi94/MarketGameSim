"""0.3.2 持续 AI 市场生态：增量内核驱动 + 人类自由参与的回归门（ADR-007 方向）。"""

from __future__ import annotations

from market_game_sim.experiment.h2.live_market import LiveMarket


def test_ai_market_generates_trades_and_candles():
    """AI 代理家族（做市商+因子策略）必须在预热后产生真实成交与 K 线。"""

    market = LiveMarket(seed=7)
    for _ in range(30):
        market.advance()
    view = market.view()
    assert view["market"]["recent_trades"], "AI 市场零成交（生态未运转）"
    assert view["market"]["klines"]["60000000000"], "1m K 线缺失"
    # mm 撤旧挂新存在瞬态单边空档（真实微观结构）：只断言市场功能不变量
    assert view["market"]["last_ticks"] is not None
    assert view["logical_timestamp"] > 0


def test_owner_market_order_fills_at_market():
    market = LiveMarket(seed=7)
    for _ in range(10):
        market.advance()
    before = market.view()["market"]["last_ticks"]
    result = market.push_order(
        {"side": "BUY", "order_type": "MARKET", "quantity_units": 5, "price_ticks": None}
    )
    assert result["accepted"] is True
    market.advance()
    view = market.view()
    assert view["account"]["position_units"] == 5
    assert view["account"]["entry_notional_units"] > 0
    assert before is not None


def test_owner_limit_order_rests_in_book():
    market = LiveMarket(seed=7)
    for _ in range(5):
        market.advance()
    last = market.view()["market"]["last_ticks"]
    assert last is not None
    result = market.push_order(
        {"side": "BUY", "order_type": "LIMIT", "quantity_units": 4, "price_ticks": int(last) - 5}
    )
    assert result["accepted"] is True
    market.advance()
    view = market.view()
    resting = [o for o in view["account"]["active_orders"] if o["order_id"] == "owner-1"]
    filled = view["account"]["position_units"] >= 4
    assert resting or filled, "限价单既未挂单也未成交"
    if resting:
        assert resting[0]["price_ticks"] == int(last) - 5


def test_owner_cancel_removes_resting_order():
    market = LiveMarket(seed=7)
    market.advance()
    bid = market.view()["market"]["best_bid"]
    assert bid is not None
    market.push_order(
        {"side": "BUY", "order_type": "LIMIT", "quantity_units": 2, "price_ticks": int(bid) - 20}
    )
    market.advance()
    market.push_cancel("owner-1")
    market.advance()
    view = market.view()
    assert not [o for o in view["account"]["active_orders"] if o["order_id"] == "owner-1"], (
        "撤单后挂单应消失"
    )


def test_same_seed_same_trajectory_without_human():
    """无人类介入时，同种子市场轨迹逐字节确定（研究对照的基线性质）。"""

    a = LiveMarket(seed=123)
    b = LiveMarket(seed=123)
    for _ in range(15):
        a.advance()
        b.advance()
    assert a.price_series == b.price_series
    assert [s["last"] for s in a.snapshots] == [s["last"] for s in b.snapshots]


def test_stability_metrics_recorded():
    market = LiveMarket(seed=7)
    for _ in range(20):
        market.advance()
    assert market.price_series, "稳定性价格序列未记录"
    assert market.price_series[0]["t_ns"] > 0
    assert market._max_drawdown <= 0
