"""V032-DOC-001/006/007 回归门：采集模式只显示冻结观察白名单字段。

- 白名单外字段（含新增的行情/研究视图、合约资金费用、资产配置卡）必须带 `free-only`；
- 结构性负向门：采集可见区域不得出现禁用字段文案，使**新增违规默认被拒**而非默认放行
  （V032-DOC-007 的教训：只锁定已知 id 清单对新增字段结构性失效）。

把任一处回退成旧形态、或新增一个未隐藏的白名单外字段时，本测试必须变红。
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

MILESTONE = (
    Path(__file__).resolve().parents[2] / "docs" / "features" / "0.3" / "0.3.2-web-trading-terminal"
)
PROTOTYPE = (MILESTONE / "interaction-design.html").read_text(encoding="utf-8")

# 采集模式白名单外、必须在采集态隐藏的字段/区块 id（spec §5 / design §6 第三类）。
NON_WHITELIST_IDS = (
    "tick-chg",
    "tick-hi",
    "tick-lo",
    "tick-vol",
    "tick-mark",
    "tick-fund",
    "depth-ratio",
    "depth-legend",
    "view-markets",
    "view-research",
    "nav-markets",
    "nav-research",
    "contract-funding",
    "assets-capital",
    "assets-leverage",
)

# 采集可见区域禁止出现的白名单外字段文案（结构性负向门，默认拒绝新增字段）。
FORBIDDEN_TOKENS = ("24h", "资金费率", "资金费用", "标记价格", "预估强平价")

_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class _ElementAttrs(HTMLParser):
    """收集静态 HTML 各 id 自身 class 及其祖先 class，用于白名单隐藏覆盖断言。"""

    def __init__(self) -> None:
        super().__init__()
        self._stack: list[list[str]] = []
        self.by_id: dict[str, list[str]] = {}

    def _record(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = dict(attrs)
        classes = (data.get("class") or "").split()
        inherited = [name for frame in self._stack for name in frame]
        element_id = data.get("id")
        if element_id:
            self.by_id[element_id] = inherited + classes
        if tag not in _VOID_TAGS:
            self._stack.append(classes)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._record(tag, attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = dict(attrs)
        classes = (data.get("class") or "").split()
        inherited = [name for frame in self._stack for name in frame]
        element_id = data.get("id")
        if element_id:
            self.by_id[element_id] = inherited + classes

    def handle_endtag(self, tag: str) -> None:
        if tag not in _VOID_TAGS and self._stack:
            self._stack.pop()


class _AppTextScanner(HTMLParser):
    """把 `#app` 产品区的文本按「采集可见 / free-only 隐藏」分类（跳过 script/style）。"""

    def __init__(self) -> None:
        super().__init__()
        self._stack: list[tuple[str, list[str], bool]] = []
        self._app_depth = 0
        self._skip = 0
        self.visible_texts: list[str] = []
        self.free_only_texts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self._skip += 1
            return
        if tag in _VOID_TAGS:
            return
        data = dict(attrs)
        classes = (data.get("class") or "").split()
        is_app = data.get("id") == "app"
        self._stack.append((tag, classes, is_app))
        if is_app:
            self._app_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            if self._skip > 0:
                self._skip -= 1
            return
        if self._stack and self._stack[-1][0] == tag:
            _, _, is_app = self._stack.pop()
            if is_app:
                self._app_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._app_depth <= 0 or self._skip > 0:
            return
        in_free_only = any("free-only" in classes for _, classes, _ in self._stack)
        target = self.free_only_texts if in_free_only else self.visible_texts
        target.append(data)


def test_non_whitelist_fields_are_hidden_in_collection_mode():
    assert "body.coll-mode .free-only{display:none !important}" in PROTOTYPE
    parser = _ElementAttrs()
    parser.feed(PROTOTYPE)
    for element_id in NON_WHITELIST_IDS:
        assert element_id in parser.by_id, f"原型缺少 #{element_id}"
        assert "free-only" in parser.by_id[element_id], f"#{element_id} 未标 free-only"
    # MA 图例、1D 周期页签与预估强平价账户行属于白名单外，必须同样归入采集态隐藏。
    assert 'class="free-only" style="margin-left:auto' in PROTOTYPE
    assert 'if(label==="1D")b.classList.add("free-only")' in PROTOTYPE
    assert '["预估强平价",`<span class="num">${fmtP(liqEstTicks())}</span>`,true]' in PROTOTYPE
    assert 'r[2]?" free-only":""' in PROTOTYPE


def test_prototype_separates_mode_from_stage_with_tradable_collection_states():
    assert 'const COLLECTION_MODE="collection";' in PROTOTYPE
    # 可交易采集态：training / formal（不再只有 exp-* 覆盖页）
    assert '["training","训练中 · 采集模式（可交易）",COLLECTION_MODE,"training"]' in PROTOTYPE
    assert '["formal","正式采集 · 采集模式（可交易）",COLLECTION_MODE,"formal"]' in PROTOTYPE
    assert "function applyMode(mode,stage){" in PROTOTYPE
    assert "const coll=mode===COLLECTION_MODE;" in PROTOTYPE
    assert "document.body.dataset.mode=mode;document.body.dataset.stage=stage;" in PROTOTYPE
    # 1D 与白名单外视图在进入采集态时必须自动退出
    assert 'if(coll&&tfKey==="1D"){tfKey="1m";renderTfTabs();}' in PROTOTYPE
    assert 'if(coll&&(view==="markets"||view==="research"))switchView("trade");' in PROTOTYPE
    assert 'startsWith("exp-")' not in PROTOTYPE


def test_collection_visible_text_has_no_forbidden_market_fields():
    scanner = _AppTextScanner()
    scanner.feed(PROTOTYPE)
    for token in FORBIDDEN_TOKENS:
        # 非空转：该字段必须真的出现在某个 free-only 区域，否则门禁看不到它
        assert any(token in text for text in scanner.free_only_texts), (
            f"门禁空转：{token} 未出现在任何 free-only 区域"
        )
        offenders = [text.strip() for text in scanner.visible_texts if token in text]
        assert not offenders, f"采集可见区域出现白名单外字段 {token}：{offenders[:2]}"
