"""T101 (FR-019): independent event-log reader tests."""

from __future__ import annotations

import json

import pytest

from market_game_sim.replay.reader import LogError, read_log


def _snapshot(txn: int, kind: str) -> dict:
    return {
        "record_kind": "EVENT",
        "schema_version": 3,
        "event_id": f"e{txn}_0",
        "run_id": "run-1",
        "timestamp": 0,
        "transaction_seq": txn,
        "record_index": 0,
        "priority_class": 5,
        "event_type": "SNAPSHOT",
        "snapshot_type": kind,
        "payload": {"accounts": [], "exchange": {}}
        if kind == "ACCOUNT"
        else {"bids": [], "asks": []},
    }


def _header() -> dict:
    return {
        "record_kind": "RUN_HEADER",
        "schema_version": 3,
        "run_id": "run-1",
        "tick_size": "0.01",
        "min_quantity": "0.001",
        "cash_unit": "0.01",
        "mult": 1000,
        "fee_bps_cap": 0,
        "initial_price_ticks": 10000,
        "agent_initial_bp": {},
    }


def _trailer(record_count: int, terminated: str = "COMPLETED") -> dict:
    return {
        "record_kind": "RUN_TRAILER",
        "terminated": terminated,
        "abort_code": None if terminated == "COMPLETED" else "INTERNAL",
        "abort_detail": None,
        "last_committed_transaction_seq": 2,
        "record_count": record_count,
    }


def _write_log(tmp_path, records: list[dict]) -> None:
    p = tmp_path / "log.jsonl"
    p.write_text(
        "".join(json.dumps(r) + "\n" for r in records),
        encoding="utf-8",
    )
    return p


def test_accepts_valid_log(tmp_path):
    records = [_header(), _snapshot(1, "ACCOUNT"), _snapshot(2, "BOOK"), _trailer(4)]
    p = _write_log(tmp_path, records)
    log = read_log(p)
    assert log.run_id == "run-1"
    assert len(log.events) == 2
    assert log.trailer["terminated"] == "COMPLETED"
    assert log.config.mult == 1000
    assert log.config.initial_price_ticks == 10000


def test_rejects_first_not_run_header(tmp_path):
    records = [_snapshot(1, "ACCOUNT"), _snapshot(2, "BOOK"), _trailer(3)]
    p = _write_log(tmp_path, records)
    with pytest.raises(LogError, match="TI-5"):
        read_log(p)


def test_rejects_missing_trailer(tmp_path):
    records = [_header(), _snapshot(1, "ACCOUNT"), _snapshot(2, "BOOK")]
    p = _write_log(tmp_path, records)
    with pytest.raises(LogError, match="TI-5"):
        read_log(p)


def test_rejects_record_count_mismatch(tmp_path):
    records = [_header(), _snapshot(1, "ACCOUNT"), _snapshot(2, "BOOK"), _trailer(99)]
    p = _write_log(tmp_path, records)
    with pytest.raises(LogError, match="TI-5"):
        read_log(p)


def test_rejects_aborted_run_as_ti4(tmp_path):
    records = [_header(), _snapshot(1, "ACCOUNT"), _snapshot(2, "BOOK"), _trailer(4, "ABORTED")]
    p = _write_log(tmp_path, records)
    with pytest.raises(LogError, match="TI-4"):
        read_log(p)


def test_rejects_corrupt_json_line(tmp_path):
    records = [_header(), _snapshot(1, "ACCOUNT"), _snapshot(2, "BOOK"), _trailer(4)]
    p = tmp_path / "log.jsonl"
    p.write_text(
        "".join(json.dumps(r) + "\n" for r in records[:-1]) + "{not json}\n",
        encoding="utf-8",
    )
    with pytest.raises(LogError, match="TI-5"):
        read_log(p)


# --- F4 regression tests ---


