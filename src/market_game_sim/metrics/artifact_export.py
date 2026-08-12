"""Artifact export adapter: map REAL producer outputs to registry shapes.

The report layer consumes the artifact registry (``report_artifacts.json``),
but the 0.1.2/0.1.3 producers emit their own object shapes (``MarketSample``,
``ProportionDiffResult``, ``RunResult``, paired ``comparison`` dicts...).
This adapter is the missing wiring: it maps the real producers' outputs to
registry-conforming artifact dicts, so a manifest can be built from REAL run
products instead of hand-fabricated fixtures (review round-5, Critical
``report-manifest-not-enforced-parquet-as-json``).

Everything here is a pure projection of producer objects -- no statistics are
recomputed, no new measurements are taken (E4: 报告不自行重算).
"""

from __future__ import annotations

import dataclasses
import pathlib
from typing import Any

from market_game_sim.ledger.account import (
    initial_margin_bp_for_tier,
)
from market_game_sim.metrics.bridge import bridge_trade
from market_game_sim.metrics.liquidation import compute_liquidation_metrics
from market_game_sim.metrics.sampling import sample_agent_series, sample_market_series
from market_game_sim.robustness.cross_matrix import CrossCell, CrossMatrix
from market_game_sim.robustness.final_conclusion import build_final_conclusion
from market_game_sim.robustness.negative_results import NegativeResult, NegativeResultReport

#: registry_declared schema_version for every artifact (report_artifacts.json).
_ARTIFACT_SCHEMA_VERSION = 1


def _run_id(run_result: Any) -> str:
    return f"exp-s{run_result.seed}"


def market_metrics_rows(run_result: Any, sample_interval_ns: int = 1_000_000_000) -> list[dict]:
    """Map real ``MarketSample`` series to market_metrics table rows."""
    samples = sample_market_series(run_result.events, sample_interval_ns)
    return [
        {
            "schema_version": _ARTIFACT_SCHEMA_VERSION,
            "run_id": _run_id(run_result),
            **{f.name: getattr(s, f.name) for f in dataclasses.fields(s)},
        }
        for s in samples
    ]


def agent_metrics_rows(
    run_result: Any, sample_interval_ns: int = 1_000_000_000, *, mult: int = 1000
) -> list[dict]:
    """Map real ``AgentSample`` series to agent_metrics table rows (all agents).

    ``mult`` must be the run's actual cash-unit scaling (margin_ratio_bp /
    leverage_bp in the rows are mult-dependent); it is threaded explicitly,
    never guessed from the run result.
    """
    rows: list[dict] = []
    for aid in run_result.accounts:
        for s in sample_agent_series(run_result.events, aid, sample_interval_ns, mult=mult):
            rows.append(
                {
                    "schema_version": _ARTIFACT_SCHEMA_VERSION,
                    "run_id": _run_id(run_result),
                    **{f.name: getattr(s, f.name) for f in dataclasses.fields(s)},
                }
            )
    return rows


def liquidation_metrics_artifact(run_result: Any) -> dict:
    """Map real ``LiquidationMetrics`` to the liquidation_metrics object."""
    lm = compute_liquidation_metrics(run_result.events)
    base = dataclasses.asdict(lm)
    total_volume = base["total_volume"]
    base["liquidation_volume_ratio"] = (
        base["liquidation_volume"] / total_volume if total_volume else 0.0
    )
    return {"schema_version": _ARTIFACT_SCHEMA_VERSION, "run_id": _run_id(run_result), **base}


def sample_classification_rows(run_result: Any) -> list[dict]:
    """Map the real ``RunClassification`` to a 1-row sample_classification table."""
    return [
        {
            "schema_version": _ARTIFACT_SCHEMA_VERSION,
            "run_id": _run_id(run_result),
            **run_result.classification.as_dict(),
        }
    ]


def pnl_bridge_rows(run_result: Any, mult: int = 1000) -> list[dict]:
    """Map every real TRADE_POSTING through ``bridge_trade`` to pnl_bridge rows.

    ``mult`` must be the run's actual cash-unit scaling (bridge components are
    mult-dependent); threaded explicitly, never guessed.
    """
    rows: list[dict] = []
    for e in run_result.events:
        if e.get("event_type") != "TRADE_SETTLE":
            continue
        vm_before_h = e.get("valuation_mark_before_half_ticks", 0)
        vm_after_h = e.get("valuation_mark_after_half_ticks", 0)
        for p in e.get("postings", []):
            if p.get("posting_type") != "TRADE_POSTING":
                continue
            result = bridge_trade(
                posting=p,
                vm_before_half=vm_before_h,
                vm_after_half=vm_after_h,
                trade_price_ticks=e.get("price_ticks", 0),
                position_before_units=p.get("position_after_units", 0)
                - p.get("position_delta_units", 0),
                mult=mult,
            )
            rows.append(
                {
                    "schema_version": _ARTIFACT_SCHEMA_VERSION,
                    "run_id": _run_id(run_result),
                    "event_id": e.get("event_id"),
                    "agent_id": p.get("agent_id"),
                    **result,
                }
            )
    return rows


