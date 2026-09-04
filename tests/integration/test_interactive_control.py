"""T810: controls, idempotency, disconnect and terminal behavior."""

from market_game_sim.interactive import InputAction, InteractiveRuntime


def test_controls_step_disconnect_and_terminal_state() -> None:
    runtime = InteractiveRuntime()
    runtime.start()
    stepped = runtime.control(InputAction.STEP, "step")
    assert stepped.accepted and runtime.view()["logical_timestamp"] == 1_000_000_000
    assert runtime.control(InputAction.RESUME, "resume").accepted
    runtime.disconnect()
    assert runtime.view()["session_state"] == "PAUSED"
    assert runtime.control(InputAction.END, "end").accepted
    rejected = runtime.place_order(
        {
            "client_request_id": "late",
            "order_id": "late",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity_units": 1,
            "price_ticks": None,
        }
    )
    assert not rejected.accepted and rejected.reason_code.value == "INVALID_STATE"
    assert runtime.view()["session_state"] == "COMPLETED"


def test_idempotent_retry_and_conflict_do_not_double_submit() -> None:
    runtime = InteractiveRuntime()
    runtime.start()
    command = {
        "client_request_id": "same",
        "order_id": "once",
        "side": "BUY",
        "order_type": "MARKET",
        "quantity_units": 2,
        "price_ticks": None,
    }
    first = runtime.place_order(command)
    assert runtime.place_order(dict(command)) == first
    assert runtime.view()["account"]["position_units"] == 2
    conflict = runtime.place_order({**command, "quantity_units": 3})
    assert not conflict.accepted and conflict.reason_code.value == "IDEMPOTENCY_CONFLICT"
    assert runtime.view()["account"]["position_units"] == 2
