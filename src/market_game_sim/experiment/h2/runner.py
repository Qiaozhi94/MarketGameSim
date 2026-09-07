"""T907：双臂生成、窗口调度匹配与 pair validator（FR-301/FR-302 / TR-301 / AC-304）。

一个 AI 配对 block = 同一个 seed 上跑两条冻结策略。它们共享账户、初始资金、信息集、
动作空间与**窗口调度**，唯一预定差异是决策策略本身。

窗口调度为什么单列：如果参照策略按内核默认的观察间隔决策、而所有者按 8 秒窗口决策，
"决策机会一致"就只是纸面声明——两边的行动次数根本不同。这里把窗口合同写进配置
（``observe_interval_ns`` = 窗口逻辑长度）并纳入 pair 比较字段，让它成为可断言的事实。

运行参数取自 v0.1.5 的冻结 plan：H2 复用同一市场配置，只换决策策略，这样两个版本的
结果才在同一模型族里可比。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.experiment.config import ExperimentConfig
from market_game_sim.experiment.h2 import protocol
from market_game_sim.experiment.runner import RunResult, run_one
from market_game_sim.ledger.account import initial_margin_bp_for_tier
from market_game_sim.rng.distributions import discrete_choice, uniform_range

ROOT = Path(__file__).resolve().parents[4]
PLAN_PATH = ROOT / "docs" / "experiments" / "0.1.5-factorial-plan.json"

#: 策略 arm 名 -> v0.1.5 冻结的 goal model id。
ARM_TO_POLICY: dict[str, str] = {
    "linear": "risk_budget_linear_v1",
    "threshold": "risk_budget_threshold_v1",
}

#: 强平连锁只在高杠杆 + 高维持保证金的制度格发生（H2-cascade-calibration）。
#: 正式场景分布必须包含它，否则该结果家族没有数据。
CASCADE_CELL_MAINT_BP = 1200
HIGH_LEVERAGE_WEIGHTS_BP: dict[int, int] = {10: 3334, 20: 3333, 50: 3333}


class PairError(RuntimeError):
    """配对 block 违反了比较矩阵合同。"""


def _run_parameters() -> dict[str, Any]:
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))["run_parameters"]


def owner_window_contract() -> dict[str, Any]:
    """窗口合同取自冻结协议；实际读取逻辑由 protocol.frozen_window_contract() 唯一拥有，
    ``session.py`` 消费同一份输出。这里保留这层薄封装只是维持既有公开名字不动。"""
    return protocol.frozen_window_contract()


#: 模块级常量形式的窗口合同，供断言与配置构造共用。
OWNER_WINDOW_CONTRACT: dict[str, Any] = owner_window_contract()


@dataclass(frozen=True, slots=True)
class PolicyRun:
    """一条策略运行及其比较矩阵字段。"""

    arm: str
    policy_id: str
    seed: int
    window_schedule: dict[str, Any]
    accounts: tuple[str, ...]
    initial_price_ticks: int
    information_set: str
    action_space: tuple[str, ...]
    result: RunResult

    def matrix_fields(self) -> dict[str, Any]:
        """比较矩阵中标为"相同"的字段。"""
        return {
            "accounts": self.accounts,
            "initial_price_ticks": self.initial_price_ticks,
            "information_set": self.information_set,
            "action_space": self.action_space,
            "window_schedule": tuple(sorted(self.window_schedule.items(), key=str)),
        }


@dataclass(frozen=True, slots=True)
class PairedBlock:
    seed: int
    runs: tuple[PolicyRun, ...]


@dataclass(frozen=True, slots=True)
class PairReport:
    identical_fields: frozenset[str]
    disclosed_differences: dict[str, tuple[Any, ...]]


def build_config(seed: int, arm: str) -> ExperimentConfig:
    """构造一条策略运行的配置。

    ``observe_interval_ns`` 直接取窗口合同的逻辑长度——这就是"两条参照跑同一窗口
    调度器"在配置层的落点，而不是靠文档约定。
    """
    if arm not in ARM_TO_POLICY:
        raise PairError(f"未知 arm {arm!r}，合法值为 {sorted(ARM_TO_POLICY)}")
    rp = _run_parameters()
    window_ns = int(OWNER_WINDOW_CONTRACT["logical_ns_per_window"])
    tier, _ = discrete_choice(
        HIGH_LEVERAGE_WEIGHTS_BP, seed, "belief-0", "bench_leverage_tier", 0, 0
    )
    appetite, _ = uniform_range(
        Decimal(500), Decimal(20_000), seed, "belief-0", "risk_appetite", 0, 0
    )
    belief = AgentSpec(
        agent_id="belief-0",
        role="belief_trader",
        observe_interval_ns=window_ns,
        latency_ns=rp["belief_latency_ns"],
        leverage_tier=tier,
        initial_bp=initial_margin_bp_for_tier(tier),
        goal_model_id=ARM_TO_POLICY[arm],
        risk_appetite_x1000=int(appetite),
        aggressiveness_bp=rp["belief_aggressiveness_bp"],
        max_order_qty=rp["belief_max_order_qty"],
        ewma_half_life_trades=rp["belief_ewma_half_life_trades"],
    )
    maker = AgentSpec(
        agent_id="mm-0",
        role="inventory_market_maker",
        observe_interval_ns=rp["market_maker_observe_interval_ns"],
        latency_ns=rp["market_maker_latency_ns"],
        is_market_maker=True,
        leverage_tier=rp["market_maker_leverage_tier"],
        initial_bp=rp["market_maker_initial_bp"],
        half_spread_ticks=rp["market_maker_half_spread_ticks"],
        quote_size=rp["market_maker_quote_size"],
        max_inventory=rp["market_maker_max_inventory"],
        inventory_skew_k_bp=rp["market_maker_inventory_skew_k_bp"],
    )
    return ExperimentConfig(
        seed=seed,
        initial_price_ticks=rp["initial_price_ticks"],
        max_transactions=rp["max_transactions"],
        maint_bp=CASCADE_CELL_MAINT_BP,
        agent_specs=[maker, belief],
    )


def _policy_run(seed: int, arm: str) -> PolicyRun:
    config = build_config(seed, arm)
    result = run_one(config)
    return PolicyRun(
        arm=arm,
        policy_id=ARM_TO_POLICY[arm],
        seed=seed,
        window_schedule=dict(OWNER_WINDOW_CONTRACT),
        accounts=tuple(sorted(spec.agent_id for spec in config.agent_specs)),
        initial_price_ticks=int(config.initial_price_ticks),
        information_set="public_book_and_own_account",
        action_space=("submit_order", "cancel_order", "no_action"),
        result=result,
    )


def run_ai_block(seed: int) -> PairedBlock:
    """跑一个配对 block：同 seed 上的两条冻结策略。"""
    return PairedBlock(seed=seed, runs=tuple(_policy_run(seed, arm) for arm in ARM_TO_POLICY))


def validate_pair(block: PairedBlock) -> PairReport:
    """比较矩阵校验：标为"相同"的字段逐字段一致，差异项完整披露。"""
    if len(block.runs) != 2:
        raise PairError(f"配对 block 必须恰含两条运行，实际 {len(block.runs)} 条")
    if len({run.seed for run in block.runs}) != 1:
        raise PairError("同一 block 内的运行必须共享 seed")

    first, second = block.runs
    left, right = first.matrix_fields(), second.matrix_fields()
    drifted = sorted(name for name in left if left[name] != right[name])
    if drifted:
        raise PairError(f"比较矩阵中标为相同的字段发生漂移：{drifted}")

    policies = tuple(run.policy_id for run in block.runs)
    if len(set(policies)) != 2:
        raise PairError(f"两条运行必须使用不同策略，实际 {policies}")

    return PairReport(
        identical_fields=frozenset(left),
        disclosed_differences={"policy_id": policies, "arm": tuple(r.arm for r in block.runs)},
    )


def chain_severity(run: PolicyRun) -> int:
    """强平连锁的主要严重度：单个 chain_id 下被强平的最大账户数。

    **不是** ``max(chain_depth)+1``——实测所有 chain_depth 都是 0，那个量恒为常数，
    用它会把这个家族变回零方差终点（H2-cascade-calibration）。
    """
    sizes = run.result.liquidation_metrics.chain_size_by_id
    return max(sizes.values()) if sizes else 0
