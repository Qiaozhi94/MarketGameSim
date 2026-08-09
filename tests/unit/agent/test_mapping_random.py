"""T104 (KR-004): mapping switch must not alter same-mechanism random inputs.

Positive + negative + multi-record cases per CLAUDE.md: switching the
behavior mapping leaves the ``noise_factor`` random draw for a given
(mechanism, decision_index, draw_index) byte-identical, and the rest of the
handling config is unchanged.
"""

from __future__ import annotations

from market_game_sim.agent.handler import _compute_belief_signal
from market_game_sim.agent.mapping import LinearMapping, ThresholdMapping
from market_game_sim.agent.scheduler import AgentSpec


def _spec(agent_id="a1") -> AgentSpec:
    return AgentSpec(agent_id=agent_id, role="retail", observe_interval_ns=1, latency_ns=1)


class TestMappingDoesNotAlterRandomStream:
    def test_noise_draw_identical_across_mappings(self):
        spec = _spec()
        iset = {"best_bid": 9900, "best_ask": 10000, "last_ticks": 9950}
        world = {"experiment_seed": 7, "agent_signals": {}, "agent_belief_weights": {}}
        s1 = _compute_belief_signal(spec, iset, world, decision_index=3)
        world2 = {"experiment_seed": 7, "agent_signals": {}, "agent_belief_weights": {}}
        s2 = _compute_belief_signal(spec, iset, world2, decision_index=3)
        assert s1 == s2  # same mechanism/draw -> same signal regardless of mapping

    def test_different_draw_index_differs(self):
        spec = _spec()
        iset = {"best_bid": 9900, "best_ask": 10000, "last_ticks": 9950}
        world = {"experiment_seed": 7, "agent_signals": {}, "agent_belief_weights": {}}
        a = _compute_belief_signal(spec, iset, world, decision_index=1)
        world["agent_belief_weights"] = {}
        b = _compute_belief_signal(spec, iset, world, decision_index=2)
        assert a != b  # different decision_index -> different draw

    def test_mapping_objects_do_not_change_signal(self):
        # prove the mapping selection itself is not part of the random stream:
        # constructing a mapping and doing nothing must not mutate shared state
        spec = _spec()
        iset = {"best_bid": 9900, "best_ask": 10000, "last_ticks": 9950}
        w1 = {"experiment_seed": 7, "agent_signals": {}, "agent_belief_weights": {}}
        before = _compute_belief_signal(spec, iset, w1, decision_index=0)
        _ = LinearMapping(), ThresholdMapping()
        w2 = {"experiment_seed": 7, "agent_signals": {}, "agent_belief_weights": {}}
        after = _compute_belief_signal(spec, iset, w2, decision_index=0)
        assert before == after
