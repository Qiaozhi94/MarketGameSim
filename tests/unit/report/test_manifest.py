"""T302 (spec §4.1, E4): artifact manifest validation.

Tests BOTH the accept and reject sides of every validation branch:

- **Accept**: a valid manifest with all 10 artifacts validates and
  ``build_report`` succeeds (``failure`` is ``null``).
- **Reject**: each of the 5 failure classes (missing artifact / hash
  mismatch / schema_version wrong / field schema invalid incl.
  ``hash_algorithm != blake2b`` / undeclared extra file) makes
  ``build_report`` fail with the correct ``failure.code``.

Also covers format/producer mismatch, unknown artifact_id, duplicate
artifact_id, and a multi-artifact batch case (all 10 processed together).
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any

import pytest

from market_game_sim.report.generate import build_report
from market_game_sim.report.manifest import load_registry

_REGISTRY = load_registry()
_REGISTRY_IDS = sorted(_REGISTRY["artifacts"].keys())


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
    fields = _build_fields(spec["required_fields"], aid)
    if spec["shape"] == "table":
        return [fields]
    return fields


def _write_artifacts(artifact_root: pathlib.Path) -> None:
    for aid in _REGISTRY_IDS:
        spec = _REGISTRY["artifacts"][aid]
        content = _make_content(aid, spec)
        (artifact_root / f"{aid}.json").write_text(
            json.dumps(content, sort_keys=True), encoding="utf-8"
        )


def _valid_entries(artifact_root: pathlib.Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for aid in _REGISTRY_IDS:
        spec = _REGISTRY["artifacts"][aid]
        fpath = artifact_root / f"{aid}.json"
        entries.append(
            {
                "artifact_id": aid,
                "path": f"{aid}.json",
                "format": spec["format"],
                "schema_version": spec["schema_version"],
                "producer": spec["producer"],
                "hash_algorithm": "blake2b",
                "hash": _blake2b_hex(fpath.read_bytes()),
            }
        )
    return entries


def _build_manifest(artifact_root_rel: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "manifest_version": 1,
        "artifact_root": artifact_root_rel,
        "artifacts": entries,
    }


def _write_manifest(tmp_path: pathlib.Path, manifest: dict[str, Any]) -> pathlib.Path:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def _setup_valid(
    tmp_path: pathlib.Path,
) -> tuple[pathlib.Path, pathlib.Path, list[dict[str, Any]]]:
    """Create a valid artifact set + manifest. Returns (manifest_path, artifact_root, entries)."""
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    _write_artifacts(artifact_root)
    entries = _valid_entries(artifact_root)
    manifest_path = _write_manifest(tmp_path, _build_manifest("artifacts", entries))
    return manifest_path, artifact_root, entries


# ---------------------------------------------------------------------------
# Accept side: valid manifest
# ---------------------------------------------------------------------------


class TestValidManifest:
    def test_valid_manifest_with_10_artifacts_succeeds(self, tmp_path):
        manifest_path, _artifact_root, _entries = _setup_valid(tmp_path)
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is True
        assert result.report["failure"] is None
        assert result.exit_code == 0

    def test_all_business_fields_populated_on_success(self, tmp_path):
        manifest_path, _artifact_root, _entries = _setup_valid(tmp_path)
        result = build_report(manifest_path, tmp_path / "out")
        assert result.report["metrics"] is not None
        assert result.report["conditional_conclusion"] is not None
        assert result.report["negative_results"] is not None

    def test_artifact_root_absolute_path_also_works(self, tmp_path):
        """artifact_root can be absolute (design.md §4)."""
        artifact_root = tmp_path / "artifacts"
        artifact_root.mkdir()
        _write_artifacts(artifact_root)
        entries = _valid_entries(artifact_root)
        manifest = _build_manifest(str(artifact_root.resolve()), entries)
        manifest_path = _write_manifest(tmp_path, manifest)
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is True
        assert result.report["failure"] is None


# ---------------------------------------------------------------------------
# Reject side: 5 failure classes
# ---------------------------------------------------------------------------


class TestMissingArtifact:
    def test_missing_artifact_entry_fails(self, tmp_path):
        """Manifest omits one of the 10 required artifact_ids -> MISSING_ARTIFACT."""
        manifest_path, _artifact_root, entries = _setup_valid(tmp_path)
        entries_missing = [e for e in entries if e["artifact_id"] != "market_metrics"]
        manifest_path = _write_manifest(tmp_path, _build_manifest("artifacts", entries_missing))
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "MISSING_ARTIFACT"
        assert result.report["failure"]["artifact_id"] == "market_metrics"
        assert result.exit_code == 1

    def test_artifact_file_not_found_fails(self, tmp_path):
        """Declared artifact file doesn't exist on disk -> MISSING_ARTIFACT."""
        manifest_path, artifact_root, _entries = _setup_valid(tmp_path)
        (artifact_root / "market_metrics.json").unlink()
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "MISSING_ARTIFACT"
        assert result.report["failure"]["artifact_id"] == "market_metrics"


