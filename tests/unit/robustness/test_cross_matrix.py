"""T105 (0.1.3 E1): cross-matrix report tests.

Positive + negative + multi-record cases per CLAUDE.md: complete same-direction
matrix -> "同向成立"; missing cell -> "证据不足"; reversal -> "依赖边界".
"""

from __future__ import annotations

from market_game_sim.robustness.cross_matrix import CrossCell, CrossMatrix

FAMILIES = ["belief_family", "signal_family"]
MAPPINGS = ["linear", "threshold"]


def _cell(family, mapping, direction, significant=True):
    return CrossCell(
        family_id=family,
        mapping_id=mapping,
        effect_direction=direction,
        significant=significant,
    )


def _full_matrix(direction=+1):
    return CrossMatrix(cells=[_cell(f, m, direction) for f in FAMILIES for m in MAPPINGS])


class TestCompleteness:
    def test_full_matrix_complete(self):
        assert _full_matrix().is_complete(FAMILIES, MAPPINGS)

    def test_missing_cell_reported(self):
        m = _full_matrix()
        m.cells = m.cells[:-1]
        assert m.missing(FAMILIES, MAPPINGS) == [("signal_family", "threshold")]


class TestReport:
    def test_same_direction_across_matrix(self):
        r = _full_matrix(+1).report(FAMILIES, MAPPINGS)
        assert r["complete"]
        assert r["same_direction"] is True
        assert r["conclusion"] == "同向成立"

    def test_reversal_is_dependency_boundary(self):
        m = _full_matrix(+1)
        # reverse one cell -> direction signature {+1, -1}
        m.cells[0].effect_direction = -1
        r = m.report(FAMILIES, MAPPINGS)
        assert r["same_direction"] is False
        assert r["conclusion"] == "依赖边界"

    def test_missing_cell_insufficient_evidence(self):
        m = _full_matrix()
        m.cells = m.cells[:-1]
        r = m.report(FAMILIES, MAPPINGS)
        assert r["conclusion"] == "证据不足"
        assert r["complete"] is False

    def test_nothing_significant_insufficient_evidence(self):
        m = _full_matrix()
        for c in m.cells:
            c.significant = False
        r = m.report(FAMILIES, MAPPINGS)
        assert r["conclusion"] == "证据不足"

    def test_reports_dimension_counts(self):
        r = _full_matrix(+1).report(FAMILIES, MAPPINGS)
        assert r["mapping_direction_counts"] == {
            "linear": [1],
            "threshold": [1],
        }
        assert r["family_direction_counts"] == {
            "belief_family": [1],
            "signal_family": [1],
        }

    def test_same_direction_must_be_whole_matrix(self):
        # separate-dimension counting would pass here, but whole-matrix
        # consistency must fail because one cell reverses
        m = _full_matrix(+1)
        m.cells[0].effect_direction = -1
        r = m.report(FAMILIES, MAPPINGS)
        # per-mapping: linear has {+1,-1} -> not all same; matrix not same
        assert r["same_direction"] is False

    def test_zero_direction_cells_break_same_direction(self):
        # v013 regression (critical): two +1 and two 0-direction cells must
        # NOT yield "同向成立" -- the zero cells show no effect, so the claim
        # does not hold across the whole matrix (dependency boundary).
        m = _full_matrix(+1)
        m.cells[2].effect_direction = 0
        m.cells[3].effect_direction = 0
        r = m.report(FAMILIES, MAPPINGS)
        assert r["same_direction"] is False
        assert r["conclusion"] == "依赖边界"

    def test_all_zero_direction_insufficient(self):
        m = _full_matrix(+1)
        for c in m.cells:
            c.effect_direction = 0
        r = m.report(FAMILIES, MAPPINGS)
        assert r["conclusion"] == "证据不足"

    def test_one_non_significant_cell_insufficient(self):
        m = _full_matrix(+1)
        m.cells[3].significant = False
        r = m.report(FAMILIES, MAPPINGS)
        assert r["same_direction"] is False
        assert r["conclusion"] == "依赖边界"


class TestCellLookup:
    def test_lookup(self):
        m = _full_matrix()
        assert m.cell("belief_family", "linear") is not None
        assert m.cell("belief_family", "nope") is None
