"""T402 (方法论 §9.2): pair_id / arm_id pairing aggregator.

Joins paired runs by ``pair_id`` (NOT ``cell_id + seed``):

- ``pair_id = H(pair_family + fixed covariates + seed + replicate_id)`` --
  treatment-field values excluded, so the two arms of one logical pair
  naturally map to the same ``pair_id``;
- ``arm_id = H(pair_family + treatment-field diff)`` -- identifies whether a
  record is the control arm or the treatment arm;
- the unique key of one logical pair is ``(pair_id, arm_id)``.

Fail-closed: duplicate ``(pair_id, arm_id)`` is a runner fault (aggregation
rejected); an ``arm_id`` outside the pre-registered family set is rejected; a
pair with one technical-invalid arm is single-side-missing (not a valid pair);
an endpoint vs non-endpoint pair is reported by the two-part T602 split; a
pair whose arm appears only once is a missing pair (goes to the negative-result
report, never silently dropped from the denominator).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from market_game_sim.robustness.cell_classify import RunCategory


class PairingError(RuntimeError):
    """Raised on a fail-closed pairing violation."""


def _h(obj: Any) -> str:
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return hashlib.blake2b(canonical.encode("utf-8"), digest_size=16).hexdigest()


def pair_id(pair_family: str, covariates: dict[str, Any], seed: int, replicate_id: int = 0) -> str:
    """Id of one logical pair.  Excludes treatment-field values so both arms
    share it; includes seed + replicate so distinct replicates stay distinct."""
    return _h(
        {
            "pair_family": pair_family,
            "covariates": covariates,
            "seed": seed,
            "replicate_id": replicate_id,
        }
    )


def arm_id(pair_family: str, treatment_diff: dict[str, Any]) -> str:
    """Id of an arm (control or treatment) within the family.  A different
    treatment diff -> a different arm id."""
    return _h({"pair_family": pair_family, "treatment_diff": treatment_diff})


@dataclass
class PairRecord:
    pair_id: str
    arm_id: str
    category: RunCategory
    seed: int = 0

    @property
    def is_valid(self) -> bool:
        return self.category not in (RunCategory.TECHNICAL_INVALID,)


@dataclass
class PairingReport:
    valid_pairs: list[tuple[PairRecord, PairRecord]] = field(default_factory=list)
    single_side_missing: list[PairRecord] = field(default_factory=list)
    missing_pairs: list[tuple[str, str]] = field(default_factory=list)  # (pair_id, missing arm_id)
    duplicates_rejected: list[tuple[str, str]] = field(default_factory=list)
    unknown_arm_rejected: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid_pair_count": len(self.valid_pairs),
            "single_side_missing": len(self.single_side_missing),
            "missing_pair_count": len(self.missing_pairs),
            "duplicate_count": len(self.duplicates_rejected),
            "unknown_arm_count": len(self.unknown_arm_rejected),
        }


def aggregate_pairs(
    records: list[PairRecord],
    *,
    registered_arm_ids: set[str],
) -> PairingReport:
    """Aggregate pair records into valid pairs, fail-closed on every anomaly.

    A pair is valid only when both arms are present exactly once and both are
    valid (non-technical-invalid).  Anything else is routed to its explicit
    fail-closed bucket -- never silently dropped.
    """
    report = PairingReport()
    seen: dict[tuple[str, str], list[PairRecord]] = {}
    by_pair: dict[str, dict[str, PairRecord]] = {}

    for rec in records:
        if rec.arm_id not in registered_arm_ids:
            report.unknown_arm_rejected.append(rec.arm_id)
            continue
        key = (rec.pair_id, rec.arm_id)
        seen.setdefault(key, []).append(rec)

    for (pid, aid), recs in seen.items():
        if len(recs) > 1:
            report.duplicates_rejected.append((pid, aid))
            continue
        by_pair.setdefault(pid, {})[aid] = recs[0]

    for pid, arms in by_pair.items():
        if len(arms) != 2:
            # missing one arm -> missing pair; if one arm alone is invalid, it's
            # single-side-missing too
            for rec in arms.values():
                if not rec.is_valid:
                    report.single_side_missing.append(rec)
            missing_arm = ""
            if len(arms) == 1:
                missing_arm = next(iter(arms))
            report.missing_pairs.append((pid, missing_arm))
            continue
        ordered = [arms[aid] for aid in sorted(arms)]
        first, second = ordered[0], ordered[1]
        if first.is_valid and second.is_valid:
            report.valid_pairs.append((first, second))
        else:
            for rec in ordered:
                if not rec.is_valid:
                    report.single_side_missing.append(rec)

    return report
