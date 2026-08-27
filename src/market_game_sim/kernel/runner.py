"""T204b/c/d + T204e3: Minimal deterministic event kernel runner.

[事件 Schema §1.4] 队列事件 vs 事务记录；事务内记录顺序 + 缓冲写出
[事件 Schema §1.5] fail-stop 失败语义：不回滚、不续跑
[事件 Schema §4.6.3] 强制初态快照 + bootstrap 屏障

This runner is **minimal**: it manages the queue, transaction sequencing,
buffered atomic write, and fail-stop -- but delegates matching/account
logic to a caller-provided ``handler`` callback.  Phase 3 (T301-T307)
will supply the real matching engine; Phase 2 tests inject a tiny
matching stub to exercise the invariants (OB-9a, OB-4 fault injection).

Key invariants enforced here:

* **§1.4 queue/record split**: only ``ORDER_ARRIVAL``/``AGENT_OBSERVE``/
  ``AGENT_DECIDE``/``SNAPSHOT`` are enqueued; transaction records
  (``TRADE_SETTLE`` etc.) are produced inside a transaction and never
  re-enqueued.
* **§1.4 buffered atomic write**: ``r0`` is buffered alongside its
  transaction records; ``fill_count`` is backfilled after matching;
  the whole buffer is committed atomically.  On failure the buffer is
  dropped entirely (including ``r0``).
* **§1.4 record order**: ``MARKET_DATA_PUBLISH`` is always last;
  ``accepted=false`` transactions contain only ``r0``.
* **§1.5 fail-stop**: any exception in a transaction terminates the
  run with ``terminated=ABORTED`` and a stable ``abort_code``.  No
  rollback, no resume.
* **§4.6.3 bootstrap barrier**: two ``SNAPSHOT`` queue events are
  pre-enqueued at ``t=0``; any business ``enqueue`` before bootstrap
  completes raises ``KernelAbort(INTERNAL)``.
"""

from __future__ import annotations

import heapq
from collections.abc import Callable
from typing import Any

from market_game_sim.kernel.abort import KernelAbort
from market_game_sim.kernel.keys import QueueKey, make_queue_key, priority_class_of
from market_game_sim.kernel.scheduling import check_class_regression, check_queue_monotonicity
from market_game_sim.schema.registry import QUEUE_EVENTS

#: Transaction handler signature: ``(event, world, kernel) -> records``.
#: The handler receives the popped queue event (mutable, so it can set
#: ``accepted`` / ``reject_reason`` etc. on ``r0``), the mutable world
#: (book, accounts), and the kernel (so it can ``enqueue`` new queue
#: events during the transaction).  Returns a list of transaction
#: records (``TRADE_SETTLE`` / ``ORDER_CANCELLED`` / ``MARGIN_CALL`` /
#: ``MARKET_DATA_PUBLISH``) -- **not** including ``r0``.
TransactionHandler = Callable[[dict, dict, "EventKernel"], list[dict]]


