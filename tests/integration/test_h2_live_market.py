"""0.3.2 持续 AI 市场生态：增量内核驱动 + 人类自由参与的回归门（ADR-010 方向）。

ADR-007 不存在于 docs/decisions/；本文件原先引用的就是这个空编号，
与 live_market.py 的模块 docstring 一并修正为 ADR-010。
"""

from __future__ import annotations

from market_game_sim.experiment.h2.live_market import HUMAN_AGENT, LiveMarket


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


def test_ai_market_has_no_injected_order_flow():
    """ADR-011 方案 D 否决门：live 市场不得靠注入流制造成交。

    历史上本模块带过一条 ``noise-flow`` 伪代理，每 3 逻辑秒发一笔市价单。实测它
    贡献了 87% 的成交（300 逻辑秒里 104/119 笔），却没有改善任何结构性指标——盘口
    可用率、中位档位、中位价差、价格振幅、大波动与强平计数全部与无注入版本一致。
    它只让成交计数好看，因此 ADR-011 明确否决这条路（方案 D）。

    本测试锁住"成交的每一方都是装配进来的真实代理或人类参与者"，让注入流一旦回来
    就变红，而不是等到有人拿它的成交数去写结论。
    """

    market = LiveMarket(seed=7)
    for _ in range(30):
        market.advance()

    # 判据必须取自**装配清单**而不是 market.accounts：注入流会先把自己塞进 accounts
    # 再下单，拿 accounts 当白名单等于让它自己给自己发通行证（本测试第一版就是这么写的，
    # 拿 HEAD 源码一跑才发现它对 noise-flow 是绿的）。
    known = (
        {spec.agent_id for spec in market.config.agent_specs}
        | set(market.config.extra_accounts)
        | {HUMAN_AGENT}
    )
    trades = [r for r in market.kernel.committed_records if r.get("event_type") == "TRADE_SETTLE"]
    assert trades, "AI 市场零成交，本断言失去意义"
    for trade in trades:
        for side in ("taker_agent_id", "maker_agent_id"):
            agent_id = trade.get(side)
            if agent_id is None:
                continue
            assert agent_id in known, f"{agent_id} 不在装配账户中——疑似注入流复活"

    # 正向一侧：人类下单后必须真的能成为成交对手方，避免把"禁止注入"误伤成"禁止外部委托"
    market.push_order(
        {"side": "BUY", "order_type": "MARKET", "quantity_units": 3, "price_ticks": None}
    )
    market.advance()
    takers = {
        r.get("taker_agent_id")
        for r in market.kernel.committed_records
        if r.get("event_type") == "TRADE_SETTLE"
    }
    assert HUMAN_AGENT in takers, "人类市价单未进入成交路径"


def test_view_surfaces_kernel_abort_through_error_code():
    """内核 abort 必须传到前端：之前 error_code 恒为 None，市场死了页面无感。"""

    market = LiveMarket(seed=7)
    market.advance()
    assert market.view()["error_code"] is None, "健康市场不应报错"

    market.dead = "LIQUIDATION_STALE: 构造的内核中止"
    assert market.view()["error_code"] == "LIQUIDATION_STALE: 构造的内核中止"


def test_module_entrypoint_serves_terminal_and_view():
    """live 市场必须保有可执行入口——否则只能靠 pytest 启动。"""

    import json
    import threading
    import urllib.request

    from market_game_sim.experiment.h2.live_market import create_live_server, main

    assert callable(main)

    market = LiveMarket(seed=7)
    for _ in range(3):
        market.advance()
    server = create_live_server(market, port=0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        page = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5).read()
        assert b"<" in page and len(page) > 1000, "终端页面未返回"
        raw = urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/v1/h2/owner/session", timeout=5
        ).read()
        view = json.loads(raw)
        assert "market" in view and "account" in view
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
