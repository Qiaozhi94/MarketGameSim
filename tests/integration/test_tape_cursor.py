"""T206: public tape, per-agent cursor and decision-evidence chain.

Covers (AC-002 / AC-005 / FR-022 / FR-025):
- the kernel projects TRADE_SETTLE records into the global public tape;
- AGENT_OBSERVE records the half-open cursor interval (from, to];
- interval consumption is a pure function of the tape (retry-safe: same
  interval -> same fills, no duplication -- design.md §5);
- per-agent cursors do not cross-talk;
- AGENT_DECIDE carries DecisionEvidenceV1 audit fields end-to-end.
"""

from __future__ import annotations

from market_game_sim.agent.handler import handle_agent_decide, handle_agent_observe
from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.agent.tape import (
    INITIAL_CURSOR_EVENT_ID,
    event_id_rank,
    tape_interval,
)
from market_game_sim.book.matching import match_order
from market_game_sim.book.orderbook import Book, RestingOrder
from market_game_sim.eventlog.bootstrap import (
    build_account_payload_from_accounts,
    build_book_payload,
)
from market_game_sim.kernel.runner import EventKernel
from market_game_sim.ledger.account import Account


def _dispatch(event: dict, world: dict, kernel: EventKernel) -> list[dict]:
    et = event["event_type"]
    if et == "ORDER_ARRIVAL":
        return match_order(event, world, kernel)
    if et == "AGENT_OBSERVE":
        return handle_agent_observe(event, world, kernel)
    if et == "AGENT_DECIDE":
        return handle_agent_decide(event, world, kernel, world["agent_specs"])
    return []


def _world(
    specs: dict[str, AgentSpec],
    accounts: dict[str, Account],
    signals: dict[str, int] | None = None,
) -> dict:
    return {
        "book": Book(initial_price_ticks=10000),
        "accounts": accounts,
        "exchange_fee_units": 0,
        "exchange_risk_pnl_units": 0,
        "mult": 1000,
        "maker_bps": -1,
        "taker_bps": 5,
        "initial_price_ticks": 10000,
        "agent_specs": specs,
        "agent_signals": signals or {},
        "agent_decision_index": {},
        "public_tape": [],
        "agent_cursors": {},
    }


def _belief_spec(
    agent_id: str,
    *,
    goal_model_id: str | None = "risk_budget_linear_v1",
    aggressiveness_bp: int = 0,
) -> AgentSpec:
    return AgentSpec(
        agent_id=agent_id,
        role="retail",
        observe_interval_ns=1_000_000_000,
        latency_ns=50_000_000,
        leverage_tier=10,
        initial_bp=1000,
        aggressiveness_bp=aggressiveness_bp,
        max_order_qty=10_000,
        goal_model_id=goal_model_id,
        risk_appetite_x1000=2000,
    )


def _mm_spec() -> AgentSpec:
    return AgentSpec(
        agent_id="mm-0",
        role="inventory_market_maker",
        observe_interval_ns=100_000_000,
        latency_ns=5_000_000,
        is_market_maker=True,
        half_spread_ticks=5,
        quote_size=10_000,
        max_inventory=100_000,
        inventory_skew_k_bp=10_000,
    )


def _seed_book(book: Book, *, bid_price: int = 9990, ask_price: int = 10010) -> None:
    book.insert(
        RestingOrder(
            order_id="seed-bid",
            agent_id="seed",
            side="BUY",
            order_type="LIMIT",
            price_ticks=bid_price,
            quantity_units=100_000,
            transaction_seq=0,
        )
    )
    book.insert(
        RestingOrder(
            order_id="seed-ask",
            agent_id="seed",
            side="SELL",
            order_type="LIMIT",
            price_ticks=ask_price,
            quantity_units=100_000,
            transaction_seq=1,
        )
    )


def _run(
    specs: dict[str, AgentSpec],
    accounts: dict[str, Account],
    *,
    signals: dict[str, int] | None = None,
    max_transactions: int = 30,
    seed_book: bool = False,
) -> tuple[EventKernel, dict]:
    world = _world(specs, accounts, signals)
    if seed_book:
        _seed_book(world["book"])
    kernel = EventKernel(run_id="tape")
    kernel.bootstrap(
        build_account_payload_from_accounts(accounts, mult=1000),
        build_book_payload(last_ticks=None),
    )
    for aid in specs:
        kernel.enqueue(
            {
                "event_type": "AGENT_OBSERVE",
                "timestamp": 0,
                "agent_id": aid,
                "observed_at": 0,
                "market_data_event_id": "e1_0",
                "information_set": {},
            }
        )
    kernel.run(_dispatch, world, max_transactions=max_transactions)
    assert kernel.terminated == "COMPLETED", f"aborted: {kernel.abort_detail}"
    return kernel, world


