"""validate_owner_evidence 证据包校验测试：三类正样例 + 各破坏样例。

加载方式沿用本仓既有约定（`test_check_secrets.py` 同款 importlib 加载
`tools/` 下的脚本），因为本仓未配置 pytest `pythonpath`。

所有 fixture 一律写在 tmp_path 下：正样例由统一的自洽 builder 生成，破坏样例
只改动单一字段，保证每个用例只命中一条预期错误。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]


def _load() -> object:
    spec = importlib.util.spec_from_file_location(
        "validate_owner_evidence", ROOT / "tools" / "validate_owner_evidence.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


voe = _load()

EVENTS_SHA = "ab" * 32
STOP_REASON = "所有者时间受限，按冻结顺序停止，不补跑、不外推"


def _session(sid: str, stage: str, status: str = "complete") -> dict:
    return {
        "session_id": sid,
        "stage": stage,
        "scenario_id": f"S-{sid}",
        "status": status,
        "seed": 20260901,
        "started_at": "2026-09-17T09:00:00+08:00",
        "ended_at": "2026-09-17T09:30:00+08:00",
        "events_sha256": EVENTS_SHA,
    }


def _complete_sessions() -> list[dict]:
    sessions = [_session(f"owner-training-{i:02d}", "training") for i in range(1, 7)]
    sessions += [_session(f"owner-formal-{i:02d}", "formal") for i in range(1, 25)]
    return sessions


def _incomplete_sessions() -> list[dict]:
    """6 训练 + 9 正式 complete + 1 正式 excluded（excluded 也占用名额）。"""
    sessions = _complete_sessions()[:15]
    sessions.append(_session("owner-formal-10", "formal", status="excluded"))
    return sessions


def _build(
    tmp_path: pathlib.Path,
    sessions: list[dict],
    study_status: str,
    stop_reason: str | None,
) -> pathlib.Path:
    target = tmp_path / "owner-n-of-1"
    target.mkdir()

    (target / "environment.json").write_text(
        json.dumps(
            {
                "os": "Linux-6.18-x86_64 (WSL2)",
                "python": "3.11.9",
                "command": "python -m market_game_sim.cli --stage formal",
                "recorded_at": "2026-09-17T09:00:00+08:00",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    manifest_bytes = json.dumps(
        {"schema_version": 1, "sessions": sessions}, indent=2, ensure_ascii=False
    ).encode("utf-8")
    (target / "owner-session-manifest.json").write_bytes(manifest_bytes)

    index: dict = {
        "schema_version": 1,
        "study_status": study_status,
        "sessions_total": len(sessions),
        "training_total": sum(1 for s in sessions if s["stage"] == "training"),
        "formal_total": sum(1 for s in sessions if s["stage"] == "formal"),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "sessions": [
            {"session_id": s["session_id"], "stage": s["stage"], "status": s["status"]}
            for s in sessions
        ],
    }
    if stop_reason is not None:
        index["stop_reason"] = stop_reason
    (target / "owner-evidence-index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return target


def _edit_index(target: pathlib.Path, mutate) -> None:
    path = target / "owner-evidence-index.json"
    index = json.loads(path.read_text(encoding="utf-8"))
    mutate(index)
    path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")


def _run(target: pathlib.Path, capsys) -> tuple[int, str]:
    rc = voe.main(["--dir", str(target)])
    captured = capsys.readouterr()
    return rc, captured.out + captured.err


def test_complete_sample_passes(tmp_path: pathlib.Path, capsys) -> None:
    target = _build(tmp_path, _complete_sessions(), "complete", None)
    rc, output = _run(target, capsys)
    assert rc == 0
    assert "OK: 30 sessions (training=6, formal=24), study_status=complete" in output


def test_incomplete_study_passes(tmp_path: pathlib.Path, capsys) -> None:
    target = _build(tmp_path, _incomplete_sessions(), "incomplete-study", STOP_REASON)
    rc, output = _run(target, capsys)
    assert rc == 0
    assert "OK: 16 sessions (training=6, formal=10), study_status=incomplete-study" in output


def test_zero_sample_passes(tmp_path: pathlib.Path, capsys) -> None:
    sessions = [_session(f"owner-training-{i:02d}", "training") for i in range(1, 3)]
    target = _build(tmp_path, sessions, "zero-sample", "正式阶段启动前技术中止")
    rc, output = _run(target, capsys)
    assert rc == 0
    assert "OK: 2 sessions (training=2, formal=0), study_status=zero-sample" in output


def test_missing_file_fails(tmp_path: pathlib.Path, capsys) -> None:
    target = _build(tmp_path, _complete_sessions(), "complete", None)
    (target / "owner-evidence-index.json").unlink()
    rc, output = _run(target, capsys)
    assert rc == 1
    assert "ERROR: 缺少文件: owner-evidence-index.json" in output


def test_missing_dir_fails(tmp_path: pathlib.Path, capsys) -> None:
    rc, output = _run(tmp_path / "nope", capsys)
    assert rc == 1
    assert "ERROR: 缺少文件: environment.json" in output


def test_invalid_json_fails(tmp_path: pathlib.Path, capsys) -> None:
    target = _build(tmp_path, _complete_sessions(), "complete", None)
    (target / "environment.json").write_text("{oops", encoding="utf-8")
    rc, output = _run(target, capsys)
    assert rc == 1
    assert "ERROR: environment.json 不是合法 JSON" in output


def test_bad_events_hash_fails(tmp_path: pathlib.Path, capsys) -> None:
    sessions = _complete_sessions()
    sessions[7]["events_sha256"] = "not-a-hash"
    target = _build(tmp_path, sessions, "complete", None)
    rc, output = _run(target, capsys)
    assert rc == 1
    assert "ERROR: manifest.sessions[7].events_sha256 必须是 64 位十六进制" in output


def test_duplicate_session_id_fails(tmp_path: pathlib.Path, capsys) -> None:
    sessions = _complete_sessions()
    sessions[1]["session_id"] = sessions[0]["session_id"]
    target = _build(tmp_path, sessions, "complete", None)
    rc, output = _run(target, capsys)
    assert rc == 1
    assert "ERROR: manifest.sessions[1].session_id 重复: owner-training-01" in output


def test_count_mismatch_fails(tmp_path: pathlib.Path, capsys) -> None:
    target = _build(tmp_path, _complete_sessions(), "complete", None)
    _edit_index(target, lambda idx: idx.__setitem__("formal_total", 23))
    rc, output = _run(target, capsys)
    assert rc == 1
    assert "ERROR: index.formal_total=23 与 manifest 不一致（应为 24）" in output


def test_manifest_hash_mismatch_fails(tmp_path: pathlib.Path, capsys) -> None:
    target = _build(tmp_path, _complete_sessions(), "complete", None)
    _edit_index(target, lambda idx: idx.__setitem__("manifest_sha256", "f" * 64))
    rc, output = _run(target, capsys)
    assert rc == 1
    assert "ERROR: index.manifest_sha256 与 manifest 文件实际 sha256 不一致" in output


def test_index_sessions_mismatch_fails(tmp_path: pathlib.Path, capsys) -> None:
    target = _build(tmp_path, _complete_sessions(), "complete", None)
    _edit_index(target, lambda idx: idx["sessions"][5].__setitem__("status", "excluded"))
    rc, output = _run(target, capsys)
    assert rc == 1
    assert (
        "ERROR: index.sessions 与 manifest.sessions 的 (session_id, stage, status) 不一致" in output
    )


def test_incomplete_without_stop_reason_fails(tmp_path: pathlib.Path, capsys) -> None:
    target = _build(tmp_path, _incomplete_sessions(), "incomplete-study", None)
    rc, output = _run(target, capsys)
    assert rc == 1
    assert "ERROR: study_status=incomplete-study 必须提供非空 stop_reason" in output


def test_study_status_counts_inconsistency_fails(tmp_path: pathlib.Path, capsys) -> None:
    # 10 个正式场却声明 complete：完整样本要求 formal==24 且 training==6
    target = _build(tmp_path, _incomplete_sessions(), "complete", None)
    rc, output = _run(target, capsys)
    assert rc == 1
    assert (
        "ERROR: index.study_status=complete 与样本数不一致"
        "（training=6, formal=10，应为 incomplete-study）" in output
    )
