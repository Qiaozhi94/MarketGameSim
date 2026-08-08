"""T404, T405, T406: AGENT_DECIDE handler that turns intents into ORDER_ARRIVAL."""

from __future__ import annotations

from decimal import Decimal

from market_game_sim.agent.factors import belief_signal
from market_game_sim.agent.factors import book as book_factor
from market_game_sim.agent.factors import herding as herding_factor
from market_game_sim.agent.factors import momentum as momentum_factor
from market_game_sim.agent.factors import noise as noise_factor
from market_game_sim.agent.factors import reversion as reversion_factor
from market_game_sim.agent.observation import Bar, InformationSet
from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.agent.strategy import market_maker_intents, order_intent_from_signal
from market_game_sim.book.orderbook import Book
from market_game_sim.kernel.runner import EventKernel
from market_game_sim.ledger.account import Account, risk_equity
from market_game_sim.rng.distributions import dirichlet_draw, standard_normal

# 代理策略 §10.3.4 BENCH-001 golden-vector alpha for the 5 belief factors
# (momentum, reversion, herding, book, noise), in the same order as
# belief_signal's factor list in _compute_belief_signal.
_BELIEF_WEIGHT_ALPHA = [
    Decimal("1.0"),
    Decimal("1.0"),
    Decimal("0.8"),
    Decimal("0.8"),
    Decimal("1.5"),
]


def _build_information_set(
    agent_id: str,
    accounts: dict[str, Account],
    book: Book,
    initial_price_ticks: int,
    min_qty: int,
    mult: int,
) -> dict:
    acct = accounts.get(agent_id)
    if acct is None:
        return {
            "agent_id": agent_id,
            "best_bid": book.best_bid(),
            "best_ask": book.best_ask(),
            "bid_depth_k": book.bid_depth_k(),
            "ask_depth_k": book.ask_depth_k(),
            "last_ticks": book.last_ticks,
            "wallet_units": 0,
            "position_units": 0,
            "entry_notional_units": 0,
            "margin_ratio_bp": None,
            "valuation_mark_half_ticks": book.valuation_mark_half_ticks(),
            "is_first_trade": book.last_ticks is None,
            "initial_price_ticks": initial_price_ticks,
        }
    last = book.last_ticks or initial_price_ticks
    valuation_mark = book.valuation_mark_half_ticks()
    re = risk_equity(acct, last, mult)
    return {
        "agent_id": agent_id,
        "best_bid": book.best_bid(),
        "best_ask": book.best_ask(),
        "bid_depth_k": book.bid_depth_k(),
        "ask_depth_k": book.ask_depth_k(),
        "last_ticks": book.last_ticks,
        "wallet_units": acct.wallet_units,
        "position_units": acct.position_units,
        "entry_notional_units": acct.entry_notional_units,
        "margin_ratio_bp": (
            None
            if acct.position_units == 0
            else re * 10_000 // (abs(acct.position_units) * last * mult)
            if acct.position_units != 0
            else None
        ),
        "valuation_mark_half_ticks": valuation_mark,
        "is_first_trade": book.last_ticks is None,
        "initial_price_ticks": initial_price_ticks,
    }


def _belief_intent(
    spec: AgentSpec,
    iset: dict,
    decision_index: int,
    signal_bp: int,
    min_qty: int,
) -> dict | None:
    if iset["best_bid"] is None or iset["best_ask"] is None:
        return None
    valuation_mark_ticks = (iset["valuation_mark_half_ticks"] or 0) // 2
    if valuation_mark_ticks <= 0:
        valuation_mark_ticks = iset["initial_price_ticks"]
    if valuation_mark_ticks <= 0:
        return None
    intent = order_intent_from_signal(
        intent_id=f"{spec.agent_id}-dec{decision_index}",
        signal_bp=signal_bp,
        current_position=iset["position_units"],
        equity_units=iset["wallet_units"],
        valuation_mark_ticks=valuation_mark_ticks,
        leverage_tier=spec.leverage_tier,
        aggressiveness_bp=spec.aggressiveness_bp,
        best_bid=iset["best_bid"],
        best_ask=iset["best_ask"],
        max_order_qty=spec.max_order_qty,
        min_qty=min_qty,
    )
    return intent


