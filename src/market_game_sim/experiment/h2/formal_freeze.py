"""T916: freeze the H2 preregistration, protocol, assignments, and analysis code.

The formal study may start only from an archive produced here.  The archive binds the
human-readable preregistration to the executable protocol and to the exact analysis
sources.  Existing archives are verified and reused; they are never overwritten in
place.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from market_game_sim.experiment.h2 import assignment, protocol

ROOT = Path(__file__).resolve().parents[4]
PREREGISTRATION_PATH = ROOT / "docs" / "experiments" / "H2-preregistration.md"
DEFAULT_OUT = ROOT / "docs" / "experiments" / "H2-formal-freeze"
OWNER_ORDER_AUDIT_SEED = 916_301

ARCHIVE_FILES = ("protocol.json", "assignments.json", "freeze-manifest.json")
ANALYSIS_PATHS = (
    ROOT / "src" / "market_game_sim" / "experiment" / "h2" / "outcomes.py",
    ROOT / "src" / "market_game_sim" / "experiment" / "h2" / "mechanisms.py",
)

# The repository-wide lifecycle validator owns the generic preregistration vocabulary.
# These H2-specific markers make the executable gate stricter: a generic-looking document
# cannot be bound to the H2 protocol merely because it happens to contain the headings.
PREREGISTRATION_MARKERS = (
    "id: H2-preregistration-v1",
    "status: FROZEN",
    "处理因子的水平取值",
    "估计量定义",
    "指标定义与判据",
    "样本量与功效",
    "seed plan",
    "停止规则",
    "多重比较",
    "校准区",
    "risk_appetite",
    "theta_in",
    "theta_out",
    "k_x1000",
    "OWNER_N_OF_1",
    "168",
    "24",
)

FORMAL_REQUIRED_FIELDS = (
    "preregistration",
    "mechanism_metrics",
    "assignment_plan",
    "exclusion_rules",
    "missing_rules",
    "analysis_plan",
    "retention_policy",
)


class FormalFreezeError(RuntimeError):
    """The formal freeze archive is incomplete or has drifted."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    try:
        # Git may materialize tracked text as CRLF on Windows and LF on CI.  The
        # freeze binds content, not checkout policy, so normalize EOL before hashing.
        content = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        return _sha256_bytes(content)
    except OSError as exc:
        raise FormalFreezeError(f"cannot read frozen input {path}: {exc}") from exc


def _canonical_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )


def _path_label(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def validate_preregistration(path: Path = PREREGISTRATION_PATH) -> dict[str, str]:
    """Run the H2 document gate and return its immutable identity."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FormalFreezeError(f"cannot read H2 preregistration {path}: {exc}") from exc
    missing = [marker for marker in PREREGISTRATION_MARKERS if marker not in text]
    if missing:
        raise FormalFreezeError(f"H2 preregistration is incomplete; missing {missing}")
    return {
        "id": "H2-preregistration-v1",
        "path": _path_label(path),
        "sha256": _sha256_bytes(text.encode("utf-8")),
    }


def _analysis_hashes(paths: Sequence[Path]) -> dict[str, str]:
    return {_path_label(path): _sha256_file(path) for path in paths}


def build_formal_protocol(
    *,
    preregistration_path: Path = PREREGISTRATION_PATH,
    analysis_paths: Sequence[Path] = ANALYSIS_PATHS,
) -> protocol.FrozenProtocol:
    """Build and validate the executable final protocol without writing it."""
    preregistration = validate_preregistration(preregistration_path)
    base = protocol.freeze(protocol.draft_from_contract())
    seed_plan = assignment.build_seed_plan(base)
    owner_order = assignment.scenario_order(base, audit_seed=OWNER_ORDER_AUDIT_SEED)
    draft = dict(base.payload)
    draft.update(
        {
            "preregistration": preregistration,
            "mechanism_metrics": {
                "dictionary": "docs/research/metrics-dictionary.md#8-h2-机制指标fr-305--tr-30203-1",
                "ids": ["H2-M-001", "H2-M-002", "H2-M-003"],
            },
            "assignment_plan": {
                "ai_planned_seeds": [seed_plan.planned[0], seed_plan.planned[-1]],
                "ai_reserve_seeds": [seed_plan.reserve[0], seed_plan.reserve[-1]],
                "owner_order_audit_seed": OWNER_ORDER_AUDIT_SEED,
                "owner_scenario_order": list(owner_order),
            },
            "exclusion_rules": [
                "protocol_drift",
                "technical_abort",
                "owner_abort",
                "incomplete_pair",
                "incomplete_session",
            ],
            "missing_rules": {
                "ai_track": "complete_pair_only; no imputation",
                "owner_track": "complete owner+linear+threshold scenario only; descriptive",
            },
            "analysis_plan": {
                "source_sha256": _analysis_hashes(analysis_paths),
                "contrast": "risk_budget_threshold_v1 - risk_budget_linear_v1",
                "bootstrap_resamples": 10_000,
                "bootstrap_seed": 0,
                "ci_level": 0.95,
                "holm_alpha": 0.05,
                "holm_scope": [
                    "price_crash.severity",
                    "liquidity_dry_up.severity",
                    "liquidation_cascade.severity",
                ],
                "occurrence_role": "descriptive",
                "owner_inference": "descriptive_only",
            },
            "retention_policy": {
                "direct_identifiers_collected": False,
                "owner_pseudonym_only": True,
                "formal_aborts_retained_for_audit": True,
            },
        }
    )
    missing = [field for field in FORMAL_REQUIRED_FIELDS if field not in draft]
    if missing:
        raise FormalFreezeError(f"formal protocol is incomplete; missing {missing}")
    frozen = protocol.freeze(draft)
    frozen.verify()
    return frozen


def _write_new(path: Path, payload: Any) -> None:
    encoded = _canonical_bytes(payload)
    if path.exists():
        if path.read_bytes() != encoded:
            raise FormalFreezeError(f"refusing to overwrite frozen artifact {path}")
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(encoded)
    temporary.replace(path)


def freeze_study(
    out: Path = DEFAULT_OUT,
    *,
    preregistration_path: Path = PREREGISTRATION_PATH,
    analysis_paths: Sequence[Path] = ANALYSIS_PATHS,
    frozen_at_utc: str | None = None,
) -> Path:
    """Create the pre-sample formal archive, or verify an existing one."""
    target = Path(out)
    manifest_path = target / "freeze-manifest.json"
    if manifest_path.is_file():
        verify_archive(
            target,
            preregistration_path=preregistration_path,
            analysis_paths=analysis_paths,
        )
        return target

    frozen = build_formal_protocol(
        preregistration_path=preregistration_path,
        analysis_paths=analysis_paths,
    )
    target.mkdir(parents=True, exist_ok=True)
    protocol_payload = {
        "schema_version": 1,
        "status": "FROZEN",
        "protocol_hash": frozen.protocol_hash,
        "payload": dict(frozen.payload),
    }
    _write_new(target / "protocol.json", protocol_payload)

    issued = assignment.issue(frozen)
    seed_plan = assignment.build_seed_plan(frozen)
    assignments_payload = {
        "schema_version": 1,
        "status": "FROZEN",
        "protocol_hash": frozen.protocol_hash,
        "ai_assignments": [
            {
                "assignment_id": item.assignment_id,
                "seed": item.seed,
                "order_index": item.order_index,
                "arms": list(item.arms),
                "protocol_hash": item.protocol_hash,
            }
            for item in issued
        ],
        "reserve_seeds": list(seed_plan.reserve),
        "owner_order_audit_seed": OWNER_ORDER_AUDIT_SEED,
        "owner_scenario_order": list(
            assignment.scenario_order(frozen, audit_seed=OWNER_ORDER_AUDIT_SEED)
        ),
    }
    _write_new(target / "assignments.json", assignments_payload)

    timestamp = frozen_at_utc or datetime.now(UTC).replace(microsecond=0).isoformat()
    manifest = {
        "schema_version": 1,
        "freeze_id": "H2-formal-freeze-v1",
        "frozen_at_utc": timestamp,
        "protocol_hash": frozen.protocol_hash,
        "formal_sample_count_at_freeze": 0,
        "first_formal_sample_allowed_after": timestamp,
        "artifacts": {
            "preregistration": validate_preregistration(preregistration_path),
            "protocol.json": _sha256_file(target / "protocol.json"),
            "assignments.json": _sha256_file(target / "assignments.json"),
            "analysis_code": _analysis_hashes(analysis_paths),
        },
    }
    _write_new(manifest_path, manifest)
    verify_archive(
        target,
        preregistration_path=preregistration_path,
        analysis_paths=analysis_paths,
    )
    return target


def verify_archive(
    out: Path = DEFAULT_OUT,
    *,
    preregistration_path: Path = PREREGISTRATION_PATH,
    analysis_paths: Sequence[Path] = ANALYSIS_PATHS,
) -> Mapping[str, Any]:
    """Verify both gates and every cross-file hash in a frozen archive."""
    target = Path(out)
    missing = [name for name in ARCHIVE_FILES if not (target / name).is_file()]
    if missing:
        raise FormalFreezeError(f"formal freeze archive is incomplete; missing {missing}")
    try:
        manifest = json.loads((target / "freeze-manifest.json").read_text(encoding="utf-8"))
        protocol_payload = json.loads((target / "protocol.json").read_text(encoding="utf-8"))
        assignments_payload = json.loads((target / "assignments.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FormalFreezeError(f"cannot parse formal freeze archive: {exc}") from exc

    preregistration = validate_preregistration(preregistration_path)
    if manifest["artifacts"]["preregistration"] != preregistration:
        raise FormalFreezeError("preregistration hash or identity drifted after the freeze")
    if manifest["artifacts"]["protocol.json"] != _sha256_file(target / "protocol.json"):
        raise FormalFreezeError("protocol.json drifted after the freeze")
    if manifest["artifacts"]["assignments.json"] != _sha256_file(target / "assignments.json"):
        raise FormalFreezeError("assignments.json drifted after the freeze")
    if manifest["artifacts"]["analysis_code"] != _analysis_hashes(analysis_paths):
        raise FormalFreezeError("analysis code drifted after the freeze")

    payload = protocol_payload["payload"]
    if protocol.content_hash(payload) != protocol_payload["protocol_hash"]:
        raise FormalFreezeError("protocol payload does not match protocol_hash")
    protocol_hash = protocol_payload["protocol_hash"]
    if manifest["protocol_hash"] != protocol_hash:
        raise FormalFreezeError("freeze manifest does not bind the frozen protocol")
    if assignments_payload["protocol_hash"] != protocol_hash:
        raise FormalFreezeError("assignment table does not bind the frozen protocol")
    ai_assignments = assignments_payload["ai_assignments"]
    if len(ai_assignments) != int(payload["minimum_blocks"]):
        raise FormalFreezeError("assignment table does not cover the frozen block count")
    if any(item["protocol_hash"] != protocol_hash for item in ai_assignments):
        raise FormalFreezeError("an assignment was issued under a different protocol")
    if manifest["formal_sample_count_at_freeze"] != 0:
        raise FormalFreezeError("freeze must be archived before the first formal sample")
    return manifest
