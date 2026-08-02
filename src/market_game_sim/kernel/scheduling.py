"""T202 + T203: Queue scheduling invariants (事件 Schema §1.1, §1.2).

Two invariants guard the event queue.  Both are fail-stop (§1.5): violation
means the kernel has a bug, and the run terminates with a specific
``abort_code`` rather than silently reordering events.

* **KR-006 monotonicity (T202)**: every newly enqueued event must have a
  ``queue_key`` strictly greater than the current queue event's key.  The
  check happens at **enqueue time**, not at pop time -- a violated event
  must never enter the queue.

* **Class-regression whitelist (T203)**: when a new event's
  ``priority_class`` is lower than the producing event's class (a
  "regression"), the jump must appear in §1.2's whitelist **and** the
  timestamp must advance by at least 1 ns.  Table外的 regressions are
  implementation defects.

Both checks raise :class:`~market_game_sim.kernel.abort.KernelAbort`
carrying the stable ``abort_code``; the runner writes ``RUN_TRAILER`` and
halts (T204d).
"""

from __future__ import annotations

from market_game_sim.kernel.abort import KernelAbort
from market_game_sim.kernel.keys import QueueKey, priority_class_of

#: 事件 Schema §1.2 回退跳转白名单。
#: (producing_event_type, new_event_type) -> minimum timestamp advance (ns).
CLASS_REGRESSION_WHITELIST: dict[tuple[str, str], int] = {
    ("AGENT_DECIDE", "ORDER_ARRIVAL"): 1,
    ("MARGIN_CALL", "ORDER_ARRIVAL"): 1,
}


def check_queue_monotonicity(new_key: QueueKey, current_key: QueueKey) -> None:
    """KR-006: ``new_key`` must be strictly greater than ``current_key``.

    Raises :class:`KernelAbort` with ``abort_code=QUEUE_KEY_MONOTONICITY``
    if violated.  Called at enqueue time; never lets the event enter the
    queue when the check fails.
    """
    if not (new_key > current_key):
        raise KernelAbort(
            abort_code="QUEUE_KEY_MONOTONICITY",
            detail=(f"queue_key monotonicity violated: new {new_key} <= current {current_key}"),
        )


def check_class_regression(
    producing_event_type: str,
    new_event_type: str,
    producing_timestamp: int,
    new_timestamp: int,
) -> None:
    """§1.2: class regressions must be whitelisted and advance time.

    A *regression* is a new event whose ``priority_class`` is lower than the
    producing event's class.  Only ``AGENT_DECIDE -> ORDER_ARRIVAL`` and
    ``MARGIN_CALL -> ORDER_ARRIVAL`` are whitelisted, and both must cross
    at least 1 ns.

    Raises :class:`KernelAbort` with
    ``abort_code=CLASS_REGRESSION_NOT_WHITELISTED`` for violations.
    """
    producing_class = priority_class_of(producing_event_type)
    new_class = priority_class_of(new_event_type)
    if new_class >= producing_class:
        return

    jump = (producing_event_type, new_event_type)
    if jump not in CLASS_REGRESSION_WHITELIST:
        raise KernelAbort(
            abort_code="CLASS_REGRESSION_NOT_WHITELISTED",
            detail=(
                f"class regression {jump} not in whitelist "
                f"(producing class={int(producing_class)}, "
                f"new class={int(new_class)})"
            ),
        )
    min_advance = CLASS_REGRESSION_WHITELIST[jump]
    advance = new_timestamp - producing_timestamp
    if advance < min_advance:
        raise KernelAbort(
            abort_code="CLASS_REGRESSION_NOT_WHITELISTED",
            detail=(
                f"class regression {jump} advances only {advance} ns, minimum is {min_advance}"
            ),
        )
