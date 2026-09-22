"""0.4.1 T960 / T963 (FR-501 / NFR-502 / AC-501): cold-start deadlock and its anchor.

Mechanism (ADR-011 背景): a goal-driven agent stays in EWMA warmup until it has
seen ``2 * ewma_half_life_trades`` public trades (``goal.py::_warmup``); while in
warmup its target position is 0, so it never orders.  The warmup samples come
from the public trade tape, and in a market whose only other participant is a
market maker nobody crosses the spread -- so the tape stays empty and warmup
never ends.

T960 pinned both halves of that claim as the red baseline, and they stay here
as AC-501's negative side:

- with warmup on and no anchor, a market with live two-sided quotes still
  produces zero trades and every goal-agent decision is ``EWMA_WARMUP``;
- the *same* market with warmup off trades -- proving the deadlock is caused by
  warmup, not by the market set-up.  (Turning warmup off is the side-effect
  bypass FR-501 forbids as a fix; here it is only the control arm.)

T963 adds the positive side: the ``synthetic`` anchor (spec Q-501) makes the
same zero-trade market produce first goal-agent orders, with direction set by
family parity, pricing at the best opposite quote or the initial price, exit
by the unchanged warmup test, and unknown sources failing closed.
"""

from __future__ import annotations

from collections import Counter

import pytest

from market_game_sim.agent.anchor import (
    AnchorError,
    anchor_order_intent,
    family_parity_directions,
    registered_anchor_sources,
    resolve_anchor,
)
from market_game_sim.agent.constraint import ConstraintReason
from market_game_sim.agent.goal import (
    AgentInternalStateV1,
    AgentPreferences,
    BookTop,
    InformationSetV1,
    OwnAccountView,
    RiskBudgetLinearV1,
    RiskBudgetThresholdV1,
)
from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.experiment.config import ExperimentConfig, compute_config_hash
from market_game_sim.experiment.runner import RunResult, run_one

GOAL_AGENTS = ("agent-0", "agent-1", "agent-2")
WARMUP_HALF_LIFE_TRADES = 5
MAX_TRANSACTIONS = 600
INITIAL_PRICE = 10_000
MM_HALF_SPREAD = 5


def _market_maker() -> AgentSpec:
    return AgentSpec(
        agent_id="mm-0",
        role="inventory_market_maker",
        observe_interval_ns=100_000_000,
        latency_ns=5_000_000,
        is_market_maker=True,
        half_spread_ticks=MM_HALF_SPREAD,
        quote_size=10_000,
        max_inventory=100_000,
        inventory_skew_k_bp=10_000,
    )


def _goal_agent(agent_id: str, half_life_trades: int) -> AgentSpec:
    return AgentSpec(
        agent_id=agent_id,
        role="retail",
        observe_interval_ns=1_000_000_000,
        latency_ns=50_000_000,
        leverage_tier=10,
        initial_bp=1000,
        aggressiveness_bp=10_000,
        max_order_qty=10_000,
        goal_model_id="risk_budget_linear_v1",
        risk_appetite_x1000=2000,
        ewma_half_life_trades=half_life_trades,
    )


def _synthetic(families: list[list], quantity_units: int = 1) -> dict:
    return {
        "source": "synthetic",
        "quantity_units": quantity_units,
        "direction": "family_parity",
        "pricing": "best_opposite_else_initial_limit",
        "families": families,
    }


def _config(
    seed: int,
    half_life_trades: int,
    *,
    agents: tuple[str, ...] = GOAL_AGENTS,
    anchor: dict | None = None,
    with_mm: bool = True,
    max_transactions: int = MAX_TRANSACTIONS,
) -> ExperimentConfig:
    # Opposite signals on purpose: buyers and sellers both exist, so a
    # zero-trade outcome cannot be blamed on everyone wanting the same side.
    signals = {aid: (10_000 if i % 2 == 0 else -10_000) for i, aid in enumerate(agents)}
    return ExperimentConfig(
        seed=seed,
        max_transactions=max_transactions,
        initial_price_ticks=INITIAL_PRICE,
        agent_specs=([_market_maker()] if with_mm else [])
        + [_goal_agent(aid, half_life_trades) for aid in agents],
        agent_signals=signals,
        bootstrap_anchor=anchor,
    )