class TestHashMismatch:
    def test_hash_mismatch_fails(self, tmp_path):
        """File content changed after manifest was written -> HASH_MISMATCH."""
        manifest_path, artifact_root, _entries = _setup_valid(tmp_path)
        target = artifact_root / "market_metrics.json"
        target.write_text(json.dumps({"corrupted": True}), encoding="utf-8")
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "HASH_MISMATCH"
        assert result.report["failure"]["artifact_id"] == "market_metrics"

    def test_declared_hash_wrong_fails(self, tmp_path):
        """Declared hash string is wrong -> HASH_MISMATCH."""
        manifest_path, _artifact_root, entries = _setup_valid(tmp_path)
        for e in entries:
            if e["artifact_id"] == "agent_metrics":
                e["hash"] = "0" * 64
        manifest_path = _write_manifest(tmp_path, _build_manifest("artifacts", entries))
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "HASH_MISMATCH"
        assert result.report["failure"]["artifact_id"] == "agent_metrics"


class TestSchemaVersionMismatch:
    def test_schema_version_wrong_fails(self, tmp_path):
        """Declared schema_version differs from registry -> SCHEMA_VERSION_MISMATCH."""
        manifest_path, _artifact_root, entries = _setup_valid(tmp_path)
        for e in entries:
            if e["artifact_id"] == "market_metrics":
                e["schema_version"] = 999
        manifest_path = _write_manifest(tmp_path, _build_manifest("artifacts", entries))
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "SCHEMA_VERSION_MISMATCH"
        assert result.report["failure"]["artifact_id"] == "market_metrics"


