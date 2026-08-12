"""T301: Report generation -- consumes frozen artifacts, produces report.

``build_report(manifest_path, out_dir) -> ReportResult`` validates the
manifest (T302), reads the frozen artifacts verbatim (no recomputation),
and writes two files to ``out_dir``:

- ``report.json`` -- machine-readable truth source.
- ``report.md`` -- human-readable, rendered FROM report.json.

Two-state (no partial success):

- **Success**: ``failure`` is ``null``, business fields filled, exit 0.
- **Failure**: business fields all ``null``, ``failure`` non-empty, exit 1.

CLI: ``python -m market_game_sim.report.generate --manifest <path> --out <dir>``

``artifact_root`` has exactly one source -- the manifest's top-level field.
It is NOT a CLI flag or function parameter (design.md §4).
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from market_game_sim.report.manifest import (
    ArtifactReadError,
    ArtifactSchemaError,
    ManifestError,
    compute_file_hash,
    load_registry,
    validate_artifact_value,
    validate_manifest,
    validate_run_id_consistency,
)
from market_game_sim.report.render import render_markdown

#: The report's own schema version (distinct from per-artifact schema versions).
REPORT_SCHEMA_VERSION = 1

#: Artifacts consumed into the top-level ``metrics`` object.  The remaining
#: 3 (conditional_conclusion, robustness_conclusion, negative_results) are
#: promoted to dedicated report.json top-level fields.
_METRIC_ARTIFACT_IDS = (
    "market_metrics",
    "agent_metrics",
    "liquidation_metrics",
    "pnl_bridge",
    "sample_classification",
    "effect_sizes",
    "robustness_effects",
)

#: Artifacts promoted to dedicated report.json top-level fields.
_TOP_LEVEL_ARTIFACT_IDS = (
    "conditional_conclusion",
    "robustness_conclusion",
    "negative_results",
)


@dataclass
class ReportResult:
    """Result of :func:`build_report`.

    Attributes:
        success: ``True`` on success, ``False`` on failure.
        report: The report.json dict (always populated -- ``failure`` is
            ``null`` on success, non-``null`` on failure).
        exit_code: ``0`` on success, ``1`` on failure.
    """

    success: bool
    report: dict[str, Any]
    exit_code: int


def build_report(manifest_path: pathlib.Path, out_dir: pathlib.Path) -> ReportResult:
    """Build ``report.json`` + ``report.md`` from an artifact manifest.

    See module docstring for the two-state contract.
    """
    manifest_path = pathlib.Path(manifest_path)
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        manifest_hash = compute_file_hash(manifest_path)
    except OSError:
        manifest_hash = ""

    generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        data = validate_manifest(manifest_path)

        root = data.artifact_root
        registry = load_registry()

        metrics: dict[str, Any] = {}
        for aid in _METRIC_ARTIFACT_IDS:
            metrics[aid] = load_and_validate_artifact(
                root, data.entries[aid]["path"], registry["artifacts"][aid], aid
            )

        conditional_conclusion = load_and_validate_artifact(
            root,
            data.entries["conditional_conclusion"]["path"],
            registry["artifacts"]["conditional_conclusion"],
            "conditional_conclusion",
        )
        robustness_conclusion = load_and_validate_artifact(
            root,
            data.entries["robustness_conclusion"]["path"],
            registry["artifacts"]["robustness_conclusion"],
            "robustness_conclusion",
        )
        negative_results = load_and_validate_artifact(
            root,
            data.entries["negative_results"]["path"],
            registry["artifacts"]["negative_results"],
            "negative_results",
        )

        all_loaded: dict[str, Any] = dict(metrics)
        all_loaded["conditional_conclusion"] = conditional_conclusion
        all_loaded["robustness_conclusion"] = robustness_conclusion
        all_loaded["negative_results"] = negative_results

        run_id = validate_run_id_consistency(all_loaded, registry)

        report: dict[str, Any] = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "run_id": run_id,
            "manifest_hash": manifest_hash,
            "generated_at": generated_at,
            "metrics": metrics,
            "conditional_conclusion": conditional_conclusion,
            "robustness_conclusion": robustness_conclusion,
            "negative_results": negative_results,
            "failure": None,
        }
    except (ManifestError, ArtifactReadError, ArtifactSchemaError) as exc:
        code = exc.code if isinstance(exc, ManifestError) else "FIELD_SCHEMA_INVALID"
        artifact_id = getattr(exc, "artifact_id", "(unknown)")
        message = getattr(exc, "message", str(exc))
        report = _failure_report(manifest_hash, generated_at, code, artifact_id, message)
        _write_report(out_dir, report)
        return ReportResult(success=False, report=report, exit_code=1)

    _write_report(out_dir, report)
    return ReportResult(success=True, report=report, exit_code=0)


def load_and_validate_artifact(
    artifact_root: pathlib.Path,
    rel_path: str,
    spec: dict[str, Any],
    artifact_id: str,
) -> Any:
    """Read an artifact file and validate it against its registry spec.

    The registry's ``format`` is the consumption contract: every artifact is
    currently ``json`` (JSON table/object, e.g. a JSON table for a
    table-shaped artifact).  ``parquet`` is a reserved enum value for future
    archive-only producers and is NOT consumable by this stdlib report layer
    (no parquet dependency, ADR-004/T507 boundary) -- it is rejected with a
    clear error, never silently mis-decoded.

    Raises:
        ArtifactReadError: artifact ``format`` is not ``"json"``, or the
            file cannot be read/decoded (OSError, UnicodeDecodeError,
            JSONDecodeError).
        ArtifactSchemaError: value fails validation against the registry spec.
    """
    if spec.get("format") != "json":
        raise ArtifactReadError(
            artifact_id,
            f"unsupported artifact format {spec.get('format')!r} "
            "(only 'json' is consumable by the stdlib report layer)",
        )

    file_path = artifact_root / rel_path
    try:
        raw = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ArtifactReadError(artifact_id, f"cannot read file '{rel_path}': {exc}") from exc
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ArtifactReadError(artifact_id, f"cannot parse JSON '{rel_path}': {exc}") from exc

    validate_artifact_value(value, spec, artifact_id)
    return value


def _failure_report(
    manifest_hash: str,
    generated_at: str,
    code: str,
    artifact_id: str,
    message: str,
) -> dict[str, Any]:
    """Build a failure report.json dict (business fields all null)."""
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "run_id": "",
        "manifest_hash": manifest_hash,
        "generated_at": generated_at,
        "metrics": None,
        "conditional_conclusion": None,
        "robustness_conclusion": None,
        "negative_results": None,
        "failure": {
            "code": code,
            "artifact_id": artifact_id,
            "message": message,
        },
    }


def _write_report(out_dir: pathlib.Path, report: dict[str, Any]) -> None:
    """Write ``report.json`` and ``report.md`` to ``out_dir``.

    Publication model (honest about filesystem limits):

    A filesystem cannot atomically replace two independent paths simultaneously.
    This function's guarantee is:

    1. Both files are fully written and fsync'd into a generation-specific
       temp directory (``.gen-<nonce>/``) BEFORE either is moved into place.
    2. Each file is individually atomically replaced via ``os.replace``.
    3. A crash after the first replace but before the second can leave a
       new ``report.json`` paired with an old ``report.md`` -- this is
       inherent to filesystem semantics and cannot be avoided without a
       single-pointer indirection (not used here for simplicity).

    What IS guaranteed: no reader ever observes a partially-written individual
    file (each is fully written + fsync'd before the replace).
    """
    report_json_path = out_dir / "report.json"
    report_md_path = out_dir / "report.md"

    gen_dir = out_dir / f".gen-{uuid.uuid4().hex}"
    gen_dir.mkdir(parents=True, exist_ok=False)

    try:
        tmp_json = gen_dir / "report.json"
        tmp_md = gen_dir / "report.md"

        with open(tmp_json, "w", encoding="utf-8") as f:
            f.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
            f.flush()
            os.fsync(f.fileno())
        with open(tmp_md, "w", encoding="utf-8") as f:
            f.write(render_markdown(report))
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp_json, report_json_path)
        os.replace(tmp_md, report_md_path)
    finally:
        shutil.rmtree(gen_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: ``python -m market_game_sim.report.generate``."""
    parser = argparse.ArgumentParser(
        prog="python -m market_game_sim.report.generate",
        description="Build summary report from an artifact manifest.",
    )
    parser.add_argument(
        "--manifest", required=True, type=pathlib.Path, help="Path to the manifest JSON file."
    )
    parser.add_argument(
        "--out",
        required=True,
        type=pathlib.Path,
        help="Output directory for report.json and report.md.",
    )
    args = parser.parse_args(argv)

    result = build_report(args.manifest, args.out)
    if not result.success:
        failure = result.report["failure"]
        print(
            f"report generation failed: [{failure['code']}] "
            f"{failure['artifact_id']}: {failure['message']}",
            file=sys.stderr,
        )
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
