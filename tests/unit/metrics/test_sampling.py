"""§2.9/T501 regression: compute_price_impact (指标字典 §3.4/§4).

Round reviews found T501 marked [x] in tasks.md (fixed-interval sampling
implemented) but grep for "impact"/"slippage" across metrics/ was zero --
the price-impact/slippage half of §2—§4's declared scope was never
implemented.  These tests cover the new compute_price_impact function
directly against hand-built TRADE_SETTLE records (no engine dependency,
deterministic).
"""

from __future__ import annotations

from market_game_sim.metrics.sampling import compute_price_impact, sample_market_series

MULT = 1000


def _trade(
    taker_order_id: str,
    price: int,
    qty: int,
    vm_before_half: int,
    taker_side: str,
    taker_agent: str = "T",
    tx: int = 1,
    idx: int = 0,
) -> dict:
    delta = qty if taker_side == "BUY" else -qty
    return {
        "event_type": "TRADE_SETTLE",
        "timestamp": tx,
        "transaction_seq": tx,
        "record_index": idx,
        "taker_order_id": taker_order_id,
        "price_ticks": price,
        "quantity_units": qty,
        "valuation_mark_before_half_ticks": vm_before_half,
        "postings": [
            {"role": "MAKER", "agent_id": "M", "position_delta_units": -delta},
            {"role": "TAKER", "agent_id": taker_agent, "position_delta_units": delta},
        ],
    }


def test_single_fill_buy_positive_impact():
    """mid_before=10000 (half=20000), fills @10050 -> adverse (paid above
    mid) -> positive impact_bp, positive slippage."""
    events = [_trade("t1", price=10050, qty=100, vm_before_half=20000, taker_side="BUY")]
    samples = compute_price_impact(events, mult=MULT)
    assert len(samples) == 1
    s = samples[0]
    assert s.order_id == "t1"
    assert s.side == "BUY"
    assert s.mid_before_ticks == 10000
    assert s.impact_bp == 50  # (10050-10000)/10000 * 10000 = 50bp
    assert s.slippage_cash_units == (10050 - 10000) * 100 * MULT


def test_single_fill_sell_sign_flipped_to_positive_when_adverse():
    """Seller receiving BELOW mid is adverse -> must still be reported as
    a POSITIVE impact_bp/slippage (统一为正值口径), not negative."""
    events = [_trade("t1", price=9950, qty=100, vm_before_half=20000, taker_side="SELL")]
    samples = compute_price_impact(events, mult=MULT)
    s = samples[0]
    assert s.side == "SELL"
    assert s.impact_bp == 50
    assert s.slippage_cash_units == (10000 - 9950) * 100 * MULT


def test_sell_favorable_fill_gives_negative_impact():
    """Negative/contrast case: a seller filled ABOVE mid got a favorable
    price -- impact must come out negative (not clamped to 0), proving the
    sign flip isn't just "always positive"."""
    events = [_trade("t1", price=10050, qty=100, vm_before_half=20000, taker_side="SELL")]
    samples = compute_price_impact(events, mult=MULT)
    assert samples[0].impact_bp == -50

    events_buy = [_trade("t2", price=9950, qty=100, vm_before_half=20000, taker_side="BUY")]
    samples_buy = compute_price_impact(events_buy, mult=MULT)
    assert samples_buy[0].impact_bp == -50


def test_multi_level_crossing_groups_by_taker_order_id_vwap():
    """A taker order that walked two book levels produces two TRADE_SETTLE
    records sharing one taker_order_id -- must be grouped into ONE
    ImpactSample with a volume-weighted price, using only the FIRST fill's
    mid_before (later fills' own valuation_mark_before is a mid-execution
    value, not "before this order started")."""
    events = [
        _trade("t1", price=10000, qty=1000, vm_before_half=19990, taker_side="BUY", idx=0),
        _trade("t1", price=10100, qty=500, vm_before_half=20200, taker_side="BUY", idx=1),
    ]
    samples = compute_price_impact(events, mult=MULT)
    assert len(samples) == 1
    s = samples[0]
    assert s.mid_before_ticks == 19990 // 2  # from the FIRST fill only
    assert s.quantity_units == 1500
    expected_vwap_num = 10000 * 1000 + 10100 * 500
    assert s.vwap_num_ticks_qty == expected_vwap_num


def test_two_distinct_orders_produce_two_samples():
    events = [
        _trade("t1", price=10050, qty=100, vm_before_half=20000, taker_side="BUY", tx=1),
        _trade("t2", price=9900, qty=200, vm_before_half=20000, taker_side="SELL", tx=2),
    ]
    samples = compute_price_impact(events, mult=MULT)
    assert {s.order_id for s in samples} == {"t1", "t2"}


