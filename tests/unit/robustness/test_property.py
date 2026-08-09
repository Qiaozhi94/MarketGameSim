"""T703 (NFR-002): property / boundary tests for the five robustness modules.

Covers scan expansion, pairing join, contamination check, ablation
renormalization and alternative mappings with *invariant* assertions
(parametrized / deterministic-exhaustive, no new deps -- hypothesis is
optional per plan.md §1 and not added):

- scan/grid: Cartesian completeness, cell_id uniqueness per combination,
  run_id uniqueness per seed/replicate;
- pairing: every input record lands in exactly one bucket (valid / duplicate /
  unknown / missing) -- the "never silently dropped" invariant;
- holdout: disjoint sets never contaminate;
- ablation: renormalized weight vector always sums to 1;
- mappings: threshold mapping is monotone in |signal|, dead-band exact.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from market_game_sim.agent.mapping import ThresholdMapping
from market_game_sim.robustness.ablation import ablated_weight_vector
from market_game_sim.robustness.cell_classify import RunCategory
from market_game_sim.robustness.grid import expand_grid
from market_game_sim.robustness.holdout import HoldoutManifest, check_contamination
from market_game_sim.robustness.pairing import (
    PairRecord,
    aggregate_pairs,
    arm_id,
    pair_id,
)

FACTOR_COUNT = 5


class TestScanExpansionProperties:
    def test_cartesian_product_complete(self):
        axes = {"maint_bp": [400, 500, 600], "mm": [1, 2, 3, 4], "lev": [3, 10]}
        g = expand_grid(axes)
        expected = 3 * 4 * 2
        assert len(g.cells) == expected

    @pytest.mark.parametrize("n_axes", [1, 2, 3])
    def test_cell_id_unique_per_combination(self, n_axes):
        axes = {f"axis{i}": list(range(i + 2)) for i in range(n_axes)}
        g = expand_grid(axes)
        ids = [c.cell_id for c in g.cells]
        assert len(set(ids)) == len(ids)  # no collisions

    def test_run_id_unique_per_seed_replicate(self):
        g = expand_grid({"maint_bp": [400]})
        c = g.cells[0]
        run_ids = {c.run_id(s, r) for s in range(5) for r in range(3)}
        assert len(run_ids) == 15


class TestPairingNoLossProperty:
    def test_every_record_lands_in_exactly_one_bucket(self):
        """The "never silently dropped" invariant: for any input set, the sum
        of records across valid / duplicate / unknown / single-side buckets
        equals the input count."""
        ctrl = arm_id("lev", {"tier": 3})
        trt = arm_id("lev", {"tier": 10})
        records = [
            # one valid pair
            PairRecord(pair_id("lev", {"n": 22}, 1), ctrl, RunCategory.COMPLETED, 1),
            PairRecord(pair_id("lev", {"n": 22}, 1), trt, RunCategory.COMPLETED, 1),
            # duplicate key (2 records)
            PairRecord(pair_id("lev", {"n": 22}, 2), ctrl, RunCategory.COMPLETED, 2),
            PairRecord(pair_id("lev", {"n": 22}, 2), ctrl, RunCategory.COMPLETED, 2),
            # unknown arm
            PairRecord(pair_id("lev", {"n": 22}, 3), "unknown", RunCategory.COMPLETED, 3),
            # single-side technical invalid (both arms accounted)
            PairRecord(pair_id("lev", {"n": 22}, 4), ctrl, RunCategory.TECHNICAL_INVALID, 4),
            PairRecord(pair_id("lev", {"n": 22}, 4), trt, RunCategory.COMPLETED, 4),
            # missing pair (only control present, accounted)
            PairRecord(pair_id("lev", {"n": 22}, 5), ctrl, RunCategory.COMPLETED, 5),
        ]
        report = aggregate_pairs(records, registered_arm_ids={ctrl, trt})
        # missing_pairs is a *marker* for the absent arm, not a record: the
        # present arm of a missing pair is already in single_side_missing
        accounted = (
            len(report.valid_pairs) * 2
            + len(report.duplicates_rejected) * 2  # each duplicate key has 2 records
            + len(report.unknown_arm_rejected)
            + len(report.single_side_missing)
        )
        assert accounted == len(records)


class TestContaminationProperty:
    def test_disjoint_sets_never_contaminate(self):
        """Invariant: any pair of disjoint cell/seed sets reports no leak."""
        for n in (1, 3, 10):
            holdout = HoldoutManifest(
                cells=[f"h{i}" for i in range(n)], seeds=[100 + i for i in range(n)]
            )
            used = [f"u{i}" for i in range(n)]
            assert check_contamination(holdout, used_cells=used, used_seeds=[1, 2, 3]) == []


class TestAblationRenormProperty:
    @pytest.mark.parametrize(
        "weights",
        [
            [Decimal("0.2")] * 5,
            [Decimal("0.5"), Decimal("0.3"), Decimal("0.1"), Decimal("0.05"), Decimal("0.05")],
        ],
    )
    def test_renormalized_sum_one_for_any_vector(self, weights):
        for disabled in ("momentum", "reversion", "herding", "book", "noise"):
            w, kept = ablated_weight_vector(weights, disabled)
            assert sum(w) == Decimal(1)
            assert len(w) == FACTOR_COUNT - 1

    def test_degenerate_vector_fails_closed(self):
        # only one nonzero weight: ablating that factor leaves zero total ->
        # fail-closed rejection, never a silent zero-sum renormalization
        from market_game_sim.robustness.ablation import AblationError

        weights = [Decimal("1"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0")]
        with pytest.raises(AblationError, match="denominator is zero"):
            ablated_weight_vector(weights, "momentum")

    def test_no_ablation_preserves_weights(self):
        w, kept = ablated_weight_vector([Decimal("0.2")] * 5, None)
        assert w == [Decimal("0.2")] * 5
        assert kept == [0, 1, 2, 3, 4]


class TestThresholdMappingProperties:
    @pytest.mark.parametrize("dead_band", [0, 100, 200, 500])
    def test_monotone_in_signal_magnitude(self, dead_band):
        m = ThresholdMapping(dead_band_bp=dead_band, step_fraction_bp=10_000)
        targets = [
            abs(m.target_position(s, 1_000_000, 10000, 1000, 1))
            for s in (0, dead_band, dead_band + 100, dead_band + 1000)
        ]
        assert targets == sorted(targets)  # non-decreasing in |signal|

    def test_dead_band_exact_boundary(self):
        m = ThresholdMapping(dead_band_bp=200, step_fraction_bp=10_000)
        assert m.target_position(199, 1_000_000, 10000, 1000, 1) == 0
        assert m.target_position(200, 1_000_000, 10000, 1000, 1) != 0
        assert m.target_position(-199, 1_000_000, 10000, 1000, 1) == 0
        assert m.target_position(-200, 1_000_000, 10000, 1000, 1) != 0

    def test_symmetry_of_sign(self):
        m = ThresholdMapping(dead_band_bp=100, step_fraction_bp=10_000)
        pos = m.target_position(500, 1_000_000, 10000, 1000, 1)
        neg = m.target_position(-500, 1_000_000, 10000, 1000, 1)
        assert pos == -neg
