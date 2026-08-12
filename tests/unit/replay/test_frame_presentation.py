"""T202 (AC-006): frame presentation (single-file HTML) tests."""

from __future__ import annotations

from types import SimpleNamespace

from market_game_sim.replay.frames import _build_frames
from market_game_sim.replay.html import _liquidation_frame_indices, render_replay_html

MULT = 1000


def _log(events, run_id="run-1"):
    return SimpleNamespace(events=events, run_id=run_id)


def _bootstrap_events():
    acct = {
        "event_type": "SNAPSHOT",
        "timestamp": 0,
        "transaction_seq": 1,
        "record_index": 0,
        "snapshot_type": "ACCOUNT",
        "payload": {
            "accounts": [
                {
                    "agent_id": "A",
                    "wallet_units": 10000,
                    "position_units": 0,
                    "entry_notional_units": 0,
                    "reserved_units": 0,
                    "realized_pnl_units": 0,
                    "state": "ACTIVE",
                    "margin_ratio_bp": None,
                    "liquidation_generation": 0,
                    "chain_id": None,
                    "chain_depth": None,
                }
            ],
            "exchange": {"fee_cash_units": 0, "risk_pnl_units": 0},
        },
    }
    book = {
        "event_type": "SNAPSHOT",
        "timestamp": 0,
        "transaction_seq": 2,
        "record_index": 0,
        "snapshot_type": "BOOK",
        "payload": {"bids": [], "asks": [], "last_ticks": None},
    }
    return [acct, book]


def _events_with_liquidation():
    events = _bootstrap_events()
    events.append(
        {
            "event_type": "MARGIN_CALL",
            "timestamp": 10,
            "transaction_seq": 3,
            "record_index": 0,
            "agent_id": "A",
            "verdict": "PENDING_LIQUIDATION",
            "postings": [],
        }
    )
    return events


def _events_with_recovery_margin_call():
    """A MARGIN_CALL with verdict=OK (recovery) - should NOT be a liquidation."""
    events = _bootstrap_events()
    events.append(
        {
            "event_type": "MARGIN_CALL",
            "timestamp": 10,
            "transaction_seq": 3,
            "record_index": 0,
            "agent_id": "A",
            "verdict": "OK",
            "postings": [],
        }
    )
    return events


def _events_with_breached_margin_call():
    events = _bootstrap_events()
    events.append(
        {
            "event_type": "MARGIN_CALL",
            "timestamp": 10,
            "transaction_seq": 3,
            "record_index": 0,
            "agent_id": "A",
            "verdict": "BREACHED",
            "postings": [],
        }
    )
    return events


def test_html_contains_required_presentation_markers():
    events = _bootstrap_events()
    log = _log(events)
    frames = _build_frames(events, MULT)
    html = render_replay_html(log, frames, [], initial_price_ticks=10000)
    for marker in (
        "price-canvas",
        "kline-canvas",
        "book-canvas",
        "account-canvas",
        "liquidation-panel",
        "btn-pause",
        "speed",
        "timeline",
    ):
        assert marker in html


def test_html_is_single_file_no_external_refs():
    events = _bootstrap_events()
    log = _log(events)
    frames = _build_frames(events, MULT)
    html = render_replay_html(log, frames, [], initial_price_ticks=10000)
    assert html.count("<html") == 1
    assert "fetch(" not in html
    assert "http://" not in html
    assert "https://" not in html
    assert "cdn" not in html.lower()
    assert "replay-data" in html


def test_liquidation_frame_marked_in_embedded_data():
    events = _events_with_liquidation()
    log = _log(events)
    frames = _build_frames(events, MULT)
    html = render_replay_html(log, frames, [], initial_price_ticks=10000)
    assert '"liquidation_frames":[1]' in html


def test_recovery_margin_call_not_marked_as_liquidation():
    """F2e: MARGIN_CALL with verdict=OK is NOT a liquidation."""
    events = _events_with_recovery_margin_call()
    log = _log(events)
    frames = _build_frames(events, MULT)
    liq = _liquidation_frame_indices(frames, log.events)
    assert 1 not in liq
    html = render_replay_html(log, frames, [], initial_price_ticks=10000)
    assert '"liquidation_frames":[]' in html


