"""T905：所有者会话的阶段标识与解盲规则（DR-301 / IR-301 / AC-308）。

双轨合同下**没有外部参与者**，所以这里没有报名、同意书、资格筛选或撤回同意流程；
唯一的真人是项目所有者本人，仓库里只出现他的研究假名。

本模块负责三件事：

* **阶段标识**：`training` 与 `formal` 必须始终可分辨（UX-303）。训练数据永不进入
  正式证据，而"忘了自己在训练局里"是最容易污染样本的一种方式。
* **解盲**：所有者同时是实验设计者与被试，这条偏倚消不掉、只能约束——24 个正式场景
  全部完成前，任何已完成场景的结果都不可读取（合同 ``unblinding_rule``）。
* **假名**：所有者只以 ``owner-<n>`` 出现，仓库不保存任何身份映射。
* **窗口调度**（T910/FR-302/TR-302）：有限决策窗口、单次提交、超时 ``NO_ACTION``、
  迟到输入拒绝。唯一线性化点是 ``submit()`` 内会话锁保护的"最终动作槽"占用——谁先
  在锁内把 ``decision`` 从 ``None`` 改成非 ``None``，谁的输入生效；deadline 只用真实
  单调钟判断，不回拨逻辑时间（design.md §5）。
* **正式会话状态机**（T911/UX-301—303）：``FormalSession`` 把窗口序列映射成 UX-302
  规定的七个可观察状态；``remaining_seconds()`` 给客户端倒计时；状态只反映"当前
  窗口发生了什么"，不复制撮合/风控业务逻辑。
"""

from __future__ import annotations

import itertools
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from market_game_sim.experiment.h2 import protocol

#: 仓库内唯一允许出现的所有者标识形态。
OWNER_ID = "owner-1"


class Stage(StrEnum):
    TRAINING = "training"
    FORMAL = "formal"


class SessionError(RuntimeError):
    """所有者会话合同被违反。"""


class StillBlinded(SessionError):
    """正式场景尚未全部完成，结果处于封盲状态。"""


@dataclass(frozen=True, slots=True)
class OwnerSession:
    """一次所有者会话。``stage`` 决定它的产物能否进入正式证据。"""

    stage: Stage
    owner_id: str = OWNER_ID


@dataclass(frozen=True, slots=True)
class OwnerProgress:
    """所有者在正式轨上的进度，用来判定是否可以解盲。"""

    completed: int
    required: int

    @property
    def is_complete(self) -> bool:
        return self.completed >= self.required


def _required_formal_scenarios() -> int:
    """正式场景数取自冻结合同，不在代码里另写一个 24。"""
    contract = protocol.load_contract()
    return int(contract["owner_n_of_1_track"]["formal_paired_blocks"])


def start_training() -> OwnerSession:
    return OwnerSession(stage=Stage.TRAINING)


def start_formal() -> OwnerSession:
    return OwnerSession(stage=Stage.FORMAL)


def stage_of(session: OwnerSession) -> str:
    return str(session.stage)


def owner_progress(*, completed: int, required: int | None = None) -> OwnerProgress:
    if completed < 0:
        raise SessionError("已完成场景数不能为负")
    return OwnerProgress(
        completed=completed,
        required=_required_formal_scenarios() if required is None else required,
    )


def read_results(progress: OwnerProgress) -> dict[str, Any]:
    """解盲入口。未跑满正式场景一律拒绝，不提供"只看一眼"的旁路。"""
    if not progress.is_complete:
        raise StillBlinded(
            f"正式场景尚未跑满（{progress.completed}/{progress.required}），结果保持封盲"
        )
    return {
        "unblinded": True,
        "completed_scenarios": progress.completed,
        "owner_id": OWNER_ID,
    }


def formal_client_controls() -> tuple[str, ...]:
    """正式态客户端暴露的控制项。

    这是一个**闭集**：暂停、单步、改参和任何未来信息都不在其中——正式会话一旦能暂停，
    所有者就获得了参照策略没有的无限思考时间，配对比较随即失效（spec 非目标）。
    """
    return ("submit_order", "cancel_order", "view_own_account", "abort_session")


# --------------------------------------------------------------------------- #
# T910：有限决策窗口、单次提交、超时 NO_ACTION、迟到输入拒绝
# --------------------------------------------------------------------------- #


class SubmitResult(StrEnum):
    """``submit()`` 的两种结果。是否被接受不取决于"合法性判断"——窗口机制不校验
    订单本身是否合规（那是撮合层的事），只判断"这次提交是否占到了最终动作槽"。
    """

    ACCEPTED = "ACCEPTED"
    WINDOW_CLOSED = "WINDOW_CLOSED"


ACCEPTED = SubmitResult.ACCEPTED
WINDOW_CLOSED = SubmitResult.WINDOW_CLOSED

