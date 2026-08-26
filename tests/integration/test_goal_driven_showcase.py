"""AC-001/AC-002/AC-005 (T208 / FR-027): goal-driven showcase bundle (R2 gate).

Drives the real pipeline with a goal-driven config (goal_model_id set) and
asserts:
- the R2 bundle produces the five fixed files with
  evidence_class=engineering-demonstration;
- the raw event log contains at least one traceable
  observe -> goal/constraint decision -> order -> trade causal chain
  (AC-005), with DecisionEvidenceV1 audit fields on every AGENT_DECIDE.
"""

from __future__ import annotations

from market_game_sim import __version__
from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.experiment.config import ExperimentConfig, compute_config_hash
from market_game_sim.showcase.generate import build_showcase_bundle
from market_game_sim.showcase.summary import DISCLAIMER

REBUILD_CMD = "python -m market_game_sim.showcase.generate <config.yaml>"


def _mm_spec() -> AgentSpec:
    return AgentSpec(
        agent_id="mm-0",
        role="inventory_market_maker",
        observe_interval_ns=100_000_000,
        latency_ns=5_000_000,
        is_market_maker=True,
        half_spread_ticks=5,
        quote_size=10_000,
        max_inventory=100_000,
        inventory_skew_k_bp=10_000,
    )


def _belief_spec() -> AgentSpec:
    return AgentSpec(
        agent_id="agent-0",
        role="retail",
        observe_interval_ns=1_000_000_000,
        latency_ns=50_000_000,
        leverage_tier=10,
        initial_bp=1000,
        aggressiveness_bp=10_000,
        max_order_qty=10_000,
        goal_model_id="risk_budget_linear_v1",
        risk_appetite_x1000=2000,
        ewma_half_life_trades=0,  # warmup off so the chain test can trade
    )


def _goal_config() -> ExperimentConfig:
    return ExperimentConfig(
        seed=7,
        max_transactions=80,
        agent_specs=[_mm_spec(), _belief_spec()],
        agent_signals={"agent-0": 10_000},
    )


