"""0.4.3 T1110 (AC-705): the "anchor too strong" diagnostics, reported but never judged.

A strong anchor pins the price and the market stops being one: in 0.4.1 §14
the price moved 0.55% in 1.6 hours and ``trend_following`` initiated 4 trades.
Spec §3 and ADR-016 裁决 B settle how that is handled: it is **shown at the top
of every configuration's report**, and it **does not change** SC-501/SC-502 --
heterogeneity is not an exit condition, and inventing a veto for it would be
adding a gate the spec does not have.

:func:`config_report` therefore builds the report in two halves that do not
touch: ``anchor_diagnostics`` first (from the run's diagnostics and segment
prices), then the verdicts, which come from :class:`MarketQualityReport` alone.
Stdlib only (KR-005).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from market_game_sim.metrics.market_quality import SC_501, SC_502

#: The 0.4.1 §15 third criterion, kept as a number to read, not a threshold.
TREND_FAMILY = "trend_following"


def down_segments(reference_ticks: int, segment_prices: Sequence[int]) -> int:
    """Segments that end below where they started (first starts at ``v_t``; spec SC-704)."""
    path = [reference_ticks, *segment_prices]
    return sum(1 for a, b in zip(path, path[1:], strict=False) if b < a)


def anchor_diagnostics(reference_ticks: int, diagnostics: Mapping[str, Any]) -> dict[str, Any]:
    """The four AC-705 fields from one quality run's diagnostics."""
    takers = {k: int(v) for k, v in diagnostics["takers_by_family"].items()}
    total = sum(takers.values())
    prices = list(diagnostics["segment_prices"])
    price_range = diagnostics.get("window_trade_price_range")
    return {
        "taker_share_by_family": {
            family: (round(count / total, 6) if total else None)
            for family, count in sorted(takers.items())
        },
        "trend_following_takers": takers.get(TREND_FAMILY, 0),
        "window_trade_price_range": price_range,
        "window_trade_price_range_pct": (
            round((price_range[1] - price_range[0]) / reference_ticks * 100, 4)
            if price_range
            else None
        ),
        "down_segments": down_segments(reference_ticks, prices),
        "segments": len(prices),
        "note": "诊断字段，只呈现不判定（spec AC-705，ADR-016 裁决 B）",
    }


def config_report(
    reference_ticks: int, report: Any, diagnostics: Mapping[str, Any]
) -> dict[str, Any]:
    """One configuration's report: diagnostics on top, verdicts from the gate only."""
    verdicts = report.verdicts
    return {
        "anchor_diagnostics": anchor_diagnostics(reference_ticks, diagnostics),
        "sc_501": verdicts[SC_501],
        "sc_502": verdicts[SC_502],
        "failed": list(report.failed),
        "quality": dict(report.quality),
        "stylized_facts": dict(verdicts["stylized_facts"]),
        "window_start_logical_ns": report.window_start_logical_ns,
        "roster_id": report.roster_id,
    }


__all__ = ["TREND_FAMILY", "anchor_diagnostics", "config_report", "down_segments"]
