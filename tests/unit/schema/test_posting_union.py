"""T204g: Posting discriminated union (TRADE_POSTING vs WRITE_OFF_POSTING).

[事件 Schema §4.2.1/§4.2.3] 分录判别联合

TRADE_POSTING (15 leaf fields, role ∈ {MAKER,TAKER}) and WRITE_OFF_POSTING
(8 leaf fields, role ∈ {ACCOUNT,EXCHANGE_RISK}) are two distinct structures,
not optional fields of one structure.  EXCHANGE_RISK side has
wallet_after_units/position_after_units/entry_notional_after_units as null
(NOT 0) -- writing 0 would let the replayer treat exchange risk as a
regular account in C1 sum.
"""

from __future__ import annotations

import pytest

from market_game_sim.eventlog.digest import event_hash_input
from market_game_sim.schema.registry import SchemaRegistry, get_registry


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return get_registry()


class TestPostingUnionStructure:
    def test_trade_posting_leaf_count_is_15(self, registry):
        assert registry.leaf_field_count("TRADE_POSTING") == 15

    def test_write_off_posting_leaf_count_is_8(self, registry):
        assert registry.leaf_field_count("WRITE_OFF_POSTING") == 8

    def test_trade_posting_role_enum_is_maker_taker(self, registry):
        role = registry.get_field("TRADE_POSTING", "role")
        assert role.enum == ("MAKER", "TAKER")

    def test_write_off_posting_role_enum_is_account_exchange_risk(self, registry):
        role = registry.get_field("WRITE_OFF_POSTING", "role")
        assert role.enum == ("ACCOUNT", "EXCHANGE_RISK")

    def test_trade_posting_fields_disjoint_from_write_off(self, registry):
        tp_fields = set(registry.field_names("TRADE_POSTING"))
        wo_fields = set(registry.field_names("WRITE_OFF_POSTING"))
        shared = tp_fields & wo_fields
        assert "posting_type" in shared
        assert "role" in shared
        assert "wallet_delta_units" in shared
        assert "wallet_after_units" in shared
        assert "position_after_units" in shared
        assert "entry_notional_after_units" in shared
        assert "risk_pnl_delta_units" in shared
        # TRADE_POSTING-only fields
        assert "position_delta_units" in tp_fields - wo_fields
        assert "fee_delta_units" in tp_fields - wo_fields
        assert "equity_after_units" in tp_fields - wo_fields
        assert "margin_ratio_after_bp" in tp_fields - wo_fields
        assert "entry_notional_delta_units" in tp_fields - wo_fields
        assert "realized_pnl_delta_units" in tp_fields - wo_fields
        assert "agent_id" in tp_fields - wo_fields or "agent_id" in shared

    def test_trade_posting_agent_id_non_null(self, registry):
        f = registry.get_field("TRADE_POSTING", "agent_id")
        assert f.nullable is False

    def test_write_off_posting_agent_id_nullable(self, registry):
        f = registry.get_field("WRITE_OFF_POSTING", "agent_id")
        assert f.nullable is True


class TestExchangeRiskNullability:
    """EXCHANGE_RISK side: wallet_after/position_after/entry_notional_after = null, NOT 0."""

    def test_wallet_after_units_nullable(self, registry):
        f = registry.get_field("WRITE_OFF_POSTING", "wallet_after_units")
        assert f.nullable is True
        constraints = {c["when"].get("field"): c["then"] for c in f.constraints}
        assert constraints.get("EXCHANGE_RISK") is None or any(
            c["when"].get("equals") == "EXCHANGE_RISK" and c["then"] == "null"
            for c in f.constraints
        )

    def test_position_after_units_nullable(self, registry):
        f = registry.get_field("WRITE_OFF_POSTING", "position_after_units")
        assert f.nullable is True

    def test_entry_notional_after_units_nullable(self, registry):
        f = registry.get_field("WRITE_OFF_POSTING", "entry_notional_after_units")
        assert f.nullable is True

    def test_exchange_risk_constraints_force_null(self, registry):
        """All three *_after fields must have a constraint forcing null for EXCHANGE_RISK."""
        for fname in ("wallet_after_units", "position_after_units", "entry_notional_after_units"):
            f = registry.get_field("WRITE_OFF_POSTING", fname)
            has_null_constraint = any(
                c["when"].get("equals") == "EXCHANGE_RISK" and c["then"] == "null"
                for c in f.constraints
            )
            assert has_null_constraint, (
                f"WRITE_OFF_POSTING.{fname} must constrain EXCHANGE_RISK -> null"
            )


class TestPostingsEmptyVsNonEmpty:
    """verdict != BREACHED -> postings is empty [].  Empty vs non-empty
    must produce different hash inputs."""

    def _margin_call_event(self, verdict: str, postings: list) -> dict:
        return {
            "event_type": "MARGIN_CALL",
            "schema_version": 4,
            "timestamp": 100,
            "transaction_seq": 3,
            "record_index": 1,
            "priority_class": 1,
            "enqueue_seq": None,
            "agent_id": "A",
            "margin_ratio_bp": None,
            "maintenance_bp": 500,
            "verdict": verdict,
            "required_quantity_units": 0,
            "chain_depth": 0,
            "chain_id": None,
            "liquidation_generation_after": 0,
            "postings": postings,
        }

    def test_empty_postings_hash_input(self, registry):
        event = self._margin_call_event("OK", [])
        projection = event_hash_input(event, registry)
        assert projection["postings"] == []

    def test_non_empty_postings_hash_input(self, registry):
        posting = {
            "posting_type": "WRITE_OFF_POSTING",
            "role": "ACCOUNT",
            "agent_id": "A",
            "wallet_delta_units": 100,
            "wallet_after_units": 0,
            "position_after_units": 0,
            "entry_notional_after_units": 0,
            "risk_pnl_delta_units": 0,
        }
        event = self._margin_call_event("BREACHED", [posting])
        projection = event_hash_input(event, registry)
        assert len(projection["postings"]) == 1

    def test_empty_vs_non_empty_different_hash(self, registry):
        empty_event = self._margin_call_event("OK", [])
        posting = {
            "posting_type": "WRITE_OFF_POSTING",
            "role": "ACCOUNT",
            "agent_id": "A",
            "wallet_delta_units": 100,
            "wallet_after_units": 0,
            "position_after_units": 0,
            "entry_notional_after_units": 0,
            "risk_pnl_delta_units": 0,
        }
        non_empty_event = self._margin_call_event("BREACHED", [posting])
        from market_game_sim.eventlog.digest import event_digest

        assert event_digest(empty_event, registry) != event_digest(non_empty_event, registry)

    def test_postings_field_is_hash_include(self, registry):
        f = registry.get_field("MARGIN_CALL", "postings")
        assert f.hash_class == "HASH_INCLUDE"
