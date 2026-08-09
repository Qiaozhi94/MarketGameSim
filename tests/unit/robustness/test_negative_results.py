"""T606 (0.1.3 §4): negative-result report tests.

Positive + negative + multi-record cases per CLAUDE.md: first-class negative
results validate, and missing body/machine-readable conclusion is rejected.
"""

from __future__ import annotations

import pytest

from market_game_sim.robustness.negative_results import (
    NegativeResult,
    NegativeResultError,
    NegativeResultReport,
)


def _result(cls="narrow_parameter_region", desc="effect only in a narrow region", machine=None):
    return NegativeResult(
        result_class=cls,
        description=desc,
        machine_readable=machine if machine is not None else {"region": (400, 500), "effect": 0.1},
    )


class TestNegativeResultReport:
    def test_all_three_classes_valid(self):
        report = NegativeResultReport(
            results=[
                _result("narrow_parameter_region"),
                _result("effect_vanishes_under_alternative_mapping", "threshold mapping kills it"),
                _result("crash_without_leverage", "crash also occurs without leverage"),
            ]
        )
        report.validate()

    def test_missing_description_rejected(self):
        r = _result(desc="")
        with pytest.raises(NegativeResultError, match="no body description"):
            NegativeResultReport(results=[r]).validate()

    def test_missing_machine_readable_rejected(self):
        r = _result(machine={})
        with pytest.raises(NegativeResultError, match="missing machine-readable"):
            NegativeResultReport(results=[r]).validate()

    def test_unknown_class_rejected(self):
        r = _result(cls="made_up")
        with pytest.raises(NegativeResultError, match="unknown negative-result class"):
            NegativeResultReport(results=[r]).validate()

    def test_as_dict(self):
        report = NegativeResultReport(results=[_result()])
        d = report.as_dict()
        assert d["results"][0]["result_class"] == "narrow_parameter_region"
