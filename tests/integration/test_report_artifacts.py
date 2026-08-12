"""AC-004 (E4/PR-019): summary report consumes upstream artifacts, no recomputation.

Builds a realistic artifact set (all 10 artifacts with registry-matching
required_fields), a valid manifest, and asserts:

- ``report.json`` has all business fields populated, ``failure`` is null.
- ``metrics`` / ``conditional_conclusion`` / ``negative_results`` content
  equals the upstream artifact content (byte-identical, NOT recomputed).
- ``report.md`` exists and contains content rendered FROM report.json.
- ``manifest_hash`` is the correct blake2b digest of the manifest file.
- Changing any upstream artifact makes the report fail (hash mismatch).
- The report layer performs NO statistical test / re-aggregation (verified
  by asserting report values are byte-identical to consumed artifacts).
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
from typing import Any

import pytest

from market_game_sim.report.generate import build_report
from market_game_sim.report.manifest import load_registry

_REGISTRY = load_registry()
_REGISTRY_IDS = sorted(_REGISTRY["artifacts"].keys())

_METRIC_IDS = (
    "market_metrics",
    "agent_metrics",
    "liquidation_metrics",
    "pnl_bridge",
    "sample_classification",
    "effect_sizes",
    "robustness_effects",
)


def _blake2b_hex(data: bytes) -> str:
    h = hashlib.blake2b(digest_size=32)
    h.update(data)
    return h.hexdigest()


def _build_value(fspec: dict[str, Any], fname: str, aid: str) -> Any:
    t = fspec.get("type")
    if t == "integer":
        return 1
    if t == "number":
        return 0.5
    if t == "string":
        # run_id must be IDENTICAL across all artifacts (R-C cross-artifact
        # consistency); other strings stay per-artifact for traceability.
        if fname == "run_id":
            return "run-1"
        return f"{aid}_{fname}"
    if t == "boolean":
        return True
    if t == "array":
        item_type = fspec.get("item_type")
        if item_type == "object":
            return [_build_fields(fspec.get("item_fields", {}), aid)]
        if item_type == "string":
            return [f"{aid}_item"]
        return []
    if t == "object":
        if "required_fields" in fspec:
            return _build_fields(fspec["required_fields"], aid)
        return {"sample_key": 1}
    return None


def _build_fields(fields: dict[str, Any], aid: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for fname, fspec in fields.items():
        result[fname] = _build_value(fspec, fname, aid)
    return result


def _make_content(aid: str, spec: dict[str, Any]) -> Any:
    """Realistic artifact content with all required_fields populated."""
    fields = _build_fields(spec["required_fields"], aid)
    if spec["shape"] == "table":
        return [fields]
    return fields


def _build_realistic_setup(
    tmp_path: pathlib.Path,
) -> tuple[pathlib.Path, pathlib.Path, dict[str, Any]]:
    """Build a realistic artifact set with all 10 artifacts.

    Returns (manifest_path, artifact_root, contents) where ``contents``
    maps artifact_id to the exact JSON value written to the file.
    """
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()

    contents: dict[str, Any] = {}
    entries: list[dict[str, Any]] = []

    for aid in _REGISTRY_IDS:
        spec = _REGISTRY["artifacts"][aid]
        content = _make_content(aid, spec)
        contents[aid] = content

        fname = f"{aid}.json"
        fpath = artifact_root / fname
        fpath.write_text(json.dumps(content, sort_keys=True), encoding="utf-8")

        entries.append(
            {
                "artifact_id": aid,
                "path": fname,
                "format": spec["format"],
                "schema_version": spec["schema_version"],
                "producer": spec["producer"],
                "hash_algorithm": "blake2b",
                "hash": _blake2b_hex(fpath.read_bytes()),
            }
        )

    manifest = {
        "manifest_version": 1,
        "artifact_root": "artifacts",
        "artifacts": entries,
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return manifest_path, artifact_root, contents


# ---------------------------------------------------------------------------
# E4 / AC-004: success path -- consume verbatim, no recomputation
# ---------------------------------------------------------------------------


class TestReportSuccess:
    def test_all_business_fields_populated_and_failure_null(self, tmp_path):
        manifest_path, _root, _contents = _build_realistic_setup(tmp_path)
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is True
        assert result.report["failure"] is None
        assert result.exit_code == 0
        assert result.report["metrics"] is not None
        assert result.report["conditional_conclusion"] is not None
        assert result.report["negative_results"] is not None

    def test_metrics_content_equals_upstream_artifact(self, tmp_path):
        """metrics values are byte-identical to consumed artifacts (no re-aggregation)."""
        manifest_path, _root, contents = _build_realistic_setup(tmp_path)
        result = build_report(manifest_path, tmp_path / "out")
        for aid in _METRIC_IDS:
            assert result.report["metrics"][aid] == contents[aid], (
                f"metrics[{aid}] differs from upstream artifact"
            )

    def test_conditional_conclusion_equals_upstream_artifact(self, tmp_path):
        manifest_path, _root, contents = _build_realistic_setup(tmp_path)
        result = build_report(manifest_path, tmp_path / "out")
        assert result.report["conditional_conclusion"] == contents["conditional_conclusion"]

    def test_robustness_conclusion_equals_upstream_artifact(self, tmp_path):
        manifest_path, _root, contents = _build_realistic_setup(tmp_path)
        result = build_report(manifest_path, tmp_path / "out")
        assert result.report["robustness_conclusion"] == contents["robustness_conclusion"]

    def test_negative_results_equals_upstream_artifact(self, tmp_path):
        manifest_path, _root, contents = _build_realistic_setup(tmp_path)
        result = build_report(manifest_path, tmp_path / "out")
        assert result.report["negative_results"] == contents["negative_results"]

    def test_run_id_consumed_from_liquidation_metrics(self, tmp_path):
        manifest_path, _root, contents = _build_realistic_setup(tmp_path)
        result = build_report(manifest_path, tmp_path / "out")
        liq = contents["liquidation_metrics"]
        if isinstance(liq, dict):
            assert result.report["run_id"] == liq["run_id"]

    def test_manifest_hash_is_correct_blake2b(self, tmp_path):
        manifest_path, _root, _contents = _build_realistic_setup(tmp_path)
        expected = _blake2b_hex(manifest_path.read_bytes())
        result = build_report(manifest_path, tmp_path / "out")
        assert result.report["manifest_hash"] == expected


# ---------------------------------------------------------------------------
# report.md rendered FROM report.json
# ---------------------------------------------------------------------------


class TestReportMarkdown:
    def test_report_md_exists(self, tmp_path):
        manifest_path, _root, _contents = _build_realistic_setup(tmp_path)
        out_dir = tmp_path / "out"
        build_report(manifest_path, out_dir)
        assert (out_dir / "report.md").is_file()

    def test_report_md_contains_content_from_report_json(self, tmp_path):
        manifest_path, _root, _contents = _build_realistic_setup(tmp_path)
        out_dir = tmp_path / "out"
        build_report(manifest_path, out_dir)
        md_text = (out_dir / "report.md").read_text(encoding="utf-8")
        assert "Summary Report" in md_text
        assert "Conditional Conclusion" in md_text
        assert "Robustness Conclusion" in md_text
        assert "Negative Results" in md_text

    def test_report_md_on_failure_shows_failure_info(self, tmp_path):
        manifest_path, _root, _contents = _build_realistic_setup(tmp_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["artifacts"] = manifest["artifacts"][:9]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        out_dir = tmp_path / "out"
        build_report(manifest_path, out_dir)
        md_text = (out_dir / "report.md").read_text(encoding="utf-8")
        assert "Report Generation Failed" in md_text
        assert "MISSING_ARTIFACT" in md_text

    def test_report_json_and_md_written_atomically(self, tmp_path):
        """Both report.json and report.md exist after build_report (no partial)."""
        manifest_path, _root, _contents = _build_realistic_setup(tmp_path)
        out_dir = tmp_path / "out"
        build_report(manifest_path, out_dir)
        assert (out_dir / "report.json").is_file()
        assert (out_dir / "report.md").is_file()
        assert not (out_dir / "report.json.tmp").exists()
        assert not (out_dir / "report.md.tmp").exists()
        assert not list(out_dir.glob(".gen-*"))


# ---------------------------------------------------------------------------
# Hash mismatch detection: changing upstream artifact changes report
# ---------------------------------------------------------------------------


class TestHashMismatchDetection:
    def test_changing_any_upstream_artifact_fails_report(self, tmp_path):
        """Modifying any artifact file after manifest creation -> HASH_MISMATCH."""
        manifest_path, artifact_root, _contents = _build_realistic_setup(tmp_path)
        for aid in _REGISTRY_IDS:
            target = artifact_root / f"{aid}.json"
            original = target.read_bytes()
            target.write_bytes(original + b" ")
            result = build_report(manifest_path, tmp_path / f"out_{aid}")
            assert result.success is False, f"{aid} change should fail"
            assert result.report["failure"]["code"] == "HASH_MISMATCH"
            assert result.report["failure"]["artifact_id"] == aid
            target.write_bytes(original)

    def test_report_values_byte_identical_no_recomputation(self, tmp_path):
        """Report values are byte-identical to consumed artifacts (no statistical
        test or re-aggregation performed by the report layer)."""
        manifest_path, _root, contents = _build_realistic_setup(tmp_path)
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is True
        for aid in _METRIC_IDS:
            assert result.report["metrics"][aid] == contents[aid]
        assert result.report["conditional_conclusion"] == contents["conditional_conclusion"]
        assert result.report["robustness_conclusion"] == contents["robustness_conclusion"]
        assert result.report["negative_results"] == contents["negative_results"]


# ---------------------------------------------------------------------------
# robustness_conclusion null case
# ---------------------------------------------------------------------------


class TestRobustnessConclusionNull:
    def test_robustness_conclusion_null_artifact_produces_null_field(self, tmp_path):
        """When the robustness_conclusion artifact file contains JSON null,
        the report field is null (design.md §4: 对象或 null)."""
        manifest_path, artifact_root, _contents = _build_realistic_setup(tmp_path)
        rc_path = artifact_root / "robustness_conclusion.json"
        rc_path.write_text("null", encoding="utf-8")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for e in manifest["artifacts"]:
            if e["artifact_id"] == "robustness_conclusion":
                e["hash"] = _blake2b_hex(rc_path.read_bytes())
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is True
        assert result.report["robustness_conclusion"] is None


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


class TestCLI:
    def test_cli_success_exit_0(self, tmp_path):
        manifest_path, _root, _contents = _build_realistic_setup(tmp_path)
        out_dir = tmp_path / "out_cli"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "market_game_sim.report.generate",
                "--manifest",
                str(manifest_path),
                "--out",
                str(out_dir),
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        assert (out_dir / "report.json").is_file()
        assert (out_dir / "report.md").is_file()

    def test_cli_failure_exit_1(self, tmp_path):
        manifest_path, _root, _contents = _build_realistic_setup(tmp_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["artifacts"] = manifest["artifacts"][:9]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        out_dir = tmp_path / "out_cli"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "market_game_sim.report.generate",
                "--manifest",
                str(manifest_path),
                "--out",
                str(out_dir),
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1
        assert "MISSING_ARTIFACT" in proc.stderr


# ---------------------------------------------------------------------------
# R1: artifact content validation against the registry
# ---------------------------------------------------------------------------


class TestArtifactSchemaValidation:
    """R1: the report validates artifact content against the registry spec."""

    def test_empty_object_for_table_artifact_fails(self, tmp_path):
        """An artifact file with content ``{}`` for a table-shaped artifact -> fails."""
        manifest_path, artifact_root, _contents = _build_realistic_setup(tmp_path)
        target = artifact_root / "market_metrics.json"
        target.write_text("{}", encoding="utf-8")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for e in manifest["artifacts"]:
            if e["artifact_id"] == "market_metrics":
                e["hash"] = _blake2b_hex(target.read_bytes())
        manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "FIELD_SCHEMA_INVALID"
        assert result.report["failure"]["artifact_id"] == "market_metrics"

    def test_missing_required_field_fails(self, tmp_path):
        """An artifact missing a required field -> FIELD_SCHEMA_INVALID."""
        manifest_path, artifact_root, contents = _build_realistic_setup(tmp_path)
        mm = contents["market_metrics"]
        assert isinstance(mm, list)
        del mm[0]["run_id"]
        target = artifact_root / "market_metrics.json"
        target.write_text(json.dumps(mm, sort_keys=True), encoding="utf-8")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for e in manifest["artifacts"]:
            if e["artifact_id"] == "market_metrics":
                e["hash"] = _blake2b_hex(target.read_bytes())
        manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "FIELD_SCHEMA_INVALID"
        assert result.report["failure"]["artifact_id"] == "market_metrics"

    def test_wrong_typed_field_fails(self, tmp_path):
        """An artifact with a wrong-typed field -> FIELD_SCHEMA_INVALID."""
        manifest_path, artifact_root, contents = _build_realistic_setup(tmp_path)
        mm = contents["market_metrics"]
        assert isinstance(mm, list)
        mm[0]["run_id"] = 12345  # string field, got integer
        target = artifact_root / "market_metrics.json"
        target.write_text(json.dumps(mm, sort_keys=True), encoding="utf-8")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for e in manifest["artifacts"]:
            if e["artifact_id"] == "market_metrics":
                e["hash"] = _blake2b_hex(target.read_bytes())
        manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "FIELD_SCHEMA_INVALID"
        assert result.report["failure"]["artifact_id"] == "market_metrics"

    def test_wrong_payload_schema_version_fails(self, tmp_path):
        """An artifact with wrong payload schema_version -> FIELD_SCHEMA_INVALID."""
        manifest_path, artifact_root, contents = _build_realistic_setup(tmp_path)
        liq = contents["liquidation_metrics"]
        assert isinstance(liq, dict)
        liq["schema_version"] = 999
        target = artifact_root / "liquidation_metrics.json"
        target.write_text(json.dumps(liq, sort_keys=True), encoding="utf-8")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for e in manifest["artifacts"]:
            if e["artifact_id"] == "liquidation_metrics":
                e["hash"] = _blake2b_hex(target.read_bytes())
        manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "FIELD_SCHEMA_INVALID"
        assert result.report["failure"]["artifact_id"] == "liquidation_metrics"

    def test_valid_multi_row_table_artifact_succeeds(self, tmp_path):
        """A valid multi-row table artifact (2+ rows) -> succeeds, byte-identical."""
        manifest_path, artifact_root, contents = _build_realistic_setup(tmp_path)
        spec = _REGISTRY["artifacts"]["market_metrics"]
        row = _build_fields(spec["required_fields"], "market_metrics")
        multi_row = [row, dict(row)]
        target = artifact_root / "market_metrics.json"
        target.write_text(json.dumps(multi_row, sort_keys=True), encoding="utf-8")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for e in manifest["artifacts"]:
            if e["artifact_id"] == "market_metrics":
                e["hash"] = _blake2b_hex(target.read_bytes())
        manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is True
        assert result.report["failure"] is None
        assert result.report["metrics"]["market_metrics"] == multi_row
        assert len(result.report["metrics"]["market_metrics"]) == 2

    def test_non_utf8_binary_artifact_fails_controlled(self, tmp_path):
        """A non-UTF8/binary artifact file -> controlled failure, not traceback."""
        manifest_path, artifact_root, _contents = _build_realistic_setup(tmp_path)
        target = artifact_root / "market_metrics.json"
        binary_data = b"\xff\xfe\x00\x01\x80\x81 not valid utf-8"
        target.write_bytes(binary_data)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for e in manifest["artifacts"]:
            if e["artifact_id"] == "market_metrics":
                e["hash"] = _blake2b_hex(binary_data)
        manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "FIELD_SCHEMA_INVALID"
        assert result.report["failure"]["artifact_id"] == "market_metrics"

    def test_invalid_json_artifact_fails_controlled(self, tmp_path):
        """A file with invalid JSON -> controlled failure (ArtifactReadError)."""
        manifest_path, artifact_root, _contents = _build_realistic_setup(tmp_path)
        target = artifact_root / "market_metrics.json"
        bad_json = "{not valid json"
        target.write_text(bad_json, encoding="utf-8")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for e in manifest["artifacts"]:
            if e["artifact_id"] == "market_metrics":
                e["hash"] = _blake2b_hex(target.read_bytes())
        manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "FIELD_SCHEMA_INVALID"
        assert result.report["failure"]["artifact_id"] == "market_metrics"


# ---------------------------------------------------------------------------
# R2: payload read/parse failures escape the two-state report contract
# ---------------------------------------------------------------------------


class TestArtifactReadFailure:
    """R2: undecodable artifacts produce a structured failure, not a traceback."""

    def test_undecodable_artifact_produces_failure_report(self, tmp_path):
        """A manifest that passes hash checks but has an undecodable artifact file
        -> build_report returns success=False, failure non-null, exit_code=1."""
        manifest_path, artifact_root, _contents = _build_realistic_setup(tmp_path)
        target = artifact_root / "agent_metrics.json"
        binary_data = b"\xff\xfe\x00\x01\x80\x81 not valid utf-8"
        target.write_bytes(binary_data)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for e in manifest["artifacts"]:
            if e["artifact_id"] == "agent_metrics":
                e["hash"] = _blake2b_hex(binary_data)
        manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"] is not None
        assert result.report["failure"]["code"] == "FIELD_SCHEMA_INVALID"
        assert result.report["failure"]["artifact_id"] == "agent_metrics"
        assert result.exit_code == 1
        assert result.report["metrics"] is None
        assert result.report["conditional_conclusion"] is None

    def test_cli_undecodable_artifact_exit_1_no_traceback(self, tmp_path):
        """CLI with an undecodable artifact -> exit 1, structured message, no traceback."""
        manifest_path, artifact_root, _contents = _build_realistic_setup(tmp_path)
        target = artifact_root / "agent_metrics.json"
        binary_data = b"\xff\xfe\x00\x01\x80\x81 not valid utf-8"
        target.write_bytes(binary_data)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for e in manifest["artifacts"]:
            if e["artifact_id"] == "agent_metrics":
                e["hash"] = _blake2b_hex(binary_data)
        manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        out_dir = tmp_path / "out_cli"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "market_game_sim.report.generate",
                "--manifest",
                str(manifest_path),
                "--out",
                str(out_dir),
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1
        assert "FIELD_SCHEMA_INVALID" in proc.stderr
        assert "Traceback" not in proc.stderr


# ---------------------------------------------------------------------------
# R4: negative_results shape is object (not array), verbatim consumption
# ---------------------------------------------------------------------------


class TestNegativeResultsShape:
    """R4: report.json.negative_results is the artifact object (not an array)."""

    def test_negative_results_is_object_not_array(self, tmp_path):
        """report['negative_results'] is a dict (object), not a list (array)."""
        manifest_path, _root, _contents = _build_realistic_setup(tmp_path)
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is True
        nr = result.report["negative_results"]
        assert isinstance(nr, dict)
        assert "schema_version" in nr
        assert "results" in nr

    def test_negative_results_equals_artifact_envelope(self, tmp_path):
        """report['negative_results'] equals the whole artifact envelope byte-identical."""
        manifest_path, _root, contents = _build_realistic_setup(tmp_path)
        result = build_report(manifest_path, tmp_path / "out")
        assert result.report["negative_results"] == contents["negative_results"]


# ---------------------------------------------------------------------------
# R5: two report files published with per-file atomicity
# ---------------------------------------------------------------------------


class TestAtomicWritePair:
    """R5: both files are fsync'd before either replace; pair-atomicity is best-effort."""

    def test_second_replace_failure_leaves_first_file_complete(self, tmp_path, monkeypatch):
        """If the second os.replace fails, the first file has the complete new content."""
        manifest_path, _root, _contents = _build_realistic_setup(tmp_path)
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        (out_dir / "report.json").write_text('{"old": true}', encoding="utf-8")
        (out_dir / "report.md").write_text("old content", encoding="utf-8")

        original_replace = os.replace
        call_count = [0]

        def patched_replace(src, dst):
            call_count[0] += 1
            if call_count[0] == 2:
                raise OSError("simulated failure on second replace")
            return original_replace(src, dst)

        monkeypatch.setattr("os.replace", patched_replace)

        with pytest.raises(OSError, match="simulated failure"):
            build_report(manifest_path, out_dir)

        new_json = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
        assert new_json.get("failure") is None
        assert "schema_version" in new_json
        assert not list(out_dir.glob(".gen-*"))

    def test_no_tmp_or_gen_residue_on_normal_success(self, tmp_path):
        """On normal success, no .tmp or .gen-* files remain."""
        manifest_path, _root, _contents = _build_realistic_setup(tmp_path)
        out_dir = tmp_path / "out"
        build_report(manifest_path, out_dir)
        assert (out_dir / "report.json").is_file()
        assert (out_dir / "report.md").is_file()
        assert not (out_dir / "report.json.tmp").exists()
        assert not (out_dir / "report.md.tmp").exists()
        assert not list(out_dir.glob(".gen-*"))


