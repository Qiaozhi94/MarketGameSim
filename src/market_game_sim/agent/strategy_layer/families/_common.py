"""0.4.1 T968/T969: shared helpers for the native strategy families.

Two things every native family needs and neither may improvise:

* **Sizing** -- the equity -> max-position ladder is the one already frozen for
  the goal layer (``risk_budget_linear_v1``); the families reuse
  :func:`market_game_sim.agent.goal.equity_units` /
  :func:`~market_game_sim.agent.goal.valuation_mark_ticks` /
  :func:`~market_game_sim.agent.goal.trunc_toward_zero` rather than carrying a
  second copy of that arithmetic.
* **Randomness** -- a family never touches ``random``; every draw is keyed by
  ``(master_seed, agent_id, mechanism, decision_index, draw_index)`` through
  :func:`market_game_sim.rng.distributions.blake2b_uniform` (KR-004), so the
  same roster + seed replays point for point.  The identity needed for that
  key lives in the agent's own ``model_private_state`` and is read here; a
  family that draws without it fails closed (``MISSING_DRAW_CONTEXT``) instead
  of silently falling back to an unkeyed source.

Stdlib only (KR-005).  Integer arithmetic, ``trunc`` toward zero (ADR-001).
"""

from __future__ import annotations

from dataclasses import dataclass

from market_game_sim.agent.goal import (
    AgentInternalStateV1,
    AgentPreferences,
    equity_units,
    trunc_toward_zero,
    valuation_mark_ticks,
)
from market_game_sim.agent.strategy_layer.protocol import (
    StrategyLayerError,
    TieredInformationSet,
)

#: Contract multiplier used by the existing goal layer (账户合同 §2.2).  The
#: families size against this value, so an assembly whose engine uses another
#: ``mult`` is refused at roster parse time (0.4.3 T1100) rather than letting the
#: two disagree silently.
DEFAULT_MULT = 1000

#: Magnitude sentinel (0.4.3 T1104 / NFR-701).  Real exchanges top out at
#: roughly 100x leverage; a ceiling implying more than that is a unit error, not
#: an aggressive parameter -- the sizing contract itself only reaches 20x
#: (``risk_appetite_x1000`` <= 20000, ``k_x1000`` <= 1000).  The bound is an
#: external fact, not a tuning knob: raising it needs evidence that real venues
#: allow more, not a market that would pass a gate with it.
MAX_PLAUSIBLE_LEVERAGE = 100

# Reason codes carried by ``no_action`` decisions.  Stable and safe to assert
# on; a new reason is a new constant, never a reworded string.
REASON_NO_MARK = "NO_VALUATION_MARK"
REASON_NO_BUDGET = "NO_RISK_BUDGET"
REASON_INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
REASON_NO_SIGNAL = "NO_SIGNAL"
REASON_PRICE_OUT_OF_RANGE = "PRICE_OUT_OF_RANGE"


@dataclass(frozen=True)
class DrawContext:
    """Per-agent identity for keyed draws (代理策略 §10.1)."""

    master_seed: int
    agent_id: str
    decision_index: int


def draw_context(state: AgentInternalStateV1, family_id: str) -> DrawContext:
    """Read the keyed-draw identity out of ``model_private_state``.

    Fail closed: a family that needs a draw but was handed a state without the
    identity raises rather than drawing from an unkeyed source -- an unkeyed
    draw would reproduce differently on the next run and silently break
    NFR-502.
    """
    bag = state.model_private_state
    master_seed = bag.get("master_seed")
    agent_id = bag.get("agent_id")
    decision_index = bag.get("decision_index", 0)
    if type(master_seed) is not int:
        raise StrategyLayerError(
            "MISSING_DRAW_CONTEXT", f"{family_id}: model_private_state.master_seed must be int"
        )
    if type(agent_id) is not str or not agent_id:
        raise StrategyLayerError(
            "MISSING_DRAW_CONTEXT",
            f"{family_id}: model_private_state.agent_id must be a non-empty str",
        )
    if type(decision_index) is not int or decision_index < 0:
        raise StrategyLayerError(
            "MISSING_DRAW_CONTEXT",
            f"{family_id}: model_private_state.decision_index must be a non-negative int",
        )
    return DrawContext(master_seed=master_seed, agent_id=agent_id, decision_index=decision_index)


def mark_ticks(info: TieredInformationSet) -> int | None:
    """Valuation mark in whole ticks, or ``None`` when the book gives none."""
    return valuation_mark_ticks(info.book_top)


def assert_plausible_leverage(position_units: int, mark: int, mult: int, equity: int) -> None:
    """Fail closed when a position ceiling implies more than 100x leverage.

    ``|position| * mark * MULT`` is the notional (账户合同 §2.2); compared against
    equity it is the leverage the ceiling asks for.  Past
    :data:`MAX_PLAUSIBLE_LEVERAGE` the arithmetic is wrong, so this raises
    instead of handing the number to the ledger -- which would quietly clip it
    and hide the bug, as it hid the missing ``MULT`` for two days (0.4.1 报告 §19.5).
    """
    if equity <= 0:
        return
    if abs(position_units) * mark * mult > MAX_PLAUSIBLE_LEVERAGE * equity:
        raise StrategyLayerError(
            "IMPLAUSIBLE_LEVERAGE",
            f"position ceiling {position_units} at mark {mark} x MULT {mult} implies more "
            f"than {MAX_PLAUSIBLE_LEVERAGE}x leverage on equity {equity}: a unit error",
        )


def max_position_units(
    info: TieredInformationSet,
    prefs: AgentPreferences,
    mark: int,
    *,
    k_x1000: int,
    mult: int = DEFAULT_MULT,
) -> int:
    """Risk-budget position ceiling, scaled by the family's ``k_x1000``.

    equity -> max notional -> max position, then the family's own fraction.
    Notional is ``position * mark * MULT``, so the position divides by both
    (0.4.3 T1100).  ``risk_budget_linear_v1`` in ``agent/goal.py``, which this
    was copied from, still divides by ``mark`` alone; that copy is frozen v0.1
    contract and is registered as a known defect (0.4.3 T1101), not fixed here.
    Returns 0 when the budget is exhausted; the caller turns that into
    ``no_action`` rather than a zero-size order.
    """
    eq = equity_units(info.own_account, mark, mult)
    max_notional = eq * prefs.risk_appetite_x1000 // 1000
    if max_notional <= 0:
        return 0
    max_position = max_notional // (mark * mult)
    ceiling = trunc_toward_zero(k_x1000 * max_position, 1000)
    assert_plausible_leverage(ceiling, mark, mult, eq)
    return ceiling


def mean_int(values: tuple[int, ...]) -> int:
    """Integer mean, truncated toward zero (ADR-001)."""
    return trunc_toward_zero(sum(values), len(values))


def deviation_bp(value: int, reference: int) -> int:
    """``(value - reference) / reference`` in basis points, trunc toward zero."""
    if reference <= 0:
        return 0
    return trunc_toward_zero((value - reference) * 10_000, reference)


__all__ = [
    "DEFAULT_MULT",
    "MAX_PLAUSIBLE_LEVERAGE",
    "REASON_INSUFFICIENT_HISTORY",
    "REASON_NO_BUDGET",
    "REASON_NO_MARK",
    "REASON_NO_SIGNAL",
    "REASON_PRICE_OUT_OF_RANGE",
    "DrawContext",
    "assert_plausible_leverage",
    "deviation_bp",
    "draw_context",
    "mark_ticks",
    "max_position_units",
    "mean_int",
]
