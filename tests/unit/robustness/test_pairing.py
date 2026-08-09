"""T402 (方法论 §9.2): pair_id/arm_id pairing tests.

Positive + negative + multi-record cases per CLAUDE.md: valid pairs joined,
and each fail-closed bucket (duplicate / unknown arm / single-side-missing /
missing pair) is exercised.
"""

from __future__ import annotations

from market_game_sim.robustness.cell_classify import RunCategory
from market_game_sim.robustness.pairing import (
    PairRecord,
    aggregate_pairs,
    arm_id,
    pair_id,
)

CTRL = arm_id("lev", {"tier": 3})
TRT = arm_id("lev", {"tier": 10})
REG = {CTRL, TRT}


def _rec(pair_family, covariates, seed, arm, category=RunCategory.COMPLETED, replicate=0):
    return PairRecord(
        pair_id=pair_id(pair_family, covariates, seed, replicate),
        arm_id=arm,
        category=category,
        seed=seed,
    )


class TestIds:
    def test_pair_id_same_across_arms(self):
        cov = {"n_agents": 22}
        # control and treatment arms of the same logical pair share pair_id
        assert _rec("lev", cov, 1, CTRL).pair_id == _rec("lev", cov, 1, TRT).pair_id

    def test_pair_id_differs_by_seed(self):
        cov = {"n_agents": 22}
        assert _rec("lev", cov, 1, CTRL).pair_id != _rec("lev", cov, 2, CTRL).pair_id

    def test_arm_id_differs_by_treatment(self):
        assert CTRL != TRT


class TestAggregatePairs:
    def test_valid_pair(self):
        r = aggregate_pairs(
            [
                _rec("lev", {"n": 22}, 1, CTRL),
                _rec("lev", {"n": 22}, 1, TRT),
            ],
            registered_arm_ids=REG,
        )
        assert len(r.valid_pairs) == 1
        assert len(r.single_side_missing) == 0

    def test_multi_seed_valid_pairs(self):
        records = []
        for seed in (1, 2, 3):
            records.append(_rec("lev", {"n": 22}, seed, CTRL))
            records.append(_rec("lev", {"n": 22}, seed, TRT))
        r = aggregate_pairs(records, registered_arm_ids=REG)
        assert len(r.valid_pairs) == 3

    def test_duplicate_pair_rejected(self):
        r = aggregate_pairs(
            [
                _rec("lev", {"n": 22}, 1, CTRL),
                _rec("lev", {"n": 22}, 1, CTRL),
                _rec("lev", {"n": 22}, 1, TRT),
            ],
            registered_arm_ids=REG,
        )
        assert len(r.duplicates_rejected) == 1
        assert len(r.valid_pairs) == 0

    def test_unknown_arm_rejected(self):
        r = aggregate_pairs(
            [_rec("lev", {"n": 22}, 1, "unknown_arm")],
            registered_arm_ids=REG,
        )
        assert len(r.unknown_arm_rejected) == 1

    def test_single_side_technical_invalid(self):
        # both arms explicitly accounted for: valid + invalid both recorded,
        # never silently dropped
        r = aggregate_pairs(
            [
                _rec("lev", {"n": 22}, 1, CTRL),
                _rec("lev", {"n": 22}, 1, TRT, category=RunCategory.TECHNICAL_INVALID),
            ],
            registered_arm_ids=REG,
        )
        assert len(r.valid_pairs) == 0
        assert len(r.single_side_missing) == 2  # both arms accounted
        assert {rec.category for _, rec in r.single_side_missing} == {
            RunCategory.COMPLETED,
            RunCategory.TECHNICAL_INVALID,
        }

    def test_missing_pair_reported(self):
        # only control arm present for seed 2 -> missing pair, and the present
        # record is explicitly accounted for
        r = aggregate_pairs(
            [
                _rec("lev", {"n": 22}, 1, CTRL),
                _rec("lev", {"n": 22}, 1, TRT),
                _rec("lev", {"n": 22}, 2, CTRL),
            ],
            registered_arm_ids=REG,
        )
        assert len(r.valid_pairs) == 1
        assert len(r.missing_pairs) == 1
        assert len(r.single_side_missing) == 1  # the lone present arm

    def test_endpoint_pair_not_dropped(self):
        # endpoint vs non-endpoint: both valid categories -> still a valid pair
        # (T602 two-part split handles the endpoint distinction downstream)
        r = aggregate_pairs(
            [
                _rec("lev", {"n": 22}, 1, CTRL),
                _rec("lev", {"n": 22}, 1, TRT, category=RunCategory.ECONOMIC_ENDPOINT),
            ],
            registered_arm_ids=REG,
        )
        assert len(r.valid_pairs) == 1