class TestFieldSchemaInvalid:
    def test_hash_algorithm_not_blake2b_fails(self, tmp_path):
        manifest_path, _artifact_root, entries = _setup_valid(tmp_path)
        for e in entries:
            if e["artifact_id"] == "market_metrics":
                e["hash_algorithm"] = "sha256"
        manifest_path = _write_manifest(tmp_path, _build_manifest("artifacts", entries))
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "FIELD_SCHEMA_INVALID"
        assert result.report["failure"]["artifact_id"] == "market_metrics"

    def test_missing_required_field_fails(self, tmp_path):
        """Removing a field from an entry -> FIELD_SCHEMA_INVALID."""
        manifest_path, _artifact_root, entries = _setup_valid(tmp_path)
        for e in entries:
            if e["artifact_id"] == "market_metrics":
                del e["hash"]
        manifest_path = _write_manifest(tmp_path, _build_manifest("artifacts", entries))
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "FIELD_SCHEMA_INVALID"

    def test_wrong_type_field_fails(self, tmp_path):
        """schema_version as string instead of int -> FIELD_SCHEMA_INVALID."""
        manifest_path, _artifact_root, entries = _setup_valid(tmp_path)
        for e in entries:
            if e["artifact_id"] == "market_metrics":
                e["schema_version"] = "1"
        manifest_path = _write_manifest(tmp_path, _build_manifest("artifacts", entries))
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "FIELD_SCHEMA_INVALID"

    def test_hash_not_64_chars_fails(self, tmp_path):
        manifest_path, _artifact_root, entries = _setup_valid(tmp_path)
        for e in entries:
            if e["artifact_id"] == "market_metrics":
                e["hash"] = "abc123"
        manifest_path = _write_manifest(tmp_path, _build_manifest("artifacts", entries))
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "FIELD_SCHEMA_INVALID"

    def test_hash_uppercase_hex_fails(self, tmp_path):
        manifest_path, _artifact_root, entries = _setup_valid(tmp_path)
        for e in entries:
            if e["artifact_id"] == "market_metrics":
                e["hash"] = e["hash"].upper()
        manifest_path = _write_manifest(tmp_path, _build_manifest("artifacts", entries))
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "FIELD_SCHEMA_INVALID"

    def test_extra_item_field_fails(self, tmp_path):
        """An 8th field on an artifact entry -> FIELD_SCHEMA_INVALID."""
        manifest_path, _artifact_root, entries = _setup_valid(tmp_path)
        for e in entries:
            if e["artifact_id"] == "market_metrics":
                e["extra_field"] = "bad"
        manifest_path = _write_manifest(tmp_path, _build_manifest("artifacts", entries))
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "FIELD_SCHEMA_INVALID"

    def test_format_mismatch_fails(self, tmp_path):
        manifest_path, _artifact_root, entries = _setup_valid(tmp_path)
        for e in entries:
            if e["artifact_id"] == "market_metrics":
                e["format"] = "parquet"  # registry declares json for this artifact
        manifest_path = _write_manifest(tmp_path, _build_manifest("artifacts", entries))
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "FIELD_SCHEMA_INVALID"

    def test_producer_mismatch_fails(self, tmp_path):
        manifest_path, _artifact_root, entries = _setup_valid(tmp_path)
        for e in entries:
            if e["artifact_id"] == "market_metrics":
                e["producer"] = "wrong-producer"
        manifest_path = _write_manifest(tmp_path, _build_manifest("artifacts", entries))
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "FIELD_SCHEMA_INVALID"

    def test_unknown_artifact_id_fails(self, tmp_path):
        manifest_path, _artifact_root, entries = _setup_valid(tmp_path)
        for e in entries:
            if e["artifact_id"] == "market_metrics":
                e["artifact_id"] = "nonexistent_artifact"
        manifest_path = _write_manifest(tmp_path, _build_manifest("artifacts", entries))
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "FIELD_SCHEMA_INVALID"

    def test_duplicate_artifact_id_fails(self, tmp_path):
        manifest_path, _artifact_root, entries = _setup_valid(tmp_path)
        for e in entries:
            if e["artifact_id"] == "agent_metrics":
                dup = dict(e)
                dup["artifact_id"] = "market_metrics"
                dup["path"] = "market_metrics.json"
                dup["hash"] = _blake2b_hex((_artifact_root / "market_metrics.json").read_bytes())
                entries.append(dup)
                break
        entries = [e for e in entries if e["artifact_id"] != "agent_metrics"]
        manifest_path = _write_manifest(tmp_path, _build_manifest("artifacts", entries))
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "FIELD_SCHEMA_INVALID"

    def test_top_level_extra_field_fails(self, tmp_path):
        manifest_path, _artifact_root, entries = _setup_valid(tmp_path)
        manifest = _build_manifest("artifacts", entries)
        manifest["extra_top_field"] = "bad"
        manifest_path = _write_manifest(tmp_path, manifest)
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "FIELD_SCHEMA_INVALID"

    def test_top_level_missing_field_fails(self, tmp_path):
        manifest_path, _artifact_root, entries = _setup_valid(tmp_path)
        manifest = _build_manifest("artifacts", entries)
        del manifest["manifest_version"]
        manifest_path = _write_manifest(tmp_path, manifest)
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "FIELD_SCHEMA_INVALID"

    def test_manifest_version_wrong_type_fails(self, tmp_path):
        manifest_path, _artifact_root, entries = _setup_valid(tmp_path)
        manifest = _build_manifest("artifacts", entries)
        manifest["manifest_version"] = "1"
        manifest_path = _write_manifest(tmp_path, manifest)
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "FIELD_SCHEMA_INVALID"


class TestUndeclaredExtraFile:
    def test_undeclared_extra_file_fails(self, tmp_path):
        manifest_path, artifact_root, _entries = _setup_valid(tmp_path)
        (artifact_root / "extra_file.json").write_text("{}", encoding="utf-8")
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "UNDECLARED_EXTRA_FILE"
        assert result.report["failure"]["artifact_id"] == "extra_file.json"

    def test_undeclared_extra_file_in_subdirectory_fails(self, tmp_path):
        manifest_path, artifact_root, _entries = _setup_valid(tmp_path)
        sub = artifact_root / "subdir"
        sub.mkdir()
        (sub / "extra.json").write_text("{}", encoding="utf-8")
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "UNDECLARED_EXTRA_FILE"
        assert result.report["failure"]["artifact_id"] == "subdir/extra.json"


# ---------------------------------------------------------------------------
# Multi-artifact batch case (all 10 processed together)
# ---------------------------------------------------------------------------


