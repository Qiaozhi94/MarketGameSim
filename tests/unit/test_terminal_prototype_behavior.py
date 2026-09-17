"""0.3.2 交易终端原型的无头浏览器行为回归门。

背景（docs/reviews/CURRENT-doc.md 第 6 轮）：重建后的原型静态门禁全绿、运行时却大面积
破损——结构断言测不到 JS 行为。本文件用 chrome 无头加载原型、注入交互脚本、--dump-dom
取证，锁定以下回归：
- 价格步进 / 数量单位切换 / 杠杆弹窗开关 / 杠杆选择条可用（V032-DOC-014/017/021/022）
- 切换品种不崩溃且全面板联动（V032-DOC-015）
- 当前持仓表列对齐（V032-DOC-018）
- 等待行情空态可达且可恢复（V032-DOC-016）
- 评审模式入口可用（V032-DOC-019）
- MA99 在 1m 视图可渲染（V032-DOC-025）

无 chrome 二进制时显式跳过（GitHub ubuntu runner 预装 google-chrome，会真实执行）。
"""

from __future__ import annotations

import glob
import html
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

MILESTONE = (
    Path(__file__).resolve().parents[2] / "docs" / "features" / "0.3" / "0.3.2-web-trading-terminal"
)
PROTOTYPE = MILESTONE / "interaction-design.html"


def _find_chrome() -> str | None:
    env_bin = os.environ.get("CHROME_BIN")
    if env_bin and Path(env_bin).exists():
        return env_bin
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    patterns = (
        "~/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell",
        "~/.cache/ms-playwright/chromium-*/chrome-linux/chrome",
    )
    for pattern in patterns:
        matches = sorted(glob.glob(os.path.expanduser(pattern)))
        if matches:
            return matches[-1]
    return None


CHROME = _find_chrome()

pytestmark = pytest.mark.skipif(
    CHROME is None, reason="无可用 chrome/chromium 二进制（可用 CHROME_BIN 指定路径）"
)

HARNESS_TEMPLATE = """
<script>
(function(){
  const out = [];
  const errs = [];
  window.onerror = function (msg) { errs.push(String(msg)); return false; };
  function step(name, fn) {
    const e0 = errs.length;
    let r = "";
    try { r = String(fn()); } catch (ex) { r = "THROW:" + ex.message; }
    const fresh = errs.slice(e0);
    out.push(name + " => " + r + (fresh.length ? " | ERR:" + fresh.join(" ; ") : ""));
  }
__STEPS__
  setTimeout(function () {
__LATE_STEPS__
    const pre = document.createElement("pre");
    pre.id = "qa-out";
    pre.textContent = "QA-BEGIN\\n" + out.join("\\n") + "\\nQA-END";
    document.body.appendChild(pre);
  }, 1200);
})();
</script>
</body>
"""


