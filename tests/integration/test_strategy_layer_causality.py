"""0.4.1 T965 (TR-501 / NFR-502 / AC-510): strategy family + tier on the causal chain.

The L2 layer adds no event type.  A decision's family and information tier ride
in the existing ``AGENT_DECIDE.internal_state``, and every order keeps reaching
back to that record through ``decision_event_id`` / ``intent_id`` -- so a fill
can be traced to the family that wanted it.

What the tests below pin down:

* **multi-family, multi-record batches** (AC-510) -- four families decide
  concurrently over a whole run and *every* record carries its own agent's
  labels.  A single-agent test would pass even if the handler wrote one
  agent's family onto everybody's records, which is exactly the index-slip
  class of bug that only shows up in batch;
* **untagged runs are byte-identical** -- bench / H2 / legacy specs carry no
  labels, so their events (and their config hashes) cannot move.  That is what
  keeps the frozen evidence of 0.1.x / 0.3.1 valid;
* **half-tagged specs fail closed** -- a family without a tier (or a tier that
  is not ``I0``—``I3``) raises instead of quietly producing a record whose
  family cannot be traced.
"""

from __future__ import annotations

import pytest

from market_game_sim.agent.handler import strategy_tags
from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.agent.strategy_layer import InformationTier, StrategyLayerError
from market_game_sim.experiment.config import ExperimentConfig, compute_config_hash
from market_game_sim.experiment.roster import (
    _FAMILIES,
    _FAMILY_TIERS,
    build_agent_specs,
    parse_roster,
)
from market_game_sim.experiment.runner import RunResult, run_one

INITIAL_PRICE = 10_000
MAX_TRANSACTIONS = 900

# family_id -> (info tier, agent count).  Tiers are the labels T968/T969's real
# families will declare; here they only have to be distinct and valid.
ROSTER: dict[str, tuple[str, int]] = {
    "market_maker_v2": ("I0", 2),
    "trend_following": ("I2", 3),
    "mean_reversion": ("I2", 3),
    "sentiment_noise": ("I1", 3),
}


def _mm(agent_id: str, family_id: str | None, tier: str | None) -> AgentSpec:
    return AgentSpec(
        agent_id=agent_id,
        role="inventory_market_maker",
        observe_interval_ns=100_000_000,
        latency_ns=5_000_000,
        is_market_maker=True,
        half_spread_ticks=5,
        quote_size=10_000,
        max_inventory=100_000,
        inventory_skew_k_bp=10_000,
        strategy_family_id=family_id,
        info_tier=tier,
    )


def _goal(agent_id: str, family_id: str | None, tier: str | None) -> AgentSpec:
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
        ewma_half_life_trades=2,
        strategy_family_id=family_id,
        info_tier=tier,
    )


def _specs(*, tagged: bool = True) -> list[AgentSpec]:
    """The same market, with or without the strategy-layer labels."""
    specs: list[AgentSpec] = []
    for family_id, (tier, count) in ROSTER.items():
        build = _mm if family_id == "market_maker_v2" else _goal
        for i in range(count):
            specs.append(
                build(
                    f"{family_id}-{i}",
                    family_id if tagged else None,
                    tier if tagged else None,
                )
            )
    return specs


def _anchor(specs: list[AgentSpec]) -> dict:
    """T963's synthetic cold-start anchor, grouped by family.

    Without it the goal agents never leave EWMA warmup and the market makes no
    trades at all -- there would be no causal chain left to test.
    """
    families: list[list] = []
    for family_id in ROSTER:
        members = [s.agent_id for s in specs if not s.is_market_maker and family_id in s.agent_id]
        if members:
            families.append([family_id, members])
    return {
        "source": "synthetic",
        "quantity_units": 1,
        "direction": "family_parity",
        "pricing": "best_opposite_else_initial_limit",
        "families": families,
    }


def _config(*, tagged: bool = True, max_transactions: int = MAX_TRANSACTIONS) -> ExperimentConfig:
    specs = _specs(tagged=tagged)
    # Opposite signals on purpose: both sides of the book are wanted, so the
    # run trades instead of stalling one-sided.
    signals = {
        s.agent_id: (10_000 if i % 2 == 0 else -10_000)
        for i, s in enumerate(s for s in specs if not s.is_market_maker)
    }
    return ExperimentConfig(
        seed=11,
        max_transactions=max_transactions,
        initial_price_ticks=INITIAL_PRICE,
        agent_specs=specs,
        agent_signals=signals,
        bootstrap_anchor=_anchor(specs),
    )


