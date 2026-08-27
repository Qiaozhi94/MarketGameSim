"""T204: v2 goal-driven agent decision layer (代理策略 §5.2, ADR-003).

Architectural boundary (ADR-003 §1, frozen in ``goal_contract_v2.json``):

    preferences + private state + permitted observations
        -> GoalModel
        -> desired_position_units
        -> InstitutionalConstraint (agent/constraint.py)
        -> executable_position_units
        -> order intents

The goal layer **must not read institutional fields** -- ``leverage_tier``,
``initial_bp``, ``maint_bp``, the experiment arm identifiers ``L`` / ``M`` or
``arm_id`` (代理策略 §5.2, ADR-003 §1).  Those only enter the constraint /
admission / risk / liquidation stages.  ``risk_appetite_x1000`` is an agent
*preference* drawn once per run independent of all institutional fields
(``goal_contract_v2.json::risk_appetite.independent_of``).

Current equity is a permitted private state (代理策略 §5.2: "当前权益可以作为
私有状态参与风险预算"); it enters ``max_notional`` but the institutional
multiplier (``leverage_tier``) does not.

Stdlib only (KR-005).  Integer arithmetic, ``trunc`` toward zero (ADR-001).
"""

from __future__ import annotations

import abc
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

# Re-exported constraint enums live in agent/constraint.py; imported here only
# for the DecisionEvidenceV1 builder to avoid a hard cycle (constraint.py does
# not import goal.py -- the dependency is one-way: goal -> constraint enums).
from market_game_sim.agent.constraint import (
    ConstraintReason,
    ExecutableDecision,
    TriggerProvenance,
)

# --------------------------------------------------------------------------- #
# Frozen V1 structures (goal_contract_v2.json::structures)
# --------------------------------------------------------------------------- #
# Each dataclass mirrors the closed field set frozen in the schema.  Unknown
# fields fail closed (代理策略 §5.2 / ADR-003 §2: "未知字段 fail closed").


@dataclass(frozen=True)
class BookTop:
    """Top-of-book snapshot (InformationSetV1.book_top).

    ``valuation_mark_half_ticks`` = ``best_bid + best_ask`` (an integer even
    when the mid is x.5 ticks); ``None`` when both sides are empty.
    """

    best_bid: int | None
    best_ask: int | None
    valuation_mark_half_ticks: int | None

    def __post_init__(self) -> None:
        # R018-C009 (Round 5): exact types; None allowed (empty side).
        for fname, value in (
            ("best_bid", self.best_bid),
            ("best_ask", self.best_ask),
            ("valuation_mark_half_ticks", self.valuation_mark_half_ticks),
        ):
            if value is not None and type(value) is not int:
                raise ValueError(f"BookTop.{fname} must be int or None, got {type(value).__name__}")


@dataclass(frozen=True)
class OwnAccountView:
    """Permitted account-derived fields only (ADR-003 §1).

    Carries *only* the private-state fields the goal layer is allowed to read:
    wallet, position, entry notional.  ``leverage_tier`` / ``initial_bp`` /
    ``maint_bp`` / ``L`` / ``M`` / ``arm_id`` are deliberately absent -- they
    belong to the constraint layer.
    """

    wallet_units: int
    position_units: int
    entry_notional_units: int

    def __post_init__(self) -> None:
        # R018-C009 (Round 5): exact types (bool excluded).
        for fname, value in (
            ("wallet_units", self.wallet_units),
            ("position_units", self.position_units),
            ("entry_notional_units", self.entry_notional_units),
        ):
            if type(value) is not int:
                raise ValueError(f"OwnAccountView.{fname} must be int, got {type(value).__name__}")


@dataclass(frozen=True)
class PublicTrade:
    """One observed public trade (InformationSetV1.public_trades[])."""

    price_ticks: int
    quantity_units: int
    timestamp: int

    def __post_init__(self) -> None:
        # R018-C009 (Round 5): exact types.
        for fname, value in (
            ("price_ticks", self.price_ticks),
            ("quantity_units", self.quantity_units),
            ("timestamp", self.timestamp),
        ):
            if type(value) is not int:
                raise ValueError(f"PublicTrade.{fname} must be int, got {type(value).__name__}")


