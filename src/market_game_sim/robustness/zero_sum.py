"""T605 (KPI-011): zero-sum declaration with five PnL channels.

States the closed-market zero-sum identity explicitly (PRD §13.4) and breaks
"who loses" into the distribution (per-agent PnL) AND the five PnL channels
of metrics-dictionary §5.2 -- spread, impact, revaluation, funding, fees --
so the total is not reported as a finding and the channels show where PnL
flowed.  Channel sums are accumulated from TRADE_SETTLE postings with
``metrics.bridge.bridge_trade`` (the same per-trade decomposition the
kernel's KPI-009 check uses).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from market_game_sim.ledger.account import Account
from market_game_sim.metrics.bridge import bridge_trade
from market_game_sim.metrics.report import build_zero_sum_declaration

CHANNELS = ("spread", "impact", "revaluation", "funding", "fees")


@dataclass
class ZeroSumChannels:
    spread: int = 0
    impact: int = 0
    revaluation: int = 0
    funding: int = 0
    fees: int = 0

    def as_dict(self) -> dict[str, int]:
        return {c: getattr(self, c) for c in CHANNELS}


def accumulate_channels(events: list[dict], *, mult: int = 1000) -> ZeroSumChannels:
    """Sum the five PnL channels across all TRADE_SETTLE postings.

    Each posting side contributes via ``bridge_trade``; ``fees`` is the fee
    delta of the side (exchange-collected, so the sum of agent-side fees is
    the exchange's income).
    """
    out = ZeroSumChannels()
    for e in events:
        if e.get("event_type") != "TRADE_SETTLE":
            continue
        vm_before_h = e.get("valuation_mark_before_half_ticks", 0)
        vm_after_h = e.get("valuation_mark_after_half_ticks", 0)
        for p in e.get("postings", []):
            if p.get("posting_type") != "TRADE_POSTING":
                continue
            res = bridge_trade(
                posting=p,
                vm_before_half=vm_before_h,
                vm_after_half=vm_after_h,
                trade_price_ticks=e.get("price_ticks", 0),
                position_before_units=p.get("position_after_units", 0)
                - p.get("position_delta_units", 0),
                mult=mult,
            )
            out.spread += res["spread"]
            out.impact += res["impact"]
            out.revaluation += res["revaluation"]
            out.funding += res["funding"]
            out.fees += res["fees"]
    return out


@dataclass
class ZeroSumReport:
    total_pnl_units: int
    expected_negative_fees_units: int
    residual_units: int
    per_agent_pnl_units: dict[str, int]
    channels: dict[str, int]
    declaration_text: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_pnl_units": self.total_pnl_units,
            "expected_negative_fees_units": self.expected_negative_fees_units,
            "residual_units": self.residual_units,
            "per_agent_pnl_units": dict(self.per_agent_pnl_units),
            "channels": dict(self.channels),
            "declaration_text": self.declaration_text,
        }


def build_zero_sum_report(
    accounts: dict[str, Account],
    initial_baseline: dict[str, int],
    exchange_fee_units: int,
    exchange_risk_pnl_units: int,
    events: list[dict],
    *,
    mult: int = 1000,
) -> ZeroSumReport:
    """Build the KPI-011 declaration with the distribution AND five channels.

    Reuses ``build_zero_sum_declaration`` for the identity text + per-agent
    distribution, and accumulates the five channels from ``events``.
    """
    decl = build_zero_sum_declaration(
        accounts, initial_baseline, exchange_fee_units, exchange_risk_pnl_units
    )
    channels = accumulate_channels(events, mult=mult).as_dict()
    return ZeroSumReport(
        total_pnl_units=decl.total_pnl_units,
        expected_negative_fees_units=decl.expected_negative_fees_units,
        residual_units=decl.residual_units,
        per_agent_pnl_units=dict(decl.per_agent_pnl_units),
        channels=channels,
        declaration_text=decl.declaration_text,
    )
