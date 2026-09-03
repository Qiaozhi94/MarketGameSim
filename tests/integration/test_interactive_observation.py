"""T804 integration tests for the committed-state observation boundary."""

import json
from dataclasses import FrozenInstanceError, asdict

import pytest

from market_game_sim.eventlog.bootstrap import (
    build_account_payload_from_accounts,
    build_book_payload,
)
from market_game_sim.interactive import (
    CommittedObservationStore,
    ObservationProjector,
    SessionState,
    SessionView,
)
from market_game_sim.kernel.runner import EventKernel
from market_game_sim.ledger.account import Account

BAR_NS = 60_000_000_000


def _committed_kernel_with_future_queue() -> tuple[EventKernel, Account]:
    kernel = EventKernel(run_id="interactive-test")
    human = Account(
        agent_id="human",
        wallet_units=1_000_000,
        position_units=2,
        entry_notional_units=200_000,
        reserved_units=10_000,
    )
    accounts = {
        "human": human,
        "agent-secret": Account(agent_id="agent-secret", wallet_units=987_654_321),
    }
    kernel.bootstrap(
        build_account_payload_from_accounts(accounts, risk_mark_ticks=100),
        build_book_payload(),
    )
    timestamp = 1
    for offset in range(12):
        for side, price_ticks in (("BUY", 100 - offset), ("SELL", 101 + offset)):
            kernel.enqueue(
                {
                    "event_type": "ORDER_ARRIVAL",
                    "timestamp": timestamp,
                    "action": "SUBMIT",
                    "agent_id": "agent-secret",
                    "order_id": f"{side.lower()}-{offset}",
                    "side": side,
                    "order_type": "LIMIT",
                    "price_ticks": price_ticks,
                    "quantity_units": offset + 1,
                }
            )
            timestamp += 1
    kernel.enqueue(
        {
            "event_type": "ORDER_ARRIVAL",
            "timestamp": timestamp,
            "action": "SUBMIT",
            "agent_id": "human",
            "order_id": "human-order",
            "side": "BUY",
            "order_type": "LIMIT",
            "price_ticks": 50,
            "quantity_units": 1,
        }
    )
    for timestamp, price_ticks in (
        (10_000_000_000, 100),
        (70_000_000_000, 101),
        (120_000_000_000, 99_999),
    ):
        kernel.enqueue(
            {
                "event_type": "ORDER_ARRIVAL",
                "timestamp": timestamp,
                "action": "SUBMIT",
                "price_ticks": price_ticks,
            }
        )

    def settle(event, world, running_kernel):
        if event["event_type"] == "SNAPSHOT":
            return []
        event["accepted"] = True
        event["reject_reason"] = None
        if event.get("order_type") == "LIMIT":
            return []
        return [
            {
                "event_type": "TRADE_SETTLE",
                "price_ticks": event["price_ticks"],
                "quantity_units": 1,
                "taker_agent_id": "agent-secret",
                "taker_side": "BUY",
            }
        ]

    kernel.run(settle, {"public_tape": []}, max_transactions=29)
    return kernel, human


def _session_view() -> SessionView:
    return SessionView(
        session_id="session-1",
        state=SessionState.PAUSED,
        snapshot_revision=7,
        processed_transactions=29,
        pending_inputs=3,
        logical_timestamp=90_000_000_000,
    )


def test_observation_hides_uncommitted_future_and_private_state() -> None:
    kernel, _human = _committed_kernel_with_future_queue()
    projector = ObservationProjector(human_agent_id="human", initial_price_ticks=100)

    snapshot = projector.project(
        session=_session_view(),
        committed_source=kernel,
        recent_input_results=[
            {
                "input_seq": 2,
                "accepted": False,
                "reason_code": "INVALID_INPUT",
                "assigned_timestamp": None,
                "event_ids": [],
                "private_diagnostic": "DO_NOT_LEAK",
            }
        ],
    )

    assert [level.price_ticks for level in snapshot.market.bids] == list(range(100, 90, -1))
    assert [level.price_ticks for level in snapshot.market.asks] == list(range(101, 111))
    assert len(snapshot.market.completed_bars) == 1
    assert snapshot.market.completed_bars[0].start_ns == 0
    assert [trade.timestamp for trade in snapshot.market.public_trades] == [
        10_000_000_000,
        70_000_000_000,
    ]
    assert [trade.price_ticks for trade in snapshot.market.public_trades] == [100, 101]
    assert snapshot.account.wallet_units == 1_000_000
    assert snapshot.account.equity_units == 1_001_000
    assert [order.order_id for order in snapshot.account.active_orders] == ["human-order"]

    encoded = json.dumps(asdict(snapshot), sort_keys=True)
    for forbidden in ("99_999", "99999", "agent-secret", "secret-order", "DO_NOT_LEAK"):
        assert forbidden not in encoded
    assert "pending_inputs" not in encoded

    first_trade_id = snapshot.market.public_trades[0].event_id
    incremental = projector.project(
        session=_session_view(),
        committed_source=kernel,
        after_event_id=first_trade_id,
    )
    assert [trade.price_ticks for trade in incremental.market.public_trades] == [101]


def test_snapshot_is_detached_from_mutable_world() -> None:
    kernel, live_human = _committed_kernel_with_future_queue()
    projector = ObservationProjector(human_agent_id="human", initial_price_ticks=100)
    snapshot = projector.project(
        session=_session_view(),
        committed_source=kernel,
    )

    live_human.wallet_units = -1

    assert snapshot.account.wallet_units == 1_000_000
    assert snapshot.market.best_bid == 100
    with pytest.raises(FrozenInstanceError):
        snapshot.account.wallet_units = -1


def test_observe_after_revision_and_revision_regression() -> None:
    kernel, _human = _committed_kernel_with_future_queue()
    projector = ObservationProjector(human_agent_id="human", initial_price_ticks=100)
    snapshot = projector.project(
        session=_session_view(),
        committed_source=kernel,
    )
    store = CommittedObservationStore()

    store.publish(snapshot)

    assert store.observe() is snapshot
    assert store.observe(after_revision=6) is snapshot
    assert store.observe(after_revision=7) is None
    with pytest.raises(ValueError, match="must increase"):
        store.publish(snapshot)
