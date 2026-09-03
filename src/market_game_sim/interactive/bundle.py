"""Closed manifest contract for H1 interactive engineering bundles."""

from __future__ import annotations

import hashlib
import pathlib
from collections.abc import Mapping, Sequence
from typing import Any

from market_game_sim.config.serialization import canonical_serialize

MANIFEST_FIELDS = {
    "manifest_version",
    "run_mode",
    "evidence_class",
    "schema_version",
    "input_schema_version",
    "session_id",
    "client_version",
    "code_version",
    "config_hash",
    "seed",
    "input_hash",
    "event_summary_hash",
    "frame_hash",
    "termination_state",
    "abort_code",
    "artifacts",
}
ARTIFACT_FIELDS = {"artifact_id", "path", "sha256"}
ARTIFACT_IDS = {"run_doc", "input_journal", "event_log", "replay"}


class InteractiveManifestError(ValueError):
    """Raised when an H1 bundle manifest is incomplete or unsafe."""


def build_interactive_manifest(
    bundle_dir: str | pathlib.Path,
    artifact_paths: Mapping[str, str],
    *,
    session_id: str,
    client_version: str,
    code_version: str,
    config_hash: str,
    seed: int,
    input_hash: str,
    event_summary_hash: str,
    frame_hash: str,
    termination_state: str,
    abort_code: str | None,
) -> dict[str, Any]:
    root = pathlib.Path(bundle_dir).resolve()
    if set(artifact_paths) != ARTIFACT_IDS:
        raise InteractiveManifestError("interactive artifact ids differ from the contract")
    artifacts = []
    for artifact_id, relative in sorted(artifact_paths.items()):
        path = _resolve_artifact(root, relative)
        if not path.is_file():
            raise InteractiveManifestError(f"missing interactive artifact: {relative}")
        artifacts.append(
            {
                "artifact_id": artifact_id,
                "path": relative,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    manifest = {
        "manifest_version": 1,
        "run_mode": "interactive",
        "evidence_class": "engineering-demonstration",
        "schema_version": 4,
        "input_schema_version": 1,
        "session_id": session_id,
        "client_version": client_version,
        "code_version": code_version,
        "config_hash": config_hash,
        "seed": seed,
        "input_hash": input_hash,
        "event_summary_hash": event_summary_hash,
        "frame_hash": frame_hash,
        "termination_state": termination_state,
        "abort_code": abort_code,
        "artifacts": artifacts,
    }
    validate_interactive_manifest(manifest, root)
    return manifest


def validate_interactive_manifest(
    manifest: Mapping[str, Any], bundle_dir: str | pathlib.Path | None = None
) -> None:
    if set(manifest) != MANIFEST_FIELDS:
        raise InteractiveManifestError("interactive manifest fields differ from the contract")
    fixed = {
        "manifest_version": 1,
        "run_mode": "interactive",
        "evidence_class": "engineering-demonstration",
        "schema_version": 4,
        "input_schema_version": 1,
        "seed": 7,
    }
    for field, expected in fixed.items():
        if type(manifest[field]) is not type(expected) or manifest[field] != expected:
            raise InteractiveManifestError(f"manifest.{field} must be {expected!r}")
    for field in ("session_id", "client_version", "code_version", "config_hash"):
        if not isinstance(manifest[field], str) or not manifest[field]:
            raise InteractiveManifestError(f"manifest.{field} must be a non-empty string")
    for field in ("input_hash", "event_summary_hash", "frame_hash"):
        _require_sha256(manifest[field], f"manifest.{field}")
    termination = manifest["termination_state"]
    if termination not in {"COMPLETED", "ABORTED"}:
        raise InteractiveManifestError("manifest.termination_state must be COMPLETED or ABORTED")
    abort_code = manifest["abort_code"]
    if termination == "COMPLETED" and abort_code is not None:
        raise InteractiveManifestError("completed manifest.abort_code must be null")
    if termination == "ABORTED" and (not isinstance(abort_code, str) or not abort_code):
        raise InteractiveManifestError("aborted manifest.abort_code must be non-empty")
    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, Sequence) or isinstance(artifacts, (str, bytes)):
        raise InteractiveManifestError("manifest.artifacts must be an array")
    ids: set[str] = set()
    root = pathlib.Path(bundle_dir).resolve() if bundle_dir is not None else None
    for entry in artifacts:
        if not isinstance(entry, Mapping) or set(entry) != ARTIFACT_FIELDS:
            raise InteractiveManifestError("manifest artifact fields differ from the contract")
        artifact_id = entry["artifact_id"]
        relative = entry["path"]
        if not isinstance(artifact_id, str) or not isinstance(relative, str):
            raise InteractiveManifestError("artifact id and path must be strings")
        if artifact_id in ids:
            raise InteractiveManifestError("manifest artifact ids must be unique")
        ids.add(artifact_id)
        _require_sha256(entry["sha256"], f"artifact {artifact_id}.sha256")
        if root is not None:
            path = _resolve_artifact(root, relative)
            if (
                not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]
            ):
                raise InteractiveManifestError(f"artifact {artifact_id} content hash mismatch")
    if ids != ARTIFACT_IDS:
        raise InteractiveManifestError("interactive manifest artifact ids differ from the contract")


def write_interactive_manifest(manifest: Mapping[str, Any], path: str | pathlib.Path) -> None:
    validate_interactive_manifest(manifest, pathlib.Path(path).parent)
    pathlib.Path(path).write_bytes(canonical_serialize(dict(manifest)) + b"\n")


def _resolve_artifact(root: pathlib.Path, relative: str) -> pathlib.Path:
    candidate = pathlib.PurePosixPath(relative)
    if candidate.is_absolute() or ".." in candidate.parts or len(candidate.parts) != 1:
        raise InteractiveManifestError(
            f"artifact path must be one safe relative filename: {relative!r}"
        )
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root):
        raise InteractiveManifestError(f"artifact path escapes bundle: {relative!r}")
    return resolved


def _require_sha256(value: object, label: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise InteractiveManifestError(f"{label} must be 64 lowercase hexadecimal characters")
