"""0.4.1 L2 trader-strategy layer (design §2): protocol, tiered information sets, registry.

Boundary: this package reads tiered information sets and returns target
positions or order intents.  It never imports the ledger, matching, kernel or
event log -- those stay behind the existing L1 handler path.
"""

from market_game_sim.agent.strategy_layer.protocol import (
    ACTION_NO_ACTION,
    ACTION_ORDER_INTENT,
    ACTION_TARGET_POSITION,
    PROTOCOL_VERSION,
    ExternalSignal,
    InformationTier,
    OrderIntentSpec,
    StrategyDecision,
    StrategyLayerError,
    TieredInformationSet,
    TraderStrategy,
    crop_information_set,
)
from market_game_sim.agent.strategy_layer.registry import (
    StrategyRegistry,
    default_registry,
    get_strategy,
    register_strategy,
)

__all__ = [
    "ACTION_NO_ACTION",
    "ACTION_ORDER_INTENT",
    "ACTION_TARGET_POSITION",
    "ExternalSignal",
    "InformationTier",
    "OrderIntentSpec",
    "PROTOCOL_VERSION",
    "StrategyDecision",
    "StrategyLayerError",
    "StrategyRegistry",
    "TieredInformationSet",
    "TraderStrategy",
    "crop_information_set",
    "default_registry",
    "get_strategy",
    "register_strategy",
]
