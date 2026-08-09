"""T601-T606: Experiment runner tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.experiment.protocol import ExperimentProtocol, ProtocolViolation
from market_game_sim.experiment.runner import (
    ExperimentConfig,
    RunResult,
    build_market_validation_report,
    build_study_report,
    check_paired_parity,
    check_shared_randomness_parity,
    run_multi_seed,
    run_one,
    run_paired,
)
from market_game_sim.ledger.account import Account
from market_game_sim.metrics.liquidation import LiquidationMetrics, RunClassification


def _mm_spec(aid: str = "mm-0") -> AgentSpec:
    return AgentSpec(
        agent_id=aid,
        role="inventory_market_maker",
        observe_interval_ns=100_000_000,
        latency_ns=5_000_000,
        is_market_maker=True,
        half_spread_ticks=5,
        quote_size=10_000,
        max_inventory=100_000,
        inventory_skew_k_bp=10_000,
    )


def _belief_spec(aid: str) -> AgentSpec:
    return AgentSpec(
        agent_id=aid,
        role="retail",
        observe_interval_ns=1_000_000_000,
        latency_ns=50_000_000,
        leverage_tier=10,
        aggressiveness_bp=5_000,
        max_order_qty=5_000,
    )


def test_run_one_with_protocol_records_calibration_trial(tmp_path):
    """§T603 wiring: run_one(config, protocol=...) in CALIBRATION stage
    must record the trial via the real protocol object, not just have the
    method available and unused -- verified by a subsequent
    enter_belief_experiment overlap check that only works if the trial was
    actually recorded."""
    mm = _mm_spec()
    b = replace(_belief_spec("agent-0"), leverage_tier=10)
    cfg = ExperimentConfig(
        seed=1,
        max_transactions=60,
        agent_specs=[mm, b],
        agent_signals={"agent-0": 10_000},
    )
    protocol = ExperimentProtocol(audit_log_path=tmp_path / "audit.jsonl")
    run_one(cfg, protocol=protocol)
    protocol.freeze_calibration(cfg)
    with pytest.raises(ProtocolViolation, match="10"):
        protocol.enter_belief_experiment([10, 50])


def test_run_one_with_protocol_enforces_frozen_config_in_validation_stage(tmp_path):
    """§T603 wiring: run_one must actually call protocol.check_config once
    out of CALIBRATION and propagate ProtocolViolation, not silently run a
    config that drifted from the frozen baseline."""
    mm = _mm_spec()
    b = _belief_spec("agent-0")
    frozen_cfg = ExperimentConfig(
        seed=1,
        max_transactions=60,
        agent_specs=[mm, b],
        agent_signals={"agent-0": 10_000},
        taker_bps=5,
    )
    protocol = ExperimentProtocol(audit_log_path=tmp_path / "audit.jsonl")
    protocol.freeze_calibration(frozen_cfg)

    drifted_cfg = replace(frozen_cfg, taker_bps=8)
    with pytest.raises(ProtocolViolation, match="taker_bps"):
        run_one(drifted_cfg, protocol=protocol)

    # the unmodified frozen config must still run fine post-freeze
    result = run_one(frozen_cfg, protocol=protocol)
    assert result.terminated == "COMPLETED"


def test_run_one_completes():
    mm = _mm_spec()
    b = _belief_spec("agent-0")
    cfg = ExperimentConfig(
        seed=1,
        max_transactions=100,
        agent_specs=[mm, b],
        agent_signals={"agent-0": 10_000},
    )
    result = run_one(cfg)
    assert result.terminated == "COMPLETED", f"abort: {result.abort_code}"
    assert len(result.events) > 0


def test_run_one_enqueues_and_processes_extra_events():
    """ExperimentConfig.extra_accounts/extra_events (added for bench/shock.py's
    forcing-trade mechanism): a positive test that an injected event is
    actually processed through the real kernel/matching pipeline -- not
    just accepted as a config field."""
    mm = _mm_spec()
    b = _belief_spec("agent-0")
    extra_event = {
        "event_type": "ORDER_ARRIVAL",
        "timestamp": 1,
        "agent_id": "injected",
        "order_id": "injected-0",
        "action": "SUBMIT",
        "side": "SELL",
        "order_type": "MARKET",
        "price_ticks": None,
        "quantity_units": 1,
    }
    cfg = ExperimentConfig(
        seed=1,
        max_transactions=100,
        agent_specs=[mm, b],
        agent_signals={"agent-0": 10_000},
        extra_accounts={"injected": 10**16},
        extra_events=[extra_event],
    )
    result = run_one(cfg)
    assert result.terminated == "COMPLETED", f"abort: {result.abort_code}"
    injected_records = [e for e in result.events if e.get("order_id") == "injected-0"]
    assert len(injected_records) >= 1
    assert "injected" in result.accounts  # pre-funded account was actually registered


def test_run_one_without_extra_events_behaves_as_before():
    """Negative/contrast case: omitting extra_accounts/extra_events (the
    default) must not introduce any phantom accounts or events -- confirms
    the new fields are purely additive."""
    mm = _mm_spec()
    b = _belief_spec("agent-0")
    cfg = ExperimentConfig(
        seed=1,
        max_transactions=100,
        agent_specs=[mm, b],
        agent_signals={"agent-0": 10_000},
    )
    result = run_one(cfg)
    assert result.terminated == "COMPLETED"
    assert set(result.accounts.keys()) == {"mm-0", "agent-0"}


def test_run_multi_seed_completes():
    mm = _mm_spec()
    b = _belief_spec("agent-0")
    cfg = ExperimentConfig(
        seed=1,
        max_transactions=60,
        agent_specs=[mm, b],
        agent_signals={"agent-0": 10_000},
    )
    results = run_multi_seed(cfg, [1, 2])

    assert len(results) == 2
    assert all(r.terminated == "COMPLETED" for r in results)


def test_run_one_healthy_run_is_not_technical_invalid():
    """§2.1 positive case: a real, uncorrupted run must pass both the
    conservation (TI-3) and causal-reference (TI-1) checks that run_one
    now actually computes and feeds into classify_run."""
    mm = _mm_spec()
    b = _belief_spec("agent-0")
    cfg = ExperimentConfig(
        seed=1,
        max_transactions=100,
        agent_specs=[mm, b],
        agent_signals={"agent-0": 10_000},
    )
    result = run_one(cfg)
    assert result.classification.is_technical_invalid is False
    assert result.classification.technical_invalid_code is None


def test_run_one_surfaces_conservation_violation_as_ti3(monkeypatch):
    """§2.1 regression: classify_run has always had a conservation_ok
    parameter/TI-3 branch, but run_one's call site never passed it through
    (always fell back to the True default) -- a genuinely corrupted run
    would silently be classified as valid.  Monkeypatching the conservation
    checker to report a violation and asserting it surfaces as TI-3 proves
    run_one now actually wires the real result through, not just the
    default."""
    import market_game_sim.experiment.runner as runner_mod

    monkeypatch.setattr(runner_mod, "check_c1_c2", lambda **kwargs: (False, "fake C1/C2 violation"))
    mm = _mm_spec()
    b = _belief_spec("agent-0")
    cfg = ExperimentConfig(
        seed=1,
        max_transactions=100,
        agent_specs=[mm, b],
        agent_signals={"agent-0": 10_000},
    )
    result = run_one(cfg)
    assert result.classification.is_technical_invalid is True
    assert result.classification.technical_invalid_code == "TI-3"


def test_run_one_surfaces_dangling_causal_reference_as_ti1(monkeypatch):
    """§2.1 regression: same gap as above but for reference_integrity_ok/
    TI-1 (dangling caused_by_event_id)."""
    import market_game_sim.experiment.runner as runner_mod

    monkeypatch.setattr(
        runner_mod, "check_causal_references", lambda events: "fake dangling reference"
    )
    mm = _mm_spec()
    b = _belief_spec("agent-0")
    cfg = ExperimentConfig(
        seed=1,
        max_transactions=100,
        agent_specs=[mm, b],
        agent_signals={"agent-0": 10_000},
    )
    result = run_one(cfg)
    assert result.classification.is_technical_invalid is True
    assert result.classification.technical_invalid_code == "TI-1"


def test_run_one_observe_cycle_is_dynamically_rescheduled_not_capped():
    """§2.16 regression: run_one() used to pre-schedule a hardcoded 100
    rounds of AGENT_OBSERVE per agent up front; once those were consumed
    and _flush_reschedules (structurally uncalled -- see runner.py history)
    never replenished the queue, a run configured for more transactions
    than 100 observe cycles worth would exhaust its queue and terminate
    early, well short of max_transactions.

    With max_transactions set far beyond what 100 static rounds could
    reach, the run must still process (COMMIT) the FULL number of
    transactions requested -- proving AGENT_OBSERVE keeps rescheduling
    itself dynamically rather than the queue running dry.
    """
    mm = _mm_spec()
    cfg = ExperimentConfig(
        seed=1,
        max_transactions=2000,
        agent_specs=[mm],
        agent_signals={},
    )
    result = run_one(cfg)
    assert result.terminated == "COMPLETED"
    committed_txn_seqs = {e["transaction_seq"] for e in result.events}
    assert len(committed_txn_seqs) == 2000
    assert max(committed_txn_seqs) == 2000


def test_run_one_propagates_group_label():
    """§1.7: RunResult must carry the config's group_label through, not
    silently default to "control" for a treatment run."""
    mm = _mm_spec()
    b = _belief_spec("agent-0")
    cfg = ExperimentConfig(
        seed=1,
        max_transactions=60,
        agent_specs=[mm, b],
        agent_signals={"agent-0": 10_000},
        group_label="treatment",
    )
    result = run_one(cfg)
    assert result.group_label == "treatment"


def test_run_multi_seed_copies_group_label_per_seed():
    """§1.7 regression: run_multi_seed previously rebuilt ExperimentConfig
    per seed without copying group_label, so every reconstructed run
    silently fell back to the dataclass default "control" regardless of
    what the caller passed in.  Positive case here (group_label=
    "treatment") would have failed before the fix; the default-label case
    below is the negative control proving the field isn't just hardcoded
    to always report "treatment"."""
    mm = _mm_spec()
    b = _belief_spec("agent-0")
    cfg = ExperimentConfig(
        seed=1,
        max_transactions=60,
        agent_specs=[mm, b],
        agent_signals={"agent-0": 10_000},
        group_label="treatment",
    )
    results = run_multi_seed(cfg, [1, 2, 3])
    assert all(r.group_label == "treatment" for r in results)


def test_run_multi_seed_default_group_label_stays_control():
    mm = _mm_spec()
    b = _belief_spec("agent-0")
    cfg = ExperimentConfig(
        seed=1,
        max_transactions=60,
        agent_specs=[mm, b],
        agent_signals={"agent-0": 10_000},
    )
    results = run_multi_seed(cfg, [1, 2])
    assert all(r.group_label == "control" for r in results)


def test_run_paired_results_carry_distinct_group_labels():
    mm = _mm_spec()
    b = _belief_spec("agent-0")
    control = ExperimentConfig(
        seed=1,
        max_transactions=60,
        agent_specs=[mm, b],
        agent_signals={"agent-0": 10_000},
        group_label="control",
    )
    treatment = ExperimentConfig(
        seed=1,
        max_transactions=60,
        agent_specs=[mm, b],
        agent_signals={"agent-0": 10_000},
        group_label="treatment",
    )
    c_results, t_results, _comparison = run_paired(control, treatment, [1, 2])
    assert all(r.group_label == "control" for r in c_results)
    assert all(r.group_label == "treatment" for r in t_results)


def test_check_paired_parity_passes_when_only_leverage_tier_differs():
    mm = _mm_spec()
    b_control = _belief_spec("agent-0")
    b_treatment = replace(b_control, leverage_tier=50)
    control = ExperimentConfig(seed=1, max_transactions=60, agent_specs=[mm, b_control])
    treatment = ExperimentConfig(seed=1, max_transactions=60, agent_specs=[mm, b_treatment])
    assert check_paired_parity(control, treatment) is None


def test_check_paired_parity_detects_other_agentspec_field_difference():
    """Negative case: a change to a field OTHER than the declared
    treatment_field (leverage_tier) must be caught -- 方法论 §10.5 requires
    single-dimension contrast, so accidentally also varying
    aggressiveness_bp would silently invalidate the attribution."""
    mm = _mm_spec()
    b_control = _belief_spec("agent-0")
    b_treatment = replace(b_control, aggressiveness_bp=9999)
    control = ExperimentConfig(seed=1, max_transactions=60, agent_specs=[mm, b_control])
    treatment = ExperimentConfig(seed=1, max_transactions=60, agent_specs=[mm, b_treatment])
    err = check_paired_parity(control, treatment)
    assert err is not None
    assert "aggressiveness_bp" in err


def test_check_paired_parity_detects_top_level_config_difference():
    mm = _mm_spec()
    b = _belief_spec("agent-0")
    control = ExperimentConfig(seed=1, max_transactions=60, agent_specs=[mm, b], taker_bps=5)
    treatment = ExperimentConfig(seed=1, max_transactions=60, agent_specs=[mm, b], taker_bps=8)
    err = check_paired_parity(control, treatment)
    assert err is not None
    assert "taker_bps" in err


def test_check_shared_randomness_parity_passes_for_real_paired_runs():
    mm = _mm_spec()
    b_control = _belief_spec("agent-0")
    b_treatment = replace(b_control, leverage_tier=50)
    control = ExperimentConfig(seed=1, max_transactions=60, agent_specs=[mm, b_control])
    treatment = ExperimentConfig(seed=1, max_transactions=60, agent_specs=[mm, b_treatment])
    c_results = run_multi_seed(control, [1, 2])
    t_results = run_multi_seed(treatment, [1, 2])
    assert check_shared_randomness_parity(c_results, t_results) is None


def test_check_shared_randomness_parity_detects_divergent_signal_bp():
    """Negative case: hand-built RunResults where the same (agent_id,
    decision_index) key got a different signal_bp between control and
    treatment -- must be flagged as a parity violation, proving the check
    actually inspects values rather than always passing."""

    def _run(signal_bp: int) -> RunResult:
        return RunResult(
            seed=1,
            terminated="COMPLETED",
            abort_code=None,
            events=[
                {
                    "event_type": "AGENT_DECIDE",
                    "agent_id": "a",
                    "_decision_index": 0,
                    "internal_state": {"signal_bp": signal_bp},
                }
            ],
            book_last_ticks=None,
            accounts={},
            liquidation_metrics=LiquidationMetrics(),
            classification=RunClassification(),
        )

    err = check_shared_randomness_parity([_run(100)], [_run(999)])
    assert err is not None
    assert "signal_bp" in err


def test_check_shared_randomness_parity_detects_key_set_mismatch():
    """v013 regression (high): a key present in only ONE arm must fail-closed.
    The old implementation only compared the key intersection, so a fully
    disjoint key set (completely misaligned random path) passed silently."""

    def _run(agent_id: str) -> RunResult:
        return RunResult(
            seed=1,
            terminated="COMPLETED",
            abort_code=None,
            events=[
                {
                    "event_type": "AGENT_DECIDE",
                    "agent_id": agent_id,
                    "_decision_index": 0,
                    "internal_state": {"signal_bp": 100},
                }
            ],
            book_last_ticks=None,
            accounts={},
            liquidation_metrics=LiquidationMetrics(),
            classification=RunClassification(),
        )

    # disjoint key sets: control has agent "a", treatment has agent "b"
    err = check_shared_randomness_parity([_run("a")], [_run("b")])
    assert err is not None
    assert "semantic-key sets differ" in err

    # one arm has an EXTRA key the other lacks -> must fail too
    def _run_two(agents: list[str]) -> RunResult:
        return RunResult(
            seed=1,
            terminated="COMPLETED",
            abort_code=None,
            events=[
                {
                    "event_type": "AGENT_DECIDE",
                    "agent_id": aid,
                    "_decision_index": 0,
                    "internal_state": {"signal_bp": 100},
                }
                for aid in agents
            ],
            book_last_ticks=None,
            accounts={},
            liquidation_metrics=LiquidationMetrics(),
            classification=RunClassification(),
        )

    err2 = check_shared_randomness_parity([_run_two(["a", "b"])], [_run_two(["a"])])
    assert err2 is not None
    assert "semantic-key sets differ" in err2


def test_run_paired_raises_on_parity_violation():
    mm = _mm_spec()
    b_control = _belief_spec("agent-0")
    b_treatment = replace(b_control, aggressiveness_bp=1)
    control = ExperimentConfig(
        seed=1,
        max_transactions=60,
        agent_specs=[mm, b_control],
        agent_signals={"agent-0": 10_000},
    )
    treatment = ExperimentConfig(
        seed=1,
        max_transactions=60,
        agent_specs=[mm, b_treatment],
        agent_signals={"agent-0": 10_000},
    )
    with pytest.raises(ValueError, match="parity"):
        run_paired(control, treatment, [1, 2])


def test_run_paired_raises_on_shared_randomness_divergence(monkeypatch):
    """Wiring regression: run_paired must actually call
    check_shared_randomness_parity on the real results and raise when it
    reports a mismatch -- not just have the check function exist and be
    correct in isolation.  A config-parity-valid pair essentially never
    triggers this in practice (leverage_tier doesn't feed the RNG key), so
    the dynamic-check-fires path is exercised via monkeypatch instead of a
    contrived real divergence."""
    import market_game_sim.experiment.runner as runner_mod

    monkeypatch.setattr(
        runner_mod, "check_shared_randomness_parity", lambda c, t: "fake divergence"
    )
    mm = _mm_spec()
    b_control = _belief_spec("agent-0")
    b_treatment = replace(b_control, leverage_tier=50)
    control = ExperimentConfig(seed=1, max_transactions=60, agent_specs=[mm, b_control])
    treatment = ExperimentConfig(seed=1, max_transactions=60, agent_specs=[mm, b_treatment])
    with pytest.raises(ValueError, match="shared random-shock"):
        run_paired(control, treatment, [1, 2])


def test_run_paired_produces_bootstrap_effect_and_conclusion():
    mm = _mm_spec()
    b_control = _belief_spec("agent-0")
    b_treatment = replace(b_control, leverage_tier=50)
    control = ExperimentConfig(
        seed=1,
        max_transactions=60,
        agent_specs=[mm, b_control],
        agent_signals={"agent-0": 10_000},
    )
    treatment = ExperimentConfig(
        seed=1,
        max_transactions=60,
        agent_specs=[mm, b_treatment],
        agent_signals={"agent-0": 10_000},
    )
    _c, _t, comparison = run_paired(control, treatment, [1, 2, 3], n_resamples=500)
    effect = comparison["endpoint_rate_effect"]
    assert effect.n_control == 3
    assert effect.n_treatment == 3
    assert "在参与者结构" in comparison["conditional_conclusion"]


def test_run_paired_comparison_carries_traceable_config_hashes():
    """E3 (0.1.2 退出条件): the conditional conclusion must be traceable back
    to the exact control/treatment configs via a content hash -- distinct
    configs (they differ in leverage_tier, the treatment field) must get
    distinct hashes, and re-hashing the same config object must reproduce
    the same value recorded in the comparison dict."""
    from market_game_sim.experiment.config import compute_config_hash

    mm = _mm_spec()
    b_control = _belief_spec("agent-0")
    b_treatment = replace(b_control, leverage_tier=50)
    control = ExperimentConfig(
        seed=1, max_transactions=60, agent_specs=[mm, b_control], agent_signals={"agent-0": 10_000}
    )
    treatment = ExperimentConfig(
        seed=1,
        max_transactions=60,
        agent_specs=[mm, b_treatment],
        agent_signals={"agent-0": 10_000},
    )
    _c, _t, comparison = run_paired(control, treatment, [1], n_resamples=200)
    assert comparison["control_config_hash"] == compute_config_hash(control)
    assert comparison["treatment_config_hash"] == compute_config_hash(treatment)
    # negative half: control/treatment differ (leverage_tier) -> must not
    # collide onto the same hash.
    assert comparison["control_config_hash"] != comparison["treatment_config_hash"]


def test_build_study_report():
    mm = _mm_spec()
    b = _belief_spec("agent-0")
    cfg = ExperimentConfig(
        seed=1,
        max_transactions=60,
        agent_specs=[mm, b],
        agent_signals={"agent-0": 10_000},
    )
    results = run_multi_seed(cfg, [1, 2])
    report = build_study_report(results)

    assert report["n_runs"] == 2
    assert report["n_completed"] == 2
    assert "impact" in report
    assert isinstance(report["impact"]["mean_impact_bp"], float)


def test_build_study_report_impact_reflects_real_taker_orders():
    """§2.9/T501 regression: compute_price_impact existed but was never
    called from the reporting path (grep for "impact" across metrics/ and
    experiment/ was zero before this fix).  A fully-aggressive taker agent
    guarantees at least one crossing trade -> n_taker_orders must be > 0
    and mean_impact_bp must reflect a real (non-default-zero) value."""
    mm = _mm_spec()
    aggressive = AgentSpec(
        agent_id="agent-0",
        role="retail",
        observe_interval_ns=1_000_000_000,
        latency_ns=50_000_000,
        leverage_tier=10,
        aggressiveness_bp=10_000,
        max_order_qty=5_000,
    )
    cfg = ExperimentConfig(
        seed=1,
        max_transactions=60,
        agent_specs=[mm, aggressive],
        agent_signals={"agent-0": 10_000},
    )
    results = run_multi_seed(cfg, [1, 2])
    report = build_study_report(results)
    assert report["impact"]["n_taker_orders"] > 0
    assert report["impact"]["mean_impact_bp"] != 0.0
    assert isinstance(report["endpoint"]["rate"], float)
    assert isinstance(report["endpoint"]["mean_margin_ratio_bp"], float)
    assert isinstance(report["endpoint"]["mean_leverage_bp"], float)


def test_build_study_report_endpoint_stats_reflect_real_endpoint_samples():
    """§2.6 regression: when a run's classification says
    is_economic_endpoint, the margin_ratio_bp/leverage_bp sampled AT that
    run's events must flow into endpoint.mean_margin_ratio_bp/
    mean_leverage_bp -- previously build_study_report computed
    endpoint_samples and only ever surfaced their COUNT
    (n_endpoint_samples), discarding the values themselves.  Hand-built
    RunResult with one TRADE_POSTING (deterministic, no dependency on
    emergent liquidation dynamics from a real run)."""
    account = Account(
        agent_id="A",
        wallet_units=10**11,
        position_units=100,
        entry_notional_units=100 * 10000 * 1000,
    )
    events = [
        {
            "event_type": "TRADE_SETTLE",
            "timestamp": 0,
            "transaction_seq": 1,
            "risk_mark_ticks": 10000,
            "postings": [
                {
                    "agent_id": "A",
                    # sample_agent_series replays wallet purely from summed
                    # postings deltas (starting at 0), not from the Account
                    # object -- must carry the real wallet here too.
                    "wallet_delta_units": 10**11,
                    "position_delta_units": 100,
                    "entry_notional_delta_units": 100 * 10000 * 1000,
                }
            ],
        }
    ]
    classification = RunClassification(is_economic_endpoint=True, economic_endpoint_codes=["EV-1"])
    result = RunResult(
        seed=1,
        terminated="COMPLETED",
        abort_code=None,
        events=events,
        book_last_ticks=10000,
        accounts={"A": account},
        liquidation_metrics=LiquidationMetrics(),
        classification=classification,
    )
    report = build_study_report([result])
    assert report["endpoint"]["n_endpoint_samples"] > 0
    assert report["endpoint"]["mean_margin_ratio_bp"] != 0.0


def test_build_study_report_includes_market_validation_matrix():
    """T606 (KPI-005): build_study_report must surface a per-seed market
    validation matrix, not just the endpoint/continuous/impact parts."""
    mm = _mm_spec()
    b = _belief_spec("agent-0")
    cfg = ExperimentConfig(
        seed=1,
        max_transactions=60,
        agent_specs=[mm, b],
        agent_signals={"agent-0": 10_000},
    )
    results = run_multi_seed(cfg, [1, 2])
    report = build_study_report(results)
    assert "market_validation" in report
    per_seed = report["market_validation"]["per_seed"]
    assert set(per_seed) == {1, 2}
    for matrix in per_seed.values():
        assert set(matrix["items"]) == {
            "fat_tails",
            "return_autocorrelation",
            "volatility_clustering",
            "price_impact_nonlinearity",
            "spread_depth_regime",
            "liquidation_chain",
        }
        # a 60-transaction toy run is far below the >=2000-sample-point
        # protocol floor, so every item must honestly declare itself
        # inapplicable rather than fabricate a verdict on a starved sample.
        for item in matrix["items"].values():
            assert item["verdict"] == "NOT_APPLICABLE"


def test_build_study_report_includes_zero_sum_declaration():
    """KPI-011 (PRD §13.4): build_study_report must surface a per-seed
    zero-sum declaration whose identity actually holds (residual 0) on a
    real run, not just endpoint/continuous/impact/market_validation."""
    mm = _mm_spec()
    b = _belief_spec("agent-0")
    cfg = ExperimentConfig(
        seed=1,
        max_transactions=60,
        agent_specs=[mm, b],
        agent_signals={"agent-0": 10_000},
    )
    results = run_multi_seed(cfg, [1, 2])
    report = build_study_report(results)
    assert "zero_sum" in report
    per_seed = report["zero_sum"]
    assert set(per_seed) == {1, 2}
    for decl in per_seed.values():
        assert decl["residual_units"] == 0
        assert "不是研究发现" in decl["declaration_text"]
        assert set(decl["per_agent_pnl_units"]) == {"mm-0", "agent-0"}


def test_build_study_report_zero_sum_skips_technical_invalid_runs():
    """Negative/contrast case: a technical-invalid run's account states
    can't support a meaningful declaration (its event log already failed
    integrity/conservation) -- must be excluded, not silently included with
    a bogus residual."""
    account = Account(agent_id="A", wallet_units=10**11)
    ti_result = RunResult(
        seed=99,
        terminated="ABORTED",
        abort_code="SOME_ABORT",
        events=[],
        book_last_ticks=None,
        accounts={"A": account},
        liquidation_metrics=LiquidationMetrics(),
        classification=RunClassification(is_technical_invalid=True, technical_invalid_code="TI-4"),
    )
    report = build_study_report([ti_result])
    assert report["zero_sum"] == {}


def test_build_market_validation_report_skips_technical_invalid_runs():
    """A run whose classification is_technical_invalid must not contribute
    a matrix entry: its event log already failed integrity/conservation
    checks, so any market-quality statistic computed on it would be
    meaningless (协议 §1's scope presumes a valid log)."""
    account = Account(agent_id="A", wallet_units=10**11)
    ti_result = RunResult(
        seed=99,
        terminated="ABORTED",
        abort_code="SOME_ABORT",
        events=[],
        book_last_ticks=None,
        accounts={"A": account},
        liquidation_metrics=LiquidationMetrics(),
        classification=RunClassification(is_technical_invalid=True, technical_invalid_code="TI-4"),
    )
    report = build_market_validation_report([ti_result])
    assert report["per_seed"] == {}


def test_verify_bridge_residuals_raises_on_nonzero_under_opt(monkeypatch):
    """v013 regression (high): KPI-009 gate must raise BridgeResidualError on
    a non-zero residual even under `python -O` -- the old `assert` is stripped
    by -O and would silently accept the corrupted run."""
    from market_game_sim.experiment import runner as runner_mod
    from market_game_sim.experiment.runner import BridgeResidualError

    # a TRADE_SETTLE whose price is inconsistent with the valuation marks
    # produces a non-zero bridge residual
    event = {
        "event_type": "TRADE_SETTLE",
        "trade_id": "t1",
        "price_ticks": 19980,
        "valuation_mark_before_half_ticks": 19980,
        "valuation_mark_after_half_ticks": 19980,
        "postings": [
            {
                "posting_type": "TRADE_POSTING",
                "agent_id": "a1",
                "wallet_delta_units": -999000,
                "position_delta_units": 1000,
                "entry_notional_delta_units": 9990000000,
                "fee_delta_units": 999000,
                "position_after_units": 1000,
            }
        ],
    }
    with pytest.raises(BridgeResidualError, match="bridge residual"):
        runner_mod._verify_bridge_residuals([event], mult=1000)

    # sanity: a consistent trade passes
    clean = dict(event)
    clean["price_ticks"] = 9990
    runner_mod._verify_bridge_residuals([clean], mult=1000)
