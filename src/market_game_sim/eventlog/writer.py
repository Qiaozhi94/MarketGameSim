"""T205: Event log writer + run metadata header.

[事件 Schema §6-§9] 事件日志写入器
[事件 Schema §6.1] RUN_HEADER (tick_size/min_quantity/cash_unit as string decimals)
[事件 Schema §6.2] RUN_TRAILER
[事件 Schema §4.6.3] bootstrap snapshots written as the first two SNAPSHOT EVENTs
  （屏障完整实现后位于 transaction_seq=1,2；当前内核下为连续事务 b/b+1，见 §4.6.3 已知缺口）

Writes a complete event log file:

  ``RUN_HEADER`` (exactly one, first line)
  ``EVENT`` × N  (at least 2: bootstrap ACCOUNT + BOOK snapshots)
  ``RUN_TRAILER`` (exactly one, last line)

Uses the canonical serializer from T104 (ADR-001 §7).  Handles fail-stop
(T204d): if the kernel aborts, the writer still writes the header +
committed records + ``ABORTED`` trailer.  Handles bootstrap (T204e3):
the two ``SNAPSHOT`` EVENTs are written first; they appear on contiguous
transactions ``b/b+1`` (bootstrap barrier fully enforced: ``1,2``; current
kernel with t=0 lower-class events: ``b, b+1``, see event-schema §4.6.3).
"""

from __future__ import annotations

import pathlib
from typing import Any

from market_game_sim.config.serialization import serialize_event
from market_game_sim.kernel.runner import EventKernel, TransactionHandler


def build_run_header(
    run_id: str,
    code_version: str,
    config_hash: str,
    master_seed: int,
    started_at_wall: str,
    tick_size: str,
    min_quantity: str,
    cash_unit: str,
    mult: int,
    fee_bps_cap: int,
    initial_price_ticks: int,
    agent_initial_bp: dict[str, int],
    run_mode: str = "benchmark",
    information_set_mode: str = "full",
    schema_version: int = 3,
) -> dict[str, Any]:
    """Build a ``RUN_HEADER`` dict (§6.1).

    ``tick_size`` / ``min_quantity`` / ``cash_unit`` are **string decimals**
    (e.g. ``"0.01"``), never floats -- otherwise the header is not
    byte-deterministic across platforms (ADR-001 §2).

    ``mult`` / ``fee_bps_cap`` / ``initial_price_ticks`` / ``agent_initial_bp``
    are replay-critical config (F1 / ADR-004): the replay reader rebuilds
    ``reserved_units`` / ``margin_ratio_bp`` from these, so they MUST travel
    in the header to guarantee the public ``build_replay`` path produces
    E1-consistent frames without hard-coded defaults.  These four fields are
    **required** -- a producer that omits them writes a header whose replay
    config does not match the actual run, making the log unreplayable via
    the public path.  Pass ``agent_initial_bp={}`` explicitly if no agent
    has a special initial margin bp.
    """
    if not all(isinstance(x, str) for x in (tick_size, min_quantity, cash_unit)):
        raise TypeError("tick_size/min_quantity/cash_unit must be string decimals (§6.1)")
    return {
        "record_kind": "RUN_HEADER",
        "schema_version": schema_version,
        "run_id": run_id,
        "code_version": code_version,
        "config_hash": config_hash,
        "master_seed": master_seed,
        "started_at_wall": started_at_wall,
        "tick_size": tick_size,
        "min_quantity": min_quantity,
        "cash_unit": cash_unit,
        "run_mode": run_mode,
        "information_set_mode": information_set_mode,
        "mult": mult,
        "fee_bps_cap": fee_bps_cap,
        "initial_price_ticks": initial_price_ticks,
        "agent_initial_bp": dict(agent_initial_bp),
    }


def write_log(
    path: str | pathlib.Path,
    header: dict[str, Any],
    kernel: EventKernel,
    handler: TransactionHandler,
    world: dict,
    max_transactions: int,
) -> dict[str, Any]:
    """Run the kernel and write the complete event log to ``path``.

    Returns the ``RUN_TRAILER`` dict that was written.
    """
    kernel.run(handler, world, max_transactions)
    committed = kernel.committed_records
    record_count = 1 + len(committed) + 1  # header + events + trailer
    trailer = kernel.build_trailer(record_count)

    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as f:
        f.write(serialize_event(header))
        for record in committed:
            f.write(serialize_event(record))
        f.write(serialize_event(trailer))
    return trailer


def serialize_log(header: dict[str, Any], kernel: EventKernel) -> bytes:
    """Serialize the complete log to bytes (in-memory, for testing).

    The kernel must have been run already.
    """
    committed = kernel.committed_records
    record_count = 1 + len(committed) + 1
    trailer = kernel.build_trailer(record_count)
    parts = [serialize_event(header)]
    parts.extend(serialize_event(r) for r in committed)
    parts.append(serialize_event(trailer))
    return b"".join(parts)
