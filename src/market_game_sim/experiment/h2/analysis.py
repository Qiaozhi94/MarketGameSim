"""T919：预注册主要、机制与敏感性分析及结论边界检查（FR-304 / FR-305 / SC-303 / AC-305 / AC-306）。

三条纪律直接来自冻结对象，本模块不持有任何研究参数：

* **样本集合只来自冻结 evidence index**（design §2）：逐 pair 重放冻结 seed，
  每臂事件流 SHA-256 必须与 index 记录一致，不一致即 fail-closed——分析的是
  "采样时锁定的状态"，不是当前代码碰巧能跑出来的任何东西。
* **分析参数取自冻结协议** ``analysis_plan``：bootstrap 次数/种子、CI 水平、
  Holm α 一律不取模块默认值。Holm 只作用于三个主要严重程度终点
  （``outcomes.analyse_families`` 的既有合同）。
* **敏感性与机制只作边界证据**（预注册 §8）：sign-flip 与分层结果不得替代
  主要 bootstrap 结论或扩大研究声明；发生指标与所有者轨保持描述性；不生成
  任何综合分数（AC-305）。结论文本过不了 ``check_conclusion_text`` 的冻结
  语法就不允许落盘。
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any

from market_game_sim.experiment.factorial import endpoint_observations
from market_game_sim.experiment.h2 import (
    evidence_index,
    mechanisms,
    outcomes,
    runner,
)
from market_game_sim.experiment.h2.artifacts import canonical_digest, write_json_atomic
from market_game_sim.rng.distributions import discrete_choice

ANALYSIS_SCHEMA_VERSION = 1

#: 机器分析结果的落盘位置（docs/experiments/ 顶层，与冻结 index 并列；
#: 不进 H2-formal-freeze/——那是 T916 的冻结归档，只存归档自己的文件）。
DEFAULT_ANALYSIS_PATH = evidence_index.ARCHIVE_PROTOCOL_PATH.parent.parent / "H2-ai-analysis.json"

MECHANISM_AGENT_ID = "belief-0"


class AnalysisError(RuntimeError):
    """重放不一致、index 缺陷或结论边界被违反。"""


def _archive_payload() -> dict[str, Any]:
    return json.loads(evidence_index.ARCHIVE_PROTOCOL_PATH.read_text(encoding="utf-8"))["payload"]


def frozen_analysis_plan() -> dict[str, Any]:
    """冻结协议的 analysis_plan——分析的唯一下量依据。"""
    return _archive_payload()["analysis_plan"]


def leverage_tier(seed: int) -> int:
    """重放 block 的 belief 杠杆层级（与 ``runner.build_config`` 同一 RNG 合同键）。

    这是 AI 轨里唯一的逐 seed 制度分层维度：所有 block 都在
    ``CASCADE_CELL_MAINT_BP`` 强平格内，层级由 seed 确定性抽取。
    """
    tier, _ = discrete_choice(
        runner.HIGH_LEVERAGE_WEIGHTS_BP, seed, MECHANISM_AGENT_ID, "bench_leverage_tier", 0, 0
    )
    return int(tier)


def check_conclusion_text(text: str, *, syntax: dict[str, Any] | None = None) -> None:
    """冻结结论语法门：禁用简写一个不能出现，必备限定词一个不能缺席。"""
    rules = syntax or _archive_payload()["conclusion_syntax"]
    hits = [bad for bad in rules["forbidden_shorthands"] if bad in text]
    if hits:
        raise AnalysisError(f"结论文本命中禁用简写 {hits}——不得写成人类效应")
    missing = [q for q in rules["required_qualifiers"] if q not in text]
    if missing:
        raise AnalysisError(f"结论文本缺少必备限定词 {missing}（模型族/参数范围/seed 分布）")


def _sign_flip_p(diffs: list[float], *, draws: int, seed: int) -> float:
    """交换性假设下的 MC sign-flip 检验（预注册 §8 的敏感性，非主要推断）。"""
    if not diffs:
        raise AnalysisError("sign-flip 需要非空配对差")
    observed = abs(sum(diffs) / len(diffs))
    rng = random.Random(seed)
    extreme = 0
    for _ in range(draws):
        flipped = [d if rng.random() < 0.5 else -d for d in diffs]
        if abs(sum(flipped) / len(flipped)) >= observed:
            extreme += 1
    return (extreme + 1) / (draws + 1)


def _mechanism_summary(block_mechanisms: list[dict[str, Any]]) -> dict[str, Any]:
    """按臂聚合三个机制指标——机制边界证据，不进主要多重性集合。"""
    summary: dict[str, dict[str, dict[str, float]]] = {}
    for entry in block_mechanisms:
        for arm, by_metric in entry["arms"].items():
            for metric, value in by_metric.items():
                bucket = summary.setdefault(
                    metric, {a: {"total": 0.0, "n": 0} for a in ("linear", "threshold")}
                )[arm]
                if value is not None:
                    bucket["total"] += value
                    bucket["n"] += 1
    return {
        metric: {
            arm: {
                "total": bucket["total"],
                "n": bucket["n"],
                "mean": bucket["total"] / bucket["n"] if bucket["n"] else None,
            }
            for arm, bucket in arms.items()
        }
        for metric, arms in summary.items()
    }


def _observe_block(seed: int, block: runner.PairedBlock) -> dict[str, outcomes.BlockObservation]:
    """把已重放的配对 block 投影成三家族观察值。

    与 ``outcomes.observe_ai_block`` 同一套投影合同（endpoint 键、级联发生判据
    ``>=2`` 账户），区别只在消费已重放的 block——分析的一次重放既当完整性证据
    又当数据。``test_projection_matches_observe_ai_block`` 锁住两者等价。
    """
    control = next(r for r in block.runs if r.policy_id == outcomes.CONTROL_POLICY)
    treatment = next(r for r in block.runs if r.policy_id == outcomes.TREATMENT_POLICY)

    control_endpoints = endpoint_observations(
        control.result, initial_price_ticks=control.initial_price_ticks
    )
    treatment_endpoints = endpoint_observations(
        treatment.result, initial_price_ticks=treatment.initial_price_ticks
    )

    observations: dict[str, outcomes.BlockObservation] = {}
    for family, v015_key in outcomes._V015_ENDPOINT_KEY.items():
        c, t = control_endpoints[v015_key], treatment_endpoints[v015_key]
        observations[family] = outcomes.BlockObservation(
            seed=seed,
            control_severity=c.severity,
            treatment_severity=t.severity,
            control_occurrence=c.occurrence,
            treatment_occurrence=t.occurrence,
        )

    control_cascade = runner.chain_severity(control)
    treatment_cascade = runner.chain_severity(treatment)
    observations["liquidation_cascade"] = outcomes.BlockObservation(
        seed=seed,
        control_severity=float(control_cascade),
        treatment_severity=float(treatment_cascade),
        control_occurrence=float(control_cascade >= 2),
        treatment_occurrence=float(treatment_cascade >= 2),
    )
    return observations


def run_formal_analysis(
    *,
    index_path: Path | None = None,
    out_path: Path | None = None,
) -> dict[str, Any]:
    """从冻结 evidence index 执行预注册分析并返回机器结果 payload（不落盘）。"""
    resolved_index = index_path or evidence_index.DEFAULT_INDEX_PATH
    index = evidence_index.load_frozen_index(resolved_index)
    plan = frozen_analysis_plan()

    observations: dict[str, list[outcomes.BlockObservation]] = {
        family: [] for family in outcomes.FAMILIES
    }
    block_mechanisms: list[dict[str, Any]] = []
    tiers: dict[int, int] = {}
    for entry in index["included"]:
        seed = int(entry["seed"])
        block = runner.run_ai_block(seed)
        for run in block.runs:
            expected = entry["arms"].get(run.arm, {}).get("events_sha256")
            if canonical_digest(run.result.events) != expected:
                raise AnalysisError(
                    f"重放事件哈希与冻结 index 不一致（block {entry['order_index']}，"
                    f"arm {run.arm}）——冻结状态被破坏，禁止分析"
                )
        for family, observation in _observe_block(seed, block).items():
            observations[family].append(observation)
        block_mechanisms.append(
            {
                "order_index": entry["order_index"],
                "seed": seed,
                "arms": {run.arm: _mechanism_row_values(run.result) for run in block.runs},
            }
        )
        tiers[seed] = leverage_tier(seed)

    report = outcomes.analyse_families(
        observations,
        n_resamples=int(plan["bootstrap_resamples"]),
        ci_level=float(plan["ci_level"]),
        bootstrap_seed=int(plan["bootstrap_seed"]),
        alpha=float(plan["holm_alpha"]),
    )

    primary: dict[str, Any] = {}
    sign_flip: dict[str, float] = {}
    diffs_by_family: dict[str, list[float]] = {}
    for family in outcomes.FAMILIES:
        result = report[family]
        diffs = [
            b.paired_severity_diff
            for b in observations[family]
            if not b.is_missing and b.paired_severity_diff is not None
        ]
        diffs_by_family[family] = diffs
        primary[family] = {
            "n_blocks": result.n_blocks,
            "n_missing": result.n_missing,
            "effect": result.effect,
            "ci_low": result.ci_low,
            "ci_high": result.ci_high,
            "p_value": result.p_value,
            "holm_significant": result.holm_significant,
            "occurrence_rate_diff": result.occurrence_rate_diff,
            "occurrence_role": result.occurrence_role,
        }
        sign_flip[family] = _sign_flip_p(
            diffs, draws=int(plan["bootstrap_resamples"]), seed=int(plan["bootstrap_seed"])
        )

    strata: dict[str, dict[str, Any]] = {}
    for family in outcomes.FAMILIES:
        by_tier: dict[int, list[float]] = {}
        for observation in observations[family]:
            if observation.paired_severity_diff is None or observation.is_missing:
                continue
            by_tier.setdefault(tiers[observation.seed], []).append(observation.paired_severity_diff)
        strata[family] = {
            f"tier_{tier}": {"n": len(values), "mean_diff": sum(values) / len(values)}
            for tier, values in sorted(by_tier.items())
        }

    sesoi = _archive_payload()["sesoi_by_family"]
    sesoi_verdict = {
        family: {
            "sesoi": sesoi[family],
            "effect": primary[family]["effect"],
            "effect_below_sesoi": abs(primary[family]["effect"]) < sesoi[family],
        }
        for family in outcomes.FAMILIES
    }

    conclusion = (
        "在冻结模型族与本参数范围内，threshold 相对 linear 对照的严重程度配对差"
        "及其 CI 见 primary；结论限定于本模型族、冻结参数范围与 50000..50167 的"
        " seed 分布，发生指标为描述性，不构成综合分数，亦不外推至人类被试。"
    )
    check_conclusion_text(conclusion)

    families_validity = {}
    for family in outcomes.FAMILIES:
        diffs = diffs_by_family[family]
        nonzero = sum(1 for d in diffs if d != 0)
        r = primary[family]
        families_validity[family] = {
            "status": "informative" if nonzero > 0 else "degenerate",
            "n_blocks": len(diffs),
            "nonzero_paired_diffs": nonzero,
            "ci_excludes_zero": bool(
                r["ci_low"] is not None and (r["ci_low"] > 0 or r["ci_high"] < 0)
            ),
            "holm_significant": r["holm_significant"],
        }

    return {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "status": "ANALYSED",
        "evidence_class": "formal-research",
        "research_claim_eligibility": "eligible",
        "experimental_validity": {
            "status": "informative"
            if all(v["status"] == "informative" for v in families_validity.values())
            else "degenerate",
            "criterion": (
                "每个预注册主要家族需要至少一个非零严重程度配对差（全零对比无法"
                "支撑估计量）；CI 与 Holm 判定作为辅助事实一并列出"
            ),
            "families": families_validity,
        },
        "index_binding": {
            "path": str(resolved_index),
            "sha256": hashlib.sha256(resolved_index.read_bytes()).hexdigest(),
            "protocol_hash": index["protocol_hash"],
            "n_included": len(index["included"]),
        },
        "analysis_plan": plan,
        "primary": primary,
        "sensitivity": {
            "sign_flip_p": sign_flip,
            "leverage_tier_strata": strata,
            "role": "boundary_evidence_only",
        },
        "mechanisms": _mechanism_summary(block_mechanisms),
        "sesoi_verdict": sesoi_verdict,
        "conclusion_boundary": {
            "occurrence_role": "descriptive",
            "owner_inference": "absent_ai_track_only",
            "composite_score": False,
            "conclusion": conclusion,
        },
    }


def _mechanism_row_values(result: Any) -> dict[str, float | None]:
    """单臂机制值：机制 ID -> 全决策的平均取值（缺失不插补，直接跳过）。"""
    rows = mechanisms.build_table_from_result(result, agent_id=MECHANISM_AGENT_ID)
    sums: dict[str, tuple[float, int]] = {}
    for row in rows:
        for name, value in row.values.items():
            if value.is_missing or value.value is None:
                continue
            total, n = sums.get(name, (0.0, 0))
            sums[name] = (total + value.value, n + 1)
    return {name: total / n for name, (total, n) in sums.items()} if sums else {}


def freeze_analysis(
    *,
    index_path: Path | None = None,
    out_path: Path | None = None,
) -> Path:
    """执行分析并原子落盘。确定性构建：同 index 重跑必须逐字节相同。"""
    target = out_path or DEFAULT_ANALYSIS_PATH
    payload = run_formal_analysis(index_path=index_path)
    if target.exists():
        existing = target.read_text(encoding="utf-8")
        blob = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if existing != blob:
            raise AnalysisError(f"{target} 已存在且与当前分析结果不同——正式结果不可原地改写")
        return target
    write_json_atomic(target, payload)
    return target


def rebind_analysis(
    *,
    index_path: Path | None = None,
    out_path: Path | None = None,
) -> Path:
    """ADR-015：index 重绑后，分析结果必须除 ``index_binding`` 外逐字节不变。

    ``index_binding.sha256`` 随重绑的 index 必然变化；``index_binding.path`` 是
    落盘时的绝对路径，只作信息用途——同一相对位置时沿用旧值，免得换个检出目录
    就改写冻结结果。任何其他字段不同即拒绝：那说明重绑改变了研究结果，不能走
    ADR-015 通道。
    """
    target = out_path or DEFAULT_ANALYSIS_PATH
    prior = json.loads(target.read_text(encoding="utf-8"))
    payload = run_formal_analysis(index_path=index_path)
    old_binding = prior.get("index_binding", {})
    new_binding = payload.get("index_binding", {})
    if {k: v for k, v in prior.items() if k != "index_binding"} != {
        k: v for k, v in payload.items() if k != "index_binding"
    }:
        raise AnalysisError(f"{target}：重绑后分析结果变化——不是簿记重绑，禁止改写")
    if set(old_binding) != set(new_binding) or any(
        old_binding[k] != new_binding[k] for k in old_binding if k not in {"sha256", "path"}
    ):
        raise AnalysisError(f"{target}：index_binding 出现 sha256/path 以外的变化")
    if Path(str(old_binding.get("path"))).name != Path(str(new_binding.get("path"))).name:
        raise AnalysisError(f"{target}：index_binding.path 指向了另一个 index 文件")
    if old_binding.get("sha256") == new_binding.get("sha256"):
        raise AnalysisError(f"{target}：index 未变化，无需重绑")
    payload["index_binding"] = {**new_binding, "path": old_binding["path"]}
    write_json_atomic(target, payload)
    return target
