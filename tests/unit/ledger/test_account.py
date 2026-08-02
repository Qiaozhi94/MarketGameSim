"""T401/T402/T403: Account entity, entry_notional update, dual-notch equity.

Integer-exact assertions against acceptance-vectors §4 (BENCH-001).

BENCH-001: tick_size=0.01, min_quantity=0.001, cash_unit=1e-8, MULT=1000.
  price 100.00 human -> 10000 ticks
  qty 10 human       -> 10000 qty_units
  cash 1000 human    -> 100000000000 cash_units (1e11)
  notional(100, 10)  -> 1e11 cash_units
"""

from __future__ import annotations

from market_game_sim.ledger.account import (
    Account,
    AccountState,
    apply_fill,
    initial_margin_bp_for_tier,
    margin_ratio_bp,
    risk_equity,
    unrealized_pnl_at_risk_mark,
    valuation_equity,
)

MULT = 1000
CASH = 10**8  # 1 human cash unit


def cash(human: float | int) -> int:
    return int(round(human * CASH))


def ticks(human_price: float | int) -> int:
    return int(round(human_price * 100))


def units(human_qty: float | int) -> int:
    return int(round(human_qty * 1000))


# --------------------------------------------------------------------------- #
# T401: account entity fields
# --------------------------------------------------------------------------- #


class TestT401AccountEntity:
    def test_default_state_active(self):
        a = Account(agent_id="A", wallet_units=cash(1000))
        assert a.state is AccountState.ACTIVE
        assert a.position_units == 0
        assert a.entry_notional_units == 0
        assert a.reserved_units == 0
        assert a.realized_pnl_units == 0
        assert a.liquidation_generation == 0
        assert a.chain_id is None
        assert a.chain_depth is None

    def test_all_states_present(self):
        assert AccountState.ACTIVE
        assert AccountState.PENDING_LIQUIDATION
        assert AccountState.LIQUIDATED

    def test_state_enum_values_match_schema(self):
        assert AccountState.ACTIVE.value == "ACTIVE"
        assert AccountState.PENDING_LIQUIDATION.value == "PENDING_LIQUIDATION"
        assert AccountState.LIQUIDATED.value == "LIQUIDATED"


# --------------------------------------------------------------------------- #
# T402: entry_notional update -- same / reverse / flip
# --------------------------------------------------------------------------- #


class TestT402SameDirectionOpen:
    """案例 1: A buys 10 @ 100 (taker), zero fee."""

    def test_case1_deltas_integer_exact(self):
        a = Account(agent_id="A", wallet_units=cash(1000))
        d = apply_fill(a, "BUY", ticks(100), units(10), MULT, fee_bps=0)
        assert d["wallet_delta_units"] == 0
        assert d["position_delta_units"] == units(10)  # +10000
        assert d["entry_notional_delta_units"] == 1e11  # +100000000000
        assert d["realized_pnl_delta_units"] == 0
        assert d["fee_delta_units"] == 0

    def test_case1_after_state(self):
        a = Account(agent_id="A", wallet_units=cash(1000))
        apply_fill(a, "BUY", ticks(100), units(10), MULT, fee_bps=0)
        assert a.wallet_units == cash(1000)
        assert a.position_units == units(10)
        assert a.entry_notional_units == 1e11
        assert a.realized_pnl_units == 0

    def test_short_open_symmetric(self):
        b = Account(agent_id="B", wallet_units=cash(1000))
        d = apply_fill(b, "SELL", ticks(100), units(10), MULT, fee_bps=0)
        assert d["position_delta_units"] == -units(10)
        assert d["entry_notional_delta_units"] == -1e11
        assert b.position_units == -units(10)
        assert b.entry_notional_units == -1e11


