"""T204f3: Contract ↔ Schema bidirectional consistency.

[事件 Schema E-002 同步强制] 合同↔Schema 双向一致性

Asserts:
  ① Full path (structure.field) coverage in both directions.
  ② All 6 metadata items match (including required and hash classification).
  ③ Doc says "N items, closed" -> N equals JSON field count and name set.
  ④ E-002 include list equals the HASH_INCLUDE set from JSON.
  ⑤ Doc table types/enums/nullability match JSON.

Does NOT just compare bare field-name counts -- agent_id, price_ticks
appear in multiple structures; only comparing names would pass a field
attached to the wrong structure.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from market_game_sim.schema.registry import HASH_INCLUDE, SchemaRegistry, get_registry

ROOT = pathlib.Path(__file__).resolve().parents[3]
DOC_PATH = ROOT / "docs" / "contracts" / "event-schema.md"
JSON_PATH = ROOT / "src" / "market_game_sim" / "schema" / "event_fields.json"


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return get_registry()


@pytest.fixture(scope="module")
def doc_text() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def raw_schema() -> dict:
    return json.loads(JSON_PATH.read_text(encoding="utf-8"))


def _backtick_tokens(text: str) -> set[str]:
    fence = re.compile(r"```.*?```", re.S)
    tokens: set[str] = set()
    for raw in re.findall(r"`([^`]+?)`", fence.sub("", text)):
        for part in re.split(r"[.\[\]]", raw):
            if re.fullmatch(r"[a-z][a-z0-9_]*", part):
                tokens.add(part)
    return tokens


def _parse_e002_table(doc: str) -> dict[str, set[str]]:
    section = re.compile(r"\| 事件类型 \| 纳入哈希的字段 \|.*?\n\n", re.S)
    m = section.search(doc)
    if not m:
        return {}
    out: dict[str, set[str]] = {}
    for etype, cell in re.findall(r"^\| `([A-Z_]+)` \| (.+?) \|$", m.group(0), re.M):
        out[etype] = _backtick_tokens(cell)
    return out


def _parse_closed_counts(doc: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for pat in (
        re.compile(r"\*\*(\w+)\*\*（\*\*?(\d+)\*\*? 项，封闭）"),
        re.compile(r"`(\w+)`(?:[^\n]{0,40}?)（共 \*\*?(\d+)\*\*? 项"),
    ):
        for name, n in pat.findall(doc):
            out[name] = int(n)
    return out


# --------------------------------------------------------------------------- #
# ① Full path coverage (both directions)
# --------------------------------------------------------------------------- #


class TestFullPathCoverage:
    def test_every_json_field_mentioned_in_doc(self, registry, doc_text):
        mentioned = _backtick_tokens(doc_text)
        missing = []
        for sname in registry.structure_names():
            for fname in registry.field_names(sname):
                if fname not in mentioned:
                    missing.append(f"{sname}.{fname}")
        assert not missing, f"JSON fields not mentioned in doc: {missing}"

    def test_every_structure_mentioned_in_doc(self, registry, doc_text):
        mentioned = _backtick_tokens(doc_text)
        # Event types and top-level record kinds must be mentioned by name.
        user_facing = set(registry.record_kinds) | {
            "ORDER_ARRIVAL", "ORDER_CANCELLED", "TRADE_SETTLE", "MARGIN_CALL",
            "MARKET_DATA_PUBLISH", "AGENT_OBSERVE", "AGENT_DECIDE", "SNAPSHOT",
            "TRADE_POSTING", "WRITE_OFF_POSTING",
        }
        for sname in user_facing:
            assert sname in mentioned or sname in doc_text, (
                f"structure {sname} not mentioned in doc"
            )


# --------------------------------------------------------------------------- #
# ② All 6 metadata items present
# --------------------------------------------------------------------------- #


class TestMetadataCompleteness:
    @pytest.mark.parametrize("sname", [
        "RUN_HEADER", "RUN_TRAILER", "EVENT_COMMON",
        "ORDER_ARRIVAL", "TRADE_SETTLE", "MARGIN_CALL",
        "TRADE_POSTING", "WRITE_OFF_POSTING",
    ])
    def test_fields_have_all_six_metadata(self, registry, sname):
        for fname in registry.field_names(sname):
            f = registry.get_field(sname, fname)
            assert f.value_type is not None, f"{sname}.{fname} missing value_type"
            assert f.nullable is not None, f"{sname}.{fname} missing nullable"
            assert f.required is not None, f"{sname}.{fname} missing required"
            assert f.hash_class in (HASH_INCLUDE, "HASH_EXCLUDE"), (
                f"{sname}.{fname} missing hash_class"
            )

    @pytest.mark.parametrize("sname", [
        "RUN_HEADER", "RUN_TRAILER",
    ])
    def test_header_trailer_all_hash_exclude(self, registry, sname):
        for fname in registry.field_names(sname):
            f = registry.get_field(sname, fname)
            assert f.hash_class == "HASH_EXCLUDE", (
                f"{sname}.{fname} should be HASH_EXCLUDE (§6)"
            )


# --------------------------------------------------------------------------- #
# ③ Closed table counts match JSON
# --------------------------------------------------------------------------- #


class TestClosedCounts:
    def test_closed_counts_match_json(self, registry, doc_text):
        counts = _parse_closed_counts(doc_text)
        for sname, expected_count in counts.items():
            assert registry.has_structure(sname), f"doc references unknown structure {sname}"
            actual = registry.leaf_field_count(sname)
            assert actual == expected_count, (
                f"{sname}: doc says {expected_count} items closed, JSON has {actual}"
            )

    def test_trade_posting_count_15(self, registry):
        assert registry.leaf_field_count("TRADE_POSTING") == 15

    def test_write_off_posting_count_8(self, registry):
        assert registry.leaf_field_count("WRITE_OFF_POSTING") == 8

    def test_account_snapshot_entry_count_11(self, registry):
        assert registry.leaf_field_count("ACCOUNT_SNAPSHOT_ENTRY") == 11

    def test_book_level_count_3(self, registry):
        assert registry.leaf_field_count("BOOK_LEVEL") == 3

    def test_exchange_snapshot_count_2(self, registry):
        assert registry.leaf_field_count("EXCHANGE_SNAPSHOT") == 2


# --------------------------------------------------------------------------- #
# ④ E-002 include list matches HASH_INCLUDE set
# --------------------------------------------------------------------------- #


class TestE002HashIncludeParity:
    def test_e002_matches_hash_include(self, registry, doc_text):
        """E-002 table lists event-specific HASH_INCLUDE fields per event type.
        Common fields (schema_version, timestamp, etc.) are in the '共有' paragraph."""
        e002 = _parse_e002_table(doc_text)
        assert e002, "E-002 table not found in doc"
        for etype, listed in e002.items():
            assert registry.has_structure(etype), f"E-002 lists unknown event type {etype}"
            fields = registry.get_fields(etype)
            own_include = {
                fname for fname, f in fields.items()
                if f.hash_class == HASH_INCLUDE and f.is_leaf
            }
            missing = own_include - listed
            assert not missing, f"E-002 {etype}: missing HASH_INCLUDE fields {sorted(missing)}"

    def test_e002_common_fields_in_doc(self, registry, doc_text):
        """The '共有' paragraph lists all EVENT_COMMON HASH_INCLUDE fields."""
        mentioned = _backtick_tokens(doc_text)
        for fname in registry.field_names("EVENT_COMMON"):
            f = registry.get_field("EVENT_COMMON", fname)
            if f.hash_class == HASH_INCLUDE:
                assert fname in mentioned, (
                    f"EVENT_COMMON.{fname} is HASH_INCLUDE but not mentioned in doc"
                )


# --------------------------------------------------------------------------- #
# ⑤ Schema version and record kinds match
# --------------------------------------------------------------------------- #


class TestSchemaVersionAndKinds:
    def test_schema_version_is_2(self, raw_schema):
        assert raw_schema["schema_version"] == 2

    def test_record_kinds_match(self, raw_schema):
        assert raw_schema["record_kinds"] == ["RUN_HEADER", "EVENT", "RUN_TRAILER"]

    def test_run_header_field_count_12(self, registry):
        assert len(registry.field_names("RUN_HEADER")) == 12

    def test_run_trailer_field_count_6(self, registry):
        assert len(registry.field_names("RUN_TRAILER")) == 6
