"""T206 (方法论 §10.1): market-sufficiency gate per model family.

Applies the first-layer market-sufficiency threshold to each parameter cell's
market-validation matrix.  A cell that fails the gate is excluded from
belief conclusions -- it can only enter failure / boundary reports.

The gate is the "够用即止" threshold (方法论 §10.1): the market must be
"enough like" a market, not perfectly calibrated.  Concrete rules:
  - ``fill_ratio_ok`` must hold (fill ratio within protocol bound);
  - the six-item matrix must contain at least one informative (non
    NOT_APPLICABLE) item and no FAIL verdict among the informative items.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Sufficiency:
    passed: bool
    reasons: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "reasons": self.reasons}


def market_sufficient(matrix: dict[str, Any]) -> Sufficiency:
    """Judge whether a per-cell market-validation matrix passes the first-layer
    threshold.  ``matrix`` is a MarketValidationMatrix.as_dict() value.

    Returns ``passed`` (bool) plus the reasons when it fails.
    """
    reasons: list[str] = []

    if not matrix.get("fill_ratio_ok", False):
        reasons.append("fill_ratio_ok is False (fill ratio above protocol bound)")

    items = matrix.get("items", {})
    informative = [
        (name, item)
        for name, item in items.items()
        if isinstance(item, dict) and item.get("verdict") != "NOT_APPLICABLE"
    ]
    if not informative:
        reasons.append("no informative (non NOT_APPLICABLE) market feature")

    for name, item in informative:
        if item.get("verdict") == "FAIL":
            reasons.append(f"feature {name} FAILED market-sufficiency check")

    return Sufficiency(passed=not reasons, reasons=reasons)
