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
    step("modal-open", () => { document.getElementById("lev-chip").click();
      return document.getElementById("modal-root").classList.contains("show"); });
    step("modal-set-leverage", () => { setLeverage(5);
      return account.leverage; });
    step("modal-close", () => { document.getElementById("lev-close").click();
      return document.getElementById("modal-root").classList.contains("show"); });
    step("modal-backdrop-close", () => { document.getElementById("lev-chip").click();
      const root = document.getElementById("modal-root");
      root.click();
      return root.classList.contains("show"); });
    """
    )
    _assert_clean(results)
    before, after = results["price-plus"].split("->")
    assert float(after) > float(before), results["price-plus"]
    assert results["unit-toggle-usdt"] == "true/金额"
    assert results["unit-toggle-back"] == "数量"
    assert results["lev-btns-populated"] == "5"
    assert results["lev-btns-highlight"] == "1×"
    assert results["modal-open"] == "true"
    assert results["modal-set-leverage"] == "5"
    assert results["modal-close"] == "false"
    assert results["modal-backdrop-close"] == "false"


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
