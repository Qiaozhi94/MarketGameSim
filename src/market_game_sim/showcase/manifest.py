"""T203 (FR-027): showcase bundle manifest.

Separate format from the closed report manifest
(``report/manifest.py::validate_manifest``), which is contractually locked to
3 top-level fields + 10 registry artifacts. A showcase bundle carries a
different artifact set (raw log, ``replay.html``, ``summary.md``, ``RUN.md``)
plus provenance (``code_version`` / ``config_hash`` / ``seed`` /
``evidence_class`` / ``gate``). The shape is declared as the sibling
``showcase_manifest_schema`` section inside ``schema/report_artifacts.json``
(loaded at runtime, never copied into Python). ``evidence_class`` is fixed to
``engineering-demonstration`` for R1 (T203); only R5 (T220) may emit
``formal-research`` and write into ``docs/experiments/``.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any

_SCHEMA_PATH = pathlib.Path(__file__).resolve().parents[1] / "schema" / "report_artifacts.json"

_DIGEST_SIZE = 32  # blake2b digest_size=32 -> 64 hex chars, matches report DIGEST_SIZE

EVIDENCE_CLASSES = frozenset({"engineering-demonstration", "experiment-preview", "formal-research"})


class ShowcaseManifestError(Exception):
    """Raised when a showcase manifest fails structural validation."""


def load_showcase_schema() -> dict[str, Any]:
    """Load the ``showcase_manifest_schema`` section from the registry JSON."""
    registry = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    schema = registry.get("showcase_manifest_schema")
    if not isinstance(schema, dict):
        raise ShowcaseManifestError(
            "showcase_manifest_schema section missing from report_artifacts.json"
        )
    return schema


def _blake2b_hex(data: bytes) -> str:
    h = hashlib.blake2b(digest_size=_DIGEST_SIZE)
    h.update(data)
    return h.hexdigest()


def build_showcase_manifest(
    bundle_dir: str | pathlib.Path,
    artifact_entries: list[dict[str, Any]],
    *,
    artifact_root: str = ".",
    code_version: str,
    config_hash: str,
    seed: int,
    seed_plan: dict[str, Any] | None = None,
    evidence_class: str,
    gate: str,
) -> dict[str, Any]:
    """Build a showcase manifest dict (manifest.json content).

    Each entry in ``artifact_entries`` is ``{artifact_id, path, format,
    producer}``; ``hash_algorithm`` + ``hash`` are computed here over the real
    file bytes at ``bundle_dir / path``. ``artifact_root`` is the value
    written into the manifest (relative to the manifest's own dir, default
    ``"."`` so the bundle is portable) and is decoupled from ``bundle_dir``
    so hashing never depends on the process CWD.

    ``seed_plan`` (R018-C012): the frozen seed plan this bundle derives from
    (e.g. ``{"n_seeds": N, "cells": [...]}``), recorded so a single-seed
    showcase bundle's provenance states its place in the plan rather than
    pretending the scalar ``seed`` is the whole design.
    """
    manifest_dir = pathlib.Path(bundle_dir)
    entries: list[dict[str, Any]] = []
    for entry in artifact_entries:
        path = entry["path"]
        fpath = manifest_dir / path
        entries.append(
            {
                "artifact_id": entry["artifact_id"],
                "path": path,
                "format": entry["format"],
                "producer": entry["producer"],
                "hash_algorithm": "blake2b",
                "hash": _blake2b_hex(fpath.read_bytes()),
            }
        )
    manifest = {
        "manifest_version": 1,
        "artifact_root": artifact_root,
        "artifacts": entries,
        "code_version": code_version,
        "config_hash": config_hash,
        "seed": seed,
        "evidence_class": evidence_class,
        "gate": gate,
    }
    if seed_plan is not None:
        manifest["seed_plan"] = seed_plan
    return manifest


def _check_type(value: Any, type_spec: dict[str, Any]) -> bool:
    t = type_spec["type"]
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "string":
        return isinstance(value, str)
    if t == "array":
        return isinstance(value, list)
    if t == "object":
        return isinstance(value, dict)
    if t == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if t == "boolean":
        return isinstance(value, bool)
    return False


def validate_showcase_manifest(manifest: dict[str, Any]) -> None:
    """Validate a showcase manifest dict against ``showcase_manifest_schema``.

    Closed-field check: the manifest must declare exactly the schema's
    top-level fields and each artifact exactly the 6 item fields, so a
    producer cannot silently drop provenance or smuggle in undeclared keys.
    """
    schema = load_showcase_schema()
    top_spec: dict[str, Any] = schema["top_level_fields"]
    # R018-C012: ``seed_plan`` is optional (present only when the bundle
    # derives from a frozen plan); the other top-level fields are required.
    optional_fields = {k for k, v in top_spec.items() if v.get("optional")}
    expected_top = set(top_spec.keys()) - optional_fields
    actual_top = set(manifest.keys()) - optional_fields
    if actual_top != expected_top:
        missing = sorted(expected_top - actual_top)
        extra = sorted(actual_top - expected_top)
        raise ShowcaseManifestError(
            f"showcase manifest top-level fields mismatch: missing={missing}, extra={extra}"
        )

    for fname, fspec in top_spec.items():
        if fname not in manifest:
            continue
        if not _check_type(manifest[fname], fspec):
            raise ShowcaseManifestError(
                f"showcase manifest field '{fname}' must be {fspec['type']}"
            )

    ev_spec = top_spec["evidence_class"]
    allowed = set(ev_spec.get("enum", []))
    if manifest["evidence_class"] not in allowed:
        raise ShowcaseManifestError(
            f"evidence_class must be one of {sorted(allowed)}, got {manifest['evidence_class']!r}"
        )

    artifacts = manifest["artifacts"]
    item_spec = top_spec["artifacts"].get("item_fields", {})
    expected_items = set(item_spec.keys())
    for i, entry in enumerate(artifacts):
        actual_items = set(entry.keys())
        if actual_items != expected_items:
            missing = sorted(expected_items - actual_items)
            extra = sorted(actual_items - expected_items)
            raise ShowcaseManifestError(
                f"showcase manifest artifacts[{i}] item fields mismatch: "
                f"missing={missing}, extra={extra}"
            )
        if entry["hash_algorithm"] != "blake2b":
            raise ShowcaseManifestError(
                f"artifacts[{i}].hash_algorithm must be 'blake2b', got {entry['hash_algorithm']!r}"
            )
        h = entry["hash"]
        hex_len = item_spec["hash"].get("hex_length")
        if not isinstance(h, str) or len(h) != hex_len:
            raise ShowcaseManifestError(
                f"artifacts[{i}].hash must be {hex_len} lowercase hex chars"
            )
        if not all(c in "0123456789abcdef" for c in h):
            raise ShowcaseManifestError(f"artifacts[{i}].hash must be lowercase hex")


def write_showcase_manifest(manifest: dict[str, Any], path: str | pathlib.Path) -> pathlib.Path:
    """Validate then write ``manifest.json`` (sorted keys) to ``path``."""
    validate_showcase_manifest(manifest)
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return p
