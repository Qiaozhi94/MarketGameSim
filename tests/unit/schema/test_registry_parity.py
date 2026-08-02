"""T204f2: Registry same-source fixture.

[事件 Schema §6.1/§6.2、E-002] 注册表同源夹具

One minimal machine fixture producing all 3 top-level record kinds and
both posting variants.  Asserts registry -> serializer -> E-002 projection
all read the **same declaration**.

Mutation test: change any field's hash classification in the registry;
the projection test must fail.  If it doesn't, the projection has a
separate hand-maintained list and the "single source of truth" is a lie.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from market_game_sim.config.serialization import canonical_serialize
from market_game_sim.eventlog.digest import event_digest, event_hash_input
from market_game_sim.eventlog.writer import build_run_header
from market_game_sim.schema.registry import SchemaRegistry

ROOT = pathlib.Path(__file__).resolve().parents[3]
JSON_PATH = ROOT / "src" / "market_game_sim" / "schema" / "event_fields.json"


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return SchemaRegistry()


def _make_fixture() -> dict:
    """Minimal fixture producing all 3 record kinds + both posting variants."""
    header = build_run_header(
        run_id="f2",
        code_version="v",
        config_hash="h",
        master_seed=1,
        started_at_wall="2026-01-01T00:00:00Z",
        tick_size="0.01",
        min_quantity="0.001",
        cash_unit="0.01",
    )
    trade_event = {
        "record_kind": "EVENT",
        "schema_version": 2,
        "event_id": "e3_1",
        "run_id": "f2",
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
        "postings": [
            {
                "posting_type": "TRADE_POSTING",
                "agent_id": "M",
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
            },
            {
                "posting_type": "TRADE_POSTING",
                "agent_id": "T",
                "role": "TAKER",
                "wallet_delta_units": 5,
                "position_delta_units": 2000,
                "entry_notional_delta_units": 20000000,
                "realized_pnl_delta_units": 0,
                "fee_delta_units": 0,
                "reserved_delta_units": 0,
                "wallet_after_units": 100005,
                "position_after_units": 2000,
                "entry_notional_after_units": 20000000,
                "equity_after_units": 100005,
                "margin_ratio_after_bp": None,
                "risk_pnl_delta_units": 0,
            },
        ],
        "trade_id": "tr1",
        "caused_by_event_id": "e3_0",
    }
    margin_call_event = {
        "record_kind": "EVENT",
        "schema_version": 2,
        "event_id": "e3_2",
        "run_id": "f2",
        "timestamp": 100,
        "transaction_seq": 4,
        "record_index": 2,
        "priority_class": 1,
        "event_type": "MARGIN_CALL",
        "enqueue_seq": None,
        "agent_id": "T",
        "margin_ratio_bp": None,
        "maintenance_bp": 500,
        "verdict": "BREACHED",
        "required_quantity_units": 0,
        "chain_depth": 0,
        "chain_id": "chain1",
        "liquidation_generation_after": 1,
        "postings": [
            {
                "posting_type": "WRITE_OFF_POSTING",
                "role": "ACCOUNT",
                "agent_id": "T",
                "wallet_delta_units": 100,
                "wallet_after_units": 0,
                "position_after_units": 0,
                "entry_notional_after_units": 0,
                "risk_pnl_delta_units": 0,
            },
            {
                "posting_type": "WRITE_OFF_POSTING",
                "role": "EXCHANGE_RISK",
                "agent_id": None,
                "wallet_delta_units": 0,
                "wallet_after_units": None,
                "position_after_units": None,
                "entry_notional_after_units": None,
                "risk_pnl_delta_units": -100,
            },
        ],
        "caused_by_event_id": "e3_0",
        "risk_mark_event_id": "e3_1",
    }
    trailer = {
        "record_kind": "RUN_TRAILER",
        "terminated": "COMPLETED",
        "abort_code": None,
        "abort_detail": None,
        "last_committed_transaction_seq": 4,
        "record_count": 5,
    }
    return {
        "header": header,
        "trade_event": trade_event,
        "margin_call_event": margin_call_event,
        "trailer": trailer,
    }


class TestSameSourceFixture:
    def test_fixture_produces_all_three_record_kinds(self, registry):
        f = _make_fixture()
        assert f["header"]["record_kind"] == "RUN_HEADER"
        assert f["trade_event"]["record_kind"] == "EVENT"
        assert f["trailer"]["record_kind"] == "RUN_TRAILER"

    def test_fixture_has_both_posting_variants(self, registry):
        f = _make_fixture()
        trade_postings = f["trade_event"]["postings"]
        assert all(p["posting_type"] == "TRADE_POSTING" for p in trade_postings)
        write_off_postings = f["margin_call_event"]["postings"]
        assert all(p["posting_type"] == "WRITE_OFF_POSTING" for p in write_off_postings)

    def test_serializer_fields_match_registry(self, registry):
        """Serialization field set comes from the registry."""
        f = _make_fixture()
        header_fields = set(registry.serialization_fields("RUN_HEADER"))
        assert set(f["header"].keys()) == header_fields

        trailer_fields = set(registry.serialization_fields("RUN_TRAILER"))
        assert set(f["trailer"].keys()) == trailer_fields

    def test_event_fields_match_registry(self, registry):
        f = _make_fixture()
        event_fields = set(registry.serialization_fields("EVENT", "TRADE_SETTLE"))
        assert set(f["trade_event"].keys()) == event_fields

    def test_hash_projection_uses_registry(self, registry):
        """E-002 projection reads hash classification from the registry."""
        f = _make_fixture()
        proj = event_hash_input(f["trade_event"], registry)
        # Included fields appear in projection
        assert "price_ticks" in proj
        assert "quantity_units" in proj
        assert "postings" in proj
        # Excluded fields do NOT appear
        assert "event_id" not in proj
        assert "run_id" not in proj
        assert "trade_id" not in proj
        assert "caused_by_event_id" not in proj

    def test_byte_deterministic_serialization(self, registry):
        """Serializer and digest both use canonical encoding."""
        f = _make_fixture()
        bytes1 = canonical_serialize(f["trade_event"])
        bytes2 = canonical_serialize(f["trade_event"])
        assert bytes1 == bytes2

    def test_digest_deterministic(self, registry):
        f = _make_fixture()
        d1 = event_digest(f["trade_event"], registry)
        d2 = event_digest(f["trade_event"], registry)
        assert d1 == d2


class TestMutationBreaksProjection:
    """Mutate any field's hash classification -> projection must change.

    If it doesn't, the projection has a separate hand-maintained list and
    T204f's 'single source of truth' is a lie."""

    @pytest.fixture
    def mutated_registry_factory(self, tmp_path):
        """Factory that creates a SchemaRegistry from a mutated JSON."""
        def _create(structure: str, field: str, new_hash: str) -> SchemaRegistry:
            raw = json.loads(JSON_PATH.read_text(encoding="utf-8"))
            raw["structures"][structure]["fields"][field]["hash"] = new_hash
            tmp_file = tmp_path / f"mutated_{structure}_{field}.json"
            tmp_file.write_text(json.dumps(raw), encoding="utf-8")
            return SchemaRegistry(tmp_file)
        return _create

    def test_mutate_price_ticks_to_exclude_changes_projection(self, mutated_registry_factory):
        normal_reg = SchemaRegistry()
        f = _make_fixture()
        normal_proj = event_hash_input(f["trade_event"], normal_reg)

        mutated_reg = mutated_registry_factory("TRADE_SETTLE", "price_ticks", "HASH_EXCLUDE")
        mutated_proj = event_hash_input(f["trade_event"], mutated_reg)

        assert "price_ticks" in normal_proj
        assert "price_ticks" not in mutated_proj
        assert normal_proj != mutated_proj

    def test_mutate_event_id_to_include_changes_projection(self, mutated_registry_factory):
        normal_reg = SchemaRegistry()
        f = _make_fixture()
        normal_proj = event_hash_input(f["trade_event"], normal_reg)

        mutated_reg = mutated_registry_factory("EVENT_COMMON", "event_id", "HASH_INCLUDE")
        mutated_proj = event_hash_input(f["trade_event"], mutated_reg)

        assert "event_id" not in normal_proj
        assert "event_id" in mutated_proj

    def test_mutate_agent_id_to_exclude_changes_digest(self, mutated_registry_factory):
        normal_reg = SchemaRegistry()
        f = _make_fixture()
        normal_digest = event_digest(f["trade_event"], normal_reg)

        mutated_reg = mutated_registry_factory("TRADE_SETTLE", "maker_agent_id", "HASH_EXCLUDE")
        mutated_digest = event_digest(f["trade_event"], mutated_reg)

        assert normal_digest != mutated_digest

    def test_mutate_postings_to_exclude_changes_projection(self, mutated_registry_factory):
        normal_reg = SchemaRegistry()
        f = _make_fixture()
        normal_proj = event_hash_input(f["trade_event"], normal_reg)

        mutated_reg = mutated_registry_factory("TRADE_SETTLE", "postings", "HASH_EXCLUDE")
        mutated_proj = event_hash_input(f["trade_event"], mutated_reg)

        assert "postings" in normal_proj
        assert "postings" not in mutated_proj
