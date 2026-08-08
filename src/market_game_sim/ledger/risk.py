"""T201, T202, T202b: Two-phase risk check + state machine.

After an ORDER_ARRIVAL's batch settlement, two phases run (账户合同 §4.1):

Phase 1 (breach capture): among accounts touched by the batch, those
with position==0 and wallet<0 transition to LIQUIDATED and receive
write-off postings.

Phase 2 (margin scan): O(N) over all non-zero position accounts; those
with margin_ratio_bp < maint_bp transition to PENDING_LIQUIDATION and
receive the actionable required_quantity_units.

State machine (plan §3.4):
  ACTIVE -> PENDING_LIQUIDATION -> LIQUIDATED
  ACTIVE <-> PENDING_LIQUIDATION (recovery)
  PENDING -> PENDING (qty change -> recount, generation +1)

liquidation_generation (事件 Schema §4.2.2) increments on every
"actionable" risk decision: first breach, recount, recovery.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from market_game_sim.ledger.account import Account, AccountState, margin_ratio_bp
from market_game_sim.ledger.bankruptcy import write_off_postings
from market_game_sim.ledger.liquidation import required_liquidation_qty


@dataclass
class MarginCallRecord:
    agent_id: str
    verdict: str
    required_quantity_units: int
    margin_ratio_bp: int | None
    maintenance_bp: int
    chain_id: str | None
    chain_depth: int | None
    liquidation_generation_after: int
    postings: list[dict] = field(default_factory=list)
    caused_by_event_id: str = ""
    risk_mark_event_id: str = ""
    trigger_ratio_bp: int | None = None


def _chain_attrs_for(
    account: Account,
    parent_chain_id: str | None,
    parent_chain_depth: int | None,
    parent_agent_id: str | None,
    this_event_id: str,
) -> tuple[str | None, int | None]:
    """Per 事件 Schema §4.2.2 (chain_id / chain_depth rules)."""
    if parent_chain_id is None:
        return this_event_id, 0
    if account.state == AccountState.PENDING_LIQUIDATION and account.chain_id is not None:
        return account.chain_id, account.chain_depth
    if parent_agent_id == account.agent_id:
        return parent_chain_id, parent_chain_depth
    return parent_chain_id, (parent_chain_depth or 0) + 1


def run_phase1_breaches(
    accounts: dict[str, Account],
    exchange_risk_pnl_units: int,
    touched_agent_ids: list[str],
    caused_by_event_id: str,
    risk_mark_event_id: str,
) -> tuple[list[MarginCallRecord], int]:
    """Phase 1: breach capture (账户合同 §4.1, step 1)."""
    records: list[MarginCallRecord] = []
    for aid in sorted(touched_agent_ids):
        acct = accounts.get(aid)
        if acct is None or acct.state == AccountState.LIQUIDATED:
            continue
        if acct.position_units == 0 and acct.wallet_units < 0:
            postings = write_off_postings(aid, acct)
            exchange_risk_pnl_units += acct.wallet_units
            acct.wallet_units = 0
            acct.state = AccountState.LIQUIDATED
            acct.liquidation_generation += 1
            acct.chain_id = None
            acct.chain_depth = None
            records.append(
                MarginCallRecord(
                    agent_id=aid,
                    verdict="BREACHED",
                    required_quantity_units=0,
                    margin_ratio_bp=None,
                    maintenance_bp=0,
                    chain_id=None,
                    chain_depth=None,
                    liquidation_generation_after=acct.liquidation_generation,
                    postings=postings,
                    caused_by_event_id=caused_by_event_id,
                    risk_mark_event_id=risk_mark_event_id,
                    trigger_ratio_bp=None,
                )
            )
    return records, exchange_risk_pnl_units


def run_phase2_margin_scan(
    accounts: dict[str, Account],
    risk_mark_ticks: int,
    maint_bp: int,
    target_bp: int,
    taker_bps: int,
    mult: int,
    caused_by_event_id: str,
    risk_mark_event_id: str,
    parent_chain_id: str | None,
    parent_chain_depth: int | None,
    parent_agent_id: str | None,
    this_event_id: str,
) -> list[MarginCallRecord]:
    """Phase 2: margin scan (账户合同 §4.1, step 2)."""
    actionable: list[tuple[str, MarginCallRecord]] = []

    for aid in sorted(accounts.keys()):
        acct = accounts[aid]
        if acct.state == AccountState.LIQUIDATED:
            continue
        if acct.position_units == 0:
            continue
        ratio = margin_ratio_bp(acct, risk_mark_ticks, mult)
        if ratio is None:
            continue

        if ratio < maint_bp:
            qty = required_liquidation_qty(acct, risk_mark_ticks, target_bp, taker_bps, mult)
            chain_id, chain_depth = _chain_attrs_for(
                acct,
                parent_chain_id,
                parent_chain_depth,
                parent_agent_id,
                this_event_id,
            )
            if acct.state == AccountState.ACTIVE:
                acct.state = AccountState.PENDING_LIQUIDATION
                acct.liquidation_generation += 1
                acct.chain_id = chain_id
                acct.chain_depth = chain_depth
                acct._last_required_qty = qty  # type: ignore[attr-defined]
                actionable.append(
                    (
                        aid,
                        MarginCallRecord(
                            agent_id=aid,
                            verdict="PENDING_LIQUIDATION",
                            required_quantity_units=qty,
                            margin_ratio_bp=ratio,
                            maintenance_bp=maint_bp,
                            chain_id=acct.chain_id,
                            chain_depth=acct.chain_depth,
                            liquidation_generation_after=acct.liquidation_generation,
                            caused_by_event_id=caused_by_event_id,
                            risk_mark_event_id=risk_mark_event_id,
                            trigger_ratio_bp=ratio,
                        ),
                    )
                )
            else:
                prev_q = getattr(acct, "_last_required_qty", None)
                if prev_q != qty:
                    acct.liquidation_generation += 1
                    acct.chain_id = chain_id
                    acct.chain_depth = chain_depth
                    acct._last_required_qty = qty  # type: ignore[attr-defined]
                    actionable.append(
                        (
                            aid,
                            MarginCallRecord(
                                agent_id=aid,
                                verdict="PENDING_LIQUIDATION",
                                required_quantity_units=qty,
                                margin_ratio_bp=ratio,
                                maintenance_bp=maint_bp,
                                chain_id=acct.chain_id,
                                chain_depth=acct.chain_depth,
                                liquidation_generation_after=acct.liquidation_generation,
                                caused_by_event_id=caused_by_event_id,
                                risk_mark_event_id=risk_mark_event_id,
                                trigger_ratio_bp=ratio,
                            ),
                        )
                    )
        else:
            if acct.state == AccountState.PENDING_LIQUIDATION:
                acct.state = AccountState.ACTIVE
                acct.liquidation_generation += 1
                acct.chain_id = None
                acct.chain_depth = None
                actionable.append(
                    (
                        aid,
                        MarginCallRecord(
                            agent_id=aid,
                            verdict="OK",
                            required_quantity_units=0,
                            margin_ratio_bp=ratio,
                            maintenance_bp=maint_bp,
                            chain_id=None,
                            chain_depth=None,
                            liquidation_generation_after=acct.liquidation_generation,
                            caused_by_event_id=caused_by_event_id,
                            risk_mark_event_id=risk_mark_event_id,
                            trigger_ratio_bp=None,
                        ),
                    )
                )

    records = [r for _, r in sorted(actionable, key=lambda kv: kv[0])]
    return records
