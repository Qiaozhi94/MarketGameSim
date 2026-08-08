"""T603 (SC-006): Independent verifier tests."""

import json

from market_game_sim.book.simulator import run_simulation
from market_game_sim.ledger.account import Account
from market_game_sim.verify import verify_log


def _sim_log(abort: bool = False) -> list[dict]:
    accounts = {
        "A": Account("A", 100000000000),
        "B": Account("B", 100000000000),
    }
    events = [
        {
            "event_type": "ORDER_ARRIVAL",
            "timestamp": 100,
            "agent_id": "B",
            "order_id": "o1",
            "action": "SUBMIT",
            "side": "SELL",
            "order_type": "LIMIT",
            "price_ticks": 10000,
            "quantity_units": 5000,
            "origin": "",
        },
        {
            "event_type": "ORDER_ARRIVAL",
            "timestamp": 200,
            "agent_id": "A",
            "order_id": "o2",
            "action": "SUBMIT",
            "side": "BUY",
            "order_type": "LIMIT",
            "price_ticks": 10000,
            "quantity_units": 3000,
            "origin": "",
        },
    ]
    records, book = run_simulation([], events, accounts=accounts)
    # Wrap records for verify: add RUN_HEADER, record_kind, RUN_TRAILER
    header = {"record_kind": "RUN_HEADER", "record_count": len(records) + 2}
    trailer = {
        "record_kind": "RUN_TRAILER",
        "terminated": "COMPLETED",
        "last_committed_transaction_seq": max(r["transaction_seq"] for r in records),
    }
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
        log_path.write_text(
            '{"record_kind":"RUN_HEADER"}\nnot-json!!!\n{"record_kind":"RUN_TRAILER"}',
            encoding="utf-8",
        )
        result = verify_log(log_path)
        assert not result["success"]
        assert result["error"] == "TI-5"

    def test_aborted_then_truncated_still_ti5(self, tmp_path):
        log_path = tmp_path / "run.jsonl"
        log_path.write_text(
            '{"record_kind":"RUN_HEADER"}\n'
            '{"record_kind":"EVENT"}\n'
            '{"record_kind":"RUN_TRAILER","terminated":"ABORTED"}\n'
            "garbage",
            encoding="utf-8",
        )
        result = verify_log(log_path)
        assert not result["success"]
        assert result["error"] == "TI-5"