# ---------------------------------------------------------------------------
# R-B / R-C / R-D / R-A: round-2 registry semantics
# ---------------------------------------------------------------------------


class TestTableSemantics:
    """R-B: empty tables are legal; an empty OBJECT still fails for a table."""

    def test_empty_table_array_is_valid(self, tmp_path):
        manifest_path, artifact_root, _contents = _build_realistic_setup(tmp_path)
        target = artifact_root / "market_metrics.json"
        target.write_text("[]", encoding="utf-8")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for e in manifest["artifacts"]:
            if e["artifact_id"] == "market_metrics":
                e["hash"] = _blake2b_hex(target.read_bytes())
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is True
        assert result.report["metrics"]["market_metrics"] == []

    def test_empty_object_still_rejected_for_table(self, tmp_path):
        manifest_path, artifact_root, _contents = _build_realistic_setup(tmp_path)
        target = artifact_root / "market_metrics.json"
        target.write_text("{}", encoding="utf-8")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for e in manifest["artifacts"]:
            if e["artifact_id"] == "market_metrics":
                e["hash"] = _blake2b_hex(target.read_bytes())
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "FIELD_SCHEMA_INVALID"


class TestCrossArtifactRunId:
    """R-C: all artifacts carrying run_id must agree on one value."""

    def _rewrite_artifact(self, tmp_path, manifest_path, artifact_root, aid, new_content):
        target = artifact_root / f"{aid}.json"
        target.write_text(json.dumps(new_content, sort_keys=True), encoding="utf-8")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for e in manifest["artifacts"]:
            if e["artifact_id"] == aid:
                e["hash"] = _blake2b_hex(target.read_bytes())
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def test_mixed_run_ids_across_artifacts_fail(self, tmp_path):
        """Two table artifacts with different run_ids must fail the report."""
        manifest_path, artifact_root, contents = _build_realistic_setup(tmp_path)
        rows = contents["market_metrics"]
        other = [dict(r) for r in rows]
        other[0]["run_id"] = "run-other"
        self._rewrite_artifact(tmp_path, manifest_path, artifact_root, "market_metrics", other)
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "FIELD_SCHEMA_INVALID"

    def test_mixed_run_ids_within_one_table_fail(self, tmp_path):
        """Two rows of the SAME artifact with different run_ids must fail (batch)."""
        manifest_path, artifact_root, contents = _build_realistic_setup(tmp_path)
        rows = contents["agent_metrics"]
        mixed = [dict(r) for r in rows] + [dict(rows[0], run_id="run-other")]
        self._rewrite_artifact(tmp_path, manifest_path, artifact_root, "agent_metrics", mixed)
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "FIELD_SCHEMA_INVALID"

    def test_consistent_run_ids_succeed(self, tmp_path):
        """All artifacts sharing one run_id still succeed (accepted side)."""
        manifest_path, _root, contents = _build_realistic_setup(tmp_path)
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is True
        assert result.report["run_id"] == contents["liquidation_metrics"]["run_id"]

    def test_empty_table_with_other_run_ids_succeed(self, tmp_path):
        """An empty table (R-B) contributes no run_id; if the remaining
        artifacts all share one run_id, the report still succeeds."""
        manifest_path, artifact_root, _contents = _build_realistic_setup(tmp_path)
        target = artifact_root / "market_metrics.json"
        target.write_text("[]", encoding="utf-8")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for e in manifest["artifacts"]:
            if e["artifact_id"] == "market_metrics":
                e["hash"] = _blake2b_hex(target.read_bytes())
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is True
        assert result.report["metrics"]["market_metrics"] == []
        assert result.report["run_id"] == "run-1"


