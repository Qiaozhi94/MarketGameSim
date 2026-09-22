"""0.4.1 T963 (FR-501 / NFR-502 / AC-501): the cold-start anchor.

Problem (T960 red baseline): a goal agent stays in EWMA warmup until it has
consumed ``2 * ewma_half_life_trades`` public trades, and in warmup its target
is 0.  A market whose only other participant is a market maker never crosses
the spread, so the tape stays empty and warmup never ends.

The anchor replaces *only* the warmup target (spec Q-501, design DQ-501): while
an anchored agent is in warmup, ``goal.py``'s degenerate branch emits a target
of ``direction * quantity_units`` instead of 0, and the order is priced at the
best opposite quote -- or, if that side is empty, as a limit at the run's
initial price, so a buyer and a seller from the anchor meet at the same price.
Exit reuses the existing warmup test unchanged; there is no new exit parameter.
Everything after warmup is the unmodified ``GoalModel`` path.

``ewma_half_life_trades`` in a live ecology
-------------------------------------------
The half-life is measured in **public trades on the shared tape**, whatever
their origin -- anchor fills count like any other fill.  Every agent reads the
same tape from ``e1_0``, so every anchored agent leaves warmup once the market
as a whole has printed ``2 * half_life`` trades.  ``0`` disables warmup, and
with it the anchor: an agent that never warms up is never anchored.  One
consequence worth knowing: each anchored agent trades at most
``quantity_units`` during warmup, so a market with too few anchored agents for
its half-life can stall again *after* the first fills; that is a property of
the frozen parameters, not something the anchor papers over.

Direction (Q-501, no RNG): within each family, in assembly order, position 0 is
a buyer, 1 a seller, and so on.  A family with an odd number of agents has one
left over; the leftovers of odd families take buy, sell, buy... in the order
the odd families appear, so the market as a whole starts as close to flat as
the family sizes allow.

Sources are pluggable (``register_anchor_source``).  Only ``synthetic`` is
registered; ``historical_snapshot`` (ADR-014) is rejected until its own
milestone registers it.  ``none`` is the explicit "no anchor" and resolves to
``None``.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Protocol

from market_game_sim.agent.goal import get_goal_model
from market_game_sim.agent.strategy import OrderIntent

if TYPE_CHECKING:
    from market_game_sim.agent.scheduler import AgentSpec

ANCHOR_NONE = "none"
ANCHOR_SYNTHETIC = "synthetic"
DIRECTION_FAMILY_PARITY = "family_parity"
PRICING_BEST_OPPOSITE_ELSE_INITIAL_LIMIT = "best_opposite_else_initial_limit"

# Runtime block keys: the roster's frozen anchor params plus the assembly the
# direction rule is computed over (``families``: [[family_id, [agent_id, ...]]]).
_SYNTHETIC_KEYS = frozenset({"source", "quantity_units", "direction", "pricing", "families"})


class AnchorError(ValueError):
    """Anchor rejected at assembly; ``code`` is stable and safe to assert on."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


class BootstrapAnchor(Protocol):
    """A resolved anchor: per-agent warmup target and the header it records."""

    source: str

    def anchored_agents(self) -> frozenset[str]:
        """Agents this anchor assigns a warmup target to."""
        ...

    def target_units(self, agent_id: str) -> int | None:
        """Signed warmup target for ``agent_id``, or ``None`` if not anchored."""
        ...

    def header(self) -> dict[str, Any]:
        """Anchor parameters and source for the run header (NFR-502)."""
        ...


def family_parity_directions(families: Sequence[tuple[str, Sequence[str]]]) -> dict[str, int]:
    """Q-501 direction rule: ``+1`` buy / ``-1`` sell per agent, no RNG."""
    directions: dict[str, int] = {}
    odd_ordinal = 0
    for _family_id, agent_ids in families:
        n = len(agent_ids)
        for i, agent_id in enumerate(agent_ids):
            if n % 2 == 1 and i == n - 1:
                directions[agent_id] = 1 if odd_ordinal % 2 == 0 else -1
                odd_ordinal += 1
            else:
                directions[agent_id] = 1 if i % 2 == 0 else -1
    return directions