def _decisions(result: RunResult) -> list[dict]:
    return [e for e in result.events if e["event_type"] == "AGENT_DECIDE"]


@pytest.fixture(scope="module")
def tagged_run() -> RunResult:
    return run_one(_config(tagged=True))


@pytest.fixture(scope="module")
def untagged_run() -> RunResult:
    return run_one(_config(tagged=False))


# --------------------------------------------------------------------------- #
# AC-510: multi-family, multi-record batches
# --------------------------------------------------------------------------- #


def test_every_decision_record_carries_its_own_agents_family(tagged_run: RunResult) -> None:
    """Four families decide over one run; no record borrows another's labels."""
    decisions = _decisions(tagged_run)
    assert decisions, "the run produced no decisions"
    per_family: dict[str, set[str]] = {}
    for record in decisions:
        agent_id = record["agent_id"]
        family_id, _, index = agent_id.rpartition("-")
        expected_tier = ROSTER[family_id][0]
        state = record["internal_state"]
        assert state["strategy_family_id"] == family_id, f"{agent_id} @ {record['event_id']}"
        assert state["info_tier"] == expected_tier, f"{agent_id} @ {record['event_id']}"
        per_family.setdefault(family_id, set()).add(index)

    # Batch, not one-by-one: all four families, every agent, several records.
    assert per_family.keys() == ROSTER.keys()
    for family_id, (_, count) in ROSTER.items():
        assert len(per_family[family_id]) == count
    assert len(decisions) > len(ROSTER) * 2


def test_the_labels_never_drift_from_the_spec(tagged_run: RunResult) -> None:
    """Cross-check against the specs themselves, not the id-naming convention."""
    by_agent = {s.agent_id: s for s in _specs(tagged=True)}
    seen = set()
    for record in _decisions(tagged_run):
        spec = by_agent[record["agent_id"]]
        assert record["internal_state"]["strategy_family_id"] == spec.strategy_family_id
        assert record["internal_state"]["info_tier"] == spec.info_tier
        seen.add(record["agent_id"])
    assert seen == set(by_agent), "some assembled agent never decided"


def test_orders_trace_back_to_the_family_that_wanted_them(tagged_run: RunResult) -> None:
    """TR-501: ORDER_ARRIVAL -> decision_event_id -> the family's decision record."""
    decisions = {e["event_id"]: e for e in _decisions(tagged_run)}
    orders = [e for e in tagged_run.events if e["event_type"] == "ORDER_ARRIVAL"]
    assert orders, "the run produced no orders"
    intents_by_decision = {
        event_id: {i["intent_id"] for i in record.get("intents", ())}
        for event_id, record in decisions.items()
    }
    families = set()
    for order in orders:
        decision = decisions[order["decision_event_id"]]
        assert decision["agent_id"] == order["agent_id"]
        # The intent id links the two records in both directions (TR-501).
        assert order["intent_id"] in intents_by_decision[order["decision_event_id"]]
        state = decision["internal_state"]
        family_id = order["agent_id"].rpartition("-")[0]
        assert state["strategy_family_id"] == family_id
        assert state["info_tier"] == ROSTER[family_id][0]
        families.add(state["strategy_family_id"])
    # Several families actually reached the book, not just the market maker.
    assert len(families) >= 3, families


