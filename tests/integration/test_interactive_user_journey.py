"""T811 H1-B gate: complete local human trading journey."""

from market_game_sim.interactive import InputAction, InteractiveRuntime


def test_representative_h1_b_user_journey() -> None:
    runtime = InteractiveRuntime()
    initial = runtime.start()
    assert initial["ui_state"] == "paused"
    assert initial["boundary_notice"] == "合成市场 · 无真实资金 · 非交易建议"
    accepted = runtime.place_order(
        {
            "client_request_id": "journey-market",
            "order_id": "journey-fill",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity_units": 3,
            "price_ticks": None,
        }
    )
    assert accepted.accepted
    rejected = runtime.place_order(
        {
            "client_request_id": "journey-bad",
            "order_id": "journey-bad",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity_units": 0,
            "price_ticks": 9990,
        }
    )
    assert not rejected.accepted and rejected.reason_code.value == "INVALID_INPUT"
    resting = runtime.place_order(
        {
            "client_request_id": "journey-limit",
            "order_id": "journey-rest",
            "side": "SELL",
            "order_type": "LIMIT",
            "quantity_units": 1,
            "price_ticks": 10030,
        }
    )
    assert resting.accepted
    assert runtime.cancel_order(
        {"client_request_id": "journey-cancel", "order_id": "journey-rest"}
    ).accepted
    view = runtime.view()
    assert view["account"]["position_units"] == 3
    assert view["account"]["active_orders"] == []
    assert {item["reason_code"] for item in view["recent_input_results"]} >= {"OK", "INVALID_INPUT"}
    assert runtime.control(InputAction.END, "journey-end").accepted
    assert runtime.view()["ui_state"] == "completed"