@dataclass(frozen=True)
class CompletedBar:
    """One completed bar (InformationSetV1.completed_bars[])."""

    open: int
    high: int
    low: int
    close: int
    volume: int
    trade_count: int

    def __post_init__(self) -> None:
        # R018-C009 (Round 5): exact types + non-negative volume/count.
        for fname, value in (
            ("open", self.open),
            ("high", self.high),
            ("low", self.low),
            ("close", self.close),
            ("volume", self.volume),
            ("trade_count", self.trade_count),
        ):
            if type(value) is not int:
                raise ValueError(f"CompletedBar.{fname} must be int, got {type(value).__name__}")
        if self.volume < 0 or self.trade_count < 0:
            raise ValueError("CompletedBar.volume / trade_count must be >= 0")


@dataclass(frozen=True)
class InformationSetV1:
    """InformationSetV1 (goal_contract_v2.json::structures).

    The closed inputs a goal model may consume: the public trade tape slice
    since this agent's last cursor, completed bars, the top of book, and a
    view of the agent's own account carrying *only* permitted fields.
    """

    schema_version: int
    cursor_from_event_id: str
    cursor_to_event_id: str
    public_trades: Sequence[PublicTrade]
    completed_bars: Sequence[CompletedBar]
    book_top: BookTop | None
    own_account: OwnAccountView

    def __post_init__(self) -> None:
        # R018-C009 (Round 3/5): versioned closed schema rejects unknown
        # versions; cursor ids are strings; nested entries are typed objects.
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError(
                f"InformationSetV1.schema_version must be 1, got {self.schema_version!r}"
            )
        for fname, value in (
            ("cursor_from_event_id", self.cursor_from_event_id),
            ("cursor_to_event_id", self.cursor_to_event_id),
        ):
            if type(value) is not str:
                raise ValueError(
                    f"InformationSetV1.{fname} must be str, got {type(value).__name__}"
                )
        for fname, expected, value in (
            ("public_trades", PublicTrade, self.public_trades),
            ("completed_bars", CompletedBar, self.completed_bars),
        ):
            if not isinstance(value, Sequence) or not all(
                isinstance(item, expected) for item in value
            ):
                raise ValueError(
                    f"InformationSetV1.{fname} must be a sequence of {expected.__name__}"
                )
        if self.book_top is not None and not isinstance(self.book_top, BookTop):
            raise ValueError("InformationSetV1.book_top must be BookTop or None")
        if not isinstance(self.own_account, OwnAccountView):
            raise ValueError(
                f"InformationSetV1.own_account must be OwnAccountView, got "
                f"{type(self.own_account).__name__}"
            )


@dataclass(frozen=True)
class AgentInternalStateV1:
    """AgentInternalStateV1 (goal_contract_v2.json::structures).

    ``ewma_value_units`` / ``ewma_sample_count`` are the per-agent EWMA anchor
    (T206/T207 maintain the EWMA update; T204/T205 only consume the warmup
    branch + the data fields per the frozen schema).  ``model_private_state``
    is a model-specific bag (e.g. ``{"signal_bp": ..., "last_held": ...}``).
    """

    schema_version: int
    last_seen_market_event_id: str
    ewma_value_units: int | None
    ewma_sample_count: int
    model_private_state: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # R018-C009 (Round 3/5): versioned closed schema rejects unknown
        # versions; cursor str; EWMA types + non-negative count.
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError(
                f"AgentInternalStateV1.schema_version must be 1, got {self.schema_version!r}"
            )
        if type(self.last_seen_market_event_id) is not str:
            raise ValueError(
                f"AgentInternalStateV1.last_seen_market_event_id must be str, got "
                f"{type(self.last_seen_market_event_id).__name__}"
            )
        if self.ewma_value_units is not None and type(self.ewma_value_units) is not int:
            raise ValueError(
                f"AgentInternalStateV1.ewma_value_units must be int or None, got "
                f"{type(self.ewma_value_units).__name__}"
            )
        if type(self.ewma_sample_count) is not int or self.ewma_sample_count < 0:
            raise ValueError("AgentInternalStateV1.ewma_sample_count must be a non-negative int")
        # R018-C009 (Round 7): model_private_state must be a Mapping, not a
        # list / scalar (a list would break keyed access downstream).
        if not isinstance(self.model_private_state, Mapping):
            raise ValueError(
                f"AgentInternalStateV1.model_private_state must be a Mapping, got "
                f"{type(self.model_private_state).__name__}"
            )


