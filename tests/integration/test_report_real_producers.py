"""Real producer -> manifest -> report E2E (review round-5, Critical).

Proves the report layer consumes artifacts produced by the REAL 0.1.2/0.1.3
producers (via the artifact_export adapter), not hand-fabricated fixtures:
run_one + run_paired on real configs -> adapter -> JSON artifact files ->
manifest with real blake2b hashes -> build_report -> success + byte-identical
consumption + cross-artifact run_id consistency.
"""

from __future__ import annotations

import json

from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.experiment.config import ExperimentConfig
from market_game_sim.experiment.runner import run_paired
from market_game_sim.metrics import artifact_export as export
from market_game_sim.report.generate import build_report
from market_game_sim.report.manifest import load_registry

_REGISTRY = load_registry()
_REGISTRY_IDS = sorted(_REGISTRY["artifacts"].keys())


def _mm_spec() -> AgentSpec:
    return AgentSpec(
        agent_id="mm-0",
        role="inventory_market_maker",
        observe_interval_ns=100_000_000,
        latency_ns=5_000_000,
        is_market_maker=True,
        half_spread_ticks=5,
        quote_size=10_000,
        max_inventory=100_000,
        inventory_skew_k_bp=10_000,
    )


def _belief_spec(leverage_tier: int) -> AgentSpec:
    return AgentSpec(
        agent_id="agent-0",
        role="retail",
        observe_interval_ns=500_000_000,
        latency_ns=50_000_000,
        leverage_tier=leverage_tier,
        aggressiveness_bp=10_000,
        max_order_qty=5_000,
    )


def _frozen_evidence() -> dict:
    """The FROZEN 0.1.3 exit evidence (docs/experiments) -- the robustness
    artifacts must be built from this, not from a fresh 0.1.4 re-run."""
    import pathlib

    p = (
        pathlib.Path(__file__).resolve().parents[2]
        / "docs"
        / "experiments"
        / "0.1.3-exit-evidence.json"
    )
    return json.loads(p.read_text(encoding="utf-8"))


def _paired_single() -> tuple:
    """One real paired experiment for the 0.1.2 run artifacts (market_metrics
    etc.); the robustness artifacts come from the FROZEN 0.1.3 evidence."""
    control = ExperimentConfig(
        seed=1,
        max_transactions=200,
        agent_specs=[_mm_spec(), _belief_spec(leverage_tier=10)],
        agent_signals={"agent-0": 10_000},
    )
    treatment = ExperimentConfig(
        seed=1,
        max_transactions=200,
        agent_specs=[_mm_spec(), _belief_spec(leverage_tier=20)],
        agent_signals={"agent-0": 10_000},
    )
    c_results, _t_results, comparison = run_paired(control, treatment, seeds=[1])
    return c_results[0], comparison


def test_report_consumes_real_producer_artifacts(tmp_path):
    """The report accepts and byte-identically consumes artifacts produced by
    the real 0.1.2/0.1.3 producers via the PRODUCTION write entry
    (artifact_export.write_artifacts), not a test helper."""
    run, comparison = _paired_single()
    evidence = _frozen_evidence()
    out_dir = tmp_path / "out"
    manifest_path, artifacts = export.write_artifacts(
        run,
        comparison,
        out_dir,
        evidence=evidence,
        structure_desc="2xMM+1xretail",
        param_range_desc="leverage_tier treatment vs control",
    )

    result = build_report(manifest_path, out_dir)
    assert result.success is True, result.report.get("failure")
    assert result.report["failure"] is None
    assert result.report["run_id"] == artifacts["liquidation_metrics"]["run_id"]
    for aid in (
        "market_metrics",
        "agent_metrics",
        "liquidation_metrics",
        "pnl_bridge",
        "sample_classification",
        "effect_sizes",
        "robustness_effects",
    ):
        assert result.report["metrics"][aid] == artifacts[aid], f"{aid} not byte-identical"
    assert result.report["conditional_conclusion"] == artifacts["conditional_conclusion"]
    assert result.report["robustness_conclusion"] == artifacts["robustness_conclusion"]
    assert result.report["negative_results"] == artifacts["negative_results"]


def test_real_artifacts_are_nonempty_and_registry_valid(tmp_path):
    """Sanity: the real producer chain produces non-empty, registry-valid
    artifacts (the E2E's accepted side must actually exercise the pipeline)."""
    run, comparison = _paired_single()
    evidence = _frozen_evidence()
    artifacts = export.build_artifacts(
        run,
        comparison,
        evidence=evidence,
        structure_desc="2xMM+1xretail",
        param_range_desc="leverage_tier treatment vs control",
    )
    assert artifacts["market_metrics"], "market_metrics rows must be non-empty"
    assert artifacts["agent_metrics"], "agent_metrics rows must be non-empty"
    assert artifacts["pnl_bridge"], "pnl_bridge rows must be non-empty"
    assert artifacts["robustness_effects"], "robustness_effects rows must be non-empty"
    for aid in _REGISTRY_IDS:
        spec = _REGISTRY["artifacts"][aid]
        assert artifacts[aid] is not None, f"{aid} missing"
        assert spec["format"] == "json", f"{aid} must be declared json"


def test_negative_results_pass_real_t606_validation(tmp_path):
    """Round-7 Critical: every negative_results class emitted by the adapter
    must pass the REAL T606 fail-closed validation (closed enum), so no
    self-created result_class can ever be written."""
    from market_game_sim.robustness.negative_results import NegativeResult, NegativeResultReport

    run, comparison = _paired_single()
    evidence = _frozen_evidence()
    artifacts = export.build_artifacts(
        run,
        comparison,
        evidence=evidence,
        structure_desc="2xMM+1xretail",
        param_range_desc="leverage_tier treatment vs control",
    )
    nr = NegativeResultReport(
        [
            NegativeResult(
                result_class=r["result_class"],
                description=r["description"],
                machine_readable=r["machine_readable"],
            )
            for r in artifacts["negative_results"]["results"]
        ]
    )
    nr.validate()  # real T606 gate: raises on any unknown class


