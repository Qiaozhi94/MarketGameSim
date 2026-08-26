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
    # Generic escape hatch (not benchmark-specific itself): extra pre-funded
    # accounts + raw events to enqueue alongside the normal AGENT_OBSERVE
    # cycle. bench/shock.py uses this to inject a one-shot forcing trade so
    # BENCH-001's coverage assertions can actually be exercised within a
    # bounded transaction budget -- belief-agent/market-maker research
    # configs simply never set these and see no behavior change.
    extra_accounts: dict[str, int] = field(default_factory=dict)  # agent_id -> wallet_units
    extra_events: list[dict] = field(default_factory=list)
    # Bootstrap accounts directly into an already-open position (wallet_units/
    # position_units/entry_notional_units), bypassing the normal decision loop
    # entirely. bench/shock.py's calibration found that building a leveraged
    # position *through* AGENT_DECIDE and then shocking it fights itself (the
    # forced buying pressure feeds back into the position size before the
    # shock can land) -- pre-positioning sidesteps that by never running a
    # buildup phase at all. These accounts get no AgentSpec and never decide;
    # they are pure static risk to be tested against, like the "A" account in
    # acceptance-vectors.md 案例7/8.
    extra_positions: dict[str, dict[str, int]] = field(default_factory=dict)
    # 0.1.3 E1/E3: robustness treatment knobs, threaded into the world so the
    # decision pipeline varies family / mapping / ablation without code change.
    # Included in compute_config_hash, so every robustness cell traces back to
    # a distinct config hash (E3).
    model_family: str = "belief_family"  # T006: belief_family | signal_family
    behavior_mapping: str = "linear"  # T102: linear | threshold
    disabled_factor: str | None = None  # T301: leave-one-out ablation switch
    # 0.1.5 T209 (FR-023): the run family (SPONTANEOUS / STRESS / BENCHMARK).
    # None = legacy config that predates the family declaration; run_one only
    # enforces the allow/deny matrix once a family is explicitly declared
    # (旧配置按 design.md §7 显式迁移为 BENCHMARK，不自动猜测).
    run_family: str | None = None


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