def test_zero_mid_before_skipped_no_crash():
    events = [_trade("t1", price=10050, qty=100, vm_before_half=0, taker_side="BUY")]
    samples = compute_price_impact(events, mult=MULT)
    assert samples == []


def test_events_without_taker_order_id_ignored():
    events = [
        {
            "event_type": "TRADE_SETTLE",
            "timestamp": 1,
            "transaction_seq": 1,
            "record_index": 0,
            "postings": [],
        }
    ]
    assert compute_price_impact(events, mult=MULT) == []


# ---------------------------------------------------------------------------
# sample_market_series -- 指标字典 §2 equal-interval sampling.
#
# T606 (KPI-005) is the first caller wiring this into the production report
# path (experiment/runner.py::build_market_validation_report); until now it
# had zero direct test coverage despite being declared implemented (T501/
# T500b), so add regression tests before relying on it.
# ---------------------------------------------------------------------------


def _mdp(ts: int, best_bid: int, best_ask: int, tx: int, bid_depth=3, ask_depth=3) -> dict:
    return {
        "event_type": "MARKET_DATA_PUBLISH",
        "timestamp": ts,
        "transaction_seq": tx,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "bid_depth_k": bid_depth,
        "ask_depth_k": ask_depth,
    }


def _settle(ts: int, price: int, qty: int, tx: int) -> dict:
    return {
        "event_type": "TRADE_SETTLE",
        "timestamp": ts,
        "transaction_seq": tx,
        "price_ticks": price,
        "quantity_units": qty,
    }


def test_sample_market_series_forward_fills_price_between_trades():
    events = [_settle(ts=0, price=100, qty=5, tx=1)]
    samples = sample_market_series(events, sample_interval_ns=1000, end_ns=2000)
    assert [s.timestamp for s in samples] == [0, 1000, 2000]
    assert [s.last_ticks for s in samples] == [100, 100, 100]
    # only the first sample's interval actually contained the trade
    assert [s.trade_count_since_last for s in samples] == [1, 0, 0]
    assert [s.volume_since_last for s in samples] == [5, 0, 0]


def test_sample_market_series_price_undefined_before_first_trade():
    events = [_settle(ts=1500, price=100, qty=1, tx=1)]
    samples = sample_market_series(events, sample_interval_ns=1000, end_ns=2000)
    assert [s.last_ticks for s in samples] == [None, None, 100]
    assert [s.trade_count_since_last for s in samples] == [0, 0, 1]


def test_sample_market_series_counts_multiple_trades_within_one_interval_and_resets():
    events = [
        _settle(ts=100, price=100, qty=1, tx=1),
        _settle(ts=200, price=101, qty=2, tx=2),
        _settle(ts=1500, price=102, qty=9, tx=3),
    ]
    samples = sample_market_series(events, sample_interval_ns=1000, end_ns=2000)
    # sample at t=0 sees nothing yet (both trades are at t=100/200 > 0);
    # sample at t=1000 picks up both trades in one window; t=2000 picks up
    # the third trade in its own window.
    assert [s.trade_count_since_last for s in samples] == [0, 2, 1]
    assert [s.volume_since_last for s in samples] == [0, 3, 9]
    assert [s.last_ticks for s in samples] == [None, 101, 102]


def test_sample_market_series_spread_from_market_data_publish():
    events = [_mdp(ts=0, best_bid=98, best_ask=102, tx=1)]
    samples = sample_market_series(events, sample_interval_ns=1000, end_ns=1000)
    assert samples[0].spread_ticks == 4
    assert samples[0].mid_ticks == 100
    assert samples[0].bid_depth_k == 3
    assert samples[0].ask_depth_k == 3


def test_sample_market_series_spread_undefined_when_no_market_data_yet():
    events = [_settle(ts=0, price=100, qty=1, tx=1)]
    samples = sample_market_series(events, sample_interval_ns=1000, end_ns=1000)
    assert all(s.spread_ticks is None for s in samples)


def test_sample_market_series_cancel_count_resets_each_interval():
    events = [
        {"event_type": "ORDER_CANCELLED", "timestamp": 100, "transaction_seq": 1},
        {"event_type": "ORDER_CANCELLED", "timestamp": 200, "transaction_seq": 2},
    ]
    samples = sample_market_series(events, sample_interval_ns=1000, end_ns=2000)
    assert [s.cancel_count_since_last for s in samples] == [0, 2, 0]