@dataclass(frozen=True)
class AgentPreferences:
    """Agent preferences (permitted, non-institutional).

    ``risk_appetite_x1000`` is "我愿意把权益放大多少倍" (behavior), drawn once
    per run independent of ``leverage_tier`` (制度允许放大多少倍).  Bounds
    ``[500, 20000]`` x1000 (goal_contract_v2.json::risk_appetite.bounds).
    """

    risk_appetite_x1000: int

    def __post_init__(self) -> None:
        # R018-C009 (Round 3): validate the frozen bounds + reject bool
        # (type(x) is int excludes bool, which isinstance would accept).
        value = self.risk_appetite_x1000
        if type(value) is not int:
            raise ValueError(f"risk_appetite_x1000 must be an int, got {type(value).__name__}")
        if not 500 <= value <= 20_000:
            raise ValueError(f"risk_appetite_x1000 must be in [500, 20000], got {value}")


class GoalRng(Protocol):
    """Deterministic RNG channel for goal models that need a draw (代理策略 §10).

    Linear / threshold models are deterministic and ignore ``rng``; it is part
    of the interface for future models.  ``uniform(mechanism, draw_index)``
    returns a ``Decimal`` in (0, 1) keyed by a *new* mechanism string (never
    reuses ``noise_factor`` / ``belief_weights`` -- KR-004 reproducibility).
    """

    def uniform(self, mechanism: str, draw_index: int) -> Decimal: ...


@dataclass(frozen=True)
class GoalDecision:
    """Output of ``GoalModel.decide`` -- the pre-constraint target.

    ``desired_position_units`` is ``None`` when the decision is skipped
    (代理策略 §5.2.3: ``valuation_mark`` undefined -> skip, no order).
    ``action`` is one of ``"emit_decision"`` / ``"skip_decision"`` /
    ``"reduce_only"``.  ``degenerate_reason`` carries the constraint_reason the
    degenerate branch maps to (``None`` for the normal equation path).
    """

    desired_position_units: int | None
    action: str
    degenerate_reason: ConstraintReason | None
    updated_state: AgentInternalStateV1


@dataclass(frozen=True)
class DecisionEvidenceV1:
    """DecisionEvidenceV1 (goal_contract_v2.json::structures).

    Every agent decision records the goal model used, the pre- and
    post-constraint targets, the binding status / reason and the trigger
    provenance, plus the event-id cursors that anchor the KPI-006 traceability
    chain (event-schema.md §4.4).  For T204/T205 the cursor / observation
    event-id fields are placeholders (the tape/cursor wiring is T206); the
    *object shape* must match the frozen schema exactly.
    """

    schema_version: int
    goal_model_id: str
    goal_model_version: int
    desired_position_units: int
    executable_position_units: int
    constraint_binding: bool
    constraint_reason: ConstraintReason | None
    trigger_provenance: TriggerProvenance
    observation_event_id: str
    cursor_from_event_id: str
    cursor_to_event_id: str


# --------------------------------------------------------------------------- #
# Pure integer helpers (ADR-001: trunc toward zero; no floats)
# --------------------------------------------------------------------------- #


