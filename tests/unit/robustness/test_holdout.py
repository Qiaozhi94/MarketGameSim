"""T501/T502: frozen holdout zone tests.

Positive + negative + multi-record cases per CLAUDE.md: sealed manifest is
immutable, and holdout leakage into non-holdout inputs is detected.
"""

from __future__ import annotations

import json

import pytest

from market_game_sim.robustness.holdout import (
    HoldoutError,
    HoldoutManifest,
    check_contamination,
    holdout_id,
    seal_holdout,
)


class TestSealHoldout:
    def test_writes_and_returns_id(self, tmp_path):
        m = HoldoutManifest(cells=["c1", "c2"], seeds=[1, 2])
        path = tmp_path / "holdout.json"
        hid = seal_holdout(m, path)
        assert hid == holdout_id(m)
        assert json.loads(path.read_text(encoding="utf-8"))["holdout_id"] == hid

    def test_refuses_overwrite_different(self, tmp_path):
        path = tmp_path / "holdout.json"
        seal_holdout(HoldoutManifest(cells=["c1"], seeds=[1]), path)
        with pytest.raises(HoldoutError, match="refusing to overwrite"):
            seal_holdout(HoldoutManifest(cells=["c9"], seeds=[9]), path)

    def test_idempotent_same_content(self, tmp_path):
        path = tmp_path / "holdout.json"
        seal_holdout(HoldoutManifest(cells=["c1"], seeds=[1]), path)
        seal_holdout(HoldoutManifest(cells=["c1"], seeds=[1]), path)


class TestCheckContamination:
    def test_no_contamination(self):
        m = HoldoutManifest(cells=["h1"], seeds=[99])
        assert check_contamination(m, used_cells=["a1"], used_seeds=[1]) == []

    def test_cell_leak_detected(self):
        m = HoldoutManifest(cells=["h1", "h2"], seeds=[1])
        violations = check_contamination(m, used_cells=["a1", "h2"])
        assert len(violations) == 1
        assert "holdout cells leaked" in violations[0]

    def test_seed_leak_detected(self):
        m = HoldoutManifest(cells=["h1"], seeds=[1, 2])
        violations = check_contamination(m, used_cells=["a1"], used_seeds=[2])
        assert len(violations) == 1
        assert "holdout seeds leaked" in violations[0]

    def test_multi_leak_all_reported(self):
        m = HoldoutManifest(cells=["h1"], seeds=[1])
        violations = check_contamination(m, used_cells=["h1"], used_seeds=[1])
        assert len(violations) == 2

    def test_no_seed_check_when_none_given(self):
        m = HoldoutManifest(cells=["h1"], seeds=[1])
        assert check_contamination(m, used_cells=["a1"]) == []