class EventKernel:
    """Minimal event kernel exercising §1.4 / §1.5 / §4.6.3 invariants."""

    def __init__(
        self,
        run_id: str = "run",
        schema_version: int = 4,
    ) -> None:
        self._run_id = run_id
        self._schema_version = schema_version
        # Priority queue: (QueueKey, tiebreaker, event_dict).
        # tiebreaker ensures dicts are never compared (QueueKey+seq is unique
        # but the guard is cheap insurance).
        self._queue: list[tuple[QueueKey, int, dict]] = []
        self._tiebreaker = 0
        self._enqueue_seq = 0
        self._transaction_seq = 0
        self._bootstrap_done = False
        self._last_popped_key: QueueKey | None = None
        self._current_event: dict | None = None
        self._last_committed_transaction_seq: int | None = None
        self._processed_transactions = 0
        self._committed_records: list[dict] = []
        self._terminated: str | None = None
        self._abort_code: str | None = None
        self._abort_detail: str | None = None

    # ------------------------------------------------------------------ #
    # Read-only properties
    # ------------------------------------------------------------------ #

    @property
    def committed_records(self) -> list[dict]:
        """All committed EVENT records (defensive shallow copy)."""
        return [dict(r) for r in self._committed_records]

    @property
    def last_committed_transaction_seq(self) -> int | None:
        return self._last_committed_transaction_seq

    @property
    def processed_transactions(self) -> int:
        return self._processed_transactions

    @property
    def terminated(self) -> str | None:
        return self._terminated

    @property
    def abort_code(self) -> str | None:
        return self._abort_code

    @property
    def abort_detail(self) -> str | None:
        return self._abort_detail

    @property
    def bootstrap_done(self) -> bool:
        return self._bootstrap_done

    @property
    def current_transaction_seq(self) -> int:
        """The transaction_seq of the currently executing transaction.

        Set at the start of :meth:`_run_transaction` before the handler
        is called, so handlers can construct ``caused_by_event_id``
        (which references r0's ``event_id = f"e{txn_seq}_0"``).
        """
        return self._transaction_seq

    @property
    def queue_empty(self) -> bool:
        return len(self._queue) == 0

    # ------------------------------------------------------------------ #
    # Bootstrap (§4.6.3)
    # ------------------------------------------------------------------ #

    def bootstrap(self, account_payload: dict, book_payload: dict) -> None:
        """Pre-enqueue two ``SNAPSHOT`` queue events at ``t=0``.

        ``ACCOUNT`` (``enqueue_seq=0``) -> ``transaction_seq=1``;
        ``BOOK``    (``enqueue_seq=1``) -> ``transaction_seq=2``;
        business transactions start from ``transaction_seq=3``.

        Must be called exactly once, before :meth:`enqueue` / :meth:`run`.
        """
        if self._bootstrap_done:
            raise KernelAbort(abort_code="INTERNAL", detail="bootstrap already done")
        if self._enqueue_seq != 0:
            raise KernelAbort(abort_code="INTERNAL", detail="bootstrap called after enqueue")
        account_event = {
            "event_type": "SNAPSHOT",
            "timestamp": 0,
            "snapshot_type": "ACCOUNT",
            "payload": account_payload,
            "_enqueue_seq": 0,
        }
        book_event = {
            "event_type": "SNAPSHOT",
            "timestamp": 0,
            "snapshot_type": "BOOK",
            "payload": book_payload,
            "_enqueue_seq": 1,
        }
        self._push_raw(account_event)
        self._push_raw(book_event)
        self._bootstrap_done = True

    def _push_raw(self, event: dict) -> None:
        """Push without barrier / monotonicity check (bootstrap only)."""
        key = make_queue_key(event["timestamp"], event["event_type"], event["_enqueue_seq"])
        heapq.heappush(self._queue, (key, self._tiebreaker, event))
        self._tiebreaker += 1
        self._enqueue_seq += 1

    # ------------------------------------------------------------------ #
    # Enqueue (business events)
    # ------------------------------------------------------------------ #

    def enqueue(self, event: dict) -> None:
        """Enqueue a business queue event (§1.4).

        Raises ``KernelAbort(INTERNAL)`` if bootstrap is not complete
        (§4.6.3 barrier).  Enforces KR-006 monotonicity (T202) and
        class-regression whitelist (T203) at enqueue time.
        """
        if not self._bootstrap_done:
            raise KernelAbort(
                abort_code="INTERNAL",
                detail="enqueue called before bootstrap complete (§4.6.3 barrier)",
            )
        event_type = event["event_type"]
        if event_type not in QUEUE_EVENTS:
            raise KernelAbort(
                abort_code="INTERNAL",
                detail=f"enqueue rejects non-queue event type {event_type} (§1.4)",
            )
        timestamp = event["timestamp"]
        enqueue_seq = self._enqueue_seq
        event["_enqueue_seq"] = enqueue_seq
        key = make_queue_key(timestamp, event_type, enqueue_seq)
        if self._last_popped_key is not None:
            check_queue_monotonicity(key, self._last_popped_key)
        if self._current_event is not None:
            # Class regression only applies during a transaction (§1.2).
            check_class_regression(
                self._current_event["event_type"],
                event_type,
                self._current_event["timestamp"],
                timestamp,
            )
        heapq.heappush(self._queue, (key, self._tiebreaker, event))
        self._tiebreaker += 1
        self._enqueue_seq += 1

    # ------------------------------------------------------------------ #
    # Run loop
    # ------------------------------------------------------------------ #

    def run(
        self,
        handler: TransactionHandler,
        world: dict,
        max_transactions: int,
    ) -> None:
        """Run until the queue is empty, ``max_transactions`` is reached,
        or a fail-stop abort occurs (§1.5)."""
        if not self._bootstrap_done:
            raise KernelAbort(abort_code="INTERNAL", detail="run called before bootstrap")
        try:
            while self._queue and self._processed_transactions < max_transactions:
                _, _, event = heapq.heappop(self._queue)
                self._last_popped_key = make_queue_key(
                    event["timestamp"],
                    event["event_type"],
                    event["_enqueue_seq"],
                )
                self._run_transaction(event, handler, world)
        except KernelAbort as exc:
            self._terminate_aborted(exc.abort_code, exc.detail)
        except Exception as exc:
            self._terminate_aborted("INTERNAL", repr(exc))
        else:
            self._terminate_completed()

    def _run_transaction(
        self,
        event: dict,
        handler: TransactionHandler,
        world: dict,
    ) -> None:
        """Run one transaction with buffered atomic write (§1.4) + fail-stop (§1.5).

        On success the buffer (``r0`` + records) is committed atomically.
        On any exception the buffer is dropped entirely (including ``r0``)
        and the exception propagates to :meth:`run` for fail-stop handling.
        """
        self._transaction_seq += 1
        txn_seq = self._transaction_seq
        self._current_event = event

        buffer: list[dict] = []
        try:
            # Handler mutates ``event`` (sets accepted etc.) and returns
            # transaction records (NOT including r0).
            records = handler(event, world, self)

            # Transaction records inherit the parent event's timestamp.
            parent_ts = event["timestamp"]
            for r in records:
                r.setdefault("timestamp", parent_ts)

            # Build r0 from the (possibly mutated) event.
            r0 = self._build_record(event, txn_seq, 0, event.get("_enqueue_seq"))
            buffer.append(r0)

            # Backfill fill_index / fill_count on TRADE_SETTLE records.
            trade_settles = [r for r in records if r.get("event_type") == "TRADE_SETTLE"]
            fill_count = len(trade_settles)
            for ti, r in enumerate(trade_settles):
                r.setdefault("fill_index", ti)
                r["fill_count"] = fill_count

            # Assign record_index and build full EVENT records.
            for idx, r in enumerate(records, start=1):
                buffer.append(self._build_record(r, txn_seq, idx, None))

            # §1.4 frozen transaction record order invariants.
            self._validate_transaction_order(buffer)
        finally:
            self._current_event = None

        # Commit atomically (only reached on success).
        self._committed_records.extend(buffer)
        self._last_committed_transaction_seq = txn_seq
        self._processed_transactions += 1

        # 0.1.5 T206/T207: maintain the global public tape + the latest market
        # data boundary.  The kernel is the only place that knows each record's
        # final event_id, so TRADE_SETTLE records are projected here into
        # ``world["public_tape"]`` (an ordered list of {event_id, price_ticks,
        # quantity_units, timestamp, taker_agent_id}) that every agent consumes
        # via its own cursor (代理策略 §1), and the last committed
        # MARKET_DATA_PUBLISH event_id is recorded so the observe scheduler
        # can snapshot a *fresh* cursor boundary for the next observation
        # (R018-C001: previously the scheduler hardcoded the bootstrap id).
        # Absent from ``world`` (legacy callers) -> no-op.
        tape = world.get("public_tape")
        if tape is not None:
            for r in buffer:
                if r.get("event_type") == "TRADE_SETTLE":
                    tape.append(
                        {
                            "event_id": r["event_id"],
                            "price_ticks": r["price_ticks"],
                            "quantity_units": r["quantity_units"],
                            "timestamp": r["timestamp"],
                            "taker_agent_id": r["taker_agent_id"],
                        }
                    )
                elif r.get("event_type") == "MARKET_DATA_PUBLISH":
                    world["last_market_data_event_id"] = r["event_id"]

        # R018-C002: apply the observe transaction's staged cursor / EWMA
        # advance now that the transaction has committed.  The handler staged
        # it on r0 (``event["_pending_agent_state"]``) so it commits with THIS
        # transaction and is dropped with the buffer on abort -- Round 3 found
        # the previous shared-world-dict staging leaked a failed observation's
        # cursor into a later successful transaction.
        r0 = buffer[0]
        pending = r0.get("_pending_agent_state")
        if pending:
            cursors = world.setdefault("agent_cursors", {})
            ewma = world.setdefault("agent_ewma", {})
            cursors[pending["agent_id"]] = pending["cursor"]
            ewma[pending["agent_id"]] = {
                "value": pending["ewma_value"],
                "count": pending["ewma_count"],
            }
        # The staged state is a transaction-internal channel, not a log field.
        r0.pop("_pending_agent_state", None)

    # ------------------------------------------------------------------ #
    # Record construction
    # ------------------------------------------------------------------ #

    def _build_record(
        self,
        event: dict,
        txn_seq: int,
        record_idx: int,
        enqueue_seq: int | None,
    ) -> dict:
        """Merge EVENT_COMMON fields with event-specific fields (T204e shape).

        Strips internal keys (``_enqueue_seq``) and fills system fields
        (``record_kind``, ``schema_version``, ``event_id``, ``run_id``,
        ``transaction_seq``, ``record_index``, ``priority_class``,
        ``enqueue_seq``).  Event-specific fields from the event dict
        are preserved.
        """
        event_type = event["event_type"]
        record: dict[str, Any] = dict(event)
        record.pop("_enqueue_seq", None)
        record["record_kind"] = "EVENT"
        record["schema_version"] = self._schema_version
        record["event_id"] = f"e{txn_seq}_{record_idx}"
        record["run_id"] = self._run_id
        record["timestamp"] = event["timestamp"]
        record["transaction_seq"] = txn_seq
        record["record_index"] = record_idx
        record["priority_class"] = int(priority_class_of(event_type))
        record["event_type"] = event_type
        record["enqueue_seq"] = enqueue_seq
        return record

    # ------------------------------------------------------------------ #
    # §1.4 transaction order validation
    # ------------------------------------------------------------------ #

    def _validate_transaction_order(self, buffer: list[dict]) -> None:
        """Assert §1.4 frozen transaction record order invariants.

        1. ``MARKET_DATA_PUBLISH`` is always the last record (if present).
        2. ``accepted=false`` transactions contain only ``r0``.
        """
        r0 = buffer[0]
        records = buffer[1:]
        if not records:
            return
        # (1) MARKET_DATA_PUBLISH must be last.
        for r in records[:-1]:
            if r["event_type"] == "MARKET_DATA_PUBLISH":
                raise KernelAbort(
                    abort_code="INTERNAL",
                    detail="MARKET_DATA_PUBLISH must be the last record in a transaction (§1.4)",
                )
        # (2) accepted=false -> only r0.
        if r0["event_type"] == "ORDER_ARRIVAL" and not r0.get("accepted", True):
            raise KernelAbort(
                abort_code="INTERNAL",
                detail="accepted=false transaction must have only r0 (§1.4)",
            )

    # ------------------------------------------------------------------ #
    # Termination
    # ------------------------------------------------------------------ #

    def _terminate_aborted(self, abort_code: str, detail: str) -> None:
        self._terminated = "ABORTED"
        self._abort_code = abort_code
        self._abort_detail = detail

    def _terminate_completed(self) -> None:
        self._terminated = "COMPLETED"

    # ------------------------------------------------------------------ #
    # RUN_TRAILER construction (§6.2) -- used by T205 writer
    # ------------------------------------------------------------------ #

    def build_trailer(self, record_count: int) -> dict:
        """Build a ``RUN_TRAILER`` dict from the kernel's termination state.

        ``record_count`` is the total number of records in the log
        (header + events + trailer = record_count, so the caller adds 1
        for the header and 1 for the trailer itself).
        """
        if self._terminated is None:
            raise KernelAbort(abort_code="INTERNAL", detail="build_trailer before run completes")
        return {
            "record_kind": "RUN_TRAILER",
            "terminated": self._terminated,
            "abort_code": self._abort_code,
            "abort_detail": self._abort_detail,
            "last_committed_transaction_seq": self._last_committed_transaction_seq,
            "record_count": record_count,
        }
