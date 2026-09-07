"""T912：三个结果家族的配对估计、不确定性、多重性与缺失处理（FR-304 / AC-305）。

主要 estimand 是三个家族各自的**严重程度**配对差（threshold - linear），Holm 校正
只作用于这三个检验（DQ-304）；发生指标降为描述性——其配对差在 v0.1.5 128 个已测量
block 上实测恒为零方差（`H2-endpoint-calibration` / `H2-cascade-calibration`），沿用
这个结论，本模块不把发生率纳入任何主要检验。

``price_crash`` / ``liquidity_dry_up`` 复用 v0.1.5 冻结的
``factorial.endpoint_observations()``——"沿用 v0.1 定义"是 Q-307 的裁决，不是本模块
另起一套算法。``liquidation_cascade`` 用 ``runner.chain_severity()``（单个 chain_id
下的账户数，不是 ``chain_depth``——理由见该函数文档）。

统计核心 ``analyse_families()`` 是纯函数，不做任何 I/O 或真实市场运行，可以用合成
观察值测试正反两面（缺失处理、退化输入等）。``analyse_ai_track()`` 是便捷入口，跑一批
真实配对 block；在 T916-T918 冻结正式 168-block evidence index 之前，没有"正式样本"
可读，这里的默认 seed 集合只是给统计机器一批可复现的真实数据做验证，不是正式证据。
"""

from __future__ import annotations

import random
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from market_game_sim.experiment.factorial import endpoint_observations
from market_game_sim.experiment.h2 import assignment, runner
from market_game_sim.experiment.stats import bootstrap_proportion_diff, holm_bonferroni

#: 三个结果家族，顺序固定（报告与 Holm 校正范围声明都按此顺序枚举）。
FAMILIES: tuple[str, ...] = ("price_crash", "liquidity_dry_up", "liquidation_cascade")

#: H2 家族名 -> v0.1.5 ``endpoint_observations()`` 对应键；``liquidation_cascade`` 在
#: v0.1.5 没有对应项，单独用 ``runner.chain_severity()`` 计算。
_V015_ENDPOINT_KEY: dict[str, str] = {
    "price_crash": "crash",
    "liquidity_dry_up": "liquidity_drought",
}

CONTROL_POLICY = "risk_budget_linear_v1"
TREATMENT_POLICY = "risk_budget_threshold_v1"

DEFAULT_BOOTSTRAP_RESAMPLES = 10_000
DEFAULT_BOOTSTRAP_SEED = 0
DEFAULT_CI_LEVEL = 0.95
DEFAULT_ALPHA = 0.05

#: 预览用途的默认 seed 数量。
DEFAULT_PREVIEW_SEED_COUNT = 24


class OutcomesError(RuntimeError):
    """结果分析合同被违反。"""


@dataclass(frozen=True, slots=True)
class BlockObservation:
    """一个配对 block 在某个家族上的观察。

    任一侧严重度缺失则整对在该家族缺失——按冻结规则处理，不推断、不手工补值
    （FR-305 的缺失原则同样适用于结果家族）。
    """

    seed: int
    control_severity: float | None
    treatment_severity: float | None
    control_occurrence: float | None = None
    treatment_occurrence: float | None = None

    @property
    def is_missing(self) -> bool:
        return self.control_severity is None or self.treatment_severity is None

    @property
    def paired_severity_diff(self) -> float | None:
        if self.is_missing:
            return None
        return self.treatment_severity - self.control_severity  # type: ignore[operator]


def _bootstrap_paired_mean(
    diffs: Sequence[float],
    *,
    n_resamples: int,
    ci_level: float,
    seed: int,
) -> tuple[float, float, float, float]:
    """block 级重抽样：返回 ``(effect, ci_low, ci_high, two_sided_p_value)``。

    p 值用标准的 bootstrap 双侧估计——重抽样均值落在 0 的哪一侧的比例乘 2、夹到
    ``[0, 1]``；不用渐近正态近似，因为严重程度分布可能有大量结构性零值（例如
    ``liquidation_cascade`` 在多数 block 上是 0-0 配对），正态近似在这种分布上不可靠。
    """
    n = len(diffs)
    if n == 0:
        raise OutcomesError("至少需要一个非缺失的配对 block 才能估计")
    observed_mean = sum(diffs) / n
    rng = random.Random(seed)
    resample_means: list[float] = []
    for _ in range(n_resamples):
        resample = [diffs[rng.randrange(n)] for _ in range(n)]
        resample_means.append(sum(resample) / n)
    resample_means.sort()

    alpha = 1 - ci_level
    lo_idx = max(int((alpha / 2) * n_resamples), 0)
    hi_idx = min(int((1 - alpha / 2) * n_resamples), n_resamples - 1)
    ci_low, ci_high = resample_means[lo_idx], resample_means[hi_idx]

    at_or_below_zero = sum(1 for m in resample_means if m <= 0) / n_resamples
    at_or_above_zero = sum(1 for m in resample_means if m >= 0) / n_resamples
    p_value = min(1.0, 2 * min(at_or_below_zero, at_or_above_zero))

    return observed_mean, ci_low, ci_high, p_value


