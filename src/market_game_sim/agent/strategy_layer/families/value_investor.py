"""0.4.3 T1106 (FR-702 / AC-702): the value-investor family.

The one family whose reference price does **not** come from the market.  The
four 0.4.1 families judge "expensive" against the market's own history, so
their fair value drifts with the price -- the stabiliser is persuaded rather
than defeated (0.4.1 报告 §16).  This family holds a constant reference
``v_t`` and leans against the deviation from it::

    dev_bp    = (mark - v_t) * 10000 / v_t
    fraction  = min(1000, sensitivity_x1000 * |dev_bp| / 100) / 1000
    target    = -sign(dev_bp) * trunc(fraction * max_position_units)

so the further price runs from ``v_t``, the larger the opposing position, up to
the family's position ceiling.  At ``v_t`` the target is flat -- unlike the
signal families this one *does* unwind when the deviation closes, because a
value view held at fair value is a position of zero.

**Where ``v_t`` comes from** (spec IR-701): the roster derives
``v_t = engine.initial_price_ticks`` and writes it into this family's
per-agent ``strategy_private`` together with ``sensitivity_x1000``; the runtime
merges that into ``model_private_state``.  It is never part of a tiered
information set, so no other family -- and no human -- can see it.  A state
without it fails closed: a value investor with no value would otherwise have to
invent one.

ADR-017 permits a constant reference only; nothing here moves ``v_t``.

Stdlib only (KR-005).  Integer arithmetic, ``trunc`` toward zero (ADR-001).
"""

from __future__ import annotations

from dataclasses import dataclass

from market_game_sim.agent.goal import (
    AgentInternalStateV1,
    AgentPreferences,
    trunc_toward_zero,
)
from market_game_sim.agent.strategy_layer.families._common import (
    REASON_NO_BUDGET,
    REASON_NO_MARK,
    deviation_bp,
    mark_ticks,
    max_position_units,
)
from market_game_sim.agent.strategy_layer.protocol import (
    ACTION_NO_ACTION,
    ACTION_TARGET_POSITION,
    InformationTier,
    StrategyDecision,
    StrategyLayerError,
    TieredInformationSet,
    TraderStrategy,
)

FAMILY_ID = "value_investor"

#: ``model_private_state`` keys the roster writes for this family (IR-701).
VALUE_REFERENCE_KEY = "value_reference_ticks"
SENSITIVITY_KEY = "sensitivity_x1000"

#: Spec FR-702: per-mille of the ceiling per 1% (100 bp) of deviation.
SENSITIVITY_MIN = 1
SENSITIVITY_MAX = 1_000_000


def _private_int(state: AgentInternalStateV1, key: str, minimum: int, maximum: int) -> int:
    value = state.model_private_state.get(key)
    if type(value) is not int or not minimum <= value <= maximum:
        raise StrategyLayerError(
            "MISSING_VALUE_REFERENCE",
            f"{FAMILY_ID}: model_private_state.{key} must be an int in "
            f"[{minimum}, {maximum}], got {value!r}",
        )
    return value


def value_reference(state: AgentInternalStateV1) -> int:
    """The agent's constant reference ``v_t`` in ticks; absent or invalid fails closed."""
    return _private_int(state, VALUE_REFERENCE_KEY, 1, 2**63 - 1)


def sensitivity(state: AgentInternalStateV1) -> int:
    """The agent's ``sensitivity_x1000``; absent or out of range fails closed."""
    return _private_int(state, SENSITIVITY_KEY, SENSITIVITY_MIN, SENSITIVITY_MAX)


def target_fraction_x1000(dev_bp: int, sensitivity_x1000: int) -> int:
    """Per-mille of the ceiling the family wants at ``dev_bp``; monotone in ``|dev_bp|``."""
    return min(1000, sensitivity_x1000 * abs(dev_bp) // 100)


@dataclass(frozen=True)
class ValueInvestor(TraderStrategy):
    """Lean against the deviation of the mark from a constant reference ``v_t``."""

    family_id: str = FAMILY_ID
    info_tier: InformationTier = InformationTier.I0
    protocol_version: int = 1

    def decide(
        self,
        info: TieredInformationSet,
        state: AgentInternalStateV1,
        prefs: AgentPreferences,
    ) -> StrategyDecision:
        reference = value_reference(state)
        sensitivity_x1000 = sensitivity(state)
        mark = mark_ticks(info)
        if mark is None:
            return self._no_action(state, REASON_NO_MARK)
        ceiling = max_position_units(info, prefs, mark, k_x1000=1000)
        if ceiling <= 0:
            return self._no_action(state, REASON_NO_BUDGET)
        dev_bp = deviation_bp(mark, reference)
        size = trunc_toward_zero(target_fraction_x1000(dev_bp, sensitivity_x1000) * ceiling, 1000)
        # Rich -> short, cheap -> long; at the reference, flat.
        target = -size if dev_bp > 0 else size
        return StrategyDecision(
            family_id=self.family_id,
            info_tier=self.info_tier,
            action=ACTION_TARGET_POSITION,
            updated_state=state,
            target_position_units=target,
        )

    def _no_action(self, state: AgentInternalStateV1, reason: str) -> StrategyDecision:
        return StrategyDecision(
            family_id=self.family_id,
            info_tier=self.info_tier,
            action=ACTION_NO_ACTION,
            updated_state=state,
            reason_code=reason,
        )


__all__ = [
    "FAMILY_ID",
    "SENSITIVITY_KEY",
    "SENSITIVITY_MAX",
    "SENSITIVITY_MIN",
    "VALUE_REFERENCE_KEY",
    "ValueInvestor",
    "sensitivity",
    "target_fraction_x1000",
    "value_reference",
]
