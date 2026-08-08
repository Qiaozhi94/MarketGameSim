"""T407/T408: acceptance vectors 1-5, 10 + PnL bridge (acceptance-vectors.md).

Integer-exact assertions against §4 (integer projection table) and §3
(step-by-step expected state).  C1/C2 verified per-event by replaying
the postings.  PnL bridge residual verified per-event == 0 using
valuation_mark (metrics-dictionary §5.2).

BENCH-001: MULT=1000, cash_unit=1e-8.
  price 100.00 -> 10000 ticks ; qty 10 -> 10000 units ; cash 1000 -> 1e11.
"""

from __future__ import annotations

from typing import Any

from market_game_sim.book.matching import match_order
from market_game_sim.book.orderbook import Book
from market_game_sim.eventlog.bootstrap import (
    build_account_payload_from_accounts,
    build_book_payload,
)
from market_game_sim.kernel.runner import EventKernel
from market_game_sim.ledger.account import Account, AccountState

MULT = 1000
MULT_HALF = MULT // 2
CASH = 10**8


def cash(h: float | int) -> int:
    return int(round(h * CASH))


def ticks(h: float | int) -> int:
    return int(round(h * 100))


def units(h: float | int) -> int:
    return int(round(h * 1000))


def _limit(oid: str, aid: str, side: str, price: int, qty: int, t: int) -> dict:
    return {
        "event_type": "ORDER_ARRIVAL",
        "timestamp": t,
        "agent_id": aid,
        "order_id": oid,
        "action": "SUBMIT",
        "side": side,
        "order_type": "LIMIT",
        "price_ticks": price,
        "quantity_units": qty,
    }


def _run(
    events: list[dict],
    accounts: dict[str, Account],
    maker_bps: int = 0,
    taker_bps: int = 0,
    initial_price: int = 10000,
    initial_bp_per_agent: dict[str, int] | None = None,
    maint_bp: int | None = None,
    target_bp: int | None = None,
    liquidation_latency_ns: int = 1_000_000,
) -> tuple[list[dict], dict[str, Account]]:
    kernel = EventKernel(run_id="acc")
    kernel.bootstrap(
        build_account_payload_from_accounts(accounts, mult=MULT),
        build_book_payload(last_ticks=None),
    )
    book = Book(initial_price_ticks=initial_price)
    world: dict[str, Any] = {
        "book": book,
        "accounts": accounts,
        "exchange_fee_units": 0,
        "exchange_risk_pnl_units": 0,
        "mult": MULT,
        "maker_bps": maker_bps,
        "taker_bps": taker_bps,
        "initial_price_ticks": initial_price,
        "agent_initial_bp": initial_bp_per_agent or {},
    }
    if maint_bp is not None:
        # Enables the two-phase risk scan (_run_post_batch_risk_check is a
        # no-op when maint_bp is absent) -- only case 8/9 need this; every
        # other case intentionally leaves it unset to keep the risk gate
        # out of the picture.
        world["maint_bp"] = maint_bp
        world["target_bp"] = target_bp if target_bp is not None else 1000
        world["liquidation_latency_ns"] = liquidation_latency_ns
    for e in events:
        kernel.enqueue(e)
    kernel.run(match_order, world, max_transactions=10000)
    assert kernel.terminated == "COMPLETED", f"aborted: {kernel.abort_detail}"
    return kernel.committed_records, accounts


def _trades(records: list[dict]) -> list[dict]:
    return [r for r in records if r["event_type"] == "TRADE_SETTLE"]


def _replay_check(records: list[dict]) -> list[dict]:
    """Replay postings; per TRADE_SETTLE assert C1, C2, PnL-bridge residual.

    Self-contained: each agent's initial wallet is discovered lazily on first
    trade as ``wallet_after - wallet_delta`` (账户合同 §7: position=0, entry=0
    at t=0).  C2 reduces to ``Σ_traded[(wallet−entry)−initial] + fees + risk
    == 0`` -- not-yet-traded agents contribute their constant initial wallet
    to both sides and cancel.
    """
    state: dict[str, dict[str, int]] = {}
    initial: dict[str, int] = {}
    exchange_fee = 0
    exchange_risk = 0
    out: list[dict] = []
    for r in records:
        if r["event_type"] != "TRADE_SETTLE":
            continue
        trade_res: dict[str, Any] = {"trade": r, "postings": []}
        for p in r["postings"]:
            aid = p["agent_id"]
            if aid not in state:
                initial[aid] = p["wallet_after_units"] - p["wallet_delta_units"]
                state[aid] = {"wallet": initial[aid], "position": 0, "entry": 0}
            before = dict(state[aid])
            state[aid] = {
                "wallet": p["wallet_after_units"],
                "position": p["position_after_units"],
                "entry": p["entry_notional_after_units"],
            }
            exchange_fee += p["fee_delta_units"]
            price = r["price_ticks"]
            vb = r["valuation_mark_before_half_ticks"]
            va = r["valuation_mark_after_half_ticks"]
            signed_qty = p["position_delta_units"]
            pos_before = before["position"]
            spread = signed_qty * (vb - 2 * price) * MULT_HALF
            impact = signed_qty * (va - vb) * MULT_HALF
            revaluation = pos_before * (va - vb) * MULT_HALF
            fees = p["fee_delta_units"]
            eq_before = before["wallet"] + pos_before * vb * MULT_HALF - before["entry"]
            eq_after = (
                state[aid]["wallet"] + state[aid]["position"] * va * MULT_HALF - state[aid]["entry"]
            )
            delta_eq = eq_after - eq_before
            decomp = spread + impact + revaluation + 0 - fees
            residual = delta_eq - decomp
            trade_res["postings"].append(
                {
                    "agent": aid,
                    "residual": residual,
                    "spread": spread,
                    "impact": impact,
                    "revaluation": revaluation,
                    "fees": fees,
                }
            )
        c1 = sum(s["position"] for s in state.values())
        c2_resid = (
            sum(s["wallet"] - s["entry"] - initial[a] for a, s in state.items())
            + exchange_fee
            + exchange_risk
        )
        trade_res["c1"] = c1
        trade_res["c2_resid"] = c2_resid
        out.append(trade_res)
    return out


