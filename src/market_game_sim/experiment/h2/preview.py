"""T909 成果门 H2-A：生成可打开的冻结协议预览包。

入口：`python -m market_game_sim.experiment protocol preview`（见
`experiment/__main__.py`）。产出标记为 `experiment-preview`——`evidence_guard`
只在 `stage == "formal"` 才放行，preview 产物本身永远进不了正式索引，标记只是
让读者一眼看清这批文件的证据级别。

产出三个文件，各自独立可打开：

* ``protocol.json``：冻结协议的完整 payload 与内容哈希。
* ``pair-manifest-diff.json``：一次真实配对 block 的 pair validator 输出——
  哪些字段相同、哪些字段（连同两条策略 ID）不同。
* ``guard-matrix.json``：evidence guard 在一组关键场景下的准入/拒绝结果，
  显式覆盖验收要求的两条——H1 交互数据被拒绝、协议漂移被拒绝。
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from market_game_sim.experiment.h2 import assignment, evidence_guard, protocol, runner

DEFAULT_OUT = Path("artifacts") / "h2" / "preview"

#: 生成配对 diff 用的示例 seed；取 H2 seed 段起点，preview 不消费正式 assignment。
SAMPLE_SEED = assignment.H2_FIRST_SEED

EVIDENCE_CLASS = "experiment-preview"

BUNDLE_FILES: tuple[str, ...] = (
    "manifest.json",
    "protocol.json",
    "pair-manifest-diff.json",
    "guard-matrix.json",
)


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_to_jsonable(item) for item in value]
    return value


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(_to_jsonable(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_pair_manifest_diff(seed: int = SAMPLE_SEED) -> dict[str, Any]:
    """跑一个真实配对 block，展示 pair validator 的实际输出（不是伪造样例）。"""
    block = runner.run_ai_block(seed)
    report = runner.validate_pair(block)
    return {
        "seed": seed,
        "policies": [run.policy_id for run in block.runs],
        "identical_fields": sorted(report.identical_fields),
        "disclosed_differences": report.disclosed_differences,
        "severity_by_policy": {run.policy_id: runner.chain_severity(run) for run in block.runs},
    }


def build_guard_matrix(frozen: protocol.FrozenProtocol) -> list[dict[str, Any]]:
    """穷举关键场景，逐条记录 evidence guard 的准入/拒绝结果。

    验收明确要求"协议漂移及 H1 数据均被拒绝"能在产出里看到，因此这两条场景显式列出，
    不依赖读者自己去脑补 guard 会怎么反应。
    """
    scenarios: tuple[dict[str, Any], ...] = (
        {
            "label": "ai_track_formal_frozen_protocol",
            "kwargs": {
                "run_mode": evidence_guard.AI_TRACK,
                "stage": "formal",
                "protocol_hash": frozen.protocol_hash,
            },
        },
        {
            "label": "owner_track_formal_frozen_protocol",
            "kwargs": {
                "run_mode": evidence_guard.OWNER_TRACK,
                "stage": "formal",
                "protocol_hash": frozen.protocol_hash,
            },
        },
        {
            "label": "h1_interactive_data_rejected",
            "kwargs": {"run_mode": "interactive", "stage": "formal"},
        },
        {
            "label": "protocol_drift_rejected",
            "kwargs": {
                "run_mode": evidence_guard.AI_TRACK,
                "stage": "formal",
                "protocol_hash": "0" * 64,
            },
        },
        {
            "label": "training_stage_rejected",
            "kwargs": {"run_mode": evidence_guard.AI_TRACK, "stage": "training"},
        },
        {
            "label": "preview_stage_rejected",
            "kwargs": {"run_mode": evidence_guard.AI_TRACK, "stage": "preview"},
        },
        {
            "label": "incomplete_pair_rejected",
            "kwargs": {
                "run_mode": evidence_guard.AI_TRACK,
                "stage": "formal",
                "protocol_hash": frozen.protocol_hash,
                "pair_complete": False,
            },
        },
    )

    matrix: list[dict[str, Any]] = []
    for scenario in scenarios:
        try:
            evidence_guard.admit(**scenario["kwargs"])
        except evidence_guard.EvidenceRejected as exc:
            matrix.append({"label": scenario["label"], "admitted": False, "reason": str(exc)})
        else:
            matrix.append({"label": scenario["label"], "admitted": True, "reason": None})
    return matrix


def generate(out: Path | None = None) -> Path:
    """生成完整 preview 包：协议 + 配对 diff + guard 矩阵，全部标记 experiment-preview。

    guard 矩阵的场景会写入账本（``evidence_guard`` 是进程内单例账本），生成前后各
    ``reset()`` 一次，避免污染其他调用方或把这里的探测记录混进真正的准入历史。
    """
    target = out or DEFAULT_OUT
    target.mkdir(parents=True, exist_ok=True)

    evidence_guard.reset()
    frozen = protocol.freeze(protocol.draft_from_contract())
    pair_diff = build_pair_manifest_diff()
    guard_matrix = build_guard_matrix(frozen)
    evidence_guard.reset()

    _write_json(
        target / "protocol.json",
        {
            "evidence_class": EVIDENCE_CLASS,
            "protocol_hash": frozen.protocol_hash,
            "payload": dict(frozen.payload),
        },
    )
    _write_json(
        target / "pair-manifest-diff.json",
        {"evidence_class": EVIDENCE_CLASS, **pair_diff},
    )
    _write_json(
        target / "guard-matrix.json",
        {"evidence_class": EVIDENCE_CLASS, "scenarios": guard_matrix},
    )
    _write_json(
        target / "manifest.json",
        {
            "evidence_class": EVIDENCE_CLASS,
            "protocol_hash": frozen.protocol_hash,
            "producer": "H2-A preview (T909)",
            "files": [name for name in BUNDLE_FILES if name != "manifest.json"],
        },
    )
    return target
