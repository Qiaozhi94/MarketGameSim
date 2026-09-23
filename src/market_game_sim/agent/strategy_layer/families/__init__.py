"""0.4.1 T968/T969: the native strategy families (FR-503).

Four families, deliberately heterogeneous -- price discovery comes from the
disagreement between them, not from any one of them being right (ADR-011
§决策 3):

===================  =====  =========================================
family_id            tier   what it does
===================  =====  =========================================
``trend_following``  I2     fast/slow MA crossover, per-agent horizon
``mean_reversion``   I1     fades deviations from the tape mean
``sentiment_noise``  I0     keyed-random mood, uninformed flow
``market_maker_v2``  I0     inventory quotes, per-agent dispersion
===================  =====  =========================================

Registration is explicit (:func:`register_native_families`), not an import
side effect: importing a module must not mutate the process-wide registry, or
test isolation and assembly-time fail-closed checks both become
import-order-dependent.  Registering twice into one registry raises
``DUPLICATE_STRATEGY_FAMILY`` -- assembly registers once (T966).
"""

from __future__ import annotations

from market_game_sim.agent.strategy_layer.families.market_maker_v2 import MarketMakerV2
from market_game_sim.agent.strategy_layer.families.mean_reversion import MeanReversion
from market_game_sim.agent.strategy_layer.families.sentiment_noise import SentimentNoise
from market_game_sim.agent.strategy_layer.families.trend_following import (
    TIME_SCALES,
    TrendFollowing,
)
from market_game_sim.agent.strategy_layer.protocol import TraderStrategy
from market_game_sim.agent.strategy_layer.registry import StrategyRegistry, default_registry

#: Family ids this milestone ships, in a stable order.
NATIVE_FAMILY_IDS: tuple[str, ...] = (
    "trend_following",
    "mean_reversion",
    "sentiment_noise",
    "market_maker_v2",
)


def build_native_families() -> tuple[TraderStrategy, ...]:
    """Default-parameter instances of the four families, in stable order."""
    return (TrendFollowing(), MeanReversion(), SentimentNoise(), MarketMakerV2())


def register_native_families(registry: StrategyRegistry | None = None) -> StrategyRegistry:
    """Register the four families into ``registry`` (default: process-wide)."""
    target = default_registry() if registry is None else registry
    for strategy in build_native_families():
        target.register(strategy)
    return target


__all__ = [
    "NATIVE_FAMILY_IDS",
    "TIME_SCALES",
    "MarketMakerV2",
    "MeanReversion",
    "SentimentNoise",
    "TrendFollowing",
    "build_native_families",
    "register_native_families",
]
