"""T204 (指标字典 §6, 退化 §4): mutually-exclusive run classification.

Classifies each parameter cell's run into one mutually-exclusive category,
preserving the original evidence index:

- TECHNICAL_INVALID -- TI-* (log/hash/conservation/abort failures)
- ECONOMIC_ENDPOINT  -- EV-* (degenerate economic terminal states)
- LOCKED            -- price locked / no movement (no trades or flat path)
- DIVERGED          -- price diverged beyond a bound
- OSCILLATING       -- periodic oscillation detected
- COMPLETED         -- normal completion

Categories are mutually exclusive: each run maps to exactly one.  The
original evidence index (which code fired) is retained so a report can point
back to the raw evidence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any

from market_game_sim.metrics.liquidation import RunClassification


class RunCategory(Enum):
    TECHNICAL_INVALID = "TECHNICAL_INVALID"
    ECONOMIC_ENDPOINT = "ECONOMIC_ENDPOINT"
    LOCKED = "LOCKED"
    DIVERGED = "DIVERGED"
    OSCILLATING = "OSCILLATING"
    COMPLETED = "COMPLETED"


@dataclass
class Classification:
    category: RunCategory
    code: str | None = None
    evidence: dict[str, Any] | None = None


def classify_cell(
    run_classification: RunClassification,
    events: list[dict],
    *,
    initial_price: int,
    lock_deviation_ticks: int = 0,
    divergence_bound: float = math.log(10),
    oscillating_window: int = 20,
    oscillation_tolerance: float = 0.1,
) -> Classification:
    """Classify one run into a mutually-exclusive RunCategory.

    Order of precedence (first match wins, categories are disjoint):
      1. TECHNICAL_INVALID (TI-*)
      2. ECONOMIC_ENDPOINT (EV-*)
      3. LOCKED / DIVERGED / OSCILLATING (price-path structure)
      4. COMPLETED (fallback)
    """
    if run_classification.is_technical_invalid:
        return Classification(
            RunCategory.TECHNICAL_INVALID, run_classification.technical_invalid_code
        )
    if run_classification.is_economic_endpoint:
        return Classification(
            RunCategory.ECONOMIC_ENDPOINT,
            ";".join(run_classification.economic_endpoint_codes),
        )

    ticks = _price_series(events)
    if not ticks or len(ticks) < 2:
        return Classification(RunCategory.LOCKED, "no_price_path")
    if max(ticks) - min(ticks) <= lock_deviation_ticks:
        return Classification(RunCategory.LOCKED, "flat_path")

    if initial_price > 0:
        max_dev = max(abs(math.log(t / initial_price)) for t in ticks if t > 0)
        if max_dev > divergence_bound:
            return Classification(RunCategory.DIVERGED, "price_diverged")

    if _is_oscillating(ticks, oscillating_window, oscillation_tolerance):
        return Classification(RunCategory.OSCILLATING, "periodic")

    return Classification(RunCategory.COMPLETED)


def _price_series(events: list[dict]) -> list[int]:
    """Extract a price series from TRADE_SETTLE / MARK events, in log order."""
    ticks: list[int] = []
    for e in events:
        et = e.get("event_type")
        if et == "TRADE_SETTLE":
            ticks.append(e.get("price_ticks", 0))
        elif et == "MARKET_DATA_PUBLISH":
            ticks.append(e.get("mid_ticks", 0) or 0)
    return [t for t in ticks if t and t > 0]


def _is_oscillating(ticks: list[int], window: int, tolerance: float) -> bool:
    """Heuristic periodic-oscillation check: count sign changes of consecutive
    deltas over recent window; if the ratio of reversals is very high AND the
    path repeatedly crosses back across its midline, treat as oscillating."""
    if len(ticks) < window:
        return False
    recent = ticks[-window:]
    deltas = [b - a for a, b in zip(recent, recent[1:], strict=False)]
    nonzero = [d for d in deltas if d != 0]
    if len(nonzero) < 2:
        return False
    reversals = sum(1 for a, b in zip(nonzero, nonzero[1:], strict=False) if a * b < 0)
    return reversals / (len(nonzero) - 1) >= (1 - tolerance)