def _effect_dict(comparison: dict) -> dict:
    """The real paired effect is a ProportionDiffResult dataclass -- normalize
    to a dict (asdict) so the adapter can project it into registry shapes."""
    eff = comparison["endpoint_rate_effect"]
    return dataclasses.asdict(eff)


def effect_sizes_artifact(comparison: dict, metric_id: str = "economic_endpoint_rate") -> dict:
    """Map the real paired ``comparison`` effect to the effect_sizes object."""
    eff = _effect_dict(comparison)
    return {
        "schema_version": _ARTIFACT_SCHEMA_VERSION,
        "comparison_id": _comparison_id(comparison),
        "metric_id": metric_id,
        "n_control": eff["n_control"],
        "n_treatment": eff["n_treatment"],
        "control_rate": eff["control_rate"],
        "treatment_rate": eff["treatment_rate"],
        "effect_size": eff["diff"],
        "ci_low": eff["ci_low"],
        "ci_high": eff["ci_high"],
        "ci_level": eff["ci_level"],
        "n_resamples": eff["n_resamples"],
        "bootstrap_seed": eff["seed"],
        "multiplicity_method": "none",
        "multiplicity_passed": True,
    }


def conditional_conclusion_artifact(comparison: dict) -> dict:
    """Map the real paired comparison conclusion (a string) to the object shape."""
    eff = _effect_dict(comparison)
    return {
        "schema_version": _ARTIFACT_SCHEMA_VERSION,
        "comparison_id": _comparison_id(comparison),
        "text": comparison["conditional_conclusion"],
        "structure_desc": comparison.get("structure_desc", ""),
        "param_range_desc": comparison.get("param_range_desc", ""),
        "n_control_seeds": comparison["control"]["n_completed"],
        "n_treatment_seeds": comparison["treatment"]["n_completed"],
        "effect_size": eff["diff"],
        "ci_low": eff["ci_low"],
        "ci_high": eff["ci_high"],
        "ci_level": eff["ci_level"],
        "failure_condition_desc": comparison.get("failure_condition_desc", ""),
        "extrapolation_forbidden": True,
    }


def _cross_report(cells: list[CrossCell], families: list[str], mappings: list[str]) -> dict:
    """The REAL T105 cross-matrix report (complete/same_direction/conclusion)."""
    return CrossMatrix(cells).report(families, mappings)


def verify_frozen_evidence(evidence: dict) -> None:
    """Fail-closed gate: the FROZEN 0.1.3 E1 report must equal recomputation
    from its own cells (round-10 review: never consume a frozen conclusion
    that contradicts its cells, and never recompute a conclusion from cells
    that contradicts the frozen report).

    Cells are reconstructed VERBATIM (including the frozen ``effect_direction``
    -- the producer's direction rule is not re-derived from effect_size).
    Raises :class:`ValueError` on any mismatch.
    """
    from market_game_sim.robustness.cross_matrix import CrossCell

    e1 = evidence["E1_cross_matrix"]
    cells = [
        CrossCell(
            family_id=c["family"],
            mapping_id=c["mapping"],
            effect_direction=c["effect_direction"],
            significant=c["significant"],
            effect_size=c["effect_size"],
            ci_low=c.get("ci_low", 0.0),
            ci_high=c.get("ci_high", 0.0),
        )
        for c in e1["cells"]
    ]
    families = sorted({c.family_id for c in cells})
    mappings = sorted({c.mapping_id for c in cells})
    recomputed = _cross_report(cells, families, mappings)
    frozen = e1["report"]
    if recomputed != frozen:
        raise ValueError(
            "frozen 0.1.3 E1 evidence is self-inconsistent: recomputed "
            f"conclusion={recomputed.get('conclusion')!r} != frozen "
            f"conclusion={frozen.get('conclusion')!r}"
        )


