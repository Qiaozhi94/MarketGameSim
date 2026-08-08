"""T201/T202/T202b (§3.3): dedicated unit tests for risk.py's two-phase scan.

Previously only covered indirectly via integration scenarios (test_ob8_
risk_check.py, test_acceptance_vectors.py's Case 8/9, test_verify_
liquidation.py).  These tests exercise run_phase1_breaches/
run_phase2_margin_scan directly against hand-built Account objects, so the
orchestration logic (which accounts get touched, verdict transitions,
liquidation_generation/chain_id bookkeeping, no-spam-on-unchanged-qty) is
protected independent of the matching engine.

qty math itself (required_liquidation_qty) is already covered in
test_liquidation.py; these tests treat it as an oracle (call it directly
to get the expected value) rather than re-deriving the binary search by
hand -- risk.py's own job is orchestration, not the liquidation math.
"""

from __future__ import annotations

from market_game_sim.ledger.account import Account, AccountState
from market_game_sim.ledger.liquidation import required_liquidation_qty
from market_game_sim.ledger.risk import run_phase1_breaches, run_phase2_margin_scan

MULT = 1000
PRICE = 100  # risk_mark_ticks used throughout unless stated otherwise
MAINT_BP = 500
TARGET_BP = 1000
TAKER_BPS = 5


def _long(agent_id: str, wallet: int, qty: int = 100, entry_price: int = PRICE) -> Account:
    return Account(
        agent_id=agent_id,
        wallet_units=wallet,
        position_units=qty,
        entry_notional_units=qty * entry_price * MULT,
    )


# --------------------------------------------------------------------------- #
# Phase 1: breach capture
# --------------------------------------------------------------------------- #


class TestPhase1Breaches:
    def test_zero_position_negative_wallet_is_breached(self):
        accounts = {"A": Account("A", wallet_units=-100, position_units=0)}
        records, risk_pnl = run_phase1_breaches(
            accounts,
            exchange_risk_pnl_units=0,
            touched_agent_ids=["A"],
            caused_by_event_id="e1_0",
            risk_mark_event_id="e1_1",
        )
        assert len(records) == 1
        assert records[0].agent_id == "A"
        assert records[0].verdict == "BREACHED"
        assert accounts["A"].wallet_units == 0
        assert accounts["A"].state == AccountState.LIQUIDATED
        assert risk_pnl == -100

    def test_zero_position_nonnegative_wallet_not_breached(self):
        accounts = {"A": Account("A", wallet_units=0, position_units=0)}
        records, risk_pnl = run_phase1_breaches(
            accounts,
            exchange_risk_pnl_units=0,
            touched_agent_ids=["A"],
            caused_by_event_id="e1_0",
            risk_mark_event_id="e1_1",
        )
        assert records == []
        assert risk_pnl == 0
        assert accounts["A"].state == AccountState.ACTIVE

    def test_nonzero_position_negative_wallet_not_caught_by_phase1(self):
        """P0-G02 dead zone: position != 0 means margin_ratio_bp is
        well-defined, so phase 1 must NOT try to write it off -- that's
        phase 2's job (or, once position hits 0, a later phase 1 pass)."""
        accounts = {"A": _long("A", wallet=-50, qty=10)}
        records, risk_pnl = run_phase1_breaches(
            accounts,
            exchange_risk_pnl_units=0,
            touched_agent_ids=["A"],
            caused_by_event_id="e1_0",
            risk_mark_event_id="e1_1",
        )
        assert records == []
        assert risk_pnl == 0
        assert accounts["A"].wallet_units == -50
        assert accounts["A"].state == AccountState.ACTIVE

    def test_already_liquidated_account_skipped(self):
        acct = Account("A", wallet_units=-100, position_units=0)
        acct.state = AccountState.LIQUIDATED
        accounts = {"A": acct}
        records, risk_pnl = run_phase1_breaches(
            accounts,
            exchange_risk_pnl_units=0,
            touched_agent_ids=["A"],
            caused_by_event_id="e1_0",
            risk_mark_event_id="e1_1",
        )
        assert records == []
        assert risk_pnl == 0
        assert accounts["A"].wallet_units == -100  # untouched, not re-written-off

    def test_untouched_account_not_processed_even_if_breached(self):
        accounts = {
            "A": Account("A", wallet_units=-100, position_units=0),
            "B": Account("B", wallet_units=100, position_units=0),
        }
        records, risk_pnl = run_phase1_breaches(
            accounts,
            exchange_risk_pnl_units=0,
            touched_agent_ids=["B"],
            caused_by_event_id="e1_0",
            risk_mark_event_id="e1_1",
        )
        assert records == []
        assert accounts["A"].state == AccountState.ACTIVE
        assert accounts["A"].wallet_units == -100

    def test_multiple_accounts_same_batch_all_breached_sorted(self):
        """Batch scenario (CLAUDE.md rule): several accounts breach in the
        SAME call, must all be processed and returned sorted by agent_id."""
        accounts = {
            "Z": Account("Z", wallet_units=-30, position_units=0),
            "A": Account("A", wallet_units=-10, position_units=0),
            "M": Account("M", wallet_units=-20, position_units=0),
            "OK": Account("OK", wallet_units=5, position_units=0),
        }
        records, risk_pnl = run_phase1_breaches(
            accounts,
            exchange_risk_pnl_units=0,
            touched_agent_ids=["Z", "A", "M", "OK"],
            caused_by_event_id="e1_0",
            risk_mark_event_id="e1_1",
        )
        assert [r.agent_id for r in records] == ["A", "M", "Z"]
        assert risk_pnl == -60
        for aid in ("A", "M", "Z"):
            assert accounts[aid].state == AccountState.LIQUIDATED
            assert accounts[aid].wallet_units == 0
        assert accounts["OK"].state == AccountState.ACTIVE


