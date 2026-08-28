"""T212: evidence-class + cross-family permission guard (AC-008 / FR-026).

Covers (FR-026 / IR-502 / SC-011):
- BENCHMARK/STRESS evidence cannot claim formal-research (rejected);
- SPONTANEOUS may produce all three classes, but formal-research requires
  the preregistration flag;
- unknown classes and unknown families fail closed;
- cross-family aggregation is rejected (no implicit downgrade).
"""

from __future__ import annotations

import json

import pytest

from market_game_sim.evidence.evidence_guard import (
    EvidenceClass,
    EvidenceClassError,
    FrozenPreregistrationReference,
    guard_aggregation,
    guard_evidence_class,
    guard_formal_research,
)


def _frozen_ref(tmp_path, *, control_hash="c", treatment_hash="t", seeds=(1,)):
    path = tmp_path / "prereg.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "FROZEN",
                "preregistration_id": "prereg-1",
                "control_config_hash": control_hash,
                "treatment_config_hash": treatment_hash,
                "seed_plan": {"n_seeds": len(seeds), "seeds": list(seeds)},
            }
        ),
        encoding="utf-8",
    )
    return FrozenPreregistrationReference.from_artifact(path)


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


def test_formal_research_requires_preregistration(tmp_path):
    with pytest.raises(EvidenceClassError, match="preregistration"):
        guard_formal_research("SPONTANEOUS", "formal-research", preregistration=None)
    ref = _frozen_ref(tmp_path)
    guard_formal_research(
        "SPONTANEOUS",
        "formal-research",
        preregistration=ref,
        control_config_hash="c",
        treatment_config_hash="t",
        seeds=[1],
    )


def test_formal_research_rejects_bare_bool():
    """R018-C011 (Round 7): a bare True is not a preregistration reference --
    only a traceable frozen preregistration id/digest may authorize a formal
    conclusion."""
    with pytest.raises(EvidenceClassError, match="preregistration"):
        guard_formal_research("SPONTANEOUS", "formal-research", preregistration=True)


def test_formal_research_rejects_arbitrary_string():
    with pytest.raises(EvidenceClassError, match="resolved"):
        guard_formal_research("SPONTANEOUS", "formal-research", preregistration="prereg-1")


def test_formal_research_rejects_drifted_artifact(tmp_path):
    ref = _frozen_ref(tmp_path)
    ref.artifact_path.write_text("{}", encoding="utf-8")
    with pytest.raises(EvidenceClassError, match="digest drifted"):
        guard_formal_research(
            "SPONTANEOUS",
            "formal-research",
            preregistration=ref,
            control_config_hash="c",
            treatment_config_hash="t",
            seeds=[1],
        )


def test_preregistration_artifact_root_must_be_object(tmp_path):
    path = tmp_path / "array.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(EvidenceClassError, match="root must be an object"):
        FrozenPreregistrationReference.from_artifact(path)


def test_formal_research_rejected_for_benchmark_even_if_preregistered(tmp_path):
    with pytest.raises(EvidenceClassError, match="not allowed"):
        guard_formal_research("BENCHMARK", "formal-research", preregistration=_frozen_ref(tmp_path))


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