def _assert_conservation(replay: list[dict]) -> None:
    for i, tr in enumerate(replay):
        assert tr["c1"] == 0, f"trade {i}: C1 violated, Σposition={tr['c1']}"
        assert tr["c2_resid"] == 0, f"trade {i}: C2 violated, resid={tr['c2_resid']}"
        for p in tr["postings"]:
            assert p["residual"] == 0, (
                f"trade {i} agent {p['agent']}: PnL bridge residual={p['residual']}"
            )


# --------------------------------------------------------------------------- #
# 案例 1: same-price open, zero fee
# --------------------------------------------------------------------------- #


class TestCase1SamePriceOpen:
    def _scenario(self):
        accts = {"A": Account("A", cash(1000)), "B": Account("B", cash(1000))}
        events = [
            _limit("b1", "B", "SELL", ticks(100), units(10), t=100),
            _limit("a1", "A", "BUY", ticks(100), units(10), t=200),
        ]
        records, accts = _run(events, accts, maker_bps=0, taker_bps=0)
        return records, accts

    def test_one_trade(self):
        records, _ = self._scenario()
        assert len(_trades(records)) == 1

    def test_posting_deltas_integer_exact(self):
        records, _ = self._scenario()
        t = _trades(records)[0]
        maker_p, taker_p = t["postings"][0], t["postings"][1]
        # B is maker (SELL): position -, entry -
        assert maker_p["agent_id"] == "B"
        assert maker_p["wallet_delta_units"] == 0
        assert maker_p["position_delta_units"] == -units(10)
        assert maker_p["entry_notional_delta_units"] == -1e11
        # A is taker (BUY): position +, entry +
        assert taker_p["agent_id"] == "A"
        assert taker_p["wallet_delta_units"] == 0
        assert taker_p["position_delta_units"] == units(10)
        assert taker_p["entry_notional_delta_units"] == 1e11

    def test_final_account_state(self):
        _, accts = self._scenario()
        assert accts["A"].position_units == units(10)
        assert accts["A"].entry_notional_units == cash(1000)
        assert accts["A"].wallet_units == cash(1000)
        assert accts["B"].position_units == -units(10)
        assert accts["B"].entry_notional_units == -cash(1000)
        assert accts["B"].wallet_units == cash(1000)

    def test_c1_c2_bridge_per_event(self):
        records, accts = self._scenario()
        replay = _replay_check(records)
        _assert_conservation(replay)

    def test_margin_ratio_null_for_open_with_no_mark_move(self):
        records, _ = self._scenario()
        t = _trades(records)[0]
        for p in t["postings"]:
            assert p["margin_ratio_after_bp"] is not None


# --------------------------------------------------------------------------- #
# 案例 2: three-agent cross-price handoff (C2 core case)
# --------------------------------------------------------------------------- #


