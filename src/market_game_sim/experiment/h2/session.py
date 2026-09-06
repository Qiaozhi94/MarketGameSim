"""T905：所有者会话的阶段标识与解盲规则（DR-301 / IR-301 / AC-308）。

双轨合同下**没有外部参与者**，所以这里没有报名、同意书、资格筛选或撤回同意流程；
唯一的真人是项目所有者本人，仓库里只出现他的研究假名。

本模块负责三件事：

* **阶段标识**：`training` 与 `formal` 必须始终可分辨（UX-303）。训练数据永不进入
  正式证据，而"忘了自己在训练局里"是最容易污染样本的一种方式。
* **解盲**：所有者同时是实验设计者与被试，这条偏倚消不掉、只能约束——24 个正式场景
  全部完成前，任何已完成场景的结果都不可读取（合同 ``unblinding_rule``）。
* **假名**：所有者只以 ``owner-<n>`` 出现，仓库不保存任何身份映射。
"""

from __future__ import annotations

from dataclasses import dataclass
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
