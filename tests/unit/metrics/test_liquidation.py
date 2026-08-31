"""§2.2/§2.5 regression: compute_liquidation_metrics (指标字典 §4.1).

Round reviews confirmed the logic itself was correct via real leveraged
liquidation scenarios (non-zero liquidation_volume_ratio/chain sizes
observed), but the function had zero direct automated test coverage --
nothing in the repo imports or calls it in a test.
"""

from __future__ import annotations

import dataclasses

import pytest

from market_game_sim.metrics.liquidation import (
    LiquidationMetrics,
    RunClassification,
    classify_run,
    compute_liquidation_metrics,
)


def _liq_order(order_id: str, agent_id: str = "A") -> dict:
    return {
        "event_type": "ORDER_ARRIVAL",
        "origin": "LIQUIDATION",
        "order_id": order_id,
        "agent_id": agent_id,
    }


def _agent_order(order_id: str, agent_id: str = "X") -> dict:
    return {
        "event_type": "ORDER_ARRIVAL",
        "origin": "AGENT",
        "order_id": order_id,
        "agent_id": agent_id,
    }


def _trade(qty: int, taker_order_id: str = "", maker_order_id: str = "") -> dict:
    return {
        "event_type": "TRADE_SETTLE",
        "quantity_units": qty,
        "taker_order_id": taker_order_id,
        "maker_order_id": maker_order_id,
    }


def _margin_call(
    agent_id: str,
    verdict: str,
    chain_depth: int | None = None,
    chain_id: str | None = None,
) -> dict:
    return {
        "event_type": "MARGIN_CALL",
        "agent_id": agent_id,
        "verdict": verdict,
        "chain_depth": chain_depth,
        "chain_id": chain_id,
    }


def test_empty_events_gives_zero_metrics():
    m = compute_liquidation_metrics([])
    assert m == LiquidationMetrics()
    assert m.liquidation_volume_ratio == 0.0


def test_total_volume_sums_all_trade_quantities():
    events = [_trade(100), _trade(50), _trade(25)]
    m = compute_liquidation_metrics(events)
    assert m.total_volume == 175


def test_liquidation_volume_counts_taker_side_liquidation_trade():
    events = [
        _liq_order("liq-1"),
        _trade(100, taker_order_id="liq-1", maker_order_id="m1"),
    ]
    m = compute_liquidation_metrics(events)
    assert m.liquidation_volume == 100
    assert m.total_volume == 100


def test_liquidation_volume_counts_maker_side_liquidation_trade():
    """A resting order that was itself a LIQUIDATION order gets hit later
    as MAKER -- must also count toward liquidation_volume."""
    events = [
        _liq_order("liq-1"),
        _trade(60, taker_order_id="t2", maker_order_id="liq-1"),
    ]
    m = compute_liquidation_metrics(events)
    assert m.liquidation_volume == 60


def test_non_liquidation_trade_not_counted():
    """Negative case: a normal AGENT-origin trade must not inflate
    liquidation_volume even though total_volume includes it."""
    events = [
        _agent_order("o1"),
        _agent_order("o2"),
        _trade(100, taker_order_id="o1", maker_order_id="o2"),
    ]
    m = compute_liquidation_metrics(events)
    assert m.total_volume == 100
    assert m.liquidation_volume == 0


def test_liquidation_volume_ratio_zero_when_no_trades():
    m = compute_liquidation_metrics([_liq_order("liq-1")])
    assert m.liquidation_volume_ratio == 0.0


def test_liquidation_volume_ratio_computes_correctly():
    events = [
        _liq_order("liq-1"),
        _agent_order("o1"),
        _trade(30, taker_order_id="liq-1", maker_order_id="o1"),
        _trade(70, taker_order_id="o1", maker_order_id="o2"),
    ]
    m = compute_liquidation_metrics(events)
    assert m.total_volume == 100
    assert m.liquidation_volume == 30
    assert m.liquidation_volume_ratio == 0.3


def test_margin_call_ok_verdict_not_counted_toward_liquidations():
    """Negative case: verdict=OK (recovered/never-breached) must not add
    to total_liquidations/chain_depth_counts/bankruptcy_total."""
    events = [_margin_call("A", "OK", chain_depth=2, chain_id="c1")]
    m = compute_liquidation_metrics(events)
    assert m.total_liquidations == 0
    assert m.chain_depth_counts == {}
    assert m.bankruptcy_total == 0
    assert m.chain_size_by_id == {}