@dataclass(frozen=True, slots=True)
class FamilyResult:
    """一个家族的完整估计结果。"""

    family: str
    primary_metric: str
    occurrence_role: str
    n_blocks: int
    n_missing: int
    effect: float
    ci_low: float
    ci_high: float
    p_value: float
    holm_significant: bool
    occurrence_rate_diff: float | None
    occurrence_ci_low: float | None
    occurrence_ci_high: float | None


class OutcomeReport(Mapping[str, FamilyResult]):
    """按家族名索引的结果，附带 Holm 校正范围声明（AC-305）。

    实现 ``Mapping`` 而不是普通 ``dict`` 子类：外部只应该读取家族结果，不应该往报告里
    插入第三方 key（比如一个"综合分数"）——``Mapping`` 没有 ``__setitem__``，这类误用
    在类型检查阶段就会被挡住，而不必依赖测试事后发现。
    """

    def __init__(
        self,
        families: dict[str, FamilyResult],
        *,
        holm_corrected_tests: Sequence[str],
    ) -> None:
        self._families = dict(families)
        self._holm_corrected_tests = tuple(holm_corrected_tests)

    def __getitem__(self, key: str) -> FamilyResult:
        return self._families[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._families)

    def __len__(self) -> int:
        return len(self._families)

    @property
    def holm_corrected_tests(self) -> list[str]:
        return list(self._holm_corrected_tests)


def analyse_families(
    observations: Mapping[str, Sequence[BlockObservation]],
    *,
    n_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    ci_level: float = DEFAULT_CI_LEVEL,
    bootstrap_seed: int = DEFAULT_BOOTSTRAP_SEED,
    alpha: float = DEFAULT_ALPHA,
) -> OutcomeReport:
    """核心统计函数：对已给定的观察值做估计，不做任何 I/O 或真实市场运行。

    Holm 校正只跨三个家族的**严重程度**检验计算一次（DQ-304）；发生率的配对风险差
    单独算出来标为描述性，不进入这次校正，也不参与 significant 判定。
    """
    missing_families = sorted(set(FAMILIES) - set(observations))
    if missing_families:
        raise OutcomesError(f"缺少家族的观察值：{missing_families}")

    severity_p_values: dict[str, float] = {}
    partial: dict[str, dict[str, Any]] = {}

    for family in FAMILIES:
        blocks = list(observations[family])
        if not blocks:
            raise OutcomesError(f"{family} 没有任何观察 block")
        complete = [b for b in blocks if not b.is_missing]
        n_missing = len(blocks) - len(complete)
        if not complete:
            raise OutcomesError(f"{family} 的全部 block 都缺失，无法估计")

        diffs = [b.paired_severity_diff for b in complete if b.paired_severity_diff is not None]
        effect, ci_low, ci_high, p_value = _bootstrap_paired_mean(
            diffs, n_resamples=n_resamples, ci_level=ci_level, seed=bootstrap_seed
        )
        severity_p_values[family] = p_value

        occurrence_complete = [
            b
            for b in blocks
            if b.control_occurrence is not None and b.treatment_occurrence is not None
        ]
        occurrence_rate_diff = occurrence_ci_low = occurrence_ci_high = None
        if occurrence_complete:
            proportion = bootstrap_proportion_diff(
                [bool(b.control_occurrence) for b in occurrence_complete],
                [bool(b.treatment_occurrence) for b in occurrence_complete],
                n_resamples=n_resamples,
                ci_level=ci_level,
                seed=bootstrap_seed,
            )
            occurrence_rate_diff = proportion.diff
            occurrence_ci_low = proportion.ci_low
            occurrence_ci_high = proportion.ci_high

        partial[family] = {
            "n_blocks": len(complete),
            "n_missing": n_missing,
            "effect": effect,
            "ci_low": ci_low,
            "ci_high": ci_high,
            "p_value": p_value,
            "occurrence_rate_diff": occurrence_rate_diff,
            "occurrence_ci_low": occurrence_ci_low,
            "occurrence_ci_high": occurrence_ci_high,
        }

    holm_decisions = holm_bonferroni(severity_p_values, alpha=alpha)

    results: dict[str, FamilyResult] = {}
    for family in FAMILIES:
        data = partial[family]
        results[family] = FamilyResult(
            family=family,
            primary_metric="severity",
            occurrence_role="descriptive",
            n_blocks=data["n_blocks"],
            n_missing=data["n_missing"],
            effect=data["effect"],
            ci_low=data["ci_low"],
            ci_high=data["ci_high"],
            p_value=data["p_value"],
            holm_significant=holm_decisions[family],
            occurrence_rate_diff=data["occurrence_rate_diff"],
            occurrence_ci_low=data["occurrence_ci_low"],
            occurrence_ci_high=data["occurrence_ci_high"],
        )

    return OutcomeReport(
        results,
        holm_corrected_tests=[f"{family}.severity" for family in FAMILIES],
    )