class TestT402ReverseClose:
    """案例 2 step 2 + 案例 3 partial close."""

    def test_case2_full_close_at_different_price(self):
        # A built +10 @100, now sells 10 @110 (full close, realizes +100).
        a = Account(
            agent_id="A",
            wallet_units=cash(1000),
            position_units=units(10),
            entry_notional_units=cash(1000),
        )
        d = apply_fill(a, "SELL", ticks(110), units(10), MULT, fee_bps=0)
        assert d["wallet_delta_units"] == cash(100)  # +1e10
        assert d["position_delta_units"] == -units(10)
        assert d["entry_notional_delta_units"] == -1e11
        assert d["realized_pnl_delta_units"] == cash(100)
        assert a.position_units == 0
        assert a.entry_notional_units == 0
        assert a.wallet_units == cash(1100)

    def test_case3_partial_close(self):
        # A +10 @100, sells 4 @105 -> realized +20, entry 1000->600.
        a = Account(
            agent_id="A",
            wallet_units=cash(1000),
            position_units=units(10),
            entry_notional_units=cash(1000),
        )
        d = apply_fill(a, "SELL", ticks(105), units(4), MULT, fee_bps=0)
        assert d["wallet_delta_units"] == cash(20)  # +2e9
        assert d["position_delta_units"] == -units(4)  # -4000
        assert d["entry_notional_delta_units"] == -4e10  # -40000000000
        assert d["realized_pnl_delta_units"] == cash(20)
        assert a.position_units == units(6)
        assert a.entry_notional_units == cash(600)
        assert a.wallet_units == cash(1020)

    def test_case3_short_partial_close_symmetric(self):
        # B -10 @100, buys 4 @105 -> realized -20, entry -1000->-600.
        b = Account(
            agent_id="B",
            wallet_units=cash(1000),
            position_units=-units(10),
            entry_notional_units=-cash(1000),
        )
        d = apply_fill(b, "BUY", ticks(105), units(4), MULT, fee_bps=0)
        assert d["wallet_delta_units"] == -cash(20)
        assert d["position_delta_units"] == units(4)
        assert d["entry_notional_delta_units"] == 4e10
        assert d["realized_pnl_delta_units"] == -cash(20)
        assert b.position_units == -units(6)
        assert b.entry_notional_units == -cash(600)

    def test_entry_notional_proportional_cut(self):
        # Close 4 of 10 -> entry cuts by 4/10 (案例 3 多空对称).
        a = Account(
            agent_id="A",
            wallet_units=cash(1000),
            position_units=units(10),
            entry_notional_units=cash(1000),
        )
        apply_fill(a, "SELL", ticks(105), units(4), MULT, fee_bps=0)
        assert a.entry_notional_units == cash(600)  # 1000 * 6/10


class TestT402Flip:
    """案例 4: A +5 @100, sells 10 @98 -> close 5 + open 5 short."""

    def test_case4_flip_deltas(self):
        a = Account(
            agent_id="A",
            wallet_units=cash(1000),
            position_units=units(5),
            entry_notional_units=cash(500),
        )
        d = apply_fill(a, "SELL", ticks(98), units(10), MULT, fee_bps=0)
        assert d["wallet_delta_units"] == -cash(10)  # -1e9
        assert d["position_delta_units"] == -units(10)  # -10000
        assert d["entry_notional_delta_units"] == -9.9e10  # -99000000000
        assert d["realized_pnl_delta_units"] == -cash(10)

    def test_case4_flip_after_state(self):
        a = Account(
            agent_id="A",
            wallet_units=cash(1000),
            position_units=units(5),
            entry_notional_units=cash(500),
        )
        apply_fill(a, "SELL", ticks(98), units(10), MULT, fee_bps=0)
        assert a.position_units == -units(5)
        assert a.entry_notional_units == -cash(490)  # -5 * 98
        assert a.wallet_units == cash(990)
        assert a.realized_pnl_units == -cash(10)

    def test_flip_zero_position_opens_new(self):
        # From 0, sell 10 -> pure open short, no realized.
        a = Account(agent_id="A", wallet_units=cash(1000))
        d = apply_fill(a, "SELL", ticks(98), units(10), MULT, fee_bps=0)
        assert d["realized_pnl_delta_units"] == 0
        assert a.position_units == -units(10)
        assert a.entry_notional_units == -9.8e10

    def test_flip_long_to_short_at_loss(self):
        # +3 @100, sell 5 @95 -> close 3 (realized -15), open 2 short @95.
        a = Account(
            agent_id="A",
            wallet_units=cash(1000),
            position_units=units(3),
            entry_notional_units=cash(300),
        )
        apply_fill(a, "SELL", ticks(95), units(5), MULT, fee_bps=0)
        assert a.position_units == -units(2)
        assert a.entry_notional_units == -cash(190)  # -2 * 95
        assert a.realized_pnl_units == -cash(15)  # 3 * (95-100)
        assert a.wallet_units == cash(985)

    def test_flip_short_to_long(self):
        # -4 @100, buy 6 @105 -> close 4 (realized -20), open 2 long @105.
        a = Account(
            agent_id="A",
            wallet_units=cash(1000),
            position_units=-units(4),
            entry_notional_units=-cash(400),
        )
        apply_fill(a, "BUY", ticks(105), units(6), MULT, fee_bps=0)
        assert a.position_units == units(2)
        assert a.entry_notional_units == cash(210)  # 2 * 105
        assert a.realized_pnl_units == -cash(20)  # 4 * (105-100) * (-1)...
        # short closed higher: 4*(105-100)*sign(-1) = 4*5*(-1) = -20


