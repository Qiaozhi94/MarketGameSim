"""T212: evidence-class + cross-family permission guard (AC-008 / FR-026).

Covers (FR-026 / IR-502 / SC-011):
- BENCHMARK/STRESS evidence cannot claim formal-research (rejected);
- SPONTANEOUS may produce all three classes, but formal-research requires
  the preregistration flag;
- unknown classes and unknown families fail closed;
- cross-family aggregation is rejected (no implicit downgrade).
"""

from __future__ import annotations

import pytest

from market_game_sim.evidence.evidence_guard import (
    EvidenceClass,
    EvidenceClassError,
    guard_aggregation,
    guard_evidence_class,
    guard_formal_research,
)


def test_benchmark_only_engineering_demonstration():
    assert guard_evidence_class("BENCHMARK", "engineering-demonstration") == (
        EvidenceClass.ENGINEERING_DEMONSTRATION
    )
    with pytest.raises(EvidenceClassError, match="not allowed"):
        guard_evidence_class("BENCHMARK", "formal-research")
    with pytest.raises(EvidenceClassError, match="not allowed"):
        guard_evidence_class("BENCHMARK", "experiment-preview")


def test_stress_only_engineering_demonstration():
    assert guard_evidence_class("STRESS", "engineering-demonstration")
    with pytest.raises(EvidenceClassError, match="not allowed"):
        guard_evidence_class("STRESS", "formal-research")


def test_spontaneous_allows_all_classes():
    for cls in ("engineering-demonstration", "experiment-preview", "formal-research"):
        assert guard_evidence_class("SPONTANEOUS", cls)


def test_formal_research_requires_preregistration():
    with pytest.raises(EvidenceClassError, match="preregistration"):
        guard_formal_research("SPONTANEOUS", "formal-research", preregistered=False)
    # No exception when preregistered.
    guard_formal_research("SPONTANEOUS", "formal-research", preregistered=True)


def test_formal_research_rejected_for_benchmark_even_if_preregistered():
    with pytest.raises(EvidenceClassError, match="not allowed"):
        guard_formal_research("BENCHMARK", "formal-research", preregistered=True)


def test_unknown_evidence_class_fails_closed():
    with pytest.raises(EvidenceClassError, match="not a known evidence class"):
        guard_evidence_class("SPONTANEOUS", "research-notes")


def test_unknown_family_fails_closed():
    with pytest.raises(EvidenceClassError, match="not a known run family"):
        guard_evidence_class("MYSTERY", "engineering-demonstration")


def test_aggregation_same_family_passes():
    guard_aggregation(
        [
            ("SPONTANEOUS", "engineering-demonstration"),
            ("SPONTANEOUS", "experiment-preview"),
        ]
    )


def test_aggregation_rejects_cross_family_batch():
    with pytest.raises(EvidenceClassError, match="cross-family"):
        guard_aggregation(
            [
                ("SPONTANEOUS", "engineering-demonstration"),
                ("BENCHMARK", "engineering-demonstration"),
            ]
        )
