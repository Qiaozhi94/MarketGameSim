"""T603 (SC-006): Independent verifier tests."""

import json

import pytest

from market_game_sim.book.simulator import run_simulation
from market_game_sim.ledger.account import Account
from market_game_sim.verify import digest_events, verify_log


def _sim_log(abort: bool = False) -> list[dict]:
    accounts = {
        "A": Account("A", 100000000000),
        "B": Account("B", 100000000000),
    }
    events = [
        {"event_type": "ORDER_ARRIVAL", "timestamp": 100, "agent_id": "B",
         "order_id": "o1", "action": "SUBMIT", "side": "SELL", "order_type": "LIMIT",
         "price_ticks": 10000, "quantity_units": 5000},
        {"event_type": "ORDER_ARRIVAL", "timestamp": 200, "agent_id": "A",
         "order_id": "o2", "action": "SUBMIT", "side": "BUY", "order_type": "LIMIT",
         "price_ticks": 10000, "quantity_units": 3000},
    ]
    records, book = run_simulation([], events, accounts=accounts)
    # Wrap records for verify: add RUN_HEADER, record_kind, RUN_TRAILER
    header = {"record_kind": "RUN_HEADER", "record_count": len(records) + 2}
    trailer = {"record_kind": "RUN_TRAILER", "terminated": "COMPLETED",
               "last_committed_transaction_seq": max(r["transaction_seq"] for r in records)}
    for r in records:
        r["record_kind"] = "EVENT"
    return [header] + records + [trailer]


class TestVerify:
    def test_valid_log_passes(self, tmp_path):
        records = _sim_log()
        log_path = tmp_path / "run.jsonl"
        lines = [json.dumps(r, ensure_ascii=False) for r in records]
        log_path.write_text("\n".join(lines), encoding="utf-8")
        result = verify_log(log_path)
        assert result["success"], f"verify failed: {result}"

    def test_truncated_log_ti5(self, tmp_path):
        records = _sim_log()
        log_path = tmp_path / "run.jsonl"
        lines = [json.dumps(r, ensure_ascii=False) for r in records]
        truncated = lines[:-1]
        log_path.write_text("\n".join(truncated), encoding="utf-8")
        result = verify_log(log_path)
        assert not result["success"]
        assert result["error"] == "TI-5"

    def test_empty_file_ti5(self, tmp_path):
        log_path = tmp_path / "run.jsonl"
        log_path.write_text("", encoding="utf-8")
        result = verify_log(log_path)
        assert not result["success"]

    def test_broken_json_ti5(self, tmp_path):
        log_path = tmp_path / "run.jsonl"
        log_path.write_text('{"record_kind":"RUN_HEADER"}\nnot-json!!!\n{"record_kind":"RUN_TRAILER"}', encoding="utf-8")
        result = verify_log(log_path)
        assert not result["success"]
        assert result["error"] == "TI-5"

    def test_aborted_then_truncated_still_ti5(self, tmp_path):
        log_path = tmp_path / "run.jsonl"
        log_path.write_text(
            '{"record_kind":"RUN_HEADER"}\n'
            '{"record_kind":"EVENT"}\n'
            '{"record_kind":"RUN_TRAILER","terminated":"ABORTED"}\n'
            'garbage',
            encoding="utf-8",
        )
        result = verify_log(log_path)
        assert not result["success"]
        assert result["error"] == "TI-5"
