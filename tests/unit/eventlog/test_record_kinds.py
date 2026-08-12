"""T204e: Three discriminated record kinds (RUN_HEADER | EVENT | RUN_TRAILER).

[事件 Schema §6.1] RUN_HEADER -- tick_size/min_quantity/cash_unit as string decimals
[事件 Schema §6.2] RUN_TRAILER -- terminated, abort_code, abort_detail,
    last_committed_transaction_seq, record_count

Byte-exact trailer vectors for both termination states (COMPLETED + ABORTED).
"""

from __future__ import annotations

import pytest

from market_game_sim.config.serialization import canonical_serialize
from market_game_sim.eventlog.writer import build_run_header
from market_game_sim.schema.registry import get_registry


class TestRecordKinds:
    def test_three_record_kinds_declared(self):
        reg = get_registry()
        assert reg.record_kinds == ("RUN_HEADER", "EVENT", "RUN_TRAILER")

    def test_run_header_has_record_kind_field(self):
        reg = get_registry()
        f = reg.get_field("RUN_HEADER", "record_kind")
        assert f.enum == ("RUN_HEADER",)

    def test_run_trailer_has_record_kind_field(self):
        reg = get_registry()
        f = reg.get_field("RUN_TRAILER", "record_kind")
        assert f.enum == ("RUN_TRAILER",)

    def test_event_common_has_record_kind_field(self):
        reg = get_registry()
        f = reg.get_field("EVENT_COMMON", "record_kind")
        assert f.enum == ("EVENT",)


class TestRunHeaderFields:
    def test_tick_size_is_string_not_float(self):
        reg = get_registry()
        f = reg.get_field("RUN_HEADER", "tick_size")
        assert f.value_type == "str"

    def test_min_quantity_is_string(self):
        reg = get_registry()
        f = reg.get_field("RUN_HEADER", "min_quantity")
        assert f.value_type == "str"

    def test_cash_unit_is_string(self):
        reg = get_registry()
        f = reg.get_field("RUN_HEADER", "cash_unit")
        assert f.value_type == "str"

    def test_all_header_fields_hash_exclude(self):
        reg = get_registry()
        for fname in reg.field_names("RUN_HEADER"):
            f = reg.get_field("RUN_HEADER", fname)
            assert f.hash_class == "HASH_EXCLUDE", f"RUN_HEADER.{fname} must be HASH_EXCLUDE"

    def test_header_has_16_fields(self):
        reg = get_registry()
        assert len(reg.field_names("RUN_HEADER")) == 16

    def test_build_run_header_rejects_float_tick_size(self):
        with pytest.raises(TypeError, match="string decimals"):
            build_run_header(
                run_id="r",
                code_version="v",
                config_hash="h",
                master_seed=1,
                started_at_wall="2026-01-01T00:00:00Z",
                tick_size=0.01,  # type: ignore[arg-type]
                min_quantity="0.001",
                cash_unit="0.01",
                mult=1000,
                fee_bps_cap=0,
                initial_price_ticks=10000,
                agent_initial_bp={},
            )


class TestRunTrailerFields:
    def test_trailer_has_6_fields(self):
        reg = get_registry()
        assert len(reg.field_names("RUN_TRAILER")) == 6

    def test_trailer_fields(self):
        reg = get_registry()
        expected = {
            "record_kind",
            "terminated",
            "abort_code",
            "abort_detail",
            "last_committed_transaction_seq",
            "record_count",
        }
        assert set(reg.field_names("RUN_TRAILER")) == expected

    def test_terminated_enum(self):
        reg = get_registry()
        f = reg.get_field("RUN_TRAILER", "terminated")
        assert f.enum == ("COMPLETED", "ABORTED")

    def test_abort_code_enum(self):
        reg = get_registry()
        f = reg.get_field("RUN_TRAILER", "abort_code")
        assert f.nullable is True

    def test_abort_code_nullable(self):
        reg = get_registry()
        f = reg.get_field("RUN_TRAILER", "abort_code")
        assert f.nullable is True

    def test_abort_detail_nullable(self):
        reg = get_registry()
        f = reg.get_field("RUN_TRAILER", "abort_detail")
        assert f.nullable is True

    def test_last_committed_transaction_seq_nullable(self):
        reg = get_registry()
        f = reg.get_field("RUN_TRAILER", "last_committed_transaction_seq")
        assert f.nullable is True

    def test_record_count_non_null(self):
        reg = get_registry()
        f = reg.get_field("RUN_TRAILER", "record_count")
        assert f.nullable is False

    def test_all_trailer_fields_hash_exclude(self):
        reg = get_registry()
        for fname in reg.field_names("RUN_TRAILER"):
            f = reg.get_field("RUN_TRAILER", fname)
            assert f.hash_class == "HASH_EXCLUDE"


class TestByteExactTrailerVectors:
    """§6.2: must have byte-exact trailer vectors for both termination states."""

    def test_completed_trailer_bytes(self):
        trailer = {
            "record_kind": "RUN_TRAILER",
            "terminated": "COMPLETED",
            "abort_code": None,
            "abort_detail": None,
            "last_committed_transaction_seq": 2,
            "record_count": 4,
        }
        expected = (
            b'{"abort_code":null,"abort_detail":null,'
            b'"last_committed_transaction_seq":2,'
            b'"record_count":4,'
            b'"record_kind":"RUN_TRAILER",'
            b'"terminated":"COMPLETED"}'
        )
        assert canonical_serialize(trailer) == expected

    def test_aborted_trailer_bytes(self):
        trailer = {
            "record_kind": "RUN_TRAILER",
            "terminated": "ABORTED",
            "abort_code": "INTERNAL",
            "abort_detail": "injected fault",
            "last_committed_transaction_seq": 1,
            "record_count": 3,
        }
        expected = (
            b'{"abort_code":"INTERNAL",'
            b'"abort_detail":"injected fault",'
            b'"last_committed_transaction_seq":1,'
            b'"record_count":3,'
            b'"record_kind":"RUN_TRAILER",'
            b'"terminated":"ABORTED"}'
        )
        assert canonical_serialize(trailer) == expected

    def test_trailer_byte_deterministic(self):
        trailer = {
            "record_kind": "RUN_TRAILER",
            "terminated": "COMPLETED",
            "abort_code": None,
            "abort_detail": None,
            "last_committed_transaction_seq": 5,
            "record_count": 10,
        }
        first = canonical_serialize(trailer)
        second = canonical_serialize(trailer)
        assert first == second
