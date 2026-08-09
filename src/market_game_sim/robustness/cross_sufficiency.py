"""T207 (0.1.3 E2): market-sufficiency applied per cross-matrix cell.

The parameter sweep and failure-boundary localization (T201-T205) run
independently for every ``model_family_id × behavior_mapping_id`` cell.
A cell that fails the T206 market-sufficiency gate enters only failure /
boundary reports -- it never feeds the cross-cell belief conclusion.

If a cell is not semantically comparable (e.g. a mapping not applicable to a
family's structure), that must be declared at preregistration and E1 degraded
to the corresponding conditional conclusion -- never silently dropped, and
never substituted with another cell's result.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from market_game_sim.robustness.market_sufficiency import market_sufficient


class CrossSufficiencyError(RuntimeError):
    """Raised on an undeclared non-comparable cell or an excluded cell feeding
    a belief conclusion."""


@dataclass
class CellSufficiency:
    family_id: str
    mapping_id: str
    passed: bool
    reasons: list[str] = field(default_factory=list)
    declared_non_comparable: bool = False


@dataclass
class CrossSufficiencyReport:
    cells: list[CellSufficiency] = field(default_factory=list)
    undeclared_non_comparable: list[str] = field(default_factory=list)

    def eligible_cells(self) -> list[CellSufficiency]:
        """Cells that may feed the belief conclusion: passed the gate and not
        declared non-comparable."""
        return [c for c in self.cells if c.passed and not c.declared_non_comparable]

    def validate_for_conclusion(self) -> None:
        """Fail-closed: if any eligible-path cell was excluded without a
        preregistered non-comparable declaration, or a passed cell was silently
        dropped, raise.  Every declared non-comparable cell must be declared."""
        if self.undeclared_non_comparable:
            raise CrossSufficiencyError(
                "undeclared non-comparable cells: " + ", ".join(self.undeclared_non_comparable)
            )


def apply_sufficiency(
    cells: list[tuple[str, str, dict]],  # (family_id, mapping_id, matrix)
    *,
    declared_non_comparable: set[tuple[str, str]] | None = None,
    sufficiency_fn: Callable[[dict], Any] = market_sufficient,
) -> CrossSufficiencyReport:
    """Evaluate the T206 gate for every cell of the cross matrix.

    ``cells`` is a list of ``(family_id, mapping_id, market_matrix)``.
    Cells whose ``(family_id, mapping_id)`` is in ``declared_non_comparable``
    are marked non-comparable (preregistered reason) and excluded from the
    belief conclusion.
    """
    declared = declared_non_comparable or set()
    report = CrossSufficiencyReport()
    seen: set[tuple[str, str]] = set()
    for family_id, mapping_id, matrix in cells:
        key = (family_id, mapping_id)
        if key in seen:
            raise CrossSufficiencyError(f"duplicate cell {key}")
        seen.add(key)
        s = sufficiency_fn(matrix)
        report.cells.append(
            CellSufficiency(
                family_id=family_id,
                mapping_id=mapping_id,
                passed=s.passed,
                reasons=list(s.reasons),
                declared_non_comparable=key in declared,
            )
        )
    return report
