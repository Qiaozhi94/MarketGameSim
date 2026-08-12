# ruff: noqa: E501  -- the HTML/JS template below is inherently long (single-file)
"""T201/T202 (FR-019): Single-file HTML frame-by-frame replay.

Produces a self-contained HTML page with the frame data inlined as JSON --
no ``fetch``, no CDN, no external fonts (E2 / PR-018).  The page renders a
price curve, orderbook depth, account equity/position, K-line candles,
liquidation annotations, a timestamp timeline, and drag-to-seek /
variable-speed / pause controls (AC-006).
"""

from __future__ import annotations

import html as html_lib
import json
from typing import Any

_LIQUIDATION_VERDICTS = frozenset({"PENDING_LIQUIDATION", "BREACHED"})


def _liquidation_frame_indices(frames: list, log_events: list[dict]) -> set[int]:
    """Frame indices whose transaction contains a liquidation MARGIN_CALL.

    Only ``verdict`` values of ``PENDING_LIQUIDATION`` or ``BREACHED`` count
    as liquidations -- a recovery ``MARGIN_CALL`` with ``verdict=OK`` is NOT
    a liquidation (F2e).  Indices are the DISPLAYED array positions
    (``enumerate(frames)``), not the original ``frame_index`` values, so the
    marks stay aligned after downsampling (round-2 review F-B).
    """
    by_txn: dict[int, int] = {}
    for display_idx, f in enumerate(frames):
        by_txn[f.transaction_seq] = display_idx
    out: set[int] = set()
    for e in log_events:
        if e.get("event_type") != "MARGIN_CALL":
            continue
        if e.get("verdict") not in _LIQUIDATION_VERDICTS:
            continue
        idx = by_txn.get(e.get("transaction_seq"))
        if idx is not None:
            out.add(idx)
    return out


def _escape_json_for_html(s: str) -> str:
    """Escape ``<``, ``>``, ``&`` so embedded JSON cannot break out of a
    ``<script>`` element (F8 security fix)."""
    return s.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def render_replay_html(
    log,
    frames: list,
    klines: list,
    *,
    initial_price_ticks: int | None = None,
    mult: int = 1000,
    downsample_desc: str | None = None,
) -> str:
    """Render a complete standalone HTML string embedding ``frames``/``klines``."""
    liquidation_frames = _liquidation_frame_indices(frames, log.events)

    data: dict[str, Any] = {
        "run_id": log.run_id,
        "frame_count": len(frames),
        "frames": [vars(f) for f in frames],
        "klines": [vars(k) for k in klines],
        "liquidation_frames": sorted(liquidation_frames),
        "downsample_desc": downsample_desc,
        "initial_price_ticks": initial_price_ticks,
        "mult": mult,
    }
    data_json = json.dumps(data, sort_keys=True, separators=(",", ":"))
    data_json = _escape_json_for_html(data_json)
    run_id_esc = html_lib.escape(log.run_id)
    downsample_html = (
        f'<p id="downsample-note">Downsampling: {html_lib.escape(downsample_desc)}</p>'
        if downsample_desc
        else ""
    )

    return _TEMPLATE.format(run_id=run_id_esc, downsample=downsample_html, data=data_json)