def trunc_toward_zero(numerator: int, denominator: int) -> int:
    """Integer division truncated toward zero (ADR-001).

    Python ``//`` floors toward -inf, so negative quotients are off-by-one;
    match the canonical recomputation in ``spec_validation._trunc_div``.
    """
    if denominator == 0:
        return 0
    quotient = abs(numerator) // denominator
    return quotient if numerator >= 0 else -quotient


def valuation_mark_ticks(book_top: BookTop | None) -> int | None:
    """Valuation mark in whole ticks (代理策略 §5.1: half-ticks // 2).

    Returns ``None`` when the book is empty on both sides (代理策略 §5.2.3:
    ``valuation_mark`` undefined -> skip decision).
    """
    if book_top is None or book_top.valuation_mark_half_ticks is None:
        return None
    half = book_top.valuation_mark_half_ticks
    if half <= 0:
        return None
    return half // 2


def equity_units(own: OwnAccountView, mark_ticks: int, mult: int) -> int:
    """Risk equity in cash units (账户合同 §2.2): ``wallet + position*mark*MULT
    - entry_notional``.

    Permitted for the goal layer (代理策略 §5.2: current equity is private
    state).  No institutional multiplier enters here.
    """
    return own.wallet_units + own.position_units * mark_ticks * mult - own.entry_notional_units


# --------------------------------------------------------------------------- #
# GoalModel interface
# --------------------------------------------------------------------------- #


class GoalModel(abc.ABC):
    """Goal formation (代理策略 §5.2.1): permitted observations + preferences
    + private state -> ``desired_position_units``.

    The parameter types (InformationSetV1 / AgentInternalStateV1 /
    AgentPreferences / GoalRng) deliberately expose **no** institutional or
    arm fields -- ADR-003 §1.  The model returns only the desired target;
    margin feasibility is the constraint layer's job (agent/constraint.py).
    """

    id: str
    version: int

    @abc.abstractmethod
    def decide(
        self,
        information_set: InformationSetV1,
        internal_state: AgentInternalStateV1,
        preferences: AgentPreferences,
        rng: GoalRng | None = None,
    ) -> GoalDecision: ...


# --------------------------------------------------------------------------- #
# Degenerate-input handling (代理策略 §5.2.3)
# --------------------------------------------------------------------------- #


def _warmup(internal_state: AgentInternalStateV1, half_life_in_trades: int) -> bool:
    """EWMA warmup: ``sample_count < 2 * half_life`` (代理策略 §5.2.3).

    T206/T207 maintain the EWMA update; T204/T205 only consume the warmup
    branch + the frozen data fields.  A non-positive ``half_life_in_trades``
    disables warmup (the model has no EWMA anchor yet).
    """
    if half_life_in_trades <= 0:
        return False
    return internal_state.ewma_sample_count < 2 * half_life_in_trades


def _degenerate(
    information_set: InformationSetV1,
    internal_state: AgentInternalStateV1,
    mult: int,
    half_life_in_trades: int,
) -> GoalDecision | None:
    """Apply 代理策略 §5.2.3 degenerate rules in their fixed order.

    Returns a ``GoalDecision`` for the degenerate case, or ``None`` to let the
    model equation run.  Order matters: mark-undefined -> skip, then
    non-positive-equity -> reduce-only, then EWMA warmup -> zero target.
    """
    mark = valuation_mark_ticks(information_set.book_top)
    if mark is None or mark <= 0:
        # valuation_mark undefined (both sides empty, no trades) -> skip.
        return GoalDecision(
            desired_position_units=None,
            action="skip_decision",
            degenerate_reason=ConstraintReason.MARK_UNDEFINED,
            updated_state=internal_state,
        )
    eq = equity_units(information_set.own_account, mark, mult)
    if eq <= 0:
        # equity <= 0 -> desired 0, reduce-only (do not skip: a frozen account
        # must still be able to self-rescue, else liquidation-chain dynamics
        # are masked -- 代理策略 §5.2.3).
        return GoalDecision(
            desired_position_units=0,
            action="reduce_only",
            degenerate_reason=ConstraintReason.NON_POSITIVE_EQUITY,
            updated_state=internal_state,
        )
    if _warmup(internal_state, half_life_in_trades):
        # EWMA warmup -> cold-start anchor, desired 0, still emit a decision.
        return GoalDecision(
            desired_position_units=0,
            action="emit_decision",
            degenerate_reason=ConstraintReason.EWMA_WARMUP,
            updated_state=internal_state,
        )
    return None