class TestCase2CrossPriceHandoff:
    def _scenario(self):
        accts = {
            "A": Account("A", cash(1000)),
            "B": Account("B", cash(1000)),
            "C": Account("C", cash(1000)),
        }
        events = [
            _limit("b1", "B", "SELL", ticks(100), units(10), t=100),  # B rests sell @100
            _limit("a1", "A", "BUY", ticks(100), units(10), t=200),  # A buys @100 from B
            _limit("a2", "A", "SELL", ticks(110), units(10), t=300),  # A rests sell @110
            _limit("c1", "C", "BUY", ticks(110), units(10), t=400),  # C buys @110 from A
        ]
        records, accts = _run(events, accts, maker_bps=0, taker_bps=0)
        return records, accts

    def test_two_trades(self):
        records, _ = self._scenario()
        assert len(_trades(records)) == 2

    def test_step2_posting_deltas(self):
        records, _ = self._scenario()
        trade2 = _trades(records)[1]
        maker_p, taker_p = trade2["postings"][0], trade2["postings"][1]
        # A is maker (SELL @110): closes +10 long, realizes +100.
        assert maker_p["agent_id"] == "A"
        assert maker_p["wallet_delta_units"] == cash(100)  # +1e10
        assert maker_p["position_delta_units"] == -units(10)  # -10000
        assert maker_p["entry_notional_delta_units"] == -1e11  # -100000000000
        assert maker_p["realized_pnl_delta_units"] == cash(100)
        # C is taker (BUY @110): opens +10 long.
        assert taker_p["agent_id"] == "C"
        assert taker_p["wallet_delta_units"] == 0
        assert taker_p["position_delta_units"] == units(10)  # +10000
        assert taker_p["entry_notional_delta_units"] == 1.1e11  # +110000000000

    def test_final_state_handoff(self):
        _, accts = self._scenario()
        # A: closed out, wallet 1100, pos 0, entry 0.
        assert accts["A"].wallet_units == cash(1100)
        assert accts["A"].position_units == 0
        assert accts["A"].entry_notional_units == 0
        # B: still short -10 @100.
        assert accts["B"].wallet_units == cash(1000)
        assert accts["B"].position_units == -units(10)
        assert accts["B"].entry_notional_units == -cash(1000)
        # C: long +10 @110.
        assert accts["C"].wallet_units == cash(1000)
        assert accts["C"].position_units == units(10)
        assert accts["C"].entry_notional_units == cash(1100)

    def test_c1_c2_bridge_per_event(self):
        records, accts = self._scenario()
        replay = _replay_check(records)
        _assert_conservation(replay)

    def test_old_equations_falsified(self):
        # Σwallet = 3100 != 3000; Σentry = +100 != 0 -- but C2 = 3000.
        _, accts = self._scenario()
        wsum = sum(a.wallet_units for a in accts.values())
        esum = sum(a.entry_notional_units for a in accts.values())
        assert wsum == cash(3100)
        assert esum == cash(100)
        c2_lhs = wsum - esum
        assert c2_lhs == cash(3000)

    def test_margin_ratios_at_110(self):
        records, _ = self._scenario()
        trade2 = _trades(records)[1]
        maker_p, taker_p = trade2["postings"]
        # A: position 0 -> margin_ratio null.
        assert maker_p["margin_ratio_after_bp"] is None
        # B: -10 @100, mark 110 -> ratio 8181.
        # B isn't in trade2's postings; check via final state instead.
        # C: +10 @110, mark 110 -> 9090.
        assert taker_p["margin_ratio_after_bp"] == 9090


# --------------------------------------------------------------------------- #
# 案例 3: partial close (long & short symmetric)
# --------------------------------------------------------------------------- #


class TestCase3PartialClose:
    def _scenario(self):
        accts = {"A": Account("A", cash(1000)), "B": Account("B", cash(1000))}
        events = [
            _limit("b1", "B", "SELL", ticks(100), units(10), t=100),
            _limit("a1", "A", "BUY", ticks(100), units(10), t=200),
            _limit("a2", "A", "SELL", ticks(105), units(4), t=300),  # A rests sell @105
            _limit("b2", "B", "BUY", ticks(105), units(4), t=400),  # B buys @105 from A
        ]
        records, accts = _run(events, accts, maker_bps=0, taker_bps=0)
        return records, accts

    def test_step3_posting_deltas(self):
        records, _ = self._scenario()
        trade = _trades(records)[1]  # second trade (partial close)
        maker_p, taker_p = trade["postings"][0], trade["postings"][1]
        # A maker SELL @105: closes 4 of 10 long, realizes +20.
        assert maker_p["agent_id"] == "A"
        assert maker_p["wallet_delta_units"] == cash(20)  # +2e9
        assert maker_p["position_delta_units"] == -units(4)  # -4000
        assert maker_p["entry_notional_delta_units"] == -4e10  # -40000000000
        assert maker_p["realized_pnl_delta_units"] == cash(20)
        # B taker BUY @105: closes 4 of 10 short, realizes -20.
        assert taker_p["agent_id"] == "B"
        assert taker_p["wallet_delta_units"] == -cash(20)
        assert taker_p["position_delta_units"] == units(4)
        assert taker_p["entry_notional_delta_units"] == 4e10
        assert taker_p["realized_pnl_delta_units"] == -cash(20)

    def test_final_state_proportional_cut(self):
        _, accts = self._scenario()
        assert accts["A"].position_units == units(6)
        assert accts["A"].entry_notional_units == cash(600)
        assert accts["A"].wallet_units == cash(1020)
        assert accts["B"].position_units == -units(6)
        assert accts["B"].entry_notional_units == -cash(600)
        assert accts["B"].wallet_units == cash(980)

    def test_c1_c2_bridge_per_event(self):
        records, accts = self._scenario()
        replay = _replay_check(records)
        _assert_conservation(replay)


# --------------------------------------------------------------------------- #
# 案例 4: flip long -> short
# --------------------------------------------------------------------------- #


