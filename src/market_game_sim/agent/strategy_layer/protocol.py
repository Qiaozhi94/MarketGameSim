"""0.4.1 T964 (FR-502 / IR-501): the ``TraderStrategy`` protocol and tiered information sets.

The L2 trader-strategy layer sits on top of the L1 engine (design §2).  A
strategy reads a *tiered* information set and returns a target position or an
order intent, tagged with its family id; it never holds a ledger reference,
never calls matching and never writes events -- the existing L1 handler path
does all of that.

Information tiers (design §4; ``I`` prefix to avoid clashing with the
architecture layers L0—L4):

* ``I0`` -- top of book + own account;
* ``I1`` -- ``I0`` + the recent public trade tape;
* ``I2`` -- ``I1`` + completed multi-period bars;
* ``I3`` -- ``I2`` + external signal channels.

Cropping happens here (:func:`crop_information_set`), from the unchanged L1
``InformationSetV1``; fields above a set's tier are ``None`` and a set that
carries them anyway is rejected on construction, so a strategy cannot see more
than its family declared.

Any change to the input/output contract below must bump
:data:`PROTOCOL_VERSION` (IR-501).

Stdlib only (KR-005).
"""

from __future__ import annotations

import abc
import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from market_game_sim.agent.goal import (
    AgentInternalStateV1,
    AgentPreferences,
    BookTop,
    CompletedBar,
    InformationSetV1,
    OwnAccountView,
    PublicTrade,
)

PROTOCOL_VERSION = 1