class TestKpi006Regression:
    """§1.8 (T506/KPI-006): regression coverage for ``_check_kpi006``.

    Round 4/5/6 of the 0.1.2 implementation review found that the original
    ``_check_kpi006`` only required *any single* ``origin=AGENT`` order to
    link to a real ``AGENT_DECIDE`` before declaring the whole log
    KPI-006-compliant -- so a log with mostly dangling
    ``decision_event_id`` references (and even one with zero
    ``AGENT_DECIDE`` events at all) would still pass ``verify_log``.

    Round 6 fixed the "mostly dangling" bypass by switching to a per-order
    check.  The "zero AGENT_DECIDE events" bypass is still open (tracked
    below as an expected failure) -- see
    docs/reviews/2026-08-06-v0.1.2-fix-verification-round6.md §3.

    Round 10 deepened the chain one hop further each side per
    event-schema.md §5.1/§5.2: AGENT_DECIDE.observation_event_id ->
    AGENT_OBSERVE.market_data_event_id, and MARGIN_CALL.caused_by_event_id/
    risk_mark_event_id must resolve within the SAME transaction_seq as the
    MARGIN_CALL.  All fixtures below were updated to carry a complete valid
    chain so they keep testing what they originally intended (rather than
    incidentally failing on the new, deeper hop).
    """

    @staticmethod
    def _write_log(tmp_path, events: list[dict]):
        header = {"record_kind": "RUN_HEADER"}
        trailer = {
            "record_kind": "RUN_TRAILER",
            "terminated": "COMPLETED",
            "record_count": len(events) + 2,
        }
        records = [header, *events, trailer]
        log_path = tmp_path / "run.jsonl"
        lines = [json.dumps(r, ensure_ascii=False) for r in records]
        log_path.write_text("\n".join(lines), encoding="utf-8")
        return log_path

    @staticmethod
    def _market_data_publish(event_id: str, tx: int) -> dict:
        return {
            "record_kind": "EVENT",
            "event_type": "MARKET_DATA_PUBLISH",
            "event_id": event_id,
            "timestamp": tx,
            "transaction_seq": tx,
            "record_index": 0,
        }

    @staticmethod
    def _agent_observe(event_id: str, market_data_event_id: str, tx: int) -> dict:
        return {
            "record_kind": "EVENT",
            "event_type": "AGENT_OBSERVE",
            "event_id": event_id,
            "market_data_event_id": market_data_event_id,
            "timestamp": tx,
            "transaction_seq": tx,
            "record_index": 0,
        }

    @staticmethod
    def _agent_decide(event_id: str, observation_event_id: str, tx: int) -> dict:
        return {
            "record_kind": "EVENT",
            "event_type": "AGENT_DECIDE",
            "event_id": event_id,
            "observation_event_id": observation_event_id,
            "timestamp": tx,
            "transaction_seq": tx,
            "record_index": 0,
        }

    @staticmethod
    def _agent_order(order_id: str, decision_event_id: str, tx: int) -> dict:
        return {
            "record_kind": "EVENT",
            "event_type": "ORDER_ARRIVAL",
            "origin": "AGENT",
            "order_id": order_id,
            "decision_event_id": decision_event_id,
            "timestamp": tx,
            "transaction_seq": tx,
            "record_index": 0,
        }

    @staticmethod
    def _order_arrival(event_id: str, tx: int, record_index: int) -> dict:
        return {
            "record_kind": "EVENT",
            "event_type": "ORDER_ARRIVAL",
            "event_id": event_id,
            "order_id": event_id,
            "origin": "",
            "timestamp": tx,
            "transaction_seq": tx,
            "record_index": record_index,
        }

    @staticmethod
    def _trade_settle(event_id: str, tx: int, record_index: int) -> dict:
        return {
            "record_kind": "EVENT",
            "event_type": "TRADE_SETTLE",
            "event_id": event_id,
            "timestamp": tx,
            "transaction_seq": tx,
            "record_index": record_index,
        }

    @staticmethod
    def _margin_call(
        event_id: str,
        caused_by_event_id: str,
        risk_mark_event_id: str,
        tx: int,
        record_index: int,
    ) -> dict:
        return {
            "record_kind": "EVENT",
            "event_type": "MARGIN_CALL",
            "event_id": event_id,
            "caused_by_event_id": caused_by_event_id,
            "risk_mark_event_id": risk_mark_event_id,
            "timestamp": tx,
            "transaction_seq": tx,
            "record_index": record_index,
        }

    @staticmethod
    def _liquidation_order(order_id: str, decision_event_id: str, tx: int) -> dict:
        return {
            "record_kind": "EVENT",
            "event_type": "ORDER_ARRIVAL",
            "origin": "LIQUIDATION",
            "order_id": order_id,
            "decision_event_id": decision_event_id,
            "timestamp": tx,
            "transaction_seq": tx,
            "record_index": 0,
        }

    def _valid_agent_chain(self, suffix: str, tx_base: int, order_id: str) -> list[dict]:
        md_id, obs_id, dec_id = f"md-{suffix}", f"obs-{suffix}", f"dec-{suffix}"
        return [
            self._market_data_publish(md_id, tx=tx_base),
            self._agent_observe(obs_id, md_id, tx=tx_base + 1),
            self._agent_decide(dec_id, obs_id, tx=tx_base + 2),
            self._agent_order(order_id, dec_id, tx=tx_base + 3),
        ]

    def test_all_agent_orders_correctly_linked_passes(self, tmp_path):
        events = [
            *self._valid_agent_chain("1", tx_base=1, order_id="o-1"),
            self._agent_order("o-2", "dec-1", tx=10),
        ]
        result = verify_log(self._write_log(tmp_path, events))
        assert result["success"], f"verify failed: {result}"
        assert result["kpi006_agent_covered"] is True

    def test_majority_dangling_with_real_decision_is_rejected(self, tmp_path):
        """Regression for the round4/5 bypass: 1 correct link + 6 dangling
        ones, with a real AGENT_DECIDE present, must now fail -- not pass
        just because *some* order links correctly."""
        events = [
            *self._valid_agent_chain("real", tx_base=1, order_id="o-good"),
            *[self._agent_order(f"o-bad-{i}", f"dangling-{i}", tx=10 + i) for i in range(6)],
        ]
        result = verify_log(self._write_log(tmp_path, events))
        assert not result["success"]
        assert result["error"] == "TI-5"
        assert "KPI-006" in result["detail"]

    def test_agent_orders_with_zero_decide_events_is_rejected(self, tmp_path):
        events = [self._agent_order(f"o-bad-{i}", f"dangling-{i}", tx=1 + i) for i in range(5)]
        result = verify_log(self._write_log(tmp_path, events))
        assert not result["success"], (
            "AGENT orders exist but no AGENT_DECIDE was ever recorded -- "
            "this should fail KPI-006, not silently pass"
        )

    def test_agent_decide_with_dangling_observation_is_rejected(self, tmp_path):
        """Round 10 deeper hop: AGENT_DECIDE.observation_event_id must
        resolve to a real, strictly-earlier AGENT_OBSERVE."""
        events = [
            self._agent_decide("dec-1", "nonexistent-obs", tx=1),
            self._agent_order("o-1", "dec-1", tx=2),
        ]
        result = verify_log(self._write_log(tmp_path, events))
        assert not result["success"]
        assert result["error"] == "TI-5"
        assert "observation_event_id" in result["detail"]

    def test_agent_observe_with_dangling_market_data_is_rejected(self, tmp_path):
        """Round 10 deeper hop: AGENT_OBSERVE.market_data_event_id must
        resolve to a real, strictly-earlier event."""
        events = [
            self._agent_observe("obs-1", "nonexistent-md", tx=1),
            self._agent_decide("dec-1", "obs-1", tx=2),
            self._agent_order("o-1", "dec-1", tx=3),
        ]
        result = verify_log(self._write_log(tmp_path, events))
        assert not result["success"]
        assert result["error"] == "TI-5"
        assert "market_data_event_id" in result["detail"]

    def _valid_liquidation_chain(self, tx: int) -> list[dict]:
        return [
            self._order_arrival("oa-1", tx=tx, record_index=0),
            self._trade_settle("trade-1", tx=tx, record_index=1),
            self._margin_call("mc-1", "oa-1", "trade-1", tx=tx, record_index=2),
        ]

    def test_liquidation_full_chain_passes(self, tmp_path):
        events = [
            *self._valid_liquidation_chain(tx=1),
            self._liquidation_order("liq-1", "mc-1", tx=2),
        ]
        result = verify_log(self._write_log(tmp_path, events))
        assert result["success"], f"verify failed: {result}"
        assert result["kpi006_liquidation_covered"] is True

    def test_margin_call_caused_by_in_different_transaction_is_rejected(self, tmp_path):
        """Round 10 deeper hop: MARGIN_CALL.caused_by_event_id must resolve
        within the SAME transaction_seq as the MARGIN_CALL.  Uses a
        caused_by_event_id that resolves to a REAL, strictly-earlier event
        (so the log's generic dangling-reference check -- which already
        catches plain dangling references regardless of this deeper
        KPI-006-specific rule -- would NOT by itself catch this; only the
        same-transaction_seq requirement does)."""
        events = [
            self._order_arrival("oa-stale", tx=1, record_index=0),
            self._order_arrival("oa-1", tx=2, record_index=0),
            self._trade_settle("trade-1", tx=2, record_index=1),
            self._margin_call("mc-1", "oa-stale", "trade-1", tx=2, record_index=2),
            self._liquidation_order("liq-1", "mc-1", tx=3),
        ]
        result = verify_log(self._write_log(tmp_path, events))
        assert not result["success"]
        assert result["error"] == "TI-5"
        assert "caused_by_event_id" in result["detail"]

    def test_margin_call_risk_mark_in_different_transaction_is_rejected(self, tmp_path):
        """Round 10 deeper hop: risk_mark_event_id pointing at a real event
        that belongs to a DIFFERENT transaction_seq than the MARGIN_CALL
        itself must be rejected (event-schema.md §5.2: same transaction_seq
        requirement)."""
        events = [
            self._order_arrival("oa-0", tx=1, record_index=0),
            self._trade_settle("trade-stale", tx=1, record_index=1),
            self._order_arrival("oa-1", tx=2, record_index=0),
            self._margin_call("mc-1", "oa-1", "trade-stale", tx=2, record_index=1),
            self._liquidation_order("liq-1", "mc-1", tx=3),
        ]
        result = verify_log(self._write_log(tmp_path, events))
        assert not result["success"]
        assert result["error"] == "TI-5"
        assert "risk_mark_event_id" in result["detail"]


