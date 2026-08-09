"""T601-T606: Experiment runner — multi-seed experiment runner.

Bootstraps the kernel, schedules observations, runs, and collects metrics
and classification for a configurable number of seeds.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

from market_game_sim.agent.handler import handle_agent_decide, handle_agent_observe
from market_game_sim.agent.mapping import get_mapping
from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.agent.strategy import target_position
from market_game_sim.book.matching import match_order
from market_game_sim.book.orderbook import Book
from market_game_sim.eventlog.bootstrap import (
    build_account_payload_from_accounts,
    build_book_payload,
)
from market_game_sim.experiment.config import ExperimentConfig, compute_config_hash
from market_game_sim.experiment.protocol import ExperimentProtocol, ProtocolStage
from market_game_sim.experiment.stats import bootstrap_proportion_diff, build_conditional_conclusion
from market_game_sim.kernel.runner import EventKernel
from market_game_sim.ledger.account import Account
from market_game_sim.ledger.conservation import check_c1_c2
from market_game_sim.metrics.bridge import bridge_trade
from market_game_sim.metrics.liquidation import (
    LiquidationMetrics,
    RunClassification,
    classify_run,
    compute_liquidation_metrics,
)
from market_game_sim.metrics.report import build_report, build_zero_sum_declaration
from market_game_sim.metrics.sampling import (
    compute_price_impact,
    sample_agent_series,
    sample_market_series,
)
from market_game_sim.metrics.validation import build_market_validation_matrix
from market_game_sim.verify import check_causal_references


def check_paired_parity(
    control: ExperimentConfig,
    treatment: ExperimentConfig,
    treatment_field: str = "leverage_tier",
) -> str | None:
    """T602 (方法论 §10.5): verify control/treatment differ ONLY in the
    pre-registered single-dimension ``treatment_field`` on each agent
    (default ``leverage_tier``).  All other ``ExperimentConfig`` fields
    (except ``seed``/``group_label``, which are expected to differ) and
    all other ``AgentSpec`` fields must be byte-identical.  Returns the
    first mismatch description found, or ``None`` if parity holds.
    """
    ignore_top = {"seed", "group_label", "agent_specs"}
    for f in dataclasses.fields(ExperimentConfig):
        if f.name in ignore_top:
            continue
        cv, tv = getattr(control, f.name), getattr(treatment, f.name)
        if cv != tv:
            return f"ExperimentConfig.{f.name} differs: control={cv!r} treatment={tv!r}"

    c_specs = {s.agent_id: s for s in control.agent_specs}
    t_specs = {s.agent_id: s for s in treatment.agent_specs}
    if c_specs.keys() != t_specs.keys():
        return (
            f"agent_specs agent_id sets differ: control={sorted(c_specs)} "
            f"treatment={sorted(t_specs)}"
        )
    for aid, cs in c_specs.items():
        ts = t_specs[aid]
        for f in dataclasses.fields(AgentSpec):
            if f.name == treatment_field:
                continue
            cv, tv = getattr(cs, f.name), getattr(ts, f.name)
            if cv != tv:
                return f"AgentSpec[{aid}].{f.name} differs: control={cv!r} treatment={tv!r}"
    return None


def check_shared_randomness_parity(
    c_results: list[RunResult], t_results: list[RunResult]
) -> str | None:
    """T602 dynamic half: empirically verify the common semantic-key
    random draws that do NOT depend on the treatment field (belief
    ``signal_bp``, keyed on master_seed/agent_id/decision_index -- see
    agent/handler.py::_compute_belief_signal) are bit-identical between
    paired control/treatment runs sharing a seed.  Compares
    AGENT_DECIDE.internal_state.signal_bp (§2.13), so it only covers
    non-static-override belief agents; market makers and static
    ``agent_signals`` overrides have no random draw to compare.
    """
    for c_run, t_run in zip(c_results, t_results, strict=True):
        if c_run.seed != t_run.seed:
            return f"paired seed mismatch: control={c_run.seed} treatment={t_run.seed}"
        c_signals = _signal_bp_by_agent_decision(c_run.events)
        t_signals = _signal_bp_by_agent_decision(t_run.events)
        for key in c_signals.keys() & t_signals.keys():
            if c_signals[key] != t_signals[key]:
                return (
                    f"seed={c_run.seed} agent/decision={key}: signal_bp differs "
                    f"control={c_signals[key]} treatment={t_signals[key]}"
                )
    return None


def _signal_bp_by_agent_decision(events: list[dict]) -> dict[tuple[str, int], int]:
    out: dict[tuple[str, int], int] = {}
    for e in events:
        if e.get("event_type") != "AGENT_DECIDE":
            continue
        signal_bp = e.get("internal_state", {}).get("signal_bp")
        if signal_bp is None:
            continue
        out[(e.get("agent_id"), e.get("_decision_index", -1))] = signal_bp
    return out


def _describe_structure(config: ExperimentConfig) -> str:
    role_counts: dict[str, int] = {}
    for spec in config.agent_specs:
        role_counts[spec.role] = role_counts.get(spec.role, 0) + 1
    parts = [f"{count}x{role}" for role, count in sorted(role_counts.items())]
    return ", ".join(parts) if parts else "(no agents)"


def run_paired(
    control: ExperimentConfig,
    treatment: ExperimentConfig,
    seeds: list[int],
    treatment_field: str = "leverage_tier",
    structure_desc: str = "",
    param_range_desc: str = "",
    n_resamples: int = 10_000,
    bootstrap_seed: int = 0,
) -> tuple[list[RunResult], list[RunResult], dict]:
    """Run control and treatment groups with the same seeds (方法论 §10.5
    single-dimension paired control).

    Raises ``ValueError`` if control/treatment differ in more than
    ``treatment_field`` (T602 static check, before running anything) or if
    the empirically observed common random draws diverge between paired
    runs (T602 dynamic check, after running) -- either means the pair is
    not a valid single-dimension contrast, and per 方法论 §10.5 "未经
    单维度对照的归因不得写入结论", it must not be allowed to silently
    produce a comparison report.

    Returns ``(control_results, treatment_results, comparison_report)``;
    the report includes a bootstrap effect-size/CI on the economic-endpoint
    rate (T604, the primary outcome metric) and a 方法论 §10.2-formatted
    conditional conclusion (T605).  Multiple-comparison correction
    (``experiment.stats.holm_bonferroni``) is not applied here because
    only one primary metric is compared; it is available for callers that
    add secondary metrics.
    """
    parity_err = check_paired_parity(control, treatment, treatment_field)
    if parity_err:
        raise ValueError(f"run_paired: control/treatment parity violated: {parity_err}")

    c_results = run_multi_seed(control, seeds)
    t_results = run_multi_seed(treatment, seeds)

    randomness_err = check_shared_randomness_parity(c_results, t_results)
    if randomness_err:
        raise ValueError(f"run_paired: shared random-shock parity violated: {randomness_err}")

    control_outcomes = [r.classification.is_economic_endpoint for r in c_results]
    treatment_outcomes = [r.classification.is_economic_endpoint for r in t_results]
    effect = bootstrap_proportion_diff(
        control_outcomes, treatment_outcomes, n_resamples=n_resamples, seed=bootstrap_seed
    )
    conclusion = build_conditional_conclusion(
        effect,
        structure_desc=structure_desc or _describe_structure(control),
        param_range_desc=param_range_desc or f"{treatment_field} treatment vs control",
    )
    comparison = {
        "n_seeds": len(seeds),
        "treatment_field": treatment_field,
        # E3 (0.1.2 退出条件): traces this conditional_conclusion back to the
        # exact ExperimentConfig that produced it -- without this, "预注册
        # 实验可从配置哈希追溯到条件性结论" has no machine-checkable link.
        "control_config_hash": compute_config_hash(control),
        "treatment_config_hash": compute_config_hash(treatment),
        "control": {
            "n_completed": sum(1 for r in c_results if r.terminated == "COMPLETED"),
            "n_endpoint": sum(control_outcomes),
        },
        "treatment": {
            "n_completed": sum(1 for r in t_results if r.terminated == "COMPLETED"),
            "n_endpoint": sum(treatment_outcomes),
        },
        "endpoint_rate_effect": effect,
        "conditional_conclusion": conclusion,
    }
    return c_results, t_results, comparison


@dataclass
class RunResult:
    seed: int
    terminated: str
    abort_code: str | None
    events: list[dict]
    book_last_ticks: int | None
    accounts: dict[str, Account]
    liquidation_metrics: LiquidationMetrics
    classification: RunClassification
    group_label: str = "control"
    book_operation_count: int = 0
    initial_baseline: dict[str, int] = field(default_factory=dict)
    exchange_fee_units: int = 0
    exchange_risk_pnl_units: int = 0


def _dispatch_agents(event: dict, world: dict, kernel: EventKernel) -> list[dict]:
    et = event.get("event_type", "")
    if et == "ORDER_ARRIVAL":
        return match_order(event, world, kernel)
    if et == "AGENT_OBSERVE":
        records = handle_agent_observe(event, world, kernel)
        _reschedule_next_observe(event, world, kernel)
        return records
    if et == "AGENT_DECIDE":
        return handle_agent_decide(
            event,
            world,
            kernel,
            world.get("agent_specs", {}),
            target_fn=world.get("behavior_mapping", target_position),
        )
    return []


def _reschedule_next_observe(event: dict, world: dict, kernel: EventKernel) -> None:
    """§2.16: keep the agent's observe cycle self-sustaining.

    Enqueues this agent's next AGENT_OBSERVE, ``observe_interval_ns`` after
    this one.  AGENT_OBSERVE -> AGENT_OBSERVE is priority class 3 -> 3 (not
    a regression -- kernel/scheduling.py's CLASS_REGRESSION_WHITELIST only
    needs to cover jumps to a *lower* class), so this needs no kernel/
    event-schema.md contract change, unlike rescheduling from AGENT_DECIDE
    (class 4 -> 3, which IS a regression and is not whitelisted -- that is
    why the previous pending_reschedules/_flush_reschedules design, which
    tried to enqueue from within the AGENT_DECIDE transaction, could never
    actually run without hitting KernelAbort(CLASS_REGRESSION_NOT_
    WHITELISTED); its ``except Exception: break`` silently swallowed that).

    Deliberately local to _dispatch_agents (the real-experiment dispatch
    path) rather than agent/handler.py::handle_agent_observe itself, so
    tests that drive handle_agent_observe directly with their own bounded,
    hand-enqueued event lists (e.g. tests/integration/test_cold_start.py)
    keep their existing finite-round behavior unchanged.
    """
    agent_id = event.get("agent_id")
    spec = world.get("agent_specs", {}).get(agent_id)
    if spec is None:
        return
    next_ts = event["timestamp"] + spec.observe_interval_ns
    kernel.enqueue(
        {
            "event_type": "AGENT_OBSERVE",
            "timestamp": next_ts,
            "agent_id": agent_id,
            "observed_at": next_ts,
            "market_data_event_id": "e1_0",
            "information_set": {},
        }
    )


def run_one(config: ExperimentConfig, protocol: ExperimentProtocol | None = None) -> RunResult:
    """Run a single experiment seed.

    ``protocol`` (T603, 方法论 §10.1/§10.3): when given, wires the
    three-zone protocol guard in automatically -- during
    ``ProtocolStage.CALIBRATION`` this records the trial (so a later
    ``enter_belief_experiment`` can check for overlap); in
    ``FROZEN_VALIDATION``/``BELIEF_EXPERIMENT`` this checks ``config``
    against the frozen snapshot / pre-registered treatment range before
    running anything, raising ``ProtocolViolation`` (with an audit-log
    entry) rather than silently producing a result that would violate
    单维度对照/不得数据窥探.
    """
    if protocol is not None:
        if protocol.stage is ProtocolStage.CALIBRATION:
            protocol.record_calibration_trial(config)
        else:
            protocol.check_config(config)

    accounts: dict[str, Account] = {}
    for spec in config.agent_specs:
        accounts[spec.agent_id] = Account(agent_id=spec.agent_id, wallet_units=10**14)
    for agent_id, wallet_units in config.extra_accounts.items():
        accounts[agent_id] = Account(agent_id=agent_id, wallet_units=wallet_units)
    for agent_id, state in config.extra_positions.items():
        accounts[agent_id] = Account(
            agent_id=agent_id,
            wallet_units=state.get("wallet_units", 0),
            position_units=state.get("position_units", 0),
            entry_notional_units=state.get("entry_notional_units", 0),
        )
    initial_wallet_sum = sum(a.wallet_units for a in accounts.values())
    # KPI-011 (metrics/report.py::build_zero_sum_declaration): baseline is
    # wallet-minus-entry at t=0, not just wallet -- extra_positions accounts
    # start with a nonzero entry_notional (already-open position), and using
    # wallet alone there would miscount their starting notional exposure as
    # a fabricated loss.
    initial_baseline = {aid: a.wallet_units - a.entry_notional_units for aid, a in accounts.items()}

    kernel = EventKernel(run_id=f"exp-s{config.seed}")
    kernel.bootstrap(
        build_account_payload_from_accounts(accounts, mult=config.mult),
        build_book_payload(last_ticks=None),
    )

    world: dict = {
        "book": Book(initial_price_ticks=config.initial_price_ticks),
        "accounts": accounts,
        "exchange_fee_units": 0,
        "exchange_risk_pnl_units": 0,
        "mult": config.mult,
        "maker_bps": config.maker_bps,
        "taker_bps": config.taker_bps,
        "initial_price_ticks": config.initial_price_ticks,
        "maint_bp": config.maint_bp,
        "target_bp": config.target_bp,
        "liquidation_latency_ns": config.liquidation_latency_ns,
        "agent_specs": {s.agent_id: s for s in config.agent_specs},
        "agent_signals": config.agent_signals,
        "agent_decision_index": {},
        "experiment_seed": config.seed,
        "trade_history": {},
        "agent_initial_bp": {
            s.agent_id: _compute_initial_bp(s.leverage_tier) for s in config.agent_specs
        },
        # 0.1.3 E1/E3 treatment knobs: threaded from the config so a robustness
        # run varies model family / behavior mapping / ablated factor.
        "model_family": config.model_family,
        "behavior_mapping": get_mapping(config.behavior_mapping).target_position,
        "disabled_factor": config.disabled_factor,
    }

    for spec in config.agent_specs:
        # Only the first observation is pre-scheduled; each subsequent one
        # is scheduled dynamically by _reschedule_next_observe as the run
        # progresses (§2.16), bounded naturally by max_transactions rather
        # than a hardcoded round count / logical-time cap.
        kernel.enqueue(
            {
                "event_type": "AGENT_OBSERVE",
                "timestamp": 0,
                "agent_id": spec.agent_id,
                "observed_at": 0,
                "market_data_event_id": "e1_0",
                "information_set": {},
            }
        )

    for event in config.extra_events:
        kernel.enqueue(event)

    kernel.run(_dispatch_agents, world, max_transactions=config.max_transactions)

    events = kernel.committed_records
    last_ticks = world["book"].last_ticks
    liq_metrics = compute_liquidation_metrics(events)
    _verify_bridge_residuals(events, mult=config.mult)
    run_total_ns = _max_event_timestamp(events)
    idle_ns = _compute_max_idle(events)

    conservation_ok, _conservation_detail = check_c1_c2(
        accounts=accounts,
        exchange_fee_units=world["exchange_fee_units"],
        exchange_risk_pnl_units=world["exchange_risk_pnl_units"],
        initial_wallet_sum=initial_wallet_sum,
    )
    reference_integrity_ok = check_causal_references(events) is None

    classification = classify_run(
        events=events,
        last_ticks=last_ticks,
        initial_price=config.initial_price_ticks,
        total_idle_ns=idle_ns,
        run_total_ns=run_total_ns,
        has_aborted=kernel.terminated == "ABORTED",
        chained_liquidation_drained_book=_book_drained_by_liq(events, world["book"]),
        reference_integrity_ok=reference_integrity_ok,
        conservation_ok=conservation_ok,
        # hash_consistent/log_truncated stay at their defaults (True/False):
        # run_one operates on kernel.committed_records in-memory and never
        # serializes to a log file, so there is no persisted log to hash or
        # truncate -- those two checks only apply to verify_log() on an
        # actual jsonl artifact.
    )

    return RunResult(
        seed=config.seed,
        terminated=kernel.terminated or "UNKNOWN",
        abort_code=kernel.abort_code,
        events=events,
        book_last_ticks=last_ticks,
        accounts=accounts,
        liquidation_metrics=liq_metrics,
        classification=classification,
        group_label=config.group_label,
        book_operation_count=world["book"].operation_count,
        initial_baseline=initial_baseline,
        exchange_fee_units=world["exchange_fee_units"],
        exchange_risk_pnl_units=world["exchange_risk_pnl_units"],
    )


def run_multi_seed(
    base_config: ExperimentConfig,
    seeds: list[int],
    protocol: ExperimentProtocol | None = None,
) -> list[RunResult]:
    """Run the same config across multiple seeds."""
    results: list[RunResult] = []
    for seed in seeds:
        cfg = ExperimentConfig(
            seed=seed,
            max_transactions=base_config.max_transactions,
            initial_price_ticks=base_config.initial_price_ticks,
            mult=base_config.mult,
            maker_bps=base_config.maker_bps,
            taker_bps=base_config.taker_bps,
            maint_bp=base_config.maint_bp,
            target_bp=base_config.target_bp,
            liquidation_latency_ns=base_config.liquidation_latency_ns,
            agent_specs=list(base_config.agent_specs),
            agent_signals=dict(base_config.agent_signals),
            group_label=base_config.group_label,
            extra_accounts=dict(base_config.extra_accounts),
            extra_events=list(base_config.extra_events),
            extra_positions={k: dict(v) for k, v in base_config.extra_positions.items()},
            model_family=base_config.model_family,
            behavior_mapping=base_config.behavior_mapping,
            disabled_factor=base_config.disabled_factor,
        )
        results.append(run_one(cfg, protocol=protocol))
    return results


def build_market_validation_report(
    results: list[RunResult], sample_interval_ns: int = 1_000_000_000
) -> dict:
    """T606 (KPI-005): per-run market validation matrix
    (docs/experiments/0.1.2-market-validation-protocol.md).

    Computed **per run**, not pooled across seeds -- concatenating
    independent runs' price series would fabricate autocorrelation at the
    run boundaries and break the equal-interval sampling assumption
    (指标字典 §2) the statistical tests rely on. Technical-invalid runs are
    skipped: their event logs failed integrity/conservation checks and
    cannot support a market-quality judgement.
    """
    per_seed: dict[int, dict] = {}
    for r in results:
        if r.classification.is_technical_invalid:
            continue
        market_samples = sample_market_series(r.events, sample_interval_ns)
        impact_samples = compute_price_impact(r.events, mult=1000)
        matrix = build_market_validation_matrix(
            market_samples, impact_samples, r.liquidation_metrics
        )
        per_seed[r.seed] = matrix.as_dict()
    return {"per_seed": per_seed}


def build_study_report(results: list[RunResult]) -> dict:
    """Build a structured study report from multi-seed results.

    Part 1 (endpoint): rates + severity across all runs.
    Part 2 (continuous): conditioned on *no* economic endpoint.
    """
    classifications = [r.classification for r in results]
    metrics_list = [r.liquidation_metrics for r in results]
    endpoint_samples: list[tuple[int | None, int | None]] = []
    continuous_samples: list[tuple[int | None, int | None]] = []
    impact_bps: list[int] = []
    for r in results:
        if r.classification.is_economic_endpoint:
            for aid in r.accounts:
                series = sample_agent_series(r.events, aid, 1_000_000_000, mult=1000)
                for s in series:
                    endpoint_samples.append((s.margin_ratio_bp, s.leverage_bp))
        elif not r.classification.is_technical_invalid:
            for aid in r.accounts:
                series = sample_agent_series(r.events, aid, 1_000_000_000, mult=1000)
                for s in series:
                    continuous_samples.append((s.margin_ratio_bp, s.leverage_bp))
        if not r.classification.is_technical_invalid:
            impact_bps.extend(s.impact_bp for s in compute_price_impact(r.events, mult=1000))
    report = build_report(classifications, metrics_list, continuous_samples, endpoint_samples)
    market_validation = build_market_validation_report(results)
    # KPI-011: per-seed zero-sum declaration -- skips technical-invalid runs
    # for the same reason build_market_validation_report does (a run whose
    # event log failed integrity/conservation checks can't support any
    # further declaration built from its account states).
    zero_sum = {
        r.seed: dataclasses.asdict(
            build_zero_sum_declaration(
                r.accounts, r.initial_baseline, r.exchange_fee_units, r.exchange_risk_pnl_units
            )
        )
        for r in results
        if not r.classification.is_technical_invalid
    }
    return {
        "endpoint": {
            "rate": report.endpoint.rate,
            "by_code": report.endpoint.by_code,
            "breach_count": report.endpoint.breach_count,
            "n_endpoint_samples": report.endpoint.n_samples,
            "mean_margin_ratio_bp": report.endpoint.mean_margin_ratio_bp,
            "mean_leverage_bp": report.endpoint.mean_leverage_bp,
        },
        "continuous": {
            "n_samples": report.continuous.n_samples,
            "mean_margin_ratio_bp": report.continuous.mean_margin_ratio_bp,
        },
        "impact": {
            "n_taker_orders": len(impact_bps),
            "mean_impact_bp": sum(impact_bps) / len(impact_bps) if impact_bps else 0.0,
        },
        "technical_invalid_rate": report.technical_invalid_rate,
        "n_runs": len(results),
        "n_completed": sum(1 for r in results if r.terminated == "COMPLETED"),
        "market_validation": market_validation,
        "zero_sum": zero_sum,
    }


def _max_event_timestamp(events: list[dict]) -> int:
    return max((e.get("timestamp", 0) for e in events), default=0)


def _compute_max_idle(events: list[dict]) -> int:
    """Longest gap between consecutive TRADE_SETTLE events (nanoseconds)."""
    trade_ts = sorted(e["timestamp"] for e in events if e.get("event_type") == "TRADE_SETTLE")
    if len(trade_ts) < 2:
        return 0
    return max(b - a for a, b in zip(trade_ts, trade_ts[1:], strict=False))


def _book_drained_by_liq(events: list[dict], book) -> bool:
    """Whether chained liquidation drained the book (both sides empty)."""
    has_chain = any(
        e.get("event_type") == "MARGIN_CALL" and (e.get("chain_depth") or 0) >= 1 for e in events
    )
    if not has_chain:
        return False
    return book.best_bid() is None and book.best_ask() is None


def _compute_initial_bp(leverage_tier: int) -> int:
    """``ceil(10000 / leverage_tier)`` per 账户合同 §3.1.1."""
    from market_game_sim.ledger.account import initial_margin_bp_for_tier

    return initial_margin_bp_for_tier(leverage_tier)


def _verify_bridge_residuals(events: list[dict], mult: int) -> None:
    """Verify PnL bridge residual = 0 for all trades (T503/KPI-009).

    ``mult`` must match the run's cash-unit scaling factor
    (``ExperimentConfig.mult``) so bridge_trade's tick-domain components
    are denominated consistently with ``wallet_delta_units``.
    """
    for e in events:
        if e.get("event_type") != "TRADE_SETTLE":
            continue
        vm_before_h = e.get("valuation_mark_before_half_ticks", 0)
        vm_after_h = e.get("valuation_mark_after_half_ticks", 0)
        for p in e.get("postings", []):
            if p.get("posting_type") != "TRADE_POSTING":
                continue
            result = bridge_trade(
                posting=p,
                vm_before_half=vm_before_h,
                vm_after_half=vm_after_h,
                trade_price_ticks=e.get("price_ticks", 0),
                position_before_units=p.get("position_after_units", 0)
                - p.get("position_delta_units", 0),
                mult=mult,
            )
            assert result["residual"] == 0, (
                f"PnL bridge residual {result['residual']} != 0 for {e.get('trade_id')}"
            )