# --------------------------------------------------------------------------- #
# Phase 2: margin scan
# --------------------------------------------------------------------------- #


class TestPhase2MarginScan:
    def test_below_maint_transitions_active_to_pending_liquidation(self):
        acct = _long("A", wallet=400_000, qty=100)  # ratio 400bp < 500bp maint
        accounts = {"A": acct}
        expected_qty = required_liquidation_qty(acct, PRICE, TARGET_BP, TAKER_BPS, MULT)
        records = run_phase2_margin_scan(
            accounts,
            risk_mark_ticks=PRICE,
            maint_bp=MAINT_BP,
            target_bp=TARGET_BP,
            taker_bps=TAKER_BPS,
            mult=MULT,
            caused_by_event_id="e1_0",
            risk_mark_event_id="e1_1",
            parent_chain_id=None,
            parent_chain_depth=None,
            parent_agent_id=None,
            this_event_id="mc1",
        )
        assert len(records) == 1
        r = records[0]
        assert r.agent_id == "A"
        assert r.verdict == "PENDING_LIQUIDATION"
        assert r.required_quantity_units == expected_qty
        assert r.margin_ratio_bp == 400
        assert acct.state == AccountState.PENDING_LIQUIDATION
        assert acct.liquidation_generation == 1
        assert r.chain_id == "mc1"
        assert r.chain_depth == 0

    def test_above_maint_healthy_position_not_touched(self):
        acct = _long("A", wallet=600_000, qty=100)  # ratio 600bp >= 500bp maint
        accounts = {"A": acct}
        records = run_phase2_margin_scan(
            accounts,
            risk_mark_ticks=PRICE,
            maint_bp=MAINT_BP,
            target_bp=TARGET_BP,
            taker_bps=TAKER_BPS,
            mult=MULT,
            caused_by_event_id="e1_0",
            risk_mark_event_id="e1_1",
            parent_chain_id=None,
            parent_chain_depth=None,
            parent_agent_id=None,
            this_event_id="mc1",
        )
        assert records == []
        assert acct.state == AccountState.ACTIVE
        assert acct.liquidation_generation == 0

    def test_zero_position_account_skipped(self):
        """P0-G02 boundary from phase 2's side: margin_ratio_bp is None at
        position==0, so phase 2 must skip it (only phase 1 can write it off
        once it's carrying a negative wallet)."""
        acct = Account("A", wallet_units=-100, position_units=0)
        accounts = {"A": acct}
        records = run_phase2_margin_scan(
            accounts,
            risk_mark_ticks=PRICE,
            maint_bp=MAINT_BP,
            target_bp=TARGET_BP,
            taker_bps=TAKER_BPS,
            mult=MULT,
            caused_by_event_id="e1_0",
            risk_mark_event_id="e1_1",
            parent_chain_id=None,
            parent_chain_depth=None,
            parent_agent_id=None,
            this_event_id="mc1",
        )
        assert records == []
        assert acct.state == AccountState.ACTIVE

    def test_liquidated_account_skipped_even_if_position_nonzero(self):
        acct = _long("A", wallet=1, qty=100)
        acct.state = AccountState.LIQUIDATED
        accounts = {"A": acct}
        records = run_phase2_margin_scan(
            accounts,
            risk_mark_ticks=PRICE,
            maint_bp=MAINT_BP,
            target_bp=TARGET_BP,
            taker_bps=TAKER_BPS,
            mult=MULT,
            caused_by_event_id="e1_0",
            risk_mark_event_id="e1_1",
            parent_chain_id=None,
            parent_chain_depth=None,
            parent_agent_id=None,
            this_event_id="mc1",
        )
        assert records == []

    def test_pending_liquidation_unchanged_qty_not_reemitted(self):
        """No-spam invariant: if a second scan finds the SAME required
        quantity (risk_mark unchanged), it must not re-emit a MARGIN_CALL
        or bump liquidation_generation again."""
        acct = _long("A", wallet=400_000, qty=100)
        accounts = {"A": acct}
        run_phase2_margin_scan(
            accounts,
            risk_mark_ticks=PRICE,
            maint_bp=MAINT_BP,
            target_bp=TARGET_BP,
            taker_bps=TAKER_BPS,
            mult=MULT,
            caused_by_event_id="e1_0",
            risk_mark_event_id="e1_1",
            parent_chain_id=None,
            parent_chain_depth=None,
            parent_agent_id=None,
            this_event_id="mc1",
        )
        gen_after_first = acct.liquidation_generation
        records = run_phase2_margin_scan(
            accounts,
            risk_mark_ticks=PRICE,
            maint_bp=MAINT_BP,
            target_bp=TARGET_BP,
            taker_bps=TAKER_BPS,
            mult=MULT,
            caused_by_event_id="e2_0",
            risk_mark_event_id="e2_1",
            parent_chain_id=None,
            parent_chain_depth=None,
            parent_agent_id=None,
            this_event_id="mc2",
        )
        assert records == []
        assert acct.liquidation_generation == gen_after_first

    def test_pending_liquidation_changed_qty_reemits_new_generation(self):
        """Recount: risk_mark moves further, required_quantity changes ->
        a NEW MARGIN_CALL with a bumped generation (Case 8's step 6-7)."""
        acct = _long("A", wallet=400_000, qty=100)
        accounts = {"A": acct}
        run_phase2_margin_scan(
            accounts,
            risk_mark_ticks=PRICE,
            maint_bp=MAINT_BP,
            target_bp=TARGET_BP,
            taker_bps=TAKER_BPS,
            mult=MULT,
            caused_by_event_id="e1_0",
            risk_mark_event_id="e1_1",
            parent_chain_id=None,
            parent_chain_depth=None,
            parent_agent_id=None,
            this_event_id="mc1",
        )
        gen_after_first = acct.liquidation_generation
        worse_price = PRICE - 20
        expected_qty = required_liquidation_qty(acct, worse_price, TARGET_BP, TAKER_BPS, MULT)
        records = run_phase2_margin_scan(
            accounts,
            risk_mark_ticks=worse_price,
            maint_bp=MAINT_BP,
            target_bp=TARGET_BP,
            taker_bps=TAKER_BPS,
            mult=MULT,
            caused_by_event_id="e2_0",
            risk_mark_event_id="e2_1",
            parent_chain_id=None,
            parent_chain_depth=None,
            parent_agent_id=None,
            this_event_id="mc2",
        )
        assert len(records) == 1
        assert records[0].required_quantity_units == expected_qty
        assert acct.liquidation_generation == gen_after_first + 1

    def test_pending_liquidation_recovers_to_active_verdict_ok(self):
        acct = _long("A", wallet=400_000, qty=100)
        accounts = {"A": acct}
        run_phase2_margin_scan(
            accounts,
            risk_mark_ticks=PRICE,
            maint_bp=MAINT_BP,
            target_bp=TARGET_BP,
            taker_bps=TAKER_BPS,
            mult=MULT,
            caused_by_event_id="e1_0",
            risk_mark_event_id="e1_1",
            parent_chain_id=None,
            parent_chain_depth=None,
            parent_agent_id=None,
            this_event_id="mc1",
        )
        assert acct.state == AccountState.PENDING_LIQUIDATION
        gen_after_first = acct.liquidation_generation
        # Recovery: mark comes back up, ratio >= maint again.
        better_price = PRICE + 50
        records = run_phase2_margin_scan(
            accounts,
            risk_mark_ticks=better_price,
            maint_bp=MAINT_BP,
            target_bp=TARGET_BP,
            taker_bps=TAKER_BPS,
            mult=MULT,
            caused_by_event_id="e2_0",
            risk_mark_event_id="e2_1",
            parent_chain_id=None,
            parent_chain_depth=None,
            parent_agent_id=None,
            this_event_id="mc2",
        )
        assert len(records) == 1
        assert records[0].verdict == "OK"
        assert acct.state == AccountState.ACTIVE
        assert acct.chain_id is None
        assert acct.chain_depth is None
        assert acct.liquidation_generation == gen_after_first + 1

    def test_multiple_accounts_same_batch_scanned_and_sorted(self):
        """Batch scenario (CLAUDE.md rule): two independent accounts both
        breach maint in the same scan; both must transition and the
        returned records must be sorted by agent_id."""
        acct_z = _long("Z", wallet=400_000, qty=100)
        acct_a = _long("A", wallet=400_000, qty=100)
        healthy = _long("H", wallet=600_000, qty=100)
        accounts = {"Z": acct_z, "A": acct_a, "H": healthy}
        records = run_phase2_margin_scan(
            accounts,
            risk_mark_ticks=PRICE,
            maint_bp=MAINT_BP,
            target_bp=TARGET_BP,
            taker_bps=TAKER_BPS,
            mult=MULT,
            caused_by_event_id="e1_0",
            risk_mark_event_id="e1_1",
            parent_chain_id=None,
            parent_chain_depth=None,
            parent_agent_id=None,
            this_event_id="mc1",
        )
        assert [r.agent_id for r in records] == ["A", "Z"]
        assert acct_a.state == AccountState.PENDING_LIQUIDATION
        assert acct_z.state == AccountState.PENDING_LIQUIDATION
        assert healthy.state == AccountState.ACTIVE

    def test_chain_root_when_no_parent(self):
        acct = _long("A", wallet=400_000, qty=100)
        accounts = {"A": acct}
        records = run_phase2_margin_scan(
            accounts,
            risk_mark_ticks=PRICE,
            maint_bp=MAINT_BP,
            target_bp=TARGET_BP,
            taker_bps=TAKER_BPS,
            mult=MULT,
            caused_by_event_id="e1_0",
            risk_mark_event_id="e1_1",
            parent_chain_id=None,
            parent_chain_depth=None,
            parent_agent_id=None,
            this_event_id="mc-root",
        )
        assert records[0].chain_id == "mc-root"
        assert records[0].chain_depth == 0

    def test_chain_depth_increments_for_cascade_onto_different_agent(self):
        """A chained liquidation (triggered by another agent's liquidation
        trade) that lands on a DIFFERENT account must keep the parent's
        chain_id but increment chain_depth."""
        acct = _long("B", wallet=400_000, qty=100)
        accounts = {"B": acct}
        records = run_phase2_margin_scan(
            accounts,
            risk_mark_ticks=PRICE,
            maint_bp=MAINT_BP,
            target_bp=TARGET_BP,
            taker_bps=TAKER_BPS,
            mult=MULT,
            caused_by_event_id="e5_0",
            risk_mark_event_id="e5_1",
            parent_chain_id="mc-root",
            parent_chain_depth=0,
            parent_agent_id="A",
            this_event_id="mc-child",
        )
        assert records[0].chain_id == "mc-root"
        assert records[0].chain_depth == 1

    def test_chain_id_preserved_when_same_agent_recounts(self):
        """A recount of the SAME already-PENDING account (parent_agent_id
        == this account) must keep its existing chain_id/depth, not treat
        itself as a new cascade hop."""
        acct = _long("A", wallet=400_000, qty=100)
        accounts = {"A": acct}
        run_phase2_margin_scan(
            accounts,
            risk_mark_ticks=PRICE,
            maint_bp=MAINT_BP,
            target_bp=TARGET_BP,
            taker_bps=TAKER_BPS,
            mult=MULT,
            caused_by_event_id="e1_0",
            risk_mark_event_id="e1_1",
            parent_chain_id=None,
            parent_chain_depth=None,
            parent_agent_id=None,
            this_event_id="mc-root",
        )
        assert acct.chain_id == "mc-root"
        assert acct.chain_depth == 0
        worse_price = PRICE - 20
        records = run_phase2_margin_scan(
            accounts,
            risk_mark_ticks=worse_price,
            maint_bp=MAINT_BP,
            target_bp=TARGET_BP,
            taker_bps=TAKER_BPS,
            mult=MULT,
            caused_by_event_id="e2_0",
            risk_mark_event_id="e2_1",
            parent_chain_id="mc-root",
            parent_chain_depth=0,
            parent_agent_id="A",
            this_event_id="mc-recount",
        )
        assert records[0].chain_id == "mc-root"
        assert records[0].chain_depth == 0