def _run(seed: int, half_life_trades: int) -> RunResult:
    return run_one(_config(seed, half_life_trades))


def _goal_orders(result: RunResult, agents: tuple[str, ...] = GOAL_AGENTS) -> Counter[str]:
    return Counter(
        e["agent_id"]
        for e in result.events
        if e["event_type"] == "ORDER_ARRIVAL"
        and e["agent_id"] in agents
        and e.get("action") == "SUBMIT"
    )


def _first_submit(result: RunResult, agent_id: str) -> dict:
    return next(
        e
        for e in result.events
        if e["event_type"] == "ORDER_ARRIVAL"
        and e["agent_id"] == agent_id
        and e.get("action") == "SUBMIT"
    )


def _goal_decisions(result: RunResult, agents: tuple[str, ...] = GOAL_AGENTS) -> list[dict]:
    return [
        e for e in result.events if e["event_type"] == "AGENT_DECIDE" and e["agent_id"] in agents
    ]


def _trades(result: RunResult) -> int:
    return sum(1 for e in result.events if e["event_type"] == "TRADE_SETTLE")


# --------------------------------------------------------------------------- #
# Negative side (T960 baseline): no anchor => deadlock
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("seed", [7, 11])
def test_warmup_deadlocks_a_quoted_market_with_zero_trades(seed: int) -> None:
    result = _run(seed, WARMUP_HALF_LIFE_TRADES)
    assert result.terminated == "COMPLETED"

    # The market maker really is quoting both sides -- the book is not empty.
    publishes = [e for e in result.events if e["event_type"] == "MARKET_DATA_PUBLISH"]
    assert any(e["best_bid"] is not None and e["best_ask"] is not None for e in publishes)

    assert _trades(result) == 0
    assert _goal_orders(result) == Counter()

    decisions = _goal_decisions(result)
    assert {d["agent_id"] for d in decisions} == set(GOAL_AGENTS)
    for d in decisions:
        assert d["internal_state"]["constraint_reason"] == "EWMA_WARMUP", d["event_id"]
        assert d["internal_state"]["desired_position_units"] == 0, d["event_id"]
        assert d["intents"] == [], d["event_id"]
        assert "bootstrap_anchor" not in d["internal_state"], d["event_id"]
    assert result.bootstrap_anchor == {"source": "none"}


@pytest.mark.parametrize("seed", [7, 11])
def test_same_market_trades_once_warmup_is_off(seed: int) -> None:
    result = _run(seed, half_life_trades=0)
    assert result.terminated == "COMPLETED"
    assert _trades(result) > 0
    assert set(_goal_orders(result)) == set(GOAL_AGENTS)
    assert all(
        d["internal_state"]["constraint_reason"] != "EWMA_WARMUP" for d in _goal_decisions(result)
    )


def test_explicit_none_anchor_is_the_unanchored_run() -> None:
    """``source: none`` is the explicit "no anchor": same run, but the declaration is hashed."""
    plain = _config(7, WARMUP_HALF_LIFE_TRADES)
    none = _config(7, WARMUP_HALF_LIFE_TRADES, anchor={"source": "none"})
    assert run_one(none).events == run_one(plain).events
    assert compute_config_hash(none) != compute_config_hash(plain)  # the declaration is recorded


def test_pre_anchor_configs_keep_their_config_hash() -> None:
    """Adding ``bootstrap_anchor`` must not move any pre-0.4.1 config hash.

    Both values were computed with the pre-T963 ``config.py`` (no anchor field).
    """
    assert compute_config_hash(ExperimentConfig(seed=7, max_transactions=100)) == (
        "8b4315c6aa93c43f1e45facdd361e129"
    )
    assert compute_config_hash(_config(7, WARMUP_HALF_LIFE_TRADES)) == (
        "8897441e3f3bcda80c5b0679eaba58de"
    )


