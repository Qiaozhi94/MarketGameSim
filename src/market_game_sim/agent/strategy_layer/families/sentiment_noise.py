"""0.4.1 T969 (FR-503 / AC-503): the sentiment-noise family.

Uninformed flow: a mood drawn per ``(agent, decision)`` decides the side and
the fraction of the risk budget.  It reads only ``I0`` -- top of book plus its
own account -- because its whole point is that it is *not* reacting to
information; it is the liquidity the informed families trade against.

The draw is keyed (``master_seed``, ``agent_id``, ``strategy_sentiment_noise``,
``decision_index``) via ``blake2b_uniform``: never ``random``, so the same
roster and seed replay point for point (KR-004 / NFR-502).  Inside the
neutral band the agent does nothing, which keeps noise flow from degenerating
into a constant two-sided stream.

Stdlib only (KR-005).  Integer arithmetic, ``trunc`` toward zero (ADR-001).
"""

from __future__ import annotations

from dataclasses import dataclass

from market_game_sim.agent.goal import AgentInternalStateV1, AgentPreferences, trunc_toward_zero
from market_game_sim.agent.strategy_layer.families._common import (
    REASON_NO_BUDGET,
    REASON_NO_MARK,
    REASON_NO_SIGNAL,
    draw_context,
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
from market_game_sim.rng.distributions import blake2b_uniform

FAMILY_ID = "sentiment_noise"

#: Keyed-draw mechanism; distinct from every existing mechanism (KR-004).
MECHANISM_SENTIMENT = "strategy_sentiment_noise"


@dataclass(frozen=True)
class SentimentNoise(TraderStrategy):
    """Keyed-random mood in ``[-1000, 1000]`` x1000, with a neutral band."""

    neutral_band_x1000: int = 300
    k_x1000: int = 400
    family_id: str = FAMILY_ID
    info_tier: InformationTier = InformationTier.I0
    protocol_version: int = 1

    def __post_init__(self) -> None:
        if type(self.neutral_band_x1000) is not int or not 0 <= self.neutral_band_x1000 < 1000:
            raise StrategyLayerError(
                "INVALID_FAMILY_PARAMS", f"{FAMILY_ID}: neutral_band_x1000 must be in [0, 1000)"
            )
        if type(self.k_x1000) is not int or not 1 <= self.k_x1000 <= 1000:
            raise StrategyLayerError(
                "INVALID_FAMILY_PARAMS", f"{FAMILY_ID}: k_x1000 must be in [1, 1000]"
            )

    def mood_x1000(self, state: AgentInternalStateV1) -> int:
        """Mood in ``[-1000, 1000)`` x1000 from one keyed uniform draw."""
        ctx = draw_context(state, FAMILY_ID)
        u = blake2b_uniform(
            ctx.master_seed, ctx.agent_id, MECHANISM_SENTIMENT, ctx.decision_index, 0
        )
        return int(u * 2000) - 1000

    def decide(
        self,
        info: TieredInformationSet,
        state: AgentInternalStateV1,
        prefs: AgentPreferences,
    ) -> StrategyDecision:
        mood = self.mood_x1000(state)
        mark = mark_ticks(info)
        if mark is None:
            return self._no_action(state, REASON_NO_MARK)
        if abs(mood) <= self.neutral_band_x1000:
            return self._no_action(state, REASON_NO_SIGNAL)
        ceiling = max_position_units(info, prefs, mark, k_x1000=self.k_x1000)
        if ceiling <= 0:
            return self._no_action(state, REASON_NO_BUDGET)
        target = trunc_toward_zero(mood * ceiling, 1000)
        if target == 0:
            return self._no_action(state, REASON_NO_BUDGET)
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


__all__ = ["FAMILY_ID", "MECHANISM_SENTIMENT", "SentimentNoise"]
