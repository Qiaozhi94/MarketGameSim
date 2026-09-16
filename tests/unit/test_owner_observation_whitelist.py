"""回归门：最终交付版（单交易页 + 多品种行情页）的原型结构约束。

owner 2026-09-14 定稿（取代 V032 旧门禁，见 interaction-design-notes.md）：
- 导航为 行情/交易/资产 三入口；无合约或研究独立页（单一合成市场，两套交易页属重复设计）；
- 交易页对齐币安合约页要素：杠杆选择条（默认 1×）、买入/卖出页签、
  当前持仓/当前委托/操作回报底栏；
- 行情页为真实币种多品种汇总表（含每行折线走势），无 PERPETUAL 价格行；
- 用户面无开发态解释文字（评审工具条仅 #review 显示，说明迁 notes 文档）；
- 采集白名单机制保留：free-only 字段在采集态隐藏（coll-mode CSS）。
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

MILESTONE = (
    Path(__file__).resolve().parents[2] / "docs" / "features" / "0.3" / "0.3.2-web-trading-terminal"
)
PROTOTYPE = (MILESTONE / "interaction-design.html").read_text(encoding="utf-8")

# 导航入口（顺序即排列顺序）
NAV_VIEWS = ("markets", "trade", "assets")
# 行情页品种（真实加密货币名，对 USDT）
MARKET_PAIRS = (
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "BNB/USDT",
    "XRP/USDT",
    "DOGE/USDT",
    "ADA/USDT",
    "LTC/USDT",
)
# 用户面禁用的开发态标记（原型任意可见位置不得出现）
DEV_TOKENS = ("DQ-", "ADR-00", "V032", "（演示", "seed 7", "PERPETUAL-SIM-1")


class _NavParser(HTMLParser):
    """按出现顺序收集顶部导航的 data-view 序列。"""

    def __init__(self) -> None:
        super().__init__()
        self.views: list[str] = []
        self._in_nav = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = dict(attrs)
        if tag == "nav":
            self._in_nav = True
        elif self._in_nav and tag == "span" and "data-view" in data:
            self.views.append(data["data-view"])

    def handle_endtag(self, tag: str) -> None:
        if tag == "nav":
            self._in_nav = False


def _nav_views() -> list[str]:
    p = _NavParser()
    p.feed(PROTOTYPE)
    return p.views


def test_nav_is_markets_trade_assets_in_order():
    assert _nav_views() == ["markets", "trade", "assets"], _nav_views()


def test_no_contract_or_research_nav_entry():
    for token in ("合约", "研究", "contract", "research"):
        for view in _nav_views():
            assert token != view or view not in ("contract", "research"), (
                f"导航不应包含独立入口：{view}"
            )
    assert 'data-view="contract"' not in PROTOTYPE
    assert 'data-view="research"' not in PROTOTYPE


def test_real_crypto_pairs_in_markets_table():
    """行情页为真实币种汇总表，含折线走势列；无 PERPETUAL 价格行。"""
    for pair in MARKET_PAIRS:
        assert pair in PROTOTYPE, f"行情页缺少品种 {pair}"
    assert "PERPETUAL-SIM-1" not in PROTOTYPE, (
        "行情页不得出现合成品种名（owner 要求使用真实加密货币名）"
    )
    assert "走势" in PROTOTYPE, "行情页缺折线走势列"
    assert "drawSpark" in PROTOTYPE, "行情页缺每行折线绘制"


def test_trade_page_leverage_defaults_to_1x_and_is_discoverable():
    assert "leverage:1" in PROTOTYPE, "杠杆默认必须为 1×"
    assert 'id="lev-btns"' in PROTOTYPE, "交易页缺杠杆选择条"
    assert "[1,2,3,5,10]" in PROTOTYPE, "杠杆档位应由 JS 生成 1–10×"


def test_assets_page_layout_and_content():
    assert 'id="assets-grid"' in PROTOTYPE, "初始资金与资产总览须并列布局"
    overview = PROTOTYPE.index("资产总览")
    capital = PROTOTYPE.index("初始资金")
    assert capital < overview, "初始资金卡应位于资产总览左侧"
    for section in ("当前持仓", "历史持仓收益", "合约信息", "市场机制"):
        assert section in PROTOTYPE, f"资产页缺少 {section}"


def test_collection_gating_mechanism_preserved():
    """采集白名单机制保留：coll-mode 隐藏 free-only 字段；合约资金费用行带标记。"""
    assert "body.coll-mode .free-only{display:none !important}" in PROTOTYPE
    assert 'id="contract-funding"' in PROTOTYPE
    assert (
        "free-only"
        in PROTOTYPE[
            PROTOTYPE.index('id="contract-funding"') - 60 : PROTOTYPE.index('id="contract-funding"')
        ]
    )


def test_user_views_contain_no_dev_facing_text():
    """用户可见区域（评审工具条以外）不得出现开发态解释文字。"""

    class _Scanner(HTMLParser):
        """收集 #app 内、评审工具条以外的可见文本（跳过 script/style）。"""

        def __init__(self) -> None:
            super().__init__()
            self._skip = 0
            self._proto_depth = 0
            self.visible: list[str] = []

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            data = dict(attrs)
            if tag in ("script", "style"):
                self._skip += 1
                return
            if tag in ("br", "input", "img", "hr", "meta", "link"):
                return
            if data.get("id") == "proto-bar":
                self._proto_depth += 1

        def handle_endtag(self, tag: str) -> None:
            if tag in ("script", "style") and self._skip > 0:
                self._skip -= 1
            if tag == "div" and self._proto_depth > 0:
                self._proto_depth -= 1

        def handle_data(self, data: str) -> None:
            if self._proto_depth <= 0 and self._skip <= 0:
                self.visible.append(data)

    scanner = _Scanner()
    scanner.feed(PROTOTYPE)
    visible = "\n".join(scanner.visible)
    for token in DEV_TOKENS:
        assert token not in visible, f"用户可见区域出现开发态文字：{token}"