@dataclass(frozen=True)
class SyntheticAnchor:
    quantity_units: int
    families: tuple[tuple[str, tuple[str, ...]], ...]
    directions: Mapping[str, int]
    source: str = ANCHOR_SYNTHETIC

    def anchored_agents(self) -> frozenset[str]:
        return frozenset(self.directions)

    def target_units(self, agent_id: str) -> int | None:
        direction = self.directions.get(agent_id)
        return None if direction is None else direction * self.quantity_units

    def header(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "quantity_units": self.quantity_units,
            "direction": DIRECTION_FAMILY_PARITY,
            "pricing": PRICING_BEST_OPPOSITE_ELSE_INITIAL_LIMIT,
            "families": [[fid, list(aids)] for fid, aids in self.families],
        }


def _build_synthetic(block: Mapping[str, Any]) -> SyntheticAnchor:
    unknown = sorted(set(block) - _SYNTHETIC_KEYS)
    missing = sorted(_SYNTHETIC_KEYS - set(block))
    if unknown:
        raise AnchorError("UNKNOWN_FIELD", f"bootstrap_anchor has unknown fields {unknown}")
    if missing:
        raise AnchorError("MISSING_FIELD", f"bootstrap_anchor is missing {missing}")
    qty = block["quantity_units"]
    if type(qty) is not int or qty < 1:
        raise AnchorError("INVALID_VALUE", f"bootstrap_anchor.quantity_units {qty!r}")
    if block["direction"] != DIRECTION_FAMILY_PARITY:
        raise AnchorError("INVALID_VALUE", f"bootstrap_anchor.direction {block['direction']!r}")
    if block["pricing"] != PRICING_BEST_OPPOSITE_ELSE_INITIAL_LIMIT:
        raise AnchorError("INVALID_VALUE", f"bootstrap_anchor.pricing {block['pricing']!r}")
    families: list[tuple[str, tuple[str, ...]]] = []
    seen: set[str] = set()
    for entry in block["families"]:
        if not isinstance(entry, Sequence) or len(entry) != 2:
            raise AnchorError("INVALID_VALUE", f"bootstrap_anchor.families entry {entry!r}")
        family_id, agent_ids = entry
        if type(family_id) is not str or not all(type(a) is str for a in agent_ids):
            raise AnchorError("INVALID_VALUE", f"bootstrap_anchor.families entry {entry!r}")
        dup = seen.intersection(agent_ids)
        if dup or len(set(agent_ids)) != len(agent_ids):
            raise AnchorError("DUPLICATE_AGENT", f"bootstrap_anchor.families repeats {entry!r}")
        seen.update(agent_ids)
        families.append((family_id, tuple(agent_ids)))
    if not families:
        raise AnchorError("INVALID_VALUE", "bootstrap_anchor.families must be non-empty")
    return SyntheticAnchor(
        quantity_units=qty,
        families=tuple(families),
        directions=MappingProxyType(family_parity_directions(families)),
    )


_SOURCES: dict[str, Callable[[Mapping[str, Any]], BootstrapAnchor]] = {}


def register_anchor_source(
    source: str, factory: Callable[[Mapping[str, Any]], BootstrapAnchor]
) -> None:
    _SOURCES[source] = factory


def registered_anchor_sources() -> frozenset[str]:
    """Sources that can run, ``none`` included (it resolves to no anchor)."""
    return frozenset(_SOURCES) | {ANCHOR_NONE}


