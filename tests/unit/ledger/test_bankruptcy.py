"""T206: Two-step bankruptcy write-off (账户合同 §5)."""

from __future__ import annotations

from market_game_sim.ledger.account import Account, AccountState
from market_game_sim.ledger.bankruptcy import (
    apply_write_off,
    find_breached,
    write_off_postings,
)


def test_find_breached_filters_to_zero_position_negative_wallet():
    accounts = {
        "A": Account(agent_id="A", wallet_units=-100),
        "B": Account(agent_id="B", wallet_units=100),
        "C": Account(agent_id="C", wallet_units=-50, position_units=10),
        "D": Account(agent_id="D", wallet_units=0),
    }
    assert find_breached(accounts) == ["A"]


def test_find_breached_returns_sorted():
    accounts = {
        "Z": Account(agent_id="Z", wallet_units=-10),
        "A": Account(agent_id="A", wallet_units=-1),
        "M": Account(agent_id="M", wallet_units=-5),
    }
    assert find_breached(accounts) == ["A", "M", "Z"]


def test_find_breached_empty_when_none_breached():
    accounts = {"A": Account(agent_id="A", wallet_units=100)}
    assert find_breached(accounts) == []


def test_write_off_postings_breached_account():
    """Build WRITE_OFF_POSTING pair (ACCOUNT, EXCHANGE_RISK) per 事件 Schema §4.2.3."""
    acct = Account(agent_id="A", wallet_units=-1000)
    postings = write_off_postings("A", acct)
    assert len(postings) == 2
    assert postings[0]["posting_type"] == "WRITE_OFF_POSTING"
    assert postings[0]["role"] == "ACCOUNT"
    assert postings[0]["agent_id"] == "A"
    assert postings[0]["wallet_delta_units"] == 1000
    assert postings[0]["wallet_after_units"] == 0
    assert postings[1]["role"] == "EXCHANGE_RISK"
    assert postings[1]["agent_id"] is None
    assert postings[1]["risk_pnl_delta_units"] == -1000
    # The exchange account's *_after fields must be null (not 0)
    assert postings[1]["wallet_after_units"] is None
    assert postings[1]["position_after_units"] is None
    assert postings[1]["entry_notional_after_units"] is None


def test_write_off_postings_rejects_non_negative_wallet():
    acct = Account(agent_id="A", wallet_units=100)
    try:
        write_off_postings("A", acct)
    except ValueError as exc:
        assert "non-negative" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_apply_write_off_zeroes_wallet_and_adds_to_risk():
    accounts = {
        "A": Account(agent_id="A", wallet_units=-1000),
        "B": Account(agent_id="B", wallet_units=500),
        "C": Account(agent_id="C", wallet_units=-50, position_units=10),
    }
    new_risk = apply_write_off(accounts, exchange_risk_pnl_units=0)
    assert accounts["A"].wallet_units == 0
    assert accounts["A"].state == AccountState.LIQUIDATED
    assert new_risk == -1000
    assert accounts["B"].wallet_units == 500
    assert accounts["B"].state == AccountState.ACTIVE
    assert accounts["C"].wallet_units == -50
    assert accounts["C"].state == AccountState.ACTIVE
