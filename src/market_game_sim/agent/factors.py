"""T402: Five factors with fixed-scale clipping (代理策略 §2-§4)."""

from __future__ import annotations

from decimal import Decimal

from market_game_sim.agent.observation import Bar, InformationSet

SCALE_MOMENTUM = Decimal("0.01")
SCALE_REVERSION = Decimal("0.02")
SCALE_HERDING = Decimal("1.0")
SCALE_BOOK = Decimal("1.0")
SCALE_NOISE = Decimal("1.0")
_ONE = Decimal(1)
_ZERO = Decimal(0)


def _clip(x: Decimal) -> Decimal:
    if x > _ONE:
        return _ONE
    if x < -_ONE:
        return -_ONE
    return x


def momentum(bars: list[Bar], lookback: int) -> Decimal:
    if len(bars) < lookback + 1 or lookback < 1:
        return _ZERO
    c0 = bars[-1 - lookback].close
    c1 = bars[-1].close
    if c0 <= 0 or c1 <= 0:
        return _ZERO
    ratio = Decimal(c1) / Decimal(c0)
    if ratio <= 0:
        return _ZERO
    return _clip(ratio.ln() / SCALE_MOMENTUM)


def reversion(last_ticks: int | None, anchor_ticks: int) -> Decimal:
    if last_ticks is None or last_ticks <= 0:
        return _ZERO
    raw = (Decimal(anchor_ticks) - Decimal(last_ticks)) / Decimal(last_ticks)
    return _clip(raw / SCALE_REVERSION)


def herding(window: list[Bar]) -> Decimal:
    if not window:
        return _ZERO
    buy = sum(b.volume for b in window if b.close >= b.open)
    sell = sum(b.volume for b in window if b.close < b.open)
    total = buy + sell
    if total == 0:
        return _ZERO
    return _clip(Decimal(buy - sell) / Decimal(total) / SCALE_HERDING)


def book(iset: InformationSet) -> Decimal:
    if iset.bid_depth_k == 0 and iset.ask_depth_k == 0:
        return _ZERO
    if iset.ask_depth_k == 0:
        return _ONE
    if iset.bid_depth_k == 0:
        return -_ONE
    raw = Decimal(iset.bid_depth_k - iset.ask_depth_k) / Decimal(
        iset.bid_depth_k + iset.ask_depth_k
    )
    return _clip(raw / SCALE_BOOK)


def noise(noise_value: Decimal) -> Decimal:
    return _clip(noise_value / SCALE_NOISE)


def belief_signal(weights: list[Decimal], factors: list[Decimal]) -> int:
    s = sum(w * f for w, f in zip(weights, factors, strict=True))
    s = max(-_ONE, min(_ONE, s))
    return int(s * 10_000)
