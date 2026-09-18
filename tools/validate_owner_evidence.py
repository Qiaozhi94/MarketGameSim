#!/usr/bin/env python3
"""owner n-of-1 证据包机器校验（0.3.2 T929 冻结的证据合同）。

owner 证据固定落在 `docs/experiments/owner-n-of-1/`，由三份 JSON 组成：
`environment.json`（目标环境记录）、`owner-session-manifest.json`（场景会话
清单）、`owner-evidence-index.json`（索引）。字段 schema 的真源是该目录下的
README，本文件与其同步冻结，不得单方面放宽。

校验规则（任一命中即失败，逐条打印 `ERROR: <原因>`）：
- 三份文件存在且 JSON 可解析，`schema_version` 恒为 1；
- manifest：`session_id` 全清单唯一；`stage`/`status` 枚举合法；
  `events_sha256` 为 64 位十六进制；`seed`/时间戳等字段类型合法；
- index：`sessions_total`/`training_total`/`formal_total` 与 manifest 一致；
- index：`study_status` 与样本数一致（complete ⇔ formal=24 且 training=6；
  incomplete-study ⇔ 0<formal<24；zero-sample ⇔ 无 formal；training 0..6）；
- index：`study_status != complete` 时必须给出非空 `stop_reason`；
- index：`manifest_sha256` 等于 manifest 文件原始字节的 sha256；
- index：`sessions` 的 `(session_id, stage, status)` 与 manifest 逐条完全一致。

用法：python tools/validate_owner_evidence.py [--dir docs/experiments/owner-n-of-1]
退出码 0 = 通过；1 = 校验失败。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_EVIDENCE_DIR = ROOT / "docs" / "experiments" / "owner-n-of-1"

SCHEMA_VERSION = 1
TRAINING_TARGET = 6
FORMAL_TARGET = 24

ENVIRONMENT_FILE = "environment.json"
MANIFEST_FILE = "owner-session-manifest.json"
INDEX_FILE = "owner-evidence-index.json"

STAGES = ("training", "formal")
SESSION_STATUSES = ("complete", "excluded")
STUDY_STATUSES = ("complete", "incomplete-study", "zero-sample")
ENVIRONMENT_FIELDS = ("os", "python", "command", "recorded_at")

HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")

# (session_id, stage, status) 三元组：manifest 与 index 一致性核对的最小单元
SessionTriple = tuple[str, str, str]


def _sha256_file(path: pathlib.Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _load_json(path: pathlib.Path, errors: list[str]) -> object | None:
    if not path.is_file():
        errors.append(f"缺少文件: {path.name}")
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"{path.name} 读取失败: {exc}")
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        errors.append(f"{path.name} 不是合法 JSON: {exc}")
        return None


def _check_schema_version(data: dict[str, object], label: str, errors: list[str]) -> None:
    version = data.get("schema_version")
    if isinstance(version, bool) or version != SCHEMA_VERSION:
        errors.append(f"{label}.schema_version 必须是 {SCHEMA_VERSION}")


def _validate_environment(data: object, errors: list[str]) -> None:
    if not isinstance(data, dict):
        errors.append("environment.json 顶层必须是 JSON 对象")
        return
    for field in ENVIRONMENT_FIELDS:
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"environment.{field} 必须是非空字符串")


def _validate_session(
    position: int, entry: object, seen: set[str], errors: list[str]
) -> SessionTriple | None:
    where = f"manifest.sessions[{position}]"
    if not isinstance(entry, dict):
        errors.append(f"{where} 必须是 JSON 对象")
        return None

    session_id = entry.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        errors.append(f"{where}.session_id 必须是非空字符串")
        session_id = None
    elif session_id in seen:
        errors.append(f"{where}.session_id 重复: {session_id}")
        session_id = None
    else:
        seen.add(session_id)

    stage = entry.get("stage")
    if stage not in STAGES:
        errors.append(f"{where}.stage 必须是 training/formal")
        stage = None

    scenario_id = entry.get("scenario_id")
    if not isinstance(scenario_id, str) or not scenario_id:
        errors.append(f"{where}.scenario_id 必须是非空字符串")

    status = entry.get("status")
    if status not in SESSION_STATUSES:
        errors.append(f"{where}.status 必须是 complete/excluded")
        status = None

    seed = entry.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        errors.append(f"{where}.seed 必须是整数")

    for field in ("started_at", "ended_at"):
        value = entry.get(field)
        if not isinstance(value, str) or not value:
            errors.append(f"{where}.{field} 必须是非空字符串")

    events_sha = entry.get("events_sha256")
    if not isinstance(events_sha, str) or not HEX64.fullmatch(events_sha):
        errors.append(f"{where}.events_sha256 必须是 64 位十六进制")

    if session_id is None or stage is None or status is None:
        return None
    return (session_id, stage, status)


def _validate_manifest(data: object, errors: list[str]) -> list[SessionTriple]:
    """校验 manifest 结构，返回可用的 (session_id, stage, status) 三元组列表。"""
    if not isinstance(data, dict):
        errors.append("manifest 顶层必须是 JSON 对象")
        return []
    _check_schema_version(data, "manifest", errors)
    sessions = data.get("sessions")
    if not isinstance(sessions, list):
        errors.append("manifest.sessions 必须是数组")
        return []
    seen: set[str] = set()
    triples: list[SessionTriple] = []
    for position, entry in enumerate(sessions):
        triple = _validate_session(position, entry, seen, errors)
        if triple is not None:
            triples.append(triple)
    return triples


def _expected_study_status(training_total: int, formal_total: int) -> str | None:
    """按冻结合同从样本数推导唯一合法的 study_status；无法对应则返回 None。"""
    if formal_total == 0:
        return "zero-sample"
    if 0 < formal_total < FORMAL_TARGET:
        return "incomplete-study"
    if formal_total == FORMAL_TARGET and training_total == TRAINING_TARGET:
        return "complete"
    return None


def _validate_index_session(
    position: int, entry: object, errors: list[str]
) -> SessionTriple | None:
    where = f"index.sessions[{position}]"
    if not isinstance(entry, dict):
        errors.append(f"{where} 必须是 JSON 对象")
        return None
    session_id = entry.get("session_id")
    stage = entry.get("stage")
    status = entry.get("status")
    if (
        not isinstance(session_id, str)
        or not session_id
        or stage not in STAGES
        or status not in SESSION_STATUSES
    ):
        errors.append(f"{where} 必须包含合法的 session_id/stage/status")
        return None
    return (session_id, stage, status)


def _validate_index(
    data: object,
    triples: list[SessionTriple],
    manifest_digest: str | None,
    errors: list[str],
) -> dict[str, object] | None:
    if not isinstance(data, dict):
        errors.append("index 顶层必须是 JSON 对象")
        return None
    _check_schema_version(data, "index", errors)

    study_status = data.get("study_status")
    if study_status not in STUDY_STATUSES:
        errors.append("index.study_status 必须是 complete/incomplete-study/zero-sample")
        study_status = None

    stop_reason = data.get("stop_reason")
    if stop_reason is not None and not isinstance(stop_reason, str):
        errors.append("index.stop_reason 必须是字符串")
    has_reason = isinstance(stop_reason, str) and bool(stop_reason.strip())
    if study_status is not None and study_status != "complete" and not has_reason:
        errors.append(f"study_status={study_status} 必须提供非空 stop_reason")

    training_total = sum(1 for _, stage, _ in triples if stage == "training")
    formal_total = sum(1 for _, stage, _ in triples if stage == "formal")
    for field, actual in (
        ("sessions_total", len(triples)),
        ("training_total", training_total),
        ("formal_total", formal_total),
    ):
        declared = data.get(field)
        if isinstance(declared, bool) or not isinstance(declared, int):
            errors.append(f"index.{field} 必须是整数")
        elif declared != actual:
            errors.append(f"index.{field}={declared} 与 manifest 不一致（应为 {actual}）")

    expected_status = _expected_study_status(training_total, formal_total)
    if expected_status is None:
        errors.append(
            f"样本数组合 training={training_total}/formal={formal_total} 不构成合法研究状态"
        )
    elif study_status is not None and study_status != expected_status:
        errors.append(
            f"index.study_status={study_status} 与样本数不一致"
            f"（training={training_total}, formal={formal_total}，应为 {expected_status}）"
        )

    declared_digest = data.get("manifest_sha256")
    if not isinstance(declared_digest, str) or not HEX64.fullmatch(declared_digest):
        errors.append("index.manifest_sha256 必须是 64 位十六进制")
    elif manifest_digest is None:
        errors.append("index.manifest_sha256 无法核对：manifest 文件不可读")
    elif declared_digest != manifest_digest:
        errors.append("index.manifest_sha256 与 manifest 文件实际 sha256 不一致")

    index_sessions = data.get("sessions")
    if not isinstance(index_sessions, list):
        errors.append("index.sessions 必须是数组")
    else:
        index_triples: list[SessionTriple] = []
        for position, entry in enumerate(index_sessions):
            triple = _validate_index_session(position, entry, errors)
            if triple is not None:
                index_triples.append(triple)
        if index_triples != triples:
            errors.append(
                "index.sessions 与 manifest.sessions 的 (session_id, stage, status) 不一致"
            )

    return {
        "sessions_total": len(triples),
        "training_total": training_total,
        "formal_total": formal_total,
        "study_status": expected_status if study_status is None else study_status,
    }


def validate_evidence_dir(
    directory: pathlib.Path,
) -> tuple[list[str], dict[str, object] | None]:
    """校验证据目录，返回（错误列表, 摘要）。错误列表为空即通过。"""
    errors: list[str] = []

    environment = _load_json(directory / ENVIRONMENT_FILE, errors)
    if environment is not None:
        _validate_environment(environment, errors)

    manifest_path = directory / MANIFEST_FILE
    manifest = _load_json(manifest_path, errors)
    triples = _validate_manifest(manifest, errors) if manifest is not None else []
    manifest_digest = _sha256_file(manifest_path)

    index = _load_json(directory / INDEX_FILE, errors)
    summary = None
    if index is not None:
        summary = _validate_index(index, triples, manifest_digest, errors)

    return errors, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="owner n-of-1 证据包机器校验（T929）")
    parser.add_argument(
        "--dir",
        type=pathlib.Path,
        default=DEFAULT_EVIDENCE_DIR,
        help=f"证据包目录（默认 {DEFAULT_EVIDENCE_DIR}）",
    )
    args = parser.parse_args(argv)

    errors, summary = validate_evidence_dir(args.dir)
    if errors:
        for message in errors:
            print(f"ERROR: {message}", file=sys.stderr)
        return 1
    assert summary is not None  # 无错误时三份文件均已解析并产出摘要
    print(
        f"OK: {summary['sessions_total']} sessions"
        f" (training={summary['training_total']}, formal={summary['formal_total']}),"
        f" study_status={summary['study_status']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