# --------------------------------------------------------------------------- #
# Positive side (T963): the synthetic anchor breaks the deadlock
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("seed", [7, 11])
def test_zero_trade_market_produces_a_first_goal_agent_order(seed: int) -> None:
    anchor = _synthetic([["retail", list(GOAL_AGENTS)]])
    result = run_one(_config(seed, WARMUP_HALF_LIFE_TRADES, anchor=anchor))
    assert result.terminated == "COMPLETED"
    assert set(_goal_orders(result)) == set(GOAL_AGENTS)
    assert _trades(result) > 0

    # Anchored decisions are tagged, pass the ordinary margin constraint, and
    # never carry the warmup reason (that is the unanchored zero target).
    anchored = [d for d in _goal_decisions(result) if "bootstrap_anchor" in d["internal_state"]]
    assert {d["agent_id"] for d in anchored} == set(GOAL_AGENTS)
    for d in anchored:
        assert d["internal_state"]["bootstrap_anchor"] == "synthetic"
        assert d["internal_state"]["constraint_reason"] != "EWMA_WARMUP"
        assert abs(d["internal_state"]["desired_position_units"]) == 1

    # Parameters and source travel with the run (NFR-502).
    assert result.bootstrap_anchor == {
        "source": "synthetic",
        "quantity_units": 1,
        "direction": "family_parity",
        "pricing": "best_opposite_else_initial_limit",
        "families": [["retail", list(GOAL_AGENTS)]],
    }


def test_anchor_prices_at_the_observed_best_opposite_else_initial() -> None:
    """Every anchored order takes the opposite quote its observation saw.

    At t=0 the market maker has not quoted yet, so the first anchors rest at the
    initial price (and cross each other); a later re-post takes the MM's ask.
    """
    anchor = _synthetic([["retail", list(GOAL_AGENTS)]])
    result = run_one(_config(7, WARMUP_HALF_LIFE_TRADES, anchor=anchor))
    assert _trades(result) < 2 * WARMUP_HALF_LIFE_TRADES  # still anchored throughout
    seen: dict[str, dict] = {}
    priced: list[tuple[str, int, bool]] = []
    for e in result.events:
        if e.get("agent_id") not in GOAL_AGENTS:
            continue
        if e["event_type"] == "AGENT_OBSERVE":
            seen[e["agent_id"]] = e["information_set"]
        elif e["event_type"] == "ORDER_ARRIVAL" and e["action"] == "SUBMIT":
            iset = seen[e["agent_id"]]
            opposite = iset["best_ask"] if e["side"] == "BUY" else iset["best_bid"]
            assert e["order_type"] == "LIMIT"
            assert e["price_ticks"] == (opposite if opposite is not None else INITIAL_PRICE)
            priced.append((e["side"], e["price_ticks"], opposite is None))
    # Both branches of the pricing rule were exercised in this run.
    assert {empty for *_, empty in priced} == {True, False}


def test_empty_book_anchors_meet_at_the_initial_price() -> None:
    """No market maker: both sides rest at the initial price and cross each other."""
    agents = tuple(f"agent-{i}" for i in range(4))
    anchor = _synthetic([["retail", list(agents)]])
    result = run_one(
        _config(7, WARMUP_HALF_LIFE_TRADES, agents=agents, anchor=anchor, with_mm=False)
    )
    first = [_first_submit(result, a) for a in agents]
    assert [o["side"] for o in first] == ["BUY", "SELL", "BUY", "SELL"]
    assert {o["price_ticks"] for o in first} == {INITIAL_PRICE}
    assert _trades(result) > 0
    assert {a: result.accounts[a].position_units for a in agents} == {
        "agent-0": 1,
        "agent-1": -1,
        "agent-2": 1,
        "agent-3": -1,
    }


