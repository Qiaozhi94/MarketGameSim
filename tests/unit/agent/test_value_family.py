"""0.4.3 T1106 (FR-702 / AC-702): the value-investor family's response function.

The family leans against the deviation of the mark from ``v_t``:

* **direction** -- rich is sold, cheap is bought, at ``v_t`` the target is flat;
* **monotone** -- the exposure (per-mille of the position ceiling) never shrinks
  as ``|deviation|`` grows, on either side, nor as ``sensitivity_x1000`` grows.
  In *units* the cheap side is monotone too; the rich side peaks where the
  exposure saturates, because the ceiling itself shrinks as price rises;
* **capped** -- it never exceeds the family's position ceiling.

Every property is asserted from both sides (the state it acts on and the state
it must not), and the roster side rejects a strength knob outside the range
FR-702 declares.  Several value agents on one market are covered at the end:
they share ``v_t`` but are distinct agents.
"""

from __future__ import annotations

import copy

import pytest

from market_game_sim.agent.goal import (
    AgentInternalStateV1,
    AgentPreferences,
    BookTop,
    InformationSetV1,
    OwnAccountView,
)
from market_game_sim.agent.strategy_layer.families._common import (
    DEFAULT_MULT,
    REASON_NO_BUDGET,
    REASON_NO_MARK,
    max_position_units,
)
from market_game_sim.agent.strategy_layer.families.value_investor import (
    SENSITIVITY_KEY,
    SENSITIVITY_MAX,
    VALUE_REFERENCE_KEY,
    ValueInvestor,
    target_fraction_x1000,
)
from market_game_sim.agent.strategy_layer.protocol import (
    ACTION_NO_ACTION,
    ACTION_TARGET_POSITION,
    InformationTier,
    StrategyLayerError,
    crop_information_set,
)
from market_game_sim.experiment.h2.live_market import DEFAULT_LIVE_ROSTER
from market_game_sim.experiment.roster import RosterError, build_agent_specs, parse_roster

V = 10_000
WALLET = 10**14
PREFS = AgentPreferences(risk_appetite_x1000=2000)
FAMILY = ValueInvestor()


def info_at(mark: int | None, *, wallet_units: int = WALLET):
    book = (
        BookTop(best_bid=None, best_ask=None, valuation_mark_half_ticks=None)
        if mark is None
        else BookTop(best_bid=mark - 1, best_ask=mark + 1, valuation_mark_half_ticks=2 * mark)
    )
    raw = InformationSetV1(
        schema_version=1,
        cursor_from_event_id="evt-0",
        cursor_to_event_id="evt-1",
        public_trades=(),
        completed_bars=(),
        book_top=book,
        own_account=OwnAccountView(
            wallet_units=wallet_units, position_units=0, entry_notional_units=0
        ),
    )
    return crop_information_set(raw, InformationTier.I0, observed_at=0)


def state(sensitivity_x1000: int = 500, reference: int | None = V) -> AgentInternalStateV1:
    bag: dict[str, object] = {SENSITIVITY_KEY: sensitivity_x1000}
    if reference is not None:
        bag[VALUE_REFERENCE_KEY] = reference
    return AgentInternalStateV1(
        schema_version=1,
        last_seen_market_event_id="evt-0",
        ewma_value_units=None,
        ewma_sample_count=0,
        model_private_state=bag,
    )


def target(mark: int, sensitivity_x1000: int = 500) -> int:
    decision = FAMILY.decide(info_at(mark), state(sensitivity_x1000), PREFS)
    assert decision.action == ACTION_TARGET_POSITION
    return decision.target_position_units


def ceiling(mark: int) -> int:
    return max_position_units(info_at(mark), PREFS, mark, k_x1000=1000)


# --------------------------------------------------------------------------- #
# Direction
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("gap", [1, 50, 400, 5_000])
def test_rich_is_sold_and_cheap_is_bought(gap):
    assert target(V + gap) < 0
    assert target(V - gap) > 0


