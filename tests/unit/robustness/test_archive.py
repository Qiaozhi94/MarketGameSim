"""T704: evidence-archive tests.

Positive + negative + multi-record cases per CLAUDE.md: archive records are
traceable back to cell/seed/raw log, and incomplete records are rejected.
"""

from __future__ import annotations

import json

import pytest

from market_game_sim.robustness.archive import (
    Archive,
    ArchiveError,
    ArchiveRecord,
    environment_fingerprint,
    save_archive,
)


def _rec(cell="c1", seed=1):
    return ArchiveRecord(
        cell_id=cell,
        seed=seed,
        event_log_path=f"logs/{cell}-{seed}.jsonl",
        artifact_kind="report",
        artifact_path=f"reports/{cell}-{seed}.json",
        config_hash="abc",
    )


class TestArchiveRecord:
    def test_validate_ok(self):
        _rec().validate()

    def test_missing_cell_fails(self):
        r = _rec()
        r.cell_id = ""
        with pytest.raises(ArchiveError, match="cell_id empty"):
            r.validate()

    def test_missing_log_fails(self):
        r = _rec()
        r.event_log_path = ""
        with pytest.raises(ArchiveError, match="event_log_path empty"):
            r.validate()

    def test_trace_id_deterministic(self):
        assert _rec().trace_id() == _rec().trace_id()

    def test_env_fingerprint(self):
        f = environment_fingerprint()
        assert "python" in f
        assert "schema_version" in f


class TestArchive:
    def test_add_and_trace(self):
        a = Archive()
        a.add(_rec("c1", 1))
        a.add(_rec("c1", 2))
        a.add(_rec("c2", 1))
        traced = a.trace("c1", 1)
        assert len(traced) == 1
        assert traced[0].event_log_path == "logs/c1-1.jsonl"

    def test_add_incomplete_fails(self):
        a = Archive()
        r = _rec()
        r.cell_id = ""
        with pytest.raises(ArchiveError):
            a.add(r)

    def test_save_archive(self, tmp_path):
        a = Archive()
        a.add(_rec("c1", 1))
        p = tmp_path / "archive.json"
        save_archive(a, p)
        data = json.loads(p.read_text(encoding="utf-8"))
        assert len(data["records"]) == 1
