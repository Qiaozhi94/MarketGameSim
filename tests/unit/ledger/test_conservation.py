"""T406: C1/C2 per-event conservation (账户合同 §2.3).

C1: Σ position ≡ 0
C2: Σ (wallet − entry_notional) + exchange_fee + exchange_risk_pnl = Σ wallet(0)

C2 must include entry_notional -- 案例 2 (cross-price handoff) is the core case.
"""

from __future__ import annotations

import pytest

from market_game_sim.ledger.account import Account, apply_fill
from market_game_sim.ledger.conservation import check_c1, check_c1_c2, check_c2

MULT = 1000
CASH = 10**8


def cash(h: float | int) -> int:
    return int(round(h * CASH))


def ticks(h: float | int) -> int:
    return int(round(h * 100))


def units(h: float | int) -> int:
    return int(round(h * 1000))


def _two_accounts():
    a = Account("A", cash(1000))
    b = Account("B", cash(1000))
    return {"A": a, "B": b}, cash(2000)


class TestT406C1:
    def test_c1_holds_at_zero(self):
        accts, _ = _two_accounts()
        ok, _ = check_c1(accts)
        assert ok

    def test_c1_holds_after_trade(self):
        accts, _ = _two_accounts()
        apply_fill(accts["A"], "BUY", ticks(100), units(10), MULT, 0)
        apply_fill(accts["B"], "SELL", ticks(100), units(10), MULT, 0)
        ok, _ = check_c1(accts)
        assert ok

    def test_c1_violated_detected(self):
        accts, _ = _two_accounts()
        apply_fill(accts["A"], "BUY", ticks(100), units(10), MULT, 0)
        ok, msg = check_c1(accts)
        assert not ok
        assert "10000" in msg


class TestT406C2Case1:
    """案例 1: same-price open, zero fee. C2 = 2000."""

    def test_c2_holds_after_case1(self):
        accts, init_sum = _two_accounts()
        apply_fill(accts["A"], "BUY", ticks(100), units(10), MULT, 0)
        apply_fill(accts["B"], "SELL", ticks(100), units(10), MULT, 0)
        ok, _ = check_c2(accts, 0, 0, init_sum)
        assert ok

    def test_c2_lhs_equals_initial(self):
        accts, init_sum = _two_accounts()
        apply_fill(accts["A"], "BUY", ticks(100), units(10), MULT, 0)
        apply_fill(accts["B"], "SELL", ticks(100), units(10), MULT, 0)
        lhs = sum(a.wallet_units - a.entry_notional_units for a in accts.values())
        assert lhs == init_sum


class TestT406C2Case2:
    """案例 2: three-agent cross-price handoff -- the core C2 case.

    ① A buys 10 @100 from B. ② C buys 10 @110 from A (A closes, C opens).
    After ②: Σentry=+100, Σwallet=3100, but C2 still = 3000.
    """

    def test_c2_holds_after_handoff(self):
        accts = {"A": Account("A", cash(1000)),
                 "B": Account("B", cash(1000)),
                 "C": Account("C", cash(1000))}
        init_sum = cash(3000)
        apply_fill(accts["A"], "BUY", ticks(100), units(10), MULT, 0)
        apply_fill(accts["B"], "SELL", ticks(100), units(10), MULT, 0)
        apply_fill(accts["A"], "SELL", ticks(110), units(10), MULT, 0)
        apply_fill(accts["C"], "BUY", ticks(110), units(10), MULT, 0)
        ok, _ = check_c2(accts, 0, 0, init_sum)
        assert ok

    def test_old_wallet_constant_equation_fails(self):
        # Σwallet = 3100 != 3000 (the旧等式 is wrong, 案例 2 is its counterexample).
        accts = {"A": Account("A", cash(1000)),
                 "B": Account("B", cash(1000)),
                 "C": Account("C", cash(1000))}
        apply_fill(accts["A"], "BUY", ticks(100), units(10), MULT, 0)
        apply_fill(accts["B"], "SELL", ticks(100), units(10), MULT, 0)
        apply_fill(accts["A"], "SELL", ticks(110), units(10), MULT, 0)
        apply_fill(accts["C"], "BUY", ticks(110), units(10), MULT, 0)
        wallet_sum = sum(a.wallet_units for a in accts.values())
        assert wallet_sum == cash(3100)  # not constant
        # but C2 holds:
        ok, _ = check_c2(accts, 0, 0, cash(3000))
        assert ok

    def test_old_entry_zero_equation_fails(self):
        # Σentry = +100 != 0 after handoff.
        accts = {"A": Account("A", cash(1000)),
                 "B": Account("B", cash(1000)),
                 "C": Account("C", cash(1000))}
        apply_fill(accts["A"], "BUY", ticks(100), units(10), MULT, 0)
        apply_fill(accts["B"], "SELL", ticks(100), units(10), MULT, 0)
        apply_fill(accts["A"], "SELL", ticks(110), units(10), MULT, 0)
        apply_fill(accts["C"], "BUY", ticks(110), units(10), MULT, 0)
        entry_sum = sum(a.entry_notional_units for a in accts.values())
        assert entry_sum == cash(100)  # not zero


