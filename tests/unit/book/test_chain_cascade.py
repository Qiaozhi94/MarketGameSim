"""事件 Schema §4.2.2 regression: chain_depth wiring in _run_post_batch_risk_check.

Deep-dive while calibrating BENCH-001's coverage assertions (E5/E6) found
that ``chain_depth`` could never exceed 0 in any real run: the chain-depth
increment logic itself (``ledger/risk.py::_chain_attrs_for`` /
``run_phase2_margin_scan``) was already implemented and directly
unit-tested (tests/unit/ledger/test_risk.py), but ``_run_post_batch_risk_check``
-- the only real call site -- always passed ``parent_chain_id=None``,
regardless of whether the triggering event was itself a liquidation order's
own trade. This is the same "component implemented + unit-tested in
isolation, never wired into the real pipeline" pattern as §6.2's missing
CANCEL emission earlier this session.

Tests call ``_run_post_batch_risk_check`` directly (matching test_risk.py's
convention of testing risk-scan functions without going through the full
kernel/matching state machine) -- constructing a scenario through the real
end-to-end order flow requires many more moving parts (a real liquidation
order needs the correct ``liquidation_generation`` and a book state that
wasn't already resolved by an intervening scan) for no additional coverage
of the logic under test.
"""

from __future__ import annotations

from market_game_sim.book.matching import _run_post_batch_risk_check
from market_game_sim.book.orderbook import Book
from market_game_sim.ledger.account import Account, AccountState

CASH = 10**8


class _FakeKernel:
    current_transaction_seq = 42

    def enqueue(self, event: dict) -> None:
        pass


def _pending_liquidator(chain_id: str = "mc-root", chain_depth: int = 0) -> Account:
    """A already flagged PENDING_LIQUIDATION with an established chain
    (matching the state a real prior phase-2 scan would have left it in)."""
    acct = Account(
        "A", wallet_units=5000 * CASH, position_units=500_000, entry_notional_units=50000 * CASH
    )
    acct.state = AccountState.PENDING_LIQUIDATION
    acct.chain_id = chain_id
    acct.chain_depth = chain_depth
    acct.liquidation_generation = 1
    return acct


def _breaching_victim() -> Account:
    """B: identical ratio to acceptance-vectors.md 案例7's account -- ACTIVE
    and healthy at price 100, breaches 500bp maintenance below ~94.7 ticks
    (verified against the real engine in TestCase7PartialLiquidationRecalc)."""
    return Account(
        "B", wallet_units=5000 * CASH, position_units=500_000, entry_notional_units=50000 * CASH
    )


def _world(accounts: dict[str, Account]) -> dict:
    return {
        "accounts": accounts,
        "maint_bp": 500,
        "target_bp": 1000,
        "taker_bps": 5,
        "mult": 1000,
        "initial_price_ticks": 10000,
        "exchange_risk_pnl_units": 0,
        "liquidation_latency_ns": 1_000_000,
    }


def test_liquidation_triggered_scan_chains_a_newly_breached_account():
    """Positive case: the triggering event is A's own liquidation trade
    (origin=LIQUIDATION); B newly breaches as a result -- B must inherit
    A's chain_id and be one hop deeper."""
    a = _pending_liquidator(chain_id="mc-root", chain_depth=0)
    b = _breaching_victim()
    book = Book(initial_price_ticks=10000)
    book.last_ticks = 9000  # below B's ~9473.68-tick breach threshold

    event = {"origin": "LIQUIDATION", "agent_id": "A", "timestamp": 500}
    records = _run_post_batch_risk_check(event, book, _world({"A": a, "B": b}), _FakeKernel(), [])

    by_agent = {r["agent_id"]: r for r in records}
    assert by_agent["A"]["chain_id"] == "mc-root"
    assert by_agent["A"]["chain_depth"] == 0
    assert by_agent["B"]["chain_id"] == "mc-root"
    assert by_agent["B"]["chain_depth"] == 1


def test_non_liquidation_triggered_scan_does_not_fabricate_a_chain():
    """Negative/contrast case: same breach, but the triggering event is a
    normal (non-liquidation) trade -- B must NOT be linked to A's chain;
    it gets its own fresh chain_id, matching pre-existing chain semantics
    for scans with no liquidation-origin trigger."""
    a = _pending_liquidator(chain_id="mc-root", chain_depth=0)
    b = _breaching_victim()
    book = Book(initial_price_ticks=10000)
    book.last_ticks = 9000

    event = {"origin": "AGENT", "agent_id": "X", "timestamp": 500}
    records = _run_post_batch_risk_check(event, book, _world({"A": a, "B": b}), _FakeKernel(), [])

    by_agent = {r["agent_id"]: r for r in records}
    assert by_agent["B"]["chain_id"] != "mc-root"
    assert by_agent["B"]["chain_depth"] == 0


def test_liquidation_origin_but_liquidator_has_no_established_chain_does_not_chain():
    """Edge case: origin=LIQUIDATION but the acting account has no
    chain_id recorded (e.g. state drifted/edge case) -- must not crash and
    must not fabricate a parent chain from nothing."""
    a = _pending_liquidator()
    a.chain_id = None
    b = _breaching_victim()
    book = Book(initial_price_ticks=10000)
    book.last_ticks = 9000

    event = {"origin": "LIQUIDATION", "agent_id": "A", "timestamp": 500}
    records = _run_post_batch_risk_check(event, book, _world({"A": a, "B": b}), _FakeKernel(), [])

    by_agent = {r["agent_id"]: r for r in records}
    assert by_agent["B"]["chain_depth"] == 0


def test_liquidation_origin_agent_not_in_accounts_does_not_crash():
    """Edge case: origin=LIQUIDATION but the acting agent_id isn't a known
    account (defensive -- must not KeyError)."""
    b = _breaching_victim()
    book = Book(initial_price_ticks=10000)
    book.last_ticks = 9000

    event = {"origin": "LIQUIDATION", "agent_id": "ghost", "timestamp": 500}
    records = _run_post_batch_risk_check(event, book, _world({"B": b}), _FakeKernel(), [])

    by_agent = {r["agent_id"]: r for r in records}
    assert by_agent["B"]["chain_depth"] == 0