class TestT402EntryNotionalRemainder:
    """avg_entry rounds toward zero; remainder stays in entry_notional."""

    def test_remainder_stays_on_partial_close(self):
        # +3 @100 -> entry 300. Close 2: avg=100 exact, entry 300->100.
        # Now +1 @100 (entry 100). Close 1 @100: avg=100, entry 100->0.
        # Use non-exact: +3 @101 -> entry 303. Close 1: avg = 303//3 = 101,
        # entry 303 -> 303 - 1*101 = 202. position 2.
        a = Account(
            agent_id="A",
            wallet_units=cash(1000),
            position_units=units(3),
            entry_notional_units=cash(303),
        )
        apply_fill(a, "SELL", ticks(101), units(1), MULT, fee_bps=0)
        # avg_entry = 303//3 = 101 (human) -> in cash/qty: cash(303)//units(3)
        avg = cash(303) // units(3)
        assert avg == cash(101) // units(1)  # per-unit
        assert a.entry_notional_units == cash(303) - avg * units(1)  # 202

    def test_c2_unaffected_by_remainder(self):
        # Remainder in entry_notional does not break C2 (账户合同 §2.1).
        a = Account(
            agent_id="A",
            wallet_units=cash(1000),
            position_units=units(3),
            entry_notional_units=cash(303),
        )
        before = a.wallet_units - a.entry_notional_units
        apply_fill(a, "SELL", ticks(101), units(1), MULT, fee_bps=0)
        after = a.wallet_units - a.entry_notional_units
        # Δ(wallet - entry) = realized - 0 (fee) - entry_delta
        # = realized - (-closed*avg*sign) ... = closed*price*MULT = price notional
        assert after - before == units(1) * ticks(101) * MULT  # = notional of close


# --------------------------------------------------------------------------- #
# T402: fees (combined with fills)
# --------------------------------------------------------------------------- #


class TestT402Fees:
    """案例 5: taker 5 bps, maker -1 bps."""

    def test_taker_fee_deducted_from_wallet(self):
        # Buy 10 @100, taker 5 bps. fee = 1000 * 5/10000 = 0.5.
        a = Account(agent_id="A", wallet_units=cash(1000))
        d = apply_fill(a, "BUY", ticks(100), units(10), MULT, fee_bps=5)
        assert d["fee_delta_units"] == cash(0.5)  # 50000000
        assert d["wallet_delta_units"] == -cash(0.5)  # realized 0 - fee
        assert a.wallet_units == cash(999.5)

    def test_maker_rebate_added_to_wallet(self):
        # Maker -1 bps: fee = round_fee(notional, -1) = ceil(-1e11/10000) = -1e7.
        b = Account(agent_id="B", wallet_units=cash(1000))
        d = apply_fill(b, "SELL", ticks(100), units(10), MULT, fee_bps=-1)
        assert d["fee_delta_units"] == -cash(0.1)  # -10000000
        assert d["wallet_delta_units"] == cash(0.1)  # 0 - (-0.1)
        assert b.wallet_units == cash(1000.1)

    def test_case5_taker_and_maker_signs(self):
        # A taker buy 10 @100 (5bps), B maker sell (-1bps).
        a = Account(agent_id="A", wallet_units=cash(1000))
        b = Account(agent_id="B", wallet_units=cash(1000))
        da = apply_fill(a, "BUY", ticks(100), units(10), MULT, fee_bps=5)
        db = apply_fill(b, "SELL", ticks(100), units(10), MULT, fee_bps=-1)
        assert da["fee_delta_units"] == cash(0.5)
        assert db["fee_delta_units"] == -cash(0.1)
        # exchange net fee = 0.5 + (-0.1) = 0.4
        assert da["fee_delta_units"] + db["fee_delta_units"] == cash(0.4)


