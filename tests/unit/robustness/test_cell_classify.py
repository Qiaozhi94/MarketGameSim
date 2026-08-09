"""T204 (指标字典 §6, 退化 §4): mutually-exclusive run classification tests.

Positive + negative + multi-record cases per CLAUDE.md: every category
reachable, each run maps to exactly one category.
"""

from __future__ import annotations

from market_game_sim.metrics.liquidation import RunClassification
from market_game_sim.robustness.cell_classify import RunCategory, classify_cell


def _trade_events(ticks):
    return [{"event_type": "TRADE_SETTLE", "price_ticks": t} for t in ticks]


class TestCategoryPrecedence:
    def test_technical_invalid_first(self):
        rc = RunClassification(is_technical_invalid=True, technical_invalid_code="TI-3")
        c = classify_cell(rc, _trade_events([10000, 10001]), initial_price=10000)
        assert c.category is RunCategory.TECHNICAL_INVALID
        assert c.code == "TI-3"

    def test_economic_endpoint_beats_price_path(self):
        rc = RunClassification(is_economic_endpoint=True, economic_endpoint_codes=["EV-1"])
        # even a flat/diverged path is trumped by EV
        c = classify_cell(rc, _trade_events([10000, 1]), initial_price=10000)
        assert c.category is RunCategory.ECONOMIC_ENDPOINT
        assert "EV-1" in c.code


class TestPricePath:
    def test_no_events_locked(self):
        c = classify_cell(RunClassification(), [], initial_price=10000)
        assert c.category is RunCategory.LOCKED

    def test_flat_path_locked(self):
        c = classify_cell(
            RunClassification(), _trade_events([10000, 10000, 10000]), initial_price=10000
        )
        assert c.category is RunCategory.LOCKED

    def test_diverged(self):
        # price 1e6 vs initial 1e4 -> ln(100) ≈ 4.6 > ln(10) bound
        c = classify_cell(
            RunClassification(), _trade_events([10000, 20000, 1_000_000]), initial_price=10000
        )
        assert c.category is RunCategory.DIVERGED

    def test_oscillating(self):
        # >= window(20) points with near-total sign reversal -> oscillating
        ticks = [10000 + (10 if i % 2 else 0) for i in range(22)]
        c = classify_cell(RunClassification(), _trade_events(ticks), initial_price=10000)
        assert c.category is RunCategory.OSCILLATING

    def test_completed_fallback(self):
        # monotonic mild drift, within bounds, no oscillation
        ticks = [10000, 10002, 10005, 10008, 10010]
        c = classify_cell(RunClassification(), _trade_events(ticks), initial_price=10000)
        assert c.category is RunCategory.COMPLETED


class TestMutualExclusivity:
    def test_each_run_one_category(self):
        # a battery of runs, none classified twice
        runs = [
            RunClassification(is_technical_invalid=True, technical_invalid_code="TI-1"),
            RunClassification(is_economic_endpoint=True, economic_endpoint_codes=["EV-3"]),
            RunClassification(),
        ]
        cats = [
            classify_cell(rc, _trade_events([10000, 10001]), initial_price=10000).category
            for rc in runs
        ]
        assert len(cats) == 3
        assert len(set(cats)) == 3  # all distinct -> mutually exclusive
