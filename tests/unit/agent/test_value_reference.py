"""0.4.3 T1105 (AC-701 / AC-706): the constant value reference and who can see it.

AC-701 -- ``v_t`` is derived from ``engine.initial_price_ticks`` at assembly and
never moves: every decision the value family takes in a real run sees the same
``v_t``, so its per-step return is identically zero.  Statistical tests on a
constant series are degenerate (zero variance), so the assertion is the
zero-return property itself, checked on both sides -- a series that moves once
must be caught.

AC-706 -- ``v_t`` travels only through the value family's per-agent private
parameters: not through any tiered information set, not into any other
family's private parameters, not into the human terminal payload, and the
strategy protocol version is unchanged.
"""

from __future__ import annotations

import copy
import dataclasses
import json
from fractions import Fraction

import pytest

from market_game_sim.agent.goal import (
    AgentInternalStateV1,
    AgentPreferences,
    BookTop,
    InformationSetV1,
    OwnAccountView,
)
from market_game_sim.agent.strategy_layer import protocol
from market_game_sim.agent.strategy_layer.families import value_investor as VI
from market_game_sim.agent.strategy_layer.families.value_investor import (
    SENSITIVITY_KEY,
    VALUE_REFERENCE_KEY,
    ValueInvestor,
)
from market_game_sim.agent.strategy_layer.protocol import (
    InformationTier,
    StrategyLayerError,
    TieredInformationSet,
    crop_information_set,
)
from market_game_sim.experiment.h2.live_market import DEFAULT_LIVE_ROSTER, LiveMarket
from market_game_sim.experiment.roster import build_agent_specs, parse_roster

VALUE_ENTRY = {
    "family_id": "value_investor",
    "count": 4,
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


def anchored_roster(initial_price_ticks: int | None = None) -> dict:
    roster = copy.deepcopy(dict(DEFAULT_LIVE_ROSTER))
    roster["families"] = [*roster["families"], copy.deepcopy(VALUE_ENTRY)]
    if initial_price_ticks is not None:
        roster["engine"] = {**roster["engine"], "initial_price_ticks": initial_price_ticks}
    return roster


def returns(series: list[int]) -> list[Fraction]:
    """Exact per-step returns -- no rounding, so a one-tick move on any level is non-zero."""
    return [Fraction(b - a, a) for a, b in zip(series, series[1:], strict=False)]


def leaking_agents(specs) -> list[str]:
    """Agents outside the value family whose private parameters carry ``v_t``."""
    return [
        s.agent_id
        for s in specs
        if s.strategy_family_id != "value_investor"
        and VALUE_REFERENCE_KEY in (s.strategy_private or {})
    ]


# --------------------------------------------------------------------------- #
# AC-701: derived at assembly, constant in a real run
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("initial", [10_000, 7_321])
def test_v_t_is_derived_from_the_engine_initial_price(initial):
    roster = parse_roster(anchored_roster(initial))
    value_specs = [s for s in build_agent_specs(roster) if s.strategy_family_id == "value_investor"]
    assert len(value_specs) == VALUE_ENTRY["count"]
    for spec in value_specs:
        assert spec.strategy_private[VALUE_REFERENCE_KEY] == initial
        assert spec.strategy_private[SENSITIVITY_KEY] == VALUE_ENTRY["params"]["sensitivity_x1000"]


def test_v_t_does_not_change_the_roster_id_of_rosters_without_the_family():
    """Derived, not stored: rosters without a value family are untouched (design §3)."""
    assert "value_reference_ticks" not in parse_roster(DEFAULT_LIVE_ROSTER).to_json()


@pytest.fixture(scope="module")
def observed_references():
    """Every ``v_t`` the value family actually saw over 40 logical seconds of a live run."""
    seen: list[int] = []
    original = VI.value_reference

    def spy(state):
        value = original(state)
        seen.append(value)
        return value

    VI.value_reference = spy
    try:
        market = LiveMarket(roster=parse_roster(anchored_roster()))
        for _ in range(40):
            market.advance()
    finally:
        VI.value_reference = original
    return seen, market


def test_v_t_never_moves_during_a_live_run(observed_references):
    seen, _ = observed_references
    assert len(seen) >= VALUE_ENTRY["count"] * 10, "the value family must actually decide"
    assert set(seen) == {DEFAULT_LIVE_ROSTER["engine"]["initial_price_ticks"]}
    assert all(r == 0 for r in returns(seen))


@pytest.mark.parametrize("level", [10_000, 10**9])
def test_a_reference_that_moves_once_is_caught(level):
    """The other side of AC-701: a single one-tick move is a non-zero return at any level."""
    series = [level] * 50 + [level + 1] * 10
    assert sum(1 for r in returns(series) if r != 0) == 1


# --------------------------------------------------------------------------- #
# AC-706: only the value family sees it
# --------------------------------------------------------------------------- #


def test_only_value_agents_carry_v_t():
    specs = build_agent_specs(parse_roster(anchored_roster()))
    assert leaking_agents(specs) == []
    assert any(s.strategy_family_id == "value_investor" for s in specs)


def test_a_leak_into_another_family_would_be_caught():
    specs = build_agent_specs(parse_roster(anchored_roster()))
    victim = next(s for s in specs if s.strategy_family_id == "trend_following")
    victim.strategy_private = {**(victim.strategy_private or {}), VALUE_REFERENCE_KEY: 10_000}
    assert leaking_agents(specs) == [victim.agent_id]


def test_no_tiered_information_set_field_can_carry_it():
    names = {f.name for f in dataclasses.fields(TieredInformationSet)}
    assert not any("value" in name or "reference" in name for name in names)


def test_v_t_reaches_the_family_only_through_private_state():
    """A full I3 information set without the private key still fails closed."""
    raw = InformationSetV1(
        schema_version=1,
        cursor_from_event_id="evt-0",
        cursor_to_event_id="evt-1",
        public_trades=(),
        completed_bars=(),
        book_top=BookTop(best_bid=9_999, best_ask=10_001, valuation_mark_half_ticks=20_000),
        own_account=OwnAccountView(wallet_units=10**14, position_units=0, entry_notional_units=0),
    )
    info = crop_information_set(raw, InformationTier.I3, observed_at=0)
    bare = AgentInternalStateV1(
        schema_version=1,
        last_seen_market_event_id="evt-0",
        ewma_value_units=None,
        ewma_sample_count=0,
        model_private_state={SENSITIVITY_KEY: 500},
    )
    with pytest.raises(StrategyLayerError) as exc:
        ValueInvestor().decide(info, bare, AgentPreferences(risk_appetite_x1000=2000))
    assert exc.value.code == "MISSING_VALUE_REFERENCE"


def test_protocol_version_is_unchanged():
    assert protocol.PROTOCOL_VERSION == 1
    assert ValueInvestor().protocol_version == 1


def test_human_terminal_payload_does_not_carry_v_t(observed_references):
    _, market = observed_references
    payload = json.dumps(market.view(), default=str)
    assert VALUE_REFERENCE_KEY not in payload
    assert SENSITIVITY_KEY not in payload
    assert "value_investor" not in payload


def test_a_payload_that_carried_v_t_would_be_caught(observed_references):
    _, market = observed_references
    view = market.view()
    view["account"][VALUE_REFERENCE_KEY] = 10_000
    assert VALUE_REFERENCE_KEY in json.dumps(view, default=str)
