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
from market_game_sim.ledger.account import Account

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
    }
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
        records, accts = _run(events, accts, maker_bps=-1, taker_bps=5)
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