class TestNullableFromRegistry:
    """R-D: artifact nullability must come from the registry, not hardcoding."""

    def test_nullable_artifact_accepts_null(self, tmp_path):
        """robustness_conclusion (registry nullable:true) may be null."""
        manifest_path, artifact_root, _contents = _build_realistic_setup(tmp_path)
        target = artifact_root / "robustness_conclusion.json"
        target.write_text("null", encoding="utf-8")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for e in manifest["artifacts"]:
            if e["artifact_id"] == "robustness_conclusion":
                e["hash"] = _blake2b_hex(target.read_bytes())
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is True
        assert result.report["robustness_conclusion"] is None

    def test_non_nullable_artifact_rejects_null(self, tmp_path):
        """conditional_conclusion (no nullable flag) must reject null."""
        manifest_path, artifact_root, _contents = _build_realistic_setup(tmp_path)
        target = artifact_root / "conditional_conclusion.json"
        target.write_text("null", encoding="utf-8")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for e in manifest["artifacts"]:
            if e["artifact_id"] == "conditional_conclusion":
                e["hash"] = _blake2b_hex(target.read_bytes())
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "FIELD_SCHEMA_INVALID"

    def test_nullability_follows_registry_mutation(self, tmp_path, monkeypatch):
        """Registry-driven: flipping nullable:true on another artifact makes it
        accept null -- proving no hardcoded artifact set is consulted."""
        import market_game_sim.report.generate as gen
        import market_game_sim.report.manifest as man

        real_load = man.load_registry

        def patched_registry():
            reg = real_load()
            reg["artifacts"]["conditional_conclusion"]["nullable"] = True
            return reg

        monkeypatch.setattr(man, "load_registry", patched_registry)
        monkeypatch.setattr(gen, "load_registry", patched_registry)

        manifest_path, artifact_root, _contents = _build_realistic_setup(tmp_path)
        target = artifact_root / "conditional_conclusion.json"
        target.write_text("null", encoding="utf-8")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for e in manifest["artifacts"]:
            if e["artifact_id"] == "conditional_conclusion":
                e["hash"] = _blake2b_hex(target.read_bytes())
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is True
        assert result.report["conditional_conclusion"] is None


class TestFormatContract:
    """R-A: the registry format is the consumption contract -- every artifact
    is json (JSON table/object); parquet is reserved and not consumable."""

    def test_parquet_declared_manifest_entry_rejected(self, tmp_path):
        """A manifest entry declaring format=parquet (registry says json) must
        fail with FIELD_SCHEMA_INVALID at manifest validation."""
        manifest_path, _root, _contents = _build_realistic_setup(tmp_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for e in manifest["artifacts"]:
            if e["artifact_id"] == "market_metrics":
                e["format"] = "parquet"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "FIELD_SCHEMA_INVALID"

    def test_json_table_artifact_consumed(self, tmp_path):
        """Accepted side: a json table artifact (the only declared format) is
        consumed and appears byte-identical in the report."""
        manifest_path, _root, contents = _build_realistic_setup(tmp_path)
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is True
        assert result.report["metrics"]["market_metrics"] == contents["market_metrics"]
