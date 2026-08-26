"""T204: constraint-layer golden vectors + binding/non-binding behavior.

Recomputes ``golden_vectors.constraint`` from ``goal_contract_v2.json`` against
:func:`clip_goal_to_feasible` (the canonical clipping frozen in
``spec_validation.py``), then exercises the full :class:`MarginConstraint.apply`
with real accounts to prove:

* a non-binding constraint does not change the order intent (changing a
  non-binding institutional param leaves ``executable == desired``);
* a binding constraint only clips scale (``executable`` has the same sign as
  ``desired`` or is 0, never the opposite sign);
* pure reduction is never margin-clipped (the §5.2.4 exemption);
* a flip clips only the new-open leg (two-stage), never the close portion.

Positive + negative cases for each behavior per ADR-003 acceptance gate 2.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from market_game_sim.agent.constraint import (
    ConstraintAccountView,
    ConstraintPolicy,
    ConstraintReason,
    MarginConstraint,
    clip_goal_to_feasible,
    new_open_target,
)

ROOT = pathlib.Path(__file__).resolve().parents[3]
CONTRACT = ROOT / "src" / "market_game_sim" / "schema" / "goal_contract_v2.json"


@pytest.fixture(scope="module")
def contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Golden vectors: clip_goal_to_feasible recomputes exactly
# --------------------------------------------------------------------------- #


def test_constraint_golden_vectors_recompute_exactly(contract):
    for vector in contract["golden_vectors"]["constraint"]:
        position = vector["position"]
        desired = vector["desired"]
        feasible = vector["feasible_new_open"]
        expected = vector["expected_executable"]
        got = clip_goal_to_feasible(position, desired, feasible)
        assert got == expected, (
            f"{vector['id']}: clip({position}, {desired}, {feasible}) -> {got}, expected {expected}"
        )


def test_pure_reduction_skips_margin_check(contract):
    """golden_vectors.constraint.pure_reduction_never_clipped: margin check
    skipped entirely, executable == desired regardless of feasible_new_open."""
    vector = contract["golden_vectors"]["constraint"][0]
    assert vector["margin_check_skipped"] is True
    # Even with feasible_new_open = 0 (no new open allowed), the reduction is
    # NOT clipped -- the exemption.
    assert clip_goal_to_feasible(100, 20, 0) == 20


def test_flip_limits_only_new_leg(contract):
    """flip: executable is the new-open leg only (sign(desired)*feasible), not
    the full desired, not 0, not the close portion."""
    assert clip_goal_to_feasible(100, -80, 30) == -30
    # Direction never flipped: result same sign as desired or 0.
    assert clip_goal_to_feasible(100, -80, 0) == 0  # no new open -> just close to flat


def test_add_beyond_limit_clips_same_sign(contract):
    """add: executable = position + feasible (same sign as desired, clipped)."""
    assert clip_goal_to_feasible(100, 200, 50) == 150


def test_new_open_target_matches_intent():
    """The new-open quantity that must pass the margin check: reduction is
    exempt (0), a flip's whole post-flip position is new, an add is the
    incremental |desired|-|position|, an open-from-zero is all new."""
    assert new_open_target(100, 20) == 0
    assert new_open_target(100, -80) == 80
    assert new_open_target(100, 200) == 100
    assert new_open_target(0, 100) == 100


# --------------------------------------------------------------------------- #
# MarginConstraint.apply: non-binding constraint does not change intent
# --------------------------------------------------------------------------- #


def _policy(leverage_tier: int, mark: int = 100, mult: int = 1000) -> ConstraintPolicy:
    from market_game_sim.ledger.account import initial_margin_bp_for_tier

    return ConstraintPolicy(
        leverage_tier=leverage_tier,
        initial_bp=initial_margin_bp_for_tier(leverage_tier),
        maint_bp=500,
        max_order_qty=10_000,
        fee_bps=0,
        mult=mult,
        risk_mark_ticks=mark,
    )


def test_non_binding_constraint_leaves_executable_equal_to_desired():
    """Plenty of equity -> margin does not bind; executable == desired.  Changing
    a non-binding institutional param (leverage_tier 1 -> 2) must NOT change the
    executable -- ADR-003 §1: "约束不绑定时，改变杠杆上限不得改变订单意图"."""
    desired = 100
    account = ConstraintAccountView(
        wallet_units=20_000_000, position_units=0, entry_notional_units=0, reserved_units=0
    )
    constraint = MarginConstraint()
    # tier 1 (initial_bp 10000): margin(100) = 10M <= 20M -> non-binding.
    exec1 = constraint.apply(desired, "emit_decision", None, account, [], _policy(leverage_tier=1))
    assert exec1.executable_position_units == desired
    assert exec1.constraint_binding is False
    assert exec1.constraint_reason is None
    # tier 2 (initial_bp 5000): margin(100) = 5M <= 20M -> also non-binding;
    # executable unchanged.
    exec2 = constraint.apply(desired, "emit_decision", None, account, [], _policy(leverage_tier=2))
    assert exec2.executable_position_units == desired
    assert exec2.executable_position_units == exec1.executable_position_units


def test_binding_constraint_clips_scale_same_sign():
    """Tight equity -> margin binds; executable clipped to feasible, same sign
    as desired (never the opposite), |executable| <= |desired|."""
    desired = 100
    # wallet 3M, position 0: tier 1 margin(100)=10M > 3M -> binds.  Max feasible
    # q where margin(q)=q*100*1000*10000/10000=q*1_000_000 <= 3M -> q=30.
    account = ConstraintAccountView(
        wallet_units=3_000_000, position_units=0, entry_notional_units=0, reserved_units=0
    )
    constraint = MarginConstraint()
    ex = constraint.apply(desired, "emit_decision", None, account, [], _policy(leverage_tier=1))
    assert ex.constraint_binding is True
    assert ex.constraint_reason == ConstraintReason.MARGIN_LIMIT
    assert ex.executable_position_units == 30
    # Same sign as desired (positive) or 0; never opposite.
    assert ex.executable_position_units >= 0
    assert abs(ex.executable_position_units) <= abs(desired)


def test_binding_constraint_never_flips_direction():
    """Negative control: a binding short-desired clip must stay <= 0, never go
    positive (the clip changes scale, NOT direction -- 代理策略 §5.2.4)."""
    desired = -100
    account = ConstraintAccountView(
        wallet_units=3_000_000, position_units=0, entry_notional_units=0, reserved_units=0
    )
    constraint = MarginConstraint()
    ex = constraint.apply(desired, "emit_decision", None, account, [], _policy(leverage_tier=1))
    assert ex.executable_position_units <= 0  # same sign as desired or 0
    assert abs(ex.executable_position_units) <= abs(desired)


def test_pure_reduction_exemption_in_apply():
    """|desired| < |position|, same sign -> margin check skipped, executable ==
    desired even when equity is too low to open anything new."""
    # position +100, desired +20 (pure reduction), wallet 0 -> risk_equity =
    # 0 + 100*100*1000 - 0 = 10M, but opening ANY new would bind; reduction
    # must still pass through unclipped.
    account = ConstraintAccountView(
        wallet_units=0, position_units=100, entry_notional_units=0, reserved_units=0
    )
    constraint = MarginConstraint()
    ex = constraint.apply(20, "emit_decision", None, account, [], _policy(leverage_tier=1))
    assert ex.executable_position_units == 20
    assert ex.constraint_binding is False
    assert ex.constraint_reason is None


def test_flip_two_stage_only_new_leg_checked():
    """Flip (position +100 -> desired -30): the close-back-to-zero portion is
    not margin-checked; only the new short leg participates.  With risk_equity
    = 2M, max feasible short = 20 (margin(20)=2M <= 2M, margin(21)=2.1M > 2M),
    so executable = -20 (not -30, not 0, not +anything)."""
    # wallet -8M, position +100, entry 0, mark 100, mult 1000:
    # risk_equity = -8M + 100*100*1000 = 2_000_000.
    account = ConstraintAccountView(
        wallet_units=-8_000_000,
        position_units=100,
        entry_notional_units=0,
        reserved_units=0,
    )
    constraint = MarginConstraint()
    ex = constraint.apply(-30, "emit_decision", None, account, [], _policy(leverage_tier=1))
    assert ex.executable_position_units == -20
    assert ex.constraint_binding is True
    assert ex.constraint_reason == ConstraintReason.MARGIN_LIMIT


def test_flip_non_binding_executes_full_desired():
    """Negative control for the flip: with enough equity, the full flip
    executes (executable == desired, non-binding)."""
    # wallet 0, position +100, mark 100, mult 1000: risk_equity = 10M.
    # margin(30 short) = 3M <= 10M -> feasible 30 -> executable -30.
    account = ConstraintAccountView(
        wallet_units=0, position_units=100, entry_notional_units=0, reserved_units=0
    )
    constraint = MarginConstraint()
    ex = constraint.apply(-30, "emit_decision", None, account, [], _policy(leverage_tier=1))
    assert ex.executable_position_units == -30
    assert ex.constraint_binding is False


def test_degenerate_reason_propagated_to_executable():
    """A degenerate goal (NON_POSITIVE_EQUITY) propagates its reason into the
    executable evidence; executable is 0 and binding."""
    account = ConstraintAccountView(
        wallet_units=-1, position_units=0, entry_notional_units=0, reserved_units=0
    )
    constraint = MarginConstraint()
    ex = constraint.apply(
        0,
        "reduce_only",
        ConstraintReason.NON_POSITIVE_EQUITY,
        account,
        [],
        _policy(leverage_tier=1),
    )
    assert ex.executable_position_units == 0
    assert ex.constraint_binding is True
    assert ex.constraint_reason == ConstraintReason.NON_POSITIVE_EQUITY


def test_skip_decision_executable_zero_with_reason():
    """MARK_UNDEFINED skip -> executable 0, binding, reason MARK_UNDEFINED."""
    account = ConstraintAccountView(
        wallet_units=1_000_000, position_units=0, entry_notional_units=0, reserved_units=0
    )
    constraint = MarginConstraint()
    ex = constraint.apply(
        None,
        "skip_decision",
        ConstraintReason.MARK_UNDEFINED,
        account,
        [],
        _policy(leverage_tier=1),
    )
    assert ex.executable_position_units == 0
    assert ex.constraint_binding is True
    assert ex.constraint_reason == ConstraintReason.MARK_UNDEFINED


# --------------------------------------------------------------------------- #
# R018-C004 regression: same-sign adds must clip symmetrically for long and
# short (the old `desired > position` test only caught long adds).
# --------------------------------------------------------------------------- #


def test_same_side_add_is_clipped_symmetrically_for_long_and_short():
    """position +100 desired +200 (long add) and position -100 desired -200
    (short add) must clip identically via clip_goal_to_feasible: executable =
    sign * (|position| + feasible), so a short add can no longer bypass the
    margin clip (the old `desired > position` test only caught long adds)."""
    for position, desired, feasible, expected in (
        (100, 200, 50, 150),  # long add: 100 + 50
        (-100, -200, 50, -150),  # short add: -(100 + 50) -- was unclipped -200
    ):
        got = clip_goal_to_feasible(position, desired, feasible)
        assert got == expected, (
            f"position={position} desired={desired} feasible={feasible}: "
            f"got {got}, expected {expected}"
        )
        # Direction preserved: same sign as desired.
        assert (got < 0) == (desired < 0)


# --------------------------------------------------------------------------- #
# R018-C008 regression: the constraint layer reserves the candidate's own
# new-open fee (delegates to ledger.reserved and counts candidate delta).
# --------------------------------------------------------------------------- #


def _policy_with_fee(fee_bps: int, mark: int = 100, mult: int = 1000) -> ConstraintPolicy:
    from market_game_sim.ledger.account import initial_margin_bp_for_tier

    return ConstraintPolicy(
        leverage_tier=1,
        initial_bp=initial_margin_bp_for_tier(1),
        maint_bp=500,
        max_order_qty=10_000,
        fee_bps=fee_bps,
        mult=mult,
        risk_mark_ticks=mark,
    )


def test_candidate_new_open_fee_is_reserved():
    """A non-zero fee rate must reduce the feasible new-open size below the
    zero-fee case: the candidate's own new-open notional fee is reserved
    (代理策略 §11.1), not just the resting orders' fees."""
    account = ConstraintAccountView(
        wallet_units=0, position_units=0, entry_notional_units=0, reserved_units=0
    )
    # risk_equity = 0 + 0 = 0... wallet 0, position 0 -> re 0 -> nothing feasible.
    # Use a funded account: wallet 20M -> re 20M.
    account = ConstraintAccountView(
        wallet_units=20_000_000, position_units=0, entry_notional_units=0, reserved_units=0
    )
    # margin(cand) = cand*100*1000 (initial_bp 10000); re=20M -> cand<=200 -> q<=200.
    ex_no_fee = MarginConstraint().apply(
        500, "emit_decision", None, account, [], _policy_with_fee(fee_bps=0)
    )
    # With fee 500bp (5%), the candidate's new-open fee reserves more:
    # reserved = margin(cand) + ceil(cand*100*1000*500/10000) -> smaller feasible.
    ex_fee = MarginConstraint().apply(
        500, "emit_decision", None, account, [], _policy_with_fee(fee_bps=500)
    )
    assert ex_no_fee.executable_position_units > 0
    assert ex_fee.executable_position_units < ex_no_fee.executable_position_units
    assert ex_fee.constraint_binding is True
