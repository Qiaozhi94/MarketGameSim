"""T403 (方法论 §10.5): configuration-diff validator.

Proves that each pre-registered contrast changes only the target treatment.

- Same-family behavior-mapping contrast: only the mapping id/version and its
  pre-registered parameters may change.
- Same-mapping model-family contrast: ``model_family_id`` is a composite
  treatment; the actual config diff must be non-empty and confined to the
  family's declared family-defining field set; all shared fields byte-identical.
- Parameter-scan cells and ablation treatments still change only the one
  pre-registered dimension.

Fail-closed: an extra field outside the allowed set is rejected; changing only
``model_family_id/version`` with no family-defining structural change is also
rejected (a no-op relabel).  Regression tests must cover "legal family diff
passes", "extra-field drift rejected", "id-only relabel rejected".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class DiffValidationError(RuntimeError):
    """Raised when a contrast changes more than the target treatment."""


# Sentinel distinguishing "key absent (deleted)" from "key present with a
# legitimately None value" (v013 round-3: disabled_factor: noise -> None is a
# legal value change, NOT a deletion).
_MISSING = object()


@dataclass
class ContrastRule:
    """Declares which fields a given contrast kind may change."""

    kind: str  # "behavior_mapping" | "model_family" | "scan_axis" | "ablation"
    allowed_fields: list[str] = field(default_factory=list)
    family_defining_fields: list[str] = field(default_factory=list)
    requires_structural_change: bool = False


def _diff(base: dict[str, Any], changed: dict[str, Any]) -> dict[str, Any]:
    """Symmetric diff: a field changed when its value differs OR when it was
    DELETED from base.  Deletion is marked with the ``_MISSING`` sentinel so a
    legitimately-None value change is never confused with a deletion (v013)."""
    diff: dict[str, Any] = {}
    for k, v in changed.items():
        if base.get(k) != v:
            diff[k] = v
    for k in base:
        if k not in changed:
            diff[k] = _MISSING  # deleted field = a change
    return diff


def _deleted_fields(diff: dict[str, Any]) -> list[str]:
    return [k for k, v in diff.items() if v is _MISSING]


def validate_contrast(
    base_config: dict[str, Any],
    changed_config: dict[str, Any],
    rule: ContrastRule,
) -> dict[str, Any]:
    """Validate that ``changed_config`` only changes fields the ``rule`` allows.

    Returns the actual diff on success; raises ``DiffValidationError`` on any
    disallowed change (fail-closed).  A contrast with NO actual change in any
    treatment field (zero diff) is rejected -- a pre-registered contrast must
    actually vary the target treatment (v013 round-3).
    """
    diff = _diff(base_config, changed_config)

    if rule.kind == "model_family":
        # composite treatment: must change family id AND at least one
        # family-defining structural field, and nothing outside defining set
        changed_structural = {k: v for k, v in diff.items() if k in rule.family_defining_fields}
        # a DELETED defining field is not a legal structural change -- it
        # removes the very field the family identity rests on.
        deleted_structural = _deleted_fields(changed_structural)
        if deleted_structural:
            raise DiffValidationError(
                f"model-family contrast deleted defining field(s): {deleted_structural}"
            )
        if not changed_structural:
            raise DiffValidationError(
                "model-family contrast changed no family-defining structural field "
                "(id/version-only relabel is a no-op, rejected)"
            )
        extra = set(diff) - set(rule.family_defining_fields) - {"model_family_id", "version"}
        if extra:
            raise DiffValidationError(
                f"model-family contrast changed fields outside defining set: {sorted(extra)}"
            )
        return diff

    # behavior_mapping / scan_axis / ablation: only allowed_fields may change
    disallowed = set(diff) - set(rule.allowed_fields)
    if disallowed:
        raise DiffValidationError(
            f"{rule.kind} contrast changed fields outside allowed set: {sorted(disallowed)}"
        )
    # DELETING a pre-registered treatment field itself is not a legal contrast
    # -- the treatment must still exist.
    deleted_allowed = _deleted_fields(diff)
    if deleted_allowed:
        raise DiffValidationError(
            f"{rule.kind} contrast deleted treatment field(s): {deleted_allowed}"
        )
    # v013 round-3: a contrast with zero actual change is invalid -- the
    # target treatment must actually vary.
    if not diff:
        raise DiffValidationError(
            f"{rule.kind} contrast has no change in any allowed field "
            f"(identical configs are not a valid contrast)"
        )
    return diff
