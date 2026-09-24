"""0.4.1 T962 (DR-501 / NFR-502): ``StrategyRoster`` -- the frozen market assembly.

A roster says *who is in the market*: which strategy families, how many agents
each, at what timescale, with which parameters, plus the cold-start anchor and
the engine configuration.  It is the unit of reproducibility for the pure AI
market: same roster (which includes the seed) => same agents => same run.

Identity is derived, not stored (derives-don't-store): ``roster_id`` is a
content hash of the canonical JSON body, and ``engine_config_digest`` a hash of
the engine block.  Both are written into the persisted file for audit and
re-derived on load, so a hand-edited roster cannot keep its old id.

Validation is closed-world and fail-closed: unknown fields, unknown families,
unknown anchor sources and wrongly typed values are rejected with a stable
:class:`RosterError` code, never silently ignored.

The family table here only covers the two families that exist today
(``inventory_market_maker`` and ``goal_belief``); T964 replaces it with the
``TraderStrategy`` registry.  The anchor's schema is frozen here; whether a
source can *run* is the anchor interface's call (``agent/anchor.py``, T963), so
a roster asking for a source with no runtime fails closed instead of running
without an anchor.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from market_game_sim.agent.anchor import (
    AnchorError,
    registered_anchor_sources,
    resolve_for_agents,
)
from market_game_sim.agent.goal import get_goal_model
from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.agent.strategy_layer import bridge as _strategy_bridge  # noqa: F401
from market_game_sim.agent.strategy_layer.families.trend_following import (
    TIME_SCALES as TREND_TIME_SCALES,
)
from market_game_sim.experiment.config import ExperimentConfig
from market_game_sim.ledger.account import initial_margin_bp_for_tier

SCHEMA_VERSION = 1

TOP_LEVEL_KEYS = frozenset({"schema_version", "seed", "engine", "bootstrap_anchor", "families"})
DERIVED_KEYS = frozenset({"roster_id", "engine_config_digest"})
ENGINE_KEYS = frozenset(
    {
        "initial_price_ticks",
        "mult",
        "maker_bps",
        "taker_bps",
        "maint_bp",
        "target_bp",
        "liquidation_latency_ns",
    }
)
FAMILY_KEYS = frozenset({"family_id", "count", "observe_interval_ns", "latency_ns", "params"})

ANCHOR_NONE = "none"
ANCHOR_SYNTHETIC = "synthetic"
# spec Q-501: direction alternates by in-family position (odd families rotate
# the remainder); an empty opposite side falls back to a limit at the initial
# price.  Frozen as enum values so a roster cannot smuggle in another rule.
ANCHOR_DIRECTION_RULES = frozenset({"family_parity"})
ANCHOR_PRICING_RULES = frozenset({"best_opposite_else_initial_limit"})
ANCHOR_KEYS = {
    ANCHOR_NONE: frozenset({"source"}),
    ANCHOR_SYNTHETIC: frozenset({"source", "quantity_units", "direction", "pricing"}),
}
# Which sources can run is owned by agent/anchor.py (registered_anchor_sources).
# ADR-014's historical_snapshot is absent from both the schema and the runtime.


class RosterError(ValueError):
    """Roster rejected; ``code`` is stable and safe to assert on."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


# --------------------------------------------------------------------------- #
# Canonical form and derived identity
# --------------------------------------------------------------------------- #


