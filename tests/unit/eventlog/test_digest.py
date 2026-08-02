"""T206 / T206b: Event digest hash (KPI-002).

[事件 Schema §7, E-002] 事件摘要哈希
[事件 Schema E-002] 哈希字段覆盖检查

T206: blake2b digest over E-002 hash projection (HASH_INCLUDE fields only).
T206b: check_coverage for all 8 event types -- required == include ∪ exclude, disjoint.
"""

from __future__ import annotations

import pytest

from market_game_sim.eventlog.digest import (
    event_digest,
    event_digest_hex,
    event_hash_input,
    rolling_digest,
    rolling_digest_hex,
)
from market_game_sim.schema.registry import EVENT_TYPES, SchemaRegistry, get_registry


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return get_registry()


def _order_arrival_event(**overrides) -> dict:
    base = {
        "record_kind": "EVENT",
        "schema_version": 2,
        "event_id": "e1_0",
        "run_id": "r",
        "timestamp": 100,
        "transaction_seq": 3,
        "record_index": 0,
        "priority_class": 0,
        "event_type": "ORDER_ARRIVAL",
        "enqueue_seq": 2,
        "agent_id": "A",
        "order_id": "o1",
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
        "decision_event_id": "e0_0",
        "submitted_at": 99,
    }
    base.update(overrides)
    return base


class TestEventDigest:
    def test_digest_is_blake2b_32_bytes(self, registry):
        event = _order_arrival_event()
        d = event_digest(event, registry)
        assert len(d) == 32

    def test_digest_deterministic(self, registry):
        event = _order_arrival_event()
        assert event_digest(event, registry) == event_digest(event, registry)

    def test_hex_digest(self, registry):
        event = _order_arrival_event()
        assert event_digest_hex(event, registry) == event_digest(event, registry).hex()

    def test_excluded_field_does_not_affect_digest(self, registry):
        """event_id is HASH_EXCLUDE -- changing it must not change the digest."""
        e1 = _order_arrival_event(event_id="e1_0")
        e2 = _order_arrival_event(event_id="e2_0")
        assert event_digest(e1, registry) == event_digest(e2, registry)

    def test_run_id_excluded(self, registry):
        e1 = _order_arrival_event(run_id="r1")
        e2 = _order_arrival_event(run_id="r2")
        assert event_digest(e1, registry) == event_digest(e2, registry)

    def test_intent_id_excluded(self, registry):
        e1 = _order_arrival_event(intent_id="i1")
        e2 = _order_arrival_event(intent_id="i2")
        assert event_digest(e1, registry) == event_digest(e2, registry)

    def test_decision_event_id_excluded(self, registry):
        e1 = _order_arrival_event(decision_event_id="d1")
        e2 = _order_arrival_event(decision_event_id="d2")
        assert event_digest(e1, registry) == event_digest(e2, registry)

    def test_submitted_at_excluded(self, registry):
        e1 = _order_arrival_event(submitted_at=99)
        e2 = _order_arrival_event(submitted_at=200)
        assert event_digest(e1, registry) == event_digest(e2, registry)

    def test_record_kind_excluded(self, registry):
        e1 = _order_arrival_event()
        e2 = _order_arrival_event()
        e2["record_kind"] = "OTHER"
        assert event_digest(e1, registry) == event_digest(e2, registry)

    def test_included_field_affects_digest(self, registry):
        e1 = _order_arrival_event(price_ticks=10000)
        e2 = _order_arrival_event(price_ticks=10100)
        assert event_digest(e1, registry) != event_digest(e2, registry)

    def test_quantity_affects_digest(self, registry):
        e1 = _order_arrival_event(quantity_units=5000)
        e2 = _order_arrival_event(quantity_units=6000)
        assert event_digest(e1, registry) != event_digest(e2, registry)

    def test_timestamp_affects_digest(self, registry):
        e1 = _order_arrival_event(timestamp=100)
        e2 = _order_arrival_event(timestamp=200)
        assert event_digest(e1, registry) != event_digest(e2, registry)

    def test_schema_version_affects_digest(self, registry):
        e1 = _order_arrival_event(schema_version=2)
        e2 = _order_arrival_event(schema_version=3)
        assert event_digest(e1, registry) != event_digest(e2, registry)

    def test_enqueue_seq_affects_digest(self, registry):
        e1 = _order_arrival_event(enqueue_seq=2)
        e2 = _order_arrival_event(enqueue_seq=3)
        assert event_digest(e1, registry) != event_digest(e2, registry)