# --------------------------------------------------------------------------- #
# Primary model: risk_budget_linear_v1
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RiskBudgetLinearV1(GoalModel):
    """``risk_budget_linear_v1`` (goal_contract_v2.json::goal_models).

    ```text
    max_notional    = equity_units * risk_appetite_x1000 // 1000
    max_position    = max_notional // mark                 # min_quantity units
    desired         = trunc(signal_bp * max_position / 10000)   # toward zero
    ```

    ``signal_bp`` is a permitted observation carried in
    ``internal_state.model_private_state["signal_bp"]`` (the factor pipeline
    -- agent/handler.py::_compute_belief_signal -- is unchanged for T204/T205;
    it is not an institutional field).  Saturation clamps at the feasible
    boundary, never errors.
    """

    id: str = "risk_budget_linear_v1"
    version: int = 1
    half_life_in_trades: int = 0  # EWMA anchor optional for the linear model
    mult: int = 1000

    def decide(
        self,
        information_set: InformationSetV1,
        internal_state: AgentInternalStateV1,
        preferences: AgentPreferences,
        rng: GoalRng | None = None,
    ) -> GoalDecision:
        deg = _degenerate(information_set, internal_state, self.mult, self.half_life_in_trades)
        if deg is not None:
            return deg
        mark = valuation_mark_ticks(information_set.book_top)
        assert mark is not None and mark > 0  # _degenerate already ruled out None
        eq = equity_units(information_set.own_account, mark, self.mult)
        max_notional = eq * preferences.risk_appetite_x1000 // 1000
        max_position = max_notional // mark if max_notional > 0 else 0
        signal_bp = int(internal_state.model_private_state.get("signal_bp", 0))
        desired = trunc_toward_zero(signal_bp * max_position, 10_000)
        return GoalDecision(
            desired_position_units=desired,
            action="emit_decision",
            degenerate_reason=None,
            updated_state=internal_state,
        )


# --------------------------------------------------------------------------- #
# Robustness model: risk_budget_threshold_v1 (hysteresis)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RiskBudgetThresholdV1(GoalModel):
    """``risk_budget_threshold_v1`` (goal_contract_v2.json::goal_models).

    Hysteresis step mapping (代理策略 §5.2.1):

    ```text
    |signal_bp| >= theta_in  -> sign(signal_bp) * trunc(k_x1000 * max_position / 1000)
    |signal_bp| <= theta_out AND has position -> 0
    theta_out < |signal_bp| < theta_in        -> HOLD current position
    ```

    Bounds (frozen, preregistered): ``0 < theta_out < theta_in <= 10000``,
    ``0 < k_x1000 <= 1000``.  Hysteresis (``theta_out < theta_in``) is
    mandatory -- without it a signal jittering at the threshold would churn
    the agent in and out at full size, fabricating volume unrelated to the
    market.  ``theta_in`` / ``theta_out`` / ``k_x1000`` are experiment design,
    frozen in preregistration.
    """

    theta_in: int
    theta_out: int
    k_x1000: int
    id: str = "risk_budget_threshold_v1"
    version: int = 1
    half_life_in_trades: int = 0
    mult: int = 1000

    def __post_init__(self) -> None:
        # param_bounds (goal_contract_v2.json::goal_models.risk_budget_
        # threshold_v1.param_bounds) -- validated at construction so a
        # misconfigured model fails closed before any decision.
        if not (1 <= self.theta_in <= 10_000):
            raise ValueError(f"theta_in must be in [1, 10000], got {self.theta_in}")
        if not (1 <= self.theta_out < self.theta_in):
            raise ValueError(
                f"theta_out must be in [1, theta_in) i.e. [1, {self.theta_in}), "
                f"got {self.theta_out}"
            )
        if not (1 <= self.k_x1000 <= 1000):
            raise ValueError(f"k_x1000 must be in [1, 1000], got {self.k_x1000}")

    def decide(
        self,
        information_set: InformationSetV1,
        internal_state: AgentInternalStateV1,
        preferences: AgentPreferences,
        rng: GoalRng | None = None,
    ) -> GoalDecision:
        deg = _degenerate(information_set, internal_state, self.mult, self.half_life_in_trades)
        if deg is not None:
            return deg
        mark = valuation_mark_ticks(information_set.book_top)
        assert mark is not None and mark > 0
        eq = equity_units(information_set.own_account, mark, self.mult)
        max_notional = eq * preferences.risk_appetite_x1000 // 1000
        max_position = max_notional // mark if max_notional > 0 else 0
        signal_bp = int(internal_state.model_private_state.get("signal_bp", 0))
        current_position = information_set.own_account.position_units
        abs_signal = abs(signal_bp)
        if abs_signal >= self.theta_in:
            magnitude = trunc_toward_zero(self.k_x1000 * max_position, 1000)
            desired = magnitude if signal_bp >= 0 else -magnitude
        elif abs_signal <= self.theta_out and current_position != 0:
            desired = 0
        else:
            # Hold band: theta_out < |signal| < theta_in -> maintain position.
            desired = current_position
        return GoalDecision(
            desired_position_units=desired,
            action="emit_decision",
            degenerate_reason=None,
            updated_state=internal_state,
        )


