"""T204f: Field registry -- loads ``event_fields.json`` as the single source of truth.

This module loads the canonical field schema (事件 Schema E-002 同步强制) and
provides query interfaces consumed by:

- **T205** (event log writer): serialization field set and order per record kind.
- **T206** (event digest hash): E-002 hash projection -- which leaf fields are
  ``HASH_INCLUDE`` vs ``HASH_EXCLUDE``.
- **T206b** (hash coverage check): ``required == include ∪ exclude`` and the
  two sets are disjoint.

The registry **never** embeds a second field declaration -- it only loads and
queries the JSON.  Pure stdlib (KR-005): ``json`` + ``importlib.resources``.

Six-item metadata per field (与 事件 Schema E-002 逐项一致):

1. 所属结构 (structure name, implicit via the structure the field lives in)
2. 值类型 (``value_type``)
3. 枚举值域 (``enum``, optional)
4. 可空性 (``nullable``)
5. 备备性 (``required`` -- only ``always``; conditionality is on *values*
   via ``constraints``, not on field *presence*)
6. 哈希分类 (``hash``: ``HASH_INCLUDE`` | ``HASH_EXCLUDE``)

Nested fields are registered by full path (``postings[].wallet_delta_units``).
Array element order rules and discriminated-union variants are preserved.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from importlib import resources
from typing import Any

# --------------------------------------------------------------------------- #
# Constants derived from 事件 Schema §1.4 / §3 / §6
# --------------------------------------------------------------------------- #

#: 事件 Schema §1.4 -- events that enter the queue and trigger transactions.
QUEUE_EVENTS: frozenset[str] = frozenset(
    {"ORDER_ARRIVAL", "AGENT_OBSERVE", "AGENT_DECIDE", "SNAPSHOT"}
)

#: 事件 Schema §1.4 -- records produced inside a transaction, never enqueued.
TRANSACTION_RECORDS: frozenset[str] = frozenset(
    {"ORDER_CANCELLED", "TRADE_SETTLE", "MARGIN_CALL", "MARKET_DATA_PUBLISH"}
)

#: 事件 Schema §6 -- three top-level record kinds, discriminated by ``record_kind``.
RECORD_KINDS: tuple[str, ...] = ("RUN_HEADER", "EVENT", "RUN_TRAILER")

#: Event types (structures that carry EVENT_COMMON fields + their own).
EVENT_TYPES: frozenset[str] = frozenset(
    {
        "ORDER_ARRIVAL",
        "ORDER_CANCELLED",
        "TRADE_SETTLE",
        "MARGIN_CALL",
        "MARKET_DATA_PUBLISH",
        "AGENT_OBSERVE",
        "AGENT_DECIDE",
        "SNAPSHOT",
    }
)

#: Posting variants -- discriminated union by ``posting_type`` (§4.2.3).
POSTING_VARIANTS: frozenset[str] = frozenset({"TRADE_POSTING", "WRITE_OFF_POSTING"})

#: Structures that are never top-level records (nested inside events/snapshots).
NESTED_STRUCTURES: frozenset[str] = frozenset(
    {
        "EVENT_COMMON",
        "INTENT",
        "TRADE_POSTING",
        "WRITE_OFF_POSTING",
        "ACCOUNT_PAYLOAD",
        "ACCOUNT_SNAPSHOT_ENTRY",
        "EXCHANGE_SNAPSHOT",
        "BOOK_PAYLOAD",
        "BOOK_LEVEL",
    }
)

#: Hash classification constants.
HASH_INCLUDE = "HASH_INCLUDE"
HASH_EXCLUDE = "HASH_EXCLUDE"

#: Required-ness constant (事件 Schema §9: fields always present, conditionality
#: is on values via constraints, not on presence).
REQUIRED_ALWAYS = "always"


# --------------------------------------------------------------------------- #
# Field metadata
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class FieldMetadata:
    """Six-item metadata for a single field (事件 Schema E-002 同步强制).

    ``structure`` is the structure this field belongs to; ``name`` is the
    field's key within that structure.  Together they form the canonical
    path ``structure.field`` used by T204f3's bidirectional consistency check.
    """

    structure: str
    name: str
    value_type: str
    nullable: bool
    required: str
    hash_class: str
    enum: tuple[str, ...] | None = None
    constraints: tuple[dict[str, Any], ...] = ()
    # Array-specific (value_type == "array")
    element_structure: str | None = None
    array_order: dict[str, Any] | None = None
    length: dict[str, Any] | None = None
    # Object-specific (value_type == "object", discriminated union)
    discriminated_by: str | None = None
    variants: dict[str, str] | None = None

    @property
    def is_leaf(self) -> bool:
        """A leaf field carries a scalar value (int/str/bool/enum).

        ``array`` and ``object`` fields are containers -- they have children
        reached via ``element_structure`` or ``variants``.
        """
        return self.value_type not in ("array", "object")


@dataclass(frozen=True)
class LeafField:
    """A leaf field reached by a full path from a root structure.

    ``path`` uses ``[]`` suffix for array elements and ``.`` for object
    nesting, e.g. ``postings[].wallet_delta_units``.
    """

    structure: str
    name: str
    path: str
    hash_class: str
    nullable: bool
    value_type: str
    enum: tuple[str, ...] | None = None


# --------------------------------------------------------------------------- #
# Schema registry
# --------------------------------------------------------------------------- #


class SchemaRegistry:
    """Loads ``event_fields.json`` and exposes typed query interfaces.

    The registry is the **sole consumer** of the JSON inside the codebase.
    T205 (serializer), T206 (hash projection) and T206b (coverage check) all
    derive from it -- hand-maintaining three lists would inevitably drift.
    """

    def __init__(self, json_path: pathlib.Path | None = None) -> None:
        if json_path is None:
            try:
                pkg = resources.files("market_game_sim.schema")
                json_path = pathlib.Path(str(pkg.joinpath("event_fields.json")))
            except (AttributeError, FileNotFoundError):
                json_path = pathlib.Path(__file__).parent / "event_fields.json"
        self._path = json_path
        self._raw: dict[str, Any] = json.loads(json_path.read_text(encoding="utf-8"))
        self._structures: dict[str, Any] = self._raw["structures"]
        self._meta: dict[str, Any] = self._raw["meta"]

    # ------------------------------------------------------------------ #
    # Raw accessors
    # ------------------------------------------------------------------ #

    @property
    def schema_version(self) -> int:
        return self._raw["schema_version"]

    @property
    def record_kinds(self) -> tuple[str, ...]:
        return tuple(self._raw["record_kinds"])

    @property
    def meta(self) -> dict[str, Any]:
        return self._meta

    @property
    def json_path(self) -> pathlib.Path:
        return self._path

    def structure_names(self) -> tuple[str, ...]:
        return tuple(self._structures.keys())

    def get_structure(self, name: str) -> dict[str, Any]:
        if name not in self._structures:
            raise KeyError(f"Unknown structure: {name}")
        return self._structures[name]

    def has_structure(self, name: str) -> bool:
        return name in self._structures

    # ------------------------------------------------------------------ #
    # Field metadata queries
    # ------------------------------------------------------------------ #

    def get_fields(self, structure: str) -> dict[str, FieldMetadata]:
        """Return field metadata for *structure* (field name -> metadata)."""
        raw = self.get_structure(structure)
        raw_fields = raw.get("fields", {})
        result: dict[str, FieldMetadata] = {}
        for fname, fdef in raw_fields.items():
            result[fname] = self._build_metadata(structure, fname, fdef)
        return result

    def get_field(self, structure: str, field: str) -> FieldMetadata:
        fields = self.get_fields(structure)
        if field not in fields:
            raise KeyError(f"Field '{field}' not in structure '{structure}'")
        return fields[field]

    def field_names(self, structure: str) -> tuple[str, ...]:
        raw = self.get_structure(structure)
        return tuple(raw.get("fields", {}).keys())

    def leaf_field_count(self, structure: str) -> int:
        """Declared leaf-field count for a structure.

        For structures with an explicit ``leaf_field_count`` (TRADE_POSTING=15,
        WRITE_OFF_POSTING=8, etc.) return it directly.  For others, count
        non-container fields (those whose ``value_type`` is not array/object).
        """
        raw = self.get_structure(structure)
        if "leaf_field_count" in raw:
            return raw["leaf_field_count"]
        fields = raw.get("fields", {})
        return sum(1 for f in fields.values() if f.get("value_type") not in ("array", "object"))

    # ------------------------------------------------------------------ #
    # Leaf-field recursion (full paths)
    # ------------------------------------------------------------------ #

    def get_leaf_fields(
        self, structure: str, prefix: str = "", _seen: frozenset[str] | None = None
    ) -> list[LeafField]:
        """Return all leaf fields reachable from *structure* with full paths.

        ``prefix`` is the dotted path from the root structure to *structure*.
        Array elements append ``[]``; discriminated-union variants are flattened
        (all variants' leaves are included, since the hash must cover every
        possible shape).

        Cycles are guarded by ``_seen`` -- though the schema is acyclic, the
        guard prevents infinite recursion if the JSON is ever malformed.
        """
        if _seen is None:
            _seen = frozenset()
        if structure in _seen:
            raise ValueError(f"Cycle detected at structure '{structure}'")
        _seen = _seen | {structure}

        fields = self.get_fields(structure)
        leaves: list[LeafField] = []
        for fname, fmeta in fields.items():
            path = f"{prefix}{fname}" if not prefix else f"{prefix}.{fname}"
            if fmeta.is_leaf:
                leaves.append(
                    LeafField(
                        structure=structure,
                        name=fname,
                        path=path,
                        hash_class=fmeta.hash_class,
                        nullable=fmeta.nullable,
                        value_type=fmeta.value_type,
                        enum=fmeta.enum,
                    )
                )
            elif fmeta.value_type == "array" and fmeta.element_structure:
                # Array: descend into element structure, path gets [] suffix.
                child_prefix = f"{path}[]"
                leaves.extend(self.get_leaf_fields(fmeta.element_structure, child_prefix, _seen))
            elif fmeta.value_type == "object" and fmeta.variants:
                # Discriminated union: descend into every variant.
                for variant_name, variant_struct in fmeta.variants.items():
                    child_prefix = f"{path}.{variant_name}"
                    leaves.extend(self.get_leaf_fields(variant_struct, child_prefix, _seen))
            elif fmeta.value_type == "object":
                # Plain object without discriminator -- treat as leaf (no
                # sub-structure to recurse into). Should not occur in the
                # current schema but handled defensively.
                leaves.append(
                    LeafField(
                        structure=structure,
                        name=fname,
                        path=path,
                        hash_class=fmeta.hash_class,
                        nullable=fmeta.nullable,
                        value_type=fmeta.value_type,
                    )
                )
        return leaves

    # ------------------------------------------------------------------ #
    # E-002 hash projection
    # ------------------------------------------------------------------ #

    def hash_include_leaves(self, structure: str) -> set[str]:
        """Leaf field paths included in the E-002 digest hash.

        A leaf is included when **every ancestor on its path** is
        ``HASH_INCLUDE`` and the leaf itself is ``HASH_INCLUDE``.  If any
        ancestor excludes the field, all its descendants are excluded too --
        this matches the principle that excluding a container excludes its
        contents.
        """
        return self._collect_hash_leaves(structure, include=True)

    def hash_exclude_leaves(self, structure: str) -> set[str]:
        """Leaf field paths excluded from the E-002 digest hash."""
        return self._collect_hash_leaves(structure, include=False)

    def _collect_hash_leaves(
        self,
        structure: str,
        include: bool,
        prefix: str = "",
        parent_excluded: bool = False,
        _seen: frozenset[str] | None = None,
    ) -> set[str]:
        if _seen is None:
            _seen = frozenset()
        if structure in _seen:
            raise ValueError(f"Cycle detected at structure '{structure}'")
        _seen = _seen | {structure}

        fields = self.get_fields(structure)
        result: set[str] = set()
        for fname, fmeta in fields.items():
            path = f"{prefix}{fname}" if not prefix else f"{prefix}.{fname}"
            # If any ancestor is HASH_EXCLUDE, descendants are excluded.
            excluded = parent_excluded or (fmeta.hash_class == HASH_EXCLUDE)
            if fmeta.is_leaf:
                is_excluded = excluded or (fmeta.hash_class == HASH_EXCLUDE)
                is_included = (not excluded) and (fmeta.hash_class == HASH_INCLUDE)
                if (include and is_included) or ((not include) and is_excluded):
                    result.add(path)
            elif fmeta.value_type == "array" and fmeta.element_structure:
                child_prefix = f"{path}[]"
                result |= self._collect_hash_leaves(
                    fmeta.element_structure, include, child_prefix, excluded, _seen
                )
            elif fmeta.value_type == "object" and fmeta.variants:
                for _variant_name, variant_struct in fmeta.variants.items():
                    child_prefix = f"{path}.{_variant_name}"
                    result |= self._collect_hash_leaves(
                        variant_struct, include, child_prefix, excluded, _seen
                    )
            else:
                # Plain object without variants (e.g. internal_state,
                # information_set, exchange) -- treated as leaf by
                # get_leaf_fields, so mirror that here.
                is_excluded = excluded or (fmeta.hash_class == HASH_EXCLUDE)
                is_included = (not excluded) and (fmeta.hash_class == HASH_INCLUDE)
                if (include and is_included) or ((not include) and is_excluded):
                    result.add(path)
        return result

    # ------------------------------------------------------------------ #
    # T206b: hash coverage check
    # ------------------------------------------------------------------ #

    def check_coverage(self, structure: str) -> dict[str, set[str]]:
        """Verify ``required == include ∪ exclude`` and the sets are disjoint.

        Returns a dict with keys ``required``, ``include``, ``exclude``,
        ``missing`` (required but in neither), ``ambiguous`` (in both).
        An empty ``missing`` and ``ambiguous`` means the coverage invariant
        holds for *structure*.
        """
        leaves = self.get_leaf_fields(structure)
        required = {lf.path for lf in leaves}
        included = self.hash_include_leaves(structure)
        excluded = self.hash_exclude_leaves(structure)
        missing = required - (included | excluded)
        ambiguous = included & excluded
        return {
            "required": required,
            "include": included,
            "exclude": excluded,
            "missing": missing,
            "ambiguous": ambiguous,
        }

    # ------------------------------------------------------------------ #
    # Serialization field order (T205)
    # ------------------------------------------------------------------ #

    def serialization_fields(self, record_kind: str, event_type: str | None = None) -> list[str]:
        """Return the field names for a record, in canonical (sorted) order.

        For ``record_kind = "EVENT"``, *event_type* selects the event-specific
        fields; EVENT_COMMON fields are prepended.  The returned list is
        sorted by Unicode code point (ADR-001 §7), matching the canonical
        serializer's ``sort_keys=True``.
        """
        if record_kind == "RUN_HEADER":
            return sorted(self.field_names("RUN_HEADER"))
        if record_kind == "RUN_TRAILER":
            return sorted(self.field_names("RUN_TRAILER"))
        if record_kind == "EVENT":
            if event_type is None:
                raise ValueError("event_type is required for record_kind='EVENT'")
            if event_type not in EVENT_TYPES:
                raise ValueError(f"Unknown event_type: {event_type}")
            common = self.field_names("EVENT_COMMON")
            specific = self.field_names(event_type)
            return sorted(set(common) | set(specific))
        raise ValueError(f"Unknown record_kind: {record_kind}")

    # ------------------------------------------------------------------ #
    # Queueing classification (事件 Schema §1.4)
    # ------------------------------------------------------------------ #

    @staticmethod
    def is_queue_event(event_type: str) -> bool:
        return event_type in QUEUE_EVENTS

    @staticmethod
    def is_transaction_record(event_type: str) -> bool:
        return event_type in TRANSACTION_RECORDS

    @staticmethod
    def queueing_class(event_type: str) -> str:
        if event_type in QUEUE_EVENTS:
            return "queue_event"
        if event_type in TRANSACTION_RECORDS:
            return "transaction_record"
        raise ValueError(f"Unknown event_type for queueing classification: {event_type}")

    # ------------------------------------------------------------------ #
    # Priority class (事件 Schema §3)
    # ------------------------------------------------------------------ #

    @staticmethod
    def priority_class(event_type: str) -> int:
        """Return the priority class (0-5) for *event_type* (§3).

        ``ORDER_CANCELLED`` and ``ORDER_ARRIVAL`` share class 0;
        ``TRADE_SETTLE`` and ``MARGIN_CALL`` share class 1.
        """
        classes = {
            "ORDER_ARRIVAL": 0,
            "ORDER_CANCELLED": 0,
            "TRADE_SETTLE": 1,
            "MARGIN_CALL": 1,
            "MARKET_DATA_PUBLISH": 2,
            "AGENT_OBSERVE": 3,
            "AGENT_DECIDE": 4,
            "SNAPSHOT": 5,
        }
        if event_type not in classes:
            raise ValueError(f"Unknown event_type for priority class: {event_type}")
        return classes[event_type]

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _build_metadata(self, structure: str, name: str, fdef: dict[str, Any]) -> FieldMetadata:
        return FieldMetadata(
            structure=structure,
            name=name,
            value_type=fdef["value_type"],
            nullable=fdef["nullable"],
            required=fdef["required"],
            hash_class=fdef["hash"],
            enum=tuple(fdef["enum"]) if "enum" in fdef else None,
            constraints=tuple(fdef.get("constraints", ())),
            element_structure=fdef.get("element_structure"),
            array_order=fdef.get("array_order"),
            length=fdef.get("length"),
            discriminated_by=fdef.get("discriminated_by"),
            variants=fdef.get("variants"),
        )


# --------------------------------------------------------------------------- #
# Module-level singleton (loaded once, reused by all consumers)
# --------------------------------------------------------------------------- #

_registry: SchemaRegistry | None = None


def get_registry() -> SchemaRegistry:
    """Return the process-wide :class:`SchemaRegistry` singleton."""
    global _registry
    if _registry is None:
        _registry = SchemaRegistry()
    return _registry


def reload_registry(json_path: pathlib.Path | None = None) -> SchemaRegistry:
    """Force-reload the registry (testing aid)."""
    global _registry
    _registry = SchemaRegistry(json_path)
    return _registry
