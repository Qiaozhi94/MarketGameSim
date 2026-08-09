"""T207 (0.1.3 E2): per-cell market-sufficiency for the cross matrix.

Positive + negative + multi-record cases per CLAUDE.md: eligible cells feed
conclusions; failing/declared-non-comparable cells are excluded.
"""

from __future__ import annotations

import pytest

from market_game_sim.robustness.cross_sufficiency import (
    CrossSufficiencyError,
    apply_sufficiency,
)


def _matrix(ok: bool):
    return {
        "fill_ratio_ok": ok,
        "items": {"fat_tails": {"name": "fat_tails", "verdict": "PASS" if ok else "FAIL"}},
    }


class TestApplySufficiency:
    def test_all_eligible(self):
        cells = [("f1", "linear", _matrix(True)), ("f1", "threshold", _matrix(True))]
        report = apply_sufficiency(cells)
        assert len(report.eligible_cells()) == 2
        report.validate_for_conclusion()

    def test_failing_cell_excluded(self):
        cells = [("f1", "linear", _matrix(True)), ("f1", "threshold", _matrix(False))]
        report = apply_sufficiency(cells)
        eligible = report.eligible_cells()
        assert len(eligible) == 1
        assert eligible[0].mapping_id == "linear"

    def test_declared_non_comparable_excluded(self):
        cells = [("f1", "linear", _matrix(True)), ("f1", "threshold", _matrix(True))]
        report = apply_sufficiency(cells, declared_non_comparable={("f1", "threshold")})
        assert len(report.eligible_cells()) == 1

    def test_duplicate_cell_fails(self):
        cells = [("f1", "linear", _matrix(True)), ("f1", "linear", _matrix(True))]
        with pytest.raises(CrossSufficiencyError, match="duplicate"):
            apply_sufficiency(cells)

    def test_multi_family_multi_mapping(self):
        cells = [(f, m, _matrix(True)) for f in ("f1", "f2") for m in ("linear", "threshold")]
        report = apply_sufficiency(cells)
        assert len(report.eligible_cells()) == 4
