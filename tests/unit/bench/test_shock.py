"""bench/shock.py: structural tests for the sustained forcing-trade builder.

NOT a test that liquidations actually trigger -- E5/E6 calibration using
this mechanism is still an open item (see docs/experiments/
0.1.2-exit-evidence-index.json). These only lock the event shape/timing
contract so future calibration work has a stable, tested building block.
"""

from __future__ import annotations

from market_game_sim.bench.shock import SHOCK_AGENT_ID, SHOCK_WALLET_UNITS, build_shock_series


def test_produces_requested_count():
    _accounts, events = build_shock_series(count=10)
    assert len(events) == 10


def test_events_are_evenly_spaced_from_start():
    _accounts, events = build_shock_series(count=5, interval_ns=200_000_000, start_ns=100_000_000)
    timestamps = [e["timestamp"] for e in events]
    assert timestamps == [100_000_000 + i * 200_000_000 for i in range(5)]


def test_order_ids_are_unique():
    _accounts, events = build_shock_series(count=20)
    order_ids = [e["order_id"] for e in events]
    assert len(order_ids) == len(set(order_ids))


def test_all_events_are_market_orders_same_side():
    _accounts, events = build_shock_series(side="SELL", count=10)
    assert all(e["order_type"] == "MARKET" for e in events)
    assert all(e["side"] == "SELL" for e in events)
    assert all(e["price_ticks"] is None for e in events)


def test_all_events_use_the_shock_agent_id():
    _accounts, events = build_shock_series(count=10)
    assert all(e["agent_id"] == SHOCK_AGENT_ID for e in events)


def test_extra_accounts_prefunds_the_shock_agent():
    accounts, _events = build_shock_series()
    assert accounts == {SHOCK_AGENT_ID: SHOCK_WALLET_UNITS}


def test_quantity_per_shock_is_applied_to_every_event():
    _accounts, events = build_shock_series(quantity_units_per_shock=777, count=3)
    assert all(e["quantity_units"] == 777 for e in events)


def test_buy_side_variant():
    _accounts, events = build_shock_series(side="BUY", count=3)
    assert all(e["side"] == "BUY" for e in events)
