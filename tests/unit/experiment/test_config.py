"""E3 (0.1.2 退出条件) regression: compute_config_hash.

"预注册实验可从配置哈希追溯到条件性结论" had no implementation anywhere
in experiment/ -- eventlog/writer.py accepts a caller-supplied
``config_hash`` for RUN_HEADER, but nothing in the experiment-running
pipeline ever computed one or threaded it through to a report.
"""

from __future__ import annotations

from dataclasses import replace

from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.experiment.config import ExperimentConfig, compute_config_hash


def _config(**overrides) -> ExperimentConfig:
    base = ExperimentConfig(seed=1, max_transactions=1000)
    return replace(base, **overrides) if overrides else base


def test_same_config_same_hash():
    a = _config()
    b = _config()
    assert compute_config_hash(a) == compute_config_hash(b)


def test_different_seed_gives_different_hash():
    a = _config(seed=1)
    b = _config(seed=2)
    assert compute_config_hash(a) != compute_config_hash(b)


def test_different_agent_specs_gives_different_hash():
    spec1 = AgentSpec(
        agent_id="a1", role="retail", observe_interval_ns=1_000_000_000, latency_ns=50_000_000
    )
    spec2 = AgentSpec(
        agent_id="a1",
        role="retail",
        observe_interval_ns=1_000_000_000,
        latency_ns=50_000_000,
        leverage_tier=10,  # only this differs
    )
    a = _config(agent_specs=[spec1])
    b = _config(agent_specs=[spec2])
    assert compute_config_hash(a) != compute_config_hash(b)


def test_hash_is_stable_across_repeated_calls():
    """Not literally a cross-process check (that's determinism_probe.py's
    job for the whole pipeline) -- just confirms this function itself
    doesn't depend on anything non-deterministic like dict iteration
    order or object identity."""
    cfg = _config()
    hashes = {compute_config_hash(cfg) for _ in range(5)}
    assert len(hashes) == 1


def test_hash_is_a_nonempty_hex_string():
    h = compute_config_hash(_config())
    assert isinstance(h, str)
    assert len(h) > 0
    int(h, 16)  # must not raise -- proves it's valid hex