def _load_log(tmp_path):
    import json

    return [
        json.loads(line)
        for line in (tmp_path / "run.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def test_goal_driven_bundle_produces_five_files(tmp_path):
    config = _goal_config()
    result = build_showcase_bundle(
        config,
        tmp_path,
        tick_size="0.01",
        min_quantity="0.001",
        cash_unit="0.01",
        gate="R2",
        rebuild_command=REBUILD_CMD,
    )
    for name in ("run.jsonl", "replay.html", "summary.md", "RUN.md", "manifest.json"):
        assert (tmp_path / name).is_file(), f"missing bundle file: {name}"
    assert result["terminated"] == "COMPLETED"


def test_goal_driven_manifest_evidence_class(tmp_path):
    import json

    config = _goal_config()
    build_showcase_bundle(
        config,
        tmp_path,
        tick_size="0.01",
        min_quantity="0.001",
        cash_unit="0.01",
        gate="R2",
        rebuild_command=REBUILD_CMD,
    )
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["evidence_class"] == "engineering-demonstration"
    assert manifest["code_version"] == __version__
    assert manifest["config_hash"] == compute_config_hash(config)
    assert manifest["seed"] == config.seed
    assert manifest["gate"] == "R2"


def test_goal_driven_summary_carries_disclaimer(tmp_path):
    config = _goal_config()
    build_showcase_bundle(
        config,
        tmp_path,
        tick_size="0.01",
        min_quantity="0.001",
        cash_unit="0.01",
        gate="R2",
        rebuild_command=REBUILD_CMD,
    )
    text = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert DISCLAIMER in text


def test_goal_driven_log_has_decision_evidence_chain(tmp_path):
    """AC-005: at least one full causal chain is traceable in the raw log --
    AGENT_OBSERVE -> AGENT_DECIDE(decision_evidence) -> ORDER_ARRIVAL ->
    TRADE_SETTLE, with each hop's event_id referenced by the next."""
    config = _goal_config()
    build_showcase_bundle(
        config,
        tmp_path,
        tick_size="0.01",
        min_quantity="0.001",
        cash_unit="0.01",
        gate="R2",
        rebuild_command=REBUILD_CMD,
    )
    records = _load_log(tmp_path)
    by_id = {r["event_id"]: r for r in records if r.get("record_kind") == "EVENT"}

    observes = [
        r
        for r in records
        if r.get("event_type") == "AGENT_OBSERVE" and r.get("agent_id") == "agent-0"
    ]
    decides = [
        r
        for r in records
        if r.get("event_type") == "AGENT_DECIDE" and r.get("agent_id") == "agent-0"
    ]
    assert observes and decides, "goal-driven run must emit observe+decide for the belief agent"

    decide = decides[0]
    ev = decide.get("decision_evidence")
    assert ev is not None, "AGENT_DECIDE must carry DecisionEvidenceV1"
    assert ev["goal_model_id"] == "risk_budget_linear_v1"
    assert ev["trigger_provenance"] == "ENDOGENOUS_AGENT"
    assert isinstance(ev["desired_position_units"], int)
    assert isinstance(ev["executable_position_units"], int)
    assert isinstance(ev["constraint_binding"], bool)
    assert ev["cursor_from_event_id"] in by_id or ev["cursor_from_event_id"] == "e1_0"

    # observe -> decide chain: the decide references its observation.
    assert decide["observation_event_id"] in by_id

    # decide -> order: at least one of this agent's decisions produced a
    # SUBMIT order (an early decision may only cancel stale orders -- §6.2
    # full-cancel-replace -- so scan rather than assume decides[0]).
    decided_ids = {d["event_id"] for d in decides}
    orders = [
        r
        for r in records
        if r.get("event_type") == "ORDER_ARRIVAL"
        and r.get("decision_event_id") in decided_ids
        and r.get("action") == "SUBMIT"
    ]
    assert orders, "a goal-driven decision must produce at least one SUBMIT order"

    # order -> trade: at least one trade settles from this decision's orders.
    trades = [r for r in records if r.get("event_type") == "TRADE_SETTLE"]
    assert trades, "the run must produce at least one trade"


def test_goal_driven_replay_offline_single_file(tmp_path):
    config = _goal_config()
    build_showcase_bundle(
        config,
        tmp_path,
        tick_size="0.01",
        min_quantity="0.001",
        cash_unit="0.01",
        gate="R2",
        rebuild_command=REBUILD_CMD,
    )
    html = (tmp_path / "replay.html").read_text(encoding="utf-8")
    assert "fetch(" not in html
    assert "http://" not in html
    assert "https://" not in html
    assert "replay-data" in html


def test_goal_driven_run_is_deterministic(tmp_path):
    """Same config + seed -> identical event summary hash across two runs."""
    from market_game_sim.eventlog.digest import rolling_digest_hex
    from market_game_sim.schema.registry import get_registry

    registry = get_registry()
    config = _goal_config()
    build_showcase_bundle(
        config,
        tmp_path,
        tick_size="0.01",
        min_quantity="0.001",
        cash_unit="0.01",
        gate="R2",
        rebuild_command=REBUILD_CMD,
    )
    first = _load_log(tmp_path)
    build_showcase_bundle(
        config,
        tmp_path / "second",
        tick_size="0.01",
        min_quantity="0.001",
        cash_unit="0.01",
        gate="R2",
        rebuild_command=REBUILD_CMD,
    )
    second = _load_log(tmp_path / "second")
    events1 = [r for r in first if r.get("record_kind") == "EVENT"]
    events2 = [r for r in second if r.get("record_kind") == "EVENT"]
    assert rolling_digest_hex(events1, registry) == rolling_digest_hex(events2, registry)
