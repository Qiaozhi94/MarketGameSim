"""T401 (KR-004): shared random-path auditor tests.

Positive + negative + multi-record cases per CLAUDE.md: same seed + same keys
=> path consistent; different seed => mismatch; asymmetric keys => reported.
"""

from __future__ import annotations

from market_game_sim.robustness.random_audit import audit_shared_path


def _keys(n=3):
    return [("a1", "noise_factor", i, 0) for i in range(n)]


class TestAuditSharedPath:
    def test_same_seed_same_keys_consistent(self):
        keys = _keys()
        a = audit_shared_path(7, 7, keys)
        assert a.path_consistent
        assert len(a.shared_keys) == 3

    def test_different_seed_mismatch(self):
        a = audit_shared_path(7, 8, _keys())
        assert not a.path_consistent
        assert len(a.mismatches) == 3

    def test_same_seed_but_different_agent_mismatch(self):
        # same seed but a different agent_id -> different draw
        c = [("a1", "noise_factor", 0, 0)]
        t = [("a2", "noise_factor", 0, 0)]
        a = audit_shared_path(7, 7, c, t)
        assert not a.path_consistent

    def test_asymmetric_keys_reported(self):
        c = [("a1", "noise_factor", 0, 0), ("a1", "noise_factor", 1, 0)]
        t = [("a1", "noise_factor", 0, 0)]
        a = audit_shared_path(7, 7, c, t)
        assert a.only_in_control == [("a1", "noise_factor", 1, 0)]
        assert not a.path_consistent

    def test_same_seed_same_key_deterministic(self):
        keys = _keys()
        assert (
            audit_shared_path(7, 7, keys).shared_keys == audit_shared_path(7, 7, keys).shared_keys
        )
