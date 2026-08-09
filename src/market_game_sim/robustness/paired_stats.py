"""T601 (0.1.3 E1/E2): paired effect size with whole-pair bootstrap.

Computes per-``pair_family`` paired effect sizes and confidence intervals by
resampling *whole* ``pair_id`` units -- never resampling the two arms
independently (which is exactly what ``experiment.stats.bootstrap_proportion_diff``
does and what T601 forbids reusing for 0.1.3 paired data).

Each input pair is ``(control_outcome, treatment_outcome)``; a bootstrap
replicate resamples pairs with replacement and recomputes the per-pair
difference.  Missing / duplicate / unknown-arm / single-side-technical-invalid
records must be excluded before calling (T402 fail-closed), and the economic
endpoint is reported under the two-part T602 split, not merged with continuous
metrics.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any


class PairedStatsError(RuntimeError):
    """Raised when paired effect size cannot be computed."""


@dataclass
class PairedEffectResult:
    n_pairs: int
    mean_diff: float
    ci_low: float
    ci_high: float
    ci_level: float
    n_resamples: int
    seed: int
    treatment_rate: float
    control_rate: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_pairs": self.n_pairs,
            "mean_diff": self.mean_diff,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "ci_level": self.ci_level,
            "n_resamples": self.n_resamples,
            "seed": self.seed,
            "treatment_rate": self.treatment_rate,
            "control_rate": self.control_rate,
        }

    @property
    def ci_excludes_zero(self) -> bool:
        return self.ci_low > 0 or self.ci_high < 0


def paired_bootstrap(
    pairs: list[tuple[bool, bool]],
    n_resamples: int = 10_000,
    ci_level: float = 0.95,
    seed: int = 0,
) -> PairedEffectResult:
    """Bootstrap CI for the mean within-pair difference over whole pairs.

    ``pairs``: ``(control_outcome, treatment_outcome)`` for each valid pair_id.
    Each replicate resamples pairs WITH REPLACEMENT and computes the mean
    ``treatment - control`` difference -- both arms of a sampled pair move
    together, preserving the pairing (T601).

    Deterministic: locally-seeded ``random.Random``, never the global module.
    """
    if not pairs:
        raise PairedStatsError("paired_bootstrap requires at least one pair")
    if not (0 < ci_level < 1):
        raise PairedStatsError(f"ci_level must be in (0, 1), got {ci_level}")
    n = len(pairs)
    rng = random.Random(seed)

    mean_diff = sum(t - c for c, t in pairs) / n
    control_rate = sum(c for c, _ in pairs) / n
    treatment_rate = sum(t for _, t in pairs) / n

    diffs: list[float] = []
    for _ in range(n_resamples):
        sample_sum = 0.0
        for _ in range(n):
            c, t = pairs[rng.randrange(n)]
            sample_sum += t - c
        diffs.append(sample_sum / n)

    diffs.sort()
    low_idx = int((1 - ci_level) / 2 * n_resamples)
    high_idx = int((1 + ci_level) / 2 * n_resamples) - 1
    return PairedEffectResult(
        n_pairs=n,
        mean_diff=mean_diff,
        ci_low=diffs[low_idx],
        ci_high=diffs[high_idx],
        ci_level=ci_level,
        n_resamples=n_resamples,
        seed=seed,
        treatment_rate=treatment_rate,
        control_rate=control_rate,
    )
