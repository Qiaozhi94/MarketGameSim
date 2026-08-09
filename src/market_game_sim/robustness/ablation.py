"""T301/T302 (FR-010, KR-004): five-factor ablation.

Provides independent enable/disable switches for the five belief factors --
momentum, reversion, herding, book, noise.  Disabling one factor removes only
that factor's entry from the weight vector and renormalizes the rest per the
pre-registered rule (uniform rescale so the remaining weights sum to 1); all
other configuration and random mechanisms are unchanged.

Ablation must not shift the random stream of the retained factors (T302): the
noise factor is drawn per (mechanism, decision_index, draw_index) in
``handler._compute_belief_signal`` independently of the weights, so disabling
a factor never consumes or reorders another factor's draw.
"""

from __future__ import annotations

from decimal import Decimal

FACTOR_ORDER = ("momentum", "reversion", "herding", "book", "noise")


class AblationError(RuntimeError):
    """Raised on an invalid ablation configuration."""


def factor_index(name: str) -> int:
    if name not in FACTOR_ORDER:
        raise AblationError(f"unknown factor {name!r}; valid: {FACTOR_ORDER}")
    return FACTOR_ORDER.index(name)


def ablated_weight_vector(
    weights: list[Decimal], disabled: str | None
) -> tuple[list[Decimal], list[int]]:
    """Return ``(renormalized_weights, kept_indices)`` after disabling one
    factor (or none).

    Disabling removes the factor's weight and renormalizes the retained
    weights uniformly so they sum to 1 (the pre-registered renormalization
    rule of T301).  ``kept_indices`` are the original factor positions that
    survive, so the caller can drop the matching factor values.
    """
    if len(weights) != len(FACTOR_ORDER):
        raise AblationError(f"expected {len(FACTOR_ORDER)} weights, got {len(weights)}")
    if disabled is None:
        return list(weights), list(range(len(weights)))

    drop = factor_index(disabled)
    kept = [i for i in range(len(weights)) if i != drop]
    kept_weights = [weights[i] for i in kept]
    total = sum(kept_weights)
    if total == 0:
        raise AblationError("renormalization denominator is zero")
    scale = Decimal(1) / total
    renormalized = [w * scale for w in kept_weights]
    return renormalized, kept


def leave_one_out_disabled() -> list[str]:
    """The five leave-one-out ablation treatments (T303)."""
    return list(FACTOR_ORDER)
