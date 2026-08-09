"""T206 (方法论 §10.1): market-sufficiency gate tests.

Positive + negative + multi-record cases per CLAUDE.md: a sufficiency matrix
passes, and each failing condition is reported.
"""

from __future__ import annotations

from market_game_sim.robustness.market_sufficiency import market_sufficient


def _matrix(fill_ratio_ok=True, verdicts=None, names=None):
    verdicts = verdicts if verdicts is not None else {"fat_tails": "PASS"}
    names = names if names is not None else list(verdicts)
    return {
        "fill_ratio_ok": fill_ratio_ok,
        "items": {n: {"name": n, "verdict": verdicts.get(n, "NOT_APPLICABLE")} for n in names},
    }


class TestMarketSufficient:
    def test_passes_when_ok(self):
        s = market_sufficient(_matrix(fill_ratio_ok=True, verdicts={"fat_tails": "PASS"}))
        assert s.passed
        assert s.reasons == []

    def test_fill_ratio_not_ok_fails(self):
        s = market_sufficient(_matrix(fill_ratio_ok=False, verdicts={"fat_tails": "PASS"}))
        assert not s.passed
        assert any("fill_ratio_ok" in r for r in s.reasons)

    def test_no_informative_feature_fails(self):
        s = market_sufficient(
            _matrix(fill_ratio_ok=True, verdicts={}, names=["fat_tails", "reversion"])
        )
        assert not s.passed
        assert any("no informative" in r for r in s.reasons)

    def test_fail_verdict_fails(self):
        s = market_sufficient(
            _matrix(fill_ratio_ok=True, verdicts={"fat_tails": "FAIL", "reversion": "PASS"})
        )
        assert not s.passed
        assert any("FAILED" in r for r in s.reasons)

    def test_multi_feature_pass(self):
        s = market_sufficient(
            _matrix(
                fill_ratio_ok=True,
                verdicts={"fat_tails": "PASS", "reversion": "PASS", "book": "PASS"},
            )
        )
        assert s.passed
