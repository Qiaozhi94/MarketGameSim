"""T808: human orders share the production matching and ledger path."""

from market_game_sim.interactive import InteractiveRuntime
from market_game_sim.schema.constraints import validate_record
from market_game_sim.schema.registry import get_registry


def _runtime() -> InteractiveRuntime:
    runtime = InteractiveRuntime()
    assert runtime.start()["session_state"] == "PAUSED"
    return runtime


def test_human_limit_market_and_cancel_use_production_events() -> None:
    runtime = _runtime()
    resting = runtime.place_order(
        {
            "client_request_id": "limit",
            "order_id": "h-limit",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity_units": 10,
            "price_ticks": 9980,
        }
    )
    assert resting.accepted
    assert runtime.view()["account"]["active_orders"][0]["order_id"] == "h-limit"
    filled = runtime.place_order(
        {
            "client_request_id": "market",
            "order_id": "h-market",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity_units": 5,
            "price_ticks": None,
        }
    )
    assert filled.accepted
    assert runtime.view()["account"]["position_units"] == 5
    cancelled = runtime.cancel_order({"client_request_id": "cancel", "order_id": "h-limit"})
    assert cancelled.accepted
    assert runtime.view()["account"]["active_orders"] == []
    records = runtime.adapter.records
    assert sum(item.get("event_type") == "AGENT_DECIDE" for item in records) == 3
    assert all(
        item.get("rule_id") == "human"
        for item in records
        if item.get("event_type") == "AGENT_DECIDE"
    )
    assert any(item.get("event_type") == "TRADE_SETTLE" for item in records)
    assert any(item.get("event_type") == "ORDER_CANCELLED" for item in records)
    for record in records:
        validate_record(record, get_registry())


def test_human_order_rejections_are_atomic_and_stable() -> None:
    runtime = _runtime()
    before = runtime.view()["account"]
    invalid = runtime.place_order(
        {
            "client_request_id": "bad",
            "order_id": "bad",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity_units": 1001,
            "price_ticks": 9980,
        }
    )
    assert not invalid.accepted and invalid.reason_code.value == "INVALID_INPUT"
    assert runtime.view()["account"]["position_units"] == before["position_units"]
    unknown = runtime.cancel_order({"client_request_id": "missing", "order_id": "absent"})
    assert not unknown.accepted and unknown.reason_code.value == "UNKNOWN_ORDER"


def test_multiple_human_orders_are_processed_in_input_order() -> None:
    runtime = _runtime()
    for index in range(3):
        result = runtime.place_order(
            {
                "client_request_id": f"batch-{index}",
                "order_id": f"order-{index}",
                "side": "BUY",
                "order_type": "LIMIT",
                "quantity_units": 1,
                "price_ticks": 9970 - index,
            }
        )
        assert result.accepted and result.input_seq == index
    assert [item["order_id"] for item in runtime.view()["account"]["active_orders"]] == [
        "order-0",
        "order-1",
        "order-2",
    ]
