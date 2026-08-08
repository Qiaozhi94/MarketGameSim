"""T701: BENCH-001 coverage assertions (README.md §1.1).

A benchmark run must prove it actually walked the paths it claims to
exercise (liquidation, chained liquidation, partial fill, cancel,
one-sided book) -- otherwise the wall-clock number is meaningless
(README.md's "任一断言不满足即判定该基准无效").
"""

from __future__ import annotations

from dataclasses import dataclass

from market_game_sim.metrics.liquidation import LiquidationMetrics

DEFAULT_THRESHOLDS: dict[str, int] = {
    "min_liquidations": 1,
    "min_chained_liquidations": 1,
    "min_partial_fills": 1,
    "min_cancels": 1,
    "min_one_sided_book_events": 1,
}


@dataclass
class CoverageAssertions:
    liquidations: int
    chained_liquidations: int
    partial_fills: int
    cancels: int
    one_sided_book_events: int

    def failures(self, thresholds: dict[str, int] = DEFAULT_THRESHOLDS) -> list[str]:
        """Names + shortfall for every assertion below its threshold; empty
        list means the benchmark run is valid (README §1.1)."""
        checks = (
            ("min_liquidations", self.liquidations),
            ("min_chained_liquidations", self.chained_liquidations),
            ("min_partial_fills", self.partial_fills),
            ("min_cancels", self.cancels),
            ("min_one_sided_book_events", self.one_sided_book_events),
        )
        return [
            f"{name}: got {value}, need >= {thresholds.get(name, 1)}"
            for name, value in checks
            if value < thresholds.get(name, 1)
        ]

    def is_valid(self, thresholds: dict[str, int] = DEFAULT_THRESHOLDS) -> bool:
        return not self.failures(thresholds)


def count_partial_fills(events: list[dict]) -> int:
    """An order counts as partially filled when it submitted with
    ``quantity_units`` > 0, was accepted, and the sum of TRADE_SETTLE
    quantity matched against its ``order_id`` (as either maker or taker) is
    strictly between 0 and the submitted quantity (指标字典/event-schema §
    "挂入量 = ORDER_ARRIVAL.quantity_units − ΣTRADE_SETTLE.quantity_units")."""
    submitted: dict[str, int] = {}
    filled: dict[str, int] = {}
    for e in events:
        et = e.get("event_type")
        if et == "ORDER_ARRIVAL" and e.get("action") == "SUBMIT" and e.get("accepted"):
            oid = e.get("order_id")
            if oid:
                submitted[oid] = e.get("quantity_units", 0)
        elif et == "TRADE_SETTLE":
            qty = e.get("quantity_units", 0)
            for key in ("taker_order_id", "maker_order_id"):
                oid = e.get(key)
                if oid:
                    filled[oid] = filled.get(oid, 0) + qty
    return sum(1 for oid, qty in submitted.items() if 0 < filled.get(oid, 0) < qty)


def count_cancels(events: list[dict]) -> int:
    return sum(1 for e in events if e.get("event_type") == "ORDER_CANCELLED")


def count_one_sided_book_events(events: list[dict]) -> int:
    """A MARKET_DATA_PUBLISH where exactly one side has no resting depth
    (退化状态 §4 一侧空簿), not both (fully empty book is a different, more
    degenerate state, and both-sides-present is the normal case)."""
    count = 0
    for e in events:
        if e.get("event_type") != "MARKET_DATA_PUBLISH":
            continue
        bid_empty = e.get("best_bid") is None
        ask_empty = e.get("best_ask") is None
        if bid_empty != ask_empty:
            count += 1
    return count


def compute_coverage(
    events: list[dict], liquidation_metrics: LiquidationMetrics
) -> CoverageAssertions:
    chained = sum(
        count for depth, count in liquidation_metrics.chain_depth_counts.items() if depth >= 1
    )
    return CoverageAssertions(
        liquidations=liquidation_metrics.total_liquidations,
        chained_liquidations=chained,
        partial_fills=count_partial_fills(events),
        cancels=count_cancels(events),
        one_sided_book_events=count_one_sided_book_events(events),
    )