def _canonical(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _digest(payload: Any) -> str:
    return hashlib.blake2b(_canonical(payload), digest_size=16).hexdigest()


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(v) for v in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: _thaw(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_thaw(v) for v in value]
    return value


@dataclass(frozen=True)
class FamilyEntry:
    family_id: str
    count: int
    observe_interval_ns: int
    latency_ns: int
    params: Mapping[str, Any]


@dataclass(frozen=True)
class StrategyRoster:
    seed: int
    engine: Mapping[str, int]
    bootstrap_anchor: Mapping[str, Any]
    families: tuple[FamilyEntry, ...]

    def body(self) -> dict[str, Any]:
        """The canonical, hashed content (derived fields excluded)."""
        return {
            "schema_version": SCHEMA_VERSION,
            "seed": self.seed,
            "engine": _thaw(self.engine),
            "bootstrap_anchor": _thaw(self.bootstrap_anchor),
            "families": [
                {
                    "family_id": f.family_id,
                    "count": f.count,
                    "observe_interval_ns": f.observe_interval_ns,
                    "latency_ns": f.latency_ns,
                    "params": _thaw(f.params),
                }
                for f in self.families
            ],
        }

    @property
    def roster_id(self) -> str:
        return f"roster-{_digest(self.body())}"

    @property
    def engine_config_digest(self) -> str:
        return _digest(_thaw(self.engine))

    def to_json(self) -> str:
        payload = self.body()
        payload["roster_id"] = self.roster_id
        payload["engine_config_digest"] = self.engine_config_digest
        return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


# --------------------------------------------------------------------------- #
# Validation helpers
# --------------------------------------------------------------------------- #


def _require_keys(obj: Any, allowed: frozenset[str], where: str) -> None:
    if not isinstance(obj, Mapping):
        raise RosterError("INVALID_VALUE", f"{where} must be an object")
    unknown = sorted(set(obj) - allowed)
    if unknown:
        raise RosterError("UNKNOWN_FIELD", f"{where} has unknown fields {unknown}")
    missing = sorted(allowed - set(obj))
    if missing:
        raise RosterError("MISSING_FIELD", f"{where} is missing {missing}")


def _int(value: Any, where: str, *, minimum: int | None = None) -> int:
    if type(value) is not int:
        raise RosterError("INVALID_VALUE", f"{where} must be an int, got {value!r}")
    if minimum is not None and value < minimum:
        raise RosterError("INVALID_VALUE", f"{where} must be >= {minimum}, got {value}")
    return value


def _str(value: Any, where: str) -> str:
    if type(value) is not str or not value:
        raise RosterError("INVALID_VALUE", f"{where} must be a non-empty string")
    return value


# --------------------------------------------------------------------------- #
# Families (T964 replaces this table with the TraderStrategy registry)
# --------------------------------------------------------------------------- #

_MM_PARAMS = frozenset(
    {"leverage_tier", "half_spread_ticks", "quote_size", "max_inventory", "inventory_skew_k_bp"}
)
_GOAL_PARAMS = frozenset(
    {
        "goal_model_id",
        "leverage_tier",
        "risk_appetite_x1000",
        "aggressiveness_bp",
        "max_order_qty",
        "ewma_half_life_trades",
    }
)


def _validate_mm_params(params: Mapping[str, Any], where: str) -> None:
    _require_keys(params, _MM_PARAMS, where)
    _int(params["leverage_tier"], f"{where}.leverage_tier", minimum=1)
    for key in ("half_spread_ticks", "quote_size", "max_inventory"):
        _int(params[key], f"{where}.{key}", minimum=1)
    _int(params["inventory_skew_k_bp"], f"{where}.inventory_skew_k_bp", minimum=0)


def _validate_goal_params(params: Mapping[str, Any], where: str) -> None:
    _require_keys(params, _GOAL_PARAMS, where)
    goal_model_id = _str(params["goal_model_id"], f"{where}.goal_model_id")
    try:
        get_goal_model(goal_model_id)
    except KeyError as exc:
        raise RosterError("INVALID_VALUE", f"{where}.goal_model_id: {exc}") from exc
    _int(params["leverage_tier"], f"{where}.leverage_tier", minimum=1)
    _int(params["risk_appetite_x1000"], f"{where}.risk_appetite_x1000", minimum=1)
    _int(params["aggressiveness_bp"], f"{where}.aggressiveness_bp", minimum=0)
    _int(params["max_order_qty"], f"{where}.max_order_qty", minimum=1)
    _int(params["ewma_half_life_trades"], f"{where}.ewma_half_life_trades", minimum=0)


# 0.4.1 T965 (TR-501): the information tier each roster family declares, used
# to label its agents' decision records.  The market maker quotes off the top
# of book and its own inventory (I0); the goal families also read the public
# trade tape and completed bars (I2).  T968/T969's families declare their own
# tier when they join ``_FAMILIES``.
_FAMILY_TIERS = {
    "inventory_market_maker": "I0",
    "goal_belief": "I2",
    "trend_following": "I2",
    "mean_reversion": "I1",
    "sentiment_noise": "I0",
    "market_maker_v2": "I0",
}

#: 0.4.1 T966: the native families' agent-level parameters.  The family's own
#: constants (horizons, thresholds, quote dispersion) are frozen in the family
#: itself -- a roster picks who trades and how much, not how the family thinks.
_TRADER_PARAMS = frozenset(
    {
        "leverage_tier",
        "risk_appetite_x1000",
        "aggressiveness_bp",
        "max_order_qty",
        "ewma_half_life_trades",
    }
)
_MM_V2_PARAMS = frozenset(
    {"leverage_tier", "base_half_spread_ticks", "half_spread_dispersion_ticks"}
)


def _build_mm(agent_id: str, family: FamilyEntry) -> AgentSpec:
    p = family.params
    return AgentSpec(
        agent_id=agent_id,
        role="inventory_market_maker",
        strategy_family_id=family.family_id,
        info_tier=_FAMILY_TIERS[family.family_id],
        observe_interval_ns=family.observe_interval_ns,
        latency_ns=family.latency_ns,
        is_market_maker=True,
        leverage_tier=p["leverage_tier"],
        initial_bp=initial_margin_bp_for_tier(p["leverage_tier"]),
        half_spread_ticks=p["half_spread_ticks"],
        quote_size=p["quote_size"],
        max_inventory=p["max_inventory"],
        inventory_skew_k_bp=p["inventory_skew_k_bp"],
    )


def _build_goal(agent_id: str, family: FamilyEntry) -> AgentSpec:
    p = family.params
    return AgentSpec(
        agent_id=agent_id,
        role="belief_trader",
        strategy_family_id=family.family_id,
        info_tier=_FAMILY_TIERS[family.family_id],
        observe_interval_ns=family.observe_interval_ns,
        latency_ns=family.latency_ns,
        leverage_tier=p["leverage_tier"],
        initial_bp=initial_margin_bp_for_tier(p["leverage_tier"]),
        goal_model_id=p["goal_model_id"],
        risk_appetite_x1000=p["risk_appetite_x1000"],
        aggressiveness_bp=p["aggressiveness_bp"],
        max_order_qty=p["max_order_qty"],
        ewma_half_life_trades=p["ewma_half_life_trades"],
    )


def _validate_trader_params(params: Mapping[str, Any], where: str) -> None:
    _require_keys(params, _TRADER_PARAMS, where)
    _int(params["leverage_tier"], f"{where}.leverage_tier", minimum=1)
    _int(params["risk_appetite_x1000"], f"{where}.risk_appetite_x1000", minimum=1)
    _int(params["aggressiveness_bp"], f"{where}.aggressiveness_bp", minimum=0)
    _int(params["max_order_qty"], f"{where}.max_order_qty", minimum=1)
    # 锚只在预热期生效，半衰期为 0 的代理永远不会被锚到（anchor.resolve_for_agents
    # 会 fail closed）；这里要求 >= 1，让「声明了锚却永不生效」在装配期就暴露。
    _int(params["ewma_half_life_trades"], f"{where}.ewma_half_life_trades", minimum=1)


def _validate_mm_v2_params(params: Mapping[str, Any], where: str) -> None:
    _require_keys(params, _MM_V2_PARAMS, where)
    _int(params["leverage_tier"], f"{where}.leverage_tier", minimum=1)
    base = _int(params["base_half_spread_ticks"], f"{where}.base_half_spread_ticks", minimum=1)
    dispersion = _int(
        params["half_spread_dispersion_ticks"],
        f"{where}.half_spread_dispersion_ticks",
        minimum=0,
    )
    if dispersion >= base:
        # 分散 >= 基准会让半价差可能为 0 或负；装配期就拒绝，不留到运行期。
        raise RosterError(
            "INVALID_VALUE",
            f"{where}.half_spread_dispersion_ticks 必须 < base_half_spread_ticks（{base}）",
        )


def _build_native_trader(agent_id: str, family: FamilyEntry, ordinal: int) -> AgentSpec:
    """A target-position family's agent: it rides the GoalModel seam (T966 bridge)."""
    p = family.params
    private: dict[str, int] | None = None
    if family.family_id == "trend_following":
        # 多时间尺度是逐代理的：按族内序号铺开，同一族的代理才会彼此分歧。
        private = {"time_scale_index": ordinal % len(TREND_TIME_SCALES)}
    return AgentSpec(
        agent_id=agent_id,
        role="belief_trader",
        strategy_family_id=family.family_id,
        info_tier=_FAMILY_TIERS[family.family_id],
        strategy_private=private,
        observe_interval_ns=family.observe_interval_ns,
        latency_ns=family.latency_ns,
        leverage_tier=p["leverage_tier"],
        initial_bp=initial_margin_bp_for_tier(p["leverage_tier"]),
        goal_model_id=family.family_id,
        risk_appetite_x1000=p["risk_appetite_x1000"],
        aggressiveness_bp=p["aggressiveness_bp"],
        max_order_qty=p["max_order_qty"],
        # 预热期由锚驱动（spec Q-501 的退出判据：样本数 >= 2 × 半衰期）；预热
        # 结束时公开成交流也够这些族形成信号，一个判据覆盖两种冷启动。
        ewma_half_life_trades=p["ewma_half_life_trades"],
    )


def _build_mm_v2(agent_id: str, family: FamilyEntry, ordinal: int) -> AgentSpec:
    """The v2 quoting family: same market-maker branch, family-owned quote rule."""
    p = family.params
    return AgentSpec(
        strategy_private={
            # 装配清单覆盖族的报价分散（T973）；族内默认值不变。
            "mm_base_half_spread_ticks": p["base_half_spread_ticks"],
            "mm_half_spread_dispersion_ticks": p["half_spread_dispersion_ticks"],
        },
        agent_id=agent_id,
        role="inventory_market_maker",
        strategy_family_id=family.family_id,
        info_tier=_FAMILY_TIERS[family.family_id],
        observe_interval_ns=family.observe_interval_ns,
        latency_ns=family.latency_ns,
        is_market_maker=True,
        leverage_tier=p["leverage_tier"],
        initial_bp=initial_margin_bp_for_tier(p["leverage_tier"]),
    )


_FAMILIES: dict[
    str,
    tuple[Callable[[Mapping[str, Any], str], None], Callable[[str, FamilyEntry, int], AgentSpec]],
] = {
    "inventory_market_maker": (_validate_mm_params, lambda a, f, _i: _build_mm(a, f)),
    "goal_belief": (_validate_goal_params, lambda a, f, _i: _build_goal(a, f)),
    "trend_following": (_validate_trader_params, _build_native_trader),
    "mean_reversion": (_validate_trader_params, _build_native_trader),
    "sentiment_noise": (_validate_trader_params, _build_native_trader),
    "market_maker_v2": (_validate_mm_v2_params, _build_mm_v2),
}


# --------------------------------------------------------------------------- #
# Parse / persist / rebuild
# --------------------------------------------------------------------------- #


def _parse_anchor(anchor: Any) -> Mapping[str, Any]:
    if not isinstance(anchor, Mapping):
        raise RosterError("INVALID_VALUE", "bootstrap_anchor must be an object")
    source = anchor.get("source")
    if source not in ANCHOR_KEYS:
        raise RosterError("UNKNOWN_ANCHOR_SOURCE", f"bootstrap_anchor.source {source!r}")
    _require_keys(anchor, ANCHOR_KEYS[source], "bootstrap_anchor")
    if source == ANCHOR_SYNTHETIC:
        _int(anchor["quantity_units"], "bootstrap_anchor.quantity_units", minimum=1)
        if anchor["direction"] not in ANCHOR_DIRECTION_RULES:
            raise RosterError(
                "INVALID_VALUE", f"bootstrap_anchor.direction {anchor['direction']!r}"
            )
        if anchor["pricing"] not in ANCHOR_PRICING_RULES:
            raise RosterError("INVALID_VALUE", f"bootstrap_anchor.pricing {anchor['pricing']!r}")
    return _freeze(dict(anchor))


def parse_roster(payload: Mapping[str, Any]) -> StrategyRoster:
    """Validate a roster body (derived fields, if present, are ignored here)."""
    body = (
        {k: v for k, v in payload.items() if k not in DERIVED_KEYS}
        if isinstance(payload, Mapping)
        else payload
    )
    _require_keys(body, TOP_LEVEL_KEYS, "roster")
    if body["schema_version"] != SCHEMA_VERSION or type(body["schema_version"]) is not int:
        raise RosterError(
            "SCHEMA_VERSION_UNSUPPORTED", f"schema_version {body['schema_version']!r}"
        )
    seed = _int(body["seed"], "seed", minimum=0)

    engine = body["engine"]
    _require_keys(engine, ENGINE_KEYS, "engine")
    for key in sorted(ENGINE_KEYS):
        minimum = None if key in {"maker_bps", "taker_bps"} else 1
        _int(engine[key], f"engine.{key}", minimum=minimum)

    anchor = _parse_anchor(body["bootstrap_anchor"])

    raw_families = body["families"]
    if not isinstance(raw_families, list) or not raw_families:
        raise RosterError("INVALID_VALUE", "families must be a non-empty list")
    families: list[FamilyEntry] = []
    seen: set[str] = set()
    for i, raw in enumerate(raw_families):
        where = f"families[{i}]"
        _require_keys(raw, FAMILY_KEYS, where)
        family_id = _str(raw["family_id"], f"{where}.family_id")
        if family_id not in _FAMILIES:
            raise RosterError("UNKNOWN_FAMILY", f"{where}.family_id {family_id!r}")
        if family_id in seen:
            raise RosterError("DUPLICATE_FAMILY", f"{where}.family_id {family_id!r}")
        seen.add(family_id)
        validate_params, _ = _FAMILIES[family_id]
        validate_params(raw["params"], f"{where}.params")
        families.append(
            FamilyEntry(
                family_id=family_id,
                count=_int(raw["count"], f"{where}.count", minimum=1),
                observe_interval_ns=_int(
                    raw["observe_interval_ns"], f"{where}.observe_interval_ns", minimum=1
                ),
                latency_ns=_int(raw["latency_ns"], f"{where}.latency_ns", minimum=1),
                params=_freeze(dict(raw["params"])),
            )
        )
    return StrategyRoster(
        seed=seed,
        engine=_freeze(dict(engine)),
        bootstrap_anchor=anchor,
        families=tuple(families),
    )


def save_roster(roster: StrategyRoster, directory: str | pathlib.Path) -> pathlib.Path:
    """Write ``<directory>/<roster_id>.json``; the file name is the identity."""
    out = pathlib.Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{roster.roster_id}.json"
    path.write_text(roster.to_json(), encoding="utf-8")
    return path


def load_roster(directory: str | pathlib.Path, roster_id: str) -> StrategyRoster:
    """Rebuild a roster from its id; the content must still hash to that id."""
    path = pathlib.Path(directory) / f"{roster_id}.json"
    if not path.is_file():
        raise RosterError("ROSTER_NOT_FOUND", f"{path.as_posix()} does not exist")
    payload = json.loads(path.read_text(encoding="utf-8"))
    roster = parse_roster(payload)
    for key, derived in (
        ("roster_id", roster.roster_id),
        ("engine_config_digest", roster.engine_config_digest),
    ):
        if payload.get(key) != derived:
            raise RosterError(
                "ROSTER_ID_MISMATCH",
                f"{path.name}: recorded {key} {payload.get(key)!r} != derived {derived!r}",
            )
    if roster.roster_id != roster_id:
        raise RosterError(
            "ROSTER_ID_MISMATCH", f"{path.name} derives {roster.roster_id}, requested {roster_id}"
        )
    return roster


def build_agent_specs(roster: StrategyRoster) -> list[AgentSpec]:
    """Expand families into agents, in roster order; ids are ``<family>-<i>``."""
    specs: list[AgentSpec] = []
    for family in roster.families:
        _, build = _FAMILIES[family.family_id]
        specs.extend(build(f"{family.family_id}-{i}", family, i) for i in range(family.count))
    return specs


def _runtime_anchor(roster: StrategyRoster, specs: list[AgentSpec]) -> dict[str, Any] | None:
    """The roster's anchor plus the goal-agent families its direction rule runs over."""
    anchor = _thaw(roster.bootstrap_anchor)
    if anchor["source"] == ANCHOR_NONE:
        return None
    families: list[list[Any]] = []
    start = 0
    for family in roster.families:
        members = specs[start : start + family.count]
        start += family.count
        if all(s.goal_model_id is not None and not s.is_market_maker for s in members):
            families.append([family.family_id, [s.agent_id for s in members]])
    return {**anchor, "families": families}


def build_experiment_config(roster: StrategyRoster, *, max_transactions: int) -> ExperimentConfig:
    """Assemble a runnable config from a roster (fail closed on unrunnable anchors)."""
    source = roster.bootstrap_anchor["source"]
    if source not in registered_anchor_sources():
        raise RosterError(
            "ANCHOR_SOURCE_NOT_IMPLEMENTED",
            f"bootstrap_anchor.source {source!r} has no runtime",
        )
    specs = build_agent_specs(roster)
    anchor = _runtime_anchor(roster, specs)
    try:
        resolve_for_agents(anchor, specs)
    except AnchorError as exc:
        raise RosterError(exc.code, str(exc)) from exc
    engine = roster.engine
    return ExperimentConfig(
        seed=roster.seed,
        max_transactions=_int(max_transactions, "max_transactions", minimum=1),
        initial_price_ticks=engine["initial_price_ticks"],
        mult=engine["mult"],
        maker_bps=engine["maker_bps"],
        taker_bps=engine["taker_bps"],
        maint_bp=engine["maint_bp"],
        target_bp=engine["target_bp"],
        liquidation_latency_ns=engine["liquidation_latency_ns"],
        agent_specs=specs,
        bootstrap_anchor=anchor,
    )
