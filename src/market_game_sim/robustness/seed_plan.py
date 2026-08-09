"""T005 (KPI-010): per-pair-family seed plan.

Pre-registers, for each ``pair_family``, the planned seed count, the minimum
number of valid pairs, the maximum number of technical-failure backfills and
a fixed backfill seed list.

Backfill may only be triggered by a predefined *technical failure* (explicit
reason passed in), never by effect direction, significance or interval width.
Reaching the backfill cap while still below the minimum valid pairs yields an
"证据不足" (insufficient evidence) conclusion -- never an effect-direction
choice.  A single seed / single path can never yield a conclusion (KPI-010).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


class SeedPlanError(RuntimeError):
    """Raised on a seed-plan violation (illegal backfill, over-backfill, or a
    conclusion drawn from an under-powered sample)."""


TECHNICAL_FAILURE_REASONS = ("TI-1", "TI-3", "TI-4", "TI-5")


@dataclass
class SeedPlan:
    pair_family: str
    planned_seed_count: int
    min_valid_pairs: int
    max_technical_failure_backfills: int
    backfill_seed_list: list[int] = field(default_factory=list)

    def validate(self) -> list[str]:
        problems: list[str] = []
        if self.planned_seed_count < 2:
            problems.append("planned_seed_count must be >= 2 (KPI-010: no single-run conclusion)")
        if self.min_valid_pairs < 1:
            problems.append("min_valid_pairs must be >= 1")
        if self.max_technical_failure_backfills < 0:
            problems.append("max_technical_failure_backfills must be >= 0")
        return problems

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BackfillDecision:
    granted: bool
    seed: int | None = None
    reason: str = ""


@dataclass
class RunTracker:
    """Tracks per-pair-family run validity for backfill / evidence gating."""

    plan: SeedPlan
    valid_pairs: int = 0
    technical_failures: int = 0
    backfills_used: int = 0
    backfill_used_seeds: list[int] = field(default_factory=list)
    _backfill_pool: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        problems = self.plan.validate()
        if problems:
            raise SeedPlanError("invalid seed plan: " + "; ".join(problems))
        self._backfill_pool = list(self.plan.backfill_seed_list)

    def record_valid_pair(self) -> None:
        self.valid_pairs += 1

    def request_backfill(self, technical_failure_reason: str) -> BackfillDecision:
        """Request one backfill run.

        Granted only when the reason is a predefined technical failure, the
        backfill cap is not exhausted, and a backfill seed remains.
        """
        if technical_failure_reason not in TECHNICAL_FAILURE_REASONS:
            return BackfillDecision(
                False, None, f"not a technical failure: {technical_failure_reason}"
            )
        if self.backfills_used >= self.plan.max_technical_failure_backfills:
            return BackfillDecision(False, None, "backfill cap reached")
        if not self._backfill_pool:
            return BackfillDecision(False, None, "no backfill seeds left")
        seed = self._backfill_pool.pop(0)
        self.backfills_used += 1
        self.backfill_used_seeds.append(seed)
        return BackfillDecision(True, seed, technical_failure_reason)

    def conclusion_eligible(self) -> tuple[bool, str]:
        """Whether the family may draw a conclusion.

        Returns ``(eligible, note)``; ineligible means "证据不足" (insufficient
        evidence) -- valid pairs below the minimum, even after exhausting the
        backfill cap.
        """
        if self.valid_pairs >= self.plan.min_valid_pairs:
            return True, f"valid_pairs={self.valid_pairs} >= min={self.plan.min_valid_pairs}"
        return False, (
            f"证据不足: valid_pairs={self.valid_pairs} < min={self.plan.min_valid_pairs} "
            f"after {self.backfills_used}/{self.plan.max_technical_failure_backfills} backfills"
        )
