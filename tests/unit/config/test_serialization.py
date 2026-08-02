"""T104 tests: canonical JSONL serialization (ADR-001 §7).

Verifies byte-deterministic serialization:
  - Integer literals as JSON integers (not strings, not floats)
  - Missing values as null (not NaN, Infinity, empty string)
  - UTF-8 encoding, NFC normalization, ensure_ascii=false
  - Keys sorted by codepoint, separators=(",", ":")
  - One LF per event, no CRLF, no trailing whitespace
  - Two serializations of the same object are byte-identical
"""

from __future__ import annotations

import json

import pytest

from market_game_sim.config.serialization import (
    SerializationError,
    canonical_serialize,
    serialize_event,
    serialize_events,
)

# --------------------------------------------------------------------------- #
# Integer literals
# --------------------------------------------------------------------------- #


class TestIntegerLiterals:
    def test_positive_int(self):
        assert canonical_serialize({"x": 42}) == b'{"x":42}'

    def test_zero_int(self):
        assert canonical_serialize({"x": 0}) == b'{"x":0}'

    def test_negative_int(self):
        assert canonical_serialize({"x": -7}) == b'{"x":-7}'

    def test_large_int(self):
        assert canonical_serialize({"x": 10_000_000_000_000}) == b'{"x":10000000000000}'

    def test_int_in_array(self):
        assert canonical_serialize({"a": [1, 2, 3]}) == b'{"a":[1,2,3]}'

    def test_rejects_float(self):
        with pytest.raises(SerializationError, match="[Ff]loat"):
            canonical_serialize({"x": 3.14})

    def test_rejects_float_zero(self):
        with pytest.raises(SerializationError, match="[Ff]loat"):
            canonical_serialize({"x": 0.0})

    def test_rejects_float_in_nested(self):
        with pytest.raises(SerializationError, match="[Ff]loat"):
            canonical_serialize({"a": {"b": [1, 2.5]}})

    def test_rejects_float_negative(self):
        with pytest.raises(SerializationError, match="[Ff]loat"):
            canonical_serialize({"x": -0.001})


# --------------------------------------------------------------------------- #
# Missing values as null
# --------------------------------------------------------------------------- #


class TestNullForMissing:
    def test_none_serializes_as_null(self):
        assert canonical_serialize({"x": None}) == b'{"x":null}'

    def test_none_in_array(self):
        assert canonical_serialize({"a": [None, 1]}) == b'{"a":[null,1]}'

    def test_none_nested(self):
        assert canonical_serialize({"a": {"b": None}}) == b'{"a":{"b":null}}'

    def test_no_nan_allowed(self):
        with pytest.raises((SerializationError, ValueError)):
            canonical_serialize({"x": float("nan")})

    def test_no_infinity_allowed(self):
        with pytest.raises((SerializationError, ValueError)):
            canonical_serialize({"x": float("inf")})

    def test_no_negative_infinity_allowed(self):
        with pytest.raises((SerializationError, ValueError)):
            canonical_serialize({"x": float("-inf")})


# --------------------------------------------------------------------------- #
# Key sorting by codepoint
# --------------------------------------------------------------------------- #


class TestKeySorting:
    def test_keys_sorted_alphabetically(self):
        result = canonical_serialize({"b": 1, "a": 2, "c": 3})
        assert result == b'{"a":2,"b":1,"c":3}'

    def test_keys_sorted_by_codepoint(self):
        result = canonical_serialize({"B": 1, "a": 2, "A": 3})
        assert result == b'{"A":3,"B":1,"a":2}'

    def test_nested_keys_sorted(self):
        result = canonical_serialize({"z": {"b": 1, "a": 2}})
        assert result == b'{"z":{"a":2,"b":1}}'

    def test_unicode_keys_sorted_by_codepoint(self):
        result = canonical_serialize({"\u4e2d": 1, "A": 2})
        assert result == '{"A":2,"\u4e2d":1}'.encode("utf-8")

    def test_digit_keys_sorted_by_codepoint(self):
        result = canonical_serialize({"10": "a", "2": "b"})
        assert result == b'{"10":"a","2":"b"}'


# --------------------------------------------------------------------------- #
# Separators and whitespace
# --------------------------------------------------------------------------- #


class TestSeparators:
    def test_no_space_after_colon(self):
        result = canonical_serialize({"x": 1})
        assert b": " not in result

    def test_no_space_after_comma(self):
        result = canonical_serialize({"x": 1, "y": 2})
        assert b", " not in result

    def test_compact_array(self):
        result = canonical_serialize({"a": [1, 2, 3]})
        assert result == b'{"a":[1,2,3]}'

    def test_no_trailing_whitespace(self):
        result = canonical_serialize({"x": 1})
        assert not result.endswith(b" ")
        assert not result.endswith(b"\t")
        assert not result.endswith(b"\n")


# --------------------------------------------------------------------------- #
# UTF-8 and ensure_ascii=false
# --------------------------------------------------------------------------- #


class TestUtf8Encoding:
    def test_non_ascii_not_escaped(self):
        result = canonical_serialize({"reason": "\u8d44\u91d1\u4e0d\u8db3"})
        assert "\u8d44\u91d1\u4e0d\u8db3".encode("utf-8") in result
        assert b"\\u" not in result

    def test_utf8_bytes_output(self):
        result = canonical_serialize({"x": "\u4e2d\u6587"})
        assert result == '{"x":"\u4e2d\u6587"}'.encode("utf-8")

    def test_no_bom(self):
        result = canonical_serialize({"x": 1})
        assert not result.startswith(b"\xef\xbb\xbf")


# --------------------------------------------------------------------------- #
# NFC normalization
# --------------------------------------------------------------------------- #


