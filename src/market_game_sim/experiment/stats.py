"""T604/T605 (方法论 §9.2/§10.2/§10.5): paired-experiment statistics.

* :func:`bootstrap_proportion_diff` -- effect size + CI for the difference
  in economic-endpoint rate between a paired control/treatment group
  (方法论 §10.2's "效应量（含置信区间）").
* :func:`holm_bonferroni` -- step-down multiple-comparison correction
  (T604), for when more than one metric/hypothesis is tested at once.
* :func:`build_conditional_conclusion` -- formats a bootstrap result into
  方法论 §10.2's required conditional-proposition text ("在参与者结构 S、
  参数区间 R 与 N 个随机种子下...").

This is the reporting/statistics layer, not the core domain kernel bound by
ADR-001's no-float/hash-only-RNG rule -- floats and a locally-seeded
``random.Random`` (not the global ``random`` module) are used for
reproducible resampling.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class ProportionDiffResult:
    """Bootstrap effect-size/CI for a difference in proportions
    (treatment_rate - control_rate)."""

    control_rate: float
    treatment_rate: float
    diff: float
    ci_low: float
    ci_high: float
    ci_level: float
    n_control: int
    n_treatment: int
    n_resamples: int
    seed: int

    @property
    def ci_excludes_zero(self) -> bool:
        """Whether the CI excludes 0 -- a simple significance proxy at the
        declared ci_level, without invoking a parametric test."""
        return self.ci_low > 0 or self.ci_high < 0


def bootstrap_proportion_diff(
    control_outcomes: list[bool],
    treatment_outcomes: list[bool],
    n_resamples: int = 10_000,
    ci_level: float = 0.95,
    seed: int = 0,
) -> ProportionDiffResult:
    """Bootstrap CI for ``treatment_rate - control_rate`` over boolean
    per-run outcomes (e.g. ``classification.is_economic_endpoint``).

    Deterministic given the same inputs/seed: uses a locally-seeded
    ``random.Random`` instance, never the global ``random`` module, so two
    calls with identical arguments always produce identical results
    (KPI-007 rerun-determinism spirit).
    """
    n_c, n_t = len(control_outcomes), len(treatment_outcomes)
    if n_c == 0 or n_t == 0:
        raise ValueError("bootstrap_proportion_diff requires at least one sample per group")
    if not (0 < ci_level < 1):
        raise ValueError(f"ci_level must be in (0, 1), got {ci_level}")

    control_rate = sum(control_outcomes) / n_c
    treatment_rate = sum(treatment_outcomes) / n_t
    diff = treatment_rate - control_rate

    rng = random.Random(seed)
    diffs = []
    for _ in range(n_resamples):
        c_sum = sum(control_outcomes[rng.randrange(n_c)] for _ in range(n_c))
        t_sum = sum(treatment_outcomes[rng.randrange(n_t)] for _ in range(n_t))
        diffs.append(t_sum / n_t - c_sum / n_c)
    diffs.sort()

    alpha = 1 - ci_level
    lo_idx = max(int((alpha / 2) * n_resamples), 0)
    hi_idx = min(int((1 - alpha / 2) * n_resamples), n_resamples - 1)
    return ProportionDiffResult(
        control_rate=control_rate,
        treatment_rate=treatment_rate,
        diff=diff,
        ci_low=diffs[lo_idx],
        ci_high=diffs[hi_idx],
        ci_level=ci_level,
        n_control=n_c,
        n_treatment=n_t,
        n_resamples=n_resamples,
        seed=seed,
    )


def holm_bonferroni(p_values: dict[str, float], alpha: float = 0.05) -> dict[str, bool]:
    """Holm-Bonferroni step-down multiple-comparison correction (T604).

    ``p_values`` maps a hypothesis name to its (uncorrected) p-value.
    Returns ``{name: significant}`` -- ``True`` means the hypothesis
    remains significant after correction.  Once a hypothesis in rank order
    fails, all hypotheses with an equal-or-larger p-value also fail (the
    step-down property), including on the empty-dict input.
    """
    if not (0 < alpha < 1):
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")
    ranked = sorted(p_values.items(), key=lambda kv: kv[1])
    m = len(ranked)
    result: dict[str, bool] = {}
    for i, (name, p) in enumerate(ranked):
        threshold = alpha / (m - i)
        if p <= threshold:
            result[name] = True
        else:
            for name2, _ in ranked[i:]:
                result[name2] = False
            break
    return result


def build_conditional_conclusion(
    result: ProportionDiffResult,
    structure_desc: str,
    param_range_desc: str,
    failure_condition_desc: str = "",
    metric_name: str = "经济终点率",
) -> str:
    """方法论 §10.2: format a bootstrap result as the required conditional
    proposition -- "在参与者结构 S、参数区间 R 与 N 个随机种子下，信念 B 的
    效应量为 X（含置信区间），在条件 C 之外失效。"  Plain "有效/无效"
    phrasing is rejected by that section; this always emits the
    structure/range/N/effect-size/CI/failure-condition form.
    """
    sig = "显著" if result.ci_excludes_zero else "不显著（置信区间跨零）"
    text = (
        f"在参与者结构 {structure_desc}、参数区间 {param_range_desc} 与 "
        f"{result.n_control} 个随机种子（control）/{result.n_treatment} 个随机种子（treatment）下，"
        f"处理对{metric_name}的效应量为 {result.diff:+.4f}"
        f"（{result.ci_level:.0%} CI：[{result.ci_low:+.4f}, {result.ci_high:+.4f}]，{sig}）。"
    )
    if failure_condition_desc:
        text += f"在 {failure_condition_desc} 之外失效，结论不外推至该范围。"
    else:
        text += "失效条件未声明——本结论只在预注册的参数区间内成立，不得外推。"
    return text
