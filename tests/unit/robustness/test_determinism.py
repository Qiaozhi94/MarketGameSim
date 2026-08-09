"""T701 (NFR-001): parallelism-invariance tests.

Positive + negative + multi-record cases per CLAUDE.md: same manifest under
different partition counts yields identical cell sets; invalid count fails.
"""

from __future__ import annotations

import pytest

from market_game_sim.robustness.determinism import (
    DeterminismError,
    partition_manifest,
    verify_partition_invariance,
)
from market_game_sim.robustness.grid import expand_grid


def _axes():
    return {"maint_bp": [400, 500, 600], "mm": [1, 2, 3]}


class TestPartitionManifest:
    def test_partitions_merge_to_full(self):
        manifest = expand_grid(_axes())
        parts = partition_manifest(manifest, 3)
        merged = [c for p in parts for c in p.cell_ids]
        assert sorted(merged) == sorted(c.cell_id for c in manifest.cells)

    def test_partition_count_variants_merge_same(self):
        manifest = expand_grid(_axes())
        base = sorted(c.cell_id for c in manifest.cells)
        for n in (1, 2, 5, 9):
            merged = [c for p in partition_manifest(manifest, n) for c in p.cell_ids]
            assert sorted(merged) == base

    def test_zero_partitions_fails(self):
        manifest = expand_grid(_axes())
        with pytest.raises(DeterminismError, match=">= 1"):
            partition_manifest(manifest, 0)


class TestVerifyPartitionInvariance:
    def test_parallelism_invariant(self):
        ref = verify_partition_invariance(_axes(), n_partitions_list=[1, 2, 3, 4])
        assert ref == sorted(c.cell_id for c in expand_grid(_axes()).cells)

    def test_empty_axes_fails(self):
        from market_game_sim.robustness.grid import GridError

        with pytest.raises(GridError):
            verify_partition_invariance({}, [1])