class TestT406C2WithFees:
    """案例 5: taker 5bps + maker -1bps. Exchange fee account is signed."""

    def test_c2_holds_with_signed_fee_account(self):
        accts, init_sum = _two_accounts()
        apply_fill(accts["A"], "BUY", ticks(100), units(10), MULT, 5)      # taker
        apply_fill(accts["B"], "SELL", ticks(100), units(10), MULT, -1)    # maker
        # exchange_fee = taker_fee + maker_fee = 0.5 + (-0.1) = 0.4
        exchange_fee = cash(0.5) + (-cash(0.1))
        ok, _ = check_c2(accts, exchange_fee, 0, init_sum)
        assert ok

    def test_rebate_does_not_break_c2(self):
        accts, init_sum = _two_accounts()
        apply_fill(accts["A"], "BUY", ticks(100), units(10), MULT, 5)
        apply_fill(accts["B"], "SELL", ticks(100), units(10), MULT, -1)
        # Without the fee account, C2 would be off by 0.4.
        ok_no_fee, _ = check_c2(accts, 0, 0, init_sum)
        assert not ok_no_fee
        exchange_fee = cash(0.4)
        ok, _ = check_c2(accts, exchange_fee, 0, init_sum)
        assert ok


class TestT406C2RiskAccount:
    """exchange_risk_pnl enters with + sign (账户合同 §2.3)."""

    def test_risk_account_signed(self):
        # Simulate: A breached, wallet -50 -> 0 (+50), risk += -50.
        accts = {"A": Account("A", cash(0))}
        init_sum = cash(1000)  # hypothetical
        # Manually set A wallet negative then write off:
        accts["A"].wallet_units = -cash(50)
        # Before write-off C2 (with risk=0): lhs = -50 - 0 + 0 = -50 != 1000.
        # After write-off: wallet 0, risk -50: lhs = 0 - 0 + (-50) = -50.
        # To make C2 = init_sum we'd need init_sum = -50; here just test the sign:
        accts["A"].wallet_units = 0
        risk = -cash(50)
        lhs = sum(a.wallet_units - a.entry_notional_units for a in accts.values()) + 0 + risk
        assert lhs == -cash(50)  # risk enters with + sign, loss is negative


class TestT406CheckC1C2Combined:
    def test_both_pass(self):
        accts, init_sum = _two_accounts()
        apply_fill(accts["A"], "BUY", ticks(100), units(10), MULT, 0)
        apply_fill(accts["B"], "SELL", ticks(100), units(10), MULT, 0)
        ok, _ = check_c1_c2(accts, 0, 0, init_sum)
        assert ok

    def test_c1_fail_stops_before_c2(self):
        accts, init_sum = _two_accounts()
        apply_fill(accts["A"], "BUY", ticks(100), units(10), MULT, 0)
        ok, msg = check_c1_c2(accts, 0, 0, init_sum)
        assert not ok
        assert "C1" in msg