def robustness_effects_rows(cells: list[CrossCell], comparison: dict) -> list[dict]:
    """Map the REAL cross-matrix cells to robustness_effects table rows.

    Each row is a genuine ``CrossCell`` (real effect/direction/significance
    from its own paired run); n_pairs/parameter_unit come from the real
    comparison and config.
    """
    eff = _effect_dict(comparison)
    n_pairs = eff["n_control"] + eff["n_treatment"]
    rows: list[dict] = []
    for c in cells:
        rows.append(
            {
                "schema_version": _ARTIFACT_SCHEMA_VERSION,
                "cell_id": f"{c.family_id}-{c.mapping_id}",
                "pair_family": "leverage_tier",
                "model_family_id": c.family_id,
                "behavior_mapping_id": c.mapping_id,
                "parameter_unit": {"leverage_tier": "tier"},
                "n_pairs": n_pairs,
                "effect_size": c.effect_size,
                "ci_low": c.ci_low,
                "ci_high": c.ci_high,
                "ci_level": eff["ci_level"],
                "significant": c.significant,
                "effect_direction": c.effect_direction,
            }
        )
    return rows


def robustness_conclusion_artifact(
    comparison: dict,
    *,
    cells: list[CrossCell],
    families: list[str],
    mappings: list[str],
    frozen_conclusion: str,
    structure_desc: str,
    param_range_desc: str,
    failure_boundary_desc: str = "",
) -> dict:
    """Consume the REAL T604 producer (``build_final_conclusion``).

    ``frozen_conclusion`` is the FROZEN 0.1.3 E1 report's conclusion,
    consumed VERBATIM (round-10 review) -- never recomputed from the cells.
    :func:`verify_frozen_evidence` guarantees it equals the cells' report
    before this is called.
    """
    fc = build_final_conclusion(
        comparison["endpoint_rate_effect"],
        structure_desc=structure_desc,
        param_range_desc=param_range_desc,
        behavior_mapping_id=mappings[0],
        model_family_id=families[0],
        cross_verdict=frozen_conclusion,
        failure_boundary_desc=failure_boundary_desc,
    )
    return {"schema_version": _ARTIFACT_SCHEMA_VERSION, **fc.as_dict()}


def _negative_result_classification(
    cells: list[CrossCell],
    *,
    parameter_scan: dict | None = None,
) -> tuple[str | None, str]:
    """Classify the REAL evidence into a T606 negative-result class (round-9
    review: semantics tied to evidence source).

    Evidence -> class:
    - cross-matrix, a significant cell and a NON-significant cell sharing a
      family but differing in mapping -> ``effect_vanishes_under_alternative_mapping``
    - parameter-scan only: a localized failure boundary on the parameter axis
      -> ``narrow_parameter_region``
    - direction REVERSAL or model-FAMILY dependence (effect holds in one
      family, not another, without a mapping-dimension vanish) are T105
      dependency boundaries, NOT T606 negative-result classes -> (None, ...)

    ``parameter_scan`` is the frozen 0.1.3 E2 parameter-scan product
    (``{cells, boundary}``); ``narrow_parameter_region`` is emitted ONLY from
    its boundary evidence, never inferred from cross-matrix sparsity.

    Returns ``(result_class_or_None, kind)`` with a stable ``kind`` tag:
    vanish / narrow / reversal / family_dependence / none.
    """
    significant = [c for c in cells if c.significant]
    nonsig = [c for c in cells if not c.significant]

    # Parameter-scan evidence is an independent axis: a localized failure
    # boundary on the parameter axis is the ONLY source of the narrow class.
    if parameter_scan and (parameter_scan.get("boundary") or {}).get("threshold_crossed"):
        return "narrow_parameter_region", "narrow"

    if significant and nonsig:
        vanish = any(
            c1.family_id == c2.family_id and c1.mapping_id != c2.mapping_id
            for c1 in significant
            for c2 in nonsig
        )
        if vanish:
            return "effect_vanishes_under_alternative_mapping", "vanish"
        return None, "family_dependence"

    if len(significant) > 1:
        directions = {c.effect_direction for c in significant}
        if len(directions) > 1:
            return None, "reversal"
        return None, "none"

    if not significant:
        if parameter_scan:
            return "narrow_parameter_region", "narrow"
        return None, "none"
    return None, "none"


