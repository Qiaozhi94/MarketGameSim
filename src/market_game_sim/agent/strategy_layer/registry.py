"""0.4.1 T964 (FR-502 / AC-502): the strategy family registry.

Adding a family means registering it here -- never touching L1 matching,
ledger, margin, liquidation or the event schema (FR-502).  Lookup is
fail-closed: an unregistered ``family_id`` raises :class:`StrategyLayerError`
with the stable code ``UNKNOWN_STRATEGY_FAMILY`` at assembly time, so a roster
naming a family that does not exist never reaches the run loop.

:func:`decide` is the single call site the assembly uses: it checks that the
information set was cropped to the family's declared tier and that the
decision comes back tagged with the right family and tier, so a family cannot
read above its tier or mislabel its output.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from market_game_sim.agent.goal import AgentInternalStateV1, AgentPreferences
from market_game_sim.agent.strategy_layer.protocol import (
    PROTOCOL_VERSION,
    InformationTier,
    StrategyDecision,
    StrategyLayerError,
    TieredInformationSet,
    TraderStrategy,
)

_FAMILY_ID = re.compile(r"^[a-z][a-z0-9_]*$")


class StrategyRegistry:
    """A closed table of ``family_id -> TraderStrategy``."""

    def __init__(self) -> None:
        self._families: dict[str, TraderStrategy] = {}

    def register(self, strategy: TraderStrategy) -> None:
        if not isinstance(strategy, TraderStrategy):
            raise StrategyLayerError(
                "INVALID_STRATEGY", f"{type(strategy).__name__} is not a TraderStrategy"
            )
        family_id = getattr(strategy, "family_id", None)
        if type(family_id) is not str or not _FAMILY_ID.match(family_id):
            raise StrategyLayerError("INVALID_STRATEGY", f"family_id {family_id!r}")
        if not isinstance(getattr(strategy, "info_tier", None), InformationTier):
            raise StrategyLayerError(
                "INVALID_STRATEGY", f"{family_id}: info_tier must be an InformationTier"
            )
        if strategy.protocol_version != PROTOCOL_VERSION:
            raise StrategyLayerError(
                "PROTOCOL_VERSION_MISMATCH",
                f"{family_id} written for v{strategy.protocol_version}, layer v{PROTOCOL_VERSION}",
            )
        if family_id in self._families:
            raise StrategyLayerError("DUPLICATE_STRATEGY_FAMILY", f"{family_id!r}")
        self._families[family_id] = strategy

    def get(self, family_id: str) -> TraderStrategy:
        try:
            return self._families[family_id]
        except (KeyError, TypeError):
            raise StrategyLayerError(
                "UNKNOWN_STRATEGY_FAMILY", f"{family_id!r} is not registered"
            ) from None

    def resolve(self, family_ids: Iterable[str]) -> tuple[TraderStrategy, ...]:
        """Resolve a whole assembly; any unknown id fails the lot (fail closed).

        All unknown ids are named in one error, so a roster with several typos
        is fixed in one pass rather than one id per run.
        """
        ids = list(family_ids)
        unknown = [f for f in ids if f not in self._families]
        if unknown:
            raise StrategyLayerError(
                "UNKNOWN_STRATEGY_FAMILY", f"not registered: {sorted(set(map(repr, unknown)))}"
            )
        return tuple(self._families[f] for f in ids)

    def family_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._families))

    def __contains__(self, family_id: object) -> bool:
        return family_id in self._families

    def decide(
        self,
        family_id: str,
        info: TieredInformationSet,
        state: AgentInternalStateV1,
        prefs: AgentPreferences,
    ) -> StrategyDecision:
        strategy = self.get(family_id)
        if not isinstance(info, TieredInformationSet) or info.tier != strategy.info_tier:
            got = getattr(info, "tier", None)
            raise StrategyLayerError(
                "INFO_TIER_MISMATCH",
                f"{family_id} declares {strategy.info_tier.name}, got {got!r}",
            )
        decision = strategy.decide(info, state, prefs)
        if not isinstance(decision, StrategyDecision):
            raise StrategyLayerError(
                "INVALID_DECISION", f"{family_id} returned {type(decision).__name__}"
            )
        if decision.family_id != family_id or decision.info_tier != strategy.info_tier:
            raise StrategyLayerError(
                "DECISION_FAMILY_MISMATCH",
                f"{family_id}/{strategy.info_tier.name} returned "
                f"{decision.family_id}/{decision.info_tier.name}",
            )
        return decision


# Process-wide default registry.  No families are registered yet: the native
# families arrive with T968/T969, and roster assembly moves onto this registry
# with T966.
_DEFAULT = StrategyRegistry()


def default_registry() -> StrategyRegistry:
    return _DEFAULT


def register_strategy(strategy: TraderStrategy) -> None:
    _DEFAULT.register(strategy)


def get_strategy(family_id: str) -> TraderStrategy:
    return _DEFAULT.get(family_id)


__all__ = [
    "StrategyRegistry",
    "default_registry",
    "get_strategy",
    "register_strategy",
]
