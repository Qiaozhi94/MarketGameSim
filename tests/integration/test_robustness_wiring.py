"""0.1.3 E1/E3: model-family / mapping / ablation wiring through real runs.

The robustness treatment knobs (model_family / behavior_mapping /
disabled_factor) must thread from ExperimentConfig through run_one's world
into the decision pipeline -- a real run with each knob actually completes
and the knobs land in the config hash (E3 traceability).
"""

from __future__ import annotations

from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.experiment.config import ExperimentConfig, compute_config_hash
from market_game_sim.experiment.runner import run_multi_seed, run_one


def _spec(aid: str = "a1") -> AgentSpec:
    return AgentSpec(
        agent_id=aid,
        role="retail",
        observe_interval_ns=1_000_000_000,
        latency_ns=50_000_000,
        leverage_tier=10,
        aggressiveness_bp=5_000,
        max_order_qty=5_000,
    )


def _cfg(**kw):
    base = dict(
        seed=1,
        max_transactions=400,
        agent_specs=[_spec()],
    )
    base.update(kw)
    return ExperimentConfig(**base)


class TestModelFamilyWiring:
    def test_both_families_run(self):
        for family in ("belief_family", "signal_family"):
            r = run_one(_cfg(model_family=family))
            assert r.terminated == "COMPLETED"

    def test_family_in_config_hash(self):
        h1 = compute_config_hash(_cfg(model_family="belief_family"))
        h2 = compute_config_hash(_cfg(model_family="signal_family"))
        assert h1 != h2


class TestMappingWiring:
    def test_threshold_mapping_runs(self):
        r = run_one(_cfg(behavior_mapping="threshold"))
        assert r.terminated == "COMPLETED"

    def test_mapping_in_config_hash(self):
        assert compute_config_hash(_cfg(behavior_mapping="linear")) != compute_config_hash(
            _cfg(behavior_mapping="threshold")
        )


class TestAblationWiring:
    def test_each_factor_ablation_runs(self):
        for factor in ("momentum", "reversion", "herding", "book", "noise"):
            r = run_one(_cfg(disabled_factor=factor))
            assert r.terminated == "COMPLETED", f"ablate {factor} failed"

    def test_ablation_in_config_hash(self):
        assert compute_config_hash(_cfg(disabled_factor=None)) != compute_config_hash(
            _cfg(disabled_factor="noise")
        )


class TestMultiSeedPreservesKnobs:
    def test_signal_family_multi_seed(self):
        rs = run_multi_seed(_cfg(model_family="signal_family"), seeds=[1, 2, 3])
        assert all(r.terminated == "COMPLETED" for r in rs)
        assert len(rs) == 3
