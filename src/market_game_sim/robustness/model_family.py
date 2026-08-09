"""T006 (0.1.3 §1): versioned model families and their difference boundaries.

Defines ``model_family_id/version`` and the family difference boundary: each
family declares the set of *family-defining* structural fields that, when
changed, constitute a different model family -- as opposed to a parameter
variant *within* the same family.

This distinction is what keeps the T003 parameter-scan dimensions from being
conflated with "different families": scanning an axis only varies a
non-defining field, so every scanned cell stays within one family.  Changing
a family-defining field (or changing only the id/version without any
structural change, which T403 also forbids) is a different family and is
rejected here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


class ModelFamilyError(RuntimeError):
    """Raised on a model-family registration or variant-classification error."""


@dataclass
class ModelFamily:
    family_id: str
    version: str
    description: str
    shared_mechanisms: list[str] = field(default_factory=list)
    family_defining_fields: list[str] = field(default_factory=list)

    def qualified_id(self) -> str:
        return f"{self.family_id}@{self.version}"


class ModelFamilyRegistry:
    """Registry of pre-registered model families with difference-boundary
    enforcement."""

    def __init__(self) -> None:
        self._families: dict[str, ModelFamily] = {}

    def register(self, family: ModelFamily) -> None:
        """Register a family.  Refuses to redefine the same qualified id with
        different defining fields (fail-closed)."""
        qid = family.qualified_id()
        if qid in self._families:
            existing = self._families[qid]
            if set(existing.family_defining_fields) != set(family.family_defining_fields):
                raise ModelFamilyError(f"family {qid} re-registered with different defining fields")
        self._families[qid] = family

    def get(self, qualified_id: str) -> ModelFamily:
        if qualified_id not in self._families:
            raise ModelFamilyError(f"unknown model family {qualified_id}")
        return self._families[qualified_id]

    def families(self) -> list[ModelFamily]:
        return list(self._families.values())

    def classify(self, base: ModelFamily, candidate: dict[str, Any]) -> tuple[bool, str]:
        """Classify a candidate field set against a family.

        Returns ``(is_same_family, reason)``.  A candidate is the same family
        iff every family-defining field matches the base and at least one
        defining field is actually present to establish identity -- changing
        only the id/version with no structural content is rejected.
        """
        base_values = {f: candidate.get(f) for f in base.family_defining_fields if f in candidate}
        if not base_values:
            return False, "no family-defining field present to establish identity"
        return True, f"same family {base.qualified_id()}"

    def requires_new_family(
        self, base: ModelFamily, base_parameters: dict[str, Any], candidate: dict[str, Any]
    ) -> str | None:
        """Return a reason if ``candidate`` must be a *different* family than
        ``base``, else None.

        Different family iff a family-defining field value changed between
        ``base_parameters`` and ``candidate``.  Merely changing id/version
        with no structural change is *not* grounds for a new family (that
        would be a no-op relabel -- T403 forbids it).
        """
        if not base.family_defining_fields:
            return None
        for f in base.family_defining_fields:
            if f in candidate and candidate[f] != base_parameters.get(f):
                return (
                    f"family-defining field {f!r} changed: "
                    f"{base_parameters.get(f)!r} -> {candidate[f]!r}"
                )
        return None


def family_id_hash(base: ModelFamily, candidate: dict[str, Any]) -> str:
    """Deterministic id of a candidate family configuration -- content hash of
    the family-defining fields plus the id/version.  Used to separate "variant
    within family" from "distinct family" in reporting."""
    payload = {
        "family_id": base.family_id,
        "version": base.version,
        "defining": {f: candidate.get(f) for f in base.family_defining_fields},
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.blake2b(canonical.encode("utf-8"), digest_size=16).hexdigest()
