"""T105 (0.1.3 E1): model-family x behavior-mapping cross matrix.

Builds the full ``model_family_id × behavior_mapping_id`` cross-contrast
matrix: every pre-registered model family runs *every* pre-registered
behavior mapping (not a sampled subset), each cell on a common comparable
parameter point and seed set, forming a single-dimension pairing.

The report declares mapping main effect, family main effect and their
interaction / direction-reversal.  "同向成立" (same-direction robustness) holds
only when the *whole* matrix is directionally consistent -- not when the two
dimensions are counted separately and stitched together.  Any reversal or
non-significance is reported as a dependency boundary (E1's "明确报告" branch).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class CrossMatrixError(RuntimeError):
    """Raised on an incomplete or directionally inconsistent cross matrix."""


@dataclass
class CrossCell:
    family_id: str
    mapping_id: str
    effect_direction: int  # +1 / -1 / 0
    significant: bool
    effect_size: float = 0.0
    ci_low: float = 0.0
    ci_high: float = 0.0


@dataclass
class CrossMatrix:
    cells: list[CrossCell] = field(default_factory=list)

    def cell(self, family_id: str, mapping_id: str) -> CrossCell | None:
        for c in self.cells:
            if c.family_id == family_id and c.mapping_id == mapping_id:
                return c
        return None

    def dimensions(self) -> tuple[list[str], list[str]]:
        families = sorted({c.family_id for c in self.cells})
        mappings = sorted({c.mapping_id for c in self.cells})
        return families, mappings

    def is_complete(self, families: list[str], mappings: list[str]) -> bool:
        """Whether every (family, mapping) combination has a cell (E1: every
        pre-registered family runs every pre-registered mapping)."""
        have = {(c.family_id, c.mapping_id) for c in self.cells}
        return all((f, m) in have for f in families for m in mappings)

    def missing(self, families: list[str], mappings: list[str]) -> list[tuple[str, str]]:
        have = {(c.family_id, c.mapping_id) for c in self.cells}
        return [(f, m) for f in families for m in mappings if (f, m) not in have]

    def direction_signature(self) -> set[int]:
        """Set of non-zero directions present across significant cells."""
        return {c.effect_direction for c in self.cells if c.significant and c.effect_direction != 0}

    def report(self, families: list[str], mappings: list[str]) -> dict[str, Any]:
        """Generate the E1 cross-matrix report.

        Returns a dict with:
          - ``complete``: matrix completeness over declared families/mappings
          - ``same_direction``: EVERY comparable cell significant, non-zero
            direction, and all agreeing -- zero-direction or non-significant
            cells are NOT silently ignored (v013 fix)
          - ``directions``: the direction signature
          - ``mapping_effect`` / ``family_effect``: per-dimension direction
            counts (reported, not stitched into a conclusion by themselves)
          - ``reversals``: cells whose direction disagrees with the majority
          - ``conclusion``: "同向成立" | "依赖边界" | "证据不足"
        """
        missing = self.missing(families, mappings)
        sig = self.direction_signature()
        n_cells = len(self.cells)
        n_significant_nonzero = len(
            [c for c in self.cells if c.significant and c.effect_direction != 0]
        )

        mapping_dirs: dict[str, set[int]] = {}
        family_dirs: dict[str, set[int]] = {}
        for c in self.cells:
            if not c.significant or c.effect_direction == 0:
                continue
            mapping_dirs.setdefault(c.mapping_id, set()).add(c.effect_direction)
            family_dirs.setdefault(c.family_id, set()).add(c.effect_direction)

        # v013 (critical): same-direction robustness holds ONLY when every
        # comparable cell is significant with a non-zero direction and all
        # directions agree.  A zero-direction cell means that cell shows no
        # effect -- the claim does NOT hold across the whole matrix, so this
        # is a dependency boundary, never "同向成立".
        same_direction = n_significant_nonzero == n_cells and len(sig) == 1

        if missing:
            conclusion = "证据不足"  # incomplete matrix
        elif n_significant_nonzero < n_cells:
            # at least one cell non-significant or zero-direction
            conclusion = "证据不足" if n_significant_nonzero == 0 else "依赖边界"
        elif same_direction:
            conclusion = "同向成立"
        else:
            conclusion = "依赖边界"

        return {
            "complete": not missing,
            "missing": missing,
            "same_direction": same_direction,
            "directions": sorted(sig),
            "mapping_direction_counts": {m: sorted(d) for m, d in sorted(mapping_dirs.items())},
            "family_direction_counts": {f: sorted(d) for f, d in sorted(family_dirs.items())},
            "conclusion": conclusion,
        }
