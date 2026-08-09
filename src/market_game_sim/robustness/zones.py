"""T004 (方法论 §10.3): belief-experiment sub-zone separation.

Keeps the three top-level zones (calibration, frozen validation, belief
experiment) and, inside the belief-experiment zone, splits it into two
disjoint sub-zones -- the exploration-scan zone and the frozen holdout
validation zone.

Each sub-zone owns a disjoint manifest of parameter cells.  Assigning a cell
that already belongs to the other sub-zone is a ``ZoneViolation``: the runner
refuses to start.  This prevents the calibration-zone / holdout-zone reuse
that would turn "market tuning" into "belief validation" (数据污染), and the
holdout zone must never be observed before its frozen run (T501).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ZoneViolation(RuntimeError):
    """Raised when a parameter cell is assigned across disjoint sub-zones."""


class SubZone(Enum):
    EXPLORATION_SCAN = "EXPLORATION_SCAN"
    HOLDOUT_VALIDATION = "HOLDOUT_VALIDATION"


@dataclass
class ZoneRegistry:
    exploration_cells: set[str] = field(default_factory=set)
    holdout_cells: set[str] = field(default_factory=set)

    def assign(self, cell_id: str, zone: SubZone) -> None:
        """Assign a parameter cell to a sub-zone.

        Fail-closed: a cell already in the *other* sub-zone is rejected --
        exploration and holdout must stay disjoint (方法论 §10.3); re-assigning
        within the same sub-zone is a no-op.
        """
        other = self.holdout_cells if zone is SubZone.EXPLORATION_SCAN else self.exploration_cells
        if cell_id in other:
            other_zone = (
                SubZone.HOLDOUT_VALIDATION
                if zone is SubZone.EXPLORATION_SCAN
                else SubZone.EXPLORATION_SCAN
            )
            raise ZoneViolation(
                f"cell {cell_id} already assigned to {other_zone.value}; "
                "exploration and holdout sub-zones must stay disjoint"
            )
        target = self.exploration_cells if zone is SubZone.EXPLORATION_SCAN else self.holdout_cells
        target.add(cell_id)

    def check_disjoint(self) -> bool:
        """Whether the two sub-zones are still disjoint."""
        return not (self.exploration_cells & self.holdout_cells)

    def validate(self) -> None:
        if not self.check_disjoint():
            raise ZoneViolation(
                f"sub-zones overlap: {sorted(self.exploration_cells & self.holdout_cells)}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "exploration_cells": sorted(self.exploration_cells),
            "holdout_cells": sorted(self.holdout_cells),
        }


def cell_id(parameter_unit: dict[str, Any]) -> str:
    """Deterministic id of a parameter cell -- ``H(normalized parameter unit,
    incl. treatment/mapping fields; excludes seed, replicate_id)`` per T202.

    Identifies *which parameter unit* this is (for aggregation/dedup);
    distinct from ``run_id`` which additionally carries seed/replicate.
    """
    unit = {
        k: v for k, v in parameter_unit.items() if k not in ("seed", "replicate_id", "replicate")
    }
    canonical = json.dumps(unit, sort_keys=True, separators=(",", ":"))
    return hashlib.blake2b(canonical.encode("utf-8"), digest_size=16).hexdigest()


def run_id(cell: str, seed: int, replicate_id: int) -> str:
    """Deterministic id of one concrete run -- ``H(cell_id + seed +
    replicate_id)`` per T202.  Identifies one execution (recovery/dedup/artifact
    path); not a pairing join key (that is T402's pair_id/arm_id)."""
    canonical = json.dumps(
        {"cell_id": cell, "seed": seed, "replicate_id": replicate_id},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.blake2b(canonical.encode("utf-8"), digest_size=16).hexdigest()
