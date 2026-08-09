"""T501/T502 (方法论 §10.3): frozen holdout zone.

Seals the holdout manifest *before* the exploration-scan results are read,
and guards against data contamination: a holdout cell/seed must never appear
in calibration, model selection, threshold selection or fine-sweep inputs.

``seal_holdout`` writes a frozen manifest file that the execution account is
forbidden to modify.  ``check_contamination`` detects any overlap between the
holdout zone and the used (non-holdout) parameter cells; any intersection
invalidates this validation round (T502 fail-closed).
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import dataclass, field
from typing import Any


class HoldoutError(RuntimeError):
    """Raised on holdout sealing or contamination violations."""


@dataclass
class HoldoutManifest:
    cells: list[str] = field(default_factory=list)
    seeds: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"cells": sorted(self.cells), "seeds": sorted(self.seeds)}


def holdout_id(manifest: HoldoutManifest) -> str:
    canonical = json.dumps(manifest.to_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.blake2b(canonical.encode("utf-8"), digest_size=16).hexdigest()


def seal_holdout(
    manifest: HoldoutManifest,
    path: str | pathlib.Path,
    *,
    force: bool = False,
) -> str:
    """Seal the holdout manifest to ``path`` and return its id.

    Refuses to overwrite an existing holdout manifest with different content
    (the execution account must not modify it after sealing)."""
    p = pathlib.Path(path)
    hid = holdout_id(manifest)
    if p.exists() and not force:
        existing = json.loads(p.read_text(encoding="utf-8"))
        if existing.get("holdout_id") != hid:
            raise HoldoutError(
                f"refusing to overwrite sealed holdout {existing.get('holdout_id')} "
                f"with different {hid}"
            )
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"holdout_id": hid, **manifest.to_dict()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return hid


def check_contamination(
    holdout: HoldoutManifest,
    used_cells: list[str],
    used_seeds: list[int] | None = None,
) -> list[str]:
    """Return contamination violations: holdout cells/seeds that also appear
    in the used (non-holdout) input set.  Any violation invalidates the round."""
    violations: list[str] = []
    holdout_cell_set = set(holdout.cells)
    used_cell_set = set(used_cells)
    overlap_cells = holdout_cell_set & used_cell_set
    if overlap_cells:
        violations.append(
            "holdout cells leaked into non-holdout inputs: " + ", ".join(sorted(overlap_cells))
        )

    if used_seeds is not None:
        holdout_seed_set = set(holdout.seeds)
        overlap_seeds = holdout_seed_set & set(used_seeds)
        if overlap_seeds:
            violations.append(
                "holdout seeds leaked: " + ", ".join(str(s) for s in sorted(overlap_seeds))
            )
    return violations