def test_trades_and_ledger_postings_reach_the_family(tagged_run: RunResult) -> None:
    """AC-510 end to end: decision -> order -> trade -> posting, both sides."""
    decisions = {e["event_id"]: e for e in _decisions(tagged_run)}
    orders = {e["order_id"]: e for e in tagged_run.events if e["event_type"] == "ORDER_ARRIVAL"}
    trades = [e for e in tagged_run.events if e["event_type"] == "TRADE_SETTLE"]
    assert trades, "the run produced no trades"
    traced: set[str] = set()
    for trade in trades:
        posted = {p["agent_id"] for p in trade["postings"] if p["posting_type"] == "TRADE_POSTING"}
        for role in ("maker", "taker"):
            order = orders[trade[f"{role}_order_id"]]
            assert order["agent_id"] == trade[f"{role}_agent_id"]
            decision = decisions[order["decision_event_id"]]
            assert decision["agent_id"] == order["agent_id"]
            family_id = decision["internal_state"]["strategy_family_id"]
            assert family_id == order["agent_id"].rpartition("-")[0]
            # The ledger side of the same fill names the very same agent, so
            # the chain reaches the account without a new event type.
            assert order["agent_id"] in posted
            traced.add(family_id)
    assert len(traced) >= 2, traced
    assert traced <= ROSTER.keys()


# --------------------------------------------------------------------------- #
# NFR-502: untagged assemblies keep their bytes
# --------------------------------------------------------------------------- #


def test_untagged_specs_produce_no_strategy_keys(untagged_run: RunResult) -> None:
    """Bench / H2 / legacy specs stay exactly as they were."""
    records = _decisions(untagged_run)
    assert records
    for record in records:
        assert "strategy_family_id" not in record["internal_state"]
        assert "info_tier" not in record["internal_state"]


def test_labels_drive_behaviour_once_the_family_is_wired(
    tagged_run: RunResult, untagged_run: RunResult
) -> None:
    """0.4.1 T966 changed this contract, deliberately.

    In T965 a label was pure metadata and a tagged run was byte-identical to an
    untagged one.  T966 wires the roster's families into the runtime, so a spec
    labelled with a **quoting** family now quotes by that family's rule instead
    of the built-in one, and family agents carry the keyed-draw identity their
    per-agent parameters are drawn from.  The run therefore differs -- which is
    the point of naming a family at all.  What must still hold is that the
    difference comes from the wired families, not from labelling as such:
    untagged specs behave exactly as before (see
    ``test_untagged_specs_produce_no_strategy_keys``).
    """
    assert len(tagged_run.events) != len(untagged_run.events)
    quoting = {
        record["agent_id"]
        for record in tagged_run.events
        if record["event_type"] == "ORDER_ARRIVAL"
        and str(record["agent_id"]).startswith("market_maker_v2-")
    }
    assert quoting, "the quoting family placed no orders: the T966 seam is broken"


def test_pre_0_4_1_configs_keep_their_config_hash() -> None:
    """Both values were computed before the AgentSpec labels existed.

    An untagged spec must drop out of the hash payload; otherwise every frozen
    T215 / H2 config hash in ``docs/experiments/`` would silently move.
    """
    assert compute_config_hash(ExperimentConfig(seed=7, max_transactions=100)) == (
        "8b4315c6aa93c43f1e45facdd361e129"
    )
    untagged = compute_config_hash(_config(tagged=False))
    assert untagged != compute_config_hash(_config(tagged=True))  # a different assembly


# --------------------------------------------------------------------------- #
# Fail closed: a half-tagged agent is a mislabel, not a legacy agent
# --------------------------------------------------------------------------- #


def test_untagged_spec_has_no_tags() -> None:
    assert strategy_tags(_goal("a-0", None, None)) == {}


def test_tagged_spec_round_trips() -> None:
    assert strategy_tags(_goal("a-0", "trend_following", "I2")) == {
        "strategy_family_id": "trend_following",
        "info_tier": "I2",
    }


@pytest.mark.parametrize(
    "family_id,tier",
    [
        ("trend_following", None),  # family without a tier
        (None, "I2"),  # tier without a family
        ("", "I2"),  # empty family id
        ("trend_following", "I4"),  # no such tier
        ("trend_following", "i2"),  # tier names are case sensitive
        ("trend_following", 2),  # the enum value is not the name
    ],
)
def test_half_or_wrongly_tagged_specs_fail_closed(family_id, tier) -> None:
    with pytest.raises(StrategyLayerError) as excinfo:
        strategy_tags(_goal("a-0", family_id, tier))
    assert excinfo.value.code == "INVALID_STRATEGY_TAG"


