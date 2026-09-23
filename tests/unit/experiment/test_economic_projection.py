"""ADR-015: the economic projection ignores exactly market-data bookkeeping.

Positive: logs that differ only in MARKET_DATA_PUBLISH records and the cursors
pointing at them project to the same digest.  Negative: any change to an order,
fill, cancel, margin call, decision or observed information changes it.  The
tool's comparison core is pinned on both outcomes as well.
"""

from __future__ import annotations

import copy
import importlib.util
import pathlib

import pytest

from market_game_sim.evidence.economic_projection import economic_digest, project

TOOL = pathlib.Path(__file__).resolve().parents[3] / "tools" / "prove_economic_equivalence.py"


def _log() -> list[dict]:
    return [
        {
            "event_type": "AGENT_OBSERVE",
            "event_id": "e5_0",
            "agent_id": "a",
            "market_data_event_id": "e4_2",
            "cursor_from_event_id": "e1_0",
            "cursor_to_event_id": "e4_2",
            "observed_at": 400,
            "information_set": {"best_bid": 9990, "best_ask": 10010},
        },
        {
            "event_type": "AGENT_DECIDE",
            "event_id": "e6_0",
            "agent_id": "a",
            "intents": [{"action": "SUBMIT", "side": "BUY", "quantity_units": 5}],
            "internal_state": {"desired_position_units": 5},
            "decision_evidence": {
                "cursor_from_event_id": "e1_0",
                "cursor_to_event_id": "e4_2",
                "desired_position_units": 5,
            },
        },
        {"event_type": "ORDER_ARRIVAL", "event_id": "e7_0", "agent_id": "a", "quantity_units": 5},
        {
            "event_type": "TRADE_SETTLE",
            "event_id": "e7_1",
            "price_ticks": 10010,
            "quantity_units": 5,
        },
        {"event_type": "ORDER_CANCELLED", "event_id": "e8_1", "order_id": "o1", "reason": "X"},
        {"event_type": "MARGIN_CALL", "event_id": "e9_1", "agent_id": "b", "verdict": "OK"},
        {"event_type": "MARKET_DATA_PUBLISH", "event_id": "e9_2", "best_bid": 9990},
    ]


def _with_extra_publish_and_moved_cursors() -> list[dict]:
    log = _log()
    log.insert(5, {"event_type": "MARKET_DATA_PUBLISH", "event_id": "e8_2", "best_ask": None})
    log[0].update(market_data_event_id="e8_2", cursor_to_event_id="e8_2", observed_at=800)
    log[1]["decision_evidence"]["cursor_to_event_id"] = "e8_2"
    return log


def test_format_version_is_not_an_economic_fact() -> None:
    """A schema_version bump touches every record but changes nothing economic."""
    bumped = copy.deepcopy(_log())
    for record in bumped:
        record["schema_version"] = 5
    assert economic_digest(bumped) == economic_digest(_log())


def test_publish_bookkeeping_alone_does_not_change_the_digest() -> None:
    assert economic_digest(_with_extra_publish_and_moved_cursors()) == economic_digest(_log())
    assert all(r["event_type"] != "MARKET_DATA_PUBLISH" for r in project(_log()))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda log: log[3].__setitem__("price_ticks", 10011),
        lambda log: log[2].__setitem__("quantity_units", 6),
        lambda log: log[4].__setitem__("reason", "Y"),
        lambda log: log[5].__setitem__("verdict", "PENDING_LIQUIDATION"),
        lambda log: log[1]["intents"][0].__setitem__("side", "SELL"),
        lambda log: log[1]["decision_evidence"].__setitem__("desired_position_units", 6),
        lambda log: log[0]["information_set"].__setitem__("best_ask", None),
        lambda log: log.pop(3),
        lambda log: log.__setitem__(slice(2, 4), [log[3], log[2]]),
    ],
    ids=[
        "fill-price",
        "order-qty",
        "cancel-reason",
        "margin-verdict",
        "decision-intent",
        "decision-evidence",
        "observed-book",
        "dropped-fill",
        "reordered",
    ],
)
def test_any_economic_change_moves_the_digest(mutate) -> None:
    log = copy.deepcopy(_log())
    mutate(log)
    assert economic_digest(log) != economic_digest(_log())


def _tool():
    spec = importlib.util.spec_from_file_location("_prove_tool", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tool_compare_reports_identical_and_differing_runs() -> None:
    compare = _tool().compare
    assert compare({"a": "1", "b": "2"}, {"a": "1", "b": "2"}) == {
        "compared": 2,
        "identical": 2,
        "differing": [],
    }
    result = compare({"a": "1", "b": "2"}, {"a": "1", "b": "3", "c": "4"})
    assert result == {"compared": 3, "identical": 1, "differing": ["b", "c"]}