def observe_ai_block(seed: int) -> dict[str, BlockObservation]:
    """跑一个真实配对 block，把它投影到三个家族各自的观察值。"""
    block = runner.run_ai_block(seed)
    control = next(r for r in block.runs if r.policy_id == CONTROL_POLICY)
    treatment = next(r for r in block.runs if r.policy_id == TREATMENT_POLICY)

    control_endpoints = endpoint_observations(
        control.result, initial_price_ticks=control.initial_price_ticks
    )
    treatment_endpoints = endpoint_observations(
        treatment.result, initial_price_ticks=treatment.initial_price_ticks
    )

    observations: dict[str, BlockObservation] = {}
    for family, v015_key in _V015_ENDPOINT_KEY.items():
        c, t = control_endpoints[v015_key], treatment_endpoints[v015_key]
        observations[family] = BlockObservation(
            seed=seed,
            control_severity=c.severity,
            treatment_severity=t.severity,
            control_occurrence=c.occurrence,
            treatment_occurrence=t.occurrence,
        )

    control_cascade = runner.chain_severity(control)
    treatment_cascade = runner.chain_severity(treatment)
    observations["liquidation_cascade"] = BlockObservation(
        seed=seed,
        control_severity=float(control_cascade),
        treatment_severity=float(treatment_cascade),
        # 发生判据是"同一 chain_id 出现两个及以上不同账户"（design.md §9 Q-307），不是
        # "发生过任意一次强平"——单账户被强平不构成连锁。max(chain_depth)>=1 已被冻结
        # 决定明确排除出发生判据（本模型族恒为假），这里不得再用它。
        control_occurrence=float(control_cascade >= 2),
        treatment_occurrence=float(treatment_cascade >= 2),
    )
    return observations


def collect_ai_block_observations(seeds: Sequence[int]) -> dict[str, list[BlockObservation]]:
    """跑一批真实配对 block，按家族组织成观察值列表。"""
    if not seeds:
        raise OutcomesError("seeds 不能为空")
    by_family: dict[str, list[BlockObservation]] = {family: [] for family in FAMILIES}
    for seed in seeds:
        for family, observation in observe_ai_block(seed).items():
            by_family[family].append(observation)
    return by_family


def preview_seeds(count: int = DEFAULT_PREVIEW_SEED_COUNT) -> tuple[int, ...]:
    """默认预览 seed 集合，取自 H2 seed 段起点。

    这不是冻结的正式 168-block 样本——T916-T918 冻结正式 evidence index 之前没有
    "正式样本"可读；这里给统计机器一批可复现的真实数据做验证，不是正式证据。
    """
    return tuple(range(assignment.H2_FIRST_SEED, assignment.H2_FIRST_SEED + count))


def analyse_ai_track(seeds: Sequence[int] | None = None, **analysis_kwargs: Any) -> OutcomeReport:
    """便捷入口：跑一批真实配对 block 并分析。"""
    observations = collect_ai_block_observations(seeds if seeds is not None else preview_seeds())
    return analyse_families(observations, **analysis_kwargs)


# --------------------------------------------------------------------------- #
# OWNER_N_OF_1 轨：描述性对比（design.md §7："该所有者相对两条参照策略发生了什么"）
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class OwnerComparison:
    """所有者单个正式场景相对两条参照策略的描述性差异。

    刻意不产生 CI、p 值或 Holm 校正——n=1 自我实验不做显著性检验（SOP 原则 3），这里
    只呈现"发生了什么"。这个类型也**不**是 ``OutcomeReport`` 的一部分、不出现在
    ``holm_corrected_tests`` 里，结构上不存在"所有者对比替代主要结论"这条路径，
    不必依赖调用方自觉遵守。
    """

    family: str
    owner_severity: float
    linear_severity: float
    threshold_severity: float

    @property
    def owner_minus_linear(self) -> float:
        return self.owner_severity - self.linear_severity

    @property
    def owner_minus_threshold(self) -> float:
        return self.owner_severity - self.threshold_severity


def describe_owner_scenario(
    owner_severities: Mapping[str, float],
    reference: Mapping[str, BlockObservation],
) -> dict[str, OwnerComparison]:
    """按家族生成所有者相对两条参照策略的描述性对比。

    ``reference`` 复用 ``BlockObservation`` 的 control/treatment 字段承载两条参照
    策略各自的严重度——它们就是这次场景绑定的同 seed ``WINDOW_MATCHED_POLICY_CONTROL``
    运行（T917 用真实所有者输入产出 ``owner_severities``，参照侧复用 ``observe_ai_block``
    同款投影逻辑，本函数不关心这些数字是怎么算出来的）。
    """
    missing = sorted(set(FAMILIES) - set(owner_severities))
    if missing:
        raise OutcomesError(f"所有者场景缺少家族的严重度：{missing}")
    result: dict[str, OwnerComparison] = {}
    for family in FAMILIES:
        ref = reference[family]
        if ref.is_missing:
            raise OutcomesError(f"{family} 的参照策略观察不完整，无法生成对比")
        result[family] = OwnerComparison(
            family=family,
            owner_severity=owner_severities[family],
            linear_severity=ref.control_severity,  # type: ignore[arg-type]
            threshold_severity=ref.treatment_severity,  # type: ignore[arg-type]
        )
    return result
