"""事件 Schema §6.2 稳定错误码与内核终止异常。

``abort_code`` 是写入 ``RUN_TRAILER`` 的稳定枚举，新增须提升
``schema_version``。``abort_detail`` 含异常消息与栈，不参与任何判定。

``KernelAbort`` 是 fail-stop 的载体：事务中抛出时，内核终止整个运行，
不回滚、不续跑（§1.5）。失败事务的缓冲整体丢弃（含 ``r0``），
日志尾部写 ``terminated=ABORTED``。
"""

from __future__ import annotations

from typing import Literal

AbortCode = Literal[
    "QUEUE_KEY_MONOTONICITY",
    "CLASS_REGRESSION_NOT_WHITELISTED",
    "CONSERVATION_BREACH",
    "ILLEGAL_STATE_TRANSITION",
    "CONFIG_INVARIANT",
    "INTERNAL",
]

ABORT_CODES: tuple[str, ...] = (
    "QUEUE_KEY_MONOTONICITY",
    "CLASS_REGRESSION_NOT_WHITELISTED",
    "CONSERVATION_BREACH",
    "ILLEGAL_STATE_TRANSITION",
    "CONFIG_INVARIANT",
    "INTERNAL",
)


class KernelAbort(Exception):
    """fail-stop 异常：携带稳定 ``abort_code``，由运行器写入尾部。"""

    def __init__(self, abort_code: AbortCode, detail: str = "") -> None:
        if abort_code not in ABORT_CODES:
            raise ValueError(f"Unknown abort_code: {abort_code}")
        self.abort_code: str = abort_code
        self.detail: str = detail
        super().__init__(f"[{abort_code}] {detail}" if detail else f"[{abort_code}]")
