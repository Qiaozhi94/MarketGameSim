"""T302: Artifact manifest validation.

Validates a manifest file against the ``report_artifacts.json`` registry
(loaded at runtime -- the field schema is NOT copied).  Enforces:

- Top-level closed fields: ``manifest_version`` / ``artifact_root`` / ``artifacts``.
- Each artifact element declares exactly 7 closed fields.
- ``artifact_root`` is the ONLY source of the artifact root (no CLI param).
- ``artifacts`` declares exactly the 10 registry artifact_ids, one each.
- ``format`` / ``schema_version`` / ``producer`` match the registry.
- ``hash_algorithm`` is exactly ``blake2b`` (registry enum).
- ``hash`` is 64 lowercase hex chars (registry hex_length + charset).
- ``blake2b(digest_size=32)`` of each file matches the declared hash.
- No undeclared extra files under ``artifact_root``.

Five failure classes (design.md §4 ``failure.code``):

- ``MISSING_ARTIFACT`` -- a registry artifact_id is not declared, or its
  file does not exist.
- ``HASH_MISMATCH`` -- computed hash differs from the declared hash.
- ``SCHEMA_VERSION_MISMATCH`` -- declared ``schema_version`` differs from
  the registry.
- ``FIELD_SCHEMA_INVALID`` -- missing or wrong-type field, unknown
  artifact_id, ``hash_algorithm != blake2b``, format/producer mismatch,
  bad hash format, or extra/missing top-level/item fields.
- ``UNDECLARED_EXTRA_FILE`` -- a regular file under ``artifact_root`` is
  not declared in any manifest entry's ``path``.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Registry loading
# ---------------------------------------------------------------------------

_REGISTRY_PATH = pathlib.Path(__file__).resolve().parents[1] / "schema" / "report_artifacts.json"


def load_registry() -> dict[str, Any]:
    """Load the artifact registry from ``report_artifacts.json`` at runtime.

    The field schema is read from this JSON -- it is never copied into
    Python source.  This is the single machine truth for manifest field
    names, types, enums, and per-artifact format/schema_version/producer.
    """
    return json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

DIGEST_SIZE = 32  # blake2b digest_size=32, same as eventlog/digest.py (KPI-002)


def compute_file_hash(path: pathlib.Path) -> str:
    """Compute ``blake2b(digest_size=32)`` hex digest of a file's bytes.

    Returns a 64-character lowercase hex string.
    """
    h = hashlib.blake2b(digest_size=DIGEST_SIZE)
    h.update(path.read_bytes())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Failure
# ---------------------------------------------------------------------------

#: The five closed failure codes (design.md §4).
FAILURE_CODES = frozenset(
    {
        "MISSING_ARTIFACT",
        "HASH_MISMATCH",
        "SCHEMA_VERSION_MISMATCH",
        "FIELD_SCHEMA_INVALID",
        "UNDECLARED_EXTRA_FILE",
    }
)


class ManifestError(Exception):
    """Raised when manifest validation fails.

    Carries the structured failure info (``code`` / ``artifact_id`` /
    ``message``) that becomes ``report.json.failure``.
    """

    def __init__(self, code: str, artifact_id: str, message: str) -> None:
        if code not in FAILURE_CODES:
            raise ValueError(f"unknown failure code: {code}")
        self.code = code
        self.artifact_id = artifact_id
        self.message = message
        super().__init__(f"[{code}] {artifact_id}: {message}")


class ArtifactReadError(Exception):
    """Raised when an artifact file cannot be read or decoded.

    Carries ``artifact_id`` and ``message`` for failure normalization
    into the two-state report contract (mapped to ``FIELD_SCHEMA_INVALID``
    in :func:`build_report`).
    """

    def __init__(self, artifact_id: str, message: str) -> None:
        self.artifact_id = artifact_id
        self.message = message
        super().__init__(f"cannot read artifact '{artifact_id}': {message}")


class ArtifactSchemaError(Exception):
    """Raised when an artifact value fails validation against the registry spec.

    Carries ``artifact_id`` and ``message`` for failure normalization
    into the two-state report contract (mapped to ``FIELD_SCHEMA_INVALID``
    in :func:`build_report`).
    """

    def __init__(self, artifact_id: str, message: str) -> None:
        self.artifact_id = artifact_id
        self.message = message
        super().__init__(f"schema invalid for artifact '{artifact_id}': {message}")


# ---------------------------------------------------------------------------
# Validated manifest data
# ---------------------------------------------------------------------------


@dataclass
class ManifestData:
    """Result of a successful ``validate_manifest`` call."""

    manifest: dict[str, Any]
    artifact_root: pathlib.Path
    entries: dict[str, dict[str, Any]]
    declared_paths: set[str]


# ---------------------------------------------------------------------------
# Type checking (driven by registry type strings)
# ---------------------------------------------------------------------------

_LOWERCASE_HEX = set("0123456789abcdef")


def _check_type(value: Any, type_spec: dict[str, Any]) -> bool:
    """Check ``value`` against a registry type spec.

    Handles ``integer`` (excluding ``bool``), ``string``, ``array``,
    ``object``, ``number``, ``boolean``.
    """
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


#: Artifact-level nullability is declared ONLY in the registry
#: (``report_artifacts.json`` per-artifact ``"nullable": true``, e.g.
#: ``robustness_conclusion`` per design.md §4 "对象或 null").  No artifact
#: nullability is hardcoded here (R-D) -- the registry is the single truth.
#: Missing ``nullable`` defaults to false.


def validate_artifact_value(value: Any, spec: dict[str, Any], artifact_id: str) -> None:
    """Validate an artifact value against its registry spec.

    Checks:
    - shape "object": value is a dict (or null if the registry declares
      the artifact ``nullable: true``).
    - shape "table": value is a list of row dicts (empty ``[]`` is valid).
    - Every ``required_fields`` field present with the correct type,
      honoring ``nullable: true``.
    - Nested object ``required_fields`` and array ``item_fields`` recursively.
    - ``item_type`` for array items; ``additional_value_type`` for map values.
    - Payload's ``schema_version`` (if in required_fields) equals the
      registry artifact's ``schema_version``.

    Raises :class:`ArtifactSchemaError` on any validation failure.
    """
    is_nullable = bool(spec.get("nullable", False))
    if value is None:
        if is_nullable:
            return
        raise ArtifactSchemaError(
            artifact_id, "artifact value is null but registry does not declare nullable"
        )

    shape = spec.get("shape")
    required_fields = spec.get("required_fields", {})
    expected_sv = spec.get("schema_version")

    if shape == "object":
        if not isinstance(value, dict):
            raise ArtifactSchemaError(
                artifact_id,
                f"shape 'object' requires a JSON object, got {type(value).__name__}",
            )
        _validate_object_fields(value, required_fields, artifact_id, "")
        _validate_payload_schema_version(value, required_fields, expected_sv, artifact_id, "")
    elif shape == "table":
        if not isinstance(value, list):
            raise ArtifactSchemaError(
                artifact_id,
                f"shape 'table' requires a JSON array of row objects, got {type(value).__name__}",
            )
        for i, row in enumerate(value):
            if not isinstance(row, dict):
                raise ArtifactSchemaError(
                    artifact_id,
                    f"row [{i}] must be a JSON object, got {type(row).__name__}",
                )
            _validate_object_fields(row, required_fields, artifact_id, f"row[{i}].")
            _validate_payload_schema_version(
                row, required_fields, expected_sv, artifact_id, f"row[{i}]."
            )
    else:
        raise ArtifactSchemaError(artifact_id, f"unknown shape '{shape}'")


def _validate_object_fields(
    obj: dict[str, Any],
    fields_spec: dict[str, Any],
    artifact_id: str,
    prefix: str,
) -> None:
    for fname, fspec in fields_spec.items():
        loc = f"{prefix}{fname}"
        if fname not in obj:
            raise ArtifactSchemaError(artifact_id, f"{loc}: required field missing")
        _validate_field_value(obj[fname], fspec, artifact_id, loc)


def _validate_field_value(
    value: Any,
    fspec: dict[str, Any],
    artifact_id: str,
    loc: str,
) -> None:
    if value is None:
        if fspec.get("nullable", False):
            return
        raise ArtifactSchemaError(artifact_id, f"{loc}: field is null but not nullable")

    t = fspec.get("type")
    if not _check_type(value, fspec):
        raise ArtifactSchemaError(artifact_id, f"{loc}: must be {t}, got {type(value).__name__}")

    if t == "array":
        item_type = fspec.get("item_type")
        item_fields = fspec.get("item_fields")
        for i, item in enumerate(value):
            item_loc = f"{loc}[{i}]"
            item_spec: dict[str, Any] = {"type": item_type}
            if item_fields is not None:
                item_spec["required_fields"] = item_fields
            _validate_field_value(item, item_spec, artifact_id, item_loc)
    elif t == "object":
        nested_required = fspec.get("required_fields")
        if nested_required:
            _validate_object_fields(value, nested_required, artifact_id, f"{loc}.")
        additional_value_type = fspec.get("additional_value_type")
        if additional_value_type:
            for k, v in value.items():
                _validate_additional_value(v, additional_value_type, artifact_id, f"{loc}.{k}")


def _validate_additional_value(
    value: Any,
    additional_value_type: str,
    artifact_id: str,
    loc: str,
) -> None:
    if additional_value_type == "json-value":
        return
    if not _check_type(value, {"type": additional_value_type}):
        raise ArtifactSchemaError(
            artifact_id,
            f"{loc}: map value must be {additional_value_type}, got {type(value).__name__}",
        )


def _validate_payload_schema_version(
    obj: dict[str, Any],
    required_fields: dict[str, Any],
    expected: Any,
    artifact_id: str,
    prefix: str,
) -> None:
    if "schema_version" not in required_fields:
        return
    actual = obj.get("schema_version")
    if actual != expected:
        raise ArtifactSchemaError(
            artifact_id,
            f"{prefix}schema_version: payload={actual} != registry={expected}",
        )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

#: The 7 closed per-artifact item fields are read from the registry at
#: runtime; this constant is only for documentation and sanity checks.
_EXPECTED_ITEM_FIELD_COUNT = 7


def validate_manifest(manifest_path: pathlib.Path) -> ManifestData:
    """Validate a manifest file against the registry.

    Raises :class:`ManifestError` on any failure (one of the 5 closed
    codes).  On success, returns :class:`ManifestData` with the parsed
    manifest, resolved ``artifact_root``, per-artifact entries, and the
    set of declared relative paths.
    """
    registry = load_registry()
    manifest_schema: dict[str, Any] = registry["manifest_schema"]["top_level_fields"]
    registry_artifacts: dict[str, Any] = registry["artifacts"]

    # --- Load manifest JSON ---
    try:
        raw = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestError(
            "FIELD_SCHEMA_INVALID", "(manifest)", f"cannot read manifest: {exc}"
        ) from exc
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ManifestError(
            "FIELD_SCHEMA_INVALID", "(manifest)", f"cannot parse manifest JSON: {exc}"
        ) from exc

    if not isinstance(manifest, dict):
        raise ManifestError(
            "FIELD_SCHEMA_INVALID", "(manifest)", "manifest root must be a JSON object"
        )

    # --- Top-level closed fields ---
    expected_top = set(manifest_schema.keys())
    actual_top = set(manifest.keys())
    if actual_top != expected_top:
        missing = sorted(expected_top - actual_top)
        extra = sorted(actual_top - expected_top)
        raise ManifestError(
            "FIELD_SCHEMA_INVALID",
            "(manifest)",
            f"top-level fields mismatch: missing={missing}, extra={extra}",
        )

    # --- Type-check top-level fields ---
    for fname, fspec in manifest_schema.items():
        if not _check_type(manifest[fname], fspec):
            raise ManifestError(
                "FIELD_SCHEMA_INVALID",
                "(manifest)",
                f"top-level field '{fname}' must be {fspec['type']}",
            )

    # --- Resolve artifact_root (relative to manifest dir if relative) ---
    artifact_root_str = manifest["artifact_root"]
    artifact_root = pathlib.Path(artifact_root_str)
    if not artifact_root.is_absolute():
        artifact_root = (manifest_path.parent / artifact_root).resolve()
    else:
        artifact_root = artifact_root.resolve()

    # --- Per-artifact validation ---
    artifacts_spec = manifest_schema["artifacts"]
    item_fields_spec: dict[str, Any] = artifacts_spec["item_fields"]
    expected_item_fields = set(item_fields_spec.keys())
    # Sanity: registry declares exactly 7 item fields.
    assert len(expected_item_fields) == _EXPECTED_ITEM_FIELD_COUNT  # noqa: S101

    entries: dict[str, dict[str, Any]] = {}
    declared_ids: list[str] = []

    for i, item in enumerate(manifest["artifacts"]):
        if not isinstance(item, dict):
            raise ManifestError(
                "FIELD_SCHEMA_INVALID",
                f"(artifacts[{i}])",
                "artifact entry must be a JSON object",
            )

        # Closed 7-field check
        actual_fields = set(item.keys())
        if actual_fields != expected_item_fields:
            missing = sorted(expected_item_fields - actual_fields)
            extra = sorted(actual_fields - expected_item_fields)
            loc = item.get("artifact_id", f"(artifacts[{i}])")
            raise ManifestError(
                "FIELD_SCHEMA_INVALID",
                str(loc),
                f"item fields mismatch: missing={missing}, extra={extra}",
            )

        # Type-check each field
        for fname, fspec in item_fields_spec.items():
            if not _check_type(item[fname], fspec):
                raise ManifestError(
                    "FIELD_SCHEMA_INVALID",
                    str(item["artifact_id"]),
                    f"field '{fname}' must be {fspec['type']}",
                )

        aid = item["artifact_id"]

        # hash_algorithm enum (from registry)
        hash_algo_spec = item_fields_spec["hash_algorithm"]
        if "enum" in hash_algo_spec and item["hash_algorithm"] not in hash_algo_spec["enum"]:
            raise ManifestError(
                "FIELD_SCHEMA_INVALID",
                aid,
                f"hash_algorithm must be one of {hash_algo_spec['enum']}, "
                f"got '{item['hash_algorithm']}'",
            )

        # hash format: hex_length + charset (from registry)
        hash_spec = item_fields_spec["hash"]
        h = item["hash"]
        hex_length = hash_spec.get("hex_length")
        if hex_length is not None and len(h) != hex_length:
            raise ManifestError(
                "FIELD_SCHEMA_INVALID",
                aid,
                f"hash must be {hex_length} hex chars, got length {len(h)}",
            )
        charset = hash_spec.get("charset")
        if charset == "lowercase_hex" and not all(c in _LOWERCASE_HEX for c in h):
            raise ManifestError(
                "FIELD_SCHEMA_INVALID",
                aid,
                f"hash must be lowercase hex, got non-hex or uppercase char in '{h}'",
            )

        # Duplicate check
        if aid in entries:
            raise ManifestError("FIELD_SCHEMA_INVALID", aid, f"duplicate artifact_id '{aid}'")

        declared_ids.append(aid)
        entries[aid] = item

    # --- Each declared artifact_id must exist in registry ---
    for aid in declared_ids:
        if aid not in registry_artifacts:
            raise ManifestError("FIELD_SCHEMA_INVALID", aid, f"artifact_id '{aid}' not in registry")

    # --- Completeness: all registry ids must be declared (no missing) ---
    registry_ids = set(registry_artifacts.keys())
    declared_set = set(declared_ids)
    missing = registry_ids - declared_set
    if missing:
        first_missing = sorted(missing)[0]
        raise ManifestError(
            "MISSING_ARTIFACT",
            first_missing,
            f"required artifact '{first_missing}' not declared in manifest",
        )

    # --- format / schema_version / producer must match registry ---
    for aid, item in entries.items():
        reg = registry_artifacts[aid]
        if item["format"] != reg["format"]:
            raise ManifestError(
                "FIELD_SCHEMA_INVALID",
                aid,
                f"format mismatch: manifest='{item['format']}', registry='{reg['format']}'",
            )
        if item["producer"] != reg["producer"]:
            raise ManifestError(
                "FIELD_SCHEMA_INVALID",
                aid,
                f"producer mismatch: manifest='{item['producer']}', registry='{reg['producer']}'",
            )
        if item["schema_version"] != reg["schema_version"]:
            raise ManifestError(
                "SCHEMA_VERSION_MISMATCH",
                aid,
                f"schema_version mismatch: manifest={item['schema_version']}, "
                f"registry={reg['schema_version']}",
            )

    # --- Path confinement + hash verification ---
    # artifact_root is the trust/integrity boundary: every artifact path
    # must resolve strictly inside it.  Absolute paths, ``../`` traversal,
    # and symlinks that escape are rejected before any file is read.
    if not artifact_root.is_dir():
        raise ManifestError(
            "FIELD_SCHEMA_INVALID",
            "(manifest)",
            f"artifact_root does not exist or is not a directory: {artifact_root}",
        )
    root = artifact_root  # already resolved above (symlinks in path resolved)

    for aid, item in entries.items():
        raw_path = item["path"]
        if pathlib.PurePath(raw_path).is_absolute():
            raise ManifestError(
                "FIELD_SCHEMA_INVALID",
                aid,
                f"artifact path must be relative, got absolute: '{raw_path}'",
            )
        candidate = root / raw_path
        if not candidate.is_file():
            raise ManifestError(
                "MISSING_ARTIFACT",
                aid,
                f"artifact file not found: {raw_path}",
            )
        resolved_candidate = candidate.resolve(strict=True)
        if not resolved_candidate.is_relative_to(root):
            raise ManifestError(
                "FIELD_SCHEMA_INVALID",
                aid,
                f"artifact path '{raw_path}' escapes artifact_root",
            )
        actual_hash = compute_file_hash(resolved_candidate)
        if actual_hash != item["hash"]:
            raise ManifestError(
                "HASH_MISMATCH",
                aid,
                f"hash mismatch for '{raw_path}': "
                f"declared='{item['hash']}', actual='{actual_hash}'",
            )

    # --- Extra-file scan ---
    declared_paths = {item["path"] for item in entries.values()}
    if artifact_root.is_dir():
        for f in sorted(artifact_root.rglob("*")):
            if f.is_file():
                rel = f.relative_to(artifact_root).as_posix()
                if rel not in declared_paths:
                    raise ManifestError(
                        "UNDECLARED_EXTRA_FILE",
                        rel,
                        f"undeclared extra file under artifact_root: {rel}",
                    )

    return ManifestData(
        manifest=manifest,
        artifact_root=artifact_root,
        entries=entries,
        declared_paths=declared_paths,
    )


# ---------------------------------------------------------------------------
# Cross-artifact run_id consistency (R-C)
# ---------------------------------------------------------------------------

#: Artifact IDs that carry a ``run_id`` required field (derived from the
#: registry at runtime in :func:`validate_run_id_consistency`).  The report
#: must verify all present run_ids are identical so artifacts from different
#: runs cannot silently produce a mixed report.
_RUN_ID_FIELD = "run_id"


def validate_run_id_consistency(
    loaded: dict[str, Any],
    registry: dict[str, Any],
) -> str:
    """Verify all artifacts that carry a ``run_id`` agree on its value.

    ``loaded`` maps artifact_id to the already-validated JSON value.
    ``registry`` is the full registry dict (``load_registry()`` output).

    Rules:
    - Collect ``run_id`` from every artifact whose registry ``required_fields``
      includes ``run_id``: object artifacts contribute ``value["run_id"]``,
      table artifacts contribute every row's ``run_id``.
    - All collected run_ids must be identical.
    - Returns the single canonical run_id (empty string if none collected).
    - On any mismatch raises :class:`ManifestError` with code
      ``FIELD_SCHEMA_INVALID``.

    Empty tables (``[]``) contribute no run_id -- this is a legal state
    (R-B allows empty tables).
    """
    artifacts = registry.get("artifacts", {})
    run_ids: set[str] = set()

    for aid, spec in artifacts.items():
        required_fields = spec.get("required_fields", {})
        if _RUN_ID_FIELD not in required_fields:
            continue
        value = loaded.get(aid)
        if value is None:
            continue
        shape = spec.get("shape")
        if shape == "object" and isinstance(value, dict):
            rid = value.get(_RUN_ID_FIELD)
            if rid is not None:
                run_ids.add(str(rid))
        elif shape == "table" and isinstance(value, list):
            for row in value:
                if isinstance(row, dict):
                    rid = row.get(_RUN_ID_FIELD)
                    if rid is not None:
                        run_ids.add(str(rid))

    if len(run_ids) > 1:
        raise ManifestError(
            "FIELD_SCHEMA_INVALID",
            "(manifest)",
            f"cross-artifact run_id mismatch: artifacts carry conflicting "
            f"run_ids {sorted(run_ids)}",
        )

    return sorted(run_ids)[0] if run_ids else ""