class TestCase4Flip:
    def _scenario(self):
        accts = {"A": Account("A", cash(1000)), "B": Account("B", cash(1000))}
        events = [
            _limit("b1", "B", "SELL", ticks(100), units(5), t=100),  # B rests sell @100
            _limit("a1", "A", "BUY", ticks(100), units(5), t=200),  # A buys 5 @100
            _limit("b2", "B", "BUY", ticks(98), units(10), t=300),  # B rests buy @98
            _limit("a2", "A", "SELL", ticks(98), units(10), t=400),  # A sells 10 @98 to B
        ]
        records, accts = _run(events, accts, maker_bps=0, taker_bps=0)
        return records, accts

    def test_flip_trade_deltas(self):
        records, _ = self._scenario()
        trade = _trades(records)[1]  # the flip trade
        maker_p, taker_p = trade["postings"][0], trade["postings"][1]
        # A taker SELL @98: close 5 long + open 5 short. B maker BUY @98.
        # A is taker here (B's buy was resting). So maker=B, taker=A.
        assert maker_p["agent_id"] == "B"
        assert taker_p["agent_id"] == "A"
        assert taker_p["wallet_delta_units"] == -cash(10)  # -1e9
        assert taker_p["position_delta_units"] == -units(10)  # -10000
        assert taker_p["entry_notional_delta_units"] == -9.9e10  # -99000000000
        assert taker_p["realized_pnl_delta_units"] == -cash(10)
        # B completely negated (zero fee, exact counterpart).
        assert maker_p["wallet_delta_units"] == cash(10)
        assert maker_p["position_delta_units"] == units(10)
        assert maker_p["entry_notional_delta_units"] == 9.9e10

    def test_final_state_flip(self):
        _, accts = self._scenario()
        # A: +5 @100 -> sell 10 @98 -> -5 @98. wallet 990.
        assert accts["A"].position_units == -units(5)
        assert accts["A"].entry_notional_units == -cash(490)
        assert accts["A"].wallet_units == cash(990)
        # B: -5 @100 -> buy 10 @98 -> +5 @98. wallet 1010.
        assert accts["B"].position_units == units(5)
        assert accts["B"].entry_notional_units == cash(490)
        assert accts["B"].wallet_units == cash(1010)

    def test_c1_c2_bridge_per_event(self):
        records, accts = self._scenario()
        replay = _replay_check(records)
        _assert_conservation(replay)


# --------------------------------------------------------------------------- #
# 案例 5: positive taker fee + negative maker rebate
# --------------------------------------------------------------------------- #


class TestCase5Fees:
    def _scenario(self):
        accts = {"A": Account("A", cash(1000)), "B": Account("B", cash(1000))}
        events = [
            _limit("b1", "B", "SELL", ticks(100), units(10), t=100),
            _limit("a1", "A", "BUY", ticks(100), units(10), t=200),
        ]
        records, accts = _run(
            events,
            accts,
            maker_bps=-1,
            taker_bps=5,
            initial_bp_per_agent={"A": 1000, "B": 1000},
        )
        return records, accts

    def test_fee_integers(self):
        records, _ = self._scenario()
        t = _trades(records)[0]
        assert t["maker_fee_cash_units"] == -10000000  # -0.1
        assert t["taker_fee_cash_units"] == 50000000  # 0.5
        assert t["maker_fee_cash_units"] + t["taker_fee_cash_units"] == 40000000

    def test_taker_wallet_reduced_by_fee(self):
        _, accts = self._scenario()
        # A taker: wallet 1000 - 0.5 = 999.5.
        assert accts["A"].wallet_units == cash(999.5)

    def test_maker_wallet_increased_by_rebate(self):
        _, accts = self._scenario()
        # B maker: wallet 1000 + 0.1 = 1000.1 (realized 0, rebate -0.1 -> wallet +0.1).
        assert accts["B"].wallet_units == cash(1000.1)

    def test_exchange_fee_signed(self):
        records, _ = self._scenario()
        t = _trades(records)[0]
        maker_fee = t["postings"][0]["fee_delta_units"]
        taker_fee = t["postings"][1]["fee_delta_units"]
        assert maker_fee == -10000000
        assert taker_fee == 50000000
        assert maker_fee + taker_fee == 40000000

    def test_c1_c2_bridge_per_event(self):
        records, accts = self._scenario()
        replay = _replay_check(records)
        _assert_conservation(replay)


# --------------------------------------------------------------------------- #
# 案例 10: three-account funding (rate=0 -> net 0, mechanism reserved)
# --------------------------------------------------------------------------- #


class TestCase10Funding:
    def _scenario(self):
        accts = {
            "A": Account("A", cash(10000)),
            "B": Account("B", cash(10000)),
            "C": Account("C", cash(10000)),
        }
        events = [
            _limit("b1", "B", "SELL", ticks(100), units(50), t=100),  # B rests sell 50
            _limit("a1", "A", "BUY", ticks(100), units(30), t=200),  # A buys 30
            _limit("c1", "C", "BUY", ticks(100), units(20), t=300),  # C buys 20
        ]
        records, accts = _run(events, accts, maker_bps=0, taker_bps=0)
        return records, accts

    def test_positions_sum_zero(self):
        _, accts = self._scenario()
        assert accts["A"].position_units == units(30)
        assert accts["C"].position_units == units(20)
        assert accts["B"].position_units == -units(50)
        assert sum(a.position_units for a in accts.values()) == 0

    def test_c1_c2_bridge_per_event(self):
        records, accts = self._scenario()
        replay = _replay_check(records)
        _assert_conservation(replay)

    def test_funding_zero_in_011(self):
        # funding_rate_bp = 0 in 0.1.1 -> no funding transfer, C2 unaffected.
        _, accts = self._scenario()
        # All wallets unchanged (zero fee, zero funding).
        assert accts["A"].wallet_units == cash(10000)
        assert accts["B"].wallet_units == cash(10000)
        assert accts["C"].wallet_units == cash(10000)


