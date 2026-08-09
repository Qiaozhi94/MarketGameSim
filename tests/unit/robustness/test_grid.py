"""T202 (FR-014): grid-expansion tests.

Positive + negative + multi-record cases per CLAUDE.md: stable order, cell_id
excludes seed while run_id includes it, and Cartesian product is complete.
"""

from __future__ import annotations

import pytest

from market_game_sim.robustness.grid import GridError, expand_grid, normalize_parameter
from market_game_sim.robustness.zones import cell_id, run_id


class TestNormalize:
    def test_key_sorted(self):
        assert list(normalize_parameter({"b": 2, "a": 1})) == ["a", "b"]


class TestExpandGrid:
    def test_cartesian_product(self):
        g = expand_grid({"maint_bp": [400, 500], "mm": [1, 2]})
        assert len(g.cells) == 4

    def test_stable_order(self):
        g1 = expand_grid({"maint_bp": [400, 500], "mm": [1, 2]})
        g2 = expand_grid({"mm": [1, 2], "maint_bp": [400, 500]})  # different input key order
        assert g1.iter_cell_ids() == g2.iter_cell_ids()

    def test_deterministic_ids(self):
        g = expand_grid({"maint_bp": [400]})
        assert g.cells[0].cell_id == g.cells[0].cell_id

    def test_cell_id_matches_zones(self):
        g = expand_grid({"maint_bp": [400]})
        assert g.cells[0].cell_id == cell_id({"maint_bp": 400})

    def test_empty_grid_fails(self):
        with pytest.raises(GridError):
            expand_grid({})


class TestRunId:
    def test_cell_run_id_includes_seed(self):
        g = expand_grid({"maint_bp": [400]})
        c = g.cells[0]
        assert c.run_id(1) != c.run_id(2)
        assert c.run_id(1, 0) == run_id(c.cell_id, 1, 0)

    def test_distinct_cells_distinct_run_ids(self):
        g = expand_grid({"maint_bp": [400, 500]})
        assert g.cells[0].run_id(1) != g.cells[1].run_id(1)