# --------------------------------------------------------------------------- #
# T403: unrealized PnL + dual-notch equity
# --------------------------------------------------------------------------- #


class TestT403Equity:
    def test_case1_equity_zero_unrealized(self):
        # A +10 @100, mark 100 -> unrealized 0, equity = wallet = 1000.
        a = Account(
            agent_id="A",
            wallet_units=cash(1000),
            position_units=units(10),
            entry_notional_units=cash(1000),
        )
        assert unrealized_pnl_at_risk_mark(a, ticks(100), MULT) == 0
        assert risk_equity(a, ticks(100), MULT) == cash(1000)

    def test_case2_unrealized_after_price_move(self):
        # B -10 @100, mark 110 -> unrealized = -10*110 - (-1000) = -100.
        b = Account(
            agent_id="B",
            wallet_units=cash(1000),
            position_units=-units(10),
            entry_notional_units=-cash(1000),
        )
        assert unrealized_pnl_at_risk_mark(b, ticks(110), MULT) == -cash(100)
        assert risk_equity(b, ticks(110), MULT) == cash(900)

    def test_long_unrealized_positive(self):
        a = Account(
            agent_id="A",
            wallet_units=cash(1000),
            position_units=units(10),
            entry_notional_units=cash(1000),
        )
        assert unrealized_pnl_at_risk_mark(a, ticks(105), MULT) == cash(50)

    def test_valuation_vs_risk_differ(self):
        # risk_mark (last) = 110, valuation mid = 10950 half-ticks (109.50).
        b = Account(
            agent_id="B",
            wallet_units=cash(1000),
            position_units=-units(10),
            entry_notional_units=-cash(1000),
        )
        re = risk_equity(b, ticks(110), MULT)
        ve = valuation_equity(b, ticks(110) * 2 - 100, MULT)  # mid 109.50
        assert re == cash(900)
        # mid 109.50: unrealized = -10*109.50 - (-1000) = -1095+1000 = -95
        assert ve == cash(905)

    def test_valuation_half_tick_integer(self):
        # mid 100.50 -> half_ticks 20100. position +10 @100.
        a = Account(
            agent_id="A",
            wallet_units=cash(1000),
            position_units=units(10),
            entry_notional_units=cash(1000),
        )
        ve = valuation_equity(a, 20100, MULT)
        # unrealized = 10 * 100.50 - 1000 = 5 -> equity 1005
        assert ve == cash(1005)

    def test_no_position_equity_equals_wallet(self):
        a = Account(agent_id="A", wallet_units=cash(500))
        assert risk_equity(a, ticks(100), MULT) == cash(500)
        assert valuation_equity(a, 20000, MULT) == cash(500)


class TestT403MarginRatio:
    def test_case2_b_margin_ratio_8181(self):
        # B -10 @100, mark 110: equity 900, notional 1100, ratio 8181 bp.
        b = Account(
            agent_id="B",
            wallet_units=cash(1000),
            position_units=-units(10),
            entry_notional_units=-cash(1000),
        )
        assert margin_ratio_bp(b, ticks(110), MULT) == 8181

    def test_case2_c_margin_ratio_9090(self):
        # C +10 @110, mark 110: equity 1000-... C wallet 1000, entry 1100.
        # equity = 1000 + 10*110 - 1100 = 1000. notional 1100. ratio 9090.
        c = Account(
            agent_id="C",
            wallet_units=cash(1000),
            position_units=units(10),
            entry_notional_units=cash(1100),
        )
        assert margin_ratio_bp(c, ticks(110), MULT) == 9090

    def test_no_position_returns_none(self):
        a = Account(agent_id="A", wallet_units=cash(1000))
        assert margin_ratio_bp(a, ticks(100), MULT) is None

    def test_initial_margin_bp_for_tier(self):
        assert initial_margin_bp_for_tier(1) == 10000
        assert initial_margin_bp_for_tier(3) == 3334
        assert initial_margin_bp_for_tier(10) == 1000