def test_many_families_cold_start_together_with_parity_and_rotating_remainder() -> None:
    """Several families anchored in one run: in-family parity, odd leftovers rotate."""
    families = [
        ["alpha", ["a-0", "a-1", "a-2"]],
        ["beta", ["b-0", "b-1"]],
        ["gamma", ["c-0"]],
        ["delta", ["d-0", "d-1", "d-2"]],
    ]
    agents = tuple(a for _, ids in families for a in ids)
    expected = {
        "a-0": 1,
        "a-1": -1,
        "a-2": 1,  # 1st odd family's leftover: buy
        "b-0": 1,
        "b-1": -1,
        "c-0": -1,  # 2nd odd family's leftover: sell
        "d-0": 1,
        "d-1": -1,
        "d-2": 1,  # 3rd: buy again
    }
    assert family_parity_directions([(f, ids) for f, ids in families]) == expected

    result = run_one(
        _config(
            7,
            WARMUP_HALF_LIFE_TRADES,
            agents=agents,
            anchor=_synthetic(families),
            max_transactions=2000,
        )
    )
    assert set(_goal_orders(result, agents)) == set(agents)
    for agent_id, direction in expected.items():
        assert _first_submit(result, agent_id)["side"] == ("BUY" if direction > 0 else "SELL")
    assert {a: result.accounts[a].position_units for a in agents} == expected


def test_anchor_exits_by_the_unchanged_warmup_test() -> None:
    """Once the tape holds ``2 * half_life`` trades the normal model takes over."""
    agents = tuple(f"agent-{i}" for i in range(12))
    half_life = 3
    anchor = _synthetic([["retail", list(agents)]])
    result = run_one(_config(7, half_life, agents=agents, anchor=anchor, max_transactions=4000))
    decisions = _goal_decisions(result, agents)
    anchored = [d for d in decisions if "bootstrap_anchor" in d["internal_state"]]
    after = [d for d in decisions if "bootstrap_anchor" not in d["internal_state"]]
    assert anchored and after
    assert _trades(result) >= 2 * half_life
    # After exit the ordinary GoalModel runs: its signal-scaled target, not ±1.
    assert all(d["internal_state"]["constraint_reason"] != "EWMA_WARMUP" for d in after)
    assert any(abs(d["internal_state"]["desired_position_units"]) > 1 for d in after)
    # An agent never returns to the anchor once it has left warmup.
    for agent_id in agents:
        mine = [d for d in decisions if d["agent_id"] == agent_id]
        flags = ["bootstrap_anchor" in d["internal_state"] for d in mine]
        assert flags == sorted(flags, reverse=True), agent_id


def test_anchored_runs_reproduce() -> None:
    anchor = _synthetic([["retail", list(GOAL_AGENTS)]])
    config = _config(11, WARMUP_HALF_LIFE_TRADES, anchor=anchor)
    assert run_one(config).events == run_one(config).events


# --------------------------------------------------------------------------- #
# Fail closed
# --------------------------------------------------------------------------- #


def test_only_synthetic_is_registered() -> None:
    assert registered_anchor_sources() == {"none", "synthetic"}


@pytest.mark.parametrize(
    ("anchor", "code"),
    [
        ({"source": "historical_snapshot"}, "UNKNOWN_ANCHOR_SOURCE"),
        ({"source": "random"}, "UNKNOWN_ANCHOR_SOURCE"),
        ({"source": "none", "quantity_units": 1}, "UNKNOWN_FIELD"),
        ({**_synthetic([["retail", ["agent-0"]]]), "extra": 1}, "UNKNOWN_FIELD"),
        ({k: v for k, v in _synthetic([]).items() if k != "families"}, "MISSING_FIELD"),
        (_synthetic([["retail", ["agent-0"]]], quantity_units=0), "INVALID_VALUE"),
        ({**_synthetic([["retail", ["agent-0"]]]), "direction": "random"}, "INVALID_VALUE"),
        ({**_synthetic([["retail", ["agent-0"]]]), "pricing": "mid"}, "INVALID_VALUE"),
        (_synthetic([]), "INVALID_VALUE"),
        (_synthetic([["a", ["agent-0"]], ["b", ["agent-0"]]]), "DUPLICATE_AGENT"),
    ],
    ids=[
        "adr014-not-registered",
        "unknown",
        "none-extra",
        "extra",
        "missing",
        "qty",
        "direction",
        "pricing",
        "no-families",
        "dup-agent",
    ],
)
def test_invalid_anchor_fails_closed(anchor: dict, code: str) -> None:
    with pytest.raises(AnchorError) as exc:
        resolve_anchor(anchor)
    assert exc.value.code == code
    # ...and the run never starts.
    with pytest.raises(AnchorError):
        run_one(_config(7, WARMUP_HALF_LIFE_TRADES, anchor=anchor))


