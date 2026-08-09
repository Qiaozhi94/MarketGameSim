"""T201 (A-005): typed scan axes for the parameter sweep.

Defines the three typed scan axes of 0.1.3 §2 -- leverage-cap distribution,
``maint_bp`` and market-maker thickness -- and validates each axis' values:

- leverage-cap distribution probabilities sum to 10000 (万分率);
- ``maint_bp < target_bp <= initial_bp``;
- quote-quantity (MM thickness) boundary checks.

Each axis is type-checked so a scan cannot silently mix dimensions
(proxy-strategy §12): an axis knows its own value type and rejects malformed
members (fail-closed).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass


class ScanAxisError(RuntimeError):
    """Raised when a scan axis or its values are invalid."""


class ScanAxis(abc.ABC):
    name: str
    description: str

    @abc.abstractmethod
    def validate(self) -> list[str]:
        """Return a list of violation strings (empty when valid)."""


@dataclass
class LeverageDistributionAxis(ScanAxis):
    """Leverage-cap distribution as a dict tier -> 万分率 probability."""

    name: str = "leverage_tier_distribution"
    description: str = "leverage cap distribution (万分率 probabilities)"
    distribution: dict[int, int] | None = None

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self.distribution:
            return ["leverage distribution is empty"]
        if any(t < 1 for t in self.distribution):
            problems.append("leverage tiers must be >= 1")
        total = sum(self.distribution.values())
        if total != 10_000:
            problems.append(f"leverage probabilities sum to {total}, expected 10000")
        return problems


@dataclass
class MaintBpAxis(ScanAxis):
    name: str = "maint_bp"
    description: str = "maintenance margin (万分率)"
    values: list[int] | None = None
    target_bp: int = 1000
    initial_bp: int = 10_000

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self.values:
            return ["maint_bp values are empty"]
        for v in self.values:
            if not (v < self.target_bp <= self.initial_bp):
                problems.append(
                    f"maint_bp={v} violates maint_bp < target_bp <= initial_bp "
                    f"(v < {self.target_bp} <= {self.initial_bp})"
                )
        return problems


@dataclass
class MmThicknessAxis(ScanAxis):
    name: str = "mm_thickness"
    description: str = "market maker quote quantity (thickness)"
    values: list[int] | None = None
    min_thickness: int = 0

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self.values:
            return ["mm_thickness values are empty"]
        for v in self.values:
            if v <= self.min_thickness:
                problems.append(f"mm_thickness={v} must be > {self.min_thickness}")
        return problems
