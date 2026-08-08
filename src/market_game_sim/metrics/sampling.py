"""T501, T500b: Fixed-interval market/agent time series sampling.

Implements:

* :func:`sample_market_series` -- at each ``t = j * dt``, return the
  market snapshot (price, spread, depth, volume, ...).
* :func:`sample_agent_series` -- per-agent snapshot (wallet, position,
  equity, leverage).
* :func:`compute_burn_in` -- returns the cut-off timestamp for burn-in.

All integers, no floats.  Uses the event log to reconstruct state
(SC-006).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MarketSample:
    timestamp: int
    last_ticks: int | None
    mid_ticks: int | None
    spread_ticks: int | None
    bid_depth_k: int
    ask_depth_k: int
    volume_since_last: int
    cancel_count_since_last: int
    trade_count_since_last: int


@dataclass
class AgentSample:
    timestamp: int
    agent_id: str
    wallet_units: int
    position_units: int
    entry_notional_units: int
    margin_ratio_bp: int | None
    leverage_bp: int | None
    realized_pnl_units: int


def compute_burn_in(bar_ns: int, n_max: int, w_max: int) -> int:
    """Burn-in window in nanoseconds: ``max(n_max+1, w_max) * bar_ns``."""
    bars = max(n_max + 1, w_max)
    return bars * bar_ns


def sample_market_series(
    events: list[dict],
    sample_interval_ns: int,
    start_ns: int = 0,
    end_ns: int | None = None,
    depth_k: int = 10,
) -> list[MarketSample]:
    """Sample the market at ``t = j * sample_interval_ns``.

    For each sample point, walk the events up to that timestamp and
    take the latest known state.  Trades that occur *exactly* at the
    sample time are included; trades after are excluded (前值填充 per
    指标字典 §2).
    """
    sorted_events = sorted(events, key=lambda e: (e["timestamp"], e["transaction_seq"]))
    if end_ns is None:
        end_ns = max((e["timestamp"] for e in sorted_events), default=0) + 1
    out: list[MarketSample] = []
    last_ticks: int | None = None
    last_mid: int | None = None
    bid_depth = 0
    ask_depth = 0
    vol = 0
    cancels = 0
    trades = 0
    sample_ts = start_ns
    ev_idx = 0
    while sample_ts <= end_ns:
        while ev_idx < len(sorted_events) and sorted_events[ev_idx]["timestamp"] <= sample_ts:
            ev = sorted_events[ev_idx]
            et = ev.get("event_type", "")
            if et == "TRADE_SETTLE":
                last_ticks = ev.get("price_ticks")
                trades += 1
                vol += ev.get("quantity_units", 0)
            elif et == "ORDER_CANCELLED":
                cancels += 1
            elif et == "MARKET_DATA_PUBLISH":
                if ev.get("best_bid") is not None and ev.get("best_ask") is not None:
                    last_mid = (ev["best_bid"] + ev["best_ask"]) // 2
                    bid_depth = ev.get("bid_depth_k", 0)
                    ask_depth = ev.get("ask_depth_k", 0)
            ev_idx += 1
        spread = (
            (sorted_events[ev_idx - 1].get("best_ask") - sorted_events[ev_idx - 1].get("best_bid"))
            if ev_idx > 0
            and sorted_events[ev_idx - 1].get("event_type") == "MARKET_DATA_PUBLISH"
            and sorted_events[ev_idx - 1].get("best_bid") is not None
            and sorted_events[ev_idx - 1].get("best_ask") is not None
            else None
        )
        out.append(
            MarketSample(
                timestamp=sample_ts,
                last_ticks=last_ticks,
                mid_ticks=last_mid,
                spread_ticks=spread,
                bid_depth_k=bid_depth,
                ask_depth_k=ask_depth,
                volume_since_last=vol,
                cancel_count_since_last=cancels,
                trade_count_since_last=trades,
            )
        )
        vol = 0
        cancels = 0
        trades = 0
        sample_ts += sample_interval_ns
    return out


def sample_agent_series(
    events: list[dict],
    agent_id: str,
    sample_interval_ns: int,
    start_ns: int = 0,
    end_ns: int | None = None,
    mult: int = 1000,
) -> list[AgentSample]:
    """Per-agent time series.  Replays postings to compute wallet/position/equity."""
    sorted_events = sorted(events, key=lambda e: (e["timestamp"], e["transaction_seq"]))
    if end_ns is None:
        end_ns = max((e["timestamp"] for e in sorted_events), default=0) + 1
    wallet = 0
    position = 0
    entry = 0
    realized = 0
    samples: list[AgentSample] = []
    sample_ts = start_ns
    ev_idx = 0
    while sample_ts <= end_ns:
        while ev_idx < len(sorted_events) and sorted_events[ev_idx]["timestamp"] <= sample_ts:
            ev = sorted_events[ev_idx]
            for p in ev.get("postings") or []:
                if p.get("agent_id") != agent_id:
                    continue
                wallet += p.get("wallet_delta_units", 0)
                position += p.get("position_delta_units", 0)
                entry += p.get("entry_notional_delta_units", 0)
                realized += p.get("realized_pnl_delta_units", 0)
            ev_idx += 1
        last_ticks = None
        for prev in reversed(sorted_events[:ev_idx]):
            if prev.get("event_type") == "TRADE_SETTLE":
                last_ticks = prev.get("risk_mark_ticks")
                break
        notional = abs(position) * last_ticks * mult if last_ticks else 0
        re = wallet + position * (last_ticks or 0) * mult - entry
        margin_ratio = (re * 10_000 // notional) if notional > 0 else None
        leverage = (notional * 10_000 // re) if re > 0 else None
        samples.append(
            AgentSample(
                timestamp=sample_ts,
                agent_id=agent_id,
                wallet_units=wallet,
                position_units=position,
                entry_notional_units=entry,
                margin_ratio_bp=margin_ratio,
                leverage_bp=leverage,
                realized_pnl_units=realized,
            )
        )
        sample_ts += sample_interval_ns
    return samples


def filter_burn_in(samples: list, burn_in_ns: int) -> list:
    """Drop samples with ``timestamp < burn_in_ns`` (T500b)."""
    return [s for s in samples if s.timestamp >= burn_in_ns]


@dataclass
class ImpactSample:
    """T501 (指标字典 §3.4/§4): per-taker-order price impact + slippage.

    ``impact_bp`` is ``(成交加权均价 − 成交前中间价) / 成交前中间价`` in
    integer bp, sign-flipped to a positive-adverse convention (买方主动取
    正号，卖方主动取负号后统一为正值口径).  ``slippage_cash_units`` is the
    §4 agent-cost analogue in cash_units (``(成交价 − 下单时中间价) ×
    数量``, same positive-adverse convention) -- ``valuation_mark_before_
    half_ticks`` of the taker order's first fill stands in for "mid at
    submission time" since order arrival and its immediate fills share one
    transaction (no elapsed time between them in this synchronous engine).
    """

    order_id: str
    agent_id: str
    side: str
    quantity_units: int
    mid_before_ticks: int
    vwap_num_ticks_qty: int  # Σ(price_ticks * qty_units), denominator is quantity_units
    impact_bp: int
    slippage_cash_units: int


def compute_price_impact(events: list[dict], mult: int = 1000) -> list[ImpactSample]:
    """T501 (指标字典 §3.4): per-taker-order price impact, grouping all
    fills of the SAME ``taker_order_id`` (a marketable/crossing order can
    walk multiple book levels, producing multiple TRADE_SETTLE records).

    Does not implement the §3.4 non-linearity bucket regression
    (``impact ~ Q^γ``) -- that is a cross-order statistical analysis
    belonging to the reporting/study layer, not a per-order metric.
    """
    sorted_events = sorted(
        events, key=lambda e: (e["timestamp"], e["transaction_seq"], e.get("record_index", 0))
    )
    groups: dict[str, dict] = {}
    order: list[str] = []
    for e in sorted_events:
        if e.get("event_type") != "TRADE_SETTLE":
            continue
        taker_order_id = e.get("taker_order_id")
        if not taker_order_id:
            continue
        taker_posting = next(
            (p for p in e.get("postings", []) if p.get("role") == "TAKER"),
            None,
        )
        if taker_posting is None:
            continue
        price = e.get("price_ticks", 0)
        qty = e.get("quantity_units", 0)
        if taker_order_id not in groups:
            order.append(taker_order_id)
            mid_before = (e.get("valuation_mark_before_half_ticks", 0) or 0) // 2
            side = "BUY" if taker_posting.get("position_delta_units", 0) > 0 else "SELL"
            groups[taker_order_id] = {
                "agent_id": taker_posting.get("agent_id"),
                "side": side,
                "mid_before_ticks": mid_before,
                "quantity_units": 0,
                "vwap_num_ticks_qty": 0,
            }
        g = groups[taker_order_id]
        g["quantity_units"] += qty
        g["vwap_num_ticks_qty"] += price * qty

    out: list[ImpactSample] = []
    for order_id in order:
        g = groups[order_id]
        mid_before = g["mid_before_ticks"]
        qty = g["quantity_units"]
        vwap_num = g["vwap_num_ticks_qty"]
        if mid_before <= 0 or qty <= 0:
            continue
        signed_diff_bp = ((vwap_num - mid_before * qty) * 10_000) // (mid_before * qty)
        signed_slippage = (vwap_num - mid_before * qty) * mult
        if g["side"] == "SELL":
            signed_diff_bp = -signed_diff_bp
            signed_slippage = -signed_slippage
        out.append(
            ImpactSample(
                order_id=order_id,
                agent_id=g["agent_id"],
                side=g["side"],
                quantity_units=qty,
                mid_before_ticks=mid_before,
                vwap_num_ticks_qty=vwap_num,
                impact_bp=signed_diff_bp,
                slippage_cash_units=signed_slippage,
            )
        )
    return out
