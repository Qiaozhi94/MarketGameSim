"""T204: institutional constraint layer (代理策略 §5.2.4, 账户合同 §3.3).

Architectural boundary (ADR-003 §1, 代理策略 §5.2): the goal layer produces
``desired_position_units`` from permitted observations only; the
**institutional** layer then clips that target to what the leverage / margin
regime permits.  This module is the *only* place leverage / margin parameters
enter the decision pipeline -- it MAY read ``leverage_tier`` /
``initial_bp`` / ``maint_bp`` (the goal layer in agent/goal.py MUST NOT).

Two responsibilities:

* :class:`InstitutionalConstraint` -- clips a belief agent's
  ``desired_position_units`` to the feasible margin boundary via the §3.3
  ``reserved_after <= risk_equity`` test (reusing
  ``ledger.reserved.compute_reserved_after`` so the口径 stays identical to
  admission).  Reduction is exempt; a flip clips only the new-open leg; the
  clip never flips direction.
* :class:`QuoteRiskPolicy` -- the market-maker quote risk policy (代理策略 §8):
  stops a side at ``max_inventory`` and stops both-side quoting when
  ``margin_ratio_bp < maint_bp`` (only the position-reducing side quotes).

Stdlib only (KR-005).  Integer arithmetic (ADR-001).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from enum import StrEnum

from market_game_sim.config.types import div_ceil
from market_game_sim.ledger.account import risk_equity
from market_game_sim.ledger.reserved import ActiveOrder


class ConstraintReason(StrEnum):
    """``DecisionEvidenceV1.constraint_reason`` enum (goal_contract_v2.json)."""

    MARGIN_LIMIT = "MARGIN_LIMIT"
    MAX_ORDER_QTY = "MAX_ORDER_QTY"
    MARK_UNDEFINED = "MARK_UNDEFINED"
    NON_POSITIVE_EQUITY = "NON_POSITIVE_EQUITY"
    EWMA_WARMUP = "EWMA_WARMUP"


class TriggerProvenance(StrEnum):
    """``DecisionEvidenceV1.trigger_provenance`` enum (goal_contract_v2.json)."""

    ENDOGENOUS_AGENT = "ENDOGENOUS_AGENT"
    LIQUIDATION = "LIQUIDATION"
    EXOGENOUS_STRESS = "EXOGENOUS_STRESS"


@dataclass(frozen=True)
class ExecutableDecision:
    """Post-constraint target + binding evidence.

    ``executable_position_units`` has the same sign as ``desired`` or is 0
    (代理策略 §5.2.4: 绑定只裁剪规模，不改方向).  ``constraint_reason`` is
    ``None`` when nothing bound (including the pure-reduction exemption).
    """

    executable_position_units: int
    constraint_binding: bool
    constraint_reason: ConstraintReason | None


@dataclass(frozen=True)
class ConstraintAccountView:
    """Account fields the constraint layer needs (代理策略 §5.2.4 + §11.1).

    Unlike the goal layer's :class:`OwnAccountView`, this MAY carry the
    institutional fields -- it is consumed only by the constraint layer.
    """

    wallet_units: int
    position_units: int
    entry_notional_units: int
    reserved_units: int  # current worst-case reserved margin (resting orders)


@dataclass(frozen=True)
class ConstraintPolicy:
    """Institutional regime snapshot (frozen at observe-time, 代理策略 §5.2.4).

    Binding is judged at the observe-time snapshot; the decision process does
    not recompute.  All leverage / margin parameters live here.
    """

    leverage_tier: int
    initial_bp: int
    maint_bp: int
    max_order_qty: int
    fee_bps: int  # max(maker_bps, taker_bps, 0) -- the freeze rate (§11.1)
    mult: int = 1000
    risk_mark_ticks: int = 0  # last trade price for the risk-equity口径


# --------------------------------------------------------------------------- #
# Pure clipping logic (代理策略 §5.2.4) -- matches golden_vectors.constraint
# --------------------------------------------------------------------------- #
# This is the canonical recomputation frozen in spec_validation.py::_validate
# _goal_contract_data (the constraint block).  Any change here MUST be mirrored
# there or the contract-source validator fails.


def _is_pure_reduction(position: int, desired: int) -> bool:
    """``|desired| < |position|`` and same sign (no zero crossing) -- §5.2.4:
    reduction is never margin-clipped, else an account is locked into a state
    it cannot escape, and "self-rescue failure" is misread as agent behavior.
    """
    return abs(desired) < abs(position) and position * desired >= 0


def clip_goal_to_feasible(
    position: int,
    desired: int,
    feasible_new_open: int,
) -> int:
    """Clip ``desired`` to the executable target given the margin-feasible
    new-open quantity (代理策略 §5.2.4, golden_vectors.constraint).

    * pure reduction (``|desired| < |position|``, same sign) -> ``desired``,
      margin check **skipped** (the exemption).
    * flip (``position * desired < 0``) -> only the new-open leg after zero
      participates: ``sign(desired) * feasible_new_open``.
    * add beyond limit (same sign, ``|desired| > |position|``) ->
      ``sign(desired) * (|position| + feasible_new_open)`` -- symmetric for
      long and short (R018-C004: the old ``desired > position`` test only
      caught long adds; a short add (position=-100, desired=-200) fell
      through to ``return desired`` unclipped).
    * no change / reduction-to-equal -> ``desired``.

    Direction is never flipped: the result has the same sign as ``desired`` or
    is 0.
    """
    if _is_pure_reduction(position, desired):
        return desired
    if position * desired < 0:
        # Flip: close back to 0 (no check) then open feasible on the other side.
        return -feasible_new_open if desired < 0 else feasible_new_open
    if abs(desired) > abs(position):
        # Add: the new-open leg is |desired| - |position|; clip to feasible.
        sign = -1 if desired < 0 else 1
        return sign * (abs(position) + feasible_new_open)
    return desired


def new_open_target(position: int, desired: int) -> int:
    """Quantity of *new* exposure (beyond closing the current position) that
    must pass the margin check (代理策略 §5.2.4).

    * pure reduction -> 0 (exempt)
    * flip -> ``|desired|`` (the whole post-flip position is new-open)
    * add -> ``|desired| - |position|``
    """
    if _is_pure_reduction(position, desired):
        return 0
    if position * desired < 0:
        return abs(desired)
    return max(abs(desired) - abs(position), 0)


# --------------------------------------------------------------------------- #
# InstitutionalConstraint: margin feasibility judge
# --------------------------------------------------------------------------- #


class InstitutionalConstraint(abc.ABC):
    """代理策略 §5.2.4: clips the goal's desired target to the executable
    feasible boundary.  Records ``constraint_binding`` / ``constraint_reason``.
    """

    @abc.abstractmethod
    def apply(
        self,
        goal_desired: int | None,
        goal_action: str,
        goal_degenerate_reason: ConstraintReason | None,
        account: ConstraintAccountView,
        active_orders: list[ActiveOrder],
        policy: ConstraintPolicy,
    ) -> ExecutableDecision: ...


def _candidate_reserved_after(
    account: ConstraintAccountView,
    active_orders: list[ActiveOrder],
    candidate_position_units: int,
    policy: ConstraintPolicy,
    candidate_delta: int = 0,
) -> int:
    """§3.3 reserved_after for a candidate executable position.

    Delegates the margin part to :func:`ledger.reserved.compute_reserved_after`
    with the candidate position as the post-decision position (R018-C008: the
    constraint layer previously hand-rolled the same formula, risking
    divergence).  The candidate's *new-open* delta joins the activity set so
    its fee is reserved too (代理策略 §11.1: fee_part covers active orders AND
    the candidate's new exposure -- the old code only counted active_orders).
    """
    from market_game_sim.ledger.reserved import compute_reserved_after

    reserved = compute_reserved_after(
        position_units=candidate_position_units,
        active_orders=active_orders,
        risk_mark_ticks=policy.risk_mark_ticks,
        initial_bp=policy.initial_bp,
        fee_bps=policy.fee_bps,
        mult=policy.mult,
    )
    if policy.fee_bps > 0 and candidate_delta > 0:
        # The new-open leg's own fee (sized at the risk mark, the conservative
        # worst-case fill price for an unknown future fill).
        reserved += div_ceil(
            candidate_delta * policy.risk_mark_ticks * policy.mult * policy.fee_bps,
            10_000,
        )
    return reserved


def _risk_equity_for(account: ConstraintAccountView, policy: ConstraintPolicy) -> int:
    """``wallet + unrealized_pnl(risk_mark)`` (账户合同 §2.2).

    Reuses :func:`ledger.account.risk_equity` via a throwaway Account view so
    the dual-notch口径 stays identical to the rest of the pipeline.
    """
    from market_game_sim.ledger.account import Account

    acct = Account(
        agent_id="constraint",
        wallet_units=account.wallet_units,
        position_units=account.position_units,
        entry_notional_units=account.entry_notional_units,
    )
    return risk_equity(acct, policy.risk_mark_ticks, policy.mult)


def _judge_feasible_new_open(
    position: int,
    desired: int,
    account: ConstraintAccountView,
    active_orders: list[ActiveOrder],
    policy: ConstraintPolicy,
) -> int:
    """Max new-open quantity in ``[0, new_open_target]`` whose candidate
    position passes ``reserved_after <= risk_equity`` (代理策略 §5.2.4 / §3.3).

    Integer binary search: ``reserved_after`` is monotonic non-decreasing in
    the candidate position magnitude (more size -> more margin), so the max
    feasible new-open is found by bisection over ``[0, new_open_target]``.
    """
    target = new_open_target(position, desired)
    if target <= 0:
        return 0
    re = _risk_equity_for(account, policy)
    if re <= 0:
        return 0

    def feasible(q: int) -> bool:
        if _is_pure_reduction(position, desired):
            return True
        if position * desired < 0:
            # Flip: candidate post-flip position is sign(desired)*q (the close
            # back to 0 is not margin-checked -- only the new-open leg).
            cand = -q if desired < 0 else q
        else:
            # Add: candidate = position + sign(desired)*q (same sign as desired).
            cand = position + (q if desired >= 0 else -q)
        reserved = _candidate_reserved_after(
            account,
            active_orders,
            cand,
            policy,
            candidate_delta=q,
        )
        return reserved <= re

    if feasible(target):
        return target
    lo, hi = 0, target
    # Invariant: feasible(lo) is True (q=0 is always feasible -- no new open),
    # feasible(hi) is False.  Binary search for the largest feasible q.
    if not feasible(0):
        return 0
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if feasible(mid):
            lo = mid
        else:
            hi = mid
    return lo


@dataclass(frozen=True)
class MarginConstraint(InstitutionalConstraint):
    """The §3.3 initial-margin feasibility constraint.

    Pure reductions skip the check (the exemption); flips check only the
    new-open leg; adds check the incremental size.  The clip never flips
    direction.  Degenerate reasons carried from the goal layer (代理策略
    §5.2.3) are propagated into the evidence.
    """

    def apply(
        self,
        goal_desired: int | None,
        goal_action: str,
        goal_degenerate_reason: ConstraintReason | None,
        account: ConstraintAccountView,
        active_orders: list[ActiveOrder],
        policy: ConstraintPolicy,
    ) -> ExecutableDecision:
        # Degenerate: the goal layer already resolved the case; propagate its
        # reason into the executable evidence (executable = desired or 0).
        if goal_action == "skip_decision" or goal_desired is None:
            reason = goal_degenerate_reason or ConstraintReason.MARK_UNDEFINED
            return ExecutableDecision(0, True, reason)
        if goal_degenerate_reason is not None:
            # reduce_only (NON_POSITIVE_EQUITY) or emit_decision (EWMA_WARMUP):
            # desired is already 0; the degenerate condition binds.
            return ExecutableDecision(0, True, goal_degenerate_reason)

        desired = goal_desired
        position = account.position_units

        # Pure reduction: never margin-clipped (§5.2.4 exemption).
        if _is_pure_reduction(position, desired):
            return ExecutableDecision(desired, False, None)

        feasible = _judge_feasible_new_open(position, desired, account, active_orders, policy)
        executable = clip_goal_to_feasible(position, desired, feasible)
        binding = executable != desired
        reason = ConstraintReason.MARGIN_LIMIT if binding else None
        return ExecutableDecision(executable, binding, reason)


# --------------------------------------------------------------------------- #
# QuoteRiskPolicy: market-maker quote risk policy (代理策略 §8)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class QuoteRiskPolicy:
    """The MM quote risk policy (代理策略 §8 last two bullets).

    This is the institutional constraint layer for the market maker: it MAY
    read ``maint_bp`` (the goal layer's :class:`MarketMakerGoal` does not).
    Applies two filters to the raw bilateral quotes:

    * ``inventory >= max_inventory`` stops the BUY (would add long); ``inventory
      <= -max_inventory`` stops the SELL.  (§8: 库存达 max_inventory 时停止
      该方向的报价.)
    * ``margin_ratio_bp < maint_bp`` stops both-side quoting; only the
      position-reducing side quotes (§8: 保证金率低于维持线时停止双边报价，
      只挂减仓方向.)

    ``margin_ratio_bp`` is a permitted input (代理策略 §8: it is not an
    ``L`` / ``M`` / ``leverage_tier`` treatment field); ``maint_bp`` is not.
    """

    max_inventory: int
    maint_bp: int

    def apply(
        self,
        bid,  # MarketMakerQuote | None
        ask,  # MarketMakerQuote | None
        inventory: int,
        margin_ratio_bp: int | None,
    ) -> tuple:
        """Return the (executable_bid, executable_ask, binding, reason)."""
        margin_warning = margin_ratio_bp is not None and margin_ratio_bp < self.maint_bp
        out_bid = bid
        out_ask = ask
        binding = False
        reason: ConstraintReason | None = None

        if margin_warning:
            binding = True
            reason = ConstraintReason.MARGIN_LIMIT
            # Long inventory -> only SELL (reduces the long); short -> only BUY.
            if inventory > 0:
                out_bid = None
            elif inventory < 0:
                out_ask = None
            else:
                # Flat but under maintenance: neither side adds risk; quote both
                # so the MM can still provide liquidity (margin_ratio on a flat
                # book is undefined -- treat as not-warning for the flat case).
                binding = False
                reason = None

        # max_inventory stopping (§8).  Applied after the margin filter so a
        # stopped side stays stopped.
        if out_bid is not None and inventory >= self.max_inventory:
            out_bid = None
            binding = True
            if reason is None:
                reason = ConstraintReason.MARGIN_LIMIT
        if out_ask is not None and inventory <= -self.max_inventory:
            out_ask = None
            binding = True
            if reason is None:
                reason = ConstraintReason.MARGIN_LIMIT

        return out_bid, out_ask, binding, reason


__all__ = [
    "ConstraintReason",
    "TriggerProvenance",
    "ExecutableDecision",
    "ConstraintAccountView",
    "ConstraintPolicy",
    "InstitutionalConstraint",
    "MarginConstraint",
    "QuoteRiskPolicy",
    "clip_goal_to_feasible",
    "new_open_target",
]