#: 窗口超时且无有效输入时的规范决定；与真实提交的 OrderIntent 用同一个字段承载。
NO_ACTION = "NO_ACTION"

_input_seq_counter = itertools.count(1)


@dataclass(frozen=True, slots=True)
class OrderIntent:
    """所有者窗口内提交的规范决定的最小信封。

    真实的下单校验、撮合与账本路径属于市场内核；这里只承载窗口控制器判定"这是一次
    合法提交尝试"所需的字段，以及 TR-302 要求的 ``intent_id`` 关联锚点。
    """

    intent_id: str
    side: str = "buy"
    quantity: int = 1


def sample_order() -> OrderIntent:
    """构造一个用于测试/预览的示例订单意图。"""
    return OrderIntent(intent_id=f"intent-{next(_input_seq_counter)}")


def _window_contract() -> dict[str, Any]:
    return protocol.frozen_window_contract()


@dataclass(slots=True)
class Window:
    """一个决策窗口。``decision`` 从 ``None`` 变为非 ``None`` 是唯一的线性化事件，
    在 ``_lock`` 保护下发生，且只发生一次——之后的所有提交都是 ``WINDOW_CLOSED``。
    """

    index: int
    open_monotonic_ns: int
    deadline_monotonic_ns: int
    window_id: str
    decision: OrderIntent | str | None = None
    received_monotonic_ns: int | None = None
    explicitly_closed: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    @property
    def is_open(self) -> bool:
        return self.decision is None and not self.explicitly_closed


def open_window(index: int, *, duration_ns: int | None = None) -> Window:
    """开窗。默认时长取自冻结窗口合同的 ``owner_wall_clock_seconds``——这是给真人
    的真实响应时限，不是 ``logical_ns_per_window``（那是市场每窗推进的模拟时间，
    两者单位都是纳秒但语义完全不同，不能混用）。
    """
    if duration_ns is None:
        seconds = _window_contract()["owner_wall_clock_seconds"]
        duration_ns = int(seconds) * 1_000_000_000
    now = time.monotonic_ns()
    return Window(
        index=index,
        open_monotonic_ns=now,
        deadline_monotonic_ns=now + duration_ns,
        window_id=f"window-{index}",
    )


def submit(window: Window, order: OrderIntent) -> SubmitResult:
    """提交一次决定。会话锁内完成"未占用 + 未超时"的检查与占用，是唯一线性化点。

    迟到输入（``received_monotonic_ns >= deadline_monotonic_ns``）稳定返回
    ``WINDOW_CLOSED``，不改写窗口状态、不回拨逻辑时间——真正把窗口标记为已关闭是
    调度器调用 ``close()`` 的职责，``submit()`` 只负责"这次提交本身算不算数"。
    """
    with window._lock:  # noqa: SLF001 -- 窗口自身状态的唯一入口，模块内访问
        if window.decision is not None or window.explicitly_closed:
            return WINDOW_CLOSED
        received = time.monotonic_ns()
        if received >= window.deadline_monotonic_ns:
            return WINDOW_CLOSED
        window.decision = order
        window.received_monotonic_ns = received
        return ACCEPTED


def close(window: Window) -> None:
    """关闭窗口。若窗口内没有被占用的决定，落定为 ``NO_ACTION``；幂等。"""
    with window._lock:  # noqa: SLF001
        window.explicitly_closed = True
        if window.decision is None:
            window.decision = NO_ACTION


def recorded_decision(window: Window) -> str:
    """窗口最终落定的决定：``NO_ACTION`` 或已接受订单的 ``intent_id``。

    未关闭窗口调用属于用法错误——决定只有在 ``close()`` 之后才算落定，调用方不应
    在窗口仍开放时读取它，读到的要么是尚未确定的中间态，要么是误以为"没提交就是
    NO_ACTION"，两者都不对。
    """
    if window.decision is None:
        raise SessionError(f"窗口 {window.window_id} 尚未关闭，决定未落定")
    if isinstance(window.decision, str):
        return window.decision
    return window.decision.intent_id


# --------------------------------------------------------------------------- #
# T911：正式会话状态机、倒计时与阶段提示
# --------------------------------------------------------------------------- #


class SessionState(StrEnum):
    """正式会话的七个可观察状态（design.md §6 / UX-302）。

    状态由窗口事件驱动：开窗进入 ``ACTIVE_WINDOW``；提交成功进入 ``SUBMITTED``；
    窗口超时无提交进入 ``NO_ACTION``；全部窗口跑完进入 ``COMPLETED``；两种终止路径
    分别是 ``TECHNICAL_ABORT``（系统故障）与 ``ABORTED``（所有者主动中止）。
    """

    WAITING = "waiting"
    ACTIVE_WINDOW = "active-window"
    SUBMITTED = "submitted"
    NO_ACTION = "no-action"
    COMPLETED = "completed"
    TECHNICAL_ABORT = "technical-abort"
    ABORTED = "aborted"


