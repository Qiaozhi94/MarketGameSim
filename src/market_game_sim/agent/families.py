"""T006/E1: model-family implementations for the belief agent.

``_compute_belief_signal`` currently hardcodes one model family (the
five-factor belief-weight agent).  E1 needs at least two pre-registered
families actually implemented -- the registry metadata (T006) is not enough.
Each family is a pure function from (factor values, weights) to a signal:
families differ only in *which factors and how they are combined*, never in
the random mechanism (KR-004: same semantic keys keep the same draws).
"""

from __future__ import annotations

from decimal import Decimal

from market_game_sim.agent.factors import belief_signal

# momentum/reversion/herding/book/noise order (handler._compute_belief_signal)
FACTOR_ORDER = ("momentum", "reversion", "herding", "book", "noise")

# signal_family's structural choice: which factors it consumes, in what
# combination.  Deterministic and configurable (E1 family-defining field).
SIGNAL_FAMILY_FACTORS = ("momentum", "book")
SIGNAL_FAMILY_WEIGHTS = (Decimal("6000"), Decimal("4000"))  # 万分率 weights


class ModelFamilyError(RuntimeError):
    """Raised on an unknown model family."""


def _normalize(weights: list[Decimal]) -> list[Decimal]:
    total = sum(weights)
    if total == 0:
        raise ModelFamilyError("family weights sum to zero")
    return [w / total for w in weights]


def belief_family_signal(
    factor_values: list[Decimal],
    weights: list[Decimal],
    factor_names: tuple[str, ...] = FACTOR_ORDER,
) -> int:
    """The 0.1.2 baseline family: weighted sum over all five factors."""
    return belief_signal(weights, factor_values)


def signal_family_signal(
    factor_values: list[Decimal],
    weights: list[Decimal],
    factor_names: tuple[str, ...] = FACTOR_ORDER,
) -> int:
    """The pre-registered alternative family: combines only momentum+book.

    ``weights`` is ignored (the family defines its own fixed combination) --
    structurally distinct from the belief family, which is the E1
    family-defining difference.  Uses the same ``belief_signal`` normalization
    so the signal scale ([-10000, 10000]) is comparable across families.

    v013 (high) fix: factors are selected BY NAME, not by position.  After an
    ablation the list is shortened (e.g. removing book leaves
    momentum/reversion/herding/noise); selecting by original index would
    silently consume the WRONG factor.  ``factor_names`` must be the names of
    ``factor_values`` in order; missing names fail-closed.
    """
    if len(factor_names) != len(factor_values):
        raise ModelFamilyError(
            f"factor_names ({len(factor_names)}) / factor_values ({len(factor_values)}) "
            "length mismatch"
        )
    by_name = dict(zip(factor_names, factor_values, strict=True))
    missing = [f for f in SIGNAL_FAMILY_FACTORS if f not in by_name]
    if missing:
        raise ModelFamilyError(f"signal_family factors missing after ablation: {missing}")
    kept = [by_name[f] for f in SIGNAL_FAMILY_FACTORS]
    return belief_signal(_normalize(list(SIGNAL_FAMILY_WEIGHTS)), kept)


FAMILY_IMPLS = {
    "belief_family": belief_family_signal,
    "signal_family": signal_family_signal,
}


def family_signal(
    family_id: str,
    factor_values: list[Decimal],
    weights: list[Decimal],
    factor_names: tuple[str, ...] = FACTOR_ORDER,
) -> int:
    if family_id not in FAMILY_IMPLS:
        raise ModelFamilyError(f"unknown model family {family_id!r}")
    return FAMILY_IMPLS[family_id](factor_values, weights, factor_names)


def apply_ablation(
    factor_values: list[Decimal],
    weights: list[Decimal],
    disabled: str | None,
) -> tuple[list[Decimal], list[Decimal]]:
    """Remove ``disabled`` factor from both factor values and weights, and
    renormalize the retained weights to sum to 1 (T301 pre-registered rule).

    Lives in the agent layer (not robustness/) because the kernel decision
    path must consume it without violating the L2->L3 dependency rule
    (plan.md §2: agent must not import experiment/robustness).

    Backward-compatible 2-tuple view of :func:`apply_ablation_named`.
    """
    values, weights_out, _names = apply_ablation_named(factor_values, weights, disabled)
    return values, weights_out


def apply_ablation_named(
    factor_values: list[Decimal],
    weights: list[Decimal],
    disabled: str | None,
) -> tuple[list[Decimal], list[Decimal], tuple[str, ...]]:
    """v013 (high) fix: like :func:`apply_ablation` but also returns the
    retained factor NAMES in order, so a downstream family can select factors
    by name instead of by position on a shortened list."""
    if len(factor_values) != len(FACTOR_ORDER) or len(weights) != len(FACTOR_ORDER):
        raise ModelFamilyError(
            f"expected {len(FACTOR_ORDER)} factor values and weights, "
            f"got {len(factor_values)}/{len(weights)}"
        )
    if disabled is None:
        return list(factor_values), list(weights), FACTOR_ORDER
    if disabled not in FACTOR_ORDER:
        raise ModelFamilyError(f"unknown factor {disabled!r}")
    drop = FACTOR_ORDER.index(disabled)
    kept_idx = [i for i in range(len(factor_values)) if i != drop]
    kept_values = [factor_values[i] for i in kept_idx]
    kept_weights = [weights[i] for i in kept_idx]
    kept_names = tuple(FACTOR_ORDER[i] for i in kept_idx)
    total = sum(kept_weights)
    if total == 0:
        raise ModelFamilyError("renormalization denominator is zero")
    scale = Decimal(1) / total
    return kept_values, [w * scale for w in kept_weights], kept_names
