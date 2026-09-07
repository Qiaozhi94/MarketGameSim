"""T914：技术中止、所有者中止、补跑与结果盲 adjudication（FR-303 / NFR-303 / AC-303 / AC-308）。

核心不变量——**裁决器看不见结果**：design.md §5 "session 完成不等于纳入；adjudication
只读取技术/协议字段，结果字段对裁决器不可见"。这里不是靠"请裁决函数不要看结果"的
自觉，而是结构性的：``TechnicalRecord`` 这个类型本身没有任何字段能装严重度、效应量
或任何市场结果——``adjudicate()`` 拿到的输入里根本不存在可以偷看的东西。

只有预定义技术故障允许补跑（Q-305）：所有者主动中止、协议漂移、pair 不完整都不触发
补跑；只有 ``technical-abort`` 触发，且补跑必须消耗预签发备用池的下一个 seed（复用
``assignment.rerun_assignment`` 的有序消耗逻辑，不在这里另写一套），原中止记录保留在
样本流图里。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from market_game_sim.experiment.h2 import assignment


#: 冻结 reason code 闭集。不得因表现或结果极端补跑——闭集里没有"结果不好"这个选项。
class ExclusionReason(StrEnum):
    PROTOCOL_DRIFT = "PROTOCOL_DRIFT"
    TECHNICAL_ABORT = "TECHNICAL_ABORT"
    OWNER_ABORT = "OWNER_ABORT"
    INCOMPLETE_PAIR = "INCOMPLETE_PAIR"
    INCOMPLETE_SESSION = "INCOMPLETE_SESSION"


class AdjudicationStatus(StrEnum):
    INCLUDED = "included"
    EXCLUDED = "excluded"


class AdjudicationError(RuntimeError):
    """裁决合同被违反。"""


@dataclass(frozen=True, slots=True)
class TechnicalRecord:
    """裁决器唯一可见的输入——只含技术/协议字段。

    这个类型故意不提供任何存放结果数据的地方：没有 severity、没有 effect、没有
    market outcome。调用方即使想把结果字段传进来，也没有字段可以传。
    """

    assignment_id: str
    session_state: str
    pair_complete: bool
    protocol_hash: str
    expected_protocol_hash: str


@dataclass(frozen=True, slots=True)
class AdjudicationDecision:
    assignment_id: str
    status: AdjudicationStatus
    reason: ExclusionReason | None
    rerun_required: bool


#: 只有这一种终止路径会触发补跑——所有者主动中止、协议漂移、pair 不完整都不会。
_RERUN_TRIGGERS = frozenset({ExclusionReason.TECHNICAL_ABORT})


def adjudicate(record: TechnicalRecord) -> AdjudicationDecision:
    """按冻结规则裁决单条记录。规则顺序即优先级：协议漂移最先检查，其余次之。"""
    if record.protocol_hash != record.expected_protocol_hash:
        return AdjudicationDecision(
            record.assignment_id, AdjudicationStatus.EXCLUDED, ExclusionReason.PROTOCOL_DRIFT, False
        )
    if record.session_state == "technical-abort":
        return AdjudicationDecision(
            record.assignment_id, AdjudicationStatus.EXCLUDED, ExclusionReason.TECHNICAL_ABORT, True
        )
    if record.session_state == "aborted":
        return AdjudicationDecision(
            record.assignment_id, AdjudicationStatus.EXCLUDED, ExclusionReason.OWNER_ABORT, False
        )
    if not record.pair_complete:
        return AdjudicationDecision(
            record.assignment_id,
            AdjudicationStatus.EXCLUDED,
            ExclusionReason.INCOMPLETE_PAIR,
            False,
        )
    if record.session_state != "completed":
        return AdjudicationDecision(
            record.assignment_id,
            AdjudicationStatus.EXCLUDED,
            ExclusionReason.INCOMPLETE_SESSION,
            False,
        )
    return AdjudicationDecision(record.assignment_id, AdjudicationStatus.INCLUDED, None, False)


def adjudicate_batch(records: tuple[TechnicalRecord, ...]) -> tuple[AdjudicationDecision, ...]:
    """批量裁决：多条记录同时存在时，逐条独立裁决，不共享状态、不互相影响。"""
    return tuple(adjudicate(record) for record in records)


def rerun_if_required(
    decision: AdjudicationDecision,
    original: assignment.Assignment,
    *,
    plan: assignment.SeedPlan,
    consumed: tuple[int, ...] = (),
) -> assignment.Assignment | None:
    """按裁决结果决定是否补跑；只有 ``rerun_required`` 的裁决才消耗备用池。

    补跑动作本身（新 seed、新 id、保留原记录引用）复用
    ``assignment.rerun_assignment``——本函数只是把"是否该补跑"这个裁决结论接到
    "怎么补跑"这个既有实现上，不重复消耗备用池的顺序逻辑。
    """
    if decision.reason not in _RERUN_TRIGGERS:
        if decision.rerun_required:
            raise AdjudicationError(
                f"reason={decision.reason!r} 不在允许补跑的原因闭集 {_RERUN_TRIGGERS} 中"
            )
        return None
    return assignment.rerun_assignment(original, plan=plan, consumed=consumed)


def sample_flow_summary(decisions: tuple[AdjudicationDecision, ...]) -> dict[str, object]:
    """样本流图：included/excluded 计数与每条排除原因的分布，供交付包引用。"""
    included = [d for d in decisions if d.status is AdjudicationStatus.INCLUDED]
    excluded = [d for d in decisions if d.status is AdjudicationStatus.EXCLUDED]
    by_reason: dict[str, int] = {}
    for d in excluded:
        key = d.reason.value if d.reason else "UNKNOWN"
        by_reason[key] = by_reason.get(key, 0) + 1
    return {
        "total": len(decisions),
        "included": len(included),
        "excluded": len(excluded),
        "excluded_by_reason": by_reason,
        "reruns_required": sum(1 for d in decisions if d.rerun_required),
    }
