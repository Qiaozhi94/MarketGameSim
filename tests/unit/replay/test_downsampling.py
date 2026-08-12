"""T204 (spec §3.3): downsampling tests."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from market_game_sim.replay.downsample import DownsampleRule, apply_downsample
from market_game_sim.replay.frames import _build_frames

MULT = 1000


def _ev(txn: int, kind: str) -> dict:
    return {
        "event_type": "SNAPSHOT",
        "timestamp": 0,
        "transaction_seq": txn,
        "record_index": 0,
        "snapshot_type": kind,
        "payload": (
            {"accounts": [], "exchange": {"fee_cash_units": 0, "risk_pnl_units": 0}}
            if kind == "ACCOUNT"
            else {"bids": [], "asks": [], "last_ticks": None}
        ),
    }


def _frames():
    events = [_ev(1, "ACCOUNT"), _ev(2, "BOOK")]
    for txn in range(3, 12):
        events.append(
            {
                "event_type": "MARKET_DATA_PUBLISH",
                "timestamp": txn,
                "transaction_seq": txn,
                "record_index": 0,
            }
        )
    return _build_frames(events, MULT)


def test_downsample_reduces_frame_count():
    frames = _frames()
    assert len(frames) == 10
    out = apply_downsample(frames, DownsampleRule(keep_every=5))
    assert len(out) == 2
    assert [f.frame_index for f in out] == [0, 5]


def test_downsample_offset_shifts_selection():
    frames = _frames()
    out = apply_downsample(frames, DownsampleRule(keep_every=5, offset=2))
    assert [f.frame_index for f in out] == [2, 7]


def test_rule_describes_ratio_visibly():
    assert "5" in DownsampleRule(keep_every=5).describe()
    assert "2" in DownsampleRule(keep_every=5, offset=2).describe()


# --- F5 regression tests ---


def test_downsample_rule_keep_every_zero_raises():
    """F5: keep_every=0 must raise ValueError (not ZeroDivisionError later)."""
    with pytest.raises(ValueError, match="keep_every"):
        DownsampleRule(keep_every=0)


def test_downsample_rule_keep_every_negative_raises():
    """F5: keep_every=-1 must raise ValueError."""
    with pytest.raises(ValueError, match="keep_every"):
        DownsampleRule(keep_every=-1)


def test_downsample_rule_offset_negative_raises():
    """F5: offset=-1 must raise ValueError."""
    with pytest.raises(ValueError, match="offset"):
        DownsampleRule(keep_every=5, offset=-1)


def test_downsample_rule_valid_construction():
    """F5 accepted side: valid rules still construct without error."""
    r = DownsampleRule(keep_every=1)
    assert r.keep_every == 1
    r2 = DownsampleRule(keep_every=10, offset=3)
    assert r2.keep_every == 10
    assert r2.offset == 3


def test_cli_downsample_zero_exits_nonzero():
    """F5: CLI --downsample 0 must exit non-zero with an error message."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "market_game_sim.replay.generate",
            "--log",
            "nonexistent.jsonl",
            "--out",
            "out.html",
            "--downsample",
            "0",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "downsample" in result.stderr.lower()


# --- F-E regression tests: downsampling during reconstruction ---


def test_inline_downsample_matches_post_hoc_apply():
    """F-E: filtering DURING reconstruction must equal apply_downsample on the
    full list (same frame_index modulo predicate), for rules with/without
    offset -- proving the sampled product is identical, just not materialized."""
    for rule in (DownsampleRule(keep_every=5), DownsampleRule(keep_every=3, offset=1)):
        inline = _build_frames(
            [_ev(1, "ACCOUNT"), _ev(2, "BOOK")]
            + [
                {"event_type": "MARKET_DATA_PUBLISH", "timestamp": txn, "transaction_seq": txn}
                for txn in range(3, 12)
            ],
            MULT,
            downsample=rule,
        )
        post_hoc = apply_downsample(_frames(), rule)
        assert [f.frame_index for f in inline] == [f.frame_index for f in post_hoc]
        assert [f.transaction_seq for f in inline] == [f.transaction_seq for f in post_hoc]


# --- F-E2 regression tests: zero-matching downsample must be rejected ---


def _write_minimal_v3_log(tmp_path, extra_events=()) -> str:
    """A minimal v3 log with bootstrap snapshots (txn 1/2) plus events."""
    from market_game_sim.replay.reader import SUPPORTED_SCHEMA_VERSION

    header = {
        "record_kind": "RUN_HEADER",
        "schema_version": SUPPORTED_SCHEMA_VERSION,
        "run_id": "run-1",
        "tick_size": "0.01",
        "min_quantity": "0.001",
        "cash_unit": "0.01",
        "mult": 1000,
        "fee_bps_cap": 0,
        "initial_price_ticks": 10000,
        "agent_initial_bp": {},
    }
    acct = {
        "record_kind": "EVENT",
        "schema_version": SUPPORTED_SCHEMA_VERSION,
        "event_id": "e1_0",
        "run_id": "run-1",
        "timestamp": 0,
        "transaction_seq": 1,
        "record_index": 0,
        "priority_class": 5,
        "event_type": "SNAPSHOT",
        "snapshot_type": "ACCOUNT",
        "payload": {"accounts": [], "exchange": {}},
    }
    book = {
        "record_kind": "EVENT",
        "schema_version": SUPPORTED_SCHEMA_VERSION,
        "event_id": "e2_0",
        "run_id": "run-1",
        "timestamp": 0,
        "transaction_seq": 2,
        "record_index": 0,
        "priority_class": 5,
        "event_type": "SNAPSHOT",
        "snapshot_type": "BOOK",
        "payload": {"bids": [], "asks": [], "last_ticks": None},
    }
    events = [acct, book, *extra_events]
    trailer = {
        "record_kind": "RUN_TRAILER",
        "terminated": "COMPLETED",
        "abort_code": None,
        "abort_detail": None,
        "last_committed_transaction_seq": max(e["transaction_seq"] for e in events),
        "record_count": 2 + len(events),
    }
    path = tmp_path / "log.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for rec in [header, *events, trailer]:
            f.write(json.dumps(rec) + "\n")
    return str(path)


def test_build_replay_rejects_zero_matching_rule(tmp_path):
    """F-E2: a valid rule that matches zero frames (e.g. keep_every=5,
    offset=101 on a 1-frame run) must be rejected, not render a broken
    empty page that dereferences DATA.frames[0]."""
    from market_game_sim.replay.generate import build_replay

    log_path = _write_minimal_v3_log(tmp_path)
    with pytest.raises(ValueError, match="zero frames"):
        build_replay(
            log_path,
            tmp_path / "out.html",
            downsample=DownsampleRule(keep_every=5, offset=101),
        )


def test_build_replay_accepts_matching_rule(tmp_path):
    """F-E2 accepted: a rule matching the only frame (offset 0) renders fine."""
    from market_game_sim.replay.generate import build_replay

    log_path = _write_minimal_v3_log(tmp_path)
    out = tmp_path / "out.html"
    build_replay(log_path, out, downsample=DownsampleRule(keep_every=5))
    assert out.is_file()
