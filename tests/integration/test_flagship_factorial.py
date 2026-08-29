"""T213: real RunResult -> paired 2x2 -> three independent BH families."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.experiment.config import ExperimentConfig
from market_game_sim.experiment.factorial import (
    CELL_IDS,
    MODEL_IDS,
    FactorialPlanBinding,
    FactorialPlanError,
    FactorialSeedPlan,
    analyze_flagship_results,
    audit_deterministic_rerun,
    endpoint_observations,
    load_factorial_plan,
    validate_flagship_configs,
)
from market_game_sim.experiment.runner import RunResult
from market_game_sim.ledger.account import initial_margin_bp_for_tier
from market_game_sim.metrics.liquidation import LiquidationMetrics, RunClassification
from market_game_sim.rng.distributions import discrete_choice, uniform_range

ROOT = Path(__file__).resolve().parents[2]
REAL_PLAN = ROOT / "docs" / "experiments" / "0.1.5-factorial-plan.json"


def _binding(
    *, planned: tuple[int, ...] = (1, 2), reserve: tuple[int, ...] = (), minimum: int = 2
) -> FactorialPlanBinding:
    return FactorialPlanBinding(
        preregistration_id="test-prereg",
        preregistration_path=Path("docs/experiments/test-prereg.md"),
        preregistration_sha256="a" * 64,
        manifest_path=Path("docs/experiments/test-plan.json"),
        manifest_sha256="b" * 64,
        seed_plan=FactorialSeedPlan(planned, reserve, minimum),
        bootstrap_resamples=200,
        bootstrap_seed=913201,
        sign_flip_resamples=500,
        sign_flip_seed=913202,
        bh_q=0.05,
    )


def _run(
    seed: int,
    *,
    crash: bool = False,
    surge: bool = False,
    liquidity: bool = False,
    technical_code: str | None = None,
    group_label: str = "LL",
) -> RunResult:
    events: list[dict] = [{"event_type": "RUN_HEADER", "timestamp": 0}]
    codes: list[str] = []
    if crash:
        codes.append("EV-1")
        events.append({"event_type": "TRADE_SETTLE", "timestamp": 10, "price_ticks": 1})
    if surge:
        codes.append("EV-2")
        events.append({"event_type": "TRADE_SETTLE", "timestamp": 20, "price_ticks": 100_001})
    if liquidity:
        codes.append("EV-3")
    events.append({"event_type": "RUN_TRAILER", "timestamp": 100})
    classification = RunClassification(
        is_technical_invalid=technical_code is not None,
        technical_invalid_code=technical_code,
        is_economic_endpoint=bool(codes),
        economic_endpoint_codes=codes,
    )
    return RunResult(
        seed=seed,
        terminated="COMPLETED",
        abort_code=None,
        events=events,
        book_last_ticks=10_000,
        accounts={},
        liquidation_metrics=LiquidationMetrics(),
        classification=classification,
        group_label=group_label,
    )


def _results(
    seeds: tuple[int, ...], *, invalid_seed: int | None = None
) -> dict[str, dict[str, list[RunResult]]]:
    output: dict[str, dict[str, list[RunResult]]] = {}
    for model_id in MODEL_IDS:
        output[model_id] = {}
        for cell_id in CELL_IDS:
            output[model_id][cell_id] = [
                _run(
                    seed,
                    crash=cell_id in {"HL", "HH"},
                    liquidity=cell_id in {"LH", "HH"},
                    technical_code=(
                        "TI-3"
                        if seed == invalid_seed and model_id == MODEL_IDS[0] and cell_id == "LL"
                        else None
                    ),
                    group_label=cell_id,
                )
                for seed in seeds
            ]
    return output


def _configs(binding: FactorialPlanBinding) -> dict[str, dict[str, ExperimentConfig]]:
    seed_plan = {"n_seeds": len(binding.seed_plan.pool), "seeds": list(binding.seed_plan.pool)}
    configs: dict[str, dict[str, ExperimentConfig]] = {}
    for model_id in MODEL_IDS:
        configs[model_id] = {}
        for cell_id in CELL_IDS:
            is_low_l = cell_id[0] == "L"
            is_low_m = cell_id[1] == "L"
            weights = {2: 3334, 3: 3333, 5: 3333} if is_low_l else {10: 3334, 20: 3333, 50: 3333}
            tier, _ = discrete_choice(weights, 1, "belief-0", "bench_leverage_tier", 0, 0)
            appetite, _ = uniform_range(
                Decimal(500), Decimal(20_000), 1, "belief-0", "risk_appetite", 0, 0
            )
            belief = AgentSpec(
                agent_id="belief-0",
                role="belief_trader",
                observe_interval_ns=10,
                latency_ns=1,
                leverage_tier=tier,
                initial_bp=initial_margin_bp_for_tier(tier),
                goal_model_id=model_id,
                risk_appetite_x1000=int(appetite),
            )
            configs[model_id][cell_id] = ExperimentConfig(
                seed=1,
                max_transactions=100,
                maint_bp=300 if is_low_m else 700,
                agent_specs=[belief],
                run_family="SPONTANEOUS",
                seed_plan=seed_plan,
                l_level="low" if is_low_l else "high",
                m_level="low" if is_low_m else "high",
                group_label=cell_id,
            )
    return configs


def test_real_machine_plan_resolves_and_binds_frozen_markdown():
    binding = load_factorial_plan(REAL_PLAN)
    assert len(binding.seed_plan.planned_seeds) == 128
    assert len(binding.seed_plan.reserve_seeds) == 16
    assert binding.seed_plan.minimum_valid_blocks == 128
    assert binding.report_reference()["preregistration_path"] == (
        "docs/experiments/0.1.5-preregistration.md"
    )


def test_machine_plan_rejects_preregistration_digest_drift(tmp_path):
    experiment_dir = tmp_path / "docs" / "experiments"
    experiment_dir.mkdir(parents=True)
    prereg = experiment_dir / "0.1.5-preregistration.md"
    prereg.write_text("changed after freeze", encoding="utf-8")
    payload = json.loads(REAL_PLAN.read_text(encoding="utf-8"))
    plan = experiment_dir / "plan.json"
    plan.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(FactorialPlanError, match="SHA-256 drifted"):
        load_factorial_plan(plan)


def test_preregistration_digest_is_stable_across_line_endings(tmp_path):
    source = ROOT / "docs" / "experiments" / "0.1.5-preregistration.md"
    experiment_dir = tmp_path / "docs" / "experiments"
    experiment_dir.mkdir(parents=True)
    prereg = experiment_dir / "0.1.5-preregistration.md"
    canonical = source.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    prereg.write_bytes(canonical.replace("\n", "\r\n").encode("utf-8"))
    payload = json.loads(REAL_PLAN.read_text(encoding="utf-8"))
    plan = experiment_dir / "plan.json"
    plan.write_text(json.dumps(payload), encoding="utf-8")
    assert load_factorial_plan(plan).preregistration_sha256 == payload["preregistration_sha256"]


def test_machine_plan_rejects_seed_or_analysis_drift(tmp_path):
    source = ROOT / "docs" / "experiments" / "0.1.5-preregistration.md"
    experiment_dir = tmp_path / "docs" / "experiments"
    experiment_dir.mkdir(parents=True)
    (experiment_dir / "0.1.5-preregistration.md").write_bytes(source.read_bytes())
    base = json.loads(REAL_PLAN.read_text(encoding="utf-8"))

    seed_drift = json.loads(json.dumps(base))
    seed_drift["seed_plan"]["planned_start"] = 29_999
    seed_plan = experiment_dir / "seed-drift.json"
    seed_plan.write_text(json.dumps(seed_drift), encoding="utf-8")
    with pytest.raises(FactorialPlanError, match="seed_plan drifted"):
        load_factorial_plan(seed_plan)

    analysis_drift = json.loads(json.dumps(base))
    analysis_drift["analysis"]["bh_q"] = 0.1
    analysis_plan = experiment_dir / "analysis-drift.json"
    analysis_plan.write_text(json.dumps(analysis_drift), encoding="utf-8")
    with pytest.raises(FactorialPlanError, match="analysis.bh_q drifted"):
        load_factorial_plan(analysis_plan)


def test_validate_flagship_configs_accepts_only_l_m_and_model_differences():
    binding = _binding()
    configs = _configs(binding)
    hashes = validate_flagship_configs(configs, binding)
    assert set(hashes) == set(MODEL_IDS)
    assert all(set(model_hashes) == set(CELL_IDS) for model_hashes in hashes.values())

    bad = _configs(binding)
    original = bad[MODEL_IDS[0]]["HH"].agent_specs[0]
    bad[MODEL_IDS[0]]["HH"].agent_specs[0] = dataclasses.replace(original, max_order_qty=9_999)
    with pytest.raises(FactorialPlanError, match="four-cell parity"):
        validate_flagship_configs(bad, binding)

    wrong_preference_draw = _configs(binding)
    original = wrong_preference_draw[MODEL_IDS[0]]["HH"].agent_specs[0]
    wrong_preference_draw[MODEL_IDS[0]]["HH"].agent_specs[0] = dataclasses.replace(
        original, risk_appetite_x1000=original.risk_appetite_x1000 + 1
    )
    with pytest.raises(FactorialPlanError, match="frozen semantic draw"):
        validate_flagship_configs(wrong_preference_draw, binding)

    mismatched_seed = _configs(binding)
    mismatched_seed[MODEL_IDS[1]]["HH"].seed = 2
    with pytest.raises(FactorialPlanError, match="paired block seed"):
        validate_flagship_configs(mismatched_seed, binding)


def test_endpoint_projection_preserves_direction_and_overlap():
    result = _run(1, crash=True, surge=True, liquidity=True)
    observed = endpoint_observations(result)
    assert observed["crash"].occurrence == 1.0
    assert observed["surge"].occurrence == 1.0
    assert observed["liquidity_drought"].occurrence == 1.0
    assert observed["crash"].severity > 0
    assert observed["surge"].severity > 0
    assert observed["liquidity_drought"].severity == 0.8


def test_analysis_builds_three_separate_twelve_test_bh_families():
    report = analyze_flagship_results(
        _results((1, 2)),
        _binding(),
        bootstrap_resamples=200,
        sign_flip_resamples=500,
    )
    assert report["seed_plan"]["evidence_sufficient"] is True
    assert set(report["endpoint_families"]) == {
        "crash",
        "surge",
        "liquidity_drought",
    }
    for family in report["endpoint_families"].values():
        assert family["bh_family_size"] == 12
    crash_linear = report["endpoint_families"]["crash"]["models"][MODEL_IDS[0]]
    assert crash_linear["occurrence"]["L"]["effect"] == 1.0
    assert crash_linear["occurrence"]["M"]["effect"] == 0.0
    liquidity_linear = report["endpoint_families"]["liquidity_drought"]["models"][MODEL_IDS[0]]
    assert liquidity_linear["occurrence"]["M"]["effect"] == 1.0
    assert "bh_adjusted_p_value" in crash_linear["severity"]["LxM"]
    assert set(report["direction_asymmetry"][MODEL_IDS[0]]) == set(CELL_IDS)


def test_any_invalid_run_excludes_the_whole_eight_run_seed_block():
    binding = _binding(planned=(1, 2), reserve=(3,), minimum=2)
    report = analyze_flagship_results(
        _results((1, 2, 3), invalid_seed=2),
        binding,
        bootstrap_resamples=50,
        sign_flip_resamples=100,
    )
    assert report["seed_plan"]["valid_seeds"] == [1, 3]
    assert report["seed_plan"]["excluded_seed_blocks"] == {2: ["TI-3"]}
    assert report["seed_plan"]["evidence_sufficient"] is True


def test_all_invalid_blocks_report_each_family_as_evidence_insufficient():
    binding = _binding(planned=(1,), minimum=1)
    report = analyze_flagship_results(
        _results((1,), invalid_seed=1),
        binding,
        bootstrap_resamples=10,
        sign_flip_resamples=10,
    )
    assert report["seed_plan"]["evidence_sufficient"] is False
    assert set(report["endpoint_families"]) == {
        "crash",
        "surge",
        "liquidity_drought",
    }
    assert all(
        family["inference_eligible"] is False for family in report["endpoint_families"].values()
    )


def test_seed_order_mismatch_fails_before_statistics():
    results = _results((1, 2))
    results[MODEL_IDS[1]]["HH"].reverse()
    with pytest.raises(FactorialPlanError, match="seed order differs"):
        analyze_flagship_results(
            results, _binding(), bootstrap_resamples=10, sign_flip_resamples=10
        )


def test_ti2_audit_compares_same_seed_canonical_event_summaries():
    primary = _run(1, crash=True)
    identical = _run(1, crash=True)
    changed = _run(1, surge=True)
    assert audit_deterministic_rerun(primary, identical) is None
    assert audit_deterministic_rerun(primary, changed) == "TI-2"
    with pytest.raises(FactorialPlanError, match="seed mismatch"):
        audit_deterministic_rerun(primary, _run(2, crash=True))


def test_machine_plan_digest_is_canonical_json_content():
    binding = load_factorial_plan(REAL_PLAN)
    payload = json.loads(REAL_PLAN.read_text(encoding="utf-8"))
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    assert binding.manifest_sha256 == hashlib.sha256(canonical).hexdigest()
