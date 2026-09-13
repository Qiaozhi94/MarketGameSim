"""V032-DOC-001 回归门：采集模式只显示冻结观察白名单字段。

原型把 mode（free/collection）与 stage 分离，并提供可交易的 training/formal 采集态；
白名单外字段必须带 `free-only` 且在采集态隐藏。把任一处回退成旧形态时本测试必须变红。
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

MILESTONE = (
    Path(__file__).resolve().parents[2] / "docs" / "features" / "0.3" / "0.3.2-web-trading-terminal"
)
PROTOTYPE = (MILESTONE / "interaction-design.html").read_text(encoding="utf-8")

# 采集模式白名单外、必须在采集态隐藏的字段 id（spec §5 / design §6 第三类）。
NON_WHITELIST_IDS = (
    "tick-chg",
    "tick-hi",
    "tick-lo",
    "tick-vol",
    "tick-mark",
    "tick-fund",
    "depth-ratio",
    "depth-legend",
)

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
    # 1D 在进入采集态时必须自动退出；mode 不得再由 key 前缀推断
    assert 'if(coll&&tfKey==="1D"){tfKey="1m";renderTfTabs();}' in PROTOTYPE
    assert 'startsWith("exp-")' not in PROTOTYPE
