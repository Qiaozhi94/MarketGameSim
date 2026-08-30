"""T208 / gate R2: single-command goal-driven engineering showcase."""

from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Any

from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.experiment.config import ExperimentConfig
from market_game_sim.showcase.generate import build_showcase_bundle

DEFAULT_OUT = pathlib.Path("artifacts/showcase/R2")
REBUILD_COMMAND = "python -m market_game_sim.showcase.r2"


def build_r2_config() -> ExperimentConfig:
    """Return the fixed-seed goal-driven R2 demonstration config."""
    market_maker = AgentSpec(
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
    goal_agent = AgentSpec(
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
        ewma_half_life_trades=0,
    )
    return ExperimentConfig(
        seed=7,
        max_transactions=80,
        agent_specs=[market_maker, goal_agent],
        agent_signals={"agent-0": 10_000},
    )


def generate_r2_bundle(out_dir: str | pathlib.Path = DEFAULT_OUT) -> dict[str, Any]:
    """Generate the fixed R2 bundle through the production showcase pipeline."""
    return build_showcase_bundle(
        build_r2_config(),
        out_dir,
        tick_size="0.01",
        min_quantity="0.001",
        cash_unit="0.01",
        gate="R2",
        rebuild_command=REBUILD_COMMAND,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=REBUILD_COMMAND)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)
    result = generate_r2_bundle(args.out)
    print(
        f"R2 goal-driven bundle written to {result['out_dir']} "
        f"(run_id={result['run_id']}, events={result['event_count']})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
