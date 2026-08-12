"""T201 (AC-002, E2/PR-018): single-file offline replay acceptance.

Generates a replay HTML from a real small run's log and asserts it is a
single self-contained file with no external requests.
"""

from __future__ import annotations

import json

from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.experiment.runner import ExperimentConfig, run_one
from market_game_sim.ledger.account import initial_margin_bp_for_tier
from market_game_sim.replay.generate import build_replay


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
        aggressiveness_bp=5_000,
        max_order_qty=5_000,
    )


def _write_log(path, result, config: ExperimentConfig) -> None:
    header = {
        "record_kind": "RUN_HEADER",
        "schema_version": 3,
        "run_id": f"exp-s{result.seed}",
        "tick_size": "0.01",
        "min_quantity": "0.001",
        "cash_unit": "0.01",
        "mult": config.mult,
        "fee_bps_cap": max(config.maker_bps, config.taker_bps, 0),
        "initial_price_ticks": config.initial_price_ticks,
        "agent_initial_bp": {
            s.agent_id: initial_margin_bp_for_tier(s.leverage_tier) for s in config.agent_specs
        },
    }
    max_txn = max((e["transaction_seq"] for e in result.events), default=2)
    trailer = {
        "record_kind": "RUN_TRAILER",
        "terminated": result.terminated,
        "abort_code": result.abort_code,
        "abort_detail": None,
        "last_committed_transaction_seq": max_txn,
        "record_count": 2 + len(result.events),
    }
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(header) + "\n")
        for e in result.events:
            f.write(json.dumps(e) + "\n")
        f.write(json.dumps(trailer) + "\n")


def test_offline_single_file_generated(tmp_path):
    cfg = ExperimentConfig(
        seed=1,
        max_transactions=60,
        agent_specs=[_mm_spec(), _belief_spec()],
        agent_signals={"agent-0": 10_000},
    )
    result = run_one(cfg)
    assert result.terminated == "COMPLETED"

    log_path = tmp_path / "run.jsonl"
    out_path = tmp_path / "replay.html"
    _write_log(log_path, result, cfg)
    build_replay(log_path, out_path)

    html = out_path.read_text(encoding="utf-8")
    assert html.count("<html") == 1
    assert "replay-data" in html
    assert "fetch(" not in html
    assert "http://" not in html
    assert "https://" not in html
    assert "cdn" not in html.lower()
    assert not (tmp_path / "replay.html.tmp").exists()


def test_generated_html_contains_run_id(tmp_path):
    cfg = ExperimentConfig(
        seed=1,
        max_transactions=40,
        agent_specs=[_mm_spec(), _belief_spec()],
        agent_signals={"agent-0": 10_000},
    )
    result = run_one(cfg)
    log_path = tmp_path / "run.jsonl"
    _write_log(log_path, result, cfg)
    out_path = tmp_path / "replay.html"
    build_replay(log_path, out_path)
    html = out_path.read_text(encoding="utf-8")
    assert f"exp-s{result.seed}" in html
