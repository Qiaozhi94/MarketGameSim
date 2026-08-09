"""T205 (0.1.3 E2): effect failure-boundary localization.

Locates the parameter region where an effect first crosses a pre-registered
threshold, reporting the *interval and resolution* of discrete grid points --
never interpolating grid points into an unverified exact critical value
(0.1.3 §4: "不把离散网格点插值成未经验证的精确临界值").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class BoundaryError(RuntimeError):
    """Raised when a failure boundary cannot be determined."""


@dataclass
class FailureBoundary:
    axis: str
    crossing_index: int | None
    crossing_interval: tuple[Any, Any] | None
    resolution: Any
    threshold_crossed: bool = False
    monotonic_axis_ordered: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "axis": self.axis,
            "crossing_index": self.crossing_index,
            "crossing_interval": self.crossing_interval,
            "resolution": self.resolution,
            "threshold_crossed": self.threshold_crossed,
            "monotonic_axis_ordered": self.monotonic_axis_ordered,
        }


def locate_failure_boundary(
    axis_values: list[Any],
    effect_sizes: list[float],
    threshold: float,
    *,
    threshold_crossed_when: str = "above",  # "above" | "below"
) -> FailureBoundary:
    """Locate the first grid point (in axis order) where the effect crosses
    ``threshold``.

    ``threshold_crossed_when="above"``: failure when ``effect > threshold``.
    ``threshold_crossed_when="below"``: failure when ``effect < threshold``.

    Returns the crossing interval as the pair of adjacent axis values bracketing
    the threshold (grid resolution preserved, no interpolation).
    """
    if len(axis_values) != len(effect_sizes):
        raise BoundaryError("axis_values and effect_sizes lengths differ")
    if len(axis_values) < 2:
        raise BoundaryError("need at least two grid points to locate a boundary")

    crossed: list[int] = []
    for i, e in enumerate(effect_sizes):
        if threshold_crossed_when == "above":
            if e > threshold:
                crossed.append(i)
        elif threshold_crossed_when == "below":
            if e < threshold:
                crossed.append(i)
        else:
            raise BoundaryError(f"unknown threshold_crossed_when: {threshold_crossed_when}")

    if not crossed:
        return FailureBoundary(
            axis=axis_values[0],
            crossing_index=None,
            crossing_interval=None,
            resolution=None,
            threshold_crossed=False,
        )

    first = crossed[0]
    interval = (
        (axis_values[first - 1], axis_values[first])
        if first > 0
        else (axis_values[first], axis_values[first + 1])
    )
    resolution = abs(axis_values[first] - axis_values[first - 1]) if first > 0 else None
    return FailureBoundary(
        axis=str(axis_values[first]),
        crossing_index=first,
        crossing_interval=interval,
        resolution=resolution,
        threshold_crossed=True,
    )
