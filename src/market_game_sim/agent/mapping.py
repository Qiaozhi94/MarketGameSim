"""T101/T102 (计划 §2, 代理策略 §12): behavior-mapping interface + mappings.

``BehaviorMapping`` is the single abstraction a belief agent uses to turn a
normalized belief signal into a *target position* in qty units.  It returns
**only the target position** -- never an order intent or order parameters --
so that the T103 shared execution pipeline (delta -> OrderIntent -> admission)
is identical across mappings, and the mapping comparison in T105 is a
single-variable contrast (代理策略 §12 known-limitation replacement).

``LinearMapping`` reproduces the 0.1.2 linear baseline exactly.  The
pre-registered alternative ``ThresholdMapping`` (T102) replaces the linear
signal->position curve with a dead-band / threshold structure; thresholds,
hysteresis and boundary rounding are configured and deterministic.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass

from market_game_sim.agent.strategy import target_position as _linear_target


class BehaviorMapping(abc.ABC):
    """Quantifies a belief signal into a target position in qty units.

    Contract (T101): returns only ``target_position`` (int qty units).  It
    must not return order intents, order parameters, or depend on the order
    book internals -- the target->execution pipeline is the T103 shared
    execution layer, not part of a mapping.
    """

    id: str
    version: str

    @abc.abstractmethod
    def target_position(
        self,
        signal_bp: int,
        equity_units: int,
        valuation_mark_ticks: int,
        initial_bp: int,
        min_qty: int,
    ) -> int: ...


@dataclass(frozen=True)
class LinearMapping(BehaviorMapping):
    """The 0.1.2 linear baseline: target proportional to signal."""

    id: str = "linear"
    version: str = "1.0"

    def target_position(
        self,
        signal_bp: int,
        equity_units: int,
        valuation_mark_ticks: int,
        initial_bp: int,
        min_qty: int,
    ) -> int:
        return _linear_target(signal_bp, equity_units, valuation_mark_ticks, initial_bp, min_qty)


@dataclass(frozen=True)
class ThresholdMapping(BehaviorMapping):
    """Alternative mapping (T102): signal passes through a dead band, then
    steps to a configured fraction of the max position.

    ``dead_band_bp``: |signal| below this maps to 0 (no position).
    ``step_fraction_bp``: for |signal| >= dead_band, target = sign(signal) *
    floor(max_position * step_fraction_bp / 10000), truncated to min_qty.

    Threshold, hysteresis-free (a single deterministic dead band), and
    boundary rounding are all configured and deterministic.
    """

    id: str = "threshold"
    version: str = "1.0"
    dead_band_bp: int = 200
    step_fraction_bp: int = 10_000

    def target_position(
        self,
        signal_bp: int,
        equity_units: int,
        valuation_mark_ticks: int,
        initial_bp: int,
        min_qty: int,
    ) -> int:
        if valuation_mark_ticks <= 0 or initial_bp <= 0 or min_qty <= 0:
            return 0
        if abs(signal_bp) < self.dead_band_bp:
            return 0
        max_pos = (equity_units * 10_000) // (initial_bp * valuation_mark_ticks)
        raw = max_pos * self.step_fraction_bp
        raw = raw // 10_000 if raw >= 0 else -((-raw) // 10_000)
        target = raw if signal_bp >= 0 else -raw
        return _trunc_toward_zero(target, min_qty)


def _trunc_toward_zero(x: int, step: int) -> int:
    if x == 0:
        return 0
    sign = 1 if x > 0 else -1
    return sign * ((abs(x) // step) * step)


_MAPPINGS: dict[str, BehaviorMapping] = {
    "linear": LinearMapping(),
    "threshold": ThresholdMapping(),
}


def register_mapping(mapping: BehaviorMapping) -> None:
    _MAPPINGS[mapping.id] = mapping


def get_mapping(mapping_id: str) -> BehaviorMapping:
    if mapping_id not in _MAPPINGS:
        raise KeyError(f"unknown behavior mapping: {mapping_id}")
    return _MAPPINGS[mapping_id]