# --------------------------------------------------------------------------- #
# Market-maker inventory goal (T205, 代理策略 §8)
# --------------------------------------------------------------------------- #
# The MM is structurally bilateral: it does not produce a single desired
# position, it posts a bid and an ask.  Its *goal* is to revert inventory
# toward 0 at the skew rate; the *quote risk policy* (agent/constraint.py::
# QuoteRiskPolicy) enforces max_inventory and the maint_bp margin limit.  The
# goal layer reads ONLY permitted inputs (inventory, half_spread, skew,
# valuation_mark) -- never leverage_tier / initial_bp / maint_bp (ADR-003 §1).


@dataclass(frozen=True)
class MarketMakerQuote:
    """One side of a raw bilateral quote (pre risk-policy)."""

    side: str  # "BUY" | "SELL"
    price_ticks: int
    quantity_units: int


@dataclass(frozen=True)
class MarketMakerGoalDecision:
    """Raw bilateral quotes from the inventory goal (pre risk-policy)."""

    bid: MarketMakerQuote | None
    ask: MarketMakerQuote | None
    # inventory goal provenance fields (populated for evidence):
    desired_position_units: int  # the MM reverts toward 0
    mid_ticks: int


@dataclass(frozen=True)
class MarketMakerGoal:
    """Inventory market-maker goal (代理策略 §8).

    ```text
    skew = inventory_skew_k_bp * (inventory / max_inventory) / 10000   # clamp [-1,1]
    bid  = mid - half_spread - skew * half_spread
    ask  = mid + half_spread - skew * half_spread
    ```

    Both sides carry ``quote_size``.  This goal layer computes *raw* quotes;
    it does NOT apply max_inventory stopping or the maint_bp margin limit --
    those are the quote risk policy (agent/constraint.py::QuoteRiskPolicy),
    which is the institutional constraint layer and may read ``maint_bp``.
    """

    half_spread_ticks: int
    quote_size: int
    max_inventory: int
    inventory_skew_k_bp: int
    id: str = "market_maker_inventory_v1"
    version: int = 1

    def decide(self, inventory: int, valuation_mark_ticks: int) -> MarketMakerGoalDecision | None:
        """Produce raw bilateral quotes.  Returns ``None`` when the mark is
        undefined or ``max_inventory`` is non-positive (代理策略 §8 boundary)."""
        if valuation_mark_ticks <= 0 or self.max_inventory <= 0:
            return None
        inv_ratio = Decimal(inventory) / Decimal(self.max_inventory)
        inv_ratio = max(Decimal(-1), min(Decimal(1), inv_ratio))
        skew_ticks = int(
            inv_ratio * self.inventory_skew_k_bp * self.half_spread_ticks / Decimal(10_000)
        )
        mid = valuation_mark_ticks
        bid_price = mid - self.half_spread_ticks - skew_ticks
        ask_price = mid + self.half_spread_ticks - skew_ticks
        bid = MarketMakerQuote(side="BUY", price_ticks=bid_price, quantity_units=self.quote_size)
        ask = MarketMakerQuote(side="SELL", price_ticks=ask_price, quantity_units=self.quote_size)
        return MarketMakerGoalDecision(
            bid=bid,
            ask=ask,
            desired_position_units=0,  # revert inventory toward 0
            mid_ticks=mid,
        )


