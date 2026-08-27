"""T404, T405, T406: AGENT_DECIDE handler that turns intents into ORDER_ARRIVAL."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from market_game_sim.agent.constraint import (
    ConstraintAccountView,
    ConstraintPolicy,
    MarginConstraint,
)
from market_game_sim.agent.factors import book as book_factor
from market_game_sim.agent.factors import herding as herding_factor
from market_game_sim.agent.factors import momentum as momentum_factor
from market_game_sim.agent.factors import noise as noise_factor
from market_game_sim.agent.factors import reversion as reversion_factor
from market_game_sim.agent.families import (
    FACTOR_ORDER,
    apply_ablation_named,
    family_signal,
)
from market_game_sim.agent.goal import (
    AgentInternalStateV1,
    AgentPreferences,
    BookTop,
    CompletedBar,
    DecisionEvidenceV1,
    InformationSetV1,
    OwnAccountView,
    PublicTrade,
    TriggerProvenance,
    build_decision_evidence,
    get_goal_model,
)
from market_game_sim.agent.observation import Bar, InformationSet
from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.agent.strategy import (
    TargetFn,
    market_maker_intents,
    order_intent_from_signal,
    order_intent_from_target,
    target_position,
)
from market_game_sim.agent.tape import INITIAL_CURSOR_EVENT_ID, tape_interval, update_ewma
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
    target_fn: TargetFn = target_position,
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
        target_fn=target_fn,
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
        leverage_tier=spec.leverage_tier,
    )


def _legacy_evidence(
    path_id: str,
    decision_index: int,
    cursor_from_event_id: str = "e1_0",
    cursor_to_event_id: str = "e1_0",
) -> DecisionEvidenceV1:
    """Path-tagged minimal evidence for the v1 / market-maker paths.

    These paths run no goal model, but every AGENT_DECIDE must carry a
    DecisionEvidenceV1 (ADR-003 §4; event_fields.json note on
    decision_evidence forbids silent absence).  The target is a no-op
    (desired == executable == 0) and ``goal_model_id`` marks the source path
    (``v1_legacy`` / ``market_maker``).  The cursor boundaries are the
    decision's own observation boundaries (R018-C007: the full-chain verifier
    requires evidence cursors to equal the referenced observation's cursors,
    for legacy paths too -- hardcoding e1_0 would mismatch once the cursor
    advances past a trade).
    """
    return DecisionEvidenceV1(
        schema_version=1,
        goal_model_id=path_id,
        goal_model_version=0,
        desired_position_units=0,
        executable_position_units=0,
        constraint_binding=False,
        constraint_reason=None,
        trigger_provenance=TriggerProvenance.ENDOGENOUS_AGENT,
        observation_event_id="",
        cursor_from_event_id=cursor_from_event_id,
        cursor_to_event_id=cursor_to_event_id,
    )


def _belief_intent_v2(
    spec: AgentSpec,
    iset: dict,
    decision_index: int,
    signal_bp: int,
    min_qty: int,
    mult: int,
    maint_bp: int,
    maker_bps: int,
    taker_bps: int,
    cursor_from_event_id: str = "e1_0",
    cursor_to_event_id: str = "e1_0",
    ewma_value: int | None = None,
    ewma_count: int = 0,
    public_trades: tuple = (),
    completed_bars: tuple = (),
) -> tuple[dict | None, dict, DecisionEvidenceV1]:
    """v2 goal + constraint pipeline (代理策略 §5.2, ADR-003).

    GoalModel.decide -> desired_position_units -> InstitutionalConstraint.apply
    -> executable_position_units -> §6 order intent.  Returns the populated
    DecisionEvidenceV1 (T206: real cursor boundaries from the observe event).
    Only runs when ``spec.goal_model_id`` is set; otherwise the v1 linear
    path is used (BENCHMARK historical-compat, 代理策略 §5.1).
    """
    assert spec.goal_model_id is not None  # caller guards the v2 switch
    model = get_goal_model(spec.goal_model_id)
    if spec.ewma_half_life_trades > 0:
        # Per-agent EWMA half-life (代理策略 §2: 半衰期逐代理抽取): the goal
        # model is a shared frozen instance, so the per-agent half-life is
        # applied via dataclasses.replace (frozen dataclass copy).
        model = replace(model, half_life_in_trades=spec.ewma_half_life_trades)
    own = OwnAccountView(
        wallet_units=iset["wallet_units"],
        position_units=iset["position_units"],
        entry_notional_units=iset["entry_notional_units"],
    )
    book = BookTop(
        best_bid=iset["best_bid"],
        best_ask=iset["best_ask"],
        valuation_mark_half_ticks=iset.get("valuation_mark_half_ticks"),
    )
    info_v2 = InformationSetV1(
        schema_version=1,
        cursor_from_event_id=cursor_from_event_id,
        cursor_to_event_id=cursor_to_event_id,
        public_trades=public_trades,
        completed_bars=completed_bars,
        book_top=book,
        own_account=own,
    )
    state = AgentInternalStateV1(
        schema_version=1,
        last_seen_market_event_id=cursor_from_event_id,
        ewma_value_units=ewma_value,
        ewma_sample_count=ewma_count,
        model_private_state={"signal_bp": signal_bp},
    )
    prefs = AgentPreferences(risk_appetite_x1000=spec.risk_appetite_x1000)
    goal_decision = model.decide(info_v2, state, prefs)

    risk_mark = iset.get("last_ticks") or iset.get("initial_price_ticks", 0)
    account = ConstraintAccountView(
        wallet_units=iset["wallet_units"],
        position_units=iset["position_units"],
        entry_notional_units=iset["entry_notional_units"],
        reserved_units=0,
    )
    policy = ConstraintPolicy(
        leverage_tier=spec.leverage_tier,
        initial_bp=spec.initial_bp,
        maint_bp=maint_bp,
        max_order_qty=spec.max_order_qty,
        fee_bps=max(maker_bps, taker_bps, 0),
        mult=mult,
        risk_mark_ticks=risk_mark,
    )
    executable = MarginConstraint().apply(
        goal_decision.desired_position_units,
        goal_decision.action,
        goal_decision.degenerate_reason,
        account,
        [],
        policy,
    )
    evidence = build_decision_evidence(
        model,
        goal_decision,
        executable,
        TriggerProvenance.ENDOGENOUS_AGENT,
        observation_event_id="",
        cursor_from_event_id=cursor_from_event_id,
        cursor_to_event_id=cursor_to_event_id,
    )

    intent = None
    if goal_decision.action != "skip_decision" and goal_decision.desired_position_units is not None:
        intent = order_intent_from_target(
            intent_id=f"{spec.agent_id}-dec{decision_index}",
            target_position_units=executable.executable_position_units,
            current_position=iset["position_units"],
            leverage_tier=spec.leverage_tier,
            aggressiveness_bp=spec.aggressiveness_bp,
            best_bid=iset["best_bid"],
            best_ask=iset["best_ask"],
            max_order_qty=spec.max_order_qty,
            min_qty=min_qty,
        )
    internal_state = {
        "signal_bp": signal_bp,
        "goal_model_id": model.id,
        "desired_position_units": evidence.desired_position_units,
        "executable_position_units": evidence.executable_position_units,
        "constraint_binding": evidence.constraint_binding,
        "constraint_reason": (
            str(evidence.constraint_reason) if evidence.constraint_reason is not None else None
        ),
    }
    return intent, internal_state, evidence


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

    # 0.1.3 E1/E3 wiring: the model family (which factors and how they combine)
    # and the ablated factor (leave-one-out switch) come from the world, so a
    # robustness run can vary them without touching this pipeline.  Same
    # semantic-key random draws either way (KR-004).
    family_id = world.get("model_family", "belief_family")
    disabled = world.get("disabled_factor")
    factor_values = [mf, rf, hf, bf, nf]
    if disabled is not None:
        # v013 (high) fix: carry the retained factor NAMES through ablation so
        # the family selects by name -- selecting by original index on the
        # shortened list would consume the wrong factor.
        factor_values, weights, factor_names = apply_ablation_named(
            factor_values, weights, disabled
        )
    else:
        factor_names = FACTOR_ORDER
    return family_signal(family_id, factor_values, weights, factor_names)


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


def _completed_bars_with_zero_fill(
    trades: list[dict], bar_ns: int, up_to_ts: int
) -> list[CompletedBar]:
    """Build the completed-bar sequence up to (but excluding) the current
    in-progress bar, padding any empty bar with the previous close + volume 0
    (代理策略 §3.1: 零成交 K 线继承上一根 close 且 volume=0).

    R018-C003 (Round 3): the v2 InformationSetV1.completed_bars must carry
    the full closed sequence including zero-fill bars -- a sparse
    trades-only aggregation would silently drop empty bars and mis-size
    momentum/herding lookbacks.
    """
    if not trades:
        return []
    by_bar: dict[int, list[dict]] = {}
    for tr in trades:
        ts_val = tr.get("timestamp", 0) if isinstance(tr, dict) else tr.timestamp
        k = ts_val // bar_ns
        by_bar.setdefault(k, []).append(tr)
    first_bar = min(by_bar)
    last_completed = up_to_ts // bar_ns - 1 if up_to_ts // bar_ns > first_bar else first_bar
    out: list[CompletedBar] = []
    prev_close: int | None = None
    for k in range(first_bar, last_completed + 1):
        ts = by_bar.get(k)
        if ts:
            prices = [t.get("price_ticks", 0) if isinstance(t, dict) else t.price_ticks for t in ts]
            volumes = [
                t.get("quantity_units", 0) if isinstance(t, dict) else t.quantity_units for t in ts
            ]
            bar = CompletedBar(
                open=prices[0],
                high=max(prices),
                low=min(prices),
                close=prices[-1],
                volume=sum(volumes),
                trade_count=len(ts),
            )
            prev_close = bar.close
        else:
            bar = CompletedBar(
                open=prev_close or 0,
                high=prev_close or 0,
                low=prev_close or 0,
                close=prev_close or 0,
                volume=0,
                trade_count=0,
            )
        out.append(bar)
    return out


def _cancel_stale_orders(
    spec: AgentSpec,
    world: dict,
    kernel: EventKernel,
    decide_event_id: str,
    decision_index: int,
    arrival_ts: int,
    submitted_at: int,
) -> list[dict]:
    """代理策略 §6.2 全撤重报: cancel every currently-resting order this
    agent owns, before this decision's new orders are enqueued.  Reads
    ``world["active_orders_by_agent"]`` (maintained by book/matching.py on
    insert/fill/cancel) rather than re-deriving it, so it stays consistent
    with whatever matching.py currently considers "resting".

    Must run *before* enqueueing the new-order intents below: cancels and
    submits are both class-0 ORDER_ARRIVAL at the same ``arrival_ts``, and
    the kernel breaks same-timestamp/class ties by enqueue order (FIFO) --
    enqueueing cancels first also means the freed-up reserved margin is
    already released by the time the new order's initial-margin check runs
    (each ORDER_ARRIVAL is processed as its own kernel transaction).

    Returns AGENT_DECIDE.intents[]-shaped summaries for the audit trail.
    """
    active = world.get("active_orders_by_agent", {}).get(spec.agent_id, {})
    summaries: list[dict] = []
    for i, order_id in enumerate(list(active.keys())):
        cancel_event = {
            "event_type": "ORDER_ARRIVAL",
            "timestamp": arrival_ts,
            "agent_id": spec.agent_id,
            "order_id": order_id,
            "action": "CANCEL",
            "target_order_id": order_id,
            "side": None,
            "order_type": None,
            "price_ticks": None,
            "quantity_units": None,
            "intent_id": f"{spec.agent_id}-dec{decision_index}-cancel-{i}",
            "decision_event_id": decide_event_id,
            "submitted_at": submitted_at,
        }
        kernel.enqueue(cancel_event)
        summaries.append(
            {
                "intent_id": cancel_event["intent_id"],
                "action": "CANCEL",
                "side": None,
                "order_type": None,
                "price_ticks": None,
                "quantity_units": None,
            }
        )
    return summaries


def handle_agent_decide(
    event: dict,
    world: dict,
    kernel: EventKernel,
    agent_specs: dict[str, AgentSpec],
    min_qty: int = 1,
    mult: int = 1000,
    target_fn: TargetFn = target_position,
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
        # R018-C007 (Round 5): evidence cursors come from the observation's
        # own boundaries (carried on the event), not the live world.
        cursor_boundary = event.get("_observed_cursor_to") or world.get("agent_cursors", {}).get(
            agent_id, "e1_0"
        )
        cursor_from = event.get("_observed_cursor_from") or world.get("agent_cursor_from", {}).get(
            agent_id, "e1_0"
        )
        evidence = _legacy_evidence(
            "market_maker",
            decision_index,
            cursor_from_event_id=cursor_from,
            cursor_to_event_id=cursor_boundary,
        )
    else:
        signal_bp = _compute_belief_signal(spec, iset, world, decision_index)
        if spec.goal_model_id is not None:
            # R018-C007 (Round 5): cursor_to must be the OBSERVATION's own
            # upper boundary (carried on the event), not the live world cursor
            # at decide-execution time -- under overlapping observations
            # (latency > observe_interval) the live cursor may have advanced
            # past the boundary this decision was based on, breaking the
            # evidence-cursor == observation-cursor invariant.
            cursor_to = event.get("_observed_cursor_to") or world.get("agent_cursors", {}).get(
                agent_id, "e1_0"
            )
            ewma_state = world.get("agent_ewma", {}).get(agent_id, {})
            # R018-C003 (Round 3): the public trades come from the OBSERVATION
            # snapshot the observe handler attached to this event -- the
            # rebuilt iset here has no public_trades.  Completed bars are
            # aggregated from them WITH zero-fill padding (代理策略 §3.1).
            # R018-C009 (Round 5): tape entries are dicts; the closed
            # InformationSetV1 requires typed PublicTrade objects.
            public_trades = tuple(
                PublicTrade(
                    price_ticks=t["price_ticks"],
                    quantity_units=t["quantity_units"],
                    timestamp=t["timestamp"],
                )
                for t in event.get("_observed_public_trades", ())
            )
            completed_bars = tuple(
                _completed_bars_with_zero_fill(
                    list(public_trades),
                    bar_ns=60_000_000_000,
                    up_to_ts=event["timestamp"],
                )
            )
            # R018-C007 (Round 3): the evidence cursor_from must be the
            # observation's own lower boundary, not a hardcoded e1_0 -- the
            # chain verifier requires evidence cursors == observation cursors,
            # and multi-interval runs advance past e1_0.
            cursor_from = event.get("_observed_cursor_from") or world.get(
                "agent_cursor_from", {}
            ).get(agent_id, "e1_0")
            intent, internal_state, evidence = _belief_intent_v2(
                spec,
                iset,
                decision_index,
                signal_bp,
                min_qty,
                mult,
                world.get("maint_bp", 500),
                world.get("maker_bps", 0),
                world.get("taker_bps", 0),
                cursor_from_event_id=cursor_from,
                cursor_to_event_id=cursor_to,
                ewma_value=ewma_state.get("value"),
                ewma_count=ewma_state.get("count", 0),
                public_trades=public_trades,
                completed_bars=completed_bars,
            )
            intents = [intent] if intent else []
        else:
            intent = _belief_intent(spec, iset, decision_index, signal_bp, min_qty, target_fn)
            intents = [intent] if intent else []
            internal_state = {"signal_bp": signal_bp}
            cursor_boundary = event.get("_observed_cursor_to") or world.get(
                "agent_cursors", {}
            ).get(agent_id, "e1_0")
            cursor_from = event.get("_observed_cursor_from") or world.get(
                "agent_cursor_from", {}
            ).get(agent_id, "e1_0")
            evidence = _legacy_evidence(
                "v1_legacy",
                decision_index,
                cursor_from_event_id=cursor_from,
                cursor_to_event_id=cursor_boundary,
            )

    decide_event_id = f"e{kernel.current_transaction_seq}_0"
    arrival_ts = event["timestamp"] + spec.latency_ns
    cancel_summaries = _cancel_stale_orders(
        spec, world, kernel, decide_event_id, decision_index, arrival_ts, event["timestamp"]
    )
    for order_seq, intent in enumerate(intents):
        order_id = f"o-{agent_id}-{decide_event_id}-{order_seq}"
        order_arrival = {
            "event_type": "ORDER_ARRIVAL",
            "timestamp": arrival_ts,
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

    event["intents"] = cancel_summaries + [
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
    # 0.1.5 T206 (ADR-003 §4): every AGENT_DECIDE carries DecisionEvidenceV1.
    # The v1 BENCHMARK and market-maker paths produce a path-tagged minimal
    # evidence (event_fields.json note on decision_evidence) so the field is
    # never silently absent -- only the v2 goal path fills real model fields.
    event["decision_evidence"] = {
        "schema_version": evidence.schema_version,
        "goal_model_id": evidence.goal_model_id,
        "goal_model_version": evidence.goal_model_version,
        "desired_position_units": evidence.desired_position_units,
        "executable_position_units": evidence.executable_position_units,
        "constraint_binding": evidence.constraint_binding,
        "constraint_reason": (
            str(evidence.constraint_reason) if evidence.constraint_reason is not None else None
        ),
        "trigger_provenance": str(evidence.trigger_provenance),
        "observation_event_id": event.get("observation_event_id", ""),
        "cursor_from_event_id": evidence.cursor_from_event_id,
        "cursor_to_event_id": evidence.cursor_to_event_id,
    }
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
    iset = _build_information_set(
        agent_id,
        world["accounts"],
        world["book"],
        world.get("initial_price_ticks", 10000),
        min_qty,
        mult,
    )
    event["information_set"] = iset

    # 0.1.5 T206 (代理策略 §1): consume the public tape through this agent's
    # cursor (half-open interval (last_seen, current]), then advance the
    # cursor atomically.  Consumption is a pure function of the tape (agent/
    # tape.py) so a retry re-consumes the same interval idempotently.
    #
    # R018-C001: the cursor upper bound is the LATEST committed market-data
    # boundary at observation-execution time, not the boundary the scheduler
    # snapshotted at enqueue time (which may lag -- the publish commits after
    # the observe transaction that rescheduled this one).  Falls back to the
    # event's own market_data_event_id when no publish has been committed.
    cursor_to = world.get("last_market_data_event_id") or event.get("market_data_event_id", "e1_0")
    cursors = world.setdefault("agent_cursors", {})
    cursor_from = cursors.get(agent_id, "e1_0")
    tape = world.get("public_tape", [])
    interval_fills = tape_interval(tape, cursor_from, cursor_to)
    event["cursor_from_event_id"] = cursor_from
    event["cursor_to_event_id"] = cursor_to
    event["market_data_event_id"] = cursor_to
    iset["public_trades"] = interval_fills
    # R018-C002: the cursor / EWMA advance must NOT mutate the live world
    # state inside the transaction -- if the transaction later aborts
    # (fail-stop, §1.5) the live cursors would have advanced past events that
    # were never committed, losing them forever.  Stage the update ON THE
    # EVENT (r0) so it commits with the transaction and is dropped with the
    # buffer on abort; the kernel applies it to the live state only after
    # commit.  (Round 3: staging in the shared world dict leaked on abort --
    # a later successful transaction would apply a failed observation's
    # cursor.  Staging on the event ties the update to this transaction.)
    ewma_state = world.get("agent_ewma", {}).get(agent_id, {"value": None, "count": 0})
    new_value, new_count = update_ewma(
        ewma_state["value"],
        ewma_state["count"],
        interval_fills,
        spec.ewma_half_life_trades,
    )
    event["_pending_agent_state"] = {
        "agent_id": agent_id,
        "cursor": cursor_to,
        "ewma_value": new_value,
        "ewma_count": new_count,
        # R018-C002 (Round 5): cursor_from and the decision index are also
        # transaction-scoped -- a failed observe must not consume the decision
        # index or advance cursor_from (previously written straight to world).
        "cursor_from": cursor_from,
        "decision_index": world.get("agent_decision_index", {}).get(agent_id, 0) + 1,
    }
    # R018-C007: the observation's lower cursor boundary is carried on the
    # event (not a world write) so legacy decisions can tag their evidence
    # with the same cursor_from the observe event recorded, and it commits
    # with the transaction (Round 5: the previous world write leaked on
    # abort and the decide path read a stale value under overlapping
    # observations).
    event["_observed_cursor_from"] = cursor_from

    # R018-C002: the decision index for THIS observation is read from the
    # committed world (advance applied by the kernel after the previous
    # successful observation); the next index is staged and applied only on
    # commit -- a failed observe must not consume it.  No world write here.
    decision_index = world.get("agent_decision_index", {}).get(agent_id, 0)
    # R018-C003 (Round 3): hand the decision the OBSERVATION's snapshot --
    # the public trades this agent consumed since its last cursor plus the
    # cursor boundaries.  handle_agent_decide rebuilds its own iset via
    # _build_information_set (no public_trades), so without this the goal
    # model could never see the real tape (Round 2 wired the field but the
    # value was always empty).
    decide = {
        "event_type": "AGENT_DECIDE",
        "timestamp": event["timestamp"] + spec.latency_ns,
        "agent_id": agent_id,
        "observation_event_id": observe_event_id,
        "rule_id": "default",
        "intents": [],
        "internal_state": {},
        "_decision_index": decision_index,
        # R018-C003 (Round 5): the decision sees the FULL tape history up to
        # the observation boundary (not just this interval) so the completed
        # K-line sequence is complete across observations -- an interval-only
        # slice dropped earlier bars, mis-sizing momentum/herding lookbacks.
        "_observed_public_trades": [
            dict(t) for t in tape_interval(tape, INITIAL_CURSOR_EVENT_ID, cursor_to)
        ],
        "_observed_cursor_from": cursor_from,
        "_observed_cursor_to": cursor_to,
    }
    kernel.enqueue(decide)
    event["accepted"] = True
    event["reject_reason"] = None
    return []
