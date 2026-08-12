"""T103 (FR-019): per-frame sequence tests (E1 input)."""

from __future__ import annotations

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


def _trivial(txn: int) -> dict:
    return {
        "event_type": "MARKET_DATA_PUBLISH",
        "timestamp": txn,
        "transaction_seq": txn,
        "record_index": 0,
    }


def test_frame_count_is_transactions_minus_one():
    events = [_ev(1, "ACCOUNT"), _ev(2, "BOOK"), _trivial(3), _trivial(4)]
    frames = _build_frames(events, MULT)
    assert len(frames) == 3  # T=4 -> frames 0..2


def test_frame_index_and_transaction_seq_alignment():
    events = [_ev(1, "ACCOUNT"), _ev(2, "BOOK"), _trivial(3), _trivial(4), _trivial(5)]
    frames = _build_frames(events, MULT)
    assert [f.frame_index for f in frames] == [0, 1, 2, 3]
    assert [f.transaction_seq for f in frames] == [2, 3, 4, 5]


def test_zero_business_transactions_yields_one_frame():
    events = [_ev(1, "ACCOUNT"), _ev(2, "BOOK")]
    frames = _build_frames(events, MULT)
    assert len(frames) == 1
    assert frames[0].frame_index == 0
    assert frames[0].transaction_seq == 2


def test_frame_zero_merges_both_bootstrap_snapshots():
    """Frame 0 must reflect the merged ACCOUNT + BOOK bootstrap state."""
    acct = _ev(1, "ACCOUNT")
    acct["payload"]["accounts"] = [
        {
            "agent_id": "A",
            "wallet_units": 5000,
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
    ]
    book = _ev(2, "BOOK")
    book["payload"]["last_ticks"] = None
    frames = _build_frames([acct, book], MULT)
    assert frames[0].accounts["A"]["wallet_units"] == 5000
    assert frames[0].last_ticks is None
    assert frames[0].exchange == {"fee_cash_units": 0, "risk_pnl_units": 0}


# --- F6 regression tests ---


def test_frame_timestamp_equals_transaction_event_timestamp():
    """F6: frame.timestamp must equal the max event timestamp in that transaction."""
    events = [
        _ev(1, "ACCOUNT"),
        _ev(2, "BOOK"),
        {
            "event_type": "MARKET_DATA_PUBLISH",
            "timestamp": 42,
            "transaction_seq": 3,
            "record_index": 0,
        },
        {
            "event_type": "MARKET_DATA_PUBLISH",
            "timestamp": 99,
            "transaction_seq": 4,
            "record_index": 0,
        },
    ]
    frames = _build_frames(events, MULT)
    assert frames[0].timestamp == 0
    assert frames[1].timestamp == 42
    assert frames[2].timestamp == 99


def test_frame_timestamp_uses_max_within_multi_record_transaction():
    """F6: when a transaction has multiple records, timestamp is the max."""
    events = [
        _ev(1, "ACCOUNT"),
        _ev(2, "BOOK"),
        {
            "event_type": "MARKET_DATA_PUBLISH",
            "timestamp": 10,
            "transaction_seq": 3,
            "record_index": 0,
        },
        {
            "event_type": "ORDER_ARRIVAL",
            "timestamp": 50,
            "transaction_seq": 3,
            "record_index": 1,
        },
    ]
    frames = _build_frames(events, MULT)
    assert len(frames) == 2
    assert frames[1].timestamp == 50
