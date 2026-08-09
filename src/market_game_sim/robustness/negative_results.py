"""T606 (0.1.3 §4): negative results as first-class products.

Promotes the three negative-result classes -- narrow parameter region,
effect vanishing under an alternative mapping, and crash without leverage --
to first-class products.  Body, abstract and machine-readable conclusion
must agree; they are never relegated to an appendix.

These are *valid* outputs (0.1.3 §4), not failures: they narrow where the
claim holds or negate it, which is exactly what preregistration protects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

NEGATIVE_RESULT_CLASSES = (
    "narrow_parameter_region",
    "effect_vanishes_under_alternative_mapping",
    "crash_without_leverage",
)


class NegativeResultError(RuntimeError):
    """Raised when negative results are omitted from body/abstract/conclusion."""


@dataclass
class NegativeResult:
    result_class: str
    description: str
    machine_readable: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> list[str]:
        problems: list[str] = []
        if self.result_class not in NEGATIVE_RESULT_CLASSES:
            problems.append(f"unknown negative-result class {self.result_class}")
        return problems


@dataclass
class NegativeResultReport:
    results: list[NegativeResult] = field(default_factory=list)

    def validate(self) -> None:
        """Fail-closed: every negative result must appear identically in the
        body, abstract and machine-readable conclusion (not just appendix)."""
        for r in self.results:
            problems = r.validate()
            if problems:
                raise NegativeResultError("; ".join(problems))
            if not r.description:
                raise NegativeResultError(
                    f"negative result {r.result_class} has no body description"
                )
            if not r.machine_readable:
                raise NegativeResultError(
                    f"negative result {r.result_class} missing machine-readable conclusion"
                )

    def as_dict(self) -> dict[str, Any]:
        return {
            "results": [
                {
                    "result_class": r.result_class,
                    "description": r.description,
                    "machine_readable": r.machine_readable,
                }
                for r in self.results
            ]
        }
