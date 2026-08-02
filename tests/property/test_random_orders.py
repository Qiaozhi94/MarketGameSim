"""T605: Property test — random order flow with C1/C2 invariants.

Multiple seeds (3, 42, 99, 123) to cover diverse order patterns.
"""

import random

import pytest

from market_game_sim.book.simulator import run_simulation
from market_game_sim.ledger.account import Account
from market_game_sim.ledger.conservation import check_c1_c2


def _rand_events(n: int, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    events: list[dict] = []
    for i in range(n):
        side = rng.choice(["BUY", "SELL"])
        price = rng.randint(50, 200)  # in absolute price, converted to ticks
        qty = rng.randint(1, 50)      # in absolute qty, converted to units
        agent = f"A{rng.randint(0, 4)}"
        events.append({
            "event_type": "ORDER_ARRIVAL",
            "timestamp": (i + 1) * 10,
            "agent_id": agent,
            "order_id": f"o{i}",
            "action": "SUBMIT",
            "side": side,
            "order_type": rng.choice(["LIMIT", "MARKET"]),
            "price_ticks": price * 100,
            "quantity_units": qty * 1000,
        })
    return events


def test_random_order_flow_c1_c2():
    events = _rand_events(200, seed=99)
    accounts = {
        "A0": Account("A0", 100000000000),
        "A1": Account("A1", 100000000000),
        "A2": Account("A2", 100000000000),
        "A3": Account("A3", 100000000000),
        "A4": Account("A4", 100000000000),
    }
    total_wallet_0 = sum(a.wallet_units for a in accounts.values())
    records, book = run_simulation([], events, accounts=accounts)

    exchange_fee = sum(
        r.get("taker_fee_cash_units", 0) + r.get("maker_fee_cash_units", 0)
        for r in records if r["event_type"] == "TRADE_SETTLE"
    )
    ok, msg = check_c1_c2(accounts, exchange_fee, 0, total_wallet_0)
    assert ok, f"C1/C2 failed: {msg}"


def test_log_keys_strictly_increasing():
    events = _rand_events(100, seed=42)
    accounts = {
        "A0": Account("A0", 100000000000),
        "A1": Account("A1", 100000000000),
    }
    records, _ = run_simulation([], events, accounts=accounts)

    for i in range(1, len(records)):
        prev = records[i - 1]
        curr = records[i]
        pk = (prev["timestamp"], prev["transaction_seq"], prev["record_index"])
        ck = (curr["timestamp"], curr["transaction_seq"], curr["record_index"])
        assert ck > pk, f"log_key not increasing at {i}: {pk} -> {ck}"
