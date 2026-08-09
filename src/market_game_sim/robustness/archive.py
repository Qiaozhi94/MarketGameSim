"""T704: evidence archive with reverse-traceability.

Archives the protocol, configuration, log summaries, aggregated data, reports
and software environment so that any conclusion drawn from the evidence matrix
can be traced back to its parameter cell, seed and raw event log.

Each archive record carries the cell_id / seed / event-log path that produced
it, and an environment fingerprint (Python version, schema version), so the
reverse lookup cell -> seed -> raw log is always available (T704 exit gate).
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import platform
from dataclasses import dataclass, field
from typing import Any


class ArchiveError(RuntimeError):
    """Raised when an archive record is incomplete or non-traceable."""


def environment_fingerprint() -> dict[str, str]:
    """Python version + platform + schema markers for reproducibility."""
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "schema_version": "2",
    }


@dataclass
class ArchiveRecord:
    cell_id: str
    seed: int
    event_log_path: str
    artifact_kind: str  # e.g. "report", "aggregate", "log_summary"
    artifact_path: str
    protocol_id: str = ""
    config_hash: str = ""
    environment: dict[str, str] = field(default_factory=environment_fingerprint)

    def validate(self) -> None:
        problems: list[str] = []
        if not self.cell_id:
            problems.append("cell_id empty")
        if not self.event_log_path:
            problems.append("event_log_path empty")
        if not self.artifact_path:
            problems.append("artifact_path empty")
        if problems:
            raise ArchiveError("; ".join(problems))

    def trace_id(self) -> str:
        canonical = json.dumps(
            {
                "cell_id": self.cell_id,
                "seed": self.seed,
                "event_log_path": self.event_log_path,
                "artifact_kind": self.artifact_kind,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.blake2b(canonical.encode("utf-8"), digest_size=16).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "seed": self.seed,
            "event_log_path": self.event_log_path,
            "artifact_kind": self.artifact_kind,
            "artifact_path": self.artifact_path,
            "protocol_id": self.protocol_id,
            "config_hash": self.config_hash,
            "environment": dict(self.environment),
            "trace_id": self.trace_id(),
        }


@dataclass
class Archive:
    records: list[ArchiveRecord] = field(default_factory=list)

    def add(self, record: ArchiveRecord) -> None:
        record.validate()
        self.records.append(record)

    def trace(self, cell_id: str, seed: int) -> list[ArchiveRecord]:
        """Reverse lookup: given a conclusion's cell/seed, return the raw-log
        and artifact records that produced it (T704)."""
        return [r for r in self.records if r.cell_id == cell_id and r.seed == seed]

    def as_dict(self) -> dict[str, Any]:
        return {"records": [r.as_dict() for r in self.records]}


def save_archive(archive: Archive, path: str | pathlib.Path) -> None:
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(archive.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