def resolve_anchor(block: Mapping[str, Any] | None) -> BootstrapAnchor | None:
    """Resolve a runtime anchor block; unknown sources fail closed."""
    if block is None:
        return None
    if not isinstance(block, Mapping):
        raise AnchorError("INVALID_VALUE", "bootstrap_anchor must be an object")
    source = block.get("source")
    if source == ANCHOR_NONE:
        if set(block) != {"source"}:
            raise AnchorError("UNKNOWN_FIELD", "bootstrap_anchor 'none' takes no parameters")
        return None
    factory = _SOURCES.get(source)  # type: ignore[arg-type]
    if factory is None:
        raise AnchorError("UNKNOWN_ANCHOR_SOURCE", f"bootstrap_anchor.source {source!r}")
    return factory(block)


def resolve_for_agents(
    block: Mapping[str, Any] | None, agent_specs: Iterable[AgentSpec]
) -> BootstrapAnchor | None:
    """Resolve an anchor against the assembled agents (fail closed at assembly).

    Every anchored agent must exist, be a goal-model agent whose model accepts
    an anchor target, and actually warm up -- an anchor on an agent with
    ``ewma_half_life_trades == 0`` could never fire, which is the silent
    "runs but never anchors" state design §7 forbids.
    """
    anchor = resolve_anchor(block)
    if anchor is None:
        return None
    specs = {s.agent_id: s for s in agent_specs}
    for agent_id in sorted(anchor.anchored_agents()):
        spec = specs.get(agent_id)
        if spec is None:
            raise AnchorError("ANCHOR_AGENT_UNKNOWN", f"{agent_id!r} is not an assembled agent")
        if spec.is_market_maker or spec.goal_model_id is None:
            raise AnchorError("ANCHOR_AGENT_NOT_GOAL", f"{agent_id!r} has no goal model")
        model = get_goal_model(spec.goal_model_id)
        if "bootstrap_anchor_units" not in {f.name for f in dataclasses.fields(model)}:  # type: ignore[arg-type]
            raise AnchorError(
                "ANCHOR_MODEL_UNSUPPORTED", f"{agent_id!r}: {spec.goal_model_id} takes no anchor"
            )
        if spec.ewma_half_life_trades <= 0:
            raise AnchorError(
                "ANCHOR_WITHOUT_WARMUP", f"{agent_id!r}: ewma_half_life_trades must be > 0"
            )
    return anchor


def anchor_header(anchor: BootstrapAnchor | None) -> dict[str, Any]:
    return {"source": ANCHOR_NONE} if anchor is None else anchor.header()


def anchor_order_intent(
    intent_id: str,
    target_position_units: int,
    current_position: int,
    leverage_tier: int,
    best_bid: int | None,
    best_ask: int | None,
    initial_price_ticks: int,
    max_order_qty: int,
    min_qty: int,
) -> OrderIntent | None:
    """Price the warmup target: take the best opposite quote, else rest at the
    initial price (``best_opposite_else_initial_limit``)."""
    delta = target_position_units - current_position
    if delta == 0:
        return None
    side = "BUY" if delta > 0 else "SELL"
    qty = min(abs(delta), max_order_qty)
    if qty < min_qty:
        return None
    opposite = best_ask if side == "BUY" else best_bid
    price = opposite if opposite is not None else initial_price_ticks
    if price <= 0:
        return None
    return OrderIntent(
        intent_id=intent_id,
        action="SUBMIT",
        side=side,
        order_type="LIMIT",
        price_ticks=price,
        quantity_units=qty,
        leverage_tier=leverage_tier,
        aggressiveness_bp=10_000,
    )


register_anchor_source(ANCHOR_SYNTHETIC, _build_synthetic)


__all__ = [
    "ANCHOR_NONE",
    "ANCHOR_SYNTHETIC",
    "AnchorError",
    "BootstrapAnchor",
    "SyntheticAnchor",
    "anchor_header",
    "anchor_order_intent",
    "family_parity_directions",
    "register_anchor_source",
    "registered_anchor_sources",
    "resolve_anchor",
    "resolve_for_agents",
]