@pytest.mark.parametrize(
    ("families", "half_life", "code"),
    [
        ([["retail", ["ghost"]]], WARMUP_HALF_LIFE_TRADES, "ANCHOR_AGENT_UNKNOWN"),
        ([["mm", ["mm-0"]]], WARMUP_HALF_LIFE_TRADES, "ANCHOR_AGENT_NOT_GOAL"),
        ([["retail", list(GOAL_AGENTS)]], 0, "ANCHOR_WITHOUT_WARMUP"),
    ],
    ids=["unknown-agent", "market-maker", "no-warmup"],
)
def test_anchor_on_the_wrong_agents_fails_at_assembly(families, half_life, code) -> None:
    with pytest.raises(AnchorError) as exc:
        run_one(_config(7, half_life, anchor=_synthetic(families)))
    assert exc.value.code == code


# --------------------------------------------------------------------------- #
# Units: goal.py's shared anchored branch and the anchor order pricing
# --------------------------------------------------------------------------- #


def _info() -> InformationSetV1:
    return InformationSetV1(
        schema_version=1,
        cursor_from_event_id="e1_0",
        cursor_to_event_id="e1_0",
        public_trades=(),
        completed_bars=(),
        book_top=BookTop(best_bid=9995, best_ask=10005, valuation_mark_half_ticks=20_000),
        own_account=OwnAccountView(wallet_units=10**12, position_units=0, entry_notional_units=0),
    )


def _state(samples: int) -> AgentInternalStateV1:
    return AgentInternalStateV1(
        schema_version=1,
        last_seen_market_event_id="e1_0",
        ewma_value_units=None,
        ewma_sample_count=samples,
        model_private_state={"signal_bp": 10_000},
    )


@pytest.mark.parametrize(
    "model",
    [
        RiskBudgetLinearV1(half_life_in_trades=5),
        RiskBudgetThresholdV1(theta_in=3000, theta_out=1200, k_x1000=600, half_life_in_trades=5),
    ],
    ids=["linear", "threshold"],
)
def test_goal_models_share_the_anchored_warmup_branch(model) -> None:
    from dataclasses import replace

    prefs = AgentPreferences(risk_appetite_x1000=2000)
    plain = model.decide(_info(), _state(0), prefs)
    assert (plain.desired_position_units, plain.degenerate_reason) == (
        0,
        ConstraintReason.EWMA_WARMUP,
    )

    anchored_model = replace(model, bootstrap_anchor_units=-1)
    anchored = anchored_model.decide(_info(), _state(0), prefs)
    assert (anchored.desired_position_units, anchored.action) == (-1, "emit_decision")
    assert anchored.degenerate_reason is None

    # Out of warmup (samples >= 2 * half_life) the anchor is inert.
    assert anchored_model.decide(_info(), _state(10), prefs) == model.decide(
        _info(), _state(10), prefs
    )


def test_anchor_order_intent_pricing_rule() -> None:
    kwargs = dict(leverage_tier=10, initial_price_ticks=INITIAL_PRICE, max_order_qty=10, min_qty=1)
    buy = anchor_order_intent("i", 1, 0, best_bid=9990, best_ask=10010, **kwargs)
    sell = anchor_order_intent("i", -1, 0, best_bid=9990, best_ask=10010, **kwargs)
    assert (buy.side, buy.price_ticks, buy.quantity_units) == ("BUY", 10010, 1)
    assert (sell.side, sell.price_ticks, sell.quantity_units) == ("SELL", 9990, 1)
    # Opposite side empty -> limit at the initial price.
    rest = anchor_order_intent("i", 1, 0, best_bid=9990, best_ask=None, **kwargs)
    assert (rest.side, rest.price_ticks, rest.order_type) == ("BUY", INITIAL_PRICE, "LIMIT")
    # Already at target -> no order.
    assert anchor_order_intent("i", 1, 1, best_bid=None, best_ask=None, **kwargs) is None
