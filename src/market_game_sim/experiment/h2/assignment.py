"""T906：预签发 assignment、场景顺序与有序备用 seed 池（FR-301 / NFR-303 / AC-304）。

三条约束决定了这个模块的形状：

* **结果盲**：assignment 在采样前一次性签发，签发过程不读取任何运行结果字段
  （spec §5 不变量）。这里的函数只接受冻结协议和一个审计种子，拿不到结果。
* **备用池有序**：技术补跑只能按冻结顺序消耗下一个备用 seed，不能挑。允许挑就等于
  允许"这个 seed 结果不好，换一个"。
* **seed 段独占**：H2 用 50000 段，与 v0.1.5 的 40000 段和更早的 30000 段不重叠——
  同一个 seed 在两套证据里出现会让"这条结果属于哪次实验"变得需要人去回忆。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from market_game_sim.experiment.h2 import protocol
from market_game_sim.rng.distributions import discrete_choice

#: H2 独占的 seed 段起点。40000 段属于 v0.1.5，30000 段属于更早的运行。
H2_FIRST_SEED = 50_000

#: 备用 seed 占计划量的百分比（向上取整），用于技术故障整局补跑。
RESERVE_PERCENT = 10


class AssignmentError(RuntimeError):
    """assignment 合同被违反。"""


class ReservePoolExhausted(AssignmentError):
    """备用 seed 已用尽；继续补跑会破坏冻结的样本量。"""


@dataclass(frozen=True, slots=True)
class SeedPlan:
    """冻结的 seed 计划。``planned`` 与 ``reserve`` 都是有序且互不重叠的。"""

    planned: tuple[int, ...]
    reserve: tuple[int, ...]

    def validate(self) -> None:
        if not self.planned:
            raise AssignmentError("planned seed 不能为空")
        if set(self.planned) & set(self.reserve):
            raise AssignmentError("planned 与 reserve seed 不得重叠")
        pool = self.planned + self.reserve
        if len(set(pool)) != len(pool):
            raise AssignmentError("seed 池内不得有重复")


@dataclass(frozen=True, slots=True)
class Assignment:
    """一个 AI 配对 block 的预签发记录。"""

    assignment_id: str
    seed: int
    order_index: int
    arms: tuple[str, ...]
    protocol_hash: str
    superseded_by: str | None = None


def build_seed_plan(frozen: protocol.FrozenProtocol) -> SeedPlan:
    """按冻结协议的 block 数派生 seed 计划。"""
    blocks = int(frozen.minimum_blocks)
    # 整数向上取整，避免 int(168 * 0.10) 先截断成 16 的浮点陷阱。
    reserve_count = (blocks * RESERVE_PERCENT + 99) // 100
    planned = tuple(range(H2_FIRST_SEED, H2_FIRST_SEED + blocks))
    reserve = tuple(range(H2_FIRST_SEED + blocks, H2_FIRST_SEED + blocks + reserve_count))
    plan = SeedPlan(planned=planned, reserve=reserve)
    plan.validate()
    return plan


def _uniform_weights_bp(count: int) -> dict[int, int]:
    """均匀万分率权重；余数并入第一项，与 v0.1.5 的 tier 抽样口径一致。"""
    share = 10_000 // count
    weights = {index: share for index in range(count)}
    weights[0] += 10_000 - share * count
    return weights


def scenario_order(frozen: protocol.FrozenProtocol, *, audit_seed: int) -> tuple[int, ...]:
    """所有者正式场景的执行顺序。

    用仓库既有的语义键 PRNG 做无放回抽样，``audit_seed`` 随协议一并冻结，因此顺序
    可复现、可审计，而不是运行时随手 shuffle 出来的。
    """
    count = int(frozen.payload["tracks"]["owner_n_of_1"]["formal_paired_blocks"])
    remaining = list(range(count))
    order: list[int] = []
    draw = 0
    while remaining:
        picked, draw = discrete_choice(
            _uniform_weights_bp(len(remaining)), audit_seed, "owner-order", "scenario", 0, draw
        )
        order.append(remaining.pop(picked))
    return tuple(order)


def issue(frozen: protocol.FrozenProtocol, *, audit_seed: int = 0) -> tuple[Assignment, ...]:
    """一次性预签发全部 AI 轨 assignment（结果盲）。"""
    plan = build_seed_plan(frozen)
    arms = tuple(arm for arm in frozen.payload["control_arms"] if arm != "owner")
    del audit_seed  # AI 轨每个 seed 都跑全部 arm，顺序无需随机化
    return tuple(
        Assignment(
            assignment_id=f"h2-ai-{seed}",
            seed=seed,
            order_index=index,
            arms=arms,
            protocol_hash=frozen.protocol_hash,
        )
        for index, seed in enumerate(plan.planned)
    )


def next_reserve_seed(plan: SeedPlan, *, consumed: tuple[int, ...] = ()) -> int:
    """按冻结顺序取下一个未使用的备用 seed；不允许挑选。"""
    for seed in plan.reserve:
        if seed not in consumed:
            return seed
    raise ReservePoolExhausted(f"备用 seed 已全部消耗（{len(plan.reserve)} 个），不得继续补跑")


def rerun_assignment(
    original: Assignment,
    *,
    plan: SeedPlan,
    consumed: tuple[int, ...] = (),
) -> Assignment:
    """技术中止后的整局补跑：新 seed、新 id，并保留对原记录的引用。"""
    seed = next_reserve_seed(plan, consumed=consumed)
    return Assignment(
        assignment_id=f"h2-ai-{seed}",
        seed=seed,
        order_index=original.order_index,
        arms=original.arms,
        protocol_hash=original.protocol_hash,
        superseded_by=original.assignment_id,
    )


def sample_flow(
    assignments: tuple[Assignment, ...],
    *,
    aborted: tuple[str, ...] = (),
) -> dict[str, Any]:
    """样本流图：中止与补跑都留痕，不允许静默替换。"""
    reruns = [a for a in assignments if a.superseded_by is not None]
    return {
        "issued": len(assignments),
        "aborted": list(aborted),
        "reruns": [
            {"assignment_id": a.assignment_id, "supersedes": a.superseded_by} for a in reruns
        ],
        "included_candidates": len(assignments) - len(aborted),
    }