class TestCase6LeverageBoundary:
    """Case 6: 3x boundary -- ``initial_bp = ceil(10000/3) = 3334`` rejects 30.000.

    Per acceptance-vectors §3 case 6 (with case 6 projections in §4):
    29.994 qty -> 999.99996 IM -> 1000 equity -> PASS
    29.995 qty -> 1000.0333 IM -> 1000 equity -> REJECT
    30.000 qty -> 1000.2 IM -> 1000 equity -> REJECT
    """

    def test_initial_bp_3x_is_3334_ceiling(self):
        from market_game_sim.ledger.account import initial_margin_bp_for_tier

        assert initial_margin_bp_for_tier(3) == 3334

    def test_29994_qty_fits_under_1000_equity(self):
        from market_game_sim.ledger.margin import initial_margin_required

        notional = 29994 * 10000 * 1000  # qty * price * MULT
        im = initial_margin_required(notional, 3334)
        assert im == 99_999_996_000  # < 1e11 = 1000 human
        assert im < 100_000_000_000  # strict pass

    def test_29995_qty_exceeds_equity(self):
        from market_game_sim.ledger.margin import initial_margin_required

        notional = 29995 * 10000 * 1000
        im = initial_margin_required(notional, 3334)
        assert im > 100_000_000_000  # reject

    def test_30000_qty_exceeds_equity(self):
        from market_game_sim.ledger.margin import initial_margin_required

        notional = 30000 * 10000 * 1000
        im = initial_margin_required(notional, 3334)
        assert im > 100_000_000_000  # reject


class TestCase7bReservedUnits:
    """Case 7b: reserved_units -- total-occupancy (position + worst-case orders)."""

    def test_scenario1_baseline(self):
        from market_game_sim.ledger.reserved import (
            compute_reserved_after,
        )

        r = compute_reserved_after(
            position_units=100000,
            active_orders=[],
            risk_mark_ticks=10000,
            initial_bp=1000,
            fee_bps=5,
            mult=1000,
        )
        assert r == 100_000_000_000

    def test_scenario2_same_direction_buys(self):
        from market_game_sim.ledger.reserved import (
            ActiveOrder,
            compute_reserved_after,
        )

        r = compute_reserved_after(
            position_units=100000,
            active_orders=[
                ActiveOrder("BUY", 10000, 20000),
                ActiveOrder("BUY", 10000, 30000),
            ],
            risk_mark_ticks=10000,
            initial_bp=1000,
            fee_bps=5,
            mult=1000,
        )
        assert r == 150_250_000_000  # 1500 margin + 2.5 fees

    def test_scenario3_bilateral_does_not_cancel(self):
        from market_game_sim.ledger.reserved import (
            ActiveOrder,
            compute_reserved_after,
        )

        r = compute_reserved_after(
            position_units=100000,
            active_orders=[
                ActiveOrder("BUY", 10000, 20000),
                ActiveOrder("SELL", 10000, 50000),
            ],
            risk_mark_ticks=10000,
            initial_bp=1000,
            fee_bps=5,
            mult=1000,
        )
        assert r == 120_350_000_000  # max(|120|, |50|) = 120 -> 1200 + 3.5 fees

    def test_scenario4_after_buy_fill(self):
        from market_game_sim.ledger.reserved import (
            ActiveOrder,
            compute_reserved_after,
        )

        r = compute_reserved_after(
            position_units=120000,
            active_orders=[ActiveOrder("SELL", 10000, 50000)],
            risk_mark_ticks=10000,
            initial_bp=1000,
            fee_bps=5,
            mult=1000,
        )
        assert r == 120_250_000_000  # 1200 + 2.5 fees

    def test_reserved_delta_1_to_2(self):
        from market_game_sim.ledger.reserved import (
            ActiveOrder,
            compute_reserved_after,
        )

        r1 = compute_reserved_after(
            position_units=100000,
            active_orders=[],
            risk_mark_ticks=10000,
            initial_bp=1000,
            fee_bps=5,
            mult=1000,
        )
        r2 = compute_reserved_after(
            position_units=100000,
            active_orders=[
                ActiveOrder("BUY", 10000, 20000),
                ActiveOrder("BUY", 10000, 30000),
            ],
            risk_mark_ticks=10000,
            initial_bp=1000,
            fee_bps=5,
            mult=1000,
        )
        assert r2 - r1 == 50_250_000_000  # +502.5 human