def _market_maker_intents(
    spec: AgentSpec,
    iset: dict,
    decision_index: int,
    maint_bp: int = 500,
) -> list[dict]:
    if iset["initial_price_ticks"] <= 0:
        return []
    valuation_mark_ticks = (
        iset["initial_price_ticks"]
        if iset["is_first_trade"]
        else ((iset["valuation_mark_half_ticks"] or 0) // 2)
    )
    if valuation_mark_ticks <= 0:
        return []
    return market_maker_intents(
        agent_id=spec.agent_id,
        inventory=iset["position_units"],
        max_inventory=spec.max_inventory,
        half_spread_ticks=spec.half_spread_ticks,
        quote_size=spec.quote_size,
        inventory_skew_k_bp=spec.inventory_skew_k_bp,
        valuation_mark_ticks=valuation_mark_ticks,
        best_bid=iset["best_bid"],
        best_ask=iset["best_ask"],
        margin_ratio_bp=iset.get("margin_ratio_bp"),
        maint_bp=maint_bp,
    )


def _belief_weights(spec: AgentSpec, world: dict) -> list[Decimal]:
    """代理策略 §4.2/§10.1: draw once at position-opening (decision_index=0)
    and cache for the rest of the run -- weights are fixed per agent, not
    redrawn every decision."""
    cache = world.setdefault("agent_belief_weights", {})
    cached = cache.get(spec.agent_id)
    if cached is not None:
        return cached
    master_seed = world.get("experiment_seed", 42)
    weights, _ = dirichlet_draw(
        alpha=_BELIEF_WEIGHT_ALPHA,
        master_seed=master_seed,
        agent_id=spec.agent_id,
        mechanism="belief_weights",
        decision_index=0,
    )
    cache[spec.agent_id] = weights
    return weights


def _compute_belief_signal(
    spec: AgentSpec,
    iset: dict,
    world: dict,
    decision_index: int,
) -> int:
    static = world.get("agent_signals", {}).get(spec.agent_id)
    if static is not None:
        return static
    master_seed = world.get("experiment_seed", 42)
    z, _ = standard_normal(
        master_seed=master_seed,
        agent_id=spec.agent_id,
        mechanism="noise_factor",
        decision_index=decision_index,
        draw_index=0,
    )
    nf = noise_factor(z)
    info = InformationSet(
        agent_id=spec.agent_id,
        observed_at=0,
        best_bid=iset.get("best_bid"),
        best_ask=iset.get("best_ask"),
        bid_depth_k=iset.get("bid_depth_k", 0),
        ask_depth_k=iset.get("ask_depth_k", 0),
        last_ticks=iset.get("last_ticks"),
    )
    bf = book_factor(info)
    history = world.get("trade_history", {}).get(spec.agent_id, [])
    bars = _bars_from_history(history, bar_ns=60_000_000_000)
    mf = momentum_factor(bars, lookback=5)
    rf = reversion_factor(info.last_ticks, iset.get("initial_price_ticks", 10000))
    hf = herding_factor(bars)
    weights = _belief_weights(spec, world)
    return belief_signal(weights, [mf, rf, hf, bf, nf])


def _bars_from_history(trades: list[dict], bar_ns: int) -> list:

    if not trades:
        return []
    by_bar: dict[int, list[dict]] = {}
    for tr in trades:
        k = tr.get("timestamp", 0) // bar_ns
        by_bar.setdefault(k, []).append(tr)
    out = []
    for k in sorted(by_bar):
        ts = by_bar[k]
        prices = [t.get("price_ticks", 0) for t in ts]
        out.append(
            Bar(
                open=prices[0],
                high=max(prices),
                low=min(prices),
                close=prices[-1],
                volume=sum(t.get("quantity_units", 0) for t in ts),
                trade_count=len(ts),
            )
        )
    return out


def handle_agent_decide(
    event: dict,
    world: dict,
    kernel: EventKernel,
    agent_specs: dict[str, AgentSpec],
    min_qty: int = 1,
    mult: int = 1000,
) -> list[dict]:
    agent_id = event["agent_id"]
    spec = agent_specs.get(agent_id)
    if spec is None:
        return []
    decision_index = event.get("_decision_index", 0)
    book: Book = world["book"]
    accounts = world["accounts"]
    initial_price = world.get("initial_price_ticks", 10000)
    iset = _build_information_set(agent_id, accounts, book, initial_price, min_qty, mult)

    if spec.is_market_maker:
        intents = _market_maker_intents(
            spec, iset, decision_index, maint_bp=world.get("maint_bp", 500)
        )
        internal_state = {
            "inventory_units": iset["position_units"],
            "margin_ratio_bp": iset.get("margin_ratio_bp"),
            "valuation_mark_half_ticks": iset.get("valuation_mark_half_ticks"),
        }
    else:
        signal_bp = _compute_belief_signal(spec, iset, world, decision_index)
        intent = _belief_intent(spec, iset, decision_index, signal_bp, min_qty)
        intents = [intent] if intent else []
        internal_state = {"signal_bp": signal_bp}

    decide_event_id = f"e{kernel.current_transaction_seq}_0"
    for order_seq, intent in enumerate(intents):
        order_id = f"o-{agent_id}-{decide_event_id}-{order_seq}"
        order_arrival = {
            "event_type": "ORDER_ARRIVAL",
            "timestamp": event["timestamp"] + spec.latency_ns,
            "agent_id": agent_id,
            "order_id": order_id,
            "action": intent.action,
            "side": intent.side,
            "order_type": intent.order_type,
            "price_ticks": intent.price_ticks,
            "quantity_units": intent.quantity_units,
            "intent_id": intent.intent_id,
            "decision_event_id": decide_event_id,
            "submitted_at": event["timestamp"],
        }
        kernel.enqueue(order_arrival)

    event["intents"] = [
        {
            "intent_id": i.intent_id,
            "action": i.action,
            "side": i.side,
            "order_type": i.order_type,
            "price_ticks": i.price_ticks,
            "quantity_units": i.quantity_units,
        }
        for i in intents
    ]
    event["accepted"] = True
    event["reject_reason"] = None
    event["internal_state"] = internal_state
    return []


def handle_agent_observe(
    event: dict, world: dict, kernel: EventKernel, min_qty: int = 1, mult: int = 1000
) -> list[dict]:
    agent_id = event["agent_id"]
    observe_event_id = f"e{kernel.current_transaction_seq}_0"
    spec: AgentSpec | None = world.get("agent_specs", {}).get(agent_id)
    if spec is None:
        return []
    # §2.13: record what the agent actually saw at this observation, per
    # event-schema.md §4.4 ("information_set 是 KPI-006 追溯链的起点") --
    # previously always the literal {} passed in at enqueue time.
    event["information_set"] = _build_information_set(
        agent_id,
        world["accounts"],
        world["book"],
        world.get("initial_price_ticks", 10000),
        min_qty,
        mult,
    )
    decision_index = world.get("agent_decision_index", {}).get(agent_id, 0)
    world.setdefault("agent_decision_index", {})[agent_id] = decision_index + 1
    decide = {
        "event_type": "AGENT_DECIDE",
        "timestamp": event["timestamp"] + spec.latency_ns,
        "agent_id": agent_id,
        "observation_event_id": observe_event_id,
        "rule_id": "default",
        "intents": [],
        "internal_state": {},
        "_decision_index": decision_index,
    }
    kernel.enqueue(decide)
    event["accepted"] = True
    event["reject_reason"] = None
    return []