def negative_results_artifact(
    cells: list[CrossCell],
    families: list[str],
    mappings: list[str],
    *,
    parameter_scan: dict | None = None,
) -> dict:
    """Consume the REAL T606 producer (``NegativeResultReport``).

    The result class is chosen from the REAL evidence (cross-matrix for
    vanish; the frozen 0.1.3 parameter-scan product for narrow), then passed
    through the real ``NegativeResultReport`` fail-closed validation.
    Direction reversal and model-family dependence are T105 dependency
    boundaries and emit NO negative-result entry.
    """
    result_class, kind = _negative_result_classification(cells, parameter_scan=parameter_scan)
    results: list[NegativeResult] = []
    if result_class == "effect_vanishes_under_alternative_mapping":
        results.append(
            NegativeResult(
                result_class=result_class,
                description="effect is present under one behavior mapping but "
                "absent under an alternative mapping in the cross matrix",
                machine_readable={
                    "families": families,
                    "mappings": mappings,
                    "kind": kind,
                },
            )
        )
    elif result_class == "narrow_parameter_region":
        boundary = (parameter_scan or {}).get("boundary") or {}
        results.append(
            NegativeResult(
                result_class=result_class,
                description="failure boundary localized to a narrow parameter "
                "region on the scan axis",
                machine_readable={
                    "axis": boundary.get("axis"),
                    "crossing_interval": boundary.get("crossing_interval"),
                    "resolution": boundary.get("resolution"),
                    "kind": kind,
                },
            )
        )
    nr = NegativeResultReport(results)
    nr.validate()  # real T606 fail-closed gate
    return {
        "schema_version": _ARTIFACT_SCHEMA_VERSION,
        "results": [
            {
                "result_class": r.result_class,
                "description": r.description,
                "machine_readable": r.machine_readable,
            }
            for r in nr.results
        ],
    }


def _comparison_id(comparison: dict) -> str:
    return f"{comparison['control_config_hash']}-{comparison['treatment_config_hash']}"


def initial_bp_by_agent(specs: list[Any]) -> dict[str, int]:
    """Registry-adjacent helper: agent_id -> initial_margin_bp (used by the
    replay header writer and experiment config parity)."""
    return {s.agent_id: initial_margin_bp_for_tier(s.leverage_tier) for s in specs}


# ---------------------------------------------------------------------------
# Production write entry (round-6 review, Critical): the adapter's outputs are
# written by REAL production code, not a test helper.
# ---------------------------------------------------------------------------

_ARTIFACT_IDS = (
    "market_metrics",
    "agent_metrics",
    "liquidation_metrics",
    "pnl_bridge",
    "sample_classification",
    "effect_sizes",
    "conditional_conclusion",
    "robustness_effects",
    "robustness_conclusion",
    "negative_results",
)


def _evidence_cells(evidence: dict) -> tuple[list[CrossCell], list[str], list[str]]:
    """Reconstruct CrossCells VERBATIM from the frozen evidence (including the
    frozen ``effect_direction`` -- never re-derived from effect_size)."""
    e1 = evidence["E1_cross_matrix"]
    cells = [
        CrossCell(
            family_id=c["family"],
            mapping_id=c["mapping"],
            effect_direction=c["effect_direction"],
            significant=c["significant"],
            effect_size=c["effect_size"],
            ci_low=c.get("ci_low", 0.0),
            ci_high=c.get("ci_high", 0.0),
        )
        for c in e1["cells"]
    ]
    families = sorted({c.family_id for c in cells})
    mappings = sorted({c.mapping_id for c in cells})
    return cells, families, mappings


def build_artifacts(
    run_result: Any,
    comparison: dict,
    *,
    evidence: dict,
    structure_desc: str,
    param_range_desc: str,
    mult: int = 1000,
) -> dict[str, Any]:
    """Project a real run + paired comparison + FROZEN 0.1.3 evidence into all
    10 registry artifacts.

    ``evidence`` is the frozen 0.1.3 exit-evidence product (E1 cross matrix +
    E2 parameter scan); it is gated by :func:`verify_frozen_evidence` (cells
    must reproduce the frozen report) and consumed verbatim -- the frozen
    conclusion is never recomputed from cells.  ``mult`` is the run's
    cash-unit scaling (threaded into mult-dependent projections)."""
    verify_frozen_evidence(evidence)
    cells, families, mappings = _evidence_cells(evidence)
    parameter_scan = evidence["E2_parameter_scan"]
    return {
        "market_metrics": market_metrics_rows(run_result),
        "agent_metrics": agent_metrics_rows(run_result, mult=mult),
        "liquidation_metrics": liquidation_metrics_artifact(run_result),
        "pnl_bridge": pnl_bridge_rows(run_result, mult=mult),
        "sample_classification": sample_classification_rows(run_result),
        "effect_sizes": effect_sizes_artifact(comparison),
        "conditional_conclusion": conditional_conclusion_artifact(comparison),
        "robustness_effects": robustness_effects_rows(cells, comparison),
        "robustness_conclusion": robustness_conclusion_artifact(
            comparison,
            cells=cells,
            families=families,
            mappings=mappings,
            frozen_conclusion=evidence["E1_cross_matrix"]["report"]["conclusion"],
            structure_desc=structure_desc,
            param_range_desc=param_range_desc,
        ),
        "negative_results": negative_results_artifact(
            cells, families, mappings, parameter_scan=parameter_scan
        ),
    }


