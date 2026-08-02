"""T204f4: Constraint positive/negative fixtures.

[事件 Schema E-002] constraint 正反夹具

For each of 7 cases (SUBMIT/CANCEL/AGENT/LIQUIDATION/OK/PENDING_LIQUIDATION/BREACHED),
provide a valid record and an invalid record, assert the validator accepts
the valid and rejects the invalid.
"""

from __future__ import annotations

import pytest

from market_game_sim.schema.constraints import validate_record
from market_game_sim.schema.registry import get_registry


@pytest.fixture(scope="module")
def registry():
    return get_registry()


def _order_arrival(**kw) -> dict:
    base = {
        "event_type": "ORDER_ARRIVAL",
        "enqueue_seq": 2,
        "action": "SUBMIT",
        "target_order_id": None,
        "side": "BUY",
        "order_type": "LIMIT",
        "price_ticks": 10000,
        "quantity_units": 5000,
        "accepted": True,
        "reject_reason": None,
        "reserved_delta_units": 0,
        "origin": "AGENT",
        "trigger_ratio_bp": None,
        "liquidation_generation": None,
        "intent_id": "i1",
        "decision_event_id": "d1",
        "submitted_at": 99,
    }
    base.update(kw)
    return base


def _margin_call(**kw) -> dict:
    base = {
        "event_type": "MARGIN_CALL",
        "enqueue_seq": None,
        "agent_id": "A",
        "margin_ratio_bp": None,
        "maintenance_bp": 500,
        "verdict": "OK",
        "required_quantity_units": 0,
        "chain_depth": 0,
        "chain_id": None,
        "liquidation_generation_after": 0,
        "postings": [],
        "caused_by_event_id": "e1",
        "risk_mark_event_id": "e2",
    }
    base.update(kw)
    return base


def _write_off_posting(role: str) -> dict:
    return {
        "posting_type": "WRITE_OFF_POSTING",
        "role": role,
        "agent_id": "A" if role == "ACCOUNT" else None,
        "wallet_delta_units": 100,
        "wallet_after_units": 0 if role == "ACCOUNT" else None,
        "position_after_units": 0 if role == "ACCOUNT" else None,
        "entry_notional_after_units": 0 if role == "ACCOUNT" else None,
        "risk_pnl_delta_units": 0,
    }


class TestSubmitFixture:
    def test_valid_submit_accepted(self, registry):
        r = _order_arrival()
        assert validate_record(r, registry) == []

    def test_invalid_submit_side_null(self, registry):
        r = _order_arrival(side=None)
        errors = validate_record(r, registry)
        assert any("side" in e and "non-null" in e for e in errors)

    def test_invalid_submit_target_order_id_non_null(self, registry):
        r = _order_arrival(target_order_id="o1")
        errors = validate_record(r, registry)
        assert any("target_order_id" in e and "null" in e for e in errors)


class TestCancelFixture:
    def test_valid_cancel(self, registry):
        r = _order_arrival(
            action="CANCEL",
            target_order_id="o1",
            side=None,
            order_type=None,
            price_ticks=None,
            quantity_units=None,
        )
        assert validate_record(r, registry) == []

    def test_invalid_cancel_target_order_id_null(self, registry):
        r = _order_arrival(
            action="CANCEL",
            target_order_id=None,
            side=None,
            order_type=None,
            price_ticks=None,
            quantity_units=None,
        )
        errors = validate_record(r, registry)
        assert any("target_order_id" in e and "non-null" in e for e in errors)

    def test_invalid_cancel_side_non_null(self, registry):
        r = _order_arrival(
            action="CANCEL",
            target_order_id="o1",
            side="BUY",
            order_type=None,
            price_ticks=None,
            quantity_units=None,
        )
        errors = validate_record(r, registry)
        assert any("side" in e and "null" in e for e in errors)


class TestAgentFixture:
    def test_valid_agent(self, registry):
        r = _order_arrival(origin="AGENT", intent_id="i1", trigger_ratio_bp=None,
                           liquidation_generation=None)
        assert validate_record(r, registry) == []

    def test_invalid_agent_intent_id_null(self, registry):
        r = _order_arrival(origin="AGENT", intent_id=None, trigger_ratio_bp=None,
                           liquidation_generation=None)
        errors = validate_record(r, registry)
        assert any("intent_id" in e and "non-null" in e for e in errors)

    def test_invalid_agent_trigger_ratio_bp_non_null(self, registry):
        r = _order_arrival(origin="AGENT", intent_id="i1", trigger_ratio_bp=5000,
                           liquidation_generation=None)
        errors = validate_record(r, registry)
        assert any("trigger_ratio_bp" in e and "null" in e for e in errors)