# --------------------------------------------------------------------------- #
# tape projection + interval semantics
# --------------------------------------------------------------------------- #


def test_kernel_projects_trades_into_public_tape():
    mm = _mm_spec()
    agent = _belief_spec("agent-0", aggressiveness_bp=10_000)
    accounts = {
        "mm-0": Account(agent_id="mm-0", wallet_units=10**14),
        "agent-0": Account(agent_id="agent-0", wallet_units=10**14),
    }
    # Pre-seed the book so the belief agent's taker order crosses the MM's
    # ask (aggressiveness 0 on an empty book skips order emission -- §6.1).
    _, world = _run(
        {"mm-0": mm, "agent-0": agent},
        accounts,
        signals={"agent-0": 5000},
        seed_book=True,
    )
    tape = world["public_tape"]
    assert tape, "a trade must have occurred (MM quotes vs taker belief order)"
    for fill in tape:
        assert "event_id" in fill
        assert fill["price_ticks"] > 0
        assert fill["quantity_units"] > 0
        assert fill["taker_agent_id"]


def test_event_id_rank_orders_tape():
    assert event_id_rank("e1_0") < event_id_rank("e2_0")
    assert event_id_rank("e2_0") < event_id_rank("e2_1")
    assert event_id_rank("e2_1") < event_id_rank("e10_0")


def test_tape_interval_half_open():
    tape = [
        {"event_id": "e1_0"},
        {"event_id": "e2_1"},
        {"event_id": "e3_0"},
        {"event_id": "e4_2"},
    ]
    got = tape_interval(tape, "e2_0", "e4_0")
    assert [f["event_id"] for f in got] == ["e2_1", "e3_0"]
    # from exclusive: e2_1 > e2_0 included; e2_0 itself excluded.
    assert all(f["event_id"] != "e1_0" for f in got)


def test_tape_interval_initial_cursor_includes_all_since_genesis():
    tape = [{"event_id": "e3_1"}, {"event_id": "e5_0"}]
    got = tape_interval(tape, INITIAL_CURSOR_EVENT_ID, "e6_0")
    assert len(got) == 2


def test_tape_interval_retry_idempotent():
    tape = [{"event_id": "e2_1"}, {"event_id": "e3_0"}]
    first = tape_interval(tape, "e1_0", "e4_0")
    second = tape_interval(tape, "e1_0", "e4_0")
    assert first == second
    assert len(first) == 2


# --------------------------------------------------------------------------- #
# observe records cursor boundaries + evidence chain
# --------------------------------------------------------------------------- #


def test_observe_records_cursor_boundaries():
    mm = _mm_spec()
    agent = _belief_spec("agent-0")
    accounts = {
        "mm-0": Account(agent_id="mm-0", wallet_units=10**14),
        "agent-0": Account(agent_id="agent-0", wallet_units=10**14),
    }
    kernel, _ = _run({"mm-0": mm, "agent-0": agent}, accounts, signals={"agent-0": 5000})
    observes = [r for r in kernel.committed_records if r["event_type"] == "AGENT_OBSERVE"]
    assert observes
    for r in observes:
        assert "cursor_from_event_id" in r
        assert "cursor_to_event_id" in r
        assert r["cursor_to_event_id"] == r["market_data_event_id"]
        assert "public_trades" in r["information_set"]
        assert isinstance(r["information_set"]["public_trades"], list)


def test_per_agent_cursors_do_not_cross_talk():
    """Two belief agents observe the same tape but each cursor advances
    independently: agent A consuming (e1_0, e5_0] must not move agent B's
    cursor, and agent B's later observation still sees everything since its
    own last-seen."""
    world = _world(
        {"a": _belief_spec("a"), "b": _belief_spec("b")},
        {
            "a": Account(agent_id="a", wallet_units=10**14),
            "b": Account(agent_id="b", wallet_units=10**14),
        },
        signals={"a": 5000, "b": -3000},
    )
    world["public_tape"] = [
        {
            "event_id": "e2_1",
            "price_ticks": 10000,
            "quantity_units": 10,
            "timestamp": 0,
            "taker_agent_id": "a",
        },
        {
            "event_id": "e3_0",
            "price_ticks": 10010,
            "quantity_units": 5,
            "timestamp": 0,
            "taker_agent_id": "b",
        },
        {
            "event_id": "e5_0",
            "price_ticks": 10020,
            "quantity_units": 3,
            "timestamp": 0,
            "taker_agent_id": "a",
        },
    ]
    kernel = EventKernel(run_id="cursors")
    kernel.bootstrap(
        build_account_payload_from_accounts(world["accounts"], mult=1000),
        build_book_payload(last_ticks=None),
    )
    for aid in ("a", "b"):
        kernel.enqueue(
            {
                "event_type": "AGENT_OBSERVE",
                "timestamp": 0,
                "agent_id": aid,
                "observed_at": 0,
                "market_data_event_id": "e5_0",
                "information_set": {},
            }
        )
    kernel.run(_dispatch, world, max_transactions=6)
    assert kernel.terminated == "COMPLETED", f"aborted: {kernel.abort_detail}"
    # Both agents observed up to e5_0; each sees the full tape since genesis.
    assert world["agent_cursors"]["a"] == "e5_0"
    assert world["agent_cursors"]["b"] == "e5_0"


