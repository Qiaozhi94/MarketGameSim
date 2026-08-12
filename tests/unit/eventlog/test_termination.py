"""T204e2: Termination discrimination -- TI-4 vs TI-5.

[事件 Schema §1.5] 先结构后语义
[退化状态 §4.1] TI-4 / TI-5 互斥

Three test vectors:
  1. Inject exception -> TI-4
  2. Normal log truncated -> TI-5
  3. ABORTED log also truncated -> TI-5 (NOT TI-4)
"""

from __future__ import annotations

import json

from market_game_sim.eventlog.bootstrap import (
    build_account_payload,
    build_account_snapshot_entry,
    build_book_payload,
)
from market_game_sim.eventlog.termination import classify_log
from market_game_sim.eventlog.writer import build_run_header, serialize_log
from market_game_sim.kernel.runner import EventKernel


def _make_header(run_id: str = "r") -> dict:
    return build_run_header(
        run_id=run_id,
        code_version="test",
        config_hash="0" * 64,
        master_seed=42,
        started_at_wall="2026-01-01T00:00:00Z",
        tick_size="0.01",
        min_quantity="0.001",
        cash_unit="0.01",
        mult=1000,
        fee_bps_cap=0,
        initial_price_ticks=10000,
        agent_initial_bp={},
    )


def _make_completed_log() -> bytes:
    kernel = EventKernel(run_id="ok")
    account = build_account_payload(
        [build_account_snapshot_entry("A", 1000, 0, 0, 0, 0, "ACTIVE", 0)]
    )
    kernel.bootstrap(account, build_book_payload())
    kernel.run(lambda e, w, k: [], {}, max_transactions=2)
    return serialize_log(_make_header(), kernel)


def _make_aborted_log() -> bytes:
    kernel = EventKernel(run_id="aborted")

    def fail_handler(event, world, kernel):
        if event.get("snapshot_type") == "BOOK":
            raise RuntimeError("injected")
        return []

    account = build_account_payload(
        [build_account_snapshot_entry("A", 1000, 0, 0, 0, 0, "ACTIVE", 0)]
    )
    kernel.bootstrap(account, build_book_payload())
    kernel.run(fail_handler, {}, max_transactions=10)
    return serialize_log(_make_header("aborted"), kernel)


class TestTerminationClassification:
    def test_completed_log_is_valid(self):
        log = _make_completed_log()
        assert classify_log(log.decode("utf-8")) == "VALID"

    def test_aborted_log_is_ti4(self):
        """Vector 1: injected exception -> TI-4."""
        log = _make_aborted_log()
        assert classify_log(log.decode("utf-8")) == "TI-4"

    def test_truncated_normal_log_is_ti5(self):
        """Vector 2: normal log with last line removed -> TI-5."""
        log = _make_completed_log().decode("utf-8")
        lines = log.strip().split("\n")
        truncated = "\n".join(lines[:-1]) + "\n"
        assert classify_log(truncated) == "TI-5"

    def test_truncated_aborted_log_is_ti5(self):
        """Vector 3: ABORTED log also truncated -> TI-5 (NOT TI-4).

        The combined case where naive implementations give different codes.
        """
        log = _make_aborted_log().decode("utf-8")
        lines = log.strip().split("\n")
        truncated = "\n".join(lines[:-1]) + "\n"
        assert classify_log(truncated) == "TI-5"

    def test_empty_log_is_ti5(self):
        assert classify_log("") == "TI-5"
        assert classify_log("   \n  \n") == "TI-5"

    def test_corrupt_json_is_ti5(self):
        log = '{"record_kind":"RUN_HEADER"}\n{bad json}\n'
        assert classify_log(log) == "TI-5"

    def test_missing_header_is_ti5(self):
        trailer = json.dumps({"record_kind": "RUN_TRAILER", "terminated": "COMPLETED"})
        log = '{"record_kind":"EVENT"}\n' + trailer + "\n"
        assert classify_log(log) == "TI-5"

    def test_missing_trailer_is_ti5(self):
        header = json.dumps({"record_kind": "RUN_HEADER"})
        log = header + '\n{"record_kind":"EVENT"}\n'
        assert classify_log(log) == "TI-5"

    def test_record_count_mismatch_is_ti5(self):
        header = json.dumps({"record_kind": "RUN_HEADER"})
        event = json.dumps({"record_kind": "EVENT"})
        trailer = json.dumps(
            {
                "record_kind": "RUN_TRAILER",
                "terminated": "COMPLETED",
                "abort_code": None,
                "abort_detail": None,
                "last_committed_transaction_seq": 1,
                "record_count": 99,
            }
        )
        log = header + "\n" + event + "\n" + trailer + "\n"
        assert classify_log(log) == "TI-5"

    def test_record_count_correct_is_valid(self):
        header = json.dumps({"record_kind": "RUN_HEADER"})
        event = json.dumps({"record_kind": "EVENT"})
        trailer = json.dumps(
            {
                "record_kind": "RUN_TRAILER",
                "terminated": "COMPLETED",
                "abort_code": None,
                "abort_detail": None,
                "last_committed_transaction_seq": 1,
                "record_count": 3,
            }
        )
        log = header + "\n" + event + "\n" + trailer + "\n"
        assert classify_log(log) == "VALID"

    def test_classify_log_bytes(self):
        from market_game_sim.eventlog.termination import classify_log_bytes

        log = _make_completed_log()
        assert classify_log_bytes(log) == "VALID"
        assert classify_log_bytes(b"\xff\xfe invalid utf8") == "TI-5"