def test_margin_call_pending_liquidation_counted_in_chain_depth():
    events = [
        _margin_call("A", "PENDING_LIQUIDATION", chain_depth=0, chain_id="c1"),
        _margin_call("B", "PENDING_LIQUIDATION", chain_depth=1, chain_id="c1"),
    ]
    m = compute_liquidation_metrics(events)
    assert m.total_liquidations == 2
    assert m.chain_depth_counts == {0: 1, 1: 1}
    assert m.bankruptcy_total == 0


def test_margin_call_missing_chain_depth_defaults_to_zero():
    events = [_margin_call("A", "PENDING_LIQUIDATION", chain_depth=None, chain_id="c1")]
    m = compute_liquidation_metrics(events)
    assert m.chain_depth_counts == {0: 1}


def test_bankruptcy_total_counts_only_breached_not_pending():
    """Positive+negative: BREACHED increments bankruptcy_total,
    PENDING_LIQUIDATION does not, even though both count toward
    total_liquidations."""
    events = [
        _margin_call("A", "BREACHED", chain_depth=0, chain_id=None),
        _margin_call("B", "PENDING_LIQUIDATION", chain_depth=0, chain_id="c1"),
    ]
    m = compute_liquidation_metrics(events)
    assert m.bankruptcy_total == 1
    assert m.total_liquidations == 2


def test_chain_size_by_id_counts_unique_agents_in_same_batch():
    """Batch scenario (CLAUDE.md rule): a chained liquidation touching
    THREE distinct accounts under the same chain_id must report chain
    size 3, not double-count repeated agent_id entries and not conflate
    separate chain_ids."""
    events = [
        _margin_call("A", "PENDING_LIQUIDATION", chain_depth=0, chain_id="c1"),
        _margin_call("B", "PENDING_LIQUIDATION", chain_depth=1, chain_id="c1"),
        _margin_call("C", "PENDING_LIQUIDATION", chain_depth=2, chain_id="c1"),
        # same agent re-flagged in the same chain (recount) must not double-count
        _margin_call("A", "PENDING_LIQUIDATION", chain_depth=0, chain_id="c1"),
        # an unrelated, independent chain
        _margin_call("D", "PENDING_LIQUIDATION", chain_depth=0, chain_id="c2"),
    ]
    m = compute_liquidation_metrics(events)
    assert m.chain_size_by_id == {"c1": 3, "c2": 1}


def test_chain_size_excludes_missing_chain_id():
    events = [_margin_call("A", "BREACHED", chain_depth=0, chain_id=None)]
    m = compute_liquidation_metrics(events)
    assert m.chain_size_by_id == {}


def _classify(events, *, last_ticks=10_000, idle_ns=0, total_ns=100):
    return classify_run(
        events=events,
        last_ticks=last_ticks,
        initial_price=10_000,
        total_idle_ns=idle_ns,
        run_total_ns=total_ns,
        has_aborted=False,
        chained_liquidation_drained_book=False,
    )


def test_ev1_records_a_floor_touch_even_when_price_recovers():
    result = _classify(
        [
            {"event_type": "TRADE_SETTLE", "price_ticks": 1},
            {"event_type": "TRADE_SETTLE", "price_ticks": 10_000},
        ]
    )
    assert "EV-1" in result.economic_endpoint_codes


def test_ev3_requires_positive_run_duration():
    assert "EV-3" not in _classify([], idle_ns=1, total_ns=0).economic_endpoint_codes
    assert "EV-3" in _classify([], idle_ns=6, total_ns=100).economic_endpoint_codes


def test_ev4_records_directional_drained_sides():
    result = classify_run(
        events=[],
        last_ticks=10_000,
        initial_price=10_000,
        total_idle_ns=0,
        run_total_ns=100,
        has_aborted=False,
        chained_liquidation_drained_book=True,
        liquidation_drained_sides=["bid"],
    )
    assert result.economic_endpoint_codes == ["EV-4"]
    assert result.ev4_drained_sides == ["bid"]
    assert set(result.as_dict()) == {field.name for field in dataclasses.fields(RunClassification)}


def test_ev4_rejects_unknown_drained_side():
    with pytest.raises(ValueError, match="only bid/ask"):
        classify_run(
            events=[],
            last_ticks=10_000,
            initial_price=10_000,
            total_idle_ns=0,
            run_total_ns=100,
            has_aborted=False,
            chained_liquidation_drained_book=True,
            liquidation_drained_sides=["middle"],
        )