#: 会话一旦进入这些状态即终止，不得再开窗或提交。
_TERMINAL_STATES = frozenset(
    {SessionState.COMPLETED, SessionState.TECHNICAL_ABORT, SessionState.ABORTED}
)


@dataclass(slots=True)
class FormalSession:
    """一次所有者正式场景的窗口序列状态机。

    只负责状态映射与窗口生命周期，不连接市场内核——真正跑场景、把决定路由进撮合
    是 T917 的事；这里的产物是客户端可以直接渲染的七个状态值和倒计时数字。
    """

    total_windows: int
    state: SessionState = SessionState.WAITING
    current_window: Window | None = None
    completed_windows: int = 0

    def open_next_window(self, *, duration_ns: int | None = None) -> Window:
        if self.state in _TERMINAL_STATES:
            raise SessionError(f"会话已处于终止状态 {self.state!r}，不得再开窗")
        if self.completed_windows >= self.total_windows:
            raise SessionError("窗口已全部完成，不得再开窗")
        self.current_window = open_window(self.completed_windows, duration_ns=duration_ns)
        self.state = SessionState.ACTIVE_WINDOW
        return self.current_window

    def submit(self, order: OrderIntent) -> SubmitResult:
        if self.state is not SessionState.ACTIVE_WINDOW or self.current_window is None:
            raise SessionError(f"当前状态 {self.state!r} 下没有开放中的窗口")
        result = submit(self.current_window, order)
        if result is ACCEPTED:
            self.state = SessionState.SUBMITTED
        return result

    def close_current_window(self) -> None:
        if self.current_window is None:
            raise SessionError("没有可关闭的窗口")
        close(self.current_window)
        self.completed_windows += 1
        if recorded_decision(self.current_window) == NO_ACTION:
            self.state = SessionState.NO_ACTION
        # 否则保持 submit() 已设置的 SUBMITTED，不在这里覆盖。
        if self.completed_windows >= self.total_windows:
            self.state = SessionState.COMPLETED

    def abort(self, *, technical: bool) -> None:
        """中止会话。``technical=True`` 对应系统故障，否则是所有者主动中止。"""
        if self.state in _TERMINAL_STATES:
            raise SessionError(f"会话已处于终止状态 {self.state!r}，不得重复中止")
        self.state = SessionState.TECHNICAL_ABORT if technical else SessionState.ABORTED


def remaining_seconds(window: Window) -> float:
    """窗口剩余可提交时间，供客户端倒计时显示（UX-301）。已关闭窗口返回 0。"""
    if not window.is_open:
        return 0.0
    remaining_ns = window.deadline_monotonic_ns - time.monotonic_ns()
    return max(0.0, remaining_ns / 1_000_000_000)


# --------------------------------------------------------------------------- #
# T915：规范输入重放（AC-304 的"处理重放"要求同样适用于所有者会话）
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class RecordedDecision:
    """一次窗口提交的规范记录——重放只读这个，不依赖任何真实墙钟等待。"""

    window_index: int
    submitted: bool
    intent_id: str | None = None


def run_fixed_session(
    total_windows: int, decisions: Sequence[RecordedDecision]
) -> tuple[FormalSession, tuple[RecordedDecision, ...]]:
    """用固定假输入跑一次会话：每一窗按 ``decisions`` 里对应记录提交或放弃。

    窗口时长给得足够宽松（5 秒），但**全程不调用任何 sleep**——不是"等墙钟"，只是
    给出一个不会被本地执行开销意外触发迟到判定的时限。真实所有者会话里这个时限是
    合同里的 8 秒真实响应窗口；这里只是复用同一条 ``submit()`` 路径。
    """
    by_index = {d.window_index: d for d in decisions}
    session = FormalSession(total_windows=total_windows)
    recorded: list[RecordedDecision] = []
    for index in range(total_windows):
        session.open_next_window(duration_ns=5_000_000_000)
        planned = by_index.get(index)
        if planned is not None and planned.submitted:
            order = OrderIntent(intent_id=planned.intent_id or f"fixed-{index}")
            session.submit(order)
            recorded.append(RecordedDecision(index, True, order.intent_id))
        else:
            recorded.append(RecordedDecision(index, False, None))
        session.close_current_window()
    return session, tuple(recorded)


def replay_fixed_session(total_windows: int, recorded: Sequence[RecordedDecision]) -> FormalSession:
    """从规范输入记录重放会话，不等待墙钟——同样的记录必须产生同样的最终状态。

    这是 AC-304"处理重放"对所有者会话的落点：重放读的是 ``RecordedDecision``，
    不是重新等一遍真实的人类响应时间。
    """
    session, replayed = run_fixed_session(total_windows, recorded)
    if replayed != tuple(recorded)[: len(replayed)]:
        raise SessionError("重放结果与记录的规范输入不一致")
    return session
