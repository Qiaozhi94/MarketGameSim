"""T401 (KR-004): shared random-path auditor.

Compares the random value at each shared semantic key
``(agent_id, mechanism, decision_index, draw_index)`` between two paired
runs, recomputed with the project's real ``blake2b_uniform`` derivation
(代理策略 §10.1).  This distinguishes "same master seed" from "complete
shared random-shock path": two runs can share a seed yet diverge if their
key consumption differs -- exactly the misalignment T401 exists to catch.

A pair is valid for single-dimension attribution only when every shared
semantic key is present in both runs and yields the identical random value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from market_game_sim.rng.distributions import blake2b_uniform


@dataclass
class RandomAudit:
    shared_keys: list[tuple[str, str, int, int]] = field(default_factory=list)
    mismatches: list[tuple[tuple[str, str, int, int], Any, Any]] = field(default_factory=list)
    only_in_control: list[tuple[str, str, int, int]] = field(default_factory=list)
    only_in_treatment: list[tuple[str, str, int, int]] = field(default_factory=list)

    @property
    def path_consistent(self) -> bool:
        return not self.mismatches and not self.only_in_control and not self.only_in_treatment

    def as_dict(self) -> dict[str, Any]:
        return {
            "path_consistent": self.path_consistent,
            "shared_key_count": len(self.shared_keys),
            "mismatch_count": len(self.mismatches),
            "only_in_control": [list(k) for k in self.only_in_control],
            "only_in_treatment": [list(k) for k in self.only_in_treatment],
        }


def _draw_value(
    seed: int, agent_id: str, mechanism: str, decision_index: int, draw_index: int
) -> Any:
    """Deterministic random value at a semantic key (代理策略 §10.1)."""
    return blake2b_uniform(seed, agent_id, mechanism, decision_index, draw_index)


def audit_shared_path(
    control_seed: int,
    treatment_seed: int,
    control_keys: list[tuple[str, str, int, int]],
    treatment_keys: list[tuple[str, str, int, int]] | None = None,
) -> RandomAudit:
    """Audit whether two paired runs share a complete, consistent random path.

    ``control_keys`` / ``treatment_keys``: each run's consumed semantic keys
    (``(agent_id, mechanism, decision_index, draw_index)``).  When
    ``treatment_keys`` is omitted it is taken to equal ``control_keys``.

    Same master seed is required but not sufficient -- every shared key must
    yield the identical value, and keys present in only one arm are reported
    (a signature of misaligned draw consumption).
    """
    t_keys = treatment_keys if treatment_keys is not None else control_keys
    audit = RandomAudit()
    c_set = set(control_keys)
    t_set = set(t_keys)

    audit.only_in_control = [k for k in control_keys if k not in t_set]
    audit.only_in_treatment = [k for k in t_keys if k not in c_set]

    for key in c_set & t_set:
        cv = _draw_value(control_seed, *key)
        tv = _draw_value(treatment_seed, *key)
        if cv != tv:
            audit.mismatches.append((key, cv, tv))
        else:
            audit.shared_keys.append(key)
    return audit
