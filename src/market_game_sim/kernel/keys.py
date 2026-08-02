"""T201 + T204: Dual ordering keys and frozen priority classes.

事件 Schema §1 defines two independent ordering keys:

* ``queue_key = (timestamp, priority_class, enqueue_seq)``
    decides when a queue event pops.  Only queue events (§1.4) carry one.
* ``log_key = (timestamp, transaction_seq, record_index)``
    decides log order, hash order and replay order.  Every record carries one.

Three monotonic counters with **distinct scopes and allocation moments**
(事件 Schema §1):

* ``enqueue_seq``      allocated at enqueue time, global across the run.
* ``transaction_seq``  allocated when a queue event pops, global across the run.
* ``record_index``     allocated within a transaction; parent = 0, records = 1..

They must never be substituted for one another -- using ``enqueue_seq`` where
``transaction_seq`` belongs would break log ordering and hash stability.

Priority classes (§3, frozen) are integers 0-5; multiple event types share a
class (``ORDER_ARRIVAL``/``ORDER_CANCELLED`` = 0, ``TRADE_SETTLE``/
``MARGIN_CALL`` = 1).  This module defines the mapping as the single source
within the kernel; ``schema.registry`` mirrors it for query convenience but
the kernel is the authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class PriorityClass(IntEnum):
    """事件 Schema §3 冻结的队列调度类别。数值越小越先处理。"""

    ORDER = 0
    SETTLE = 1
    MARKET_DATA = 2
    OBSERVE = 3
    DECIDE = 4
    SNAPSHOT = 5


EVENT_TYPE_PRIORITY_CLASS: dict[str, PriorityClass] = {
    "ORDER_ARRIVAL": PriorityClass.ORDER,
    "ORDER_CANCELLED": PriorityClass.ORDER,
    "TRADE_SETTLE": PriorityClass.SETTLE,
    "MARGIN_CALL": PriorityClass.SETTLE,
    "MARKET_DATA_PUBLISH": PriorityClass.MARKET_DATA,
    "AGENT_OBSERVE": PriorityClass.OBSERVE,
    "AGENT_DECIDE": PriorityClass.DECIDE,
    "SNAPSHOT": PriorityClass.SNAPSHOT,
}


def priority_class_of(event_type: str) -> PriorityClass:
    if event_type not in EVENT_TYPE_PRIORITY_CLASS:
        raise ValueError(f"Unknown event_type: {event_type}")
    return EVENT_TYPE_PRIORITY_CLASS[event_type]


@dataclass(frozen=True, order=True)
class QueueKey:
    """事件 Schema §1 队列键。只决定队列事件何时弹出。"""

    timestamp: int
    priority_class: int
    enqueue_seq: int


@dataclass(frozen=True, order=True)
class LogKey:
    """事件 Schema §1 日志键。决定日志、哈希与重放顺序。"""

    timestamp: int
    transaction_seq: int
    record_index: int


def make_queue_key(timestamp: int, event_type: str, enqueue_seq: int) -> QueueKey:
    return QueueKey(
        timestamp=timestamp,
        priority_class=int(priority_class_of(event_type)),
        enqueue_seq=enqueue_seq,
    )
