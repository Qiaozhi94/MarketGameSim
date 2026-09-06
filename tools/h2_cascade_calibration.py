"""Calibrate the H2 `liquidation_cascade` family by actually running paired blocks.

v0.1.5 measured `crash` / `surge` / `liquidity_drought`; it never measured a
liquidation-cascade family, so `H2-endpoint-calibration` left that SESOI ``null``
rather than borrowing another family's number.  This tool fills the gap by running
the two frozen policies over paired seeds on the frozen v0.1.5 run parameters.

Two findings drive the contract, and both must survive into the evidence file:

1. Cascades only appear in the ``HH`` regime cell (high leverage, ``maint_bp=1200``).
   The other three cells produce zero liquidations at all, so a calibration that
   averaged over cells would report a variance that does not exist.
2. ``chain_depth`` is **0 in every observed chain**.  Per `contracts/event-schema.md`
   depth 0 means "not cascade-triggered", so what varies is the number of accounts
   liquidated under one ``chain_id``, not a causal cascade.  The severity metric is
   therefore honest only if it is read as "accounts liquidated in one chain", and
   the spec's occurrence condition (``max(chain_depth) >= 1``) is unsatisfiable in
   this model family -- another degenerate endpoint.

Usage::

    python tools/h2_cascade_calibration.py                # full run, writes evidence
    python tools/h2_cascade_calibration.py --seeds 16     # quick probe
    python tools/h2_cascade_calibration.py --check docs/experiments/H2-cascade-calibration.json
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from decimal import Decimal
from pathlib import Path
from statistics import NormalDist
from typing import Any

from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.experiment.config import ExperimentConfig
from market_game_sim.experiment.runner import RunResult, run_one
from market_game_sim.ledger.account import initial_margin_bp_for_tier
from market_game_sim.rng.distributions import discrete_choice, uniform_range

EVIDENCE_ID = "H2-cascade-calibration-v1"
CONTROL_MODEL = "risk_budget_linear_v1"
TREATMENT_MODEL = "risk_budget_threshold_v1"
FAMILYWISE_ALPHA = 0.05
PRIMARY_FAMILIES = 3
TARGET_POWER = 0.80
SESOI_SD_FRACTION = 0.25
DEFAULT_SEEDS = 256
FIRST_SEED = 40_000
# Only the high-leverage / high-maintenance cell produces liquidations at all.
CASCADE_CELL = {"maint_bp": 1200, "leverage_weights": {10: 3334, 20: 3333, 50: 3333}}
PROBE_CELLS = {
    "LL": (300, {2: 3334, 3: 3333, 5: 3333}),
    "LH": (1200, {2: 3334, 3: 3333, 5: 3333}),
    "HL": (300, {10: 3334, 20: 3333, 50: 3333}),
    "HH": (1200, {10: 3334, 20: 3333, 50: 3333}),
}

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "docs" / "experiments" / "0.1.5-factorial-plan.json"
DEFAULT_OUTPUT = ROOT / "docs" / "experiments" / "H2-cascade-calibration.json"


def _run_parameters() -> dict[str, Any]:
    return json.loads(PLAN.read_text(encoding="utf-8"))["run_parameters"]


def build_config(seed: int, model_id: str, maint_bp: int, weights: dict[int, int]):
    """Frozen v0.1.5 run parameters with only the goal model varying."""
    rp = _run_parameters()
    tier, _ = discrete_choice(weights, seed, "belief-0", "bench_leverage_tier", 0, 0)
    appetite, _ = uniform_range(
        Decimal(500), Decimal(20_000), seed, "belief-0", "risk_appetite", 0, 0
    )
    belief = AgentSpec(
        agent_id="belief-0",
        role="belief_trader",
        observe_interval_ns=rp["belief_observe_interval_ns"],
        latency_ns=rp["belief_latency_ns"],
        leverage_tier=tier,
        initial_bp=initial_margin_bp_for_tier(tier),
        goal_model_id=model_id,
        risk_appetite_x1000=int(appetite),
        aggressiveness_bp=rp["belief_aggressiveness_bp"],
        max_order_qty=rp["belief_max_order_qty"],
        ewma_half_life_trades=rp["belief_ewma_half_life_trades"],
    )
    maker = AgentSpec(
        agent_id="mm-0",
        role="inventory_market_maker",
        observe_interval_ns=rp["market_maker_observe_interval_ns"],
        latency_ns=rp["market_maker_latency_ns"],
        is_market_maker=True,
        leverage_tier=rp["market_maker_leverage_tier"],
        initial_bp=rp["market_maker_initial_bp"],
        half_spread_ticks=rp["market_maker_half_spread_ticks"],
        quote_size=rp["market_maker_quote_size"],
        max_inventory=rp["market_maker_max_inventory"],
        inventory_skew_k_bp=rp["market_maker_inventory_skew_k_bp"],
    )
    return ExperimentConfig(
        seed=seed,
        initial_price_ticks=rp["initial_price_ticks"],
        max_transactions=rp["max_transactions"],
        maint_bp=maint_bp,
        agent_specs=[maker, belief],
    )


def chain_severity(result: RunResult) -> int:
    """Accounts liquidated under the largest single ``chain_id`` (0 if none)."""
    sizes = result.liquidation_metrics.chain_size_by_id
    return max(sizes.values()) if sizes else 0


def spec_occurrence(result: RunResult) -> int:
    """The spec's occurrence condition: >=2 accounts in one chain AND depth >= 1."""
    metrics = result.liquidation_metrics
    sizes = metrics.chain_size_by_id
    if not sizes or max(sizes.values()) < 2:
        return 0
    return 1 if max(metrics.chain_depth_counts, default=0) >= 1 else 0


