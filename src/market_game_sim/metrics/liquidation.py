"""T502, T504: Liquidation metrics + sample classification.

* :class:`LiquidationMetrics` -- chain_depth distribution, volume ratio,
  per-chain size.
* :func:`classify_run` -- TI-* (technical invalid, exclude) vs EV-*
  (economic endpoint, retain).
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class LiquidationMetrics:
    """Aggregate liquidation statistics (指标字典 §4.1)."""

    total_liquidations: int = 0
    total_volume: int = 0
    liquidation_volume: int = 0
    chain_depth_counts: dict[int, int] = field(default_factory=Counter)
    chain_size_by_id: dict[str, int] = field(default_factory=dict)
    bankruptcy_total: int = 0
    breach_volume_units: int = 0

    @property
    def liquidation_volume_ratio(self) -> float:
        if self.total_volume == 0:
            return 0.0
        return self.liquidation_volume / self.total_volume


def compute_liquidation_metrics(events: list[dict]) -> LiquidationMetrics:
    """Walk the event log to compute liquidation aggregates."""
    metrics = LiquidationMetrics()
    chain_size_acc: dict[str, set[str]] = {}
    liq_order_ids: set[str] = set()
    for ev in events:
        et = ev.get("event_type", "")
        if et == "ORDER_ARRIVAL" and ev.get("origin") == "LIQUIDATION":
            liq_order_ids.add(ev.get("order_id", ""))
        elif et == "TRADE_SETTLE":
            qty = ev.get("quantity_units", 0)
            metrics.total_volume += qty
            taker_oid = ev.get("taker_order_id", "")
            maker_oid = ev.get("maker_order_id", "")
            if taker_oid in liq_order_ids or maker_oid in liq_order_ids:
                metrics.liquidation_volume += qty
        elif et == "MARGIN_CALL":
            verdict = ev.get("verdict", "")
            if verdict == "BREACHED":
                metrics.bankruptcy_total += 1
            if verdict == "OK":
                continue
            depth = ev.get("chain_depth") or 0
            metrics.chain_depth_counts[depth] += 1
            metrics.total_liquidations += 1

    for ev in events:
        if ev.get("event_type") != "MARGIN_CALL":
            continue
        verdict = ev.get("verdict", "")
        if verdict == "OK":
            continue
        chain_id = ev.get("chain_id")
        if not chain_id:
            continue
        agent = ev.get("agent_id", "")
        chain_size_acc.setdefault(chain_id, set()).add(agent)
    metrics.chain_size_by_id = {k: len(v) for k, v in chain_size_acc.items()}
    return metrics


@dataclass
class RunClassification:
    """Result of classifying one run (退化状态 §4)."""

    is_technical_invalid: bool = False
    technical_invalid_code: str | None = None
    is_economic_endpoint: bool = False
    economic_endpoint_codes: list[str] = field(default_factory=list)
    breached: bool = False

    def as_dict(self) -> dict:
        return {
            "is_technical_invalid": self.is_technical_invalid,
            "technical_invalid_code": self.technical_invalid_code,
            "is_economic_endpoint": self.is_economic_endpoint,
            "economic_endpoint_codes": list(self.economic_endpoint_codes),
            "breached": self.breached,
        }


def classify_run(
    events: list[dict],
    last_ticks: int | None,
    initial_price: int,
    total_idle_ns: int,
    run_total_ns: int,
    has_aborted: bool,
    chained_liquidation_drained_book: bool,
    reference_integrity_ok: bool = True,
    hash_consistent: bool = True,
    conservation_ok: bool = True,
    log_truncated: bool = False,
) -> RunClassification:
    """Classify a finished run as TI-* or EV-* (退化状态 §4.1).

    * TI-1: reference integrity check failed (``reference_integrity_ok == False``).
    * TI-2: hash inconsistent (``hash_consistent == False``).
    * TI-3: C1/C2 conservation violated (``conservation_ok == False``).
    * TI-4: ``terminated=ABORTED``.
    * TI-5: log structure corrupt/truncated (``log_truncated == True``).
    * EV-1: price touched 1 tick.
    * EV-2: max|ln(P/P0)| > ln(10) over entire run interval.
    * EV-3: continuous idle time > 5% of run length.
    * EV-4: chained liquidation drained the book.
    """
    result = RunClassification()
    if log_truncated:
        result.is_technical_invalid = True
        result.technical_invalid_code = "TI-5"
        return result
    if has_aborted:
        result.is_technical_invalid = True
        result.technical_invalid_code = "TI-4"
        return result
    if not reference_integrity_ok:
        result.is_technical_invalid = True
        result.technical_invalid_code = "TI-1"
        return result
    if not hash_consistent:
        result.is_technical_invalid = True
        result.technical_invalid_code = "TI-2"
        return result
    if not conservation_ok:
        result.is_technical_invalid = True
        result.technical_invalid_code = "TI-3"
        return result
    if total_idle_ns > 0.05 * run_total_ns:
        result.is_economic_endpoint = True
        result.economic_endpoint_codes.append("EV-3")
    if last_ticks is not None and initial_price > 0 and last_ticks <= 1:
        result.is_economic_endpoint = True
        result.economic_endpoint_codes.append("EV-1")
    if initial_price > 0:
        max_deviation = _max_price_deviation(events, initial_price)
        if max_deviation is not None and abs(max_deviation) > math.log(10):
            result.is_economic_endpoint = True
            result.economic_endpoint_codes.append("EV-2")
    if chained_liquidation_drained_book:
        result.is_economic_endpoint = True
        result.economic_endpoint_codes.append("EV-4")
    if any(
        ev.get("event_type") == "MARGIN_CALL" and ev.get("verdict") == "BREACHED" for ev in events
    ):
        result.breached = True
    return result


def _max_price_deviation(events: list[dict], initial_price: int) -> float | None:
    """Maximum |ln(P_t/P_0)| over all TRADE_SETTLE events."""
    max_abs = 0.0
    found = False
    for ev in events:
        if ev.get("event_type") != "TRADE_SETTLE":
            continue
        p = ev.get("price_ticks")
        if p is not None and p > 0 and initial_price > 0:
            dev = abs(math.log(p / initial_price))
            if dev > max_abs:
                max_abs = dev
            found = True
    return max_abs if found else None
