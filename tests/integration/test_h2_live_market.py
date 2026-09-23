"""0.3.2 持续 AI 市场生态：增量内核驱动 + 人类自由参与的回归门（ADR-010 方向）。

ADR-007 不存在于 docs/decisions/；本文件原先引用的就是这个空编号，
与 live_market.py 的模块 docstring 一并修正为 ADR-010。
"""

from __future__ import annotations

import copy
import json
from collections import Counter

import pytest

from market_game_sim.agent.strategy_layer.families.trend_following import (
    TIME_SCALES as TREND_TIME_SCALES,
)
from market_game_sim.experiment.h2.live_market import (
    DEFAULT_LIVE_ROSTER,
    HUMAN_AGENT,
    LiveMarket,
)
from market_game_sim.experiment.roster import RosterError


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


# --------------------------------------------------------------------------- #
# 0.4.1 T966 (FR-503 / DR-501 / AC-503): 按 StrategyRoster 装配 live 市场
# --------------------------------------------------------------------------- #


def _roster(**overrides) -> dict:
    return copy.deepcopy(DEFAULT_LIVE_ROSTER) | overrides


def test_roster_assembles_every_declared_family_and_trades_without_injection():
    market = LiveMarket(roster=DEFAULT_LIVE_ROSTER)
    assert market.roster_id and market.roster_id.startswith("roster-")

    families = Counter(spec.strategy_family_id for spec in market.config.agent_specs)
    assert families == {
        "market_maker_v2": 6,
        "trend_following": 9,
        "mean_reversion": 9,
        "sentiment_noise": 6,
    }
    for _ in range(40):
        market.advance()

    view = market.view()
    assert view["market"]["recent_trades"], "清单装配的市场零成交"
    # ADR-011 方案 D 门：成交双方只能来自清单装配的代理或人类。
    assembled = {spec.agent_id for spec in market.config.agent_specs} | {HUMAN_AGENT}
    trades = [r for r in market.kernel.committed_records if r.get("event_type") == "TRADE_SETTLE"]
    for trade in trades:
        assert {trade["maker_agent_id"], trade["taker_agent_id"]} <= assembled

    # 报价必须来自清单声明的做市商族本身（T966 接线），而且逐代理分散——
    # 全员同价位正是 ADR-011 实测到的「中位档位 (1,1)」的成因。
    quotes: dict[str, set[int]] = {}
    for record in market.kernel.committed_records:
        if record.get("event_type") == "ORDER_ARRIVAL" and str(
            record.get("agent_id", "")
        ).startswith("market_maker_v2-"):
            quotes.setdefault(record["agent_id"], set()).add(record["price_ticks"])
    assert len(quotes) >= 2, "做市商族没有报价：族接线断了"
    assert len({frozenset(prices) for prices in quotes.values()}) > 1, "做市商族报价未分散"


def test_trend_followers_are_spread_across_time_scales():
    """多时间尺度是逐代理的：同族代理必须拿到不同的窗口，否则整族同步移动。"""
    market = LiveMarket(roster=DEFAULT_LIVE_ROSTER)
    indexes = [
        spec.strategy_private["time_scale_index"]
        for spec in market.config.agent_specs
        if spec.strategy_family_id == "trend_following"
    ]
    assert len(set(indexes)) == len(TREND_TIME_SCALES) > 1
    # 其他族不需要这个参数，不应被塞进私有状态。
    assert all(
        spec.strategy_private is None
        for spec in market.config.agent_specs
        if spec.strategy_family_id != "trend_following"
    )


def test_same_roster_and_seed_reproduce_the_price_series_pointwise():
    a = LiveMarket(roster=DEFAULT_LIVE_ROSTER)
    b = LiveMarket(roster=DEFAULT_LIVE_ROSTER)
    for _ in range(25):
        a.advance()
        b.advance()
    assert a.roster_id == b.roster_id
    assert a.price_series == b.price_series

    other = LiveMarket(roster=_roster(seed=DEFAULT_LIVE_ROSTER["seed"] + 1))
    for _ in range(25):
        other.advance()
    assert other.roster_id != a.roster_id

    # 换种子必须改变市场行为。比较的是**委托流**而不是价格序列：在这个长度的
    # 窗口里成交几乎全来自冷启动锚（按族内奇偶确定，与种子无关），价格还没开始
    # 移动，两条价格序列会恰好相同——价格发现是否成立由 T967/T973 的质量报告
    # 实测判定，不在本测试的断言范围内。
    def _order_flow(market: LiveMarket) -> list[tuple]:
        return [
            (r["agent_id"], r.get("side"), r.get("price_ticks"))
            for r in market.kernel.committed_records
            if r.get("event_type") == "ORDER_ARRIVAL"
        ]

    assert _order_flow(other) != _order_flow(a)