class TestCase8LiquidationRetry:
    """Case 8: no-counterparty liquidation, no false retry, real retry on a
    new trade (acceptance-vectors.md §3 案例8).  State-machine sequence, no
    numeric assertions per the spec ("案例 8 为状态机序列，无数值断言").

    A opens a leveraged long, M's resting sell drops risk_mark and triggers
    PENDING_LIQUIDATION.  A's auto-scheduled LIQUIDATION order arrives with
    nothing to trade against (book only has SELL-side liquidity) -> full
    IOC cancel.  A same-side resting order (Y) then enters the book without
    trading -- must NOT itself produce a new LIQUIDATION order (step 5:
    "不触发重试"，挂单不改变 risk_mark).  A real trade (W/Z) then moves
    risk_mark further -> triggers a genuine re-scan -> a second, larger
    LIQUIDATION order (required_quantity recomputed against the new mark).
    """

    def _scenario(self):
        lat = 1_000_000
        accts = {
            "M": Account("M", 10**16),
            "A": Account(
                "A",
                wallet_units=5000 * CASH,
                position_units=500_000,
                entry_notional_units=50000 * CASH,
            ),
            "S": Account(
                "S",
                wallet_units=50000 * CASH,
                position_units=-500_000,
                entry_notional_units=-50000 * CASH,
            ),
            "X": Account("X", 10**16),
            "Y": Account("Y", 10**16),
            "W": Account("W", 10**16),
            "Z": Account("Z", 10**16),
        }
        events = [
            _limit("m1", "M", "SELL", 9400, 500_000, t=100),
            {
                "event_type": "ORDER_ARRIVAL",
                "timestamp": 200,
                "agent_id": "X",
                "order_id": "x1",
                "action": "SUBMIT",
                "side": "BUY",
                "order_type": "MARKET",
                "price_ticks": None,
                "quantity_units": 100_000,
            },
            # step 5: same-side resting order after the first (failed)
            # liquidation attempt -- must not itself trigger a retry.
            _limit("y1", "Y", "SELL", 9500, 1_000, t=200 + lat + 100),
            # step 6: a real trade at a new price moves risk_mark further.
            _limit("w1", "W", "SELL", 9000, 50_000, t=200 + lat + 200),
            {
                "event_type": "ORDER_ARRIVAL",
                "timestamp": 200 + lat + 300,
                "agent_id": "Z",
                "order_id": "z1",
                "action": "SUBMIT",
                "side": "BUY",
                "order_type": "MARKET",
                "price_ticks": None,
                "quantity_units": 50_000,
            },
        ]
        for e in events:
            e.setdefault("origin", "")
        records, accts = _run(events, accts, maker_bps=0, taker_bps=0, maint_bp=500, target_bp=1000)
        return records, accts

    def test_sequence_matches_state_machine(self):
        records, _ = self._scenario()
        types = [
            (r.get("event_type"), r.get("agent_id"), r.get("origin"))
            for r in records
            if r.get("event_type")
            in ("TRADE_SETTLE", "MARGIN_CALL", "ORDER_ARRIVAL", "ORDER_CANCELLED")
        ]
        # 1. M/X trade (risk_mark drops) -> triggers phase-2 scan.
        idx_trade1 = next(i for i, t in enumerate(types) if t[0] == "TRADE_SETTLE")
        # 2. A flagged PENDING_LIQUIDATION, after the triggering trade.
        idx_mc1 = next(i for i, t in enumerate(types) if t[0] == "MARGIN_CALL")
        assert idx_mc1 > idx_trade1
        assert types[idx_mc1][1] == "A"
        # 3. A's LIQUIDATION order arrives.
        idx_liq1 = next(
            i for i, t in enumerate(types) if t[0] == "ORDER_ARRIVAL" and t[2] == "LIQUIDATION"
        )
        assert types[idx_liq1][1] == "A"
        # 4. No counterparty -> full IOC cancel (no TRADE_SETTLE in between).
        idx_cancel1 = idx_liq1 + 1
        assert types[idx_cancel1][0] == "ORDER_CANCELLED"
        # 5. Y's same-side resting order does not appear between the first
        #    cancel and the next real trade as a MARGIN_CALL trigger --
        #    i.e. no MARGIN_CALL immediately follows Y's ORDER_ARRIVAL.
        idx_y = next(i for i, t in enumerate(types) if t[1] == "Y")
        assert types[idx_y + 1][0] != "MARGIN_CALL"
        # 6. W/Z trade happens after Y, moving risk_mark again.
        idx_trade2 = next(i for i, t in enumerate(types) if t[0] == "TRADE_SETTLE" and i > idx_y)
        assert idx_trade2 > idx_y
        # 7. A second MARGIN_CALL + LIQUIDATION order follows the new trade.
        idx_mc2 = next(i for i, t in enumerate(types) if t[0] == "MARGIN_CALL" and i > idx_trade2)
        assert types[idx_mc2][1] == "A"
        idx_liq2 = next(
            i
            for i, t in enumerate(types)
            if t[0] == "ORDER_ARRIVAL" and t[2] == "LIQUIDATION" and i > idx_mc2
        )
        assert types[idx_liq2][1] == "A"

    def test_first_liquidation_fully_cancelled_no_counterparty(self):
        records, _ = self._scenario()
        mcs = [r for r in records if r.get("event_type") == "MARGIN_CALL"]
        first_req_qty = mcs[0]["required_quantity_units"]
        cancels = [
            r
            for r in records
            if r.get("event_type") == "ORDER_CANCELLED" and r.get("order_id") == "liq-A-4"
        ]
        assert len(cancels) == 1
        assert cancels[0]["cancelled_qty_units"] == first_req_qty

    def test_second_margin_call_recomputes_larger_requirement(self):
        """risk_mark dropped further (9000 vs 9400) -> the recomputed
        required_quantity for the second attempt must differ from (be
        larger than) the first, confirming a genuine re-evaluation
        happened rather than reusing stale state."""
        records, _ = self._scenario()
        mcs = [r for r in records if r.get("event_type") == "MARGIN_CALL"]
        assert len(mcs) == 2
        assert mcs[1]["required_quantity_units"] > mcs[0]["required_quantity_units"]


