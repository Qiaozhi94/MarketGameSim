"""0.4.1 T968 (FR-503 / AC-503): the mean-reversion family.

Reads the recent public tape (``I1``) and fades deviations: the last traded
price far above the window mean is sold, far below is bought.  It is the
structural counterparty to :mod:`.trend_following` -- the two disagree by
construction, which is where price discovery comes from (ADR-011 §决策 3).

Inside the band the family returns ``no_action``; it does not re-post on every
observation just because it holds an opinion.

Stdlib only (KR-005).  Integer arithmetic, ``trunc`` toward zero (ADR-001).
"""

from __future__ import annotations

from dataclasses import dataclass

from market_game_sim.agent.goal import AgentInternalStateV1, AgentPreferences
from market_game_sim.agent.strategy_layer.families._common import (
    REASON_INSUFFICIENT_HISTORY,
    REASON_NO_BUDGET,
    REASON_NO_MARK,
    REASON_NO_SIGNAL,
    deviation_bp,
    mark_ticks,
    max_position_units,
    mean_int,
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

FAMILY_ID = "mean_reversion"


@dataclass(frozen=True)
class MeanReversion(TraderStrategy):
    """Fade deviations of the last trade from the tape-window mean."""

    window_trades: int = 20
    entry_threshold_bp: int = 30
    k_x1000: int = 500
    family_id: str = FAMILY_ID
    info_tier: InformationTier = InformationTier.I1
    protocol_version: int = 1

    def __post_init__(self) -> None:
        if type(self.window_trades) is not int or self.window_trades < 2:
            raise StrategyLayerError(
                "INVALID_FAMILY_PARAMS", f"{FAMILY_ID}: window_trades must be an int >= 2"
            )
        if type(self.entry_threshold_bp) is not int or self.entry_threshold_bp <= 0:
            raise StrategyLayerError(
                "INVALID_FAMILY_PARAMS", f"{FAMILY_ID}: entry_threshold_bp must be a positive int"
            )
        if type(self.k_x1000) is not int or not 1 <= self.k_x1000 <= 1000:
            raise StrategyLayerError(
                "INVALID_FAMILY_PARAMS", f"{FAMILY_ID}: k_x1000 must be in [1, 1000]"
            )

    def decide(
        self,
        info: TieredInformationSet,
        state: AgentInternalStateV1,
        prefs: AgentPreferences,
    ) -> StrategyDecision:
        mark = mark_ticks(info)
        if mark is None:
            return self._no_action(state, REASON_NO_MARK)
        trades = info.public_trades or ()
        if len(trades) < self.window_trades:
            return self._no_action(state, REASON_INSUFFICIENT_HISTORY)
        prices = tuple(trade.price_ticks for trade in trades[-self.window_trades :])
        window_mean = mean_int(prices)
        gap_bp = deviation_bp(prices[-1], window_mean)
        if abs(gap_bp) < self.entry_threshold_bp:
            return self._no_action(state, REASON_NO_SIGNAL)
        ceiling = max_position_units(info, prefs, mark, k_x1000=self.k_x1000)
        if ceiling <= 0:
            return self._no_action(state, REASON_NO_BUDGET)
        # Fade: price above the mean -> short, below -> long.
        target = -ceiling if gap_bp > 0 else ceiling
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


__all__ = ["FAMILY_ID", "MeanReversion"]
