"""T604 (KPI-007): final conditional conclusion.

Assembles the 方法论 §10.2 conditional proposition for a robustness result,
with every element KPI-007 requires: participant structure, parameter range,
behavior mapping, model family (with the T105 cross-matrix verdict), seed
count, effect size, interval estimate, failure boundary -- and the explicit
no-extrapolation clause.

Reuses ``experiment.stats.build_conditional_conclusion`` for the core
structure/range/N/effect/CI wording and prepends the mapping/family/cross-
verdict context that the robustness layer must carry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from market_game_sim.experiment.stats import (
    ProportionDiffResult,
    build_conditional_conclusion,
)


@dataclass
class FinalConclusion:
    text: str
    elements: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"text": self.text, "elements": self.elements}


def build_final_conclusion(
    result: ProportionDiffResult,
    *,
    structure_desc: str,
    param_range_desc: str,
    behavior_mapping_id: str,
    model_family_id: str,
    cross_verdict: str,
    failure_boundary_desc: str = "",
) -> FinalConclusion:
    """Build the final conditional conclusion for one robustness cell.

    ``cross_verdict``: the T105 cross-matrix verdict for this
    (model_family, behavior_mapping) cell -- 同向成立 / 依赖边界 / 证据不足.
    ``failure_boundary_desc``: the T205 localized failure boundary (interval +
    resolution), when one exists.
    """
    core = build_conditional_conclusion(
        result,
        structure_desc=structure_desc,
        param_range_desc=param_range_desc,
        failure_condition_desc=failure_boundary_desc,
    )
    elements = {
        "structure_desc": structure_desc,
        "param_range_desc": param_range_desc,
        "behavior_mapping_id": behavior_mapping_id,
        "model_family_id": model_family_id,
        "cross_verdict": cross_verdict,
        "n_control_seeds": result.n_control,
        "n_treatment_seeds": result.n_treatment,
        "effect_size": result.diff,
        "ci_low": result.ci_low,
        "ci_high": result.ci_high,
        "failure_boundary_desc": failure_boundary_desc,
        "extrapolation_forbidden": True,
    }
    text = (
        f"行为映射 {behavior_mapping_id} × 模型族 {model_family_id}，"
        f"交叉判定：{cross_verdict}。{core}"
    )
    return FinalConclusion(text=text, elements=elements)
