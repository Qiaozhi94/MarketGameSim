"""T101 (FR-019): Independent event-log reader.

Parses the three top-level record kinds (``RUN_HEADER`` + ``EVENT*`` +
``RUN_TRAILER``) from a JSONL log file WITHOUT importing ``kernel/`` or
``eventlog/``.  Rejects TI-4/TI-5 logs (degenerate-states.md §4).

Termination discrimination is structural first (TI-5), then semantic (TI-4):
a structurally broken log never has its ``terminated`` field trusted.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from typing import Any


class LogError(Exception):
    """Raised when a log cannot be read or is TI-4/TI-5 invalid."""


@dataclass
class ReplayConfig:
    """Replay-critical config parsed from the RUN_HEADER (F1).

    These four values are needed to rebuild ``reserved_units`` and
    ``margin_ratio_bp`` per frame; they are not derivable from the event
    stream alone (ADR-001 forbids float derivation), so they travel in the
    header to guarantee the public ``build_replay`` path is E1-consistent.
    """

    mult: int = 1000
    fee_bps_cap: int = 0
    initial_price_ticks: int = 10000
    agent_initial_bp: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_header(cls, header: dict[str, Any]) -> ReplayConfig:
        required = ("mult", "fee_bps_cap", "initial_price_ticks", "agent_initial_bp")
        missing = [k for k in required if k not in header]
        if missing:
            raise LogError(f"TI-5: RUN_HEADER missing replay-critical fields: {missing}")
        if not isinstance(header["mult"], int) or isinstance(header["mult"], bool):
            raise LogError("TI-5: RUN_HEADER.mult must be int")
        if not isinstance(header["fee_bps_cap"], int) or isinstance(header["fee_bps_cap"], bool):
            raise LogError("TI-5: RUN_HEADER.fee_bps_cap must be int")
        ipt = header["initial_price_ticks"]
        if not isinstance(ipt, int) or isinstance(ipt, bool):
            raise LogError("TI-5: RUN_HEADER.initial_price_ticks must be int")
        bp = header["agent_initial_bp"]
        if not isinstance(bp, dict):
            raise LogError("TI-5: RUN_HEADER.agent_initial_bp must be an object")
        for k, v in bp.items():
            if not isinstance(k, str) or not isinstance(v, int) or isinstance(v, bool):
                raise LogError("TI-5: RUN_HEADER.agent_initial_bp must map str->int")
        return cls(
            mult=header["mult"],
            fee_bps_cap=header["fee_bps_cap"],
            initial_price_ticks=header["initial_price_ticks"],
            agent_initial_bp=dict(bp),
        )


@dataclass
class LogData:
    """A parsed, validated event log (no kernel state)."""

    header: dict[str, Any]
    events: list[dict[str, Any]]
    trailer: dict[str, Any]
    run_id: str
    config: ReplayConfig = field(default_factory=ReplayConfig)


def _parse_lines(text: str) -> list[dict[str, Any]]:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        raise LogError("TI-5: fewer than 2 lines")

    records: list[dict[str, Any]] = []
    for i, line in enumerate(lines):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LogError(f"TI-5: line {i + 1}: {exc}") from exc
        if not isinstance(record, dict):
            raise LogError(f"TI-5: line {i + 1}: expected JSON object, got {type(record).__name__}")
        records.append(record)
    return records


def _validate_structure(records: list[dict[str, Any]]) -> None:
    if records[0].get("record_kind") != "RUN_HEADER":
        raise LogError("TI-5: first record is not RUN_HEADER")
    if records[-1].get("record_kind") != "RUN_TRAILER":
        raise LogError("TI-5: last record is not RUN_TRAILER")

    for i, r in enumerate(records):
        kind = r.get("record_kind")
        if kind not in ("RUN_HEADER", "EVENT", "RUN_TRAILER"):
            raise LogError(f"TI-5: line {i + 1}: unknown record_kind {kind!r}")

    header_count = sum(1 for r in records if r.get("record_kind") == "RUN_HEADER")
    if header_count != 1:
        raise LogError(f"TI-5: expected exactly 1 RUN_HEADER, got {header_count}")
    trailer_count = sum(1 for r in records if r.get("record_kind") == "RUN_TRAILER")
    if trailer_count != 1:
        raise LogError(f"TI-5: expected exactly 1 RUN_TRAILER, got {trailer_count}")


def _validate_bootstrap_snapshots(events: list[dict[str, Any]]) -> None:
    """Require the exact bootstrap structure (event-schema.md §4.6.3).

    The first two SNAPSHOT events must be, in order, SNAPSHOT ACCOUNT then
    SNAPSHOT BOOK, both at ``timestamp=0`` with ``record_index=0``, and on
    CONTIGUOUS transactions (``BOOK.transaction_seq == ACCOUNT.transaction_seq
    + 1``).  A gap between them (e.g. ACCOUNT at 5, BOOK at 8), wrong order,
    wrong timestamp/index, or a missing snapshot is a TI-5 structural failure.
    """
    snapshots = [
        e for e in events if e.get("event_type") == "SNAPSHOT" and e.get("record_kind") == "EVENT"
    ]
    if len(snapshots) < 2:
        raise LogError("TI-5: missing bootstrap ACCOUNT/BOOK SNAPSHOT events")
    acct, book = snapshots[0], snapshots[1]
    if acct.get("snapshot_type") != "ACCOUNT" or book.get("snapshot_type") != "BOOK":
        raise LogError("TI-5: first two SNAPSHOTs must be ACCOUNT then BOOK")
    if acct.get("timestamp") != 0 or book.get("timestamp") != 0:
        raise LogError("TI-5: bootstrap snapshots must have timestamp=0")
    if acct.get("record_index") != 0 or book.get("record_index") != 0:
        raise LogError("TI-5: bootstrap snapshots must have record_index=0")
    acct_txn = acct.get("transaction_seq")
    book_txn = book.get("transaction_seq")
    if not isinstance(acct_txn, int) or not isinstance(book_txn, int):
        raise LogError("TI-5: bootstrap snapshots must have integer transaction_seq")
    if book_txn != acct_txn + 1:
        raise LogError(
            f"TI-5: bootstrap transactions must be contiguous (BOOK = ACCOUNT + 1), "
            f"got ACCOUNT={acct_txn}, BOOK={book_txn}"
        )


def _validate_event_consistency(events: list[dict[str, Any]], header: dict[str, Any]) -> None:
    if not events:
        return

    header_schema = header.get("schema_version")
    header_run_id = header.get("run_id")

    seen_txn: set[int] = set()
    for e in events:
        if e.get("record_kind") != "EVENT":
            raise LogError("TI-5: middle record is not EVENT")
        _validate_event_required_fields(e)

        ev_schema = e.get("schema_version")
        if ev_schema != header_schema:
            raise LogError(f"TI-5: event schema_version {ev_schema!r} != header {header_schema!r}")
        ev_run_id = e.get("run_id")
        if ev_run_id != header_run_id:
            raise LogError(f"TI-5: event run_id {ev_run_id!r} != header {header_run_id!r}")

        txn = e.get("transaction_seq")
        if not isinstance(txn, int) or isinstance(txn, bool):
            raise LogError(f"TI-5: event transaction_seq missing or non-int: {txn!r}")
        seen_txn.add(txn)

    for txn in sorted(seen_txn):
        txn_events = [e for e in events if e["transaction_seq"] == txn]
        for expected_idx, e in enumerate(txn_events):
            actual = e.get("record_index")
            if not isinstance(actual, int) or isinstance(actual, bool):
                raise LogError(f"TI-5: event record_index missing/non-int at txn {txn}: {actual!r}")
            if actual != expected_idx:
                raise LogError(
                    f"TI-5: record_index gap at txn {txn}: expected {expected_idx}, got {actual}"
                )


#: Common EVENT fields (event-schema §4): every EVENT record must carry them.
_EVENT_REQUIRED_FIELDS = (
    "schema_version",
    "event_id",
    "run_id",
    "timestamp",
    "transaction_seq",
    "record_index",
    "priority_class",
    "event_type",
)


def _validate_event_required_fields(event: dict[str, Any]) -> None:
    """Require the event-schema §4 common EVENT fields (round-5 review F-C2:
    a log whose EVENTs lack schema_version/run_id etc. must be TI-5)."""
    missing = [f for f in _EVENT_REQUIRED_FIELDS if f not in event]
    if missing:
        raise LogError(f"TI-5: EVENT missing required fields: {missing}")


def _validate_trailer(
    trailer: dict[str, Any], events: list[dict[str, Any]], line_count: int
) -> None:
    # event-schema §6.2: all five fields are required columns on the record.
    _TRAILER_REQUIRED = (
        "terminated",
        "abort_code",
        "abort_detail",
        "last_committed_transaction_seq",
        "record_count",
    )
    missing = [f for f in _TRAILER_REQUIRED if f not in trailer]
    if missing:
        raise LogError(f"TI-5: trailer missing required fields: {missing}")

    terminated = trailer["terminated"]
    if terminated not in ("COMPLETED", "ABORTED"):
        raise LogError(f"TI-5: trailer terminated must be COMPLETED|ABORTED, got {terminated!r}")

    rc = trailer["record_count"]
    if not isinstance(rc, int) or isinstance(rc, bool):
        raise LogError(f"TI-5: trailer record_count non-int: {rc!r}")
    if rc != line_count:
        raise LogError(f"TI-5: record_count {rc} != {line_count}")

    if terminated == "COMPLETED":
        if trailer["abort_code"] is not None or trailer["abort_detail"] is not None:
            raise LogError(
                "TI-5: COMPLETED trailer must carry abort_code=null and abort_detail=null"
            )
    else:  # ABORTED
        if trailer["abort_code"] is None:
            raise LogError("TI-5: ABORTED trailer must carry non-null abort_code")

    last_committed = trailer["last_committed_transaction_seq"]
    max_txn = max(e["transaction_seq"] for e in events)
    if last_committed is None:
        if events:
            raise LogError(
                "TI-5: trailer last_committed_transaction_seq must not be null with events"
            )
    elif last_committed != max_txn:
        raise LogError(
            f"TI-5: trailer last_committed_transaction_seq {last_committed}"
            f" != max event txn {max_txn}"
        )


#: The only event log schema version this reader supports (ADR-004, v4).
SUPPORTED_SCHEMA_VERSION = 4


def _validate_supported_schema_version(header: dict[str, Any]) -> None:
    """Reject logs whose schema_version is not exactly the supported v4.

    ADR-004 policy: v2/v3 logs are NOT replayable via the public path -- the
    RUN_HEADER replay-critical fields are a v3+ contract, and an older header
    (even one that happens to carry the fields) is an unknown-format log.
    Unknown FUTURE versions are likewise rejected, never guessed.
    """
    sv = header.get("schema_version")
    if sv != SUPPORTED_SCHEMA_VERSION:
        raise LogError(
            f"TI-5: unsupported schema_version {sv!r} (supported: {SUPPORTED_SCHEMA_VERSION})"
        )


def read_log(path: str | pathlib.Path) -> LogData:
    """Parse and validate ``path`` as an event log.

    Raises :class:`LogError` on any structural failure (TI-5) or an
    aborted run (TI-4).
    """
    p = pathlib.Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise LogError(f"TI-5: cannot read log: {exc}") from exc

    records = _parse_lines(text)
    _validate_structure(records)

    trailer = records[-1]
    header = records[0]
    events = [r for r in records if r.get("record_kind") == "EVENT"]

    _validate_supported_schema_version(header)
    _validate_bootstrap_snapshots(events)
    _validate_event_consistency(events, header)
    _validate_trailer(trailer, events, len(records))

    if trailer.get("terminated") == "ABORTED":
        detail = trailer.get("abort_code")
        raise LogError(f"TI-4: aborted (abort_code={detail})")

    config = ReplayConfig.from_header(header)
    return LogData(
        header=header,
        events=events,
        trailer=trailer,
        run_id=str(header.get("run_id", "")),
        config=config,
    )