def test_collection_mode_switch_exists():
    """采集模式演示（owner 2026-09-17 裁决方案 A）：模式开关与 coll-mode 机制存在。"""
    assert 'id="mode-select"' in PROTOTYPE, "评审工具条缺运行模式切换"
    assert 'value="coll"' in PROTOTYPE, "模式切换缺采集态选项"
    assert "function applyMode(" in PROTOTYPE, "缺模式应用函数"
    assert 'location.hash.indexOf("coll")' in PROTOTYPE, "缺 #coll 直达入口"
    assert "body.coll-mode .free-only{display:none !important}" in PROTOTYPE


def test_static_forbidden_fields_marked_free_only():
    """design §6 自由模拟专用字段的静态标记（JS 渲染路径另由无头门实测）。"""
    # 盘口买卖深度比条
    assert 'id="depth-ratio" class="free-only"' in PROTOTYPE, "深度比条未标 free-only"
    assert 'id="depth-legend" class="free-only"' in PROTOTYPE, "深度比图例未标 free-only"
    # 两处持仓表的强平价列表头
    assert PROTOTYPE.count('<th class="free-only">强平价</th>') == 2, "持仓表强平价表头未标 free-only"
    # 既有约束防回归：标记价格/资金费率条
    assert 'class="mark-strip free-only"' in PROTOTYPE


def test_js_rendered_forbidden_fields_marked_free_only():
    """JS 渲染的白名单外字段必须在模板里带 free-only（V032-DOC-010/013）。"""
    # K 线图例三段 MA 读数（updateLegend 模板）
    assert 'class="free-only" style="color:#f0b90b">MA7 ' in PROTOTYPE
    assert 'class="free-only" style="color:#e543d0">MA25 ' in PROTOTYPE
    assert 'class="free-only" style="color:#7c8ce0">MA99 ' in PROTOTYPE
    # 两处持仓行模板的强平价单元格
    assert PROTOTYPE.count('<td class="free-only">') == 2, "持仓行强平价单元格未标 free-only"


def test_collection_freeze_guards_present():
    """采集态行为冻结的守卫必须存在（行为验证由无头门实测）。"""
    assert 'if(mode==="coll"){hintErr("采集模式下杠杆由实验协议冻结");return}' in PROTOTYPE
    assert "if(mode===\"coll\")return;" in PROTOTYPE, "setLeverage 缺采集态短路"
    assert '["dep-btn","reset-btn","dep-input"].forEach(id=>$(id).disabled=frozen)' in PROTOTYPE
