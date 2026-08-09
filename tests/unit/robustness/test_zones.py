"""T004 (方法论 §10.3): sub-zone separation tests.

Positive + negative + multi-record cases per CLAUDE.md: cells stay disjoint
between exploration and holdout; cross-zone assignment fails-closed; cell_id
excludes seed while run_id includes it.
"""

from __future__ import annotations

import pytest

from market_game_sim.robustness.zones import (
    SubZone,
    ZoneRegistry,
    ZoneViolation,
    cell_id,
    run_id,
)


class TestCellId:
    def test_excludes_seed_and_replicate(self):
        unit = {"maint_bp": 500, "mapping": "linear"}
        assert cell_id({**unit, "seed": 1}) == cell_id({**unit, "seed": 999})
        assert cell_id({**unit, "replicate_id": 1}) == cell_id(unit)

    def test_includes_treatment_and_mapping(self):
        a = cell_id({"maint_bp": 500, "mapping": "linear"})
        b = cell_id({"maint_bp": 600, "mapping": "linear"})
        c = cell_id({"maint_bp": 500, "mapping": "threshold"})
        assert a != b
        assert a != c

    def test_deterministic(self):
        unit = {"maint_bp": 500, "mapping": "linear"}
        assert cell_id(unit) == cell_id(unit)

    def test_key_order_independent(self):
        assert cell_id({"a": 1, "b": 2}) == cell_id({"b": 2, "a": 1})


class TestRunId:
    def test_includes_seed_and_replicate(self):
        base = run_id("cell1", 1, 1)
        assert base != run_id("cell1", 2, 1)
        assert base != run_id("cell1", 1, 2)
        assert base != run_id("cell2", 1, 1)

    def test_deterministic(self):
        assert run_id("cell1", 1, 1) == run_id("cell1", 1, 1)


class TestZoneRegistry:
    def test_assign_and_disjoint(self):
        reg = ZoneRegistry()
        c1 = cell_id({"maint_bp": 500})
        c2 = cell_id({"maint_bp": 600})
        reg.assign(c1, SubZone.EXPLORATION_SCAN)
        reg.assign(c2, SubZone.HOLDOUT_VALIDATION)
        assert reg.check_disjoint()
        reg.validate()  # no error

    def test_cross_zone_assign_fails_closed(self):
        reg = ZoneRegistry()
        c1 = cell_id({"maint_bp": 500})
        reg.assign(c1, SubZone.EXPLORATION_SCAN)
        with pytest.raises(ZoneViolation, match="disjoint"):
            reg.assign(c1, SubZone.HOLDOUT_VALIDATION)

    def test_reassign_same_zone_is_noop(self):
        reg = ZoneRegistry()
        c1 = cell_id({"maint_bp": 500})
        reg.assign(c1, SubZone.EXPLORATION_SCAN)
        reg.assign(c1, SubZone.EXPLORATION_SCAN)  # no error
        assert reg.check_disjoint()

    def test_validate_catches_overlap(self):
        reg = ZoneRegistry()
        c1 = cell_id({"maint_bp": 500})
        reg.exploration_cells.add(c1)
        reg.holdout_cells.add(c1)  # force overlap
        with pytest.raises(ZoneViolation, match="overlap"):
            reg.validate()

    def test_multi_cell_partition(self):
        reg = ZoneRegistry()
        cells = [cell_id({"maint_bp": bp}) for bp in (400, 500, 600, 700)]
        for c in cells[:2]:
            reg.assign(c, SubZone.EXPLORATION_SCAN)
        for c in cells[2:]:
            reg.assign(c, SubZone.HOLDOUT_VALIDATION)
        assert reg.check_disjoint()
        assert len(reg.exploration_cells) == 2
        assert len(reg.holdout_cells) == 2