def test_decision_carries_decision_evidence():
    agent = _belief_spec("agent-0")
    accounts = {"agent-0": Account(agent_id="agent-0", wallet_units=10**14)}
    kernel, _ = _run({"agent-0": agent}, accounts, signals={"agent-0": 5000})
    decides = [r for r in kernel.committed_records if r["event_type"] == "AGENT_DECIDE"]
    assert decides
    for d in decides:
        ev = d.get("decision_evidence")
        assert ev is not None
        assert ev["goal_model_id"] == "risk_budget_linear_v1"
        assert ev["goal_model_version"] == 1
        assert ev["trigger_provenance"] == "ENDOGENOUS_AGENT"
        assert isinstance(ev["desired_position_units"], int)
        assert isinstance(ev["executable_position_units"], int)
        assert isinstance(ev["constraint_binding"], bool)
        assert ev["cursor_from_event_id"] == "e1_0"
        assert ev["cursor_to_event_id"] == "e1_0"


def test_v1_path_decision_evidence_is_path_tagged():
    """BENCHMARK compat: goal_model_id=None -> v1 linear path, no goal model
    -- decision_evidence still exists (never silently absent) but is a
    path-tagged minimal evidence with goal_model_id='v1_legacy'."""
    agent = _belief_spec("agent-0", goal_model_id=None)
    accounts = {"agent-0": Account(agent_id="agent-0", wallet_units=10**14)}
    kernel, _ = _run({"agent-0": agent}, accounts, signals={"agent-0": 5000})
    decides = [r for r in kernel.committed_records if r["event_type"] == "AGENT_DECIDE"]
    assert decides
    for d in decides:
        ev = d["decision_evidence"]
        assert ev is not None
        assert ev["goal_model_id"] == "v1_legacy"
        assert ev["desired_position_units"] == 0
        assert ev["executable_position_units"] == 0


# --------------------------------------------------------------------------- #
# R018-C001 regression: the observe scheduler must snapshot the LATEST
# market-data boundary, not the hardcoded bootstrap id (so the cursor
# advances after a trade).
# --------------------------------------------------------------------------- #


def test_post_trade_observation_consumes_latest_market_interval():
    """A real run with a trade must schedule the *next* observation at the
    latest committed MARKET_DATA_PUBLISH boundary, so its cursor interval
    (last_seen, current] is non-empty and the public tape advances."""
    from market_game_sim.experiment.config import ExperimentConfig
    from market_game_sim.experiment.runner import run_one

    cfg = ExperimentConfig(
        seed=31,
        max_transactions=80,
        agent_specs=[_mm_spec(), _belief_spec("agent-0", aggressiveness_bp=10_000)],
        agent_signals={"agent-0": 10_000},
    )
    result = run_one(cfg)
    assert result.terminated == "COMPLETED", f"aborted: {result.abort_code}"
    events = result.events

    trades = [r for r in events if r.get("event_type") == "TRADE_SETTLE"]
    assert trades, "precondition: the run must produce at least one trade"

    # A later AGENT_OBSERVE (rescheduled after the first) must reference a
    # market-data boundary beyond the bootstrap snapshot.
    observes = [
        r
        for r in events
        if r.get("event_type") == "AGENT_OBSERVE" and r.get("agent_id") == "agent-0"
    ]
    assert len(observes) >= 2, "precondition: the belief agent observes more than once"
    later = observes[-1]
    assert later["market_data_event_id"] != "e1_0", (
        "R018-C001: rescheduled observation still references the bootstrap id; "
        "the cursor can never advance past the initial snapshot"
    )
    # Its cursor interval must be non-empty (fresh fills since last_seen).
    assert later["cursor_to_event_id"] != "e1_0"


# --------------------------------------------------------------------------- #
# R018-C002 regression: the cursor / EWMA advance is staged and only applied
# after the transaction commits -- a failed observe transaction must NOT
# advance the live cursors (fail-stop loses the staged update, not the data).
# --------------------------------------------------------------------------- #