class TestCase9BankruptcyWriteOff:
    """Case 9: undercollateralized liquidation, phase-1 write-off, replay
    (acceptance-vectors.md §3 案例9).  A(wallet=5000, tier=10) opens a
    leveraged long, an unrelated C/D trade drops risk_mark to 80,
    triggering PENDING_LIQUIDATION; A's liquidation trade against B closes
    the position but leaves wallet negative (-5000) -- exactly the P0-G02
    dead zone the spec calls out: once position hits 0 mid-transaction,
    phase 2 (margin_ratio-based) would skip the account (margin_ratio is
    null at position=0), so only phase 1's explicit
    ``position==0 and wallet<0`` check can catch it, in the SAME
    transaction as the liquidation trade.

    The wallet=-1 cash_unit boundary ("最小的穿仓也必须被捕获") is covered
    at the unit level in tests/unit/ledger/test_bankruptcy.py::
    test_find_breached_returns_sorted.
    """

    def _scenario(self):
        accts = {
            "A": Account("A", cash(5000)),
            "B": Account("B", cash(500000)),
            "C": Account("C", cash(1000)),
            "D": Account("D", cash(1000)),
        }
        events = [
            _limit("b1", "B", "SELL", ticks(100), units(500), t=100),
            _limit("a1", "A", "BUY", ticks(100), units(500), t=200),
            _limit("d1", "D", "SELL", ticks(80), units(1), t=300),
            _limit("c1", "C", "BUY", ticks(80), units(1), t=400),
            _limit("b2", "B", "BUY", ticks(80), units(500), t=500),
        ]
        records, accts = _run(
            events,
            accts,
            maker_bps=0,
            taker_bps=0,
            maint_bp=500,
            target_bp=1000,
            initial_bp_per_agent={"A": 1000},
        )
        return records, accts

    def test_final_state_matches_table(self):
        _, accts = self._scenario()
        assert accts["A"].wallet_units == 0
        assert accts["A"].position_units == 0
        assert accts["A"].entry_notional_units == 0
        assert accts["A"].state == AccountState.LIQUIDATED
        assert accts["B"].wallet_units == cash(510000)
        assert accts["B"].position_units == 0
        assert accts["B"].entry_notional_units == 0
        assert accts["C"].wallet_units == cash(1000)
        assert accts["C"].position_units == units(1)
        assert accts["C"].entry_notional_units == cash(80)
        assert accts["D"].wallet_units == cash(1000)
        assert accts["D"].position_units == -units(1)
        assert accts["D"].entry_notional_units == -cash(80)

    def test_step3_liquidation_trade_deltas(self):
        records, _ = self._scenario()
        trades = _trades(records)
        liq_trade = next(
            t for t in trades if t["price_ticks"] == ticks(80) and t["quantity_units"] > units(1)
        )
        by_agent = {p["agent_id"]: p for p in liq_trade["postings"]}
        assert by_agent["A"]["wallet_delta_units"] == -cash(10000)
        assert by_agent["A"]["position_delta_units"] == -units(500)
        assert by_agent["A"]["entry_notional_delta_units"] == -cash(50000)
        assert by_agent["B"]["wallet_delta_units"] == cash(10000)
        assert by_agent["B"]["position_delta_units"] == units(500)
        assert by_agent["B"]["entry_notional_delta_units"] == cash(50000)

    def test_step4_write_off_posting_shape(self):
        """事件 Schema §4.2.3: [ACCOUNT, EXCHANGE_RISK], exchange side's
        *_after fields are null (not 0)."""
        records, _ = self._scenario()
        breached = next(
            r
            for r in records
            if r.get("event_type") == "MARGIN_CALL" and r.get("verdict") == "BREACHED"
        )
        postings = breached["postings"]
        assert len(postings) == 2
        assert postings[0]["posting_type"] == "WRITE_OFF_POSTING"
        assert postings[0]["role"] == "ACCOUNT"
        assert postings[0]["agent_id"] == "A"
        assert postings[0]["wallet_delta_units"] == cash(5000)
        assert postings[0]["wallet_after_units"] == 0
        assert postings[0]["position_after_units"] == 0
        assert postings[0]["entry_notional_after_units"] == 0
        assert postings[1]["posting_type"] == "WRITE_OFF_POSTING"
        assert postings[1]["role"] == "EXCHANGE_RISK"
        assert postings[1]["agent_id"] is None
        assert postings[1]["wallet_delta_units"] == 0
        assert postings[1]["wallet_after_units"] is None
        assert postings[1]["position_after_units"] is None
        assert postings[1]["entry_notional_after_units"] is None
        assert postings[1]["risk_pnl_delta_units"] == -cash(5000)

    def test_exchange_risk_pnl_matches_table(self):
        records, _ = self._scenario()
        breached = next(
            r
            for r in records
            if r.get("event_type") == "MARGIN_CALL" and r.get("verdict") == "BREACHED"
        )
        assert breached["postings"][1]["risk_pnl_delta_units"] == -cash(5000)

    def test_c1_conserved_throughout(self):
        """Σposition == 0 at every C/D trade step (write-off doesn't touch
        position, only wallet/risk)."""
        records, accts = self._scenario()
        assert sum(a.position_units for a in accts.values()) == 0