def test_roster_id_and_anchor_travel_with_the_metrics_artifact(tmp_path):
    market = LiveMarket(roster=DEFAULT_LIVE_ROSTER)
    for _ in range(5):
        market.advance()
    payload = json.loads(market.export_metrics(tmp_path / "m.json").read_text(encoding="utf-8"))
    assert payload["strategy_roster_id"] == market.roster_id
    assert payload["bootstrap_anchor"]["source"] == "synthetic"

    plain = LiveMarket(seed=7)
    plain_payload = json.loads(
        plain.export_metrics(tmp_path / "plain.json").read_text(encoding="utf-8")
    )
    assert plain_payload["strategy_roster_id"] is None
    assert plain_payload["bootstrap_anchor"] is None


def test_roster_decisions_carry_family_labels_across_families():
    market = LiveMarket(roster=DEFAULT_LIVE_ROSTER)
    for _ in range(20):
        market.advance()
    labelled = {
        record["internal_state"].get("strategy_family_id")
        for record in market.kernel.committed_records
        if record.get("event_type") == "AGENT_DECIDE"
    }
    assert {"trend_following", "mean_reversion", "sentiment_noise"} <= labelled


def test_unknown_family_fails_closed_at_assembly():
    bad = _roster()
    bad["families"][0] = bad["families"][0] | {"family_id": "no_such_family"}
    with pytest.raises(RosterError) as exc:
        LiveMarket(roster=bad)
    assert exc.value.code == "UNKNOWN_FAMILY"


def test_advance_never_copies_the_whole_log(monkeypatch):
    """0.4.1 T970: 推进循环只读尾部。

    性能门（tests/performance）断言的是墙钟，依机器而变；这条断言的是**机制**：
    每逻辑秒工作量恒定，却随记录数增长的墙钟来自 ``committed_records`` 的全量
    复制。这里直接禁止驱动循环碰它——否则 O(n²) 会悄悄长回来，而墙钟断言在
    短测试里未必红。
    """
    from market_game_sim.kernel.runner import EventKernel

    copies: list[int] = []
    original = EventKernel.committed_records.fget

    def counting(self):
        copies.append(len(self._committed_records))
        return original(self)

    monkeypatch.setattr(EventKernel, "committed_records", property(counting))

    market = LiveMarket(roster=DEFAULT_LIVE_ROSTER)
    for _ in range(10):
        market.advance()
    assert copies == [], f"advance() 复制了 {len(copies)} 次全量记录"

    # view() 需要全量记录是合理的（它要重建 K 线与盘口快照），不在禁令范围内。
    market.view()
    assert copies, "view() 未读取记录，说明这条守卫失去了对照"


def test_quoting_family_covers_both_sides_at_every_instant():
    """0.4.1 T967 根因守卫：同一报价时刻必须两侧都有报价。

    实测的失效形态：相位同步时 415/415 个报价时刻全族同侧，盘口在代理观察时刻
    几乎永远单边，而 ``order_intent_from_target`` 要求两侧同时存在——于是没有
    任何信号族能下单，市场停在「只有锚单成交」的状态（12 笔成交、价格不动）。
    """
    market = LiveMarket(roster=DEFAULT_LIVE_ROSTER)
    for _ in range(30):
        market.advance()

    per_instant: dict[int, set[str]] = {}
    for record in market.kernel.committed_records:
        if (
            record.get("event_type") == "ORDER_ARRIVAL"
            and record.get("action") == "SUBMIT"
            and str(record["agent_id"]).startswith("market_maker_v2-")
        ):
            per_instant.setdefault(record["timestamp"], set()).add(record["side"])
    assert per_instant, "做市商族没有报价"
    single_sided = [ts for ts, sides in per_instant.items() if len(sides) < 2]
    assert not single_sided, f"{len(single_sided)}/{len(per_instant)} 个报价时刻只有单侧"


def test_signal_families_trade_once_the_book_is_two_sided():
    """根因修复的正面判据：成交不再只来自冷启动锚，价格会动。"""
    market = LiveMarket(roster=DEFAULT_LIVE_ROSTER)
    for _ in range(30):
        market.advance()
    trades = [r for r in market.kernel.committed_records if r.get("event_type") == "TRADE_SETTLE"]
    assert len(trades) > 50, f"只有 {len(trades)} 笔成交：市场仍然几乎不成交"
    assert len({t["price_ticks"] for t in trades}) > 1, "所有成交同价：价格没有移动"
    # 锚只在预热期发单；预热后仍有成交，说明是策略族在交易。
    anchor_window_ns = 2_000_000_000
    assert [t for t in trades if t["timestamp"] > anchor_window_ns], "预热期之后没有成交"