def _run_prototype(steps: str, late_steps: str = "", url_hash: str = "") -> dict[str, str]:
    """加载原型副本、注入步骤脚本，返回 {步骤名: 结果}。结果含 ERR:/THROW: 即为失败证据。"""
    harness = HARNESS_TEMPLATE.replace("__STEPS__", steps).replace("__LATE_STEPS__", late_steps)
    page = PROTOTYPE.read_text(encoding="utf-8").replace("</body>", harness, 1)
    with tempfile.TemporaryDirectory(prefix="proto-qa-") as tmpdir:
        tmp = Path(tmpdir) / "proto.html"
        tmp.write_text(page, encoding="utf-8")
        proc = subprocess.run(
            [
                CHROME,
                "--headless",
                "--no-sandbox",
                "--disable-gpu",
                "--dump-dom",
                "--virtual-time-budget=8000",
                f"file://{tmp}#{url_hash}" if url_hash else f"file://{tmp}",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
    dom = proc.stdout
    anchor = dom.index('<pre id="qa-out">')
    block = html.unescape(dom[dom.index("QA-BEGIN", anchor) : dom.index("QA-END", anchor)])
    results: dict[str, str] = {}
    for line in block.splitlines():
        if " => " in line:
            key, value = line.split(" => ", 1)
            results[key] = value
    return results


def _assert_clean(results: dict[str, str]) -> None:
    for key, value in results.items():
        assert "ERR:" not in value and "THROW:" not in value, f"{key}: {value}"


def test_trade_panel_controls_work():
    results = _run_prototype(
        """
    step("price-plus", () => { const before = parseFloat(document.getElementById("px").value);
      document.getElementById("px-plus").click();
      return before + "->" + parseFloat(document.getElementById("px").value); });
    step("price-minus", () => { document.getElementById("px-minus").click();
      return document.getElementById("px").value; });
    step("unit-toggle-usdt", () => { document.getElementById("u-usdt").click();
      return document.getElementById("u-usdt").classList.contains("on") + "/"
        + document.getElementById("qty-label").textContent; });
    step("unit-toggle-back", () => { document.getElementById("u-base").click();
      return document.getElementById("qty-label").textContent; });
    step("lev-btns-populated", () => document.getElementById("lev-btns").children.length);
    step("lev-btns-highlight", () => document.querySelector("#lev-btns button.on").textContent);
    step("lev-btn-click", () => { document.querySelectorAll("#lev-btns button")[3].click();
      return account.leverage + "/" + document.querySelector("#lev-btns button.on").textContent; });
    step("lev-more-select", () => { const sel = document.getElementById("lev-more");
      sel.value = "10"; sel.dispatchEvent(new Event("change"));
      return account.leverage + "/" + sel.value; });
    """
    )
    _assert_clean(results)
    before, after = results["price-plus"].split("->")
    assert float(after) > float(before), results["price-plus"]
    assert results["unit-toggle-usdt"] == "true/金额"
    assert results["unit-toggle-back"] == "数量"
    assert results["lev-btns-populated"] == "5"
    assert results["lev-btns-highlight"] == "1×"
    assert results["lev-btn-click"] == "5/5×"
    assert results["lev-more-select"] == "10/10"


def test_instrument_switch_and_positions_table_alignment():
    results = _run_prototype(
        """
    step("switch-sym", () => { setInstrument("ETH/USDT");
      return document.getElementById("q-sym").textContent; });
    step("switch-btn", () => document.getElementById("btn-action").textContent);
    step("market-order", () => { document.querySelector('#type-tabs button[data-t="market"]')
      .click(); document.getElementById("btn-action").click();
      return "ok"; });
    step("positions-aligned", () => {
      const th = document.querySelectorAll("#pane-positions thead th").length;
      const tr = document.querySelector("#positions-body tr");
      const td = tr ? tr.querySelectorAll("td").length : 0;
      const lp = tr ? tr.querySelectorAll("td")[4].textContent : "";
      return "th=" + th + "/td=" + td + "/lp=" + lp;
    });
    """
    )
    _assert_clean(results)
    assert results["switch-sym"] == "ETH/USDT"
    assert "ETH" in results["switch-btn"], results["switch-btn"]
    assert results["positions-aligned"] == "th=7/td=7/lp=—", results["positions-aligned"]


def test_warming_empty_state_and_recovery():
    results = _run_prototype(
        """
    step("enter-warming", () => { setState("warming");
      return document.getElementById("btn-action").disabled + "/"
        + document.getElementById("state-select").value; });
    step("empty-quote", () => document.getElementById("mid-last").textContent);
    step("empty-book", () => document.getElementById("asks-host").children.length);
    step("empty-chart", () => document.getElementById("kline-empty").style.display);
    step("back-to-trading", () => { setState("trading");
      return "ok"; });
    """,
        late_steps="""
    step("recovered-quote", () => document.getElementById("mid-last").textContent);
    """,
    )
    _assert_clean(results)
    assert results["enter-warming"] == "true/warming"
    assert results["empty-quote"] == "—"
    assert results["empty-book"] == "0"
    assert results["empty-chart"] == "block"
    assert results["recovered-quote"] not in ("", "—"), results["recovered-quote"]


def test_assets_deposit_and_reset():
    results = _run_prototype(
        """
    step("open-position", () => { document.querySelector('#type-tabs button[data-t="market"]')
      .click(); document.getElementById("btn-action").click();
      return "ok"; });
    step("deposit-100", () => { switchView("assets");
      document.getElementById("dep-input").value = "100";
      document.getElementById("dep-btn").click();
      return account.wallet; });
    step("deposit-invalid", () => { document.getElementById("dep-input").value = "abc";
      document.getElementById("dep-btn").click();
      return document.getElementById("assets-msg").textContent; });
    step("reset-5000", () => { document.getElementById("dep-input").value = "5000";
      document.getElementById("reset-btn").click();
      return account.wallet
        + "/持仓=" + (document.getElementById("pos-body").textContent.includes("当前无持仓")); });
    step("orders-cleared", () => { switchView("trade");
      return document.getElementById("orders-count").textContent; });
    """
    )
    _assert_clean(results)
    assert results["deposit-100"] == "10100", results["deposit-100"]
    assert "大于 0" in results["deposit-invalid"], results["deposit-invalid"]
    assert results["reset-5000"] == "5000/持仓=true", results["reset-5000"]
    assert results["orders-cleared"] == "0"


def test_topnav_and_markets_row_switch_views():
    """顶部导航与行情行必须真实切换视图（重建曾丢失绑定：cursor:pointer 但无 onclick）。"""
    results = _run_prototype(
        """
    step("nav-markets", () => { document.getElementById("nav-markets").click();
      return !document.getElementById("view-markets").hidden + "/"
        + document.getElementById("terminal-wrap").style.display; });
    step("nav-assets", () => { document.querySelector('[data-view="assets"]').click();
      return !document.getElementById("view-assets").hidden; });
    step("nav-trade", () => { document.querySelector('[data-view="trade"]').click();
      return document.getElementById("terminal-wrap").style.display; });
    step("markets-row-click", () => { document.getElementById("nav-markets").click();
      document.querySelector('#mkt-body tr[data-sym="ETH/USDT"]').click();
      return document.getElementById("q-sym").textContent + "/"
        + document.getElementById("terminal-wrap").style.display; });
    """
    )
    _assert_clean(results)
    assert results["nav-markets"] == "true/none", results["nav-markets"]
    assert results["nav-assets"] == "true", results["nav-assets"]
    assert results["nav-trade"] == "block", results["nav-trade"]
    assert results["markets-row-click"] == "ETH/USDT/block", results["markets-row-click"]


def test_review_toolbar_reachable_and_ma99_renders():
    results = _run_prototype(
        """
    step("proto-bar-visible", () => getComputedStyle(document.getElementById("proto-bar")).display);
    step("ma99-legend", () => {
      const m = document.getElementById("ohlc-legend").textContent.match(/MA99\\s*[\\d.]+/);
      return m ? m[0] : "none";
    });
    """,
        url_hash="review",
    )
    _assert_clean(results)
    assert results["proto-bar-visible"] == "flex"
    assert results["ma99-legend"].startswith("MA99 "), results["ma99-legend"]


# design §6 自由模拟专用（采集态必须隐藏）字段关键词
FORBIDDEN_TOKENS = (
    "MA7",
    "MA25",
    "MA99",
    "标记价格",
    "资金费率",
    "资金费用",
    "24h",
    "强平价",
    "1D",
)


def test_collection_mode_hides_forbidden_fields():
    """采集态全视图可见文本负向门 + 自由态阳性对照（防止门禁空转）。"""
    results = _run_prototype(
        """
    function visibleText() {
      return document.getElementById("app").innerText.replace(/\\s+/g, " ");
    }
    step("free-scan-trade", () => { switchView("trade"); return visibleText(); });
    step("free-scan-assets", () => { switchView("assets"); return visibleText(); });
    step("to-coll", () => { applyMode("coll");
      return document.body.className; });
    step("coll-badge", () => document.getElementById("sim-badge").textContent);
    step("coll-scan-trade", () => { switchView("trade"); return visibleText(); });
    step("coll-scan-assets", () => { switchView("assets"); return visibleText(); });
    step("coll-markets-nav", () => {
      return getComputedStyle(document.getElementById("nav-markets")).display;
    });
    step("coll-mode-select", () => document.getElementById("mode-select").value);
    """
    )
    _assert_clean(results)
    # 阳性对照：自由态必须能看到禁区字段，否则扫描本身失效
    assert "标记价格" in results["free-scan-trade"], "自由态看不到标记价格条，阳性对照失效"
    assert "MA7" in results["free-scan-trade"], "自由态看不到 MA 图例，阳性对照失效"
    # 负向断言：采集态任何视图不得出现白名单外字段
    for key in ("coll-scan-trade", "coll-scan-assets"):
        for token in FORBIDDEN_TOKENS:
            assert token not in results[key], f"{key} 泄漏白名单外字段：{token}"
    assert results["coll-badge"] == "SIM · 采集"
    assert results["coll-markets-nav"] == "none"
    assert results["coll-mode-select"] == "coll"


def test_collection_mode_freezes_behavior():
    """采集态协议冻结：杠杆/入金/重置入口只读，切回自由态恢复。"""
    results = _run_prototype(
        """
    step("to-coll", () => { applyMode("coll"); return "ok"; });
    step("lev-btns-frozen-click", () => { document.querySelectorAll("#lev-btns button")[3].click();
      return document.querySelector("#lev-btns button").disabled + "/" + account.leverage
        + "/" + document.getElementById("lev-more").disabled; });
    step("lev-direct-frozen", () => { setLeverage(10);
      return account.leverage; });
    step("lev-btns-disabled", () => document.querySelector("#lev-btns button").disabled);
    step("dep-frozen", () => { document.getElementById("dep-input").value = "999";
      document.getElementById("dep-btn").click();
      return document.getElementById("dep-btn").disabled + "/" + account.wallet; });
    step("reset-frozen", () => document.getElementById("reset-btn").disabled);
    step("back-free-restored", () => { applyMode("free"); setLeverage(5);
      return account.leverage + "/" + document.getElementById("dep-btn").disabled; });
    """
    )
    _assert_clean(results)
    assert results["lev-btns-frozen-click"] == "true/1/true", results["lev-btns-frozen-click"]
    assert results["lev-direct-frozen"] == "1"
    assert results["lev-btns-disabled"] == "true"
    assert results["dep-frozen"] == "true/10000"
    assert results["reset-frozen"] == "true"
    assert results["back-free-restored"] == "5/false"
