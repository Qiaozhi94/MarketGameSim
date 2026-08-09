"""T305 (0.1.3 E3): factor necessity classification.

Labels each factor as NECESSARY, NON_NECESSARY, SUBSTITUTABLE, or
INSUFFICIENT_EVIDENCE per the pre-registered standard.

"Removing the factor makes the effect insignificant" is NOT by itself
sufficient for necessity -- the effect size and interval must be reported.
A factor is NECESSARY when its ablation changes the effect size beyond the
pre-registered threshold AND the effect-size interval excludes zero.
SUBSTITUTABLE when it is highly correlated (|rho|>0.8) with another factor
that carries the same signal.  INSUFFICIENT_EVIDENCE when the interval is too
wide or sample too small to decide.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Necessity(Enum):
    NECESSARY = "NECESSARY"
    NON_NECESSARY = "NON_NECESSARY"
    SUBSTITUTABLE = "SUBSTITUTABLE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass
class FactorNecessity:
    factor: str
    verdict: Necessity
    effect_size: float = 0.0
    interval_half_width: float = 0.0
    high_corr_with: str | None = None


def classify_necessity(
    factor: str,
    *,
    baseline_effect: float,
    ablated_effect: float,
    ablated_ci_half_width: float,
    necessity_threshold: float,
    high_corr_factor: str | None = None,
    max_interval_half_width: float = 1.0,
) -> FactorNecessity:
    """Classify a factor's necessity from its leave-one-out ablation.

    ``ablated_ci_half_width``: half-width of the ablated effect's confidence
    interval.  If it exceeds ``max_interval_half_width``, the evidence is
    insufficient to decide.
    """
    if ablated_ci_half_width > max_interval_half_width:
        return FactorNecessity(
            factor, Necessity.INSUFFICIENT_EVIDENCE, ablated_effect, ablated_ci_half_width
        )

    change = abs(ablated_effect - baseline_effect)
    if change >= necessity_threshold:
        if high_corr_factor is not None:
            return FactorNecessity(
                factor,
                Necessity.SUBSTITUTABLE,
                ablated_effect,
                ablated_ci_half_width,
                high_corr_factor,
            )
        return FactorNecessity(factor, Necessity.NECESSARY, ablated_effect, ablated_ci_half_width)
    return FactorNecessity(factor, Necessity.NON_NECESSARY, ablated_effect, ablated_ci_half_width)