_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Replay - {run_id}</title>
<style>
body{{font-family:system-ui,sans-serif;margin:0;padding:16px;background:#111;color:#ddd}}
h1{{font-size:18px}} #controls{{display:flex;gap:10px;align-items:center;margin:12px 0}}
canvas{{background:#0a0a0a;border:1px solid #333;width:100%;max-width:1100px}}
#timeline{{width:100%;max-width:1100px}} .panel{{margin:8px 0}}
</style>
</head>
<body>
<h1>Replay - {run_id}</h1>
{downsample}
<div id="controls">
  <button id="btn-pause">Pause</button>
  <label>Speed <input id="speed" type="range" min="0.1" max="5" step="0.1" value="1"></label>
  <span id="frame-info">frame 0</span>
</div>
<div class="panel" id="price-panel"><strong>Price curve</strong><canvas id="price-canvas" width="1100" height="220"></canvas></div>
<div class="panel" id="kline-panel"><strong>K-line</strong><canvas id="kline-canvas" width="1100" height="200"></canvas></div>
<div class="panel" id="book-panel"><strong>Orderbook depth</strong><canvas id="book-canvas" width="1100" height="160"></canvas></div>
<div class="panel" id="account-panel"><strong>Account equity / position</strong><canvas id="account-canvas" width="1100" height="160"></canvas></div>
<div class="panel" id="liquidation-panel"><strong>Liquidations</strong><span id="liq-marks"></span></div>
<input id="timeline" type="range" min="0" max="0" value="0">
<script id="replay-data" type="application/json">{data}</script>
<script>
const DATA = JSON.parse(document.getElementById('replay-data').textContent);
let frame = 0;
let paused = false;
let speed = 1;
let stepTimer = null;
const timeline = document.getElementById('timeline');
// Slider positions are UNIQUE per frame (0..frame_count-1) so every frame is
// reachable even when several frames share one logical timestamp; the frame's
// timestamp is shown in the frame-info line and rendered next to the slider.
timeline.min = 0;
timeline.max = Math.max(0, DATA.frame_count - 1);
function arrayMin(arr) {{ let m = arr[0]; for (let i = 1; i < arr.length; i++) {{ if (arr[i] < m) m = arr[i]; }} return m; }}
function arrayMax(arr) {{ let m = arr[0]; for (let i = 1; i < arr.length; i++) {{ if (arr[i] > m) m = arr[i]; }} return m; }}
function draw() {{
  const f = DATA.frames[frame];
  document.getElementById('frame-info').textContent = 'frame ' + frame + ' txn ' + f.transaction_seq + ' ts ' + f.timestamp + ' last ' + f.last_ticks;
  drawPrice(f); drawKlines(); drawBook(f); drawAccount(f);
  const liqSet = DATA.liquidation_frames;
  document.getElementById('liq-marks').textContent = liqSet.includes(frame) ? 'LIQUIDATION' : '';
  timeline.value = frame;
  timeline.setAttribute('aria-valuetext', 'ts ' + f.timestamp);
}}
function drawPrice(f) {{
  const c = document.getElementById('price-canvas'); const g = c.getContext('2d'); g.clearRect(0,0,c.width,c.height);
  const prices = DATA.frames.slice(0, frame+1).map(x => x.last_ticks).filter(p => p != null);
  if (prices.length < 2) return;
  const min = arrayMin(prices), max = arrayMax(prices), span = (max-min) || 1;
  g.strokeStyle = '#4fc3f7'; g.beginPath();
  prices.forEach((p, i) => {{ const x = (i/(prices.length-1))*c.width; const y = c.height - ((p-min)/span)*(c.height-10); i ? g.lineTo(x,y) : g.moveTo(x,y); }});
  g.stroke();
}}
function drawKlines() {{
  const c = document.getElementById('kline-canvas'); const g = c.getContext('2d'); g.clearRect(0,0,c.width,c.height);
  const klines = DATA.klines || [];
  if (klines.length === 0) return;
  const allHighs = klines.map(k => k.high), allLows = klines.map(k => k.low);
  const maxP = arrayMax(allHighs), minP = arrayMin(allLows), span = (maxP - minP) || 1;
  const candleW = Math.max(4, c.width / klines.length);
  klines.forEach((k, i) => {{
    const cx = i * candleW + candleW / 2;
    const yHigh = c.height - ((k.high - minP) / span) * (c.height - 10);
    const yLow = c.height - ((k.low - minP) / span) * (c.height - 10);
    const yOpen = c.height - ((k.open - minP) / span) * (c.height - 10);
    const yClose = c.height - ((k.close - minP) / span) * (c.height - 10);
    const isUp = k.close >= k.open;
    g.strokeStyle = isUp ? '#26a69a' : '#ef5350';
    g.fillStyle = isUp ? '#26a69a' : '#ef5350';
    g.beginPath(); g.moveTo(cx, yHigh); g.lineTo(cx, yLow); g.stroke();
    const bodyTop = Math.min(yOpen, yClose);
    const bodyH = Math.max(1, Math.abs(yClose - yOpen));
    g.fillRect(cx - candleW / 3, bodyTop, candleW * 2 / 3, bodyH);
  }});
}}
function drawBook(f) {{
  const c = document.getElementById('book-canvas'); const g = c.getContext('2d'); g.clearRect(0,0,c.width,c.height);
  let maxq = 1; const lv = (f.book.bids||[]).concat(f.book.asks||[]); lv.forEach(l => {{ if (l.quantity_units > maxq) maxq = l.quantity_units; }});
  const draw = (levels, color, base) => levels.forEach(l => {{
    const x = (l.price_ticks % 1000) / 1000 * c.width; const h = (l.quantity_units/maxq)*(c.height-10);
    g.fillStyle = color; g.fillRect(x, base - h, 6, h);
  }});
  draw(f.book.asks || [], '#ef5350', c.height);
  draw(f.book.bids || [], '#26a69a', c.height);
}}
function drawAccount(f) {{
  const c = document.getElementById('account-canvas'); const g = c.getContext('2d'); g.clearRect(0,0,c.width,c.height);
  const aids = Object.keys(DATA.frames[0].accounts || {{}});
  aids.forEach((aid, i) => {{
    const posSeries = DATA.frames.slice(0, frame+1).map(x => (x.accounts[aid]||{{}}).position_units || 0);
    const eqSeries = DATA.frames.slice(0, frame+1).map(x => {{
      const a = x.accounts[aid] || {{}};
      const lt = (x.last_ticks != null) ? x.last_ticks : (DATA.initial_price_ticks || 0);
      const m = DATA.mult || 1000;
      return (a.wallet_units || 0) + (a.position_units || 0) * lt * m - (a.entry_notional_units || 0);
    }});
    const posColor = ['#ffd54f','#81c784','#ba68c8','#ff8a65'][i%4];
    const eqColor = ['#4fc3f7','#ce93d8','#a5d6a7','#ffab91'][i%4];
    g.strokeStyle = posColor; g.beginPath();
    posSeries.forEach((v, j) => {{ const x = (j/Math.max(1,posSeries.length-1))*c.width; const y = c.height/2 - v/2000; j ? g.lineTo(x,y) : g.moveTo(x,y); }});
    g.stroke();
    g.strokeStyle = eqColor; g.beginPath();
    eqSeries.forEach((v, j) => {{ const x = (j/Math.max(1,eqSeries.length-1))*c.width; const y = c.height - 10 - v/100000; j ? g.lineTo(x,y) : g.moveTo(x,y); }});
    g.stroke();
  }});
}}
function step() {{
  if (paused) return;
  if (frame < DATA.frame_count - 1) {{ frame++; draw(); }}
}}
function scheduleStep() {{
  if (stepTimer !== null) clearTimeout(stepTimer);
  stepTimer = setTimeout(() => {{ step(); scheduleStep(); }}, 500 / speed);
}}
scheduleStep();
document.getElementById('btn-pause').onclick = () => {{ paused = !paused; document.getElementById('btn-pause').textContent = paused ? 'Play' : 'Pause'; }};
document.getElementById('speed').oninput = (e) => {{ speed = parseFloat(e.target.value); scheduleStep(); }};
document.getElementById('timeline').oninput = (e) => {{ frame = parseInt(e.target.value, 10); draw(); }};
draw();
</script>
</body>
</html>
"""
