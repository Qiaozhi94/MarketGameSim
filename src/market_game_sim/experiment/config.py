"""ExperimentConfig -- split out of runner.py so experiment/protocol.py (T603)
can import it without a runner.py<->protocol.py circular import (runner.py
wires ExperimentProtocol into run_one/run_multi_seed)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

from market_game_sim.agent.scheduler import AgentSpec


@dataclass
class ExperimentConfig:
    """Runtime configuration for one experiment run."""

    seed: int
    max_transactions: int
    initial_price_ticks: int = 10000
    mult: int = 1000
    maker_bps: int = -1
    taker_bps: int = 5
    maint_bp: int = 500
    target_bp: int = 1000
    liquidation_latency_ns: int = 1_000_000
    agent_specs: list[AgentSpec] = field(default_factory=list)
    agent_signals: dict[str, int] = field(default_factory=dict)
    group_label: str = "control"  # "control" | "treatment" for paired experiments


def compute_config_hash(config: ExperimentConfig) -> str:
    """E3 (0.1.2 退出条件): stable content hash of a full ``ExperimentConfig``
    (including every ``AgentSpec``), so a reported conditional conclusion can
    be traced back to the exact configuration that produced it.

    Uses ``hashlib.blake2b`` over a canonical (sorted-key, no whitespace)
    JSON serialization of ``dataclasses.asdict`` -- not Python's builtin
    ``hash()``, which is per-process-salted and would make the same config
    hash differently across runs (reference-machine.md §3).
    """
    canonical = json.dumps(asdict(config), sort_keys=True, separators=(",", ":"))
    return hashlib.blake2b(canonical.encode("utf-8"), digest_size=16).hexdigest()
