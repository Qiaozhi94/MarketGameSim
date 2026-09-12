"""Paired-seed-block sample-size baseline for the H2 `AI_FORMAL` track.

Why a second tool instead of editing `h2_power_feasibility.py`: that file is the
frozen record of the **superseded** human-participant plan, whose experimental
unit was a *participant* contributing ~7.2 paired rounds.  The dual-track
contract changed the unit to a single *paired seed block*, so the variance
structure is different and the old number must not be carried over.  The old
evidence file says so explicitly; this tool provides the replacement basis.

Model (deliberately conservative, same family as the v0.1 paired screen):

* Each block yields one paired difference ``D in {-1, 0, 1}`` for a family.
* ``Var(D) = q - delta**2`` with ``q`` the paired-discordance probability.
* Blocks are independent (no participant clustering in a pure-agent track).
* Each of the three primary families is planned at the Holm first-step
  threshold ``alpha / 3``, which is the most conservative step.

The result is a **lower bound under an assumed ``q``**.  ``q`` for a pure-agent
paired track has never been measured in this repository, so the contract must
still calibrate it before freezing a final block count; the calibration may
raise the requirement but must never lower it below this baseline.

Usage::

    python tools/h2_block_power.py
    python tools/h2_block_power.py --check docs/experiments/H2-block-power-baseline.json
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import NormalDist
from typing import Any

EVIDENCE_ID = "H2-block-power-baseline-v1"
FAMILYWISE_ALPHA = 0.05
PRIMARY_FAMILIES = 3
TARGET_POWER = 0.80
SESOI = 0.125
PAIRED_DISCORDANCE = 0.25
DISCORDANCE_GRID = (0.15, 0.25, 0.35)
REPORTED_BLOCK_COUNTS = (130, 158, 200, 260)
SUPERSEDED_PARTICIPANT_CAP = 130
SUPERSEDED_ROUNDS_PER_PARTICIPANT = 8
SUPERSEDED_PAIR_MISSING_RATE = 0.10
# ``statistics.NormalDist`` can differ by one IEEE-754 ulp between supported
# CPython versions.  Evidence is a committed, cross-version contract, so
# canonicalize only at the serialization boundary; internal calculations keep
# their full float precision.
EVIDENCE_FLOAT_DECIMAL_PLACES = 15

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "docs" / "experiments" / "H2-block-power-baseline.json"


def first_step_alpha() -> float:
    """Holm's most conservative per-family threshold."""
    return FAMILYWISE_ALPHA / PRIMARY_FAMILIES


def block_power(blocks: int, discordance: float) -> float:
    """Two-sided normal-approximation power for one family at ``blocks`` blocks."""
    if blocks < 1:
        return 0.0
    variance = discordance - SESOI**2
    standard_error = math.sqrt(variance / blocks)
    critical = NormalDist().inv_cdf(1.0 - first_step_alpha() / 2.0)
    normal = NormalDist()
    upper = 1.0 - normal.cdf(critical - SESOI / standard_error)
    lower = normal.cdf(-critical - SESOI / standard_error)
    return upper + lower


def minimum_blocks(discordance: float) -> int:
    """Smallest block count reaching ``TARGET_POWER`` under ``discordance``."""
    blocks = 2
    while block_power(blocks, discordance) < TARGET_POWER:
        blocks += 1
        if blocks > 100_000:  # pragma: no cover - guards against a bad assumption
            raise RuntimeError(f"no feasible block count for q={discordance}")
    return blocks


def superseded_paired_rounds() -> float:
    """Paired rounds implied by the retired human plan, for the unit-change note."""
    return (
        SUPERSEDED_PARTICIPANT_CAP
        * SUPERSEDED_ROUNDS_PER_PARTICIPANT
        * (1.0 - SUPERSEDED_PAIR_MISSING_RATE)
    )


def canonical_evidence_float(value: float) -> float:
    """Return a stable JSON number for evidence generated across Python versions."""
    return round(value, EVIDENCE_FLOAT_DECIMAL_PLACES)


def build_evidence() -> dict[str, Any]:
    """Machine-readable baseline consumed by the dual-track contract."""
    return {
        "evidence_id": EVIDENCE_ID,
        "evidence_class": "planning-sensitivity-analysis",
        "experimental_unit": "paired_seed_block",
        "inputs": {
            "sesoi": SESOI,
            "paired_discordance_assumed": PAIRED_DISCORDANCE,
            "paired_discordance_grid": list(DISCORDANCE_GRID),
            "familywise_alpha": FAMILYWISE_ALPHA,
            "primary_families": PRIMARY_FAMILIES,
            "first_step_alpha": first_step_alpha(),
            "target_power": TARGET_POWER,
            "blocks_are_independent": True,
        },
        "baseline_minimum_blocks": minimum_blocks(PAIRED_DISCORDANCE),
        "power_by_blocks": {
            str(blocks): canonical_evidence_float(block_power(blocks, PAIRED_DISCORDANCE))
            for blocks in REPORTED_BLOCK_COUNTS
        },
        "minimum_blocks_by_discordance": {str(q): minimum_blocks(q) for q in DISCORDANCE_GRID},
        "superseded_unit_change": {
            "old_unit": "participant",
            "old_target": SUPERSEDED_PARTICIPANT_CAP,
            "old_paired_rounds_implied": superseded_paired_rounds(),
            "new_unit": "paired_seed_block",
            "note": (
                "130 participants implied about 936 paired rounds; 130 blocks are 130 "
                "paired rounds. The number must not survive the unit change unexamined."
            ),
        },
        "calibration_required": True,
        "may_lower_baseline": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="H2 paired-seed-block power baseline")
    parser.add_argument("--check", type=Path, default=None)
    parser.add_argument("--write", type=Path, default=None)
    args = parser.parse_args()

    evidence = build_evidence()
    if args.check is not None:
        recorded = json.loads(args.check.read_text(encoding="utf-8"))
        if recorded != evidence:
            print(f"{args.check} 与当前计算不一致；重新生成后再提交")
            return 1
        print(f"{args.check} 与当前计算一致")
        return 0

    target = args.write or DEFAULT_OUTPUT
    target.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已写入 {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