def test_flat_at_the_reference():
    assert target(V) == 0


def test_it_unwinds_rather_than_skipping_when_the_gap_closes():
    """Back at ``v_t`` the decision is a flat *target*, not ``no_action``."""
    decision = FAMILY.decide(info_at(V), state(), PREFS)
    assert decision.action == ACTION_TARGET_POSITION
    assert decision.target_position_units == 0


# --------------------------------------------------------------------------- #
# Monotone in deviation and in strength
# --------------------------------------------------------------------------- #


def exposure_x1000(gap: int, sensitivity_x1000: int = 500) -> int:
    """Per-mille of the ceiling the family asks for -- the quantity FR-702 makes monotone."""
    return target_fraction_x1000(gap * 10_000 // V, sensitivity_x1000)


def test_exposure_never_shrinks_as_the_deviation_grows():
    for sign in (1, -1):
        fractions = [exposure_x1000(sign * gap) for gap in range(0, 3_000, 25)]
        assert fractions == sorted(fractions), f"non-monotone on side {sign:+d}"
        assert fractions[-1] == 1000 and fractions[1] > 0


def test_units_follow_exposure_times_the_ceiling():
    for gap in range(-3_000, 3_000, 37):
        mark = V + gap
        expected = exposure_x1000(gap) * ceiling(mark) // 1000
        assert abs(target(mark)) == expected


def test_units_are_monotone_on_the_cheap_side():
    """Below ``v_t`` a lower price both raises the fraction and the ceiling (units are cheaper)."""
    sizes = [abs(target(V - gap)) for gap in range(0, 5_000, 25)]
    assert sizes == sorted(sizes)


def test_units_peak_at_saturation_on_the_rich_side():
    """Above ``v_t`` the ceiling shrinks as price rises (units cost more), so once the
    fraction saturates the unit count falls as 1/price.  Recorded behaviour, not a bug:
    the notional exposure stays at the cap.  Pinned so a change is a decision, not a drift.
    """
    saturation_gap = next(g for g in range(1, 5_000) if exposure_x1000(g) == 1000)
    before = [abs(target(V + g)) for g in range(0, saturation_gap + 1, 5)]
    assert before == sorted(before)
    after = [abs(target(V + g)) for g in range(saturation_gap, saturation_gap + 2_000, 100)]
    assert after == sorted(after, reverse=True)
    assert all(abs(target(V + g)) == ceiling(V + g) for g in range(saturation_gap, 4_000, 250))


def test_size_never_shrinks_as_sensitivity_grows():
    for mark in (V + 120, V - 120):
        sizes = [abs(target(mark, s)) for s in (1, 10, 100, 500, 1_000, 10_000, SENSITIVITY_MAX)]
        assert sizes == sorted(sizes)
        assert sizes[-1] > sizes[0]


def test_fraction_formula_matches_the_design():
    """design §2: per-mille of the ceiling per 1% of deviation, saturating at 1000."""
    assert target_fraction_x1000(100, 500) == 500
    assert target_fraction_x1000(-100, 500) == 500
    assert target_fraction_x1000(1, 1) == 0
    assert target_fraction_x1000(10_000, SENSITIVITY_MAX) == 1000


# --------------------------------------------------------------------------- #
# Capped at the family ceiling
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("mark", [V // 2, V * 2])
def test_large_deviations_saturate_at_the_ceiling(mark):
    assert abs(target(mark, SENSITIVITY_MAX)) == ceiling(mark)


def test_small_deviations_stay_below_the_ceiling():
    assert 0 < abs(target(V + 10)) < ceiling(V + 10)


# --------------------------------------------------------------------------- #
# Stays out / fails closed
# --------------------------------------------------------------------------- #


def test_no_mark_is_no_action():
    decision = FAMILY.decide(info_at(None), state(), PREFS)
    assert decision.action == ACTION_NO_ACTION
    assert decision.reason_code == REASON_NO_MARK


def test_no_budget_is_no_action():
    decision = FAMILY.decide(info_at(V + 500, wallet_units=0), state(), PREFS)
    assert decision.action == ACTION_NO_ACTION
    assert decision.reason_code == REASON_NO_BUDGET


@pytest.mark.parametrize("bad", [0, -1, SENSITIVITY_MAX + 1, "500", None])
def test_out_of_range_sensitivity_fails_closed(bad):
    bag = {VALUE_REFERENCE_KEY: V}
    if bad is not None:
        bag[SENSITIVITY_KEY] = bad
    broken = AgentInternalStateV1(
        schema_version=1,
        last_seen_market_event_id="evt-0",
        ewma_value_units=None,
        ewma_sample_count=0,
        model_private_state=bag,
    )
    with pytest.raises(StrategyLayerError) as exc:
        FAMILY.decide(info_at(V), broken, PREFS)
    assert exc.value.code == "MISSING_VALUE_REFERENCE"


@pytest.mark.parametrize("bad", [0, -5, "10000"])
def test_invalid_reference_fails_closed(bad):
    with pytest.raises(StrategyLayerError) as exc:
        FAMILY.decide(info_at(V), state(reference=bad), PREFS)
    assert exc.value.code == "MISSING_VALUE_REFERENCE"


def test_tier_is_i0():
    assert FAMILY.info_tier == InformationTier.I0


# --------------------------------------------------------------------------- #
# Roster side
# --------------------------------------------------------------------------- #

VALUE_ENTRY = {
    "family_id": "value_investor",
    "count": 3,
    "observe_interval_ns": 1_000_000_000,
    "latency_ns": 1_000_000,
    "params": {
        "leverage_tier": 5,
        "risk_appetite_x1000": 2000,
        "aggressiveness_bp": 8000,
        "max_order_qty": 10000,
        "ewma_half_life_trades": 5,
        "sensitivity_x1000": 500,
    },
}


def roster_with(params_patch: dict | None = None, drop: str | None = None, mult: int | None = None):
    roster = copy.deepcopy(dict(DEFAULT_LIVE_ROSTER))
    entry = copy.deepcopy(VALUE_ENTRY)
    entry["params"].update(params_patch or {})
    if drop:
        del entry["params"][drop]
    roster["families"] = [*roster["families"], entry]
    if mult is not None:
        roster["engine"] = {**roster["engine"], "mult": mult}
    return roster


@pytest.mark.parametrize("value", [1, 500, SENSITIVITY_MAX])
def test_roster_accepts_sensitivity_in_range(value):
    parse_roster(roster_with({"sensitivity_x1000": value}))


@pytest.mark.parametrize("value", [0, SENSITIVITY_MAX + 1])
def test_roster_rejects_sensitivity_out_of_range(value):
    with pytest.raises(RosterError) as exc:
        parse_roster(roster_with({"sensitivity_x1000": value}))
    assert exc.value.code == "INVALID_VALUE"


def test_roster_requires_the_strength_knob():
    with pytest.raises(RosterError):
        parse_roster(roster_with(drop="sensitivity_x1000"))


def test_value_family_is_bound_to_the_family_mult():
    """It sizes through ``max_position_units``, so T1100's MULT check covers it."""
    roster = roster_with(mult=DEFAULT_MULT * 2)
    roster["families"] = [f for f in roster["families"] if f["family_id"] == "value_investor"]
    with pytest.raises(RosterError) as exc:
        parse_roster(roster)
    assert exc.value.code == "MULT_MISMATCH"


def test_several_value_agents_share_v_t_and_stay_distinct():
    specs = [
        s
        for s in build_agent_specs(parse_roster(roster_with()))
        if s.strategy_family_id == "value_investor"
    ]
    assert [s.agent_id for s in specs] == [f"value_investor-{i}" for i in range(3)]
    assert {s.strategy_private[VALUE_REFERENCE_KEY] for s in specs} == {V}
    assert all(s.goal_model_id == "value_investor" for s in specs)
    assert all(s.info_tier == "I0" for s in specs)
