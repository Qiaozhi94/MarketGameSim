"""0.4.1 T968 (FR-503 / AC-503): the trend-following family, multi time scale.

Reads completed bars (``I2``) and compares a fast against a slow moving
average of closes.  "Multi time scale" is per *agent*, not per family: the
family owns a frozen table of ``(fast, slow)`` bar windows and each agent
picks one by ``model_private_state["time_scale_index"]``, so one roster entry
can spread its agents across horizons -- which is what makes trend followers
disagree with each other instead of moving as one block.

No signal means ``no_action``: a trend follower that re-posts every tick while
the averages are flat manufactures volume unrelated to the market (the same
reason the threshold goal model has a hold band).

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

FAMILY_ID = "trend_following"

#: Frozen ``(fast_bars, slow_bars)`` horizons (spec §3: 多时间尺度).
TIME_SCALES: tuple[tuple[int, int], ...] = ((3, 12), (5, 30), (10, 60))


@dataclass(frozen=True)
class TrendFollowing(TraderStrategy):
    """Fast-vs-slow moving average crossover on completed bars."""

    entry_threshold_bp: int = 20
    k_x1000: int = 500
    family_id: str = FAMILY_ID
    info_tier: InformationTier = InformationTier.I2
    protocol_version: int = 1

    def __post_init__(self) -> None:
        if type(self.entry_threshold_bp) is not int or self.entry_threshold_bp <= 0:
            raise StrategyLayerError(
                "INVALID_FAMILY_PARAMS", f"{FAMILY_ID}: entry_threshold_bp must be a positive int"
            )
        if type(self.k_x1000) is not int or not 1 <= self.k_x1000 <= 1000:
            raise StrategyLayerError(
                "INVALID_FAMILY_PARAMS", f"{FAMILY_ID}: k_x1000 must be in [1, 1000]"
            )

    def time_scale(self, state: AgentInternalStateV1) -> tuple[int, int]:
        """The agent's ``(fast, slow)`` windows; unknown index fails closed."""
        index = state.model_private_state.get("time_scale_index", 0)
        if type(index) is not int or not 0 <= index < len(TIME_SCALES):
            raise StrategyLayerError(
                "INVALID_TIME_SCALE",
                f"{FAMILY_ID}: time_scale_index {index!r} outside 0..{len(TIME_SCALES) - 1}",
            )
        return TIME_SCALES[index]

    def decide(
        self,
        info: TieredInformationSet,
        state: AgentInternalStateV1,
        prefs: AgentPreferences,
    ) -> StrategyDecision:
        fast_window, slow_window = self.time_scale(state)
        mark = mark_ticks(info)
        if mark is None:
            return self._no_action(state, REASON_NO_MARK)
        bars = info.completed_bars or ()
        if len(bars) < slow_window:
            return self._no_action(state, REASON_INSUFFICIENT_HISTORY)
        closes = tuple(bar.close for bar in bars)
        fast_ma = mean_int(closes[-fast_window:])
        slow_ma = mean_int(closes[-slow_window:])
        spread_bp = deviation_bp(fast_ma, slow_ma)
        if abs(spread_bp) < self.entry_threshold_bp:
            return self._no_action(state, REASON_NO_SIGNAL)
        ceiling = max_position_units(info, prefs, mark, k_x1000=self.k_x1000)
        if ceiling <= 0:
            return self._no_action(state, REASON_NO_BUDGET)
        target = ceiling if spread_bp > 0 else -ceiling
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


__all__ = ["FAMILY_ID", "TIME_SCALES", "TrendFollowing"]
