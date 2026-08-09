"""T605 (KPI-011): zero-sum declaration + five-channel tests.

Positive + negative + multi-record cases per CLAUDE.md: identity declared,
distribution present, all five channels accumulated, no channel skipped.
"""

from __future__ import annotations

from market_game_sim.ledger.account import Account
from market_game_sim.robustness.zero_sum import (
    CHANNELS,
    accumulate_channels,
    build_zero_sum_report,
)


def _trade(posting):
    return {
        "event_type": "TRADE_SETTLE",
        "trade_id": "t1",
        "price_ticks": 9990,
        "valuation_mark_before_half_ticks": 19980,
        "valuation_mark_after_half_ticks": 19980,
        "postings": [posting],
    }


def _posting():
    return {
        "posting_type": "TRADE_POSTING",
        "agent_id": "a1",
        "wallet_delta_units": -999000,
        "position_delta_units": 1000,
        "entry_notional_delta_units": 9990000000,
        "fee_delta_units": 999000,
        "position_after_units": 1000,
    }


class TestAccumulateChannels:
    def test_empty_events_zero_channels(self):
        c = accumulate_channels([])
        assert c.as_dict() == {ch: 0 for ch in CHANNELS}

    def test_single_trade_accumulates(self):
        c = accumulate_channels([_trade(_posting())])
        d = c.as_dict()
        assert set(d) == set(CHANNELS)
        assert d["fees"] == 999000  # the side's fee

    def test_multi_trade_sums(self):
        c = accumulate_channels([_trade(_posting()), _trade(_posting())])
        assert c.fees == 2 * 999000

    def test_non_trade_events_ignored(self):
        events = [{"event_type": "AGENT_DECIDE"}, {"event_type": "SNAPSHOT"}]
        assert accumulate_channels(events).as_dict() == {ch: 0 for ch in CHANNELS}


class TestBuildZeroSumReport:
    def test_full_report(self):
        accounts = {"a1": Account(agent_id="a1", wallet_units=10**14 - 999000, position_units=1000)}
        baseline = {"a1": 10**14}
        r = build_zero_sum_report(
            accounts,
            baseline,
            exchange_fee_units=999000,
            exchange_risk_pnl_units=0,
            events=[_trade(_posting())],
        )
        assert set(r.channels) == set(CHANNELS)
        assert "恒等式" in r.declaration_text
        assert "不是研究发现" in r.declaration_text
        assert r.per_agent_pnl_units["a1"] == -999000

    def test_distribution_present(self):
        accounts = {
            "a1": Account(agent_id="a1", wallet_units=10**14 - 100, position_units=0),
            "a2": Account(agent_id="a2", wallet_units=10**14 + 100, position_units=0),
        }
        baseline = {"a1": 10**14, "a2": 10**14}
        r = build_zero_sum_report(accounts, baseline, 0, 0, events=[])
        assert r.per_agent_pnl_units == {"a1": -100, "a2": 100}
