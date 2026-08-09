"""T203 (方法论 §9.4): coarse/fine sweep refinement.

Pre-registers coarse- and fine-sweep rules: a refinement trigger threshold,
a maximum number of refinement levels, and a total budget.  Fine-sweep
regions are generated automatically by the frozen refinement rule -- never by
humanly picking regions after seeing results.

Given a coarse-sweep failure boundary (T205), the rule bisects the bracketing
interval and re-sweeps at higher resolution, up to ``max_levels``, staying
within the total per-level cell budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class RefinementError(RuntimeError):
    """Raised when a fine-sweep refinement cannot be generated."""


@dataclass
class RefinementRule:
    trigger_threshold: float
    max_levels: int
    level_budget: int

    def validate(self) -> list[str]:
        problems: list[str] = []
        if self.max_levels < 1:
            problems.append("max_levels must be >= 1")
        if self.level_budget < 2:
            problems.append("level_budget must be >= 2")
        return problems


@dataclass
class FineSweepRegion:
    level: int
    interval: tuple[Any, Any]
    points: list[Any]

    def as_dict(self) -> dict[str, Any]:
        return {"level": self.level, "interval": list(self.interval), "points": self.points}


def generate_fine_sweep(
    rule: RefinementRule,
    boundary_interval: tuple[Any, Any],
    *,
    integer_axis: bool = True,
) -> list[FineSweepRegion]:
    """Generate fine-sweep regions by bisecting the coarse boundary interval.

    Each level splits the previous interval into ``level_budget`` points; up
    to ``max_levels`` levels are produced.  The regions are generated purely
    from the frozen rule + boundary interval -- no human selection.
    """
    problems = rule.validate()
    if problems:
        raise RefinementError("invalid refinement rule: " + "; ".join(problems))

    lo, hi = boundary_interval
    if lo == hi:
        raise RefinementError("boundary interval endpoints are equal")

    regions: list[FineSweepRegion] = []
    cur_lo, cur_hi = (lo, hi) if lo < hi else (hi, lo)
    for level in range(1, rule.max_levels + 1):
        step = (cur_hi - cur_lo) / rule.level_budget
        points = []
        for k in range(1, rule.level_budget):
            p = cur_lo + step * k
            points.append(int(p) if integer_axis else p)
        # dedup identical integer points
        points = _dedup(points)
        regions.append(FineSweepRegion(level=level, interval=(cur_lo, cur_hi), points=points))
        if len(points) >= 2:
            cur_lo, cur_hi = points[0], points[-1]
        else:
            break
    return regions


def _dedup(points: list[Any]) -> list[Any]:
    out: list[Any] = []
    for p in points:
        if p not in out:
            out.append(p)
    return out
