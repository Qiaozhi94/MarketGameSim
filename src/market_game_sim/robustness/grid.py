"""T202 (FR-014): deterministic parameter-grid expansion.

Expands a typed scan-axes spec into a deterministic grid of parameter cells,
each identified by ``cell_id`` (a content hash of the normalized parameter
unit, treatment/mapping included but seed/replicate excluded -- see zones.py)
and each concrete run by ``run_id`` (cell_id + seed + replicate).

Ordering is stable: the same manifest yields the same sequence of cells in
the same order regardless of how many workers process it, so parallelism
cannot change output order or summaries (NFR-001).  ``cell_id``/``run_id``
are used for aggregation/dedup/artifact paths, NOT as pairing join keys
(that is T402's pair_id/arm_id).
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any

from market_game_sim.robustness.zones import cell_id as _cell_id
from market_game_sim.robustness.zones import run_id as _run_id


class GridError(RuntimeError):
    """Raised on a malformed grid expansion."""


@dataclass
class ParameterCell:
    parameters: dict[str, Any]
    cell_id: str

    def run_id(self, seed: int, replicate_id: int = 0) -> str:
        return _run_id(self.cell_id, seed, replicate_id)


@dataclass
class GridManifest:
    axes_order: list[str] = field(default_factory=list)
    cells: list[ParameterCell] = field(default_factory=list)

    def iter_cell_ids(self) -> list[str]:
        return [c.cell_id for c in self.cells]


def normalize_parameter(unit: dict[str, Any]) -> dict[str, Any]:
    """Normalize a parameter unit to a canonical form (sorted keys, string
    scalars) so cell_id is stable regardless of input construction."""
    return {k: v for k, v in sorted(unit.items())}


def expand_grid(axis_values: dict[str, list[Any]]) -> GridManifest:
    """Deterministically expand a ``{axis_name: [values]}`` spec into the full
    Cartesian grid.  Axis order follows sorted keys (stable across processes);
    cell parameter dicts are key-sorted.

    Each cell's ``parameters`` includes the axis values so the treatment/
    mapping fields are captured in ``cell_id`` (excludes seed/replicate).
    """
    if not axis_values:
        raise GridError("cannot expand an empty grid")
    axes_order = sorted(axis_values)
    keys = axes_order
    combos = list(itertools.product(*(axis_values[k] for k in keys)))
    cells: list[ParameterCell] = []
    for combo in combos:
        params = dict(zip(keys, combo, strict=True))
        cells.append(
            ParameterCell(parameters=params, cell_id=_cell_id(normalize_parameter(params)))
        )
    return GridManifest(axes_order=keys, cells=cells)
