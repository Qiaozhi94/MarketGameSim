"""0.4.1 T969 (FR-503 / AC-503): the improved market-maker family.

Same inventory-reverting quote as ``MarketMakerGoal`` (代理策略 §8), with the
one change this milestone needs: **per-agent parameter dispersion**.  The v1
market makers all computed the identical half spread from the identical mid,
so every quote landed on the same two ticks and the book showed a single level
per side -- which is exactly the "单档盘口" the market-quality gate fails on
(spec §6 档位).  Here each agent draws its own half spread and quote size once,
keyed by ``agent_id``, so the same roster produces a laddered book.

The quote is one-sided per decision: the protocol carries one intent, so the
agent alternates sides by ``decision_index`` parity and posts both sides over
two observations.  Inventory at or beyond ``max_inventory`` overrides the
parity and only the reducing side is quoted -- the inventory goal is still to
revert toward flat.

Draw mechanisms (``strategy_mm_half_spread`` / ``strategy_mm_quote_size``) are
new keys, never reusing an existing mechanism (KR-004).

Stdlib only (KR-005).  Integer arithmetic, ``trunc`` toward zero (ADR-001).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from market_game_sim.agent.goal import AgentInternalStateV1, AgentPreferences
from market_game_sim.agent.strategy_layer.families._common import (
    REASON_NO_MARK,
    REASON_PRICE_OUT_OF_RANGE,
    DrawContext,
    draw_context,
    mark_ticks,
)
from market_game_sim.agent.strategy_layer.protocol import (
    ACTION_NO_ACTION,
    ACTION_ORDER_INTENT,
    InformationTier,
    OrderIntentSpec,
    StrategyDecision,
    StrategyLayerError,
    TieredInformationSet,
    TraderStrategy,
)
from market_game_sim.rng.distributions import blake2b_uniform

FAMILY_ID = "market_maker_v2"

#: Keyed-draw mechanisms; distinct from every existing mechanism (KR-004).
MECHANISM_HALF_SPREAD = "strategy_mm_half_spread"
MECHANISM_QUOTE_SIZE = "strategy_mm_quote_size"


@dataclass(frozen=True)
class MarketMakerV2(TraderStrategy):
    """Inventory-reverting quotes with per-agent spread / size dispersion."""

    base_half_spread_ticks: int = 4
    half_spread_dispersion_ticks: int = 3
    base_quote_size: int = 2
    quote_size_dispersion: int = 1
    max_inventory: int = 10
    inventory_skew_k_bp: int = 5000
    family_id: str = FAMILY_ID
    info_tier: InformationTier = InformationTier.I0
    protocol_version: int = 1

    def __post_init__(self) -> None:
        if type(self.base_half_spread_ticks) is not int or self.base_half_spread_ticks < 1:
            raise StrategyLayerError(
                "INVALID_FAMILY_PARAMS", f"{FAMILY_ID}: base_half_spread_ticks must be an int >= 1"
            )
        if (
            type(self.half_spread_dispersion_ticks) is not int
            or self.half_spread_dispersion_ticks < 0
            or self.half_spread_dispersion_ticks >= self.base_half_spread_ticks
        ):
            raise StrategyLayerError(
                "INVALID_FAMILY_PARAMS",
                f"{FAMILY_ID}: half_spread_dispersion_ticks must be in [0, base_half_spread_ticks)",
            )
        if type(self.base_quote_size) is not int or self.base_quote_size < 1:
            raise StrategyLayerError(
                "INVALID_FAMILY_PARAMS", f"{FAMILY_ID}: base_quote_size must be an int >= 1"
            )
        if (
            type(self.quote_size_dispersion) is not int
            or self.quote_size_dispersion < 0
            or self.quote_size_dispersion >= self.base_quote_size
        ):
            raise StrategyLayerError(
                "INVALID_FAMILY_PARAMS",
                f"{FAMILY_ID}: quote_size_dispersion must be in [0, base_quote_size)",
            )
        if type(self.max_inventory) is not int or self.max_inventory < 1:
            raise StrategyLayerError(
                "INVALID_FAMILY_PARAMS", f"{FAMILY_ID}: max_inventory must be an int >= 1"
            )
        if type(self.inventory_skew_k_bp) is not int or self.inventory_skew_k_bp < 0:
            raise StrategyLayerError(
                "INVALID_FAMILY_PARAMS", f"{FAMILY_ID}: inventory_skew_k_bp must be an int >= 0"
            )

    # ----------------------------------------------------------------- #
    # Per-agent dispersion (drawn once per agent: decision_index fixed 0)
    # ----------------------------------------------------------------- #

    def half_spread_ticks(self, ctx: DrawContext) -> int:
        span = 2 * self.half_spread_dispersion_ticks + 1
        u = blake2b_uniform(ctx.master_seed, ctx.agent_id, MECHANISM_HALF_SPREAD, 0, 0)
        offset = int(u * span) - self.half_spread_dispersion_ticks
        return self.base_half_spread_ticks + offset

    def quote_size(self, ctx: DrawContext) -> int:
        span = 2 * self.quote_size_dispersion + 1
        u = blake2b_uniform(ctx.master_seed, ctx.agent_id, MECHANISM_QUOTE_SIZE, 0, 0)
        offset = int(u * span) - self.quote_size_dispersion
        return self.base_quote_size + offset

    def _skew_ticks(self, inventory: int, half_spread: int) -> int:
        inv_ratio = Decimal(inventory) / Decimal(self.max_inventory)
        inv_ratio = max(Decimal(-1), min(Decimal(1), inv_ratio))
        return int(inv_ratio * self.inventory_skew_k_bp * half_spread / Decimal(10_000))

    def _side(self, inventory: int, ctx: DrawContext) -> str:
        """Alternate by decision parity; an inventory cap overrides it."""
        if inventory >= self.max_inventory:
            return "SELL"
        if inventory <= -self.max_inventory:
            return "BUY"
        return "BUY" if ctx.decision_index % 2 == 0 else "SELL"

    def decide(
        self,
        info: TieredInformationSet,
        state: AgentInternalStateV1,
        prefs: AgentPreferences,
    ) -> StrategyDecision:
        ctx = draw_context(state, FAMILY_ID)
        mark = mark_ticks(info)
        if mark is None:
            return self._no_action(state, REASON_NO_MARK)
        half_spread = self.half_spread_ticks(ctx)
        skew = self._skew_ticks(info.own_account.position_units, half_spread)
        side = self._side(info.own_account.position_units, ctx)
        price = mark - half_spread - skew if side == "BUY" else mark + half_spread - skew
        if price <= 0:
            return self._no_action(state, REASON_PRICE_OUT_OF_RANGE)
        return StrategyDecision(
            family_id=self.family_id,
            info_tier=self.info_tier,
            action=ACTION_ORDER_INTENT,
            updated_state=state,
            order_intent=OrderIntentSpec(
                side=side,
                order_type="LIMIT",
                quantity_units=self.quote_size(ctx),
                price_ticks=price,
            ),
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
    "MECHANISM_HALF_SPREAD",
    "MECHANISM_QUOTE_SIZE",
    "MarketMakerV2",
]