class TestMultiArtifactBatch:
    def test_all_10_artifacts_consumed_together(self, tmp_path):
        """Batch case: all 10 artifacts present and valid -> all consumed."""
        manifest_path, _artifact_root, _entries = _setup_valid(tmp_path)
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is True
        assert set(result.report["metrics"].keys()) == {
            "market_metrics",
            "agent_metrics",
            "liquidation_metrics",
            "pnl_bridge",
            "sample_classification",
            "effect_sizes",
            "robustness_effects",
        }
        assert result.report["conditional_conclusion"] is not None
        assert result.report["robustness_conclusion"] is not None
        assert result.report["negative_results"] is not None

    def test_any_single_artifact_corruption_breaks_batch(self, tmp_path):
        """Corrupting any one of the 10 artifacts makes the whole batch fail."""
        manifest_path, artifact_root, _entries = _setup_valid(tmp_path)
        for aid in _REGISTRY_IDS:
            target = artifact_root / f"{aid}.json"
            original = target.read_bytes()
            target.write_bytes(original + b" ")
            result = build_report(manifest_path, tmp_path / f"out_{aid}")
            assert result.success is False, f"{aid} corruption should fail"
            assert result.report["failure"]["code"] == "HASH_MISMATCH"
            assert result.report["failure"]["artifact_id"] == aid
            target.write_bytes(original)


# ---------------------------------------------------------------------------
# R3: path confinement -- artifact paths must not escape artifact_root
# ---------------------------------------------------------------------------


class TestPathConfinement:
    def test_absolute_path_fails(self, tmp_path):
        """An absolute path entry -> FIELD_SCHEMA_INVALID."""
        manifest_path, _artifact_root, entries = _setup_valid(tmp_path)
        abs_path = str((tmp_path / "artifacts" / "market_metrics.json").resolve())
        for e in entries:
            if e["artifact_id"] == "market_metrics":
                e["path"] = abs_path
        manifest_path = _write_manifest(tmp_path, _build_manifest("artifacts", entries))
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "FIELD_SCHEMA_INVALID"
        assert result.report["failure"]["artifact_id"] == "market_metrics"

    def test_traversal_path_fails(self, tmp_path):
        """A ``../outside`` path -> FIELD_SCHEMA_INVALID (file not consumed)."""
        manifest_path, artifact_root, entries = _setup_valid(tmp_path)
        outside = tmp_path / "outside.json"
        outside.write_text(json.dumps({"outside": True}), encoding="utf-8")
        for e in entries:
            if e["artifact_id"] == "market_metrics":
                e["path"] = "../outside.json"
                e["hash"] = _blake2b_hex(outside.read_bytes())
        manifest_path = _write_manifest(tmp_path, _build_manifest("artifacts", entries))
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "FIELD_SCHEMA_INVALID"
        assert result.report["failure"]["artifact_id"] == "market_metrics"

    def test_valid_relative_path_inside_root_succeeds(self, tmp_path):
        """A valid relative path inside root -> succeeds (accept side)."""
        manifest_path, _artifact_root, _entries = _setup_valid(tmp_path)
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is True
        assert result.report["failure"] is None

    def test_multi_entry_one_path_escapes_fails(self, tmp_path):
        """Batch: one path escapes, others valid -> fails (batch case)."""
        manifest_path, artifact_root, entries = _setup_valid(tmp_path)
        outside = tmp_path / "outside.json"
        outside.write_text(json.dumps({"outside": True}), encoding="utf-8")
        for e in entries:
            if e["artifact_id"] == "pnl_bridge":
                e["path"] = "../outside.json"
                e["hash"] = _blake2b_hex(outside.read_bytes())
        manifest_path = _write_manifest(tmp_path, _build_manifest("artifacts", entries))
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["failure"]["code"] == "FIELD_SCHEMA_INVALID"
        assert result.report["failure"]["artifact_id"] == "pnl_bridge"


# ---------------------------------------------------------------------------
# Failure report structure on failure
# ---------------------------------------------------------------------------


