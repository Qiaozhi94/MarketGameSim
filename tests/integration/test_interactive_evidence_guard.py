"""T806 integration tests for interactive evidence isolation."""

import json

import pytest

from market_game_sim.evidence.evidence_guard import (
    EvidenceBundleCandidate,
    EvidenceRunModeError,
    RunMode,
    consume_guarded_bundle_batch,
    guard_evidence_bundle,
)


def _candidate(tmp_path, name: str, manifest_mode: object, header_mode: object):
    root = tmp_path / name
    root.mkdir()
    manifest = {"manifest_version": 1}
    if manifest_mode is not None:
        manifest["run_mode"] = manifest_mode
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    header = {"record_kind": "RUN_HEADER"}
    if header_mode is not None:
        header["run_mode"] = header_mode
    log_path = root / "run.jsonl"
    log_path.write_text(
        json.dumps(header) + "\n" + json.dumps({"secret": "body"}), encoding="utf-8"
    )
    return EvidenceBundleCandidate(manifest_path=manifest_path, event_log_path=log_path)


@pytest.mark.parametrize(
    ("manifest_mode", "header_mode", "message"),
    [
        ("interactive", "research", "interactive"),
        ("research", "interactive", "interactive"),
        (None, "research", "manifest.run_mode"),
        ("unknown", "research", "manifest.run_mode"),
        ("research", None, "RUN_HEADER.run_mode"),
        ("research", "unknown", "RUN_HEADER.run_mode"),
        ("benchmark", "research", "does not match"),
    ],
)
def test_guard_rejects_interactive_missing_unknown_and_mismatch(
    tmp_path, manifest_mode, header_mode, message
) -> None:
    candidate = _candidate(tmp_path, "bundle", manifest_mode, header_mode)

    with pytest.raises(EvidenceRunModeError, match=message):
        guard_evidence_bundle(candidate)


@pytest.mark.parametrize("mode", ["benchmark", "research"])
def test_guard_accepts_matching_non_interactive_modes(tmp_path, mode) -> None:
    guarded = guard_evidence_bundle(_candidate(tmp_path, "bundle", mode, mode))

    assert guarded.run_mode is RunMode(mode)


def test_header_mode_tamper_is_rejected_even_when_event_body_is_unchanged(tmp_path) -> None:
    candidate = _candidate(tmp_path, "bundle", "research", "research")
    original_body = candidate.event_log_path.read_bytes().splitlines()[1:]
    header = {"record_kind": "RUN_HEADER", "run_mode": "interactive"}
    candidate.event_log_path.write_text(
        json.dumps(header) + "\n" + json.dumps({"secret": "body"}), encoding="utf-8"
    )

    assert candidate.event_log_path.read_bytes().splitlines()[1:] == original_body
    with pytest.raises(EvidenceRunModeError, match="interactive"):
        guard_evidence_bundle(candidate)


def test_batch_validates_every_bundle_before_any_downstream_write(tmp_path) -> None:
    candidates = [
        _candidate(tmp_path, "valid", "research", "research"),
        _candidate(tmp_path, "invalid", "research", "interactive"),
    ]
    downstream_writes = []

    with pytest.raises(EvidenceRunModeError, match="interactive"):
        consume_guarded_bundle_batch(candidates, downstream_writes.extend)

    assert downstream_writes == []
