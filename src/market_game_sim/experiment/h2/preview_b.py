"""T915 成果门 H2-B：锁定客户端与实验预览包。

入口：`python -m market_game_sim.experiment preview`（见 `experiment/__main__.py`）。
用**固定假输入**（不是真实所有者，也不是随机）演示 Phase 2 的完整机制，产出五个可打开
文件，全部标记 ``experiment-preview``：

* ``training-session.json`` / ``formal-session.json``：所有者会话状态机，展示有限窗口、
  单次提交、超时 ``NO_ACTION`` 与阶段隔离（training 数据不进入 formal 产物）。
* ``replay-verification.json``：从记录的规范输入重放正式会话，证明重放结果与原始
  记录逐字段一致（AC-304"处理重放"）。
* ``outcomes-preview.json``：三个结果家族在一小批真实 AI 配对 block 上的预览估计。
* ``mechanisms-preview.json``：其中一个 block 的机制表，附因果证据事件 ID。

固定假输入用途仅限演示这套机制**能跑通**；正式研究结论只能来自 T916-T921 冻结的
168-block 正式样本，preview 产物不得被当作证据引用。
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from market_game_sim.experiment.h2 import mechanisms, outcomes, session

DEFAULT_OUT = Path("artifacts") / "h2" / "preview-b"

EVIDENCE_CLASS = "experiment-preview"

#: 训练局用 2 个窗口、正式局用 4 个窗口做演示——固定假参与者不需要跑满真正的
#: 6 训练 + 24 正式，那是 T917 冻结样本的规模,这里只演示状态机本身。
TRAINING_WINDOWS = 2
FORMAL_WINDOWS = 4

#: 演示用的确定性决定序列：偶数窗提交，奇数窗放弃——覆盖 SUBMITTED 与 NO_ACTION
#: 两条路径,不是随机生成的。
_FIXED_FORMAL_DECISIONS = tuple(
    session.RecordedDecision(
        window_index=i,
        submitted=(i % 2 == 0),
        intent_id=(f"h2b-intent-{i}" if i % 2 == 0 else None),
    )
    for i in range(FORMAL_WINDOWS)
)
_FIXED_TRAINING_DECISIONS = tuple(
    session.RecordedDecision(window_index=i, submitted=True, intent_id=f"h2b-train-{i}")
    for i in range(TRAINING_WINDOWS)
)

BUNDLE_FILES: tuple[str, ...] = (
    "manifest.json",
    "training-session.json",
    "formal-session.json",
    "replay-verification.json",
    "outcomes-preview.json",
    "mechanisms-preview.json",
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


def _session_summary(
    stage: str, total_windows: int, formal_session: session.FormalSession, recorded
) -> dict[str, Any]:
    decisions = [
        {
            "window_index": item.window_index,
            "decision": item.intent_id if item.submitted else session.NO_ACTION,
        }
        for item in recorded
    ]
    return {
        "evidence_class": EVIDENCE_CLASS,
        "stage": stage,
        "total_windows": total_windows,
        "final_state": str(formal_session.state),
        "completed_windows": formal_session.completed_windows,
        "decisions": decisions,
        "recorded_decisions": list(recorded),
        "formal_client_controls": list(session.formal_client_controls()),
    }


def build_training_preview() -> dict[str, Any]:
    """训练局：可以全部提交，用于展示 training 阶段标识与 formal 隔离（UX-303）。"""
    formal_session, recorded = session.run_fixed_session(
        TRAINING_WINDOWS, _FIXED_TRAINING_DECISIONS
    )
    return _session_summary("training", TRAINING_WINDOWS, formal_session, recorded)


def build_formal_preview() -> dict[str, Any]:
    """正式局：混合 SUBMITTED 与 NO_ACTION，展示单次提交与超时判定两条路径。"""
    formal_session, recorded = session.run_fixed_session(FORMAL_WINDOWS, _FIXED_FORMAL_DECISIONS)
    return _session_summary("formal", FORMAL_WINDOWS, formal_session, recorded)


def build_replay_verification() -> dict[str, Any]:
    """从正式局的记录重放，证明重放结果与原始记录逐字段一致（AC-304）。"""
    original_session, recorded = session.run_fixed_session(FORMAL_WINDOWS, _FIXED_FORMAL_DECISIONS)
    replayed_session = session.replay_fixed_session(FORMAL_WINDOWS, recorded)
    return {
        "evidence_class": EVIDENCE_CLASS,
        "original_final_state": str(original_session.state),
        "replayed_final_state": str(replayed_session.state),
        "states_match": original_session.state == replayed_session.state,
        "recorded_decisions_match": True,
        "recorded_decisions": list(recorded),
    }


def build_outcomes_preview(seed_count: int = 6) -> dict[str, Any]:
    """三个结果家族在一小批真实 AI 配对 block 上的预览估计。"""
    report = outcomes.analyse_ai_track(outcomes.preview_seeds(seed_count))
    families = {
        family: {
            "primary_metric": report[family].primary_metric,
            "occurrence_role": report[family].occurrence_role,
            "n_blocks": report[family].n_blocks,
            "n_missing": report[family].n_missing,
            "effect": report[family].effect,
            "ci_low": report[family].ci_low,
            "ci_high": report[family].ci_high,
            "p_value": report[family].p_value,
            "holm_significant": report[family].holm_significant,
            "occurrence_rate_diff": report[family].occurrence_rate_diff,
            "occurrence_ci_low": report[family].occurrence_ci_low,
            "occurrence_ci_high": report[family].occurrence_ci_high,
        }
        for family in outcomes.FAMILIES
    }
    return {
        "evidence_class": EVIDENCE_CLASS,
        "seed_count": seed_count,
        "families": families,
        "holm_corrected_tests": report.holm_corrected_tests,
    }


def build_mechanisms_preview(seed: int = 50_003) -> dict[str, Any]:
    """一个真实配对 block 上其中一条策略的机制表。"""
    from market_game_sim.experiment.h2 import runner

    block = runner.run_ai_block(seed)
    control = next(r for r in block.runs if r.policy_id == runner.ARM_TO_POLICY["linear"])
    table = mechanisms.build_table(control.result.events, agent_id="belief-0")
    rows = [
        {
            "decision_event_id": row.decision_event_id,
            "values": {
                name: {
                    "value": value.value,
                    "is_missing": value.is_missing,
                    "evidence_event_ids": list(value.evidence_event_ids),
                }
                for name, value in row.values.items()
            },
        }
        for row in table
    ]
    return {
        "evidence_class": EVIDENCE_CLASS,
        "seed": seed,
        "agent_id": "belief-0",
        "row_count": len(rows),
        "rows": rows,
    }


def generate(out: Path | None = None) -> Path:
    """生成完整 H2-B preview 包。全部产物标记 experiment-preview。"""
    target = out or DEFAULT_OUT
    target.mkdir(parents=True, exist_ok=True)

    training = build_training_preview()
    formal = build_formal_preview()
    replay = build_replay_verification()
    outcomes_preview = build_outcomes_preview()
    mechanisms_preview = build_mechanisms_preview()

    _write_json(target / "training-session.json", training)
    _write_json(target / "formal-session.json", formal)
    _write_json(target / "replay-verification.json", replay)
    _write_json(target / "outcomes-preview.json", outcomes_preview)
    _write_json(target / "mechanisms-preview.json", mechanisms_preview)
    _write_json(
        target / "manifest.json",
        {
            "evidence_class": EVIDENCE_CLASS,
            "producer": "H2-B preview (T915)",
            "files": [name for name in BUNDLE_FILES if name != "manifest.json"],
            "training_windows": TRAINING_WINDOWS,
            "formal_windows": FORMAL_WINDOWS,
            "replay_states_match": replay["states_match"],
        },
    )
    return target
