"""T404/T405 (KPI-008 empty-set guard, KPI-010): report-generator guards.

T404: 0.1.3 does not arrange evidence for the four capability dimensions
(funding / information / speed / execution) -- so any capability-attribution
text in a report must be an empty set.  A capability attribution that lacks
any of the required evidence items (treatment-field diff, shared random-path
audit, paired sample size, effect size, confidence interval) must be rejected
at generation (fail-closed), never silently defaulted to "empty and thus ok".

T405: the report generator rejects conclusion-style wording backed by a
single run, a single price path, or fewer than the minimum paired sample
size; such claims may only be listed separately as "探索性观察".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CAPABILITY_DIMENSIONS = ("funding", "information", "speed", "execution")
REQUIRED_EVIDENCE = (
    "treatment_field_diff",
    "shared_random_path_audit",
    "paired_sample_size",
    "effect_size",
    "confidence_interval",
)


class ReportGuardError(RuntimeError):
    """Raised when a report tries to emit a forbidden claim."""


@dataclass
class CapabilityAttribution:
    dimension: str
    evidence: dict[str, Any]


def validate_capability_attributions(
    attributions: list[CapabilityAttribution],
) -> list[str]:
    """Return the ids of attributions missing required evidence (fail-closed:
    none may be missing).  An empty list means the capability-attribution set
    is legitimately empty / fully-evidenced."""
    violations: list[str] = []
    for attr in attributions:
        if attr.dimension not in CAPABILITY_DIMENSIONS:
            violations.append(f"unknown capability dimension {attr.dimension}")
            continue
        # presence check, not truthiness: effect_size 0.0 and empty CI are
        # legitimate evidence values, not missing evidence
        missing = [e for e in REQUIRED_EVIDENCE if attr.evidence.get(e) is None]
        if missing:
            violations.append(f"{attr.dimension} attribution missing evidence: {missing}")
    return violations


def guard_capability_attributions(
    attributions: list[CapabilityAttribution],
) -> None:
    """Raise ReportGuardError if any capability attribution is unevidenced.

    0.1.3 produces no capability-attribution evidence, so the only acceptable
    set is empty; any non-empty attribution must carry every required item."""
    violations = validate_capability_attributions(attributions)
    if violations:
        raise ReportGuardError("capability attribution guard: " + "; ".join(violations))


def validate_conclusion_wording(
    *,
    n_seeds: int,
    n_paired_samples: int,
    min_paired_samples: int,
    wording: str,
) -> list[str]:
    """Return violation strings for conclusion-style wording that lacks the
    required paired-sample evidence (KPI-010: no single-run/path conclusion).
    """
    violations: list[str] = []
    if n_seeds < 2:
        violations.append(f"n_seeds={n_seeds} < 2 (KPI-010: no single-run conclusion)")
    if n_paired_samples < min_paired_samples:
        violations.append(f"n_paired_samples={n_paired_samples} < min={min_paired_samples}")
    return violations


def guard_conclusion(
    *,
    n_seeds: int,
    n_paired_samples: int,
    min_paired_samples: int,
    conclusion_wording: str,
) -> None:
    """Reject conclusion-style wording backed by insufficient paired samples.

    Allows the wording only as an explicit "探索性观察" when the evidence
    gate fails."""
    violations = validate_conclusion_wording(
        n_seeds=n_seeds,
        n_paired_samples=n_paired_samples,
        min_paired_samples=min_paired_samples,
        wording=conclusion_wording,
    )
    if violations:
        raise ReportGuardError(
            "conclusion guard: " + "; ".join(violations) + " (只能作为探索性观察)"
        )