class TestRollingDigest:
    def test_rolling_deterministic(self, registry):
        events = [_order_arrival_event(), _order_arrival_event(transaction_seq=4)]
        assert rolling_digest(events, registry) == rolling_digest(events, registry)

    def test_rolling_order_matters(self, registry):
        e1 = _order_arrival_event(timestamp=100, transaction_seq=3)
        e2 = _order_arrival_event(timestamp=200, transaction_seq=4)
        assert rolling_digest([e1, e2], registry) != rolling_digest([e2, e1], registry)

    def test_rolling_hex(self, registry):
        events = [_order_arrival_event()]
        assert rolling_digest_hex(events, registry) == rolling_digest(events, registry).hex()

    def test_empty_events(self, registry):
        d = rolling_digest([], registry)
        assert len(d) == 32


class TestHashProjection:
    def test_projection_excludes_event_id(self, registry):
        event = _order_arrival_event()
        proj = event_hash_input(event, registry)
        assert "event_id" not in proj

    def test_projection_excludes_run_id(self, registry):
        event = _order_arrival_event()
        proj = event_hash_input(event, registry)
        assert "run_id" not in proj

    def test_projection_includes_price_ticks(self, registry):
        event = _order_arrival_event()
        proj = event_hash_input(event, registry)
        assert proj["price_ticks"] == 10000

    def test_projection_includes_schema_version(self, registry):
        event = _order_arrival_event()
        proj = event_hash_input(event, registry)
        assert proj["schema_version"] == 2


class TestPostingsHashProjection:
    def _trade_settle_event(self, postings: list) -> dict:
        return {
            "record_kind": "EVENT",
            "schema_version": 2,
            "event_id": "e3_1",
            "run_id": "r",
            "timestamp": 100,
            "transaction_seq": 3,
            "record_index": 1,
            "priority_class": 1,
            "event_type": "TRADE_SETTLE",
            "enqueue_seq": None,
            "maker_order_id": "m1",
            "taker_order_id": "t1",
            "maker_agent_id": "M",
            "taker_agent_id": "T",
            "price_ticks": 10000,
            "quantity_units": 2000,
            "notional_cash_units": 20000000,
            "maker_fee_cash_units": 0,
            "taker_fee_cash_units": 0,
            "valuation_mark_before_half_ticks": 20000,
            "valuation_mark_after_half_ticks": 20000,
            "risk_mark_ticks": 10000,
            "fill_index": 0,
            "fill_count": 1,
            "postings": postings,
            "trade_id": "tr1",
            "caused_by_event_id": "e3_0",
        }

    def _trade_posting(self, **overrides) -> dict:
        base = {
            "posting_type": "TRADE_POSTING",
            "agent_id": "A",
            "role": "MAKER",
            "wallet_delta_units": -5,
            "position_delta_units": 0,
            "entry_notional_delta_units": 0,
            "realized_pnl_delta_units": 0,
            "fee_delta_units": 0,
            "reserved_delta_units": 0,
            "wallet_after_units": 99995,
            "position_after_units": 0,
            "entry_notional_after_units": 0,
            "equity_after_units": 99995,
            "margin_ratio_after_bp": None,
            "risk_pnl_delta_units": 0,
        }
        base.update(overrides)
        return base

    def test_postings_included_in_projection(self, registry):
        event = self._trade_settle_event([self._trade_posting(), self._trade_posting(role="TAKER")])
        proj = event_hash_input(event, registry)
        assert "postings" in proj
        assert len(proj["postings"]) == 2

    def test_posting_wallet_delta_included(self, registry):
        p1 = self._trade_posting(wallet_delta_units=-5)
        p2 = self._trade_posting(wallet_delta_units=-10)
        e1 = self._trade_settle_event([p1, self._trade_posting(role="TAKER")])
        e2 = self._trade_settle_event([p2, self._trade_posting(role="TAKER")])
        assert event_digest(e1, registry) != event_digest(e2, registry)

    def test_trade_id_excluded(self, registry):
        e1 = self._trade_settle_event([self._trade_posting()])
        e2 = self._trade_settle_event([self._trade_posting()])
        e2["trade_id"] = "different"
        assert event_digest(e1, registry) == event_digest(e2, registry)

    def test_caused_by_event_id_excluded(self, registry):
        e1 = self._trade_settle_event([self._trade_posting()])
        e2 = self._trade_settle_event([self._trade_posting()])
        e2["caused_by_event_id"] = "different"
        assert event_digest(e1, registry) == event_digest(e2, registry)

    def test_fill_count_included(self, registry):
        e1 = self._trade_settle_event([self._trade_posting()])
        e2 = self._trade_settle_event([self._trade_posting()])
        e2["fill_count"] = 2
        assert event_digest(e1, registry) != event_digest(e2, registry)