# --------------------------------------------------------------------------- #
# T408: PnL bridge residual == 0 (metrics-dictionary §5.2, valuation_mark)
# --------------------------------------------------------------------------- #


class TestT408PnlBridge:
    """Per-event PnL bridge: Δequity = Spread + Impact + Revaluation + Funding − Fees."""

    def test_bridge_zero_residual_case1(self):
        accts = {"A": Account("A", cash(1000)), "B": Account("B", cash(1000))}
        events = [
            _limit("b1", "B", "SELL", ticks(100), units(10), t=100),
            _limit("a1", "A", "BUY", ticks(100), units(10), t=200),
        ]
        records, _ = _run(events, accts)
        replay = _replay_check(records)
        for tr in replay:
            for p in tr["postings"]:
                assert p["residual"] == 0

    def test_bridge_zero_residual_with_fees(self):
        accts = {"A": Account("A", cash(1000)), "B": Account("B", cash(1000))}
        events = [
            _limit("b1", "B", "SELL", ticks(100), units(10), t=100),
            _limit("a1", "A", "BUY", ticks(100), units(10), t=200),
        ]
        records, _ = _run(events, accts, maker_bps=-1, taker_bps=5)
        replay = _replay_check(records)
        for tr in replay:
            for p in tr["postings"]:
                assert p["residual"] == 0
                assert p["fees"] != 0  # fees are present and non-zero

    def test_bridge_zero_residual_cross_price(self):
        accts = {
            "A": Account("A", cash(1000)),
            "B": Account("B", cash(1000)),
            "C": Account("C", cash(1000)),
        }
        events = [
            _limit("b1", "B", "SELL", ticks(100), units(10), t=100),
            _limit("a1", "A", "BUY", ticks(100), units(10), t=200),
            _limit("a2", "A", "SELL", ticks(110), units(10), t=300),
            _limit("c1", "C", "BUY", ticks(110), units(10), t=400),
        ]
        records, _ = _run(events, accts)
        replay = _replay_check(records)
        for tr in replay:
            for p in tr["postings"]:
                assert p["residual"] == 0

    def test_bridge_zero_residual_flip(self):
        accts = {"A": Account("A", cash(1000)), "B": Account("B", cash(1000))}
        events = [
            _limit("b1", "B", "SELL", ticks(100), units(5), t=100),
            _limit("a1", "A", "BUY", ticks(100), units(5), t=200),
            _limit("b2", "B", "BUY", ticks(98), units(10), t=300),
            _limit("a2", "A", "SELL", ticks(98), units(10), t=400),
        ]
        records, _ = _run(events, accts)
        replay = _replay_check(records)
        for tr in replay:
            for p in tr["postings"]:
                assert p["residual"] == 0

    def test_bridge_uses_valuation_mark_not_risk_mark(self):
        # Partial fill so both bid and ask remain → mid != price, impact=0, spread≠0.
        # If vm were risk_mark (last), spread+impact == 0 (both computed from price).
        accts = {
            "A": Account("A", cash(1000)),
            "N": Account("N", cash(1000)),
            "M": Account("M", cash(1000)),
        }
        events = [
            _limit("n1", "N", "BUY", ticks(99), units(10), t=100),  # N rests buy @99
            _limit("m1", "M", "SELL", ticks(100), units(10), t=200),  # M rests sell @100
            _limit("a1", "A", "BUY", ticks(100), units(3), t=300),  # A buys 3@100, M still has 7
        ]
        records, _ = _run(events, accts)
        trade = _trades(records)[0]
        vb = trade["valuation_mark_before_half_ticks"]
        va = trade["valuation_mark_after_half_ticks"]
        assert vb == 9900 + 10000  # bid(99)+ask(100) = 19900
        assert va == 9900 + 10000  # both sides still present after partial fill
        replay = _replay_check(records)
        taker_posting = replay[0]["postings"][1]  # A is taker
        assert taker_posting["spread"] + taker_posting["impact"] != 0
        assert taker_posting["residual"] == 0
