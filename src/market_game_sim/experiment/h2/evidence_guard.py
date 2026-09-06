"""T908：H2 正式证据的多重闭锁与原子拒绝（FR-303 / IR-302 / AC-303）。

单靠 ``run_mode`` 一个字段挡不住误纳——一次改名、一次复制粘贴就能让 H1 的交互数据
看起来像正式样本。所以准入要同时满足五把锁：

1. **run_mode** 属于 H2 的两个模式之一（``interactive`` 及任何未知值一律拒绝）；
2. **sample_stage** 是 ``formal``（training / preview 只能进各自的预览产物）；
3. **protocol_hash** 与当前冻结协议一致（协议漂移即拒绝）；
4. **pair 完整**（AI 轨两条策略齐备；缺一条的 block 不进主要分析）；
5. **未命中预注册排除条件**。

原子性在这里的含义是：**校验全部通过之前不产生任何输出**。``admit`` 不写盘，
``partial_writes()`` 用来断言"拒绝路径上没有留下半截产物"——这条如果只靠代码走查，
恰恰是最容易在某次重构里丢掉的。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from market_game_sim.experiment.h2 import protocol

#: H2 的两个运行模式。两者各自维护 evidence index，永不合并。
AI_TRACK = "ai-mechanism-experiment"
OWNER_TRACK = "owner-n-of-1"
RUN_MODES: tuple[str, ...] = (AI_TRACK, OWNER_TRACK)

#: 样本阶段。只有 formal 能进正式分析。
STAGES: tuple[str, ...] = ("training", "preview", "formal")
FORMAL_STAGE = "formal"


class EvidenceRejected(RuntimeError):
    """运行不满足正式证据准入条件。"""


class CrossTrackMerge(EvidenceRejected):
    """试图跨轨合并证据——两轨的样本量与不确定性永不合并。"""


@dataclass(slots=True)
class GuardLedger:
    """记录准入决定。拒绝路径不得向这里追加任何产物。"""

    admitted: list[str] = field(default_factory=list)
    partial: list[str] = field(default_factory=list)


_LEDGER = GuardLedger()


def partial_writes() -> list[str]:
    """拒绝路径上遗留的半截产物；恒应为空。"""
    return list(_LEDGER.partial)


def reset() -> None:
    """测试用：清空账本。生产路径每次运行都用新进程。"""
    _LEDGER.admitted.clear()
    _LEDGER.partial.clear()


def admit(
    *,
    run_mode: str,
    stage: str,
    protocol_hash: str | None = None,
    pair_complete: bool = True,
    excluded_reason: str | None = None,
) -> bool:
    """五把锁全过才准入。任一不满足即抛异常，且不产生任何输出。"""
    if run_mode not in RUN_MODES:
        raise EvidenceRejected(f"run_mode {run_mode!r} 不在 H2 的 {RUN_MODES}")
    if stage not in STAGES:
        raise EvidenceRejected(f"未知 sample_stage {stage!r}")
    if stage != FORMAL_STAGE:
        raise EvidenceRejected(f"{stage!r} 阶段的运行不得进入正式证据")

    frozen = protocol.freeze(protocol.draft_from_contract())
    if protocol_hash is not None and not protocol.accepts_assignment(
        frozen, issued_under=protocol_hash
    ):
        raise EvidenceRejected("协议哈希漂移，assignment 不属于当前冻结协议")

    if not pair_complete:
        raise EvidenceRejected("pair 不完整，缺失成员的 block 不进入主要分析")
    if excluded_reason is not None:
        raise EvidenceRejected(f"命中预注册排除条件：{excluded_reason}")

    _LEDGER.admitted.append(f"{run_mode}:{stage}")
    return True


def merge(run_modes: list[str]) -> None:
    """跨轨合并禁令。同轨聚合是正常操作，混轨一律拒绝。"""
    distinct = {mode for mode in run_modes}
    unknown = sorted(distinct - set(RUN_MODES))
    if unknown:
        raise EvidenceRejected(f"未知 run_mode：{unknown}")
    if len(distinct) > 1:
        raise CrossTrackMerge(
            f"禁止跨轨合并样本量或不确定性：{sorted(distinct)}；"
            "研究声明只由 AI 轨承担，所有者轨是描述性的"
        )