# --------------------------------------------------------------------------- #
# T206b: hash coverage check
# --------------------------------------------------------------------------- #


class TestHashCoverage:
    """For each event type: required == include ∪ exclude, disjoint."""

    @pytest.mark.parametrize("event_type", sorted(EVENT_TYPES))
    def test_coverage_no_missing_no_ambiguous(self, event_type, registry):
        result = registry.check_coverage(event_type)
        assert not result["missing"], (
            f"{event_type}: fields in neither include nor exclude: {result['missing']}"
        )
        assert not result["ambiguous"], (
            f"{event_type}: fields in both include and exclude: {result['ambiguous']}"
        )

    @pytest.mark.parametrize("event_type", sorted(EVENT_TYPES))
    def test_include_exclude_disjoint(self, event_type, registry):
        result = registry.check_coverage(event_type)
        assert result["include"].isdisjoint(result["exclude"])

    @pytest.mark.parametrize("event_type", sorted(EVENT_TYPES))
    def test_union_equals_required(self, event_type, registry):
        result = registry.check_coverage(event_type)
        assert result["include"] | result["exclude"] == result["required"]

    def test_event_common_coverage(self, registry):
        result = registry.check_coverage("EVENT_COMMON")
        assert not result["missing"]
        assert not result["ambiguous"]

    def test_trade_posting_coverage(self, registry):
        result = registry.check_coverage("TRADE_POSTING")
        assert not result["missing"]
        assert not result["ambiguous"]

    def test_write_off_posting_coverage(self, registry):
        result = registry.check_coverage("WRITE_OFF_POSTING")
        assert not result["missing"]
        assert not result["ambiguous"]

    def test_empty_vs_nonempty_postings_different_hash_input(self, registry):
        """Empty postings array must produce different hash input than non-empty."""
        empty_event = {
            "event_type": "MARGIN_CALL",
            "schema_version": 2,
            "timestamp": 100,
            "transaction_seq": 3,
            "record_index": 1,
            "priority_class": 1,
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
        }
        non_empty_event = dict(empty_event)
        non_empty_event["postings"] = [
            {
                "posting_type": "WRITE_OFF_POSTING",
                "role": "ACCOUNT",
                "agent_id": "A",
                "wallet_delta_units": 100,
                "wallet_after_units": 0,
                "position_after_units": 0,
                "entry_notional_after_units": 0,
                "risk_pnl_delta_units": 0,
            }
        ]
        proj_empty = event_hash_input(empty_event, registry)
        proj_non_empty = event_hash_input(non_empty_event, registry)
        assert proj_empty["postings"] != proj_non_empty["postings"]
        assert event_digest(empty_event, registry) != event_digest(non_empty_event, registry)
