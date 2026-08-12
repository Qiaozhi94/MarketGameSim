"""T102 (FR-019): state rebuild from events tests."""

from __future__ import annotations

from market_game_sim.replay.frames import build_frame
from market_game_sim.replay.state import ReserveConfig, apply_event, new_state

MULT = 1000


def _acct_snapshot(accounts, fee=0, risk=0) -> dict:
    return {
        "event_type": "SNAPSHOT",
        "snapshot_type": "ACCOUNT",
        "payload": {
            "accounts": accounts,
            "exchange": {"fee_cash_units": fee, "risk_pnl_units": risk},
        },
    }


def _entry(aid, wallet, pos=0, entry=0, state="ACTIVE", gen=0) -> dict:
    return {
        "agent_id": aid,
        "wallet_units": wallet,
        "position_units": pos,
        "entry_notional_units": entry,
        "reserved_units": 0,
        "realized_pnl_units": 0,
        "state": state,
        "margin_ratio_bp": None,
        "liquidation_generation": gen,
        "chain_id": None,
        "chain_depth": None,
    }


def test_account_snapshot_initializes_accounts_and_exchange():
    st = new_state()
    apply_event(st, _acct_snapshot([_entry("A", 1000), _entry("B", 2000)], fee=5, risk=-3))
    assert set(st.accounts) == {"A", "B"}
    assert st.accounts["A"].wallet_units == 1000
    assert st.fee_cash_units == 5
    assert st.risk_pnl_units == -3


def test_trade_settle_updates_account_fields():
    st = new_state()
    st.reserve = ReserveConfig(mult=1000, initial_price_ticks=10000, agent_initial_bp={"A": 10000})
    apply_event(st, _acct_snapshot([_entry("A", 10000)]))
    trade = {
        "event_type": "TRADE_SETTLE",
        "price_ticks": 10000,
        "quantity_units": 10,
        "maker_fee_cash_units": 5,
        "taker_fee_cash_units": 7,
        "maker_order_id": "o1",
        "maker_agent_id": "A",
        "taker_agent_id": "B",
        "postings": [
            {
                "posting_type": "TRADE_POSTING",
                "agent_id": "A",
                "wallet_after_units": 9000,
                "position_after_units": 10,
                "entry_notional_after_units": 100_000_000,
                "reserved_delta_units": -100,
                "realized_pnl_delta_units": 50,
            }
        ],
    }
    apply_event(st, trade)
    a = st.accounts["A"]
    assert a.wallet_units == 9000
    assert a.position_units == 10
    assert a.entry_notional_units == 100_000_000
    assert a.realized_pnl_units == 50
    assert st.fee_cash_units == 12
    assert st.last_ticks == 10000
    # reserved_units is recomputed (worst-case margin over position, no orders):
    # div_ceil(10 * 10000 * 1000 * 10000, 10000) == 100_000_000
    assert a.reserved_units == 100_000_000


def test_margin_call_breached_sets_state_and_wallet():
    st = new_state()
    apply_event(st, _acct_snapshot([_entry("A", -5)]))
    mc = {
        "event_type": "MARGIN_CALL",
        "agent_id": "A",
        "verdict": "BREACHED",
        "chain_id": None,
        "chain_depth": None,
        "liquidation_generation_after": 1,
        "postings": [
            {
                "posting_type": "WRITE_OFF_POSTING",
                "role": "ACCOUNT",
                "agent_id": "A",
                "wallet_delta_units": 5,
            },
            {
                "posting_type": "WRITE_OFF_POSTING",
                "role": "EXCHANGE_RISK",
                "risk_pnl_delta_units": -5,
            },
        ],
    }
    apply_event(st, mc)
    a = st.accounts["A"]
    assert a.state == "LIQUIDATED"
    assert a.wallet_units == 0
    assert a.liquidation_generation == 1
    assert st.risk_pnl_units == -5


def test_margin_call_recovery_sets_active():
    st = new_state()
    apply_event(st, _acct_snapshot([_entry("A", 1000, state="PENDING_LIQUIDATION", gen=2)]))
    mc = {
        "event_type": "MARGIN_CALL",
        "agent_id": "A",
        "verdict": "OK",
        "chain_id": None,
        "chain_depth": None,
        "liquidation_generation_after": 3,
        "postings": [],
    }
    apply_event(st, mc)
    assert st.accounts["A"].state == "ACTIVE"
    assert st.accounts["A"].liquidation_generation == 3


def test_book_aggregation_includes_order_count_for_multiple_orders():
    st = new_state()
    apply_event(st, _acct_snapshot([_entry("A", 10000), _entry("B", 10000)]))
    apply_event(
        st,
        {
            "event_type": "SNAPSHOT",
            "snapshot_type": "BOOK",
            "payload": {"bids": [], "asks": [], "last_ticks": None},
        },
    )
    for i, (side, price, qty) in enumerate(
        [("BUY", 9900, 100), ("BUY", 9900, 50), ("SELL", 10100, 80)]
    ):
        apply_event(
            st,
            {
                "event_type": "ORDER_ARRIVAL",
                "action": "SUBMIT",
                "accepted": True,
                "order_type": "LIMIT",
                "order_id": f"o{i}",
                "side": side,
                "price_ticks": price,
                "quantity_units": qty,
                "agent_id": "A",
            },
        )
    frame = build_frame(st, frame_index=0, transaction_seq=2, mult=MULT)
    bids = frame.book["bids"]
    asks = frame.book["asks"]
    assert bids == [{"price_ticks": 9900, "quantity_units": 150, "order_count": 2}]
    assert asks == [{"price_ticks": 10100, "quantity_units": 80, "order_count": 1}]


def test_cancelled_order_drops_from_book():
    st = new_state()
    apply_event(st, _acct_snapshot([_entry("A", 10000)]))
    apply_event(
        st,
        {
            "event_type": "SNAPSHOT",
            "snapshot_type": "BOOK",
            "payload": {"bids": [], "asks": [], "last_ticks": None},
        },
    )
    apply_event(
        st,
        {
            "event_type": "ORDER_ARRIVAL",
            "action": "SUBMIT",
            "accepted": True,
            "order_type": "LIMIT",
            "order_id": "o1",
            "side": "BUY",
            "price_ticks": 9900,
            "quantity_units": 100,
            "agent_id": "A",
        },
    )
    apply_event(
        st,
        {
            "event_type": "ORDER_CANCELLED",
            "order_id": "o1",
            "agent_id": "A",
            "cancelled_qty_units": 100,
        },
    )
    frame = build_frame(st, frame_index=0, transaction_seq=2, mult=MULT)
    assert frame.book["bids"] == []
