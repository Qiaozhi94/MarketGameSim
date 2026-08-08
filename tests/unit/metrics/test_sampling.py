"""§2.9/T501 regression: compute_price_impact (指标字典 §3.4/§4).

Round reviews found T501 marked [x] in tasks.md (fixed-interval sampling
implemented) but grep for "impact"/"slippage" across metrics/ was zero --
the price-impact/slippage half of §2—§4's declared scope was never
implemented.  These tests cover the new compute_price_impact function
directly against hand-built TRADE_SETTLE records (no engine dependency,
deterministic).
"""

from __future__ import annotations

from market_game_sim.metrics.sampling import compute_price_impact

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
