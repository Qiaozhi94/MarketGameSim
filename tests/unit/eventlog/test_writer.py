"""T205: Event log writer + run metadata header.

[事件 Schema §6-§9] 事件日志写入器
[事件 Schema §6.1] RUN_HEADER with string-decimal units
[事件 Schema §4.6.3] bootstrap snapshots as first two EVENTs
[事件 Schema §1.5] fail-stop produces ABORTED trailer
"""

from __future__ import annotations

import json
import pathlib

import pytest

from market_game_sim.config.serialization import canonical_serialize
from market_game_sim.eventlog.bootstrap import (
    build_account_payload,
    build_account_snapshot_entry,
    build_book_payload,
)
from market_game_sim.eventlog.termination import classify_log
from market_game_sim.eventlog.writer import build_run_header, serialize_log, write_log
from market_game_sim.kernel.runner import EventKernel


def _make_header(run_id: str = "r") -> dict:
    return build_run_header(
        run_id=run_id,
        code_version="abc123",
        config_hash="0" * 64,
        master_seed=42,
        started_at_wall="2026-01-01T00:00:00Z",
        tick_size="0.01",
        min_quantity="0.001",
        cash_unit="0.01",
    )


def _bootstrap(kernel: EventKernel) -> None:
    kernel.bootstrap(
        build_account_payload(
            [build_account_snapshot_entry("A", 1000, 0, 0, 0, 0, "ACTIVE", 0)]
        ),
        build_book_payload(),
    )


class TestRunHeader:
    def test_header_fields(self):
        h = _make_header()
        assert h["record_kind"] == "RUN_HEADER"
        assert h["schema_version"] == 2
        assert h["tick_size"] == "0.01"
        assert h["min_quantity"] == "0.001"
        assert h["cash_unit"] == "0.01"
        assert h["run_mode"] == "benchmark"
        assert h["information_set_mode"] == "full"

    def test_header_byte_deterministic(self):
        h1 = _make_header("r1")
        h2 = _make_header("r1")
        assert canonical_serialize(h1) == canonical_serialize(h2)

    def test_header_rejects_float_units(self):
        with pytest.raises(TypeError):
            build_run_header(
                run_id="r", code_version="v", config_hash="h", master_seed=1,
                started_at_wall="t", tick_size=0.01, min_quantity="0.001", cash_unit="0.01",
            )


class TestWriterStructure:
    def test_log_has_header_events_trailer(self, tmp_path: pathlib.Path):
        kernel = EventKernel(run_id="w1")
        _bootstrap(kernel)
        path = tmp_path / "log.jsonl"
        write_log(path, _make_header("w1"), kernel, lambda e, w, k: [], {}, 2)

        lines = path.read_text(encoding="utf-8").strip().split("\n")
        records = [json.loads(ln) for ln in lines]
        assert records[0]["record_kind"] == "RUN_HEADER"
        assert records[-1]["record_kind"] == "RUN_TRAILER"
        assert all(r["record_kind"] == "EVENT" for r in records[1:-1])

    def test_record_count_includes_header_and_trailer(self, tmp_path: pathlib.Path):
        kernel = EventKernel(run_id="w2")
        _bootstrap(kernel)
        path = tmp_path / "log.jsonl"
        write_log(path, _make_header("w2"), kernel, lambda e, w, k: [], {}, 2)

        lines = path.read_text(encoding="utf-8").strip().split("\n")
        records = [json.loads(ln) for ln in lines]
        trailer = records[-1]
        assert trailer["record_count"] == len(records)

    def test_bootstrap_events_first(self, tmp_path: pathlib.Path):
        kernel = EventKernel(run_id="w3")
        _bootstrap(kernel)
        path = tmp_path / "log.jsonl"
        write_log(path, _make_header("w3"), kernel, lambda e, w, k: [], {}, 2)

        lines = path.read_text(encoding="utf-8").strip().split("\n")
        records = [json.loads(ln) for ln in lines]
        events = [r for r in records if r["record_kind"] == "EVENT"]
        assert events[0]["event_type"] == "SNAPSHOT"
        assert events[0]["snapshot_type"] == "ACCOUNT"
        assert events[1]["event_type"] == "SNAPSHOT"
        assert events[1]["snapshot_type"] == "BOOK"
        assert events[0]["transaction_seq"] == 1
        assert events[1]["transaction_seq"] == 2

    def test_completed_trailer(self, tmp_path: pathlib.Path):
        kernel = EventKernel(run_id="w4")
        _bootstrap(kernel)
        path = tmp_path / "log.jsonl"
        trailer = write_log(path, _make_header("w4"), kernel, lambda e, w, k: [], {}, 2)

        assert trailer["terminated"] == "COMPLETED"
        assert trailer["abort_code"] is None
        assert trailer["abort_detail"] is None
        assert trailer["last_committed_transaction_seq"] == 2

    def test_log_byte_deterministic(self):
        kernel1 = EventKernel(run_id="w5")
        _bootstrap(kernel1)
        kernel1.run(lambda e, w, k: [], {}, 2)
        log1 = serialize_log(_make_header("w5"), kernel1)

        kernel2 = EventKernel(run_id="w5")
        _bootstrap(kernel2)
        kernel2.run(lambda e, w, k: [], {}, 2)
        log2 = serialize_log(_make_header("w5"), kernel2)

        assert log1 == log2


class TestWriterFailStop:
    def test_aborted_log_written(self, tmp_path: pathlib.Path):
        kernel = EventKernel(run_id="w6")
        _bootstrap(kernel)

        def fail_handler(event, world, kernel):
            if event.get("snapshot_type") == "BOOK":
                raise RuntimeError("boom")
            return []

        path = tmp_path / "log.jsonl"
        trailer = write_log(path, _make_header("w6"), kernel, fail_handler, {}, 10)

        assert trailer["terminated"] == "ABORTED"
        assert trailer["abort_code"] == "INTERNAL"
        assert trailer["last_committed_transaction_seq"] == 1

        lines = path.read_text(encoding="utf-8").strip().split("\n")
        records = [json.loads(ln) for ln in lines]
        assert records[0]["record_kind"] == "RUN_HEADER"
        assert records[-1]["record_kind"] == "RUN_TRAILER"
        assert records[-1]["terminated"] == "ABORTED"

    def test_aborted_log_classified_ti4(self, tmp_path: pathlib.Path):
        kernel = EventKernel(run_id="w7")
        _bootstrap(kernel)

        def fail_handler(event, world, kernel):
            if event.get("snapshot_type") == "BOOK":
                raise RuntimeError("boom")
            return []

        path = tmp_path / "log.jsonl"
        write_log(path, _make_header("w7"), kernel, fail_handler, {}, 10)
        text = path.read_text(encoding="utf-8")
        assert classify_log(text) == "TI-4"

    def test_failed_transaction_not_in_log(self, tmp_path: pathlib.Path):
        kernel = EventKernel(run_id="w8")
        _bootstrap(kernel)

        call_count = [0]

        def fail_on_second(event, world, kernel):
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("fail on second")
            return []

        path = tmp_path / "log.jsonl"
        write_log(path, _make_header("w8"), kernel, fail_on_second, {}, 10)

        lines = path.read_text(encoding="utf-8").strip().split("\n")
        records = [json.loads(ln) for ln in lines]
        events = [r for r in records if r["record_kind"] == "EVENT"]
        assert len(events) == 1  # only the first (ACCOUNT) snapshot committed