def test_rejects_json_scalar_line(tmp_path):
    """F4: a JSON scalar (not object) must be rejected with LogError."""
    records = [_header(), _snapshot(1, "ACCOUNT"), _snapshot(2, "BOOK"), _trailer(4)]
    p = tmp_path / "log.jsonl"
    p.write_text(
        json.dumps(records[0])
        + "\n"
        + json.dumps(records[1])
        + "\n"
        + json.dumps(records[2])
        + "\n"
        + '"a string scalar"\n',
        encoding="utf-8",
    )
    with pytest.raises(LogError, match="TI-5"):
        read_log(p)


def test_rejects_json_number_line(tmp_path):
    """F4: a JSON number (not object) must be rejected with LogError."""
    records = [_header(), _snapshot(1, "ACCOUNT"), _snapshot(2, "BOOK"), _trailer(4)]
    p = tmp_path / "log.jsonl"
    p.write_text(
        json.dumps(records[0])
        + "\n"
        + json.dumps(records[1])
        + "\n"
        + "42\n"
        + json.dumps(records[3])
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(LogError, match="TI-5"):
        read_log(p)


def test_rejects_unknown_record_kind(tmp_path):
    """F4: an unknown record_kind in the middle must be rejected, not silently discarded."""
    bad = dict(_snapshot(1, "ACCOUNT"))
    bad["record_kind"] = "WEIRD_KIND"
    records = [_header(), bad, _snapshot(2, "BOOK"), _trailer(4)]
    p = _write_log(tmp_path, records)
    with pytest.raises(LogError, match="TI-5"):
        read_log(p)


def test_rejects_missing_bootstrap_account_snapshot(tmp_path):
    """F4: missing bootstrap ACCOUNT snapshot must be rejected."""
    records = [_header(), _snapshot(2, "BOOK"), _trailer(3)]
    p = _write_log(tmp_path, records)
    with pytest.raises(LogError, match="TI-5"):
        read_log(p)


def test_rejects_missing_bootstrap_book_snapshot(tmp_path):
    """F4: missing bootstrap BOOK snapshot must be rejected."""
    records = [_header(), _snapshot(1, "ACCOUNT"), _trailer(3)]
    p = _write_log(tmp_path, records)
    with pytest.raises(LogError, match="TI-5"):
        read_log(p)


def test_rejects_record_index_gap(tmp_path):
    """F4: record_index must be contiguous (0,1,2,...) within a transaction_seq."""
    e1 = _snapshot(1, "ACCOUNT")
    e2 = _snapshot(2, "BOOK")
    e3 = {
        "record_kind": "EVENT",
        "schema_version": 3,
        "run_id": "run-1",
        "timestamp": 10,
        "transaction_seq": 3,
        "record_index": 5,
        "priority_class": 1,
        "event_type": "MARKET_DATA_PUBLISH",
    }
    trailer = dict(_trailer(5))
    trailer["last_committed_transaction_seq"] = 3
    records = [_header(), e1, e2, e3, trailer]
    p = _write_log(tmp_path, records)
    with pytest.raises(LogError, match="TI-5"):
        read_log(p)


def test_accepts_contiguous_record_index(tmp_path):
    """F4 accepted side: contiguous record_index within a transaction passes."""
    e1 = _snapshot(1, "ACCOUNT")
    e2 = _snapshot(2, "BOOK")
    e3a = {
        "record_kind": "EVENT",
        "schema_version": 3,
        "event_id": "e3_0",
        "run_id": "run-1",
        "timestamp": 10,
        "transaction_seq": 3,
        "record_index": 0,
        "priority_class": 1,
        "event_type": "MARKET_DATA_PUBLISH",
    }
    e3b = {
        "record_kind": "EVENT",
        "schema_version": 3,
        "event_id": "e3_1",
        "run_id": "run-1",
        "timestamp": 10,
        "transaction_seq": 3,
        "record_index": 1,
        "priority_class": 1,
        "event_type": "ORDER_ARRIVAL",
    }
    trailer = dict(_trailer(6))
    trailer["last_committed_transaction_seq"] = 3
    records = [_header(), e1, e2, e3a, e3b, trailer]
    p = _write_log(tmp_path, records)
    log = read_log(p)
    assert len(log.events) == 4


def test_rejects_last_committed_mismatch(tmp_path):
    """F4: trailer last_committed_transaction_seq != max event txn must be rejected."""
    e1 = _snapshot(1, "ACCOUNT")
    e2 = _snapshot(2, "BOOK")
    e3 = {
        "record_kind": "EVENT",
        "schema_version": 3,
        "run_id": "run-1",
        "timestamp": 10,
        "transaction_seq": 3,
        "record_index": 0,
        "priority_class": 1,
        "event_type": "MARKET_DATA_PUBLISH",
    }
    trailer = dict(_trailer(5))
    trailer["last_committed_transaction_seq"] = 99
    records = [_header(), e1, e2, e3, trailer]
    p = _write_log(tmp_path, records)
    with pytest.raises(LogError, match="TI-5"):
        read_log(p)


def test_rejects_schema_version_mismatch(tmp_path):
    """F4: event schema_version != header schema_version must be rejected."""
    e1 = _snapshot(1, "ACCOUNT")
    e1["schema_version"] = 99
    records = [_header(), e1, _snapshot(2, "BOOK"), _trailer(4)]
    p = _write_log(tmp_path, records)
    with pytest.raises(LogError, match="TI-5"):
        read_log(p)


def test_rejects_run_id_mismatch(tmp_path):
    """F4: event run_id != header run_id must be rejected."""
    e1 = _snapshot(1, "ACCOUNT")
    e1["run_id"] = "different-run"
    records = [_header(), e1, _snapshot(2, "BOOK"), _trailer(4)]
    p = _write_log(tmp_path, records)
    with pytest.raises(LogError, match="TI-5"):
        read_log(p)


def test_rejects_missing_replay_config_fields(tmp_path):
    """F1: header without replay-critical fields must be rejected."""
    h = {
        "record_kind": "RUN_HEADER",
        "schema_version": 3,
        "run_id": "run-1",
        "tick_size": "0.01",
        "min_quantity": "0.001",
        "cash_unit": "0.01",
    }
    records = [h, _snapshot(1, "ACCOUNT"), _snapshot(2, "BOOK"), _trailer(4)]
    p = _write_log(tmp_path, records)
    with pytest.raises(LogError, match="TI-5"):
        read_log(p)


def test_rejects_wrong_type_replay_config_fields(tmp_path):
    """F1: header with wrong-typed replay-critical fields must be rejected."""
    h = dict(_header())
    h["mult"] = "not an int"
    records = [h, _snapshot(1, "ACCOUNT"), _snapshot(2, "BOOK"), _trailer(4)]
    p = _write_log(tmp_path, records)
    with pytest.raises(LogError, match="TI-5"):
        read_log(p)


def test_accepts_replay_config_with_agent_initial_bp(tmp_path):
    """F1 accepted side: header with agent_initial_bp populated parses correctly."""
    h = dict(_header())
    h["agent_initial_bp"] = {"A": 1000, "B": 2000}
    records = [h, _snapshot(1, "ACCOUNT"), _snapshot(2, "BOOK"), _trailer(4)]
    p = _write_log(tmp_path, records)
    log = read_log(p)
    assert log.config.agent_initial_bp == {"A": 1000, "B": 2000}


def test_rejects_multiple_run_headers(tmp_path):
    """F4: multiple RUN_HEADER records must be rejected."""
    records = [_header(), _header(), _snapshot(2, "BOOK"), _trailer(4)]
    p = _write_log(tmp_path, records)
    with pytest.raises(LogError, match="TI-5"):
        read_log(p)


# --- F-C regression tests: exact bootstrap structure ---


def _bootstrap_log(*events) -> list[dict]:
    """Log records with the given EVENTs (bootstrap pairs default to 1/2)."""
    e = list(events)
    if not e:
        e = [_snapshot(1, "ACCOUNT"), _snapshot(2, "BOOK")]
    trailer = dict(_trailer(len(e) + 2))
    trailer["last_committed_transaction_seq"] = max((ev["transaction_seq"] for ev in e), default=2)
    return [_header(), *e, trailer]


def test_accepts_contiguous_bootstrap_at_later_txns(tmp_path):
    """F-C accepted: real-kernel shape -- ACCOUNT at txn 3, BOOK at txn 4
    (contiguous, t=0, record_index=0) is valid.  The experiment runner
    enqueues AGENT_OBSERVE at t=0 (class 3) which is processed before
    SNAPSHOT (class 5), so bootstrap snapshots land at txn 3/4 in practice.
    The contract requires contiguous transactions, timestamp=0, and
    record_index=0 -- not absolute txn 1/2."""
    acct = _snapshot(3, "ACCOUNT")
    book = _snapshot(4, "BOOK")
    records = _bootstrap_log(acct, book)
    p = _write_log(tmp_path, records)
    log = read_log(p)
    assert len(log.events) == 2


def test_rejects_bootstrap_txn_gap(tmp_path):
    """F-C rejected: ACCOUNT at 5, BOOK at 8 (non-contiguous) must be TI-5."""
    records = _bootstrap_log(_snapshot(5, "ACCOUNT"), _snapshot(8, "BOOK"))
    p = _write_log(tmp_path, records)
    with pytest.raises(LogError, match="TI-5"):
        read_log(p)


def test_rejects_swapped_bootstrap_order(tmp_path):
    """F-C rejected: BOOK before ACCOUNT must be TI-5."""
    records = _bootstrap_log(_snapshot(1, "BOOK"), _snapshot(2, "ACCOUNT"))
    p = _write_log(tmp_path, records)
    with pytest.raises(LogError, match="TI-5"):
        read_log(p)


def test_rejects_bootstrap_nonzero_timestamp(tmp_path):
    """F-C rejected: bootstrap snapshot with timestamp != 0 must be TI-5."""
    acct = _snapshot(1, "ACCOUNT")
    acct["timestamp"] = 100
    records = _bootstrap_log(acct, _snapshot(2, "BOOK"))
    p = _write_log(tmp_path, records)
    with pytest.raises(LogError, match="TI-5"):
        read_log(p)


def test_rejects_bootstrap_nonzero_record_index(tmp_path):
    """F-C rejected: bootstrap snapshot with record_index != 0 must be TI-5."""
    book = _snapshot(2, "BOOK")
    book["record_index"] = 1
    records = _bootstrap_log(_snapshot(1, "ACCOUNT"), book)
    p = _write_log(tmp_path, records)
    with pytest.raises(LogError, match="TI-5"):
        read_log(p)


def test_rejects_missing_bootstrap_book(tmp_path):
    """F-C rejected: only the ACCOUNT snapshot present must be TI-5."""
    records = _bootstrap_log(_snapshot(1, "ACCOUNT"))
    p = _write_log(tmp_path, records)
    with pytest.raises(LogError, match="TI-5"):
        read_log(p)


# --- F-H2 regression tests: schema_version must be exactly v3 ---


def test_rejects_v2_even_with_replay_fields(tmp_path):
    """F-H2 rejected: a v2 header carrying the replay fields is still an
    unknown-format log (ADR-004 v2 explicit-rejection policy)."""
    h = dict(_header())
    h["schema_version"] = 2
    records = [h, _snapshot(1, "ACCOUNT"), _snapshot(2, "BOOK"), _trailer(4)]
    p = _write_log(tmp_path, records)
    with pytest.raises(LogError, match="TI-5.*schema_version"):
        read_log(p)


def test_rejects_future_schema_version(tmp_path):
    """F-H2 rejected: an unknown future schema_version (e.g. 4) must be refused."""
    h = dict(_header())
    h["schema_version"] = 4
    records = [h, _snapshot(1, "ACCOUNT"), _snapshot(2, "BOOK"), _trailer(4)]
    p = _write_log(tmp_path, records)
    with pytest.raises(LogError, match="TI-5.*schema_version"):
        read_log(p)


def test_accepts_v3(tmp_path):
    """F-H2 accepted: a v3 header parses successfully."""
    records = [_header(), _snapshot(1, "ACCOUNT"), _snapshot(2, "BOOK"), _trailer(4)]
    p = _write_log(tmp_path, records)
    log = read_log(p)
    assert log.header["schema_version"] == 3


# --- F-C2 regression tests: EVENT / trailer required fields ---


def test_rejects_event_missing_schema_version(tmp_path):
    """F-C2 rejected: an EVENT lacking schema_version must be TI-5."""
    e1 = _snapshot(1, "ACCOUNT")
    del e1["schema_version"]
    records = [_header(), e1, _snapshot(2, "BOOK"), _trailer(4)]
    p = _write_log(tmp_path, records)
    with pytest.raises(LogError, match="TI-5.*missing required"):
        read_log(p)


def test_rejects_event_missing_run_id(tmp_path):
    """F-C2 rejected: an EVENT lacking run_id must be TI-5."""
    e1 = _snapshot(1, "ACCOUNT")
    del e1["run_id"]
    records = [_header(), e1, _snapshot(2, "BOOK"), _trailer(4)]
    p = _write_log(tmp_path, records)
    with pytest.raises(LogError, match="TI-5.*missing required"):
        read_log(p)


def test_rejects_trailer_without_terminated(tmp_path):
    """F-C2 rejected: a trailer lacking terminated must be TI-5 (the reviewer's
    exact repro: trailer containing only record_kind)."""
    t = {"record_kind": "RUN_TRAILER"}
    records = [_header(), _snapshot(1, "ACCOUNT"), _snapshot(2, "BOOK"), t]
    p = _write_log(tmp_path, records)
    with pytest.raises(LogError, match="TI-5.*terminated"):
        read_log(p)


def test_rejects_aborted_trailer_without_abort_code(tmp_path):
    """F-C2 rejected: an ABORTED trailer must carry abort_code."""
    t = dict(_trailer(4, "ABORTED"))
    t["abort_code"] = None
    records = [_header(), _snapshot(1, "ACCOUNT"), _snapshot(2, "BOOK"), t]
    p = _write_log(tmp_path, records)
    with pytest.raises(LogError, match="TI-5.*abort_code"):
        read_log(p)


# --- F-H4 regression tests (round-6): trailer full-field enforcement ---


def test_rejects_trailer_missing_last_committed(tmp_path):
    """F-H4 rejected: a trailer without last_committed_transaction_seq must be TI-5."""
    t = dict(_trailer(4))
    del t["last_committed_transaction_seq"]
    records = [_header(), _snapshot(1, "ACCOUNT"), _snapshot(2, "BOOK"), t]
    p = _write_log(tmp_path, records)
    with pytest.raises(LogError, match="TI-5.*missing required"):
        read_log(p)


def test_rejects_completed_trailer_with_abort_code(tmp_path):
    """F-H4 rejected: COMPLETED must carry abort_code=null (event-schema §6.2)."""
    t = dict(_trailer(4))
    t["abort_code"] = "INTERNAL"
    records = [_header(), _snapshot(1, "ACCOUNT"), _snapshot(2, "BOOK"), t]
    p = _write_log(tmp_path, records)
    with pytest.raises(LogError, match="TI-5.*abort_code=null"):
        read_log(p)


def test_rejects_trailer_missing_abort_detail(tmp_path):
    """F-H4 rejected: a trailer without abort_detail must be TI-5 (it is a
    required column of §6.2, COMPLETED must carry null)."""
    t = dict(_trailer(4))
    del t["abort_detail"]
    records = [_header(), _snapshot(1, "ACCOUNT"), _snapshot(2, "BOOK"), t]
    p = _write_log(tmp_path, records)
    with pytest.raises(LogError, match="TI-5.*missing required"):
        read_log(p)