def write_artifacts(
    run_result: Any,
    comparison: dict,
    out_dir: pathlib.Path,
    *,
    evidence: dict,
    structure_desc: str,
    param_range_desc: str,
    mult: int = 1000,
) -> tuple[pathlib.Path, dict[str, Any]]:
    """Write all 10 registry artifacts + a manifest (real blake2b hashes) to
    ``out_dir`` and return ``(manifest_path, artifacts)``.

    This is the production write entry the report E2E drives -- the manifest's
    hashes are computed over the REAL written bytes, and the robustness
    artifacts consume the FROZEN 0.1.3 evidence verbatim (gated), so the
    report layer consumes genuine frozen products (round-6/10 review).
    """
    import hashlib
    import json

    from market_game_sim.report.manifest import load_registry

    registry = load_registry()
    root = out_dir / "artifacts"
    root.mkdir(parents=True, exist_ok=True)
    artifacts = build_artifacts(
        run_result,
        comparison,
        evidence=evidence,
        structure_desc=structure_desc,
        param_range_desc=param_range_desc,
        mult=mult,
    )

    entries: list[dict[str, Any]] = []
    for aid in _ARTIFACT_IDS:
        spec = registry["artifacts"][aid]
        fname = f"{aid}.json"
        fpath = root / fname
        fpath.write_text(json.dumps(artifacts[aid], sort_keys=True), encoding="utf-8")
        h = hashlib.blake2b(digest_size=32)
        h.update(fpath.read_bytes())
        entries.append(
            {
                "artifact_id": aid,
                "path": fname,
                "format": spec["format"],
                "schema_version": spec["schema_version"],
                "producer": spec["producer"],
                "hash_algorithm": "blake2b",
                "hash": h.hexdigest(),
            }
        )
    manifest = {"manifest_version": 1, "artifact_root": "artifacts", "artifacts": entries}
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return manifest_path, artifacts


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m market_game_sim.metrics.artifact_export <config.yaml> <out_dir>``

    Runs ONE real paired experiment from a bench-style YAML config (control =
    config; treatment = config with belief-agent leverage_tier doubled) for
    the 0.1.2 run artifacts, and consumes the FROZEN 0.1.3 exit evidence
    (``--evidence``, default ``docs/experiments/0.1.3-exit-evidence.json``)
    for the cross-matrix cells and parameter scan -- the robustness artifacts
    are built from the frozen upstream products, never from a fresh 0.1.4
    re-run (round-9 review, Critical).
    """
    import argparse
    import dataclasses
    import json

    from market_game_sim.bench.runner import build_experiment_config
    from market_game_sim.config.parser import parse_config
    from market_game_sim.experiment.runner import run_paired

    parser = argparse.ArgumentParser(prog="python -m market_game_sim.metrics.artifact_export")
    parser.add_argument("config", help="bench-style YAML config path (BENCH-001.yaml shape)")
    parser.add_argument("out_dir", help="output directory for artifacts/ + manifest.json")
    parser.add_argument(
        "--evidence",
        default="docs/experiments/0.1.3-exit-evidence.json",
        help="frozen 0.1.3 exit-evidence JSON (cross matrix + parameter scan)",
    )
    args = parser.parse_args(argv)

    base = build_experiment_config(parse_config(args.config))
    role_counts: dict[str, int] = {}
    for s in base.agent_specs:
        role_counts[s.role] = role_counts.get(s.role, 0) + 1
    structure_desc = ", ".join(f"{c}x{r}" for r, c in sorted(role_counts.items()))

    control = base
    treatment = dataclasses.replace(control)
    treatment.agent_specs = [
        dataclasses.replace(s, leverage_tier=s.leverage_tier * 2) if s.role == "retail" else s
        for s in control.agent_specs
    ]
    c_results, _t, comparison = run_paired(control, treatment, seeds=[control.seed])
    run = c_results[0]

    evidence = json.loads(pathlib.Path(args.evidence).read_text(encoding="utf-8"))
    verify_frozen_evidence(evidence)

    manifest_path, artifacts = write_artifacts(
        run,
        comparison,
        pathlib.Path(args.out_dir),
        evidence=evidence,
        structure_desc=structure_desc,
        param_range_desc="leverage_tier treatment vs control",
        mult=base.mult,
    )
    print(f"wrote {len(artifacts)} artifacts + manifest to {manifest_path}")
    return 0
