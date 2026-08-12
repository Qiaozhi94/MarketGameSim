"""T203 (FR-020): K-line view from event log.

Implements metrics-dictionary §1.9/§1.9.1: bars are logical-time windows
``[k*bar_ns, (k+1)*bar_ns)`` (left-closed, right-open), only COMPLETED bars
are emitted, empty bars carry the previous close, and bars before the first
trade carry ``initial_price``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_BAR_NS = 60 * 10**9  # 60s (metrics-dictionary §1.9)


@dataclass
class Kline:
    start_ns: int
    open: int
    high: int
    low: int
    close: int
    volume: int
    trade_count: int


def build_klines(
    events: list[dict[str, Any]],
    *,
    period_ns: int,
    initial_price_ticks: int,
) -> list[Kline]:
    """Build the completed-bar K-line series.

    ``period_ns`` is the bar period in logical nanoseconds (e.g. 5 min per
    metrics-dictionary §1.9); ``initial_price_ticks`` is used for bars
    before the first trade.  ``period_ns`` must be a positive integer --
    ``<= 0`` raises :class:`ValueError` (round-2 review F-F).

    Trades are binned in a single pass keyed by ``timestamp // period_ns``
    instead of rescanning all trades for every bar.
    """
    if not isinstance(period_ns, int) or isinstance(period_ns, bool) or period_ns <= 0:
        raise ValueError(f"period_ns must be a positive integer, got {period_ns!r}")
    if not events:
        return []

    end_ns = max(e["timestamp"] for e in events)
    if end_ns < period_ns:
        return []

    last_completed = end_ns // period_ns - 1
    if last_completed < 0:
        return []

    bins: dict[int, list[tuple[int, int, int]]] = {}
    for e in events:
        if e.get("event_type") != "TRADE_SETTLE":
            continue
        price = e.get("price_ticks")
        if price is None:
            continue
        ts = e["timestamp"]
        qty = e.get("quantity_units", 0)
        bin_idx = ts // period_ns
        bins.setdefault(bin_idx, []).append((ts, price, qty))

    for trades in bins.values():
        trades.sort(key=lambda t: t[0])

    prev_close = initial_price_ticks
    out: list[Kline] = []

    for k in range(last_completed + 1):
        bar_trades = bins.get(k)
        if bar_trades:
            open_p = bar_trades[0][1]
            high = max(t[1] for t in bar_trades)
            low = min(t[1] for t in bar_trades)
            close = bar_trades[-1][1]
            volume = sum(t[2] for t in bar_trades)
            prev_close = close
        else:
            open_p = high = low = close = prev_close
            volume = 0
        out.append(
            Kline(
                start_ns=k * period_ns,
                open=open_p,
                high=high,
                low=low,
                close=close,
                volume=volume,
                trade_count=len(bar_trades) if bar_trades else 0,
            )
        )

    return out