class TestKpi009Regression:
    """§2.9 (T503/KPI-009): PnL bridge residual must be asserted in the same
    independent verification pass as KPI-006/C1/C2, not only inside
    experiment/runner.py's in-process ``_verify_bridge_residuals``
    (round 9 finding: KPI-009 was "two separate code paths", one of which
    -- verify_log -- never checked it at all).
    """

    def test_valid_real_simulation_log_reports_kpi009_ok(self, tmp_path):
        """Positive case: a real matched-trade log (same fixture as
        TestVerify) must report kpi009_bridge_ok True in the same pass as
        the other checks."""
        records = _sim_log()
        log_path = tmp_path / "run.jsonl"
        lines = [json.dumps(r, ensure_ascii=False) for r in records]
        log_path.write_text("\n".join(lines), encoding="utf-8")
        result = verify_log(log_path)
        assert result["success"], f"verify failed: {result}"
        assert result["kpi009_bridge_ok"] is True

    def test_corrupted_posting_fails_kpi009(self, tmp_path):
        """Negative case: corrupt a TRADE_SETTLE's recorded ``price_ticks``
        (as if a tampered/buggy log desynced the trade price from the
        wallet/entry_notional postings that were computed against the real
        price) and confirm verify_log rejects it via KPI-009.  price_ticks
        does not feed C1/C2 (only postings' wallet/position/entry_notional
        deltas do), so this isolates the KPI-009 check -- proving it is
        load-bearing rather than an always-true no-op, and not just
        incidentally caught by the C1/C2 check that runs earlier."""
        records = _sim_log()
        corrupted = False
        for r in records:
            if r.get("record_kind") != "EVENT" or r.get("event_type") != "TRADE_SETTLE":
                continue
            if any(p.get("posting_type") == "TRADE_POSTING" for p in r.get("postings", [])):
                r["price_ticks"] = r.get("price_ticks", 0) + 1000
                corrupted = True
                break
        assert corrupted, "fixture produced no TRADE_POSTING to corrupt"

        log_path = tmp_path / "run.jsonl"
        lines = [json.dumps(r, ensure_ascii=False) for r in records]
        log_path.write_text("\n".join(lines), encoding="utf-8")
        result = verify_log(log_path)
        assert not result["success"]
        assert result["error"] == "TI-5"
        assert "KPI-009" in result["detail"]
