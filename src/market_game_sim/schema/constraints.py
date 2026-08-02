"""T204f4: Record-level constraint validator.

[事件 Schema E-002 同步强制] constraint 正反夹具

Validates a record dict against the ``when``/``then`` constraints declared
in ``event_fields.json``.  Also validates enum value domains and array
``length`` rules.  Returns a list of error strings (empty = valid).

The ``when`` forms that need runtime context (``account_has_position``,
``side_empty``, ``no_trade_yet``, ``no_committed_transaction``) are
evaluated from an optional ``context`` dict; when absent they default
to "not applicable" (constraint skipped).
"""

from __future__ import annotations

from typing import Any

from market_game_sim.schema.registry import SchemaRegistry


def validate_record(
    record: dict,
    registry: SchemaRegistry,
    context: dict[str, Any] | None = None,
) -> list[str]:
    """Validate ``record`` against its event type's constraints.

    Returns a list of human-readable error strings.  An empty list means
    the record is valid.
    """
    event_type = record.get("event_type")
    if event_type is None:
        return ["record has no event_type"]
    if not registry.has_structure(event_type):
        return [f"unknown event_type: {event_type}"]

    ctx = context or {}
    errors: list[str] = []

    for structure_name in ("EVENT_COMMON", event_type):
        if not registry.has_structure(structure_name):
            continue
        _validate_structure_fields(record, structure_name, registry, ctx, errors, prefix="")

    _validate_nested(record, event_type, registry, ctx, errors)
    return errors


def _validate_structure_fields(
    record: dict,
    structure: str,
    registry: SchemaRegistry,
    ctx: dict,
    errors: list[str],
    prefix: str,
) -> None:
    for fname, fmeta in registry.get_fields(structure).items():
        value = record.get(fname)
        field_path = f"{prefix}{fname}" if prefix else fname

        if fmeta.enum is not None and value is not None and value not in fmeta.enum:
            errors.append(
                f"{structure}.{field_path}: value {value!r} not in enum {list(fmeta.enum)}"
            )

        for constraint in fmeta.constraints:
            when = constraint["when"]
            then = constraint["then"]
            if not _evaluate_when(when, record, registry, ctx):
                continue
            if then == "null" and value is not None:
                errors.append(
                    f"{structure}.{field_path}: expected null when {_when_desc(when)}, "
                    f"got {value!r}"
                )
            elif then == "non_null" and value is None:
                errors.append(
                    f"{structure}.{field_path}: expected non-null when {_when_desc(when)}"
                )

        if fmeta.value_type == "array" and fmeta.length is not None:
            _validate_array_length(value, fmeta.length, record, structure, field_path, errors)


def _validate_array_length(
    value: Any,
    length_rule: dict,
    record: dict,
    structure: str,
    field_path: str,
    errors: list[str],
) -> None:
    kind = length_rule.get("kind")
    if kind == "fixed":
        expected = length_rule["value"]
    elif kind == "conditional":
        when = length_rule["when"]
        if _evaluate_when(when, record, None, {}):
            expected = length_rule["then"]
        else:
            expected = length_rule["otherwise"]
    else:
        return

    actual = len(value) if value is not None else 0
    if actual != expected:
        errors.append(f"{structure}.{field_path}: array length {actual} != expected {expected}")


def _validate_nested(
    record: dict,
    event_type: str,
    registry: SchemaRegistry,
    ctx: dict,
    errors: list[str],
) -> None:
    for fname, fmeta in registry.get_fields(event_type).items():
        if fmeta.value_type == "array" and fmeta.element_structure:
            elements = record.get(fname) or []
            for i, elem in enumerate(elements):
                if isinstance(elem, dict):
                    _validate_structure_fields(
                        elem,
                        fmeta.element_structure,
                        registry,
                        ctx,
                        errors,
                        prefix=f"{fname}[{i}].",
                    )
        elif fmeta.value_type == "object" and fmeta.variants:
            obj = record.get(fname, {})
            disc = fmeta.discriminated_by
            variant = record.get(disc)
            if variant and variant in fmeta.variants and isinstance(obj, dict):
                _validate_structure_fields(
                    obj,
                    fmeta.variants[variant],
                    registry,
                    ctx,
                    errors,
                    prefix=f"{fname}.",
                )


def _evaluate_when(
    when: dict,
    record: dict,
    registry: SchemaRegistry | None,
    ctx: dict,
) -> bool:
    if "field" in when and "equals" in when:
        return record.get(when["field"]) == when["equals"]
    if "field" in when and "in" in when:
        return record.get(when["field"]) in when["in"]
    if "always" in when:
        return when["always"] is True
    if "queueing" in when and registry is not None:
        return registry.queueing_class(record["event_type"]) == when["queueing"]
    if "account_has_position" in when:
        return ctx.get("account_has_position", False) == when["account_has_position"]
    if "side_empty" in when:
        return ctx.get("side_empty", {}).get(when["side_empty"], False)
    if "no_trade_yet" in when:
        return ctx.get("no_trade_yet", False) == when["no_trade_yet"]
    if "no_committed_transaction" in when:
        return ctx.get("no_committed_transaction", False) == when["no_committed_transaction"]
    return False


def _when_desc(when: dict) -> str:
    return str(when)
