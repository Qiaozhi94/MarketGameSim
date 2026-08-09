"""T001 (0.1.2 退出清单): 0.1.3 startup admission gate.

Rebuilds the 0.1.2 exit checklist E1--E7 (+ additional gate) from the
machine-truth evidence index ``docs/experiments/0.1.2-exit-evidence-index.json``
instead of hand-copying the list, then verifies that every exit condition is
``met`` and that each piece of evidence it cites actually exists on disk
(guarding against the recurring "marked-done-not-implemented" failure mode
documented in docs/reviews/RETROSPECTIVE.md).

It then reconciles the milestone's run artifact
``docs/experiments/0.1.2-e6-demonstration-run.json`` against the same
machine sources: conditional conclusion matches the human summary, the
market-validation matrix is readable with a valid verdict enum, and the
KPI-011 zero-sum residual is 0 on every seed.

Everything is fail-closed: any unmet exit condition, missing evidence target,
unreadable artifact, or digest/summary mismatch raises ``AdmissionGateError``.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import dataclass, field
from typing import Any

VALID_VERDICTS = {"PASS", "FAIL", "NOT_APPLICABLE"}


class AdmissionGateError(RuntimeError):
    """Raised when the 0.1.3 admission gate does not pass."""


@dataclass(frozen=True)
class ExitCondition:
    id: str
    description: str
    tasks: tuple[str, ...]
    status: str
    evidence: tuple[str, ...]
    notes: str | None = None


@dataclass
class GateResult:
    exit_conditions: list[ExitCondition] = field(default_factory=list)
    unmet: list[str] = field(default_factory=list)
    missing_evidence: list[tuple[str, str]] = field(default_factory=list)
    artifact_digest: str = ""
    summary_digest: str = ""
    conclusion_matches_summary: bool = False
    market_matrix_seeds: list[str] = field(default_factory=list)
    matrix_verdicts_ok: bool = False
    zero_sum_residuals: list[int] = field(default_factory=list)
    zero_sum_ok: bool = False


def load_exit_index(path: str | pathlib.Path) -> list[ExitCondition]:
    """Parse the 0.1.2 exit-evidence-index.json into ExitCondition objects.

    The list of conditions is read from the file, never hardcoded, so the
    gate automatically tracks any change to the 0.1.2 scope.
    """
    p = pathlib.Path(path)
    if not p.is_file():
        raise AdmissionGateError(f"exit index not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdmissionGateError(f"exit index unreadable: {p}: {exc}") from exc

    items = data.get("items")
    if not isinstance(items, list):
        raise AdmissionGateError(f"exit index has no items list: {p}")

    conditions: list[ExitCondition] = []
    for item in items:
        if not isinstance(item, dict) or "id" not in item:
            raise AdmissionGateError(f"exit index malformed item (missing id): {item!r}")
        conditions.append(
            ExitCondition(
                id=str(item["id"]),
                description=str(item.get("description", "")),
                tasks=tuple(str(t) for t in item.get("tasks", [])),
                status=str(item.get("status", "")),
                evidence=tuple(str(e) for e in item.get("evidence", [])),
                notes=item.get("notes"),
            )
        )
    return conditions


def _evidence_target(evidence: str) -> str:
    """Extract the on-disk file/dir target from an evidence string.

    Evidence strings cite ``<path>::<symbol>`` or ``<path> (comment)`` or a
    bare path.  We want the leading path token up to the first ``::``, `` ``,
    ``(``, ``（`` or ``§``.
    """
    stripped = evidence.strip()
    for sep in ("::", " ", "(", "（", "§"):
        idx = stripped.find(sep)
        if idx != -1:
            stripped = stripped[:idx]
            break
    return stripped.rstrip("/")


def verify_evidence_targets(
    conditions: list[ExitCondition], repo_root: str | pathlib.Path
) -> list[tuple[str, str]]:
    """Return ``(condition_id, missing_target)`` for every cited evidence file
    or directory that does not exist under ``repo_root``."""
    root = pathlib.Path(repo_root)
    missing: list[tuple[str, str]] = []
    for cond in conditions:
        for evidence in cond.evidence:
            target = _evidence_target(evidence)
            if not target:
                continue
            if not (root / target).exists():
                missing.append((cond.id, target))
    return missing


def unmet_conditions(conditions: list[ExitCondition]) -> list[str]:
    """Return ids whose status is not ``met`` (fail-closed on not_met and
    partially_met alike -- neither admits an unchecked entry)."""
    return [c.id for c in conditions if c.status != "met"]


def _canonical_digest(obj: Any) -> str:
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.blake2b(canonical.encode("utf-8"), digest_size=16).hexdigest()


def _load_json(path: str | pathlib.Path, what: str) -> dict[str, Any]:
    p = pathlib.Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdmissionGateError(f"{what} unreadable: {p}: {exc}") from exc
    if not isinstance(data, dict):
        raise AdmissionGateError(f"{what} is not a JSON object: {p}")
    return data


def artifact_digest(path: str | pathlib.Path) -> str:
    """Deterministic blake2b digest of a run artifact file's JSON content."""
    return _canonical_digest(_load_json(path, "run artifact"))


def _extract_conclusion(comparison: dict[str, Any]) -> str:
    conclusion = comparison.get("conditional_conclusion")
    if not isinstance(conclusion, str) or not conclusion.strip():
        raise AdmissionGateError("comparison.conditional_conclusion missing or empty")
    return conclusion.strip()


def verify_run_artifact(
    artifact: dict[str, Any],
) -> tuple[str, list[str], bool, list[int]]:
    """Validate a 0.1.2 run artifact's cross-source consistency.

    Returns ``(conclusion, matrix_seeds, matrix_verdicts_ok, zero_sum_residuals)``
    and raises ``AdmissionGateError`` on any structural violation.
    """
    comparison = artifact.get("comparison")
    if not isinstance(comparison, dict):
        raise AdmissionGateError("run artifact missing comparison block")

    for key in ("control_config_hash", "treatment_config_hash"):
        if not isinstance(comparison.get(key), str) or not comparison[key]:
            raise AdmissionGateError(f"comparison.{key} missing or empty")

    conclusion = _extract_conclusion(comparison)

    matrix_seeds: list[str] = []
    verdicts_ok = True
    for report_key in ("control_report", "treatment_report"):
        report = artifact.get(report_key)
        if not isinstance(report, dict):
            raise AdmissionGateError(f"run artifact missing {report_key}")
        mv = report.get("market_validation", {})
        per_seed = mv.get("per_seed")
        if not isinstance(per_seed, dict) or not per_seed:
            raise AdmissionGateError(f"{report_key}.market_validation.per_seed missing or empty")
        for seed, matrix in per_seed.items():
            matrix_seeds.append(str(seed))
            items = matrix.get("items")
            if not isinstance(items, dict) or not items:
                raise AdmissionGateError(f"{report_key} seed {seed}: market matrix has no items")
            for _name, item in items.items():
                if not isinstance(item, dict):
                    verdicts_ok = False
                    continue
                if item.get("verdict") not in VALID_VERDICTS:
                    verdicts_ok = False

    residuals: list[int] = []
    for report_key in ("control_report", "treatment_report"):
        zero_sum = artifact.get(report_key, {}).get("zero_sum")
        if not isinstance(zero_sum, dict) or not zero_sum:
            raise AdmissionGateError(f"{report_key}.zero_sum missing or empty")
        for seed, decl in zero_sum.items():
            res = decl.get("residual_units")
            if not isinstance(res, int):
                raise AdmissionGateError(f"{report_key} seed {seed}: residual_units not an int")
            residuals.append(res)

    return conclusion, matrix_seeds, verdicts_ok, residuals


def _collapse_ws(text: str) -> str:
    """Strip all whitespace (spaces, newlines, tabs) -- the .md summary wraps
    the conclusion across lines inside its code block while the JSON artifact
    stores it on one line, so a whitespace-insensitive comparison is required
    for the摘要匹配 check."""
    return "".join(text.split())


def summarize_matches(artifact_conclusion: str, summary_text: str) -> bool:
    """Whether the run artifact's conditional conclusion appears in the human
    summary (whitespace-insensitive) -- the摘要匹配 check for T001."""
    return _collapse_ws(artifact_conclusion) in _collapse_ws(summary_text)


def run_gate(
    exit_index_path: str | pathlib.Path,
    run_artifact_path: str | pathlib.Path,
    summary_path: str | pathlib.Path | None,
    repo_root: str | pathlib.Path,
) -> GateResult:
    """Run the full 0.1.3 admission gate.

    Raises ``AdmissionGateError`` on any failure; otherwise returns a
    ``GateResult`` populated with the verified facts.
    """
    result = GateResult()

    conditions = load_exit_index(exit_index_path)
    result.exit_conditions = conditions

    result.unmet = unmet_conditions(conditions)
    result.missing_evidence = verify_evidence_targets(conditions, repo_root)
    if result.unmet:
        raise AdmissionGateError(f"unmet 0.1.2 exit conditions: {result.unmet}")
    if result.missing_evidence:
        raise AdmissionGateError(
            "0.1.2 evidence targets missing: "
            + ", ".join(f"{cid}:{tgt}" for cid, tgt in result.missing_evidence)
        )

    result.artifact_digest = artifact_digest(run_artifact_path)
    artifact = _load_json(run_artifact_path, "run artifact")

    conclusion, matrix_seeds, verdicts_ok, residuals = verify_run_artifact(artifact)
    result.market_matrix_seeds = matrix_seeds
    result.matrix_verdicts_ok = verdicts_ok
    result.zero_sum_residuals = residuals
    result.zero_sum_ok = all(res == 0 for res in residuals)

    if not verdicts_ok:
        raise AdmissionGateError("market-validation matrix contains an invalid verdict")
    if not result.zero_sum_ok:
        raise AdmissionGateError(f"KPI-011 zero-sum residuals non-zero: {residuals}")

    if summary_path is not None:
        sp = pathlib.Path(summary_path)
        try:
            summary_text = sp.read_text(encoding="utf-8")
        except OSError as exc:
            raise AdmissionGateError(f"summary unreadable: {sp}: {exc}") from exc
        result.summary_digest = _canonical_digest(summary_text)
        result.conclusion_matches_summary = summarize_matches(conclusion, summary_text)
        if not result.conclusion_matches_summary:
            raise AdmissionGateError("conditional conclusion does not match the summary")

    return result
