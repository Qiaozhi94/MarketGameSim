"""T213: frozen 2x2 seed blocks and three-family factorial inference.

The module consumes real :class:`RunResult` objects but never launches a
formal run by itself.  T215 owns execution; T213 owns the fail-closed pairing,
whole-block exclusions, endpoint projection, contrasts, uncertainty and the
three independent BH families frozen by the 0.1.5 preregistration.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from market_game_sim.agent.goal import RiskBudgetThresholdV1, get_goal_model
from market_game_sim.experiment.config import ExperimentConfig, compute_config_hash
from market_game_sim.experiment.run_family import (
    RunFamily,
    from_experiment_config,
    validate_run_family,
    validate_seed_plan,
)
from market_game_sim.experiment.stats import benjamini_hochberg
from market_game_sim.ledger.account import initial_margin_bp_for_tier
from market_game_sim.rng.distributions import discrete_choice, uniform_range

if TYPE_CHECKING:
    from market_game_sim.experiment.runner import RunResult


CELL_IDS = ("LL", "LH", "HL", "HH")
MODEL_IDS = ("risk_budget_linear_v1", "risk_budget_threshold_v1")
ENDPOINT_FAMILIES = ("crash", "surge", "liquidity_drought")
METRICS = ("occurrence", "severity")
CONTRASTS = ("L", "M", "LxM")
TECHNICAL_INVALID_CODES = frozenset({"TI-1", "TI-2", "TI-3", "TI-4", "TI-5"})
PREREGISTRATION_ID = "0.1.5-flagship-preregistration-v1"
PREREGISTRATION_SHA256 = "a3d2021eb16e17dd40c5ec2427f22e7e063f096c56c8caf8806c0b9594668116"


class FactorialPlanError(ValueError):
    """The frozen plan, cell configuration or paired result set is invalid."""


@dataclass(frozen=True)
class FactorialSeedPlan:
    planned_seeds: tuple[int, ...]
    reserve_seeds: tuple[int, ...]
    minimum_valid_blocks: int

    @property
    def pool(self) -> tuple[int, ...]:
        return self.planned_seeds + self.reserve_seeds

    def validate(self) -> None:
        if not self.planned_seeds:
            raise FactorialPlanError("seed plan requires at least one planned seed")
        if type(self.minimum_valid_blocks) is not int or self.minimum_valid_blocks <= 0:
            raise FactorialPlanError("minimum_valid_blocks must be positive")
        if self.minimum_valid_blocks > len(self.planned_seeds):
            raise FactorialPlanError("minimum_valid_blocks cannot exceed the planned seed count")
        seeds = self.pool
        if any(type(seed) is not int for seed in seeds):
            raise FactorialPlanError("all planned/reserve seeds must be integers")
        if len(set(seeds)) != len(seeds):
            raise FactorialPlanError("planned/reserve seeds must be globally unique")


FROZEN_SEED_PLAN = FactorialSeedPlan(
    planned_seeds=tuple(range(30_000, 30_128)),
    reserve_seeds=tuple(range(30_128, 30_144)),
    minimum_valid_blocks=128,
)


@dataclass(frozen=True)
class FactorialPlanBinding:
    preregistration_id: str
    preregistration_path: Path
    preregistration_sha256: str
    manifest_path: Path
    manifest_sha256: str
    seed_plan: FactorialSeedPlan
    bootstrap_resamples: int
    bootstrap_seed: int
    sign_flip_resamples: int
    sign_flip_seed: int
    bh_q: float

    def report_reference(self) -> dict[str, Any]:
        return {
            "preregistration_id": self.preregistration_id,
            "preregistration_path": _portable_path(self.preregistration_path),
            "preregistration_sha256": self.preregistration_sha256,
            "factorial_plan_path": _portable_path(self.manifest_path),
            "factorial_plan_sha256": self.manifest_sha256,
        }


@dataclass(frozen=True)
class EndpointObservation:
    occurrence: float
    severity: float


@dataclass(frozen=True)
class FactorialEffect:
    effect: float
    ci_low: float
    ci_high: float
    p_value: float
    n_blocks: int
    bootstrap_resamples: int
    sign_flip_resamples: int

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def load_factorial_plan(path: str | Path) -> FactorialPlanBinding:
    """Resolve the machine plan and verify its frozen Markdown digest."""
    manifest_path = Path(path).resolve()
    raw = _read_json_object(manifest_path)
    _require_exact_keys(
        raw,
        {
            "schema_version",
            "preregistration_id",
            "status",
            "preregistration_path",
            "preregistration_sha256",
            "models",
            "cells",
            "leverage_tier_weights_bp",
            "leverage_tier_mechanism",
            "goal_parameters",
            "seed_plan",
            "analysis",
        },
        "factorial plan",
    )
    if raw["schema_version"] != 1 or raw["status"] != "FROZEN":
        raise FactorialPlanError("factorial plan must have schema_version=1 and status=FROZEN")
    if raw["preregistration_id"] != PREREGISTRATION_ID:
        raise FactorialPlanError(f"preregistration_id must be {PREREGISTRATION_ID!r}")
    if raw["preregistration_sha256"] != PREREGISTRATION_SHA256:
        raise FactorialPlanError("preregistration_sha256 drifted from the T202 freeze")
    if raw["preregistration_path"] != "docs/experiments/0.1.5-preregistration.md":
        raise FactorialPlanError("preregistration_path drifted from the T202 repository path")
    if tuple(raw["models"]) != MODEL_IDS:
        raise FactorialPlanError(f"factorial plan models must be {MODEL_IDS}")
    _validate_cells_payload(raw["cells"])
    _validate_tier_weights(raw["leverage_tier_weights_bp"])
    if raw["leverage_tier_mechanism"] != "bench_leverage_tier":
        raise FactorialPlanError("leverage_tier_mechanism must remain 'bench_leverage_tier'")
    _validate_goal_parameters(raw["goal_parameters"])

    seed_payload = raw["seed_plan"]
    _require_exact_keys(
        seed_payload,
        {
            "planned_start",
            "planned_end",
            "reserve_start",
            "reserve_end",
            "minimum_valid_blocks",
        },
        "seed_plan",
    )
    integers = list(seed_payload.values())
    if any(type(value) is not int for value in integers):
        raise FactorialPlanError("seed_plan fields must be integers")
    expected_seed_payload = {
        "planned_start": 30_000,
        "planned_end": 30_127,
        "reserve_start": 30_128,
        "reserve_end": 30_143,
        "minimum_valid_blocks": 128,
    }
    if seed_payload != expected_seed_payload:
        raise FactorialPlanError("seed_plan drifted from the T202 frozen 128+16 plan")
    plan = FROZEN_SEED_PLAN
    plan.validate()

    analysis = raw["analysis"]
    _require_exact_keys(
        analysis,
        {
            "endpoint_families",
            "metrics",
            "contrasts",
            "bootstrap_resamples",
            "bootstrap_seed",
            "sign_flip_resamples",
            "sign_flip_seed",
            "bh_q",
            "tests_per_family",
        },
        "analysis",
    )
    if tuple(analysis["endpoint_families"]) != ENDPOINT_FAMILIES:
        raise FactorialPlanError("analysis.endpoint_families drifted from the frozen set")
    if tuple(analysis["metrics"]) != METRICS or tuple(analysis["contrasts"]) != CONTRASTS:
        raise FactorialPlanError("analysis metrics/contrasts drifted from the frozen set")
    if analysis["tests_per_family"] != len(MODEL_IDS) * len(METRICS) * len(CONTRASTS):
        raise FactorialPlanError("analysis.tests_per_family is inconsistent")
    for field in (
        "bootstrap_resamples",
        "bootstrap_seed",
        "sign_flip_resamples",
        "sign_flip_seed",
    ):
        if type(analysis[field]) is not int:
            raise FactorialPlanError(f"analysis.{field} must be an integer")
    if analysis["bootstrap_resamples"] <= 0 or analysis["sign_flip_resamples"] <= 0:
        raise FactorialPlanError("resample counts must be positive")
    bh_q = analysis["bh_q"]
    if isinstance(bh_q, bool) or not isinstance(bh_q, (int, float)) or not (0 < bh_q < 1):
        raise FactorialPlanError("analysis.bh_q must be in (0, 1)")
    frozen_analysis = {
        "bootstrap_resamples": 10_000,
        "bootstrap_seed": 913_201,
        "sign_flip_resamples": 100_000,
        "sign_flip_seed": 913_202,
        "bh_q": 0.05,
    }
    for field, expected in frozen_analysis.items():
        if analysis[field] != expected:
            raise FactorialPlanError(
                f"analysis.{field} drifted from T202: expected {expected!r}, "
                f"got {analysis[field]!r}"
            )

    preregistration_path = _resolve_repo_relative(manifest_path, raw["preregistration_path"])
    try:
        preregistration_text = preregistration_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise FactorialPlanError(
            f"cannot resolve preregistration {preregistration_path}: {exc}"
        ) from exc
    canonical_preregistration = preregistration_text.replace("\r\n", "\n").replace("\r", "\n")
    actual_prereg_digest = hashlib.sha256(canonical_preregistration.encode("utf-8")).hexdigest()
    if actual_prereg_digest != raw["preregistration_sha256"]:
        raise FactorialPlanError(
            "preregistration SHA-256 drifted after freeze "
            f"(expected {raw['preregistration_sha256']}, got {actual_prereg_digest})"
        )
    return FactorialPlanBinding(
        preregistration_id=raw["preregistration_id"],
        preregistration_path=preregistration_path,
        preregistration_sha256=actual_prereg_digest,
        manifest_path=manifest_path,
        manifest_sha256=_canonical_json_digest(raw),
        seed_plan=plan,
        bootstrap_resamples=analysis["bootstrap_resamples"],
        bootstrap_seed=analysis["bootstrap_seed"],
        sign_flip_resamples=analysis["sign_flip_resamples"],
        sign_flip_seed=analysis["sign_flip_seed"],
        bh_q=float(bh_q),
    )


def validate_flagship_configs(
    configs: Mapping[str, Mapping[str, ExperimentConfig]], binding: FactorialPlanBinding
) -> dict[str, dict[str, str]]:
    """Validate one seed's eight model/cell configs before runs are launched."""
    binding.seed_plan.validate()
    _require_exact_keys(configs, set(MODEL_IDS), "configs.models")
    expected_seed_plan = {
        "n_seeds": len(binding.seed_plan.pool),
        "seeds": list(binding.seed_plan.pool),
    }
    fingerprints: dict[str, dict[str, str]] = {}
    frozen_remainder: dict[str, Any] | None = None
    tier_assignment_by_level: dict[str, dict[str, int]] = {}
    execution_seed: int | None = None
    for model_id in MODEL_IDS:
        model_cells = configs[model_id]
        _require_exact_keys(model_cells, set(CELL_IDS), f"configs.{model_id}.cells")
        fingerprints[model_id] = {}
        for cell_id in CELL_IDS:
            cfg = model_cells[cell_id]
            if cfg.seed not in binding.seed_plan.pool:
                raise FactorialPlanError(
                    f"configs.{model_id}.{cell_id}.seed={cfg.seed} is outside the frozen pool"
                )
            if execution_seed is None:
                execution_seed = cfg.seed
            elif cfg.seed != execution_seed:
                raise FactorialPlanError(
                    f"configs.{model_id}.{cell_id}.seed={cfg.seed} does not match "
                    f"the paired block seed {execution_seed}"
                )
            if cfg.group_label != cell_id:
                raise FactorialPlanError(
                    f"configs.{model_id}.{cell_id}.group_label must be {cell_id!r}"
                )
            expected_l = "low" if cell_id[0] == "L" else "high"
            expected_m = "low" if cell_id[1] == "L" else "high"
            expected_maint = 300 if expected_m == "low" else 700
            if cfg.run_family != RunFamily.SPONTANEOUS:
                raise FactorialPlanError(
                    f"configs.{model_id}.{cell_id}.run_family must be SPONTANEOUS"
                )
            validate_run_family(from_experiment_config(cfg))
            if (cfg.l_level, cfg.m_level, cfg.maint_bp) != (
                expected_l,
                expected_m,
                expected_maint,
            ):
                raise FactorialPlanError(
                    f"configs.{model_id}.{cell_id} has wrong L/M encoding: "
                    f"{cfg.l_level}/{cfg.m_level}/{cfg.maint_bp}"
                )
            if validate_seed_plan(cfg.seed_plan) != expected_seed_plan:
                raise FactorialPlanError(
                    f"configs.{model_id}.{cell_id}.seed_plan is not the frozen full pool"
                )
            belief_agents = [spec for spec in cfg.agent_specs if not spec.is_market_maker]
            if not belief_agents:
                raise FactorialPlanError(f"configs.{model_id}.{cell_id} has no belief agents")
            agent_ids = [spec.agent_id for spec in cfg.agent_specs]
            if len(set(agent_ids)) != len(agent_ids):
                raise FactorialPlanError(
                    f"configs.{model_id}.{cell_id}.agent_specs has duplicate agent_id values"
                )
            allowed_tiers = {2, 3, 5} if expected_l == "low" else {10, 20, 50}
            tier_weights = (
                {2: 3334, 3: 3333, 5: 3333}
                if expected_l == "low"
                else {10: 3334, 20: 3333, 50: 3333}
            )
            for spec in belief_agents:
                if spec.goal_model_id != model_id:
                    raise FactorialPlanError(
                        f"configs.{model_id}.{cell_id}.agent_specs[{spec.agent_id}]."
                        f"goal_model_id={spec.goal_model_id!r}"
                    )
                if spec.leverage_tier not in allowed_tiers:
                    raise FactorialPlanError(
                        f"configs.{model_id}.{cell_id}.agent_specs[{spec.agent_id}]."
                        f"leverage_tier={spec.leverage_tier} outside {sorted(allowed_tiers)}"
                    )
                expected_tier, _ = discrete_choice(
                    tier_weights,
                    cfg.seed,
                    spec.agent_id,
                    "bench_leverage_tier",
                    0,
                    0,
                )
                if spec.leverage_tier != expected_tier:
                    raise FactorialPlanError(
                        f"configs.{model_id}.{cell_id}.agent_specs[{spec.agent_id}]."
                        f"leverage_tier={spec.leverage_tier} does not match the frozen "
                        f"semantic draw {expected_tier}"
                    )
                expected_appetite, _ = uniform_range(
                    Decimal(500),
                    Decimal(20_000),
                    cfg.seed,
                    spec.agent_id,
                    "risk_appetite",
                    0,
                    0,
                )
                if spec.risk_appetite_x1000 != int(expected_appetite):
                    raise FactorialPlanError(
                        f"configs.{model_id}.{cell_id}.agent_specs[{spec.agent_id}]."
                        f"risk_appetite_x1000={spec.risk_appetite_x1000} does not match "
                        f"the frozen semantic draw {int(expected_appetite)}"
                    )
                expected_initial = initial_margin_bp_for_tier(spec.leverage_tier)
                if spec.initial_bp != expected_initial:
                    raise FactorialPlanError(
                        f"configs.{model_id}.{cell_id}.agent_specs[{spec.agent_id}].initial_bp "
                        f"must be {expected_initial}, got {spec.initial_bp}"
                    )
            tier_assignment = {spec.agent_id: spec.leverage_tier for spec in belief_agents}
            if expected_l not in tier_assignment_by_level:
                tier_assignment_by_level[expected_l] = tier_assignment
            elif tier_assignment != tier_assignment_by_level[expected_l]:
                raise FactorialPlanError(
                    f"configs.{model_id}.{cell_id} changes realized tier assignment "
                    f"within L_{expected_l}; M/model cells must share the same draw path"
                )
            remainder = _non_treatment_snapshot(cfg)
            if frozen_remainder is None:
                frozen_remainder = remainder
            elif remainder != frozen_remainder:
                path, expected, actual = _first_difference(frozen_remainder, remainder)
                raise FactorialPlanError(
                    f"four-cell parity violated at {path}: expected {expected!r}, got {actual!r}"
                )
            fingerprints[model_id][cell_id] = compute_config_hash(cfg)
    threshold = get_goal_model("risk_budget_threshold_v1")
    if not isinstance(threshold, RiskBudgetThresholdV1) or (
        threshold.theta_in,
        threshold.theta_out,
        threshold.k_x1000,
    ) != (3000, 1200, 600):
        raise FactorialPlanError(
            "registered risk_budget_threshold_v1 parameters drifted from 3000/1200/600"
        )
    return fingerprints


