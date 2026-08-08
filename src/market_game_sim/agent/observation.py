"""T401: Information set for an agent (代理策略 §1, 指标字典 §1.9).

Each agent's information set contains:
* Best bid/ask + k-tick depth
* Trade increments since last observation
* Completed K-lines (not the in-progress one)
* Own account snapshot (wallet, position, entry, reserved, margin, open orders)

The information set is what the agent sees -- not the engine's true state.
Missing values (cold start, single-sided book) follow 代理策略 §3.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Bar:
    open: int
    high: int
    low: int
    close: int
    volume: int
    trade_count: int


@dataclass
class Trade:
    price_ticks: int
    quantity_units: int
    taker_side: str
    timestamp: int = 0


@dataclass
class InformationSet:
    agent_id: str
    observed_at: int
    best_bid: int | None
    best_ask: int | None
    bid_depth_k: int
    ask_depth_k: int
    last_ticks: int | None
    trades: list[Trade] = field(default_factory=list)
    bars: list[Bar] = field(default_factory=list)
    wallet_units: int = 0
    position_units: int = 0
    entry_notional_units: int = 0
    reserved_units: int = 0
    margin_ratio_bp: int | None = None
    valuation_mark_half_ticks: int | None = None
    open_orders: list[dict] = field(default_factory=list)

    def book_signal(self) -> int:
        """``(bid_depth - ask_depth) / (bid_depth + ask_depth)`` in [-1, 1].

        Single-sided -> ±1.  Both empty -> 0 (代理策略 §3.1).
        """
        if self.bid_depth_k == 0 and self.ask_depth_k == 0:
            return 0
        if self.ask_depth_k == 0:
            return 1
        if self.bid_depth_k == 0:
            return -1
        return (self.bid_depth_k - self.ask_depth_k) // (self.bid_depth_k + self.ask_depth_k)

    def herding_signal(self, window: list[Bar]) -> int:
        """``(buy_vol - sell_vol) / total_vol`` in [-1, 1] across the window.

        The window is the bar sequence (excludes the in-progress one).
        Zero volume -> 0 (代理策略 §3.1).
        """
        if not window:
            return 0
        buy = sum(b.volume for b in window if b.close >= b.open)
        sell = sum(b.volume for b in window if b.close < b.open)
        total = buy + sell
        if total == 0:
            return 0
        return (buy - sell) // total


def aggregate_bars(trades: list[Trade], bar_ns: int, now_ns: int) -> list[Bar]:
    """Aggregate trade history into completed K-lines (指标字典 §1.9).

    Each trade is placed in the bar whose ``[k * bar_ns, (k+1) * bar_ns)``
    range it falls in.  Bars with no trades are not emitted (we only emit
    bars that have at least one trade, since the agent needs to compute
    momentum/reversion from real prices).  The bar aggregation
    "no trade -> copy close" applies in metrics sampling, not here.
    """
    if bar_ns <= 0:
        raise ValueError(f"bar_ns must be positive, got {bar_ns}")
    by_bar: dict[int, list[Trade]] = {}
    for tr in trades:
        bar_idx = tr.timestamp // bar_ns if tr.timestamp is not None else now_ns // bar_ns
        by_bar.setdefault(bar_idx, []).append(tr)
    out: list[Bar] = []
    for bar_idx in sorted(by_bar):
        ts = by_bar[bar_idx]
        prices = [t.price_ticks for t in ts]
        out.append(
            Bar(
                open=prices[0],
                high=max(prices),
                low=min(prices),
                close=prices[-1],
                volume=sum(t.quantity_units for t in ts),
                trade_count=len(ts),
            )
        )
    return out
