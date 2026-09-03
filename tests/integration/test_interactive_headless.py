"""T807 H1-A gate: one command produces a complete headless bundle."""

import hashlib
import json
import subprocess
import sys

import pytest

from market_game_sim.evidence.evidence_guard import (
    EvidenceBundleCandidate,
    EvidenceRunModeError,
    guard_evidence_bundle,
)
from market_game_sim.interactive import read_input_journal, replay_input_journal
from market_game_sim.replay.reader import read_log

BUNDLE_FILES = {
    "RUN.md",
    "input-journal.jsonl",
    "manifest.json",
    "replay.html",
    "run.jsonl",
}


def test_single_command_generates_complete_headless_interactive_bundle(tmp_path) -> None:
    out = tmp_path / "H1-A"
    completed = subprocess.run(
        [sys.executable, "-m", "market_game_sim.interactive.headless", "--out", str(out)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert {path.name for path in out.iterdir()} == BUNDLE_FILES

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_mode"] == "interactive"
    assert manifest["evidence_class"] == "engineering-demonstration"
    assert manifest["seed"] == 7
    assert manifest["termination_state"] == "COMPLETED"
    assert manifest["abort_code"] is None
    assert manifest["input_schema_version"] == 1
    assert manifest["schema_version"] == 4
    assert len(manifest["event_summary_hash"]) == 64
    assert len(manifest["frame_hash"]) == 64

    entries = {entry["artifact_id"]: entry for entry in manifest["artifacts"]}
    assert set(entries) == {"run_doc", "input_journal", "event_log", "replay"}
    for entry in entries.values():
        artifact = out / entry["path"]
        assert artifact.is_file()
        assert artifact.resolve().is_relative_to(out.resolve())
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == entry["sha256"]

    log = read_log(out / "run.jsonl")
    assert log.header["run_mode"] == "interactive"
    account_snapshot = next(
        event
        for event in log.events
        if event.get("event_type") == "SNAPSHOT" and event.get("snapshot_type") == "ACCOUNT"
    )
    human_snapshot = account_snapshot["payload"]["accounts"]
    assert (
        next(item for item in human_snapshot if item["agent_id"] == "human")["wallet_units"]
        == 1_000_000
    )

    journal = read_input_journal(out / "input-journal.jsonl")
    assert journal.session_id == manifest["session_id"] == log.run_id
    assert journal.input_hash == manifest["input_hash"]
    replayed = []
    replay_result = replay_input_journal(out / "input-journal.jsonl", replayed.append)
    assert replay_result.input_count == len(journal.records) == 2
    assert [record.action.value for record in replayed] == ["RESUME", "END"]

    html = (out / "replay.html").read_text(encoding="utf-8")
    assert "replay-data" in html
    assert "fetch(" not in html
    assert "http://" not in html
    assert "https://" not in html
    run_doc = (out / "RUN.md").read_text(encoding="utf-8")
    assert "python -m market_game_sim.interactive.headless" in run_doc
    assert "engineering-demonstration" in run_doc
    assert "不构成研究结论" in run_doc

    with pytest.raises(EvidenceRunModeError, match="interactive"):
        guard_evidence_bundle(EvidenceBundleCandidate(out / "manifest.json", out / "run.jsonl"))
