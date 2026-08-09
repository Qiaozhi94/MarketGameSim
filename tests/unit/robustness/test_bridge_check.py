"""T603 (KPI-009): per-run bridge residual check tests.

Positive + negative + multi-record cases per CLAUDE.md: a clean run passes,
a single non-zero residual is reported and disqualifies the run.
"""

from __future__ import annotations

from market_game_sim.robustness.bridge_check import check_bridge_residuals


def _clean_trade():
    return {
        "event_type": "TRADE_SETTLE",
        "trade_id": "t1",
        "price_ticks": 9990,
        "valuation_mark_before_half_ticks": 19980,
        "valuation_mark_after_half_ticks": 19980,
        "postings": [
            {
                "posting_type": "TRADE_POSTING",
                "agent_id": "a1",
                "wallet_delta_units": -999000,
                "position_delta_units": 1000,
                "entry_notional_delta_units": 9990000000,
                "fee_delta_units": 999000,
                "position_after_units": 1000,
            }
        ],
    }


def _run(run_id="r1", trades=None):
    return {"run_id": run_id, "events": trades or [_clean_trade()]}


class TestCheckBridgeResiduals:
    def test_clean_run_passes(self):
        result = check_bridge_residuals([_run()])
        assert result.all_zero
        assert result.runs_checked == 1

    def test_multi_run_all_zero(self):
        result = check_bridge_residuals([_run("r1"), _run("r2")])
        assert result.all_zero
        assert result.runs_checked == 2

    def test_empty_runs(self):
        result = check_bridge_residuals([])
        assert result.all_zero
        assert result.runs_checked == 0

    def test_corrupt_price_disqualifies(self):
        # a trade whose price is inconsistent with the valuation marks has a
        # non-zero bridge residual
        trade = _clean_trade()
        trade["price_ticks"] = 19980  # inconsistent with half-ticks 19980/19980
        result = check_bridge_residuals([_run("r1", [trade])])
        assert not result.all_zero
        assert result.violations[0].run_id == "r1"