class TestNfcNormalization:
    def test_nfc_normalizes_decomposed(self):
        composed = "\u00e9"  # é (precomposed)
        decomposed = "e\u0301"  # e + combining acute
        assert canonical_serialize({"x": decomposed}) == canonical_serialize({"x": composed})

    def test_nfc_normalization_in_keys(self):
        composed_key = "\u00e9"
        decomposed_key = "e\u0301"
        assert canonical_serialize({composed_key: 1}) == canonical_serialize({decomposed_key: 1})

    def test_nfc_produces_canonical_form(self):
        decomposed = "e\u0301"
        result = canonical_serialize({"x": decomposed})
        assert result == b'{"x":"\xc3\xa9"}'


# --------------------------------------------------------------------------- #
# Boolean values
# --------------------------------------------------------------------------- #


class TestBooleans:
    def test_true(self):
        assert canonical_serialize({"x": True}) == b'{"x":true}'

    def test_false(self):
        assert canonical_serialize({"x": False}) == b'{"x":false}'

    def test_bool_in_array(self):
        assert canonical_serialize({"a": [True, False]}) == b'{"a":[true,false]}'


# --------------------------------------------------------------------------- #
# String values
# --------------------------------------------------------------------------- #


class TestStrings:
    def test_simple_string(self):
        assert canonical_serialize({"x": "hello"}) == b'{"x":"hello"}'

    def test_empty_string(self):
        assert canonical_serialize({"x": ""}) == b'{"x":""}'

    def test_string_with_spaces(self):
        assert canonical_serialize({"x": "a b"}) == b'{"x":"a b"}'

    def test_escaped_chars(self):
        result = canonical_serialize({"x": 'a"b'})
        assert result == b'{"x":"a\\"b"}'

    def test_newline_in_string(self):
        result = canonical_serialize({"x": "a\nb"})
        assert result == b'{"x":"a\\nb"}'


# --------------------------------------------------------------------------- #
# Byte-deterministic: two serializations are identical
# --------------------------------------------------------------------------- #


class TestByteDeterminism:
    def test_same_object_twice(self):
        obj = {"b": [1, 2, {"c": None}], "a": "hello", "d": True}
        first = canonical_serialize(obj)
        second = canonical_serialize(obj)
        assert first == second

    def test_reordered_keys_same_output(self):
        import collections

        ordered = collections.OrderedDict([("b", 1), ("a", 2)])
        reversed_ = collections.OrderedDict([("a", 2), ("b", 1)])
        assert canonical_serialize(ordered) == canonical_serialize(reversed_)

    def test_with_unicode_and_nulls(self):
        obj = {
            "reject_reason": "\u8d44\u91d1\u4e0d\u8db3",
            "price_ticks": 10000,
            "mid": None,
            "nested": {"z": None, "a": [1, None, 3]},
        }
        first = canonical_serialize(obj)
        second = canonical_serialize(obj)
        assert first == second

    def test_complex_nested_determinism(self):
        obj = {
            "event_id": "evt_001",
            "transaction_seq": 42,
            "timestamp": 1000000,
            "postings": [
                {"role": "MAKER", "wallet_delta_units": -5, "wallet_after_units": 99995},
                {"role": "TAKER", "wallet_delta_units": 5, "wallet_after_units": 100005},
            ],
            "mid": None,
            "last_price_ticks": 10000,
        }
        first = canonical_serialize(obj)
        second = canonical_serialize(obj)
        assert first == second

    def test_serialization_idempotent(self):
        obj = {"a": 1, "b": [2, None, "x"]}
        first = canonical_serialize(obj)
        parsed = json.loads(first)
        second = canonical_serialize(parsed)
        assert first == second


# --------------------------------------------------------------------------- #
# Event-level serialization (one LF per event)
# --------------------------------------------------------------------------- #


class TestEventSerialization:
    def test_single_event_ends_with_lf(self):
        result = serialize_event({"x": 1})
        assert result == b'{"x":1}\n'
        assert result.endswith(b"\n")

    def test_single_event_no_crlf(self):
        result = serialize_event({"x": 1})
        assert b"\r\n" not in result

    def test_multiple_events_each_terminated_with_lf(self):
        events = [{"x": 1}, {"y": 2}, {"z": 3}]
        result = serialize_events(events)
        assert result == b'{"x":1}\n{"y":2}\n{"z":3}\n'

    def test_multiple_events_no_crlf(self):
        events = [{"x": 1}, {"y": 2}]
        result = serialize_events(events)
        assert b"\r\n" not in result

    def test_empty_events_list(self):
        result = serialize_events([])
        assert result == b""

    def test_each_event_one_line(self):
        events = [{"a": 1, "b": 2}, {"c": 3}]
        result = serialize_events(events)
        lines = result.split(b"\n")
        assert lines[-1] == b""
        assert len(lines) == 3
        assert all(b"\n" not in line for line in lines[:-1])

    def test_events_byte_deterministic(self):
        events = [{"b": 2, "a": 1}, {"d": None, "c": "x"}]
        first = serialize_events(events)
        second = serialize_events(events)
        assert first == second


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #


class TestEdgeCases:
    def test_empty_object(self):
        assert canonical_serialize({}) == b"{}"

    def test_empty_array(self):
        assert canonical_serialize({"a": []}) == b'{"a":[]}'

    def test_deeply_nested(self):
        obj = {"a": {"b": {"c": {"d": 1}}}}
        assert canonical_serialize(obj) == b'{"a":{"b":{"c":{"d":1}}}}'

    def test_mixed_types(self):
        obj = {
            "int_val": 42,
            "str_val": "hello",
            "null_val": None,
            "bool_val": True,
            "arr_val": [1, "two", None, False],
        }
        result = canonical_serialize(obj)
        parsed = json.loads(result)
        assert parsed == obj