# --------------------------------------------------------------------------- #
# DecisionEvidenceV1 builder
# --------------------------------------------------------------------------- #


def build_decision_evidence(
    goal_model: GoalModel,
    goal: GoalDecision,
    executable: ExecutableDecision,
    provenance: TriggerProvenance,
    observation_event_id: str = "",
    cursor_from_event_id: str = "",
    cursor_to_event_id: str = "",
    schema_version: int = 1,
) -> DecisionEvidenceV1:
    """Assemble ``DecisionEvidenceV1`` from a goal decision + its executable.

    The cursor / observation event-id fields are placeholders for T204/T205
    (the tape/cursor wiring is T206); the object *shape* matches the frozen
    schema exactly so the evidence is ready to emit once cursors land.
    """
    desired = goal.desired_position_units
    return DecisionEvidenceV1(
        schema_version=schema_version,
        goal_model_id=goal_model.id,
        goal_model_version=goal_model.version,
        desired_position_units=desired if desired is not None else 0,
        executable_position_units=executable.executable_position_units,
        constraint_binding=executable.constraint_binding,
        constraint_reason=executable.constraint_reason,
        trigger_provenance=provenance,
        observation_event_id=observation_event_id,
        cursor_from_event_id=cursor_from_event_id,
        cursor_to_event_id=cursor_to_event_id,
    )


# Registry of belief-agent goal models (config-selectable via AgentSpec.
# goal_model_id).  Threshold models are constructed with their frozen
# preregistered params at registration time.
_GOAL_MODELS: dict[str, GoalModel] = {}


def register_goal_model(model: GoalModel) -> None:
    _GOAL_MODELS[model.id] = model


def get_goal_model(model_id: str) -> GoalModel:
    if model_id not in _GOAL_MODELS:
        raise KeyError(f"unknown goal model: {model_id}")
    return _GOAL_MODELS[model_id]


# Default registrations: the linear primary model is always available.  The
# threshold model needs preregistered params, so callers register their own
# instance (register_goal_model) -- a default (theta_in=3000, theta_out=1200,
# k_x1000=600 matching the golden vector fixture) is provided so the registry
# is non-empty for tests / BENCHMARK wiring.
register_goal_model(RiskBudgetLinearV1())
register_goal_model(RiskBudgetThresholdV1(theta_in=3000, theta_out=1200, k_x1000=600))


__all__ = [
    "BookTop",
    "CompletedBar",
    "PublicTrade",
    "OwnAccountView",
    "InformationSetV1",
    "AgentInternalStateV1",
    "AgentPreferences",
    "GoalRng",
    "GoalDecision",
    "DecisionEvidenceV1",
    "GoalModel",
    "RiskBudgetLinearV1",
    "RiskBudgetThresholdV1",
    "MarketMakerGoal",
    "MarketMakerQuote",
    "MarketMakerGoalDecision",
    "ExecutableDecision",
    "ConstraintReason",
    "TriggerProvenance",
    "trunc_toward_zero",
    "valuation_mark_ticks",
    "equity_units",
    "build_decision_evidence",
    "register_goal_model",
    "get_goal_model",
]
