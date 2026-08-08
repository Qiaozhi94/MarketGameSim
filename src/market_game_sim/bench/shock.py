"""T701/E5-E6 calibration: benchmark-only sustained forcing trades.

Deep-dive found the BENCH-001 market settles into a static equilibrium no
matter how many transactions run: ``aggressiveness_bp`` is drawn once per
agent at population-build time (not per-decision), so only the small
fraction of agents who happen to draw a high value ever cross the spread;
once they've each traded once toward their (noise-dominated, usually weak)
target position, nothing changes further and price stays flat.

A single one-shot forcing trade does not work either -- confirmed
empirically across shock sizes from 100K to 15M units and timings from 1ms
to 5s: 180 retail agents doing full-cancel-reissue every ~1s (§6.2) and 10
market makers requoting every 0.1s refill any hole within about one decision
cycle, regardless of shock size. The market self-heals faster than a
one-shot push can move it.

This instead injects a *series* of same-direction MARKET orders at a fixed
interval, from a synthetic participant that exists only in the benchmark
harness -- sustained pressure that outpaces the population's replenishment
rate, rather than a single push it absorbs in one cycle. Purely to make the
coverage assertions (README §1.1) exercisable within a bounded transaction
budget; does not touch belief-agent/market-maker decision logic (README's
own scope for BENCH-001: "参与者构成只求覆盖代码路径，不追求统计特征").
"""

from __future__ import annotations

SHOCK_AGENT_ID = "bench-shock"
SHOCK_WALLET_UNITS = 10**16


def build_shock_series(
    side: str = "SELL",
    quantity_units_per_shock: int = 1_000_000,
    interval_ns: int = 200_000_000,
    count: int = 50,
    start_ns: int = 200_000_000,
) -> tuple[dict[str, int], list[dict]]:
    """Returns ``(extra_accounts, extra_events)`` ready to pass to
    ``ExperimentConfig(extra_accounts=..., extra_events=events)``.

    Defaults: 50 pushes, 200ms apart (faster than a retail agent's 1s
    decision cycle, so pressure compounds instead of being absorbed each
    round), starting at 200ms (after the first market-maker quotes exist,
    so there is a real counterparty on the first push).
    """
    events = [
        {
            "event_type": "ORDER_ARRIVAL",
            "timestamp": start_ns + i * interval_ns,
            "agent_id": SHOCK_AGENT_ID,
            "order_id": f"{SHOCK_AGENT_ID}-{i}",
            "action": "SUBMIT",
            "side": side,
            "order_type": "MARKET",
            "price_ticks": None,
            "quantity_units": quantity_units_per_shock,
        }
        for i in range(count)
    ]
    return {SHOCK_AGENT_ID: SHOCK_WALLET_UNITS}, events