def test_breached_margin_call_marked_as_liquidation():
    """F2e: MARGIN_CALL with verdict=BREACHED IS a liquidation."""
    events = _events_with_breached_margin_call()
    log = _log(events)
    frames = _build_frames(events, MULT)
    liq = _liquidation_frame_indices(frames, log.events)
    assert 1 in liq


def test_pending_liquidation_marked_as_liquidation():
    """F2e: MARGIN_CALL with verdict=PENDING_LIQUIDATION IS a liquidation."""
    events = _events_with_liquidation()
    log = _log(events)
    frames = _build_frames(events, MULT)
    liq = _liquidation_frame_indices(frames, log.events)
    assert 1 in liq


def test_downsample_rule_visible_in_html():
    events = _bootstrap_events()
    log = _log(events)
    frames = _build_frames(events, MULT)
    html = render_replay_html(
        log, frames, [], initial_price_ticks=10000, downsample_desc="keep every 5-th frame"
    )
    assert "keep every 5-th frame" in html
    assert "downsample-note" in html


# --- F2 regression tests ---


def test_js_uses_includes_not_in_operator():
    """F2a: the JS must use .includes() for liquidation frame membership, not `in`."""
    events = _bootstrap_events()
    log = _log(events)
    frames = _build_frames(events, MULT)
    html = render_replay_html(log, frames, [], initial_price_ticks=10000)
    assert "frame in liq" not in html
    assert ".includes(frame)" in html


def test_js_uses_settimeout_recursion_for_speed():
    """F2b: speed changes must take effect -- use self-rescheduling setTimeout."""
    events = _bootstrap_events()
    log = _log(events)
    frames = _build_frames(events, MULT)
    html = render_replay_html(log, frames, [], initial_price_ticks=10000)
    assert "setInterval(step" not in html
    assert "scheduleStep" in html
    assert "setTimeout" in html


def test_js_draws_both_equity_and_position():
    """F2c: drawAccount must draw both an equity series and a position series."""
    events = _bootstrap_events()
    log = _log(events)
    frames = _build_frames(events, MULT)
    html = render_replay_html(log, frames, [], initial_price_ticks=10000)
    assert "eqSeries" in html
    assert "posSeries" in html


def test_js_ask_bars_use_bottom_base():
    """F2d: asks must be drawn from the bottom up (base = c.height), matching bids."""
    events = _bootstrap_events()
    log = _log(events)
    frames = _build_frames(events, MULT)
    html = render_replay_html(log, frames, [], initial_price_ticks=10000)
    assert "draw(f.book.asks || [], '#ef5350', c.height)" in html


# --- F3 regression tests ---


def test_html_contains_kline_canvas_and_draw_function():
    """F3: HTML must have a kline-canvas and a drawKlines function."""
    events = _bootstrap_events()
    log = _log(events)
    frames = _build_frames(events, MULT)
    html = render_replay_html(log, frames, [], initial_price_ticks=10000)
    assert 'id="kline-canvas"' in html
    assert "function drawKlines" in html


# --- F8 regression tests ---


def test_script_injection_escaped_in_embedded_data():
    """F8: a run_id containing </script> must be escaped in the embedded JSON."""
    evil = "</script><script>alert(1)</script>"
    events = _bootstrap_events()
    log = _log(events, run_id=evil)
    frames = _build_frames(events, MULT)
    html = render_replay_html(log, frames, [], initial_price_ticks=10000)
    assert "\\u003c/script" in html
    data_start = html.index('type="application/json">') + len('type="application/json">')
    data_end = html.index("</script>", data_start)
    embedded = html[data_start:data_end]
    assert "</script>" not in embedded


# --- F-B / F-D regression tests ---


