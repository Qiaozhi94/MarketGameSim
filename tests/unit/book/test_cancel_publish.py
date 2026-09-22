"""事件 Schema §4.2 推论 3 / §4.3: a CANCEL that changes the book must publish.

Regression for the L1 gap found in 0.4.1 T961 (ADR-015): the cancel path returned
without ``MARKET_DATA_PUBLISH``, so a cancel that emptied a side left the public
record showing a two-sided book until the next submit.  The rule is field-based,
not "something was removed": a cancel that leaves every §4.3 field unchanged
(the order shared its level with another) must stay silent.
"""

from __future__ import annotations

from market_game_sim.book.simulator import BookLevel, run_simulation


def _cancel(order_id: str, agent_id: str, target: str, t: int) -> dict:
    return {
        "event_type": "ORDER_ARRIVAL",
        "timestamp": t,
        "agent_id": agent_id,
        "order_id": order_id,
        "action": "CANCEL",
        "target_order_id": target,
        "side": None,
        "order_type": None,
        "price_ticks": None,
        "quantity_units": None,
    }


def _by_transaction(records: list[dict]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for r in records:
        if r.get("record_kind", "EVENT") == "EVENT" and "transaction_seq" in r:
            out.setdefault(r["transaction_seq"], []).append(r)
    return out


def _cancel_transactions(records: list[dict]) -> list[list[dict]]:
    return [
        txn
        for txn in _by_transaction(records).values()
        if txn[0]["event_type"] == "ORDER_ARRIVAL" and txn[0].get("action") == "CANCEL"
    ]


def test_cancel_that_empties_a_side_publishes_the_one_sided_book() -> None:
    levels = [BookLevel("SELL", "a1", "mm", 10010, 5), BookLevel("BUY", "b1", "mm", 9990, 5)]
    records, _ = run_simulation(levels, [_cancel("c1", "mm", "a1", 100)])
    [txn] = _cancel_transactions(records)
    assert [r["event_type"] for r in txn] == [
        "ORDER_ARRIVAL",
        "ORDER_CANCELLED",
        "MARKET_DATA_PUBLISH",
    ]
    publish = txn[-1]
    assert (publish["best_bid"], publish["best_ask"]) == (9990, None)
    assert (publish["bid_depth_k"], publish["ask_depth_k"]) == (1, 0)


def test_cancel_that_moves_the_best_price_publishes() -> None:
    levels = [
        BookLevel("SELL", "a1", "mm", 10010, 5),
        BookLevel("SELL", "a2", "mm", 10020, 5),
        BookLevel("BUY", "b1", "mm", 9990, 5),
    ]
    records, _ = run_simulation(levels, [_cancel("c1", "mm", "a1", 100)])
    [txn] = _cancel_transactions(records)
    assert txn[-1]["event_type"] == "MARKET_DATA_PUBLISH"
    assert txn[-1]["best_ask"] == 10020


def test_cancel_that_changes_no_published_field_stays_silent() -> None:
    # a2 shares a1's level: best price and level count both survive the cancel.
    levels = [
        BookLevel("SELL", "a1", "mm", 10010, 5),
        BookLevel("SELL", "a2", "mm2", 10010, 5),
        BookLevel("BUY", "b1", "mm", 9990, 5),
    ]
    records, _ = run_simulation(levels, [_cancel("c1", "mm", "a1", 100)])
    [txn] = _cancel_transactions(records)
    assert [r["event_type"] for r in txn] == ["ORDER_ARRIVAL", "ORDER_CANCELLED"]


def test_cancel_of_an_unknown_order_stays_silent() -> None:
    levels = [BookLevel("SELL", "a1", "mm", 10010, 5), BookLevel("BUY", "b1", "mm", 9990, 5)]
    records, _ = run_simulation(levels, [_cancel("c1", "mm", "nope", 100)])
    [txn] = _cancel_transactions(records)
    assert [r["event_type"] for r in txn] == ["ORDER_ARRIVAL"]


def test_batch_of_cancels_publishes_exactly_when_the_book_changes() -> None:
    """Several agents cancel in turn; each publish reports the book after that cancel."""
    levels = [
        BookLevel("SELL", "a1", "mm-0", 10010, 5),
        BookLevel("SELL", "a2", "mm-1", 10010, 5),
        BookLevel("SELL", "a3", "mm-2", 10020, 5),
        BookLevel("BUY", "b1", "mm-0", 9990, 5),
        BookLevel("BUY", "b2", "mm-1", 9980, 5),
    ]
    events = [
        _cancel("c1", "mm-0", "a1", 100),  # level 10010 keeps a2 -> silent
        _cancel("c2", "mm-1", "a2", 200),  # 10010 emptied -> best ask 10020
        _cancel("c3", "mm-2", "a3", 300),  # ask side emptied
        _cancel("c4", "mm-1", "b2", 400),  # deeper bid level gone -> depth 1
        _cancel("c5", "mm-0", "b1", 500),  # book empty
    ]
    records, book = run_simulation(levels, events)
    txns = _cancel_transactions(records)
    assert len(txns) == 5
    published = [
        (t[0]["order_id"], t[-1]["best_bid"], t[-1]["best_ask"], t[-1]["bid_depth_k"])
        for t in txns
        if t[-1]["event_type"] == "MARKET_DATA_PUBLISH"
    ]
    assert published == [
        ("c2", 9990, 10020, 2),
        ("c3", 9990, None, 2),
        ("c4", 9990, None, 1),
        ("c5", None, None, 0),
    ]
    for t in txns:  # publish, when present, is always the transaction's last record
        kinds = [r["event_type"] for r in t]
        assert "MARKET_DATA_PUBLISH" not in kinds[:-1]
    assert book.best_bid() is None and book.best_ask() is None
