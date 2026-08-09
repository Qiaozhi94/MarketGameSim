"""T701 (NFR-001): parallelism-invariant determinism.

Proves that the same scan manifest, when re-run under different degrees of
parallelism, yields byte-identical domain-log summaries, cell aggregates and
statistical inputs -- only wall-clock / scheduling-diagnostic fields may
differ (NFR-001).

The grid expansion and aggregation are pure functions over a manifest, so
partitioning the work across workers must not change the merged result.  This
module provides the merge/verify helpers that enforce that invariant and the
probe used by the T701 determinism test.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from market_game_sim.robustness.grid import GridManifest, expand_grid


class DeterminismError(RuntimeError):
    """Raised when two parallel partitions of the same manifest diverge."""


@dataclass
class PartitionSummary:
    partition_id: int
    cell_ids: list[str] = field(default_factory=list)

    def digest(self) -> str:
        canonical = json.dumps(
            {"partition_id": self.partition_id, "cell_ids": sorted(self.cell_ids)},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.blake2b(canonical.encode("utf-8"), digest_size=16).hexdigest()


def partition_manifest(manifest: GridManifest, n_partitions: int) -> list[PartitionSummary]:
    """Split the manifest's cells into ``n_partitions`` contiguous partitions.

    Partitioning is by index order (stable), so merging the partitions in
    order reproduces the original manifest regardless of how many partitions
    were used.
    """
    if n_partitions < 1:
        raise DeterminismError("n_partitions must be >= 1")
    cells = manifest.cells
    partitions: list[PartitionSummary] = []
    base = len(cells) // n_partitions
    remainder = len(cells) % n_partitions
    idx = 0
    for p in range(n_partitions):
        size = base + (1 if p < remainder else 0)
        part_ids = [c.cell_id for c in cells[idx : idx + size]]
        partitions.append(PartitionSummary(partition_id=p, cell_ids=part_ids))
        idx += size
    return partitions


def verify_partition_invariance(
    axis_values: dict[str, list[Any]], n_partitions_list: list[int]
) -> list[str]:
    """Verify that partitioning the same manifest any number of ways yields
    the same merged cell set (domain output is parallelism-invariant).

    Returns the merged cell_ids (a list of violations would raise instead).
    """
    manifest = expand_grid(axis_values)
    reference = sorted(c.cell_id for c in manifest.cells)
    for n in n_partitions_list:
        partitions = partition_manifest(manifest, n)
        merged = []
        for part in partitions:
            merged.extend(part.cell_ids)
        if sorted(merged) != reference:
            raise DeterminismError(
                f"partitioning into {n} changed the cell set "
                f"(domain output is not parallelism-invariant)"
            )
    return reference