def event_summary_sha256(result: RunResult) -> str:
    """Canonical event-summary digest used by the frozen TI-2 rerun audit."""
    canonical = json.dumps(
        result.events,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def audit_deterministic_rerun(primary: RunResult, audit: RunResult) -> str | None:
    """Return ``TI-2`` on a same-seed event digest mismatch, else ``None``."""
    if primary.seed != audit.seed:
        raise FactorialPlanError(
            f"TI-2 audit seed mismatch: primary={primary.seed}, audit={audit.seed}"
        )
    if event_summary_sha256(primary) != event_summary_sha256(audit):
        return "TI-2"
    return None


def endpoint_observations(
    result: RunResult, initial_price_ticks: int = 10_000
) -> dict[str, EndpointObservation]:
    """Project one valid run into the three overlapping endpoint families."""
    if result.classification.is_technical_invalid:
        raise FactorialPlanError("technical-invalid runs cannot be projected into endpoints")
    prices = [
        event["price_ticks"]
        for event in result.events
        if event.get("event_type") == "TRADE_SETTLE"
        and type(event.get("price_ticks")) is int
        and event["price_ticks"] > 0
    ]
    log_moves = [math.log(price / initial_price_ticks) for price in prices]
    max_up = max([0.0, *log_moves])
    max_down = max([0.0, *(-move for move in log_moves)])
    codes = set(result.classification.economic_endpoint_codes)
    drained_sides = set(result.classification.ev4_drained_sides)
    if "EV-4" in codes and not drained_sides:
        drained_sides = {"bid", "ask"}
    crash = "EV-1" in codes or min([0.0, *log_moves]) < -math.log(10) or "bid" in drained_sides
    surge = max_up > math.log(10) or "ask" in drained_sides
    liquidity = "EV-3" in codes or bool(drained_sides)
    run_total_ns = max(
        (
            event.get("timestamp", 0)
            for event in result.events
            if type(event.get("timestamp", 0)) is int
        ),
        default=0,
    )
    trade_times = sorted(
        event["timestamp"]
        for event in result.events
        if event.get("event_type") == "TRADE_SETTLE" and type(event.get("timestamp")) is int
    )
    boundaries = [0, *trade_times, run_total_ns]
    max_idle = max((b - a for a, b in zip(boundaries, boundaries[1:], strict=False)), default=0)
    idle_ratio = max_idle / run_total_ns if run_total_ns > 0 else 0.0
    return {
        "crash": EndpointObservation(float(crash), max_down),
        "surge": EndpointObservation(float(surge), max_up),
        "liquidity_drought": EndpointObservation(float(liquidity), idle_ratio),
    }


def analyze_flagship_results(
    results: Mapping[str, Mapping[str, Sequence[RunResult]]],
    binding: FactorialPlanBinding,
    *,
    initial_price_ticks: int = 10_000,
    bootstrap_resamples: int | None = None,
    sign_flip_resamples: int | None = None,
) -> dict[str, Any]:
    """Build the pre-registered factorial report from eight paired run series."""
    binding.seed_plan.validate()
    _require_exact_keys(results, set(MODEL_IDS), "results.models")
    seed_order: list[int] | None = None
    by_model_cell_seed: dict[str, dict[str, dict[int, RunResult]]] = {}
    for model_id in MODEL_IDS:
        _require_exact_keys(results[model_id], set(CELL_IDS), f"results.{model_id}.cells")
        by_model_cell_seed[model_id] = {}
        for cell_id in CELL_IDS:
            runs = list(results[model_id][cell_id])
            if any(run.group_label != cell_id for run in runs):
                raise FactorialPlanError(
                    f"results.{model_id}.{cell_id} contains a run with the wrong group_label"
                )
            seeds = [run.seed for run in runs]
            if len(set(seeds)) != len(seeds):
                raise FactorialPlanError(f"results.{model_id}.{cell_id} has duplicate seeds")
            if seed_order is None:
                seed_order = seeds
            elif seeds != seed_order:
                raise FactorialPlanError(
                    f"results.{model_id}.{cell_id} seed order differs from the paired block order"
                )
            by_model_cell_seed[model_id][cell_id] = dict(zip(seeds, runs, strict=True))
    executed_seeds = seed_order or []
    expected_prefix = list(binding.seed_plan.pool[: len(executed_seeds)])
    if executed_seeds != expected_prefix:
        raise FactorialPlanError(
            f"executed seeds must be the frozen pool prefix {expected_prefix}, got {executed_seeds}"
        )

    valid_seeds: list[int] = []
    exclusions: dict[int, list[str]] = {}
    reached_target_at: int | None = None
    for index, seed in enumerate(executed_seeds):
        codes: set[str] = set()
        for model_id in MODEL_IDS:
            for cell_id in CELL_IDS:
                classification = by_model_cell_seed[model_id][cell_id][seed].classification
                if classification.is_technical_invalid != (
                    classification.technical_invalid_code is not None
                ):
                    raise FactorialPlanError(
                        f"seed {seed} has inconsistent technical-invalid flag/code"
                    )
                if classification.is_technical_invalid:
                    code = classification.technical_invalid_code
                    if code not in TECHNICAL_INVALID_CODES:
                        raise FactorialPlanError(
                            f"seed {seed} carries unknown technical invalid code {code!r}"
                        )
                    codes.add(code)
        if codes:
            exclusions[seed] = sorted(codes)
        else:
            valid_seeds.append(seed)
            if len(valid_seeds) == binding.seed_plan.minimum_valid_blocks:
                reached_target_at = index
                break
    if reached_target_at is not None and reached_target_at != len(executed_seeds) - 1:
        raise FactorialPlanError(
            "runs continue after the frozen minimum valid block count was reached"
        )
    sufficient = len(valid_seeds) >= binding.seed_plan.minimum_valid_blocks
    if not sufficient and len(executed_seeds) < len(binding.seed_plan.pool):
        raise FactorialPlanError(
            "seed execution stopped before reaching the target while frozen reserve seeds remained"
        )

    report: dict[str, Any] = {
        "schema_version": 1,
        "plan": binding.report_reference(),
        "seed_plan": {
            "executed_seeds": executed_seeds,
            "valid_seeds": valid_seeds,
            "excluded_seed_blocks": exclusions,
            "minimum_valid_blocks": binding.seed_plan.minimum_valid_blocks,
            "evidence_sufficient": sufficient,
        },
        "endpoint_families": {},
        "direction_asymmetry": {},
    }
    if not valid_seeds:
        for family in ENDPOINT_FAMILIES:
            report["endpoint_families"][family] = {
                "evidence_sufficient": False,
                "inference_eligible": False,
                "reason": "no technically valid paired seed blocks",
                "models": {},
            }
        return report

    observations: dict[str, dict[str, dict[int, dict[str, EndpointObservation]]]] = {}
    for model_id in MODEL_IDS:
        observations[model_id] = {}
        for cell_id in CELL_IDS:
            observations[model_id][cell_id] = {
                seed: endpoint_observations(
                    by_model_cell_seed[model_id][cell_id][seed], initial_price_ticks
                )
                for seed in valid_seeds
            }

    n_bootstrap = (
        binding.bootstrap_resamples if bootstrap_resamples is None else bootstrap_resamples
    )
    n_sign_flip = (
        binding.sign_flip_resamples if sign_flip_resamples is None else sign_flip_resamples
    )
    if type(n_bootstrap) is not int or n_bootstrap <= 0:
        raise FactorialPlanError("bootstrap_resamples must be a positive integer")
    if type(n_sign_flip) is not int or n_sign_flip <= 0:
        raise FactorialPlanError("sign_flip_resamples must be a positive integer")
    for family in ENDPOINT_FAMILIES:
        family_report: dict[str, Any] = {
            "evidence_sufficient": sufficient,
            "inference_eligible": sufficient,
            "models": {},
        }
        p_values: dict[str, float] = {}
        for model_id in MODEL_IDS:
            model_report: dict[str, Any] = {}
            for metric in METRICS:
                metric_report: dict[str, Any] = {}
                blocks = [
                    {
                        cell_id: getattr(observations[model_id][cell_id][seed][family], metric)
                        for cell_id in CELL_IDS
                    }
                    for seed in valid_seeds
                ]
                for contrast in CONTRASTS:
                    hypothesis_id = f"{model_id}.{metric}.{contrast}"
                    effect = _factorial_effect(
                        blocks,
                        contrast,
                        n_bootstrap,
                        n_sign_flip,
                        binding.bootstrap_seed,
                        binding.sign_flip_seed,
                        f"{family}.{hypothesis_id}",
                    )
                    metric_report[contrast] = effect.as_dict()
                    p_values[hypothesis_id] = effect.p_value
                model_report[metric] = metric_report
            family_report["models"][model_id] = model_report
        decisions = benjamini_hochberg(p_values, q=binding.bh_q)
        for hypothesis_id, decision in decisions.items():
            model_id, metric, contrast = hypothesis_id.split(".")
            effect_dict = family_report["models"][model_id][metric][contrast]
            effect_dict["bh_adjusted_p_value"] = decision.adjusted_p_value
            effect_dict["bh_significant"] = decision.significant
        family_report["bh_q"] = binding.bh_q
        family_report["bh_family_size"] = len(decisions)
        report["endpoint_families"][family] = family_report

    for model_id in MODEL_IDS:
        report["direction_asymmetry"][model_id] = {}
        for cell_id in CELL_IDS:
            values = [
                observations[model_id][cell_id][seed]["crash"].occurrence
                - observations[model_id][cell_id][seed]["surge"].occurrence
                for seed in valid_seeds
            ]
            report["direction_asymmetry"][model_id][cell_id] = _bootstrap_mean(
                values,
                n_bootstrap,
                binding.bootstrap_seed,
                f"direction_asymmetry.{model_id}.{cell_id}",
            )
    return report


def _factorial_effect(
    blocks: list[dict[str, float]],
    contrast: str,
    n_bootstrap: int,
    n_sign_flip: int,
    bootstrap_seed: int,
    sign_flip_seed: int,
    label: str,
) -> FactorialEffect:
    values = [_contrast_value(block, contrast) for block in blocks]
    effect = sum(values) / len(values)
    bootstrap_rng = random.Random(_derived_seed(bootstrap_seed, label))
    bootstrap_values = []
    for _ in range(n_bootstrap):
        bootstrap_values.append(
            sum(values[bootstrap_rng.randrange(len(values))] for _ in values) / len(values)
        )
    bootstrap_values.sort()
    ci_low, ci_high = _percentile_interval(bootstrap_values)
    sign_rng = random.Random(_derived_seed(sign_flip_seed, label))
    abs_observed = abs(effect)
    extreme = 0
    for _ in range(n_sign_flip):
        permuted = sum(value if sign_rng.randrange(2) else -value for value in values) / len(values)
        if abs(permuted) >= abs_observed:
            extreme += 1
    p_value = (1 + extreme) / (n_sign_flip + 1)
    return FactorialEffect(
        effect=effect,
        ci_low=ci_low,
        ci_high=ci_high,
        p_value=p_value,
        n_blocks=len(blocks),
        bootstrap_resamples=n_bootstrap,
        sign_flip_resamples=n_sign_flip,
    )


def _contrast_value(block: Mapping[str, float], contrast: str) -> float:
    _require_exact_keys(block, set(CELL_IDS), "factorial block")
    if contrast == "L":
        return (block["HL"] + block["HH"] - block["LL"] - block["LH"]) / 2
    if contrast == "M":
        return (block["LH"] + block["HH"] - block["LL"] - block["HL"]) / 2
    if contrast == "LxM":
        return block["HH"] - block["HL"] - block["LH"] + block["LL"]
    raise FactorialPlanError(f"unknown factorial contrast {contrast!r}")


def _bootstrap_mean(values: list[float], n_resamples: int, seed: int, label: str) -> dict:
    point = sum(values) / len(values)
    rng = random.Random(_derived_seed(seed, label))
    samples = [
        sum(values[rng.randrange(len(values))] for _ in values) / len(values)
        for _ in range(n_resamples)
    ]
    samples.sort()
    ci_low, ci_high = _percentile_interval(samples)
    return {
        "effect": point,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "n_blocks": len(values),
        "bootstrap_resamples": n_resamples,
    }


def _percentile_interval(sorted_values: list[float]) -> tuple[float, float]:
    count = len(sorted_values)
    low_index = max(int(0.025 * count), 0)
    high_index = min(int(0.975 * count), count - 1)
    return sorted_values[low_index], sorted_values[high_index]


def _derived_seed(seed: int, label: str) -> int:
    digest = hashlib.blake2b(f"{seed}:{label}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big")


def _non_treatment_snapshot(config: ExperimentConfig) -> dict[str, Any]:
    payload = dataclasses.asdict(config)
    for field in ("seed", "group_label", "l_level", "m_level", "maint_bp"):
        payload.pop(field, None)
    for spec in payload["agent_specs"]:
        for field in ("leverage_tier", "initial_bp", "goal_model_id"):
            spec.pop(field, None)
    return payload


def _first_difference(expected: Any, actual: Any, path: str = "config") -> tuple[str, Any, Any]:
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(set(expected) | set(actual)):
            if key not in expected or key not in actual:
                return f"{path}.{key}", expected.get(key), actual.get(key)
            if expected[key] != actual[key]:
                return _first_difference(expected[key], actual[key], f"{path}.{key}")
    if isinstance(expected, list) and isinstance(actual, list):
        for index, (left, right) in enumerate(zip(expected, actual, strict=False)):
            if left != right:
                return _first_difference(left, right, f"{path}[{index}]")
        if len(expected) != len(actual):
            return f"{path}.length", len(expected), len(actual)
    return path, expected, actual


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FactorialPlanError(f"cannot resolve factorial plan {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise FactorialPlanError("factorial plan root must be an object")
    return payload


def _canonical_json_digest(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _require_exact_keys(value: Any, expected: set[str], path: str) -> None:
    if not isinstance(value, Mapping):
        raise FactorialPlanError(f"{path} must be an object")
    actual = set(value)
    if actual != expected:
        raise FactorialPlanError(
            f"{path} keys must be exactly {sorted(expected)}; "
            f"missing={sorted(expected - actual)}, unknown={sorted(actual - expected)}"
        )


def _validate_cells_payload(cells: Any) -> None:
    _require_exact_keys(cells, set(CELL_IDS), "cells")
    for cell_id in CELL_IDS:
        _require_exact_keys(cells[cell_id], {"l_level", "m_level", "maint_bp"}, f"cells.{cell_id}")
        expected = {
            "l_level": "low" if cell_id[0] == "L" else "high",
            "m_level": "low" if cell_id[1] == "L" else "high",
            "maint_bp": 300 if cell_id[1] == "L" else 700,
        }
        if cells[cell_id] != expected:
            raise FactorialPlanError(f"cells.{cell_id} must be {expected}")


def _validate_tier_weights(payload: Any) -> None:
    _require_exact_keys(payload, {"low", "high"}, "leverage_tier_weights_bp")
    expected = {
        "low": {"2": 3334, "3": 3333, "5": 3333},
        "high": {"10": 3334, "20": 3333, "50": 3333},
    }
    if payload != expected:
        raise FactorialPlanError(f"leverage_tier_weights_bp must be {expected}")


def _validate_goal_parameters(payload: Any) -> None:
    _require_exact_keys(
        payload,
        {"risk_appetite_x1000", "risk_budget_threshold_v1"},
        "goal_parameters",
    )
    appetite = payload["risk_appetite_x1000"]
    expected_appetite = {
        "distribution": "int_uniform_half_open",
        "low_inclusive": 500,
        "high_exclusive": 20_000,
        "mechanism": "risk_appetite",
        "drawn_once_per_run": True,
    }
    if appetite != expected_appetite:
        raise FactorialPlanError(f"goal_parameters.risk_appetite_x1000 must be {expected_appetite}")
    threshold = payload["risk_budget_threshold_v1"]
    expected_threshold = {"theta_in": 3000, "theta_out": 1200, "k_x1000": 600}
    if threshold != expected_threshold:
        raise FactorialPlanError(
            f"goal_parameters.risk_budget_threshold_v1 must be {expected_threshold}"
        )


def _resolve_repo_relative(manifest_path: Path, relative_path: Any) -> Path:
    if not isinstance(relative_path, str) or not relative_path:
        raise FactorialPlanError("preregistration_path must be a non-empty string")
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise FactorialPlanError("preregistration_path must be repository-relative")
    for ancestor in manifest_path.parents:
        resolved = ancestor / candidate
        if resolved.is_file():
            return resolved.resolve()
    raise FactorialPlanError(f"cannot resolve repository-relative preregistration {relative_path}")


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    for ancestor in resolved.parents:
        if (ancestor / ".git").exists():
            return resolved.relative_to(ancestor).as_posix()
    return resolved.as_posix()


__all__ = [
    "CELL_IDS",
    "CONTRASTS",
    "ENDPOINT_FAMILIES",
    "FactorialPlanBinding",
    "FactorialPlanError",
    "FactorialSeedPlan",
    "MODEL_IDS",
    "analyze_flagship_results",
    "audit_deterministic_rerun",
    "endpoint_observations",
    "event_summary_sha256",
    "load_factorial_plan",
    "validate_flagship_configs",
]