class StrategyLayerError(ValueError):
    """Strategy layer rejected an input; ``code`` is stable and safe to assert on."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


class InformationTier(enum.IntEnum):
    """Information tier a family declares; higher tiers see strictly more."""

    I0 = 0
    I1 = 1
    I2 = 2
    I3 = 3


@dataclass(frozen=True)
class ExternalSignal:
    """One value on an external signal channel (``I3`` only).

    ``source_id`` / ``signal_version`` exist so a decision driven by the signal
    can be traced to its source and version (TR-501); T975 extends the
    injection side, not this record's identity fields.
    """

    source_id: str
    signal_version: str
    value: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for fname, value in (
            ("source_id", self.source_id),
            ("signal_version", self.signal_version),
        ):
            if type(value) is not str or not value:
                raise StrategyLayerError(
                    "INVALID_EXTERNAL_SIGNAL", f"ExternalSignal.{fname} must be a non-empty str"
                )
        if not isinstance(self.value, Mapping):
            raise StrategyLayerError(
                "INVALID_EXTERNAL_SIGNAL", "ExternalSignal.value must be a Mapping"
            )
        object.__setattr__(self, "value", MappingProxyType(dict(self.value)))


# Field -> lowest tier allowed to carry it.  ``book_top`` / ``own_account`` are
# the I0 base and always present.
_TIERED_FIELDS: Mapping[str, InformationTier] = MappingProxyType(
    {
        "public_trades": InformationTier.I1,
        "completed_bars": InformationTier.I2,
        "external_signals": InformationTier.I3,
    }
)


@dataclass(frozen=True)
class TieredInformationSet:
    """What a strategy is allowed to see, cropped to its declared tier."""

    tier: InformationTier
    observed_at: int
    book_top: BookTop | None
    own_account: OwnAccountView
    public_trades: tuple[PublicTrade, ...] | None = None
    completed_bars: tuple[CompletedBar, ...] | None = None
    external_signals: tuple[ExternalSignal, ...] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.tier, InformationTier):
            raise StrategyLayerError("INVALID_INFO_TIER", f"tier {self.tier!r}")
        if type(self.observed_at) is not int:
            raise StrategyLayerError("INVALID_INFO_SET", "observed_at must be int")
        if self.book_top is not None and not isinstance(self.book_top, BookTop):
            raise StrategyLayerError("INVALID_INFO_SET", "book_top must be BookTop or None")
        if not isinstance(self.own_account, OwnAccountView):
            raise StrategyLayerError("INVALID_INFO_SET", "own_account must be OwnAccountView")
        for fname, min_tier in _TIERED_FIELDS.items():
            value = getattr(self, fname)
            if self.tier < min_tier:
                if value is not None:
                    raise StrategyLayerError(
                        "INFO_TIER_VIOLATION",
                        f"{fname} requires {min_tier.name}, set is {self.tier.name}",
                    )
            elif value is None:
                raise StrategyLayerError(
                    "INVALID_INFO_SET", f"{fname} is required at {self.tier.name}"
                )
        for fname, expected in (
            ("public_trades", PublicTrade),
            ("completed_bars", CompletedBar),
            ("external_signals", ExternalSignal),
        ):
            value = getattr(self, fname)
            if value is None:
                continue
            if not isinstance(value, Sequence) or not all(isinstance(v, expected) for v in value):
                raise StrategyLayerError(
                    "INVALID_INFO_SET", f"{fname} must be a sequence of {expected.__name__}"
                )
            object.__setattr__(self, fname, tuple(value))


def crop_information_set(
    info: InformationSetV1,
    tier: InformationTier,
    *,
    observed_at: int,
    external_signals: Sequence[ExternalSignal] | None = None,
) -> TieredInformationSet:
    """Crop the L1 ``InformationSetV1`` down to ``tier``.

    External signals are not part of the L1 set; they are passed in and only
    accepted at ``I3`` -- supplying them to a lower tier is a violation, not a
    silent drop, so a mis-wired channel surfaces at assembly time.
    """
    if not isinstance(tier, InformationTier):
        raise StrategyLayerError("INVALID_INFO_TIER", f"tier {tier!r}")
    if tier < InformationTier.I3 and external_signals is not None:
        raise StrategyLayerError(
            "INFO_TIER_VIOLATION", f"external_signals requires I3, set is {tier.name}"
        )
    return TieredInformationSet(
        tier=tier,
        observed_at=observed_at,
        book_top=info.book_top,
        own_account=info.own_account,
        public_trades=tuple(info.public_trades) if tier >= InformationTier.I1 else None,
        completed_bars=tuple(info.completed_bars) if tier >= InformationTier.I2 else None,
        external_signals=(tuple(external_signals or ()) if tier >= InformationTier.I3 else None),
    )


# --------------------------------------------------------------------------- #
# Output contract
# --------------------------------------------------------------------------- #

ACTION_TARGET_POSITION = "target_position"
ACTION_ORDER_INTENT = "order_intent"
ACTION_NO_ACTION = "no_action"
ACTIONS = frozenset({ACTION_TARGET_POSITION, ACTION_ORDER_INTENT, ACTION_NO_ACTION})

SIDES = frozenset({"BUY", "SELL"})
ORDER_TYPES = frozenset({"LIMIT", "MARKET"})


@dataclass(frozen=True)
class OrderIntentSpec:
    """A direct order intent; L1 admission / risk still decide whether it lands."""

    side: str
    order_type: str
    quantity_units: int
    price_ticks: int | None = None

    def __post_init__(self) -> None:
        if self.side not in SIDES:
            raise StrategyLayerError("INVALID_ORDER_INTENT", f"side {self.side!r}")
        if self.order_type not in ORDER_TYPES:
            raise StrategyLayerError("INVALID_ORDER_INTENT", f"order_type {self.order_type!r}")
        if type(self.quantity_units) is not int or self.quantity_units <= 0:
            raise StrategyLayerError(
                "INVALID_ORDER_INTENT", "quantity_units must be a positive int"
            )
        if self.order_type == "LIMIT":
            if type(self.price_ticks) is not int or self.price_ticks <= 0:
                raise StrategyLayerError(
                    "INVALID_ORDER_INTENT", "LIMIT needs a positive int price_ticks"
                )
        elif self.price_ticks is not None:
            raise StrategyLayerError("INVALID_ORDER_INTENT", "MARKET must not carry price_ticks")


@dataclass(frozen=True)
class StrategyDecision:
    """Output of ``TraderStrategy.decide``.

    Exactly one payload matches ``action``: ``target_position_units`` for
    ``target_position``, ``order_intent`` for ``order_intent``, neither for
    ``no_action`` (``reason_code`` then says why).  ``family_id`` and
    ``info_tier`` let the decision record trace back to the family (TR-501).
    """

    family_id: str
    info_tier: InformationTier
    action: str
    updated_state: AgentInternalStateV1
    target_position_units: int | None = None
    order_intent: OrderIntentSpec | None = None
    reason_code: str | None = None
    protocol_version: int = PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if type(self.family_id) is not str or not self.family_id:
            raise StrategyLayerError("INVALID_DECISION", "family_id must be a non-empty str")
        if not isinstance(self.info_tier, InformationTier):
            raise StrategyLayerError("INVALID_DECISION", f"info_tier {self.info_tier!r}")
        if self.action not in ACTIONS:
            raise StrategyLayerError("INVALID_DECISION", f"action {self.action!r}")
        if not isinstance(self.updated_state, AgentInternalStateV1):
            raise StrategyLayerError(
                "INVALID_DECISION", "updated_state must be AgentInternalStateV1"
            )
        if self.protocol_version != PROTOCOL_VERSION:
            raise StrategyLayerError(
                "PROTOCOL_VERSION_MISMATCH",
                f"decision v{self.protocol_version}, layer v{PROTOCOL_VERSION}",
            )
        has_target = self.target_position_units is not None
        has_intent = self.order_intent is not None
        if has_target and type(self.target_position_units) is not int:
            raise StrategyLayerError("INVALID_DECISION", "target_position_units must be int")
        if has_intent and not isinstance(self.order_intent, OrderIntentSpec):
            raise StrategyLayerError("INVALID_DECISION", "order_intent must be OrderIntentSpec")
        expected = {
            ACTION_TARGET_POSITION: (True, False),
            ACTION_ORDER_INTENT: (False, True),
            ACTION_NO_ACTION: (False, False),
        }[self.action]
        if (has_target, has_intent) != expected:
            raise StrategyLayerError(
                "INVALID_DECISION", f"payload does not match action {self.action!r}"
            )
        if self.reason_code is not None and (
            type(self.reason_code) is not str or not self.reason_code
        ):
            raise StrategyLayerError("INVALID_DECISION", "reason_code must be a non-empty str")


class TraderStrategy(abc.ABC):
    """A strategy family: declares its id and tier, decides from a tiered set."""

    #: Stable family identifier (the ``family_id`` a roster names).
    family_id: str
    #: The highest information tier this family may read.
    info_tier: InformationTier
    #: Protocol version the family was written against.
    protocol_version: int = PROTOCOL_VERSION

    @abc.abstractmethod
    def decide(
        self,
        info: TieredInformationSet,
        state: AgentInternalStateV1,
        prefs: AgentPreferences,
    ) -> StrategyDecision:
        """Return a target position, an order intent, or ``no_action``."""


__all__ = [
    "ACTIONS",
    "ACTION_NO_ACTION",
    "ACTION_ORDER_INTENT",
    "ACTION_TARGET_POSITION",
    "ExternalSignal",
    "InformationTier",
    "OrderIntentSpec",
    "PROTOCOL_VERSION",
    "StrategyDecision",
    "StrategyLayerError",
    "TieredInformationSet",
    "TraderStrategy",
    "crop_information_set",
]