def test_embedded_data_carries_mult():
    """F-B: the rendered HTML must embed the real mult so the JS equity
    formula can compute notional = position * mark * mult."""
    events = _bootstrap_events()
    log = _log(events)
    frames = _build_frames(events, MULT)
    html = render_replay_html(log, frames, [], initial_price_ticks=10000, mult=750)
    assert '"mult":750' in html
    assert "* m" in html and "DATA.mult" in html


def test_equity_formula_uses_mult_and_initial_price_fallback():
    """F-B: the JS equity formula must multiply by mult and fall back to
    initial_price_ticks (not 0) before the first trade."""
    events = _bootstrap_events()
    log = _log(events)
    frames = _build_frames(events, MULT)
    html = render_replay_html(log, frames, [], initial_price_ticks=12345, mult=750)
    assert "(a.position_units || 0) * lt * m" in html
    assert "DATA.initial_price_ticks" in html
    assert "(x.last_ticks || 0)" not in html


def test_frame_info_displays_logical_timestamp():
    """F-D: the frame-info line must show the frame's logical timestamp."""
    events = _bootstrap_events()
    log = _log(events)
    frames = _build_frames(events, MULT)
    html = render_replay_html(log, frames, [], initial_price_ticks=10000)
    assert "' ts ' + f.timestamp" in html


def test_timeline_is_timestamp_based():
    """F-D: the timeline positions are unique per frame (every frame reachable
    even with duplicate timestamps) while the logical timestamp is displayed
    in the frame-info and as the slider's valuetext."""
    events = _bootstrap_events()
    log = _log(events)
    frames = _build_frames(events, MULT)
    html = render_replay_html(log, frames, [], initial_price_ticks=10000)
    assert "timeline.min = 0" in html
    assert "timeline.max = Math.max(0, DATA.frame_count - 1)" in html
    assert "timeline.value = frame" in html
    assert "aria-valuetext" in html
    assert "timeline').oninput" in html


def test_timeline_reaches_every_frame_with_duplicate_timestamps():
    """F-H3 (round-5): frames sharing one logical timestamp must ALL be
    reachable -- the slider is index-positioned (0..frame_count-1), so the
    seek maps value -> frame index directly, never collapsing duplicates."""
    from market_game_sim.replay.frames import _build_frames as build

    events = _bootstrap_events()
    for txn, ts in [(3, 0), (4, 0), (5, 10)]:  # two frames at ts=0
        events.append(
            {
                "event_type": "MARKET_DATA_PUBLISH",
                "timestamp": ts,
                "transaction_seq": txn,
                "record_index": 0,
            }
        )
    log = _log(events)
    frames = build(events, MULT)
    assert [f.timestamp for f in frames] == [0, 0, 0, 10]
    html = render_replay_html(log, frames, [], initial_price_ticks=10000)
    # Slider max is frame_count-1 (unique positions), and seek is a direct
    # index assignment -- no timestamp->frame mapping that could skip frames.
    assert "timeline.max = Math.max(0, DATA.frame_count - 1)" in html
    assert "frame = parseInt(e.target.value, 10)" in html


def test_liquidation_frames_aligned_after_downsample():
    """F-B: after downsampling, liquidation marks must use DISPLAYED indices
    (array positions), not original frame_index values."""
    from market_game_sim.replay.downsample import DownsampleRule
    from market_game_sim.replay.frames import _build_frames as build

    events = _bootstrap_events()
    for txn in range(3, 15):
        events.append(
            {
                "event_type": "MARGIN_CALL",
                "timestamp": txn,
                "transaction_seq": txn,
                "record_index": 0,
                "agent_id": "A",
                "verdict": "BREACHED",
                "postings": [],
            }
        )
    log = _log(events)
    rule = DownsampleRule(keep_every=5)
    full = build(events, MULT)
    sampled = build(events, MULT, downsample=rule)
    assert len(sampled) < len(full)
    liq = _liquidation_frame_indices(sampled, log.events)
    assert liq, "downsampled run must still mark liquidations"
    for idx in liq:
        assert idx < len(sampled), f"liquidation index {idx} out of displayed range"
    html = render_replay_html(log, sampled, [], initial_price_ticks=10000)
    assert '"liquidation_frames":' in html
