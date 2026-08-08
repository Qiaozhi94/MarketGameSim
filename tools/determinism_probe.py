"""T704 (0.1.2 附加门槛): cross-process determinism probe.

Runs a fixed small experiment and prints a JSON summary (event digest +
classification + liquidation metrics + study report) to stdout. Intended to
be invoked as a subprocess with different ``PYTHONHASHSEED`` values so a
test can assert the two outputs are byte-identical -- proving reproducibility
does not accidentally depend on Python's per-process hash randomization
(benchmarks/reference-machine.md §3: 摘要哈希一律使用 hashlib, 不得依赖内置
``hash()``/``set``/``dict`` 遍历顺序).

Usage::

    PYTHONHASHSEED=0 python tools/determinism_probe.py
    PYTHONHASHSEED=1 python tools/determinism_probe.py

Wall-clock is deliberately never captured here (T704: "墙钟字段排除在确定性
比较之外" -- the simplest way to honor that is to not compute it at all).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from market_game_sim.agent.scheduler import AgentSpec  # noqa: E402
from market_game_sim.eventlog.digest import rolling_digest_hex  # noqa: E402
from market_game_sim.experiment.config import ExperimentConfig  # noqa: E402
from market_game_sim.experiment.runner import build_study_report, run_multi_seed  # noqa: E402
from market_game_sim.schema.registry import get_registry  # noqa: E402


def _fixed_config() -> ExperimentConfig:
    mm = AgentSpec(
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
    belief = AgentSpec(
        agent_id="agent-0",
        role="retail",
        observe_interval_ns=1_000_000_000,
        latency_ns=50_000_000,
        leverage_tier=10,
        aggressiveness_bp=5_000,
        max_order_qty=5_000,
    )
    return ExperimentConfig(
        seed=1,
        max_transactions=400,
        agent_specs=[mm, belief],
        agent_signals={},
    )


def main() -> int:
    registry = get_registry()
    results = run_multi_seed(_fixed_config(), seeds=[1, 2])
    payload = {
        "event_digests": [rolling_digest_hex(r.events, registry) for r in results],
        "classifications": [r.classification.as_dict() for r in results],
        "liquidation_metrics": [
            {
                "total_liquidations": r.liquidation_metrics.total_liquidations,
                "total_volume": r.liquidation_metrics.total_volume,
                "liquidation_volume": r.liquidation_metrics.liquidation_volume,
                "chain_depth_counts": dict(
                    sorted(r.liquidation_metrics.chain_depth_counts.items())
                ),
                "bankruptcy_total": r.liquidation_metrics.bankruptcy_total,
            }
            for r in results
        ],
        "report": build_study_report(results),
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