class TestLiquidationFixture:
    def test_valid_liquidation(self, registry):
        r = _order_arrival(
            origin="LIQUIDATION",
            trigger_ratio_bp=5000,
            liquidation_generation=1,
            intent_id=None,
        )
        assert validate_record(r, registry) == []

    def test_invalid_liquidation_trigger_ratio_bp_null(self, registry):
        r = _order_arrival(
            origin="LIQUIDATION",
            trigger_ratio_bp=None,
            liquidation_generation=1,
            intent_id=None,
        )
        errors = validate_record(r, registry)
        assert any("trigger_ratio_bp" in e and "non-null" in e for e in errors)

    def test_invalid_liquidation_intent_id_non_null(self, registry):
        r = _order_arrival(
            origin="LIQUIDATION",
            trigger_ratio_bp=5000,
            liquidation_generation=1,
            intent_id="i1",
        )
        errors = validate_record(r, registry)
        assert any("intent_id" in e and "null" in e for e in errors)


class TestOKFixture:
    def test_valid_ok(self, registry):
        r = _margin_call(verdict="OK", chain_id=None, postings=[])
        assert validate_record(r, registry) == []

    def test_invalid_ok_chain_id_non_null(self, registry):
        r = _margin_call(verdict="OK", chain_id="chain1", postings=[])
        errors = validate_record(r, registry)
        assert any("chain_id" in e and "null" in e for e in errors)

    def test_invalid_ok_postings_non_empty(self, registry):
        r = _margin_call(verdict="OK", chain_id=None, postings=[_write_off_posting("ACCOUNT")])
        errors = validate_record(r, registry)
        assert any("postings" in e and "length" in e for e in errors)


class TestPendingLiquidationFixture:
    def test_valid_pending(self, registry):
        r = _margin_call(verdict="PENDING_LIQUIDATION", chain_id="chain1", postings=[])
        assert validate_record(r, registry) == []

    def test_invalid_pending_chain_id_null(self, registry):
        r = _margin_call(verdict="PENDING_LIQUIDATION", chain_id=None, postings=[])
        errors = validate_record(r, registry)
        assert any("chain_id" in e and "non-null" in e for e in errors)

    def test_invalid_pending_postings_non_empty(self, registry):
        r = _margin_call(
            verdict="PENDING_LIQUIDATION", chain_id="chain1",
            postings=[_write_off_posting("ACCOUNT"), _write_off_posting("EXCHANGE_RISK")],
        )
        errors = validate_record(r, registry)
        assert any("postings" in e and "length" in e for e in errors)


class TestBreachedFixture:
    def test_valid_breached(self, registry):
        r = _margin_call(
            verdict="BREACHED",
            chain_id="chain1",
            postings=[_write_off_posting("ACCOUNT"), _write_off_posting("EXCHANGE_RISK")],
        )
        assert validate_record(r, registry) == []

    def test_invalid_breached_postings_empty(self, registry):
        r = _margin_call(verdict="BREACHED", chain_id="chain1", postings=[])
        errors = validate_record(r, registry)
        assert any("postings" in e and "length" in e for e in errors)

    def test_invalid_breached_chain_id_null(self, registry):
        r = _margin_call(
            verdict="BREACHED",
            chain_id=None,
            postings=[_write_off_posting("ACCOUNT"), _write_off_posting("EXCHANGE_RISK")],
        )
        errors = validate_record(r, registry)
        assert any("chain_id" in e and "non-null" in e for e in errors)

    def test_invalid_breached_postings_length_1(self, registry):
        r = _margin_call(
            verdict="BREACHED",
            chain_id="chain1",
            postings=[_write_off_posting("ACCOUNT")],
        )
        errors = validate_record(r, registry)
        assert any("postings" in e and "length" in e for e in errors)


class TestWriteOffPostingRoleConstraints:
    def test_valid_account_role(self, registry):
        r = _margin_call(
            verdict="BREACHED",
            chain_id="chain1",
            postings=[_write_off_posting("ACCOUNT"), _write_off_posting("EXCHANGE_RISK")],
        )
        assert validate_record(r, registry) == []

    def test_invalid_exchange_risk_agent_id_non_null(self, registry):
        p = _write_off_posting("EXCHANGE_RISK")
        p["agent_id"] = "should_be_null"
        r = _margin_call(verdict="BREACHED", chain_id="chain1",
                         postings=[_write_off_posting("ACCOUNT"), p])
        errors = validate_record(r, registry)
        assert any("agent_id" in e and "null" in e for e in errors)

    def test_invalid_exchange_risk_wallet_after_non_null(self, registry):
        p = _write_off_posting("EXCHANGE_RISK")
        p["wallet_after_units"] = 0
        r = _margin_call(verdict="BREACHED", chain_id="chain1",
                         postings=[_write_off_posting("ACCOUNT"), p])
        errors = validate_record(r, registry)
        assert any("wallet_after_units" in e and "null" in e for e in errors)