# --- Round-8 regression tests: T606 semantic classification ---


def _cell(family, mapping, direction, significant, eff=1.0):
    from market_game_sim.robustness.cross_matrix import CrossCell

    return CrossCell(
        family_id=family,
        mapping_id=mapping,
        effect_direction=direction,
        significant=significant,
        effect_size=eff,
        ci_low=0.1 if direction > 0 else -1.0,
        ci_high=1.0 if direction > 0 else -0.1,
    )


def test_vanish_maps_to_effect_vanishes_under_alternative_mapping():
    """Round-8: [significant +, non-significant 0] across mappings is a VANISH
    -> effect_vanishes_under_alternative_mapping, not narrow_parameter_region."""
    cells = [
        _cell("belief_family", "linear", 1, True),
        _cell("belief_family", "threshold", 0, False),
        _cell("signal_family", "linear", 1, True),
        _cell("signal_family", "threshold", 1, True),
    ]
    art = export.negative_results_artifact(
        cells, ["belief_family", "signal_family"], ["linear", "threshold"]
    )
    assert [r["result_class"] for r in art["results"]] == [
        "effect_vanishes_under_alternative_mapping"
    ]


def test_reversal_emits_no_negative_result():
    """Round-8: [significant +, significant -] is a REVERSAL -- a T105
    dependency boundary, NOT a T606 negative-result class."""
    cells = [
        _cell("belief_family", "linear", 1, True),
        _cell("belief_family", "threshold", -1, True),
        _cell("signal_family", "linear", 1, True),
        _cell("signal_family", "threshold", 1, True),
    ]
    art = export.negative_results_artifact(
        cells, ["belief_family", "signal_family"], ["linear", "threshold"]
    )
    assert art["results"] == []


def test_family_dependence_emits_no_negative_result():
    """Round-9: effect holds in belief_family but not signal_family (model-FAMILY
    dependence, no mapping-dimension vanish) is a T105 dependency boundary --
    it must NOT be classified as narrow_parameter_region (the reviewer's
    exact repro FAMILY_DEPENDENCE_CLASSIFIED_AS narrow)."""
    cells = [
        _cell("belief_family", "linear", 1, True),
        _cell("belief_family", "threshold", 1, True),
        _cell("signal_family", "linear", 0, False),
        _cell("signal_family", "threshold", 0, False),
    ]
    art = export.negative_results_artifact(
        cells, ["belief_family", "signal_family"], ["linear", "threshold"]
    )
    assert art["results"] == []


def test_narrow_region_requires_parameter_scan():
    """Round-9/10: narrow_parameter_region is emitted ONLY from the frozen
    parameter-scan boundary evidence, and its machine_readable carries the
    REAL frozen fields (round-10 review: the real boundary axis is the string
    ``"700"``, not a self-made fixture)."""
    evidence = _frozen_evidence()
    scan = evidence["E2_parameter_scan"]
    cells = [
        _cell("belief_family", "linear", 1, True),
        _cell("belief_family", "threshold", 1, True),
        _cell("signal_family", "linear", 1, True),
        _cell("signal_family", "threshold", 1, True),
    ]
    art = export.negative_results_artifact(
        cells, ["belief_family", "signal_family"], ["linear", "threshold"], parameter_scan=scan
    )
    assert [r["result_class"] for r in art["results"]] == ["narrow_parameter_region"]
    # the frozen boundary's own fields, verbatim
    assert art["results"][0]["machine_readable"]["axis"] == scan["boundary"]["axis"]
    assert (
        art["results"][0]["machine_readable"]["crossing_interval"]
        == scan["boundary"]["crossing_interval"]
    )


def test_frozen_evidence_self_consistent_and_conclusion_verbatim():
    """Round-10: the frozen 0.1.3 E1 report equals recomputation from its own
    cells (verify_frozen_evidence passes), and the report's robustness_
    conclusion consumes the frozen conclusion VERBATIM (依赖边界), never the
    recomputed 同向成立."""
    evidence = _frozen_evidence()
    export.verify_frozen_evidence(evidence)  # must not raise

    run, comparison = _paired_single()
    artifacts = export.build_artifacts(
        run,
        comparison,
        evidence=evidence,
        structure_desc="2xMM+1xretail",
        param_range_desc="leverage_tier treatment vs control",
    )
    frozen_conclusion = evidence["E1_cross_matrix"]["report"]["conclusion"]
    # T604 text embeds the frozen cross_verdict
    assert frozen_conclusion in artifacts["robustness_conclusion"]["text"]
    # the frozen conclusion must NOT be silently flipped to 同向成立
    assert artifacts["robustness_conclusion"]["elements"]["cross_verdict"] == frozen_conclusion


def test_frozen_evidence_gate_rejects_inconsistent_cells():
    """Round-10 rejected: tampering with a cell's effect_direction so it no
    longer reproduces the frozen report must make verify_frozen_evidence
    raise (the gate is the self-consistency contract)."""
    import copy

    import pytest

    evidence = _frozen_evidence()
    bad = copy.deepcopy(evidence)
    bad["E1_cross_matrix"]["cells"][2]["effect_direction"] = 1  # signal cell flipped
    with pytest.raises(ValueError, match="self-inconsistent"):
        export.verify_frozen_evidence(bad)