class TestFailureReportStructure:
    def test_failure_report_has_all_null_business_fields(self, tmp_path):
        """On failure, all business fields must be null (two-state, no partial)."""
        manifest_path, _artifact_root, entries = _setup_valid(tmp_path)
        entries_missing = [e for e in entries if e["artifact_id"] != "market_metrics"]
        manifest_path = _write_manifest(tmp_path, _build_manifest("artifacts", entries_missing))
        result = build_report(manifest_path, tmp_path / "out")
        assert result.success is False
        assert result.report["metrics"] is None
        assert result.report["conditional_conclusion"] is None
        assert result.report["robustness_conclusion"] is None
        assert result.report["negative_results"] is None
        assert result.report["failure"] is not None

    def test_failure_report_has_manifest_hash_and_generated_at(self, tmp_path):
        """Even on failure, manifest_hash and generated_at are populated."""
        manifest_path, _artifact_root, entries = _setup_valid(tmp_path)
        entries_missing = [e for e in entries if e["artifact_id"] != "market_metrics"]
        manifest = _build_manifest("artifacts", entries_missing)
        manifest_path = _write_manifest(tmp_path, manifest)
        result = build_report(manifest_path, tmp_path / "out")
        expected_hash = _blake2b_hex(manifest_path.read_bytes())
        assert result.report["manifest_hash"] == expected_hash
        assert len(result.report["generated_at"]) > 0

    def test_failure_report_files_written(self, tmp_path):
        """Both report.json and report.md are written even on failure."""
        manifest_path, _artifact_root, entries = _setup_valid(tmp_path)
        entries_missing = [e for e in entries if e["artifact_id"] != "market_metrics"]
        manifest_path = _write_manifest(tmp_path, _build_manifest("artifacts", entries_missing))
        out_dir = tmp_path / "out"
        build_report(manifest_path, out_dir)
        assert (out_dir / "report.json").is_file()
        assert (out_dir / "report.md").is_file()


# ---------------------------------------------------------------------------
# R-B: empty table semantics (unit-level, via validate_artifact_value)
# ---------------------------------------------------------------------------


class TestTableEmptySemantics:
    """R-B: empty [] is a legal table; empty {} is not (not a list)."""

    def test_empty_list_valid_for_table(self):
        from market_game_sim.report.manifest import validate_artifact_value

        spec = _REGISTRY["artifacts"]["market_metrics"]
        validate_artifact_value([], spec, "market_metrics")

    def test_empty_object_invalid_for_table(self):
        from market_game_sim.report.manifest import ArtifactSchemaError, validate_artifact_value

        spec = _REGISTRY["artifacts"]["market_metrics"]
        with pytest.raises(ArtifactSchemaError):
            validate_artifact_value({}, spec, "market_metrics")

    def test_single_row_valid_for_table(self):
        from market_game_sim.report.manifest import validate_artifact_value

        spec = _REGISTRY["artifacts"]["market_metrics"]
        row = _build_fields(spec["required_fields"], "market_metrics")
        validate_artifact_value([row], spec, "market_metrics")

    def test_multi_row_valid_for_table(self):
        from market_game_sim.report.manifest import validate_artifact_value

        spec = _REGISTRY["artifacts"]["market_metrics"]
        row = _build_fields(spec["required_fields"], "market_metrics")
        validate_artifact_value([row, dict(row)], spec, "market_metrics")


# ---------------------------------------------------------------------------
# R-D: nullability driven by registry (unit-level)
# ---------------------------------------------------------------------------


class TestNullableRegistryDriven:
    """R-D: nullability comes from the registry spec, not a hardcoded set."""

    def test_nullable_artifact_accepts_null(self):
        from market_game_sim.report.manifest import validate_artifact_value

        spec = _REGISTRY["artifacts"]["robustness_conclusion"]
        validate_artifact_value(None, spec, "robustness_conclusion")

    def test_non_nullable_artifact_rejects_null(self):
        from market_game_sim.report.manifest import ArtifactSchemaError, validate_artifact_value

        spec = _REGISTRY["artifacts"]["conditional_conclusion"]
        with pytest.raises(
            ArtifactSchemaError, match="null but registry does not declare nullable"
        ):
            validate_artifact_value(None, spec, "conditional_conclusion")

    def test_nullability_follows_registry_spec(self):
        """Mutating the registry spec's nullable flag flips behavior."""
        from market_game_sim.report.manifest import ArtifactSchemaError, validate_artifact_value

        spec = _REGISTRY["artifacts"]["conditional_conclusion"]
        assert not spec.get("nullable", False)
        with pytest.raises(ArtifactSchemaError):
            validate_artifact_value(None, spec, "conditional_conclusion")

        mutated = dict(spec)
        mutated["nullable"] = True
        validate_artifact_value(None, mutated, "conditional_conclusion")
