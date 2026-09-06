"""Reproduce the conservative Q-304 H2 sample-size feasibility screen.

This is a planning calculation, not empirical human-participant evidence.  It
uses the v0.1 paired-discordance assumption and the H2 frozen sensitivity grid
to answer whether the current cap of 130 assigned participants can reach 80%
power under a conservative first-step Holm threshold.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import NormalDist
from typing import Any

EVIDENCE_ID = "H2-Q304-power-feasibility-v4"
FAMILYWISE_ALPHA = 0.05
PRIMARY_FAMILIES = 3
TARGET_POWER = 0.80
SESOI = 0.125
PAIRED_DISCORDANCE = 0.25
ROUNDS_PER_PARTICIPANT = 8
PAIR_MISSING_RATE = 0.10
PARTICIPANT_CAP = 130
WITHIN_PARTICIPANT_CORRELATIONS = (0.2, 0.5, 0.8)
BASE_COMPENSATION_USD = 22.00
MAX_BONUS_RATE = 0.20
PILOT_PARTICIPANTS = 8
MAX_PREASSIGNMENT_SCREEN_OUTS = 26
SCREEN_OUT_COMPENSATION_USD = 2.00
COMPENSATION_CONTINGENCY_RATE = 0.10
COMPENSATION_RESERVE_USD = 4100.00
RECRUITMENT_PLATFORM = "Prolific"
PLATFORM_FEE_RATE = 0.428
PROJECT_FUNDING_RESERVE_USD = 5900.00


def _power(participants: int, correlation: float) -> float:
    """Return two-sided normal-approximation power for one primary family."""
    observed_rounds = ROUNDS_PER_PARTICIPANT * (1.0 - PAIR_MISSING_RATE)
    pair_difference_variance = PAIRED_DISCORDANCE - SESOI**2
    cluster_mean_variance = (
        pair_difference_variance * (1.0 + (observed_rounds - 1.0) * correlation) / observed_rounds
    )
    standard_error = math.sqrt(cluster_mean_variance / participants)
    noncentrality = SESOI / standard_error
    normal = NormalDist()
    alpha = FAMILYWISE_ALPHA / PRIMARY_FAMILIES
    critical = normal.inv_cdf(1.0 - alpha / 2.0)
    return 1.0 - normal.cdf(critical - noncentrality) + normal.cdf(-critical - noncentrality)


def _required_participants(correlation: float) -> int:
    for participants in range(2, 1001):
        if _power(participants, correlation) >= TARGET_POWER:
            return participants
    raise RuntimeError("required participant count exceeds search bound")


def build_evidence() -> dict[str, Any]:
    results = []
    for correlation in WITHIN_PARTICIPANT_CORRELATIONS:
        required = _required_participants(correlation)
        results.append(
            {
                "within_participant_correlation": correlation,
                "power_at_participant_cap": round(_power(PARTICIPANT_CAP, correlation), 6),
                "minimum_participants_for_target_power": required,
                "power_at_minimum_participants": round(_power(required, correlation), 6),
            }
        )

    cap_meets_target = all(row["power_at_participant_cap"] >= TARGET_POWER for row in results)
    max_bonus_usd = round(BASE_COMPENSATION_USD * MAX_BONUS_RATE, 2)
    max_completion_compensation_usd = round(BASE_COMPENSATION_USD + max_bonus_usd, 2)
    compensation_subtotal_usd = round(
        (PARTICIPANT_CAP + PILOT_PARTICIPANTS) * max_completion_compensation_usd
        + MAX_PREASSIGNMENT_SCREEN_OUTS * SCREEN_OUT_COMPENSATION_USD,
        2,
    )
    compensation_with_contingency_usd = round(
        compensation_subtotal_usd * (1.0 + COMPENSATION_CONTINGENCY_RATE), 2
    )
    platform_fee_on_reserve_usd = round(COMPENSATION_RESERVE_USD * PLATFORM_FEE_RATE, 2)
    project_funding_required_usd = round(COMPENSATION_RESERVE_USD + platform_fee_on_reserve_usd, 2)
    return {
        "schema_version": 1,
        "evidence_id": EVIDENCE_ID,
        "status": "SUPERSEDED_BY_SCOPE_CLARIFICATION",
        "historical_planning_status": (
            "CONSERVATIVE_GO_AT_CAP" if cap_meets_target else "CONSERVATIVE_NO_GO"
        ),
        "generated_by": "python tools/h2_power_feasibility.py",
        "assumptions": {
            "familywise_alpha": FAMILYWISE_ALPHA,
            "primary_families": PRIMARY_FAMILIES,
            "holm_planning_alpha": FAMILYWISE_ALPHA / PRIMARY_FAMILIES,
            "target_power": TARGET_POWER,
            "sesoi_absolute_paired_risk_difference": SESOI,
            "paired_discordance_probability": PAIRED_DISCORDANCE,
            "rounds_per_participant": ROUNDS_PER_PARTICIPANT,
            "pair_missing_rate": PAIR_MISSING_RATE,
            "participant_cap": PARTICIPANT_CAP,
            "within_participant_correlations": list(WITHIN_PARTICIPANT_CORRELATIONS),
        },
        "method": {
            "test": (
                "two-sided normal approximation for the participant-level mean paired difference"
            ),
            "pair_difference_variance": "q - delta^2",
            "cluster_mean_variance": "(q - delta^2) * (1 + (m - 1) * rho) / m",
            "observed_rounds_approximation": "m = rounds_per_participant * (1 - pair_missing_rate)",
            "multiplicity": "conservative first-step Holm threshold alpha/3",
        },
        "results": results,
        "decision": {
            "active_for_current_contract": False,
            "participant_cap_meets_target_power": cap_meets_target,
            "reason": (
                "power at N=130 is at least 0.80 for every frozen correlation scenario"
                if cap_meets_target
                else "power at the participant cap is below 0.80 in at least one scenario"
            ),
            "next_gate": (
                "use H2-dual-track-contract.json and replace this human-participant power model "
                "with paired-seed calibration"
            ),
        },
        "compensation_budget": {
            "currency": "USD",
            "base_compensation_per_completer": BASE_COMPENSATION_USD,
            "max_bonus_rate": MAX_BONUS_RATE,
            "max_bonus_per_completer": max_bonus_usd,
            "max_compensation_per_completer": max_completion_compensation_usd,
            "pilot_participants": PILOT_PARTICIPANTS,
            "max_preassignment_screen_outs": MAX_PREASSIGNMENT_SCREEN_OUTS,
            "screen_out_compensation_per_person": SCREEN_OUT_COMPENSATION_USD,
            "subtotal": compensation_subtotal_usd,
            "contingency_rate": COMPENSATION_CONTINGENCY_RATE,
            "required_after_contingency": compensation_with_contingency_usd,
            "frozen_reserve": COMPENSATION_RESERVE_USD,
            "platform_fees_taxes_and_fx_included": False,
            "recruitment_platform": RECRUITMENT_PLATFORM,
            "platform_fee_rate": PLATFORM_FEE_RATE,
            "platform_fee_on_frozen_reserve": platform_fee_on_reserve_usd,
            "project_funding_required_before_vat_and_fx": project_funding_required_usd,
            "project_funding_reserve_before_vat_and_fx": PROJECT_FUNDING_RESERVE_USD,
        },
        "limitations": [
            "No H1 human input or H2 pilot data exist in the repository.",
            "The paired discordance probability q=0.25 is inherited from v0.1 planning.",
            (
                "This sensitivity screen does not replace the preregistered "
                "simulated-human-policy analysis."
            ),
            "The alpha/3 threshold is conservative relative to later Holm steps.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", type=Path, help="compare a JSON artifact with the calculation")
    args = parser.parse_args()
    evidence = build_evidence()
    if args.check is not None:
        existing = json.loads(args.check.read_text(encoding="utf-8"))
        if existing != evidence:
            print(f"MISMATCH: {args.check}")
            return 1
        print(f"OK: {args.check}")
        return 0
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
