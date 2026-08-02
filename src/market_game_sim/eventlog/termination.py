"""T204e2: Termination classification -- TI-4 vs TI-5.

[事件 Schema §1.5] 先结构后语义
[退化状态 §4.1] TI-4 / TI-5 互斥

A log is classified in two phases; the order is fixed:

Phase 1 (structure) -- any failure -> **TI-5**:
  - Every line is valid JSON (no truncation, no parse error).
  - First record is ``RUN_HEADER``, last is ``RUN_TRAILER``.
  - ``record_count`` equals the actual number of lines.

Phase 2 (semantics) -- only when phase 1 passes:
  - ``terminated = COMPLETED`` -> **VALID**.
  - ``terminated = ABORTED``   -> **TI-4**.

A log with ``ABORTED`` trailer that is also truncated is **TI-5**,
not TI-4: when the structure is damaged, ``terminated`` itself is
untrustworthy.  TI-4 points to a kernel defect (has ``abort_code``);
TI-5 points to an environment problem (process killed, disk full).
"""

from __future__ import annotations

import json
from typing import Literal

TerminationCode = Literal["VALID", "TI-4", "TI-5"]


def classify_log(log_text: str) -> TerminationCode:
    """Classify an event log string as ``VALID``, ``TI-4``, or ``TI-5``.

    ``log_text`` is the raw file content (UTF-8 decoded).  Empty or
    whitespace-only input is TI-5 (no records at all).
    """
    lines = [ln for ln in log_text.split("\n") if ln.strip()]
    if not lines:
        return "TI-5"

    # Phase 1: structural integrity.
    records: list[dict] = []
    for ln in lines:
        try:
            obj = json.loads(ln)
        except (json.JSONDecodeError, ValueError):
            return "TI-5"
        if not isinstance(obj, dict):
            return "TI-5"
        records.append(obj)

    if records[0].get("record_kind") != "RUN_HEADER":
        return "TI-5"
    if records[-1].get("record_kind") != "RUN_TRAILER":
        return "TI-5"

    trailer = records[-1]
    declared_count = trailer.get("record_count")
    if not isinstance(declared_count, int):
        return "TI-5"
    if declared_count != len(records):
        return "TI-5"

    # Phase 2: termination semantics.
    terminated = trailer.get("terminated")
    if terminated == "ABORTED":
        return "TI-4"
    return "VALID"


def classify_log_bytes(log_bytes: bytes) -> TerminationCode:
    """Classify raw log bytes (UTF-8 decoded first)."""
    try:
        text = log_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return "TI-5"
    return classify_log(text)
