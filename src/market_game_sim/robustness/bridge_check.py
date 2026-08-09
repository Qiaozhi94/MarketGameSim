"""T603 (KPI-009): per-run PnL bridge residual check.

Rechecks that every effective run of a scan / ablation / alternative-mapping
has all five PnL bridge residuals exactly 0 per agent.  A single non-zero
residual disqualifies that run from the statistical report (it would break the
KPI-009 guarantee the report relies on).

Reuses the existing bridge-residual computation path rather than re-deriving
it, so the check is consistent with the kernel's own KPI-009 enforcement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from market_game_sim.metrics.bridge import bridge_trade


@dataclass
class BridgeViolation:
    run_id: str
    agent_id: str
    trade_id: str
    residual: int


@dataclass
class BridgeCheckResult:
    violations: list[BridgeViolation] = field(default_factory=list)
    runs_checked: int = 0

    @property
    def all_zero(self) -> bool:
        return not self.violations

    def as_dict(self) -> dict[str, Any]:
        return {
            "runs_checked": self.runs_checked,
            "violation_count": len(self.violations),
            "all_zero": self.all_zero,
        }


def check_bridge_residuals(
    runs: list[dict[str, Any]],
    *,
    mult: int = 1000,
) -> BridgeCheckResult:
    """Recheck KPI-009 bridge residuals for a list of runs.

    Each ``run`` is a dict with ``run_id`` and ``events``.  Any trade posting
    with a non-zero residual disqualifies the run's run_id.
    """
    result = BridgeCheckResult()
    for run in runs:
        run_id = run.get("run_id", "")
        result.runs_checked += 1
        events = run.get("events", [])
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
                if res["residual"] != 0:
                    result.violations.append(
                        BridgeViolation(
                            run_id=run_id,
                            agent_id=p.get("agent_id", ""),
                            trade_id=e.get("trade_id", ""),
                            residual=res["residual"],
                        )
                    )
    return result
