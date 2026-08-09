"""T503/T504 (0.1.3 E4): one-shot holdout run and cross-zone comparison.

T503: runs the holdout zone once with frozen code and analysis plan.  Any
re-run is allowed only for a *technical failure*, and every failed attempt
(with its reason and new run id) is retained -- never overwritten.

T504: compares exploration-zone vs holdout-zone direction, effect size and
coverage interval.  If a pre-defined replication criterion is not met, that
is reported honestly -- the exploration assumptions are not retrofitted and
the same holdout zone is not re-consumed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

TECHNICAL_RETRY_REASONS = ("TI-1", "TI-3", "TI-4", "TI-5")


class HoldoutRunError(RuntimeError):
    """Raised on an illegal holdout re-run or a replication violation."""


@dataclass
class FailedAttempt:
    run_id: str
    reason: str


@dataclass
class HoldoutRunTracker:
    frozen_plan_id: str
    attempts: list[FailedAttempt] = field(default_factory=list)
    completed_run_id: str | None = None

    def request_rerun(self, run_id: str, reason: str) -> None:
        """Record a failed holdout attempt; allowed only for technical
        failures.  Every failed attempt is retained with its run id."""
        if reason not in TECHNICAL_RETRY_REASONS:
            raise HoldoutRunError(
                f"holdout re-run reason {reason!r} is not a technical failure; "
                "holdout runs once with a frozen plan"
            )
        self.attempts.append(FailedAttempt(run_id=run_id, reason=reason))

    def mark_completed(self, run_id: str) -> None:
        self.completed_run_id = run_id


@dataclass
class ZoneComparison:
    direction_consistent: bool
    effect_size_diff: float
    interval_overlap: bool
    replication_passed: bool
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "direction_consistent": self.direction_consistent,
            "effect_size_diff": self.effect_size_diff,
            "interval_overlap": self.interval_overlap,
            "replication_passed": self.replication_passed,
            "note": self.note,
        }


def compare_zones(
    *,
    exploration_direction: int,
    holdout_direction: int,
    exploration_effect: float,
    holdout_effect: float,
    exploration_ci: tuple[float, float],
    holdout_ci: tuple[float, float],
    effect_tolerance: float = 0.1,
) -> ZoneComparison:
    """Compare exploration-zone vs holdout-zone results against the frozen
    replication criterion: same direction, small effect-size drift, and CI
    overlap.  Reports honestly; never re-consumes the holdout zone."""
    direction_consistent = (exploration_direction == holdout_direction) or (
        exploration_direction == 0 or holdout_direction == 0
    )
    effect_diff = abs(exploration_effect - holdout_effect)
    interval_overlap = _overlaps(exploration_ci, holdout_ci)
    replication_passed = (
        direction_consistent and effect_diff <= effect_tolerance and interval_overlap
    )
    return ZoneComparison(
        direction_consistent=direction_consistent,
        effect_size_diff=effect_diff,
        interval_overlap=interval_overlap,
        replication_passed=replication_passed,
        note="" if replication_passed else "replication criterion not met; reported as-is",
    )


def _overlaps(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return not (a[1] < b[0] or b[1] < a[0])
