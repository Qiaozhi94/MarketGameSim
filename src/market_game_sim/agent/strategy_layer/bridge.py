"""0.4.1 T966 (FR-503 / DR-501): run strategy families through the existing seams.

A roster names families; the agent runtime knows goal models and market-maker
quoting.  This module is the join, and it deliberately adds **no** new path
into L1:

* families that return a **target position** (`trend_following`,
  `mean_reversion`, `sentiment_noise`) are wrapped as :class:`GoalModel`s and
  registered under their ``family_id``.  A roster entry then just sets
  ``goal_model_id=<family_id>`` and the whole existing v2 pipeline applies
  unchanged -- cold-start anchor, constraint layer, margin feasibility,
  decision evidence, causal chain;
* families that return an **order intent** (`market_maker_v2`) are converted to
  the ``OrderIntent`` objects the market-maker branch already emits, so their
  quotes travel the same admission, ledger and risk path as every other order
  (ADR-011 §决策 1: L2 never touches the book itself).

Tier cropping is the protocol's job (``crop_information_set``): a family sees
only what its declared tier allows, here as everywhere else.
"""

from __future__ import annotations

from dataclasses import dataclass

from market_game_sim.agent.goal import (
    AgentInternalStateV1,
    AgentPreferences,
    BookTop,
    GoalDecision,
    GoalModel,
    GoalRng,
    InformationSetV1,
    OwnAccountView,
    in_bootstrap,
    register_goal_model,
)
from market_game_sim.agent.strategy import OrderIntent
from market_game_sim.agent.strategy_layer.families.market_maker_v2 import MarketMakerV2
from market_game_sim.agent.strategy_layer.families.mean_reversion import MeanReversion
from market_game_sim.agent.strategy_layer.families.sentiment_noise import SentimentNoise
from market_game_sim.agent.strategy_layer.families.trend_following import TrendFollowing
from market_game_sim.agent.strategy_layer.protocol import (
    ACTION_NO_ACTION,
    ACTION_ORDER_INTENT,
    ACTION_TARGET_POSITION,
    StrategyLayerError,
    TieredInformationSet,
    TraderStrategy,
    crop_information_set,
)
from market_game_sim.agent.strategy_layer.registry import get_strategy, register_strategy

#: Families whose output is a target position -- they ride the GoalModel seam.
TARGET_POSITION_FAMILIES: tuple[TraderStrategy, ...] = (
    TrendFollowing(),
    MeanReversion(),
    SentimentNoise(),
)
#: Families whose output is an order intent -- they ride the quoting seam.
ORDER_INTENT_FAMILIES: tuple[TraderStrategy, ...] = (MarketMakerV2(),)
#: Their ids: the market-maker branch only defers to a family in this set, so a
#: spec labelled with a non-quoting family keeps the built-in quote rule.
ORDER_INTENT_FAMILY_IDS = frozenset(s.family_id for s in ORDER_INTENT_FAMILIES)


@dataclass(frozen=True)
class StrategyGoalModel(GoalModel):
    """Adapts a target-position :class:`TraderStrategy` to the GoalModel seam."""

    strategy: TraderStrategy
    id: str = ""
    version: int = 0
    # 0.4.1 T963/T966: the handler injects these per agent (``dataclasses.replace``),
    # exactly as it does for the built-in goal models.  The anchor fires while the
    # agent is in EWMA warmup and the exit test is the unchanged warmup test
    # (spec Q-501), which is also when a family has no tape or bars to reason
    # from -- so one rule covers both cold starts.
    half_life_in_trades: int = 0
    bootstrap_anchor_units: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", self.strategy.family_id)
        object.__setattr__(self, "version", self.strategy.protocol_version)

    def decide(
        self,
        information_set: InformationSetV1,
        internal_state: AgentInternalStateV1,
        preferences: AgentPreferences,
        rng: GoalRng | None = None,
    ) -> GoalDecision:
        if in_bootstrap(internal_state, self):
            return GoalDecision(
                desired_position_units=self.bootstrap_anchor_units,
                action="emit_decision",
                degenerate_reason=None,
                updated_state=internal_state,
            )
        # ``InformationSetV1`` carries no timestamp (its boundaries are the
        # cursor ids); the families use ``observed_at`` for nothing but their
        # own records, so the seam passes 0 rather than inventing a clock.
        info = crop_information_set(information_set, self.strategy.info_tier, observed_at=0)
        decision = self.strategy.decide(info, internal_state, preferences)
        if decision.action == ACTION_TARGET_POSITION:
            return GoalDecision(
                desired_position_units=decision.target_position_units,
                action="emit_decision",
                degenerate_reason=None,
                updated_state=decision.updated_state,
            )
        if decision.action == ACTION_NO_ACTION:
            # No signal is not "target zero": flattening on every quiet tick
            # would manufacture order flow the family did not ask for.
            return GoalDecision(
                desired_position_units=None,
                action="skip_decision",
                degenerate_reason=None,
                updated_state=decision.updated_state,
            )
        raise StrategyLayerError(
            "UNSUPPORTED_ACTION_FOR_SEAM",
            f"{self.strategy.family_id} returned {decision.action!r}; the GoalModel seam "
            "carries target positions only",
        )


def family_quote_intents(
    family_id: str,
    agent_id: str,
    iset: dict,
    decision_index: int,
    state: AgentInternalStateV1,
    preferences: AgentPreferences,
    leverage_tier: int,
) -> list[OrderIntent]:
    """Quotes from an order-intent family, as the market-maker branch's intents."""
    strategy = get_strategy(family_id)
    info = TieredInformationSet(
        tier=strategy.info_tier,
        observed_at=0,
        book_top=BookTop(
            best_bid=iset["best_bid"],
            best_ask=iset["best_ask"],
            valuation_mark_half_ticks=iset.get("valuation_mark_half_ticks"),
        ),
        own_account=OwnAccountView(
            wallet_units=iset["wallet_units"],
            position_units=iset["position_units"],
            entry_notional_units=iset["entry_notional_units"],
        ),
    )
    decision = strategy.decide(info, state, preferences)
    if decision.action != ACTION_ORDER_INTENT or decision.order_intent is None:
        return []
    intent = decision.order_intent
    return [
        OrderIntent(
            intent_id=f"{agent_id}-{family_id}-{decision_index}",
            action="SUBMIT",
            side=intent.side,
            order_type=intent.order_type,
            price_ticks=intent.price_ticks,
            quantity_units=intent.quantity_units,
            leverage_tier=leverage_tier,
            aggressiveness_bp=0,
        )
    ]


def register_families() -> None:
    """Register every native family in both registries (idempotent)."""
    for strategy in TARGET_POSITION_FAMILIES + ORDER_INTENT_FAMILIES:
        try:
            get_strategy(strategy.family_id)
        except StrategyLayerError:
            register_strategy(strategy)
    for strategy in TARGET_POSITION_FAMILIES:
        register_goal_model(StrategyGoalModel(strategy))


register_families()
