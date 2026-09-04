"""T814: disconnect, write failure, offline and portable-path behavior."""

import pytest

from market_game_sim.interactive.delivery import generate_interactive_delivery
from market_game_sim.interactive.runtime import InteractiveRuntime
from market_game_sim.interactive.types import InputAction


def test_disconnect_pauses_without_rolling_back_committed_trade() -> None:
    runtime = InteractiveRuntime()
    runtime.start()
    runtime.control(InputAction.RESUME, "resume")
    result = runtime.place_order(
        {
            "client_request_id": "fill",
            "order_id": "fill",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity_units": 1,
            "price_ticks": None,
        }
    )
    runtime.disconnect()
    assert result.accepted
    assert runtime.view()["session_state"] == "PAUSED"
    assert runtime.view()["account"]["position_units"] == 1


def test_internal_failure_aborts_without_partial_commit(monkeypatch) -> None:
    runtime = InteractiveRuntime()
    runtime.start()
    before = runtime.view()["account"]

    def fail(*_args, **_kwargs):
        raise OSError("injected kernel failure")

    monkeypatch.setattr(runtime.adapter, "place_order", fail)
    result = runtime.place_order(
        {
            "client_request_id": "fail",
            "order_id": "fail",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity_units": 1,
            "price_ticks": None,
        }
    )
    assert not result.accepted and result.reason_code.value == "INTERNAL_ABORT"
    assert runtime.view()["session_state"] == "ABORTED"
    assert runtime.view()["account"] == before


@pytest.mark.parametrize("stage", ["journal", "event_log"])
def test_write_failure_leaves_no_partial_bundle_and_fresh_retry_succeeds(tmp_path, stage) -> None:
    out = tmp_path / "portable" / "H1"
    with pytest.raises(OSError, match="injected"):
        generate_interactive_delivery(out, fail_after=stage)
    assert not out.exists()
    result = generate_interactive_delivery(out)
    assert result["manifest"].is_file()


def test_replay_is_single_file_and_offline(tmp_path) -> None:
    out = tmp_path / "windows-compatible" / "H1"
    generate_interactive_delivery(out)
    html = (out / "replay.html").read_text(encoding="utf-8")
    assert "replay-data" in html
    assert "fetch(" not in html
    assert "http://" not in html and "https://" not in html