def blocks_for(sesoi: float, paired_sd: float) -> int:
    critical = NormalDist().inv_cdf(1.0 - FAMILYWISE_ALPHA / PRIMARY_FAMILIES / 2.0)
    power_z = NormalDist().inv_cdf(TARGET_POWER)
    return math.ceil(((critical + power_z) * paired_sd / sesoi) ** 2)


def probe_cells(seeds: int = 32) -> dict[str, dict[str, int]]:
    """Which regime cells produce liquidations at all."""
    summary: dict[str, dict[str, int]] = {}
    for cell_id, (maint_bp, weights) in PROBE_CELLS.items():
        runs = with_liquidation = 0
        for seed in range(FIRST_SEED, FIRST_SEED + seeds):
            for model in (CONTROL_MODEL, TREATMENT_MODEL):
                result = run_one(build_config(seed, model, maint_bp, weights))
                runs += 1
                with_liquidation += 1 if result.liquidation_metrics.total_liquidations else 0
        summary[cell_id] = {"runs": runs, "runs_with_liquidation": with_liquidation}
    return summary


def build_evidence(seeds: int = DEFAULT_SEEDS, *, include_probe: bool = True) -> dict[str, Any]:
    maint_bp = CASCADE_CELL["maint_bp"]
    weights = CASCADE_CELL["leverage_weights"]

    severity_diffs: list[int] = []
    occurrence_diffs: list[int] = []
    depths: set[int] = set()
    control_nonzero = treatment_nonzero = 0

    for seed in range(FIRST_SEED, FIRST_SEED + seeds):
        control = run_one(build_config(seed, CONTROL_MODEL, maint_bp, weights))
        treatment = run_one(build_config(seed, TREATMENT_MODEL, maint_bp, weights))
        severity_diffs.append(chain_severity(treatment) - chain_severity(control))
        occurrence_diffs.append(spec_occurrence(treatment) - spec_occurrence(control))
        control_nonzero += 1 if chain_severity(control) else 0
        treatment_nonzero += 1 if chain_severity(treatment) else 0
        for result in (control, treatment):
            depths.update(result.liquidation_metrics.chain_depth_counts)

    paired_sd = statistics.stdev(severity_diffs)
    sesoi = paired_sd * SESOI_SD_FRACTION

    return {
        "evidence_id": EVIDENCE_ID,
        "evidence_class": "measured-calibration-from-paired-simulation",
        "family": "liquidation_cascade",
        "regime_cell": {
            "maint_bp": maint_bp,
            "leverage_weights": {str(k): v for k, v in weights.items()},
        },
        "models": {"control": CONTROL_MODEL, "treatment": TREATMENT_MODEL},
        "paired_blocks": seeds,
        "severity_metric": "max accounts liquidated under one chain_id",
        "severity": {
            "nonzero_paired_blocks": sum(1 for d in severity_diffs if d != 0),
            "mean_paired_difference": statistics.fmean(severity_diffs),
            "paired_sd": paired_sd,
            "blocks_with_control_chain": control_nonzero,
            "blocks_with_treatment_chain": treatment_nonzero,
            "usable_as_primary_estimand": paired_sd > 0.0,
        },
        "spec_occurrence": {
            "condition": ">=2 accounts in one chain AND max(chain_depth) >= 1",
            "nonzero_paired_blocks": sum(1 for d in occurrence_diffs if d != 0),
            "paired_difference_is_degenerate": all(d == 0 for d in occurrence_diffs),
            "usable_as_primary_estimand": False,
        },
        "observed_chain_depths": sorted(depths),
        "true_cascade_observed": any(depth >= 1 for depth in depths),
        "sesoi_scale": f"{SESOI_SD_FRACTION} x measured paired SD",
        "sesoi": sesoi,
        "blocks_required": blocks_for(sesoi, paired_sd),
        "cell_probe": probe_cells() if include_probe else None,
        "limitations": [
            "Only the HH cell (high leverage, maint_bp=1200) produces liquidations; the other "
            "three cells produce none, so this SESOI applies to that cell's scenario distribution.",
            "Every observed chain has chain_depth 0, which event-schema defines as "
            "'not cascade-triggered': no causal cascade propagation was observed at all.",
            "The severity metric therefore counts accounts liquidated together under one "
            "chain_id; it must not be described as cascade depth.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="H2 liquidation-cascade calibration")
    parser.add_argument("--seeds", type=int, default=DEFAULT_SEEDS)
    parser.add_argument("--check", type=Path, default=None)
    parser.add_argument("--write", type=Path, default=None)
    args = parser.parse_args()

    if args.check is not None:
        recorded = json.loads(args.check.read_text(encoding="utf-8"))
        current = build_evidence(recorded["paired_blocks"])
        if recorded != current:
            print(f"{args.check} 与当前模拟不一致；重新生成后再提交")
            return 1
        print(f"{args.check} 与当前模拟一致")
        return 0

    evidence = build_evidence(args.seeds)
    target = args.write or DEFAULT_OUTPUT
    target.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已写入 {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
