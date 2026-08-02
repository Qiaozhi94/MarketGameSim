"""T602 (SC-002): Determinism across different PYTHONHASHSEED values."""

import os
import subprocess
import sys

from market_game_sim.book.simulator import run_simulation
from market_game_sim.ledger.account import Account
from market_game_sim.verify import digest_events


def _make_simulation() -> list[dict]:
    accounts = {
        "A": Account("A", 100000000000),
        "B": Account("B", 100000000000),
        "C": Account("C", 100000000000),
    }
    events = [
        {
            "event_type": "ORDER_ARRIVAL",
            "timestamp": 100,
            "agent_id": "B",
            "order_id": "o1",
            "action": "SUBMIT",
            "side": "SELL",
            "order_type": "LIMIT",
            "price_ticks": 10000,
            "quantity_units": 5000,
        },
        {
            "event_type": "ORDER_ARRIVAL",
            "timestamp": 200,
            "agent_id": "A",
            "order_id": "o2",
            "action": "SUBMIT",
            "side": "BUY",
            "order_type": "LIMIT",
            "price_ticks": 10000,
            "quantity_units": 3000,
        },
    ]
    records, book = run_simulation([], events, accounts=accounts)
    return records


def test_same_run_same_hash():
    r1 = _make_simulation()
    r2 = _make_simulation()
    assert digest_events(r1) == digest_events(r2)


def test_cross_pythonhashseed_determinism():
    script = f"""
import json, sys
sys.path.insert(0, r'{os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}')
from market_game_sim.book.simulator import run_simulation
from market_game_sim.ledger.account import Account
from market_game_sim.verify import digest_events
accounts = {{"A": Account("A", 100000000000), "B": Account("B", 100000000000)}}
events = [{{"event_type":"ORDER_ARRIVAL","timestamp":100,"agent_id":"B",
  "order_id":"o1","action":"SUBMIT","side":"SELL","order_type":"LIMIT",
  "price_ticks":10000,"quantity_units":5000}},
 {{"event_type":"ORDER_ARRIVAL","timestamp":200,"agent_id":"A",
  "order_id":"o2","action":"SUBMIT","side":"BUY","order_type":"LIMIT",
  "price_ticks":10000,"quantity_units":3000}}]
records, book = run_simulation([], events, accounts=accounts)
print(digest_events(records))
"""
    # Run with PYTHONHASHSEED=1
    env1 = {**os.environ, "PYTHONHASHSEED": "1"}
    r1 = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env1,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    # Run with PYTHONHASHSEED=2
    env2 = {**os.environ, "PYTHONHASHSEED": "2"}
    r2 = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env2,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    h1 = r1.stdout.strip()
    h2 = r2.stdout.strip()
    assert h1 == h2, f"hash mismatch: {h1} != {h2}"