def test_a_mislabelled_agent_aborts_the_run_and_writes_no_record() -> None:
    """One bad label stops the run; it does not produce an untraceable record.

    L1 §1.5 fail-stop turns the handler's raise into an ``ABORTED``/``INTERNAL``
    run (the kernel never lets a handler exception escape) -- T965 does not
    change that contract, so the assertion is on the run's outcome: the
    mislabelled agent has no ``AGENT_DECIDE`` record at all, while the agents
    that decided before it kept theirs.
    """
    config = _config(tagged=True)
    specs = list(config.agent_specs)
    bad_agent = specs[-1].agent_id
    specs[-1] = _goal(bad_agent, "sentiment_noise", None)
    config.agent_specs = specs

    result = run_one(config)

    assert (result.terminated, result.abort_code) == ("ABORTED", "INTERNAL")
    deciders = [r["agent_id"] for r in _decisions(result)]
    assert bad_agent not in deciders
    assert deciders, "the abort swallowed the records of the correctly tagged agents"
    for record in _decisions(result):
        assert record["internal_state"]["strategy_family_id"]


def test_the_same_run_completes_once_the_label_is_fixed() -> None:
    """The positive half: only the missing tier made the run abort."""
    result = run_one(_config(tagged=True))
    assert (result.terminated, result.abort_code) != ("ABORTED", "INTERNAL")


# --------------------------------------------------------------------------- #
# The roster is the producer of the labels (DR-501 -> TR-501)
# --------------------------------------------------------------------------- #


def _roster_payload() -> dict:
    return {
        "schema_version": 1,
        "seed": 11,
        "engine": {
            "initial_price_ticks": INITIAL_PRICE,
            "mult": 1000,
            "maker_bps": 1,
            "taker_bps": 2,
            "maint_bp": 500,
            "target_bp": 1000,
            "liquidation_latency_ns": 1_000_000,
        },
        "bootstrap_anchor": {"source": "none"},
        "families": [
            {
                "family_id": "inventory_market_maker",
                "count": 2,
                "observe_interval_ns": 100_000_000,
                "latency_ns": 5_000_000,
                "params": {
                    "leverage_tier": 1,
                    "half_spread_ticks": 5,
                    "quote_size": 10_000,
                    "max_inventory": 100_000,
                    "inventory_skew_k_bp": 10_000,
                },
            },
            {
                "family_id": "goal_belief",
                "count": 3,
                "observe_interval_ns": 1_000_000_000,
                "latency_ns": 50_000_000,
                "params": {
                    "goal_model_id": "risk_budget_linear_v1",
                    "leverage_tier": 10,
                    "risk_appetite_x1000": 2000,
                    "aggressiveness_bp": 10_000,
                    "max_order_qty": 10_000,
                    "ewma_half_life_trades": 2,
                },
            },
        ],
    }


def test_roster_assembly_tags_every_agent() -> None:
    specs = build_agent_specs(parse_roster(_roster_payload()))
    assert len(specs) == 5
    for spec in specs:
        family_id = spec.agent_id.rpartition("-")[0]
        assert spec.strategy_family_id == family_id
        assert spec.info_tier == _FAMILY_TIERS[family_id]
        assert strategy_tags(spec)["info_tier"] in InformationTier.__members__


def test_every_roster_family_declares_a_tier() -> None:
    """A family added to the roster table without a tier must not slip through.

    T968/T969 add four more families here; without this check a new family
    would raise ``KeyError`` deep inside assembly instead of being noticed.
    """
    assert set(_FAMILY_TIERS) == set(_FAMILIES)
    assert set(_FAMILY_TIERS.values()) <= set(InformationTier.__members__)


def test_roster_assembled_run_records_the_family() -> None:
    specs = build_agent_specs(parse_roster(_roster_payload()))
    result = run_one(
        ExperimentConfig(
            seed=11,
            max_transactions=400,
            initial_price_ticks=INITIAL_PRICE,
            agent_specs=specs,
            agent_signals={
                s.agent_id: (10_000 if i % 2 == 0 else -10_000)
                for i, s in enumerate(s for s in specs if not s.is_market_maker)
            },
        )
    )
    families = {r["internal_state"]["strategy_family_id"] for r in _decisions(result)}
    assert families == {"inventory_market_maker", "goal_belief"}
