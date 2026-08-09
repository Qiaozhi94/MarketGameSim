"""T607 (0.1.3 E1-E5): robustness evidence matrix.

Assembles a machine-readable matrix linking, per row, the robustness evidence
products: behavior mappings, model families, parameter boundaries, ablation,
holdout replication and KPI-009 bridge checks.  The capability-attribution
column must be empty (0.1.3 arranges no such evidence) or carry its explicit
source; the generator never skips the empty-set column validation (T404).

Each row's artifact links point to the run manifest / raw log summary that
produced it, so any conclusion can be traced back (T704).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from market_game_sim.robustness.report_guard import (
    validate_capability_attributions,
)


class EvidenceMatrixError(RuntimeError):
    """Raised when the evidence matrix is incomplete or has an invalid
    capability-attribution column."""


@dataclass
class EvidenceRow:
    family_id: str
    mapping_id: str
    behavior_mapping_artifact: str = ""
    parameter_boundary_artifact: str = ""
    ablation_artifact: str = ""
    holdout_artifact: str = ""
    kpi009_artifact: str = ""
    capability_attributions: list[Any] = field(default_factory=list)


@dataclass
class EvidenceMatrix:
    rows: list[EvidenceRow] = field(default_factory=list)

    def validate(self) -> None:
        """Fail-closed: every row must have a non-empty artifact for each of
        the five evidence columns, and the capability-attribution column must
        pass the empty-set/evidenced guard (never skipped)."""
        for row in self.rows:
            missing = [
                c
                for c in (
                    "behavior_mapping_artifact",
                    "parameter_boundary_artifact",
                    "ablation_artifact",
                    "holdout_artifact",
                    "kpi009_artifact",
                )
                if not getattr(row, c)
            ]
            if missing:
                raise EvidenceMatrixError(
                    f"row {row.family_id}@{row.mapping_id} missing artifacts: {missing}"
                )
            violations = validate_capability_attributions(row.capability_attributions)
            if violations:
                raise EvidenceMatrixError(
                    f"row {row.family_id}@{row.mapping_id} capability attribution: "
                    + "; ".join(violations)
                )

    def as_dict(self) -> dict[str, Any]:
        return {
            "rows": [
                {
                    "family_id": r.family_id,
                    "mapping_id": r.mapping_id,
                    "behavior_mapping_artifact": r.behavior_mapping_artifact,
                    "parameter_boundary_artifact": r.parameter_boundary_artifact,
                    "ablation_artifact": r.ablation_artifact,
                    "holdout_artifact": r.holdout_artifact,
                    "kpi009_artifact": r.kpi009_artifact,
                    "capability_attributions": [
                        {"dimension": a.dimension, "evidence": a.evidence}
                        for a in r.capability_attributions
                    ],
                }
                for r in self.rows
            ]
        }