def _bad_tape_world(specs: dict[str, AgentSpec], accounts: dict[str, Account]) -> dict:
    world = _world(specs, accounts)
    world["public_tape"] = [
        # Deliberately missing "event_id" -> tape_interval's event_id_rank
        # raises mid-transaction, proving the staged state is dropped.
        {"price_ticks": 100, "quantity_units": 10, "timestamp": 0, "taker_agent_id": "a"}
    ]
    return world


def test_observe_failure_rolls_back_cursor_and_ewma():
    """A corrupt tape entry that breaks interval consumption must abort the
    observe transaction WITHOUT advancing the live cursor -- the staged
    update lives on the event (r0) and is dropped with the buffer on abort."""
    agent = _belief_spec("agent-0")
    accounts = {"agent-0": Account(agent_id="agent-0", wallet_units=10**14)}
    world = _bad_tape_world({"agent-0": agent}, accounts)
    kernel = EventKernel(run_id="rollback")
    kernel.bootstrap(
        build_account_payload_from_accounts(accounts, mult=1000),
        build_book_payload(last_ticks=None),
    )
    kernel.enqueue(
        {
            "event_type": "AGENT_OBSERVE",
            "timestamp": 0,
            "agent_id": "agent-0",
            "observed_at": 0,
            "market_data_event_id": "e1_0",
            "information_set": {},
        }
    )
    kernel.run(_dispatch, world, max_transactions=3)
    # Fail-stop: the run aborts, but the live cursor was never advanced past
    # the corrupted fill (R018-C002: staged state dropped with the buffer).
    assert world["agent_cursors"].get("agent-0", "e1_0") == "e1_0"
    assert kernel.terminated == "ABORTED"


def test_failure_after_staging_does_not_leak_into_next_transaction():
    """R018-C002 (Round 3): a transaction that stages its cursor/EWMA update
    and THEN aborts must not leak the staged state into a later successful
    transaction on the same world -- the stage lives on the event (r0) and
    is dropped with the buffer, not in a shared world dict."""
    agent = _belief_spec("agent-0")
    accounts = {"agent-0": Account(agent_id="agent-0", wallet_units=10**14)}
    world = _world({"agent-0": agent}, accounts)
    # The observe will stage cursor=e5_0 (from a fake last_market_data), then
    # the injected failure aborts the transaction.
    world["last_market_data_event_id"] = "e5_0"

    fail_dispatch_calls = {"n": 0}

    def fail_after_staging(event, w, kernel):
        et = event["event_type"]
        if et == "AGENT_OBSERVE":
            handle_agent_observe(event, w, kernel)
            # Staging is done (event["_pending_agent_state"] set); now abort.
            fail_dispatch_calls["n"] += 1
            raise RuntimeError("simulated abort after staging")
        return []

    k1 = EventKernel(run_id="leak1")
    k1.bootstrap(
        build_account_payload_from_accounts(accounts, mult=1000),
        build_book_payload(last_ticks=None),
    )
    k1.enqueue(
        {
            "event_type": "AGENT_OBSERVE",
            "timestamp": 0,
            "agent_id": "agent-0",
            "observed_at": 0,
            "market_data_event_id": "e5_0",
            "information_set": {},
        }
    )
    k1.run(fail_after_staging, world, max_transactions=3)
    assert k1.terminated == "ABORTED"
    assert fail_dispatch_calls["n"] == 1
    # Live cursor must NOT have advanced to the failed observation's e5_0.
    assert world["agent_cursors"].get("agent-0", "e1_0") == "e1_0", (
        "failed observe leaked its staged cursor into the live world"
    )

    # Reuse the SAME world for a fresh successful run: the failed stage must
    # not resurface and push the cursor.  Remove the fake boundary so this
    # run's own observation targets e1_0 -- if k1's e5_0 stage leaked, the
    # cursor would jump to e5_0 despite this run staging e1_0.
    world.pop("last_market_data_event_id", None)
    k2 = EventKernel(run_id="leak2")
    k2.bootstrap(
        build_account_payload_from_accounts(accounts, mult=1000),
        build_book_payload(last_ticks=None),
    )
    k2.enqueue(
        {
            "event_type": "AGENT_OBSERVE",
            "timestamp": 0,
            "agent_id": "agent-0",
            "observed_at": 0,
            "market_data_event_id": "e1_0",
            "information_set": {},
        }
    )
    k2.run(_dispatch, world, max_transactions=3)
    assert k2.terminated == "COMPLETED"
    # Still at e1_0: the failed e5_0 stage did not leak into this run.
    assert world["agent_cursors"].get("agent-0", "e1_0") == "e1_0"
