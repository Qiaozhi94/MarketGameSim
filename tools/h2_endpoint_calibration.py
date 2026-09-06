"""Calibrate the H2 `AI_FORMAL` primary endpoint from v0.1.5 measured evidence.

The dual-track contract picks **occurrence** (a binary per-block indicator) as the
primary estimand for all three families, with a paired risk-difference SESOI of
0.125.  v0.1.5 already ran the very same two frozen policies over 128 paired seed
blocks, and its evidence index records, per hypothesis, how many blocks produced a
non-zero paired contrast:

* every ``occurrence`` hypothesis: **0 non-zero blocks**
* every ``severity`` hypothesis: 91 of 128 blocks

A paired difference that is identically zero across the sample has zero variance,
so the test statistic is degenerate: no block count reaches any power at all.
Adding blocks cannot fix a zero-variance endpoint -- the endpoint has to change.

This tool derives, from the recorded bootstrap intervals, the observed severity
paired-difference dispersion and the block count needed for a range of candidate
severity SESOIs, so the owner can freeze a SESOI on measured ground instead of
reusing the human-era 0.125 risk-difference number.

Usage::

    python tools/h2_endpoint_calibration.py
    python tools/h2_endpoint_calibration.py --check docs/experiments/H2-endpoint-calibration.json
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import NormalDist, median
from typing import Any

EVIDENCE_ID = "H2-endpoint-calibration-v1"
SOURCE_EVIDENCE = "0.1.5-evidence-index.json"
FAMILYWISE_ALPHA = 0.05
PRIMARY_FAMILIES = 3
TARGET_POWER = 0.80
CANDIDATE_SESOI_FRACTIONS = (1.0, 0.5, 0.25)
REFERENCE_BLOCK_COUNTS = (128, 158, 300)

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "experiments" / SOURCE_EVIDENCE
DEFAULT_OUTPUT = ROOT / "docs" / "experiments" / "H2-endpoint-calibration.json"

# H2 keeps three families; v0.1.5 named the third one `surge`, which H2 does not
# use.  Only the two shared families feed the calibration.
SHARED_FAMILIES = ("crash", "liquidity_drought")


def first_step_alpha() -> float:
    return FAMILYWISE_ALPHA / PRIMARY_FAMILIES


def _hypotheses(index: dict) -> list[dict[str, Any]]:
    """Flatten the recorded per-hypothesis results."""
    rows: list[dict[str, Any]] = []
    for family, family_block in index["endpoint_results"].items():
        counts = index["experimental_validity"]["families"][family]["nonzero_block_counts"]
        for model, metrics in family_block["models"].items():
            for metric, contrasts in metrics.items():
                for contrast, cell in contrasts.items():
                    if not isinstance(cell, dict) or "effect" not in cell:
                        continue
                    key = f"{model}.{metric}.{contrast}"
                    rows.append(
                        {
                            "family": family,
                            "model": model,
                            "metric": metric,
                            "contrast": contrast,
                            "effect": cell["effect"],
                            "ci_low": cell["ci_low"],
                            "ci_high": cell["ci_high"],
                            "p_value": cell["p_value"],
                            "n_blocks": cell["n_blocks"],
                            "nonzero_blocks": counts[key],
                        }
                    )
    return rows


def _paired_sd(row: dict[str, Any]) -> float:
    """Recover the paired-difference SD implied by a recorded bootstrap CI."""
    half_width = (row["ci_high"] - row["ci_low"]) / 2.0
    standard_error = half_width / NormalDist().inv_cdf(0.975)
    return standard_error * math.sqrt(row["n_blocks"])


def blocks_for(sesoi: float, paired_sd: float) -> int:
    """Blocks needed for ``TARGET_POWER`` on a continuous paired difference."""
    critical = NormalDist().inv_cdf(1.0 - first_step_alpha() / 2.0)
    power_z = NormalDist().inv_cdf(TARGET_POWER)
    return math.ceil(((critical + power_z) * paired_sd / sesoi) ** 2)


def mde_at(blocks: int, paired_sd: float) -> float:
    """Smallest paired difference detectable with ``TARGET_POWER`` at ``blocks``."""
    critical = NormalDist().inv_cdf(1.0 - first_step_alpha() / 2.0)
    power_z = NormalDist().inv_cdf(TARGET_POWER)
    return (critical + power_z) * paired_sd / math.sqrt(blocks)


def build_evidence() -> dict[str, Any]:
    index = json.loads(SOURCE.read_text(encoding="utf-8"))
    rows = _hypotheses(index)
    shared = [row for row in rows if row["family"] in SHARED_FAMILIES]

    occurrence = [row for row in shared if row["metric"] == "occurrence"]
    severity = [row for row in shared if row["metric"] == "severity"]

    # Represent dispersion by the median implied SD rather than any single
    # hypothesis: one extreme cell would otherwise drive the whole plan.
    paired_sd = median(_paired_sd(row) for row in severity)
    largest_effect = max(severity, key=lambda row: abs(row["effect"]))

    return {
        "evidence_id": EVIDENCE_ID,
        "evidence_class": "measured-calibration-from-frozen-evidence",
        "source_evidence": SOURCE_EVIDENCE,
        "shared_families": list(SHARED_FAMILIES),
        "occurrence_endpoint": {
            "hypotheses": len(occurrence),
            "hypotheses_with_any_nonzero_block": sum(
                1 for row in occurrence if row["nonzero_blocks"] > 0
            ),
            "total_nonzero_blocks": sum(row["nonzero_blocks"] for row in occurrence),
            "blocks_per_hypothesis": sorted({row["n_blocks"] for row in occurrence}),
            "paired_difference_is_degenerate": all(
                row["nonzero_blocks"] == 0 for row in occurrence
            ),
            "usable_as_primary_estimand": False,
            "reason": (
                "Every occurrence hypothesis produced 0 non-zero paired blocks over 128 "
                "blocks: the paired difference has zero variance, so power is 0 at any "
                "block count and no SESOI is detectable."
            ),
        },
        "severity_endpoint": {
            "hypotheses": len(severity),
            "hypotheses_with_any_nonzero_block": sum(
                1 for row in severity if row["nonzero_blocks"] > 0
            ),
            "min_nonzero_blocks": min(row["nonzero_blocks"] for row in severity),
            "max_nonzero_blocks": max(row["nonzero_blocks"] for row in severity),
            "usable_as_primary_estimand": True,
            "largest_observed_effect": {
                "hypothesis": (
                    f"{largest_effect['family']}.{largest_effect['model']}"
                    f".{largest_effect['metric']}.{largest_effect['contrast']}"
                ),
                "effect": largest_effect["effect"],
                "ci_low": largest_effect["ci_low"],
                "ci_high": largest_effect["ci_high"],
                "n_blocks": largest_effect["n_blocks"],
            },
            "median_implied_paired_sd": paired_sd,
            "blocks_by_candidate_sesoi": {
                f"{fraction:g}sd": {
                    "sesoi": paired_sd * fraction,
                    "blocks": blocks_for(paired_sd * fraction, paired_sd),
                }
                for fraction in CANDIDATE_SESOI_FRACTIONS
            },
            "minimum_detectable_effect": {
                str(blocks): mde_at(blocks, paired_sd) for blocks in REFERENCE_BLOCK_COUNTS
            },
        },
        "conclusion": (
            "The AI_FORMAL primary estimand must move from occurrence to severity; "
            "occurrence stays as a descriptive secondary. The final block count follows "
            "from the severity SESOI the owner freezes, not from the retired 0.125 "
            "risk-difference number."
        ),
        "sesoi_still_owner_decision": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="H2 primary-endpoint calibration")
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
