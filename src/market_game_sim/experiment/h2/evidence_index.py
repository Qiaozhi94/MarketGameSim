"""T918：H2 AI 轨 formal evidence index 冻结与样本流图。

design.md 给了这个对象两条硬边界，本模块的结构就长在它们上面：

* **分析只读冻结 index，不扫目录**（§2）——T919 拿到的样本集合只能来自
  ``load_frozen_index``，采样目录里的文件多一个少一个都不影响分析；
* **index 只列纳入 pair 与协议哈希，不复制身份资料，也不预支分析结论**（§3）
  ——所以 payload 里没有 severity、没有 effect、没有 p 值，只有"哪些 pair
  以什么证据哈希被纳入"。

冻结语义与归档一致：内容由冻结输入（分配表 + 盘上工件的技术字段）确定性
决定，重建必须逐字节相同；已冻结的 index 不允许被静默改写，输入变化后想
重冻结必须显式删除旧文件留痕。验证全部完成之前不写任何部分聚合（IR-302
的原子性）。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from market_game_sim.experiment.h2 import adjudication, artifacts, evidence_guard
from market_game_sim.experiment.h2.artifacts import canonical_digest, write_json_atomic

INDEX_SCHEMA_VERSION = 1

#: 冻结 index 的落盘位置。采样证据靠 index 冻结进仓（artifacts/ 在 .gitignore 里），
#: 与 0.1.5 的 evidence index 同一目录家族；AI/owner 各自维护，owner 的由 0.3.2 生成。
DEFAULT_INDEX_PATH = artifacts.ROOT / "docs" / "experiments" / "H2-ai-evidence-index.json"

_PRIMARY_FAMILIES = ("price_crash", "liquidity_dry_up", "liquidation_cascade")

ARCHIVE_PROTOCOL_PATH = (
    artifacts.ROOT / "docs" / "experiments" / "H2-formal-freeze" / "protocol.json"
)

#: 分析禁止预支的字段——它们只能由 T919 从冻结 seed 重放后产生。
_FORBIDDEN_RESULT_FIELDS = ("severity", "effect", "p_value", "ci_low", "ci_high", "holm")


#: ADR-015：冻结后唯一允许重绑的字段——都是「事件流 / 工件字节」的摘要，不是样本、
#: 分配或裁决。重绑还必须附带经济等价证明（``tools/prove_economic_equivalence.py``）。
REBIND_ATTESTATIONS_KEY = "rebind_attestations"
REBINDABLE_FIELDS = frozenset({"artifact_sha256", "events_sha256"})
_ATTESTATION_KEYS = frozenset(
    {"rebound_at", "adr", "reason", "prior_index_sha256", "changed_fields", "economic_equivalence"}
)
_EQUIVALENCE_KEYS = frozenset(
    {
        "projection",
        "baseline_ref",
        "arms_compared",
        "arms_identical",
        "baseline_reproduces_frozen_index",
        "reproduce",
    }
)


class EvidenceIndexError(RuntimeError):
    """evidence index 的构建或冻结合同被违反。"""


class IncompleteStudy(EvidenceIndexError):
    """合格 pair 未达冻结停止规则——按预注册 §7 不得冻结可分析 index。"""


def _artifact_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


#: 运行终止态 → 裁决器 session_state 词汇（session.SessionState 的冻结闭集）。
_TERMINATED_TO_STATE = {
    "COMPLETED": "completed",
    "TECHNICAL_ABORT": "technical-abort",
    "ABORTED": "aborted",
}


def _technical_record(
    payload: dict[str, Any], *, expected_protocol_hash: str
) -> adjudication.TechnicalRecord:
    """把盘上工件投影成裁决器输入——只含技术/协议字段，结构上装不进结果。"""
    runs = payload.get("runs")
    valid_runs = (
        isinstance(runs, list) and len(runs) == 2 and all(isinstance(r, dict) for r in runs)
    )
    pair_arms = {run.get("arm") for run in runs} if valid_runs else set()
    states = [_TERMINATED_TO_STATE.get(run.get("terminated")) for run in runs] if valid_runs else []
    pair_complete = (
        valid_runs
        and pair_arms == {"linear", "threshold"}
        and all(
            state == "completed" and run.get("abort_code") is None
            for state, run in zip(states, runs, strict=True)
        )
    )
    if pair_complete:
        state = "completed"
    elif "technical-abort" in states or any(
        isinstance(run, dict) and run.get("abort_code") is not None for run in (runs or [])
    ):
        state = "technical-abort"
    elif "aborted" in states:
        state = "aborted"
    else:
        state = "incomplete-session"
    return adjudication.TechnicalRecord(
        assignment_id=str(payload.get("assignment_id", "")),
        session_state=state,
        pair_complete=pair_complete,
        protocol_hash=str(payload.get("protocol_hash", "")),
        expected_protocol_hash=expected_protocol_hash,
    )


def build_index(
    *,
    out_dir: Path | None = None,
    assignments: dict[str, Any] | None = None,
    minimum_blocks: int | None = None,
) -> dict[str, Any]:
    """从冻结分配表 + 盘上工件的技术字段构建 index payload（不落盘）。

    顺序与样本集合由冻结分配表拥有：逐条 issued assignment 消费其盘上工件
    （缺席即 INCOMPLETE_SESSION），工件里多出来的 order_index 不在分配表内的
    直接 fail-closed。裁决只读技术字段（T914），纳入结果与排除原因全部来自
    冻结规则。``minimum_blocks`` 覆盖停止规则的合同下限（仅测试用）；缺省
    读取冻结协议的 ``contract_minimum_blocks``。
    """
    table = assignments or artifacts.load_assignments()
    bindings = artifacts.verify_formal_bindings(table)
    expected_hash = table["protocol_hash"]
    target_dir = out_dir or artifacts.DEFAULT_FORMAL_ROOT / "ai"

    by_order: dict[int, dict[str, Any]] = {}
    for path in sorted(target_dir.glob("block-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = None
        if not isinstance(payload, dict):
            raise EvidenceIndexError(f"采样目录存在不可读工件：{path}")
        if payload.get("run_mode") != evidence_guard.AI_TRACK:
            raise EvidenceIndexError(
                f"工件 {path.name} 的 run_mode {payload.get('run_mode')!r} 不是 AI 轨——"
                "外来轨道不得进入 AI 采样目录（FR-303 fail closed）"
            )
        order_index = payload.get("order_index")
        if order_index not in {entry["order_index"] for entry in table["ai_assignments"]}:
            raise EvidenceIndexError(
                f"工件 {path.name} 的 order_index {order_index!r} 不在冻结分配表内"
            )
        if order_index in by_order:
            raise EvidenceIndexError(f"order_index {order_index} 有多个盘上工件")
        by_order[int(order_index)] = payload | {"_artifact_path": path}

    decisions: list[adjudication.AdjudicationDecision] = []
    included: list[dict[str, Any]] = []
    records: list[adjudication.TechnicalRecord] = []
    for entry in table["ai_assignments"]:
        order_index = int(entry["order_index"])
        payload = by_order.get(order_index)
        if payload is None:
            # 工件缺席 = 会话未完成，不是协议漂移：带期望哈希让裁决落到
            # INCOMPLETE_SESSION（漂移优先级最高，空哈希会被它抢先误判）。
            record = adjudication.TechnicalRecord(
                assignment_id=entry["assignment_id"],
                session_state="incomplete-session",
                pair_complete=False,
                protocol_hash=expected_hash,
                expected_protocol_hash=expected_hash,
            )
        else:
            record = _technical_record(payload, expected_protocol_hash=expected_hash)
        records.append(record)
        decision = adjudication.adjudicate(record)
        decisions.append(decision)
        if decision.status is adjudication.AdjudicationStatus.INCLUDED:
            path: Path = payload["_artifact_path"]
            arms: dict[str, Any] = {}
            for run in payload["runs"]:
                arms[run["arm"]] = {
                    "policy_id": run["policy_id"],
                    "events_sha256": run["events_sha256"],
                }
            evidence_guard.admit(
                run_mode=payload.get("run_mode", ""),
                stage=payload.get("stage", ""),
                pair_complete=record.pair_complete,
            )
            included.append(
                {
                    "order_index": order_index,
                    "assignment_id": entry["assignment_id"],
                    "seed": int(entry["seed"]),
                    "artifact_sha256": _artifact_digest(path),
                    "pair_identical_fields": sorted(
                        payload.get("pair", {}).get("identical_fields", [])
                    ),
                    "arms": arms,
                }
            )

    archive_protocol = json.loads(ARCHIVE_PROTOCOL_PATH.read_text(encoding="utf-8"))
    flow = adjudication.sample_flow_summary(tuple(decisions))
    reserve = table["reserve_seeds"]
    minimum = (
        minimum_blocks
        if minimum_blocks is not None
        else int(archive_protocol["payload"]["contract_minimum_blocks"])
    )
    if flow["included"] < minimum:
        raise IncompleteStudy(
            f"合格 pair {flow['included']}/{minimum}，备用池未用尽前不得冻结可分析 index"
            "（预注册 §7：输出 incomplete-study，禁止分析）"
        )

    return {
        "schema_version": INDEX_SCHEMA_VERSION,
        "status": "FROZEN",
        "track": evidence_guard.AI_TRACK,
        "research_claim_eligibility": "eligible",
        "experimental_validity": {
            "status": "informative",
            "criterion": (
                "每个预注册主要家族需要完整冻结样本（合格 pair 全数纳入、备用池未"
                "消耗）；严重程度对比的非退化性由 H2-ai-analysis.json 机器校验"
            ),
            "families": {
                family: {"status": "informative", "qualified_pairs": flow["included"]}
                for family in _PRIMARY_FAMILIES
            },
        },
        "protocol_hash": expected_hash,
        "contract_protocol_hash": bindings["contract_protocol_hash"],
        "contract_id": archive_protocol["payload"]["contract_id"],
        "preregistration": archive_protocol["payload"]["preregistration"],
        "assignments_sha256": canonical_digest(table),
        "sample_flow": {
            **flow,
            "issued_blocks": len(table["ai_assignments"]),
            "reserve_pool": {"size": len(reserve), "consumed": [], "unused": len(reserve)},
        },
        "included": included,
    }


def freeze_index(
    path: Path | None = None,
    *,
    out_dir: Path | None = None,
    assignments: dict[str, Any] | None = None,
    required_blocks: int | None = None,
) -> Path:
    """构建并原子冻结 index。已冻结且内容不同 → 拒绝改写；完全相同 → 幂等。"""
    target = path or DEFAULT_INDEX_PATH
    payload = build_index(out_dir=out_dir, assignments=assignments, minimum_blocks=required_blocks)
    blob = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    for field in _FORBIDDEN_RESULT_FIELDS:
        if f'"{field}"' in blob:
            raise EvidenceIndexError(f"index 不得预支分析结论字段：{field}")
    if target.exists():
        existing_payload = json.loads(target.read_text(encoding="utf-8"))
        existing_payload.pop(REBIND_ATTESTATIONS_KEY, None)
        existing = json.dumps(existing_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if existing != blob:
            raise EvidenceIndexError(
                f"{target} 已冻结且与当前重建结果不同——冻结证据不可原地改写；"
                "如确需修订，显式移除旧文件并按预注册修订规则留痕"
            )
        return target
    write_json_atomic(target, payload)
    return target


def load_frozen_index(path: Path | None = None) -> dict[str, Any]:
    """分析入口的唯一样本来源。schema、状态、协议绑定任一不对即 fail-closed。"""
    target = path or DEFAULT_INDEX_PATH
    if not target.exists():
        raise FileNotFoundError(f"冻结 evidence index 不存在：{target}（先跑 T918 freeze）")
    payload = json.loads(target.read_text(encoding="utf-8"))
    if payload.get("schema_version") != INDEX_SCHEMA_VERSION:
        raise EvidenceIndexError(f"未知 index schema_version：{payload.get('schema_version')!r}")
    if payload.get("status") != "FROZEN":
        raise EvidenceIndexError(f"index 状态 {payload.get('status')!r} 不是 FROZEN")
    if payload.get("track") != evidence_guard.AI_TRACK:
        raise EvidenceIndexError(f"index 轨道 {payload.get('track')!r} 不是 AI 轨")
    table = artifacts.load_assignments()
    if payload.get("protocol_hash") != table["protocol_hash"]:
        raise EvidenceIndexError("index 协议哈希与当前冻结归档不一致")
    validate_rebind_attestations(payload.get(REBIND_ATTESTATIONS_KEY, []))
    return payload


# --------------------------------------------------------------------------- #
# ADR-015：冻结后重绑（只换摘要、不换样本），带经济等价证明留痕
# --------------------------------------------------------------------------- #


def validate_rebind_attestations(attestations: Any) -> None:
    """每条重绑记录必须结构完整、且声明的经济等价是全量且成立的。"""
    if not isinstance(attestations, list):
        raise EvidenceIndexError(f"{REBIND_ATTESTATIONS_KEY} 必须是列表")
    for i, att in enumerate(attestations):
        where = f"{REBIND_ATTESTATIONS_KEY}[{i}]"
        if not isinstance(att, dict) or set(att) != _ATTESTATION_KEYS:
            raise EvidenceIndexError(f"{where} 字段集合必须恰为 {sorted(_ATTESTATION_KEYS)}")
        if att["adr"] != "ADR-015":
            raise EvidenceIndexError(f"{where}.adr 必须为 ADR-015")
        if not isinstance(att["reason"], str) or not att["reason"].strip():
            raise EvidenceIndexError(f"{where}.reason 不能为空")
        changed = att["changed_fields"]
        if not isinstance(changed, list) or not changed or not set(changed) <= REBINDABLE_FIELDS:
            raise EvidenceIndexError(
                f"{where}.changed_fields 只能是 {sorted(REBINDABLE_FIELDS)} 的非空子集"
            )
        eq = att["economic_equivalence"]
        if not isinstance(eq, dict) or set(eq) != _EQUIVALENCE_KEYS:
            raise EvidenceIndexError(f"{where}.economic_equivalence 字段集合不符")
        if eq["baseline_reproduces_frozen_index"] is not True:
            raise EvidenceIndexError(f"{where}：基线未能复现冻结 index，等价证明无效")
        compared, identical = eq["arms_compared"], eq["arms_identical"]
        if type(compared) is not int or compared <= 0 or identical != compared:
            raise EvidenceIndexError(f"{where}：经济等价必须全量成立（{identical}/{compared}）")


def _changed_fields(old: Any, new: Any, path: str = "") -> set[str]:
    """两棵 JSON 树里取值不同的叶子字段名（按最后一段键名归类）。"""
    if isinstance(old, dict) and isinstance(new, dict):
        if set(old) != set(new):
            return {f"<keys@{path or 'root'}>"}
        out: set[str] = set()
        for key in old:
            leaf = _changed_fields(old[key], new[key], f"{path}.{key}")
            out |= {key} if leaf == {"<leaf>"} else leaf
        return out
    if isinstance(old, list) and isinstance(new, list):
        if len(old) != len(new):
            return {f"<length@{path}>"}
        out = set()
        for a, b in zip(old, new, strict=True):
            out |= _changed_fields(a, b, path)
        return out
    return set() if old == new else {"<leaf>"}


def rebind_frozen_index(
    path: Path | None = None,
    *,
    economic_equivalence: dict[str, Any],
    reason: str,
    rebound_at: str,
    out_dir: Path | None = None,
    assignments: dict[str, Any] | None = None,
    required_blocks: int | None = None,
) -> Path:
    """ADR-015：用重采样的工件重建 index；与旧 index 相比只允许摘要字段变化。

    样本、分配、裁决、样本流任何一处变化都会让重建与旧 index 在非摘要字段上
    出现差异，这里直接拒绝——那不是重绑，是重新做实验。
    """
    target = path or DEFAULT_INDEX_PATH
    prior_bytes = target.read_bytes()
    prior = json.loads(prior_bytes)
    history = prior.pop(REBIND_ATTESTATIONS_KEY, [])
    rebuilt = build_index(out_dir=out_dir, assignments=assignments, minimum_blocks=required_blocks)
    changed = _changed_fields(prior, rebuilt)
    if not changed:
        raise EvidenceIndexError("重建结果与冻结 index 完全相同，无需重绑")
    if not changed <= REBINDABLE_FIELDS:
        raise EvidenceIndexError(
            f"重建结果在非摘要字段上变化：{sorted(changed - REBINDABLE_FIELDS)}——拒绝重绑"
        )
    attestation = {
        "rebound_at": rebound_at,
        "adr": "ADR-015",
        "reason": reason,
        "prior_index_sha256": hashlib.sha256(prior_bytes).hexdigest(),
        "changed_fields": sorted(changed),
        "economic_equivalence": economic_equivalence,
    }
    attestations = [*history, attestation]
    validate_rebind_attestations(attestations)
    write_json_atomic(target, {**rebuilt, REBIND_ATTESTATIONS_KEY: attestations})
    return target
