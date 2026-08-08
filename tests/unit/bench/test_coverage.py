"""T701: BENCH-001 coverage assertion tests."""

from __future__ import annotations

from market_game_sim.bench.coverage import (
    DEFAULT_THRESHOLDS,
    CoverageAssertions,
    compute_coverage,
    count_cancels,
    count_one_sided_book_events,
    count_partial_fills,
)
from market_game_sim.metrics.liquidation import LiquidationMetrics


def _submit(order_id: str, qty: int, accepted: bool = True) -> dict:
    return {
        "event_type": "ORDER_ARRIVAL",
        "action": "SUBMIT",
        "order_id": order_id,
        "quantity_units": qty,
        "accepted": accepted,
    }


def _trade(taker_order_id: str | None, maker_order_id: str | None, qty: int) -> dict:
    e = {"event_type": "TRADE_SETTLE", "quantity_units": qty}
    if taker_order_id:
        e["taker_order_id"] = taker_order_id
    if maker_order_id:
        e["maker_order_id"] = maker_order_id
    return e


class TestCountPartialFills:
    def test_fully_filled_order_is_not_partial(self):
        events = [_submit("o1", 100), _trade("o1", None, 100)]
        assert count_partial_fills(events) == 0

    def test_partially_filled_taker_order_counts(self):
        events = [_submit("o1", 100), _trade("o1", None, 40)]
        assert count_partial_fills(events) == 1

    def test_partially_filled_maker_order_counts(self):
        events = [_submit("m1", 100), _trade(None, "m1", 30)]
        assert count_partial_fills(events) == 1

    def test_unfilled_order_is_not_counted_as_partial(self):
        """A resting order with zero fills isn't "partial" -- it's just
        resting; only 0 < filled < submitted counts (指标字典 formula)."""
        events = [_submit("o1", 100)]
        assert count_partial_fills(events) == 0

    def test_multiple_fills_summed_before_comparing(self):
        events = [_submit("o1", 100), _trade("o1", None, 30), _trade("o1", None, 20)]
        assert count_partial_fills(events) == 1  # 50 < 100

    def test_rejected_submit_not_counted(self):
        events = [_submit("o1", 100, accepted=False)]
        assert count_partial_fills(events) == 0


class TestCountCancels:
    def test_counts_order_cancelled_events(self):
        events = [
            {"event_type": "ORDER_CANCELLED"},
            {"event_type": "ORDER_CANCELLED"},
            {"event_type": "TRADE_SETTLE"},
        ]
        assert count_cancels(events) == 2

    def test_zero_when_none_present(self):
        assert count_cancels([{"event_type": "TRADE_SETTLE"}]) == 0


class TestCountOneSidedBookEvents:
    def test_one_sided_bid_only_counts(self):
        events = [{"event_type": "MARKET_DATA_PUBLISH", "best_bid": 100, "best_ask": None}]
        assert count_one_sided_book_events(events) == 1

    def test_one_sided_ask_only_counts(self):
        events = [{"event_type": "MARKET_DATA_PUBLISH", "best_bid": None, "best_ask": 100}]
        assert count_one_sided_book_events(events) == 1

    def test_both_sides_present_does_not_count(self):
        events = [{"event_type": "MARKET_DATA_PUBLISH", "best_bid": 99, "best_ask": 100}]
        assert count_one_sided_book_events(events) == 0

    def test_both_sides_empty_does_not_count(self):
        """Fully empty book is a distinct, more degenerate state -- must not
        be conflated with "one-sided"."""
        events = [{"event_type": "MARKET_DATA_PUBLISH", "best_bid": None, "best_ask": None}]
        assert count_one_sided_book_events(events) == 0


class TestCoverageAssertions:
    def _full(self) -> CoverageAssertions:
        return CoverageAssertions(
            liquidations=1,
            chained_liquidations=1,
            partial_fills=1,
            cancels=1,
            one_sided_book_events=1,
        )

    def test_all_thresholds_met_is_valid(self):
        assert self._full().is_valid()
        assert self._full().failures() == []

    def test_missing_one_dimension_fails_with_message(self):
        cov = CoverageAssertions(
            liquidations=0,
            chained_liquidations=1,
            partial_fills=1,
            cancels=1,
            one_sided_book_events=1,
        )
        assert not cov.is_valid()
        failures = cov.failures()
        assert len(failures) == 1
        assert "min_liquidations" in failures[0]

    def test_custom_thresholds_override_defaults(self):
        cov = CoverageAssertions(
            liquidations=5,
            chained_liquidations=1,
            partial_fills=1,
            cancels=1,
            one_sided_book_events=1,
        )
        assert cov.is_valid({**DEFAULT_THRESHOLDS, "min_liquidations": 10}) is False
        assert cov.is_valid({**DEFAULT_THRESHOLDS, "min_liquidations": 3}) is True


class TestComputeCoverage:
    def test_chained_liquidations_only_counts_depth_gte_1(self):
        metrics = LiquidationMetrics(total_liquidations=3, chain_depth_counts={0: 2, 1: 1})
        cov = compute_coverage([], metrics)
        assert cov.liquidations == 3
        assert cov.chained_liquidations == 1

    def test_no_liquidations_gives_zero_chained(self):
        cov = compute_coverage([], LiquidationMetrics())
        assert cov.liquidations == 0
        assert cov.chained_liquidations == 0

    def test_aggregates_all_five_dimensions_from_a_mixed_event_log(self):
        events = [
            _submit("o1", 100),
            _trade("o1", None, 40),
            {"event_type": "ORDER_CANCELLED"},
            {"event_type": "MARKET_DATA_PUBLISH", "best_bid": 100, "best_ask": None},
        ]
        metrics = LiquidationMetrics(total_liquidations=1, chain_depth_counts={2: 1})
        cov = compute_coverage(events, metrics)
        assert cov.liquidations == 1
        assert cov.chained_liquidations == 1
        assert cov.partial_fills == 1
        assert cov.cancels == 1
        assert cov.one_sided_book_events == 1
        assert cov.is_valid()
