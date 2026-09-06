"""T904：H2 协议的完整性校验、内容寻址与不可变冻结（FR-301 / AC-301）。

设计要点：

* **唯一真源是双轨合同**：``draft_from_contract()`` 从
  ``docs/experiments/H2-dual-track-contract.json`` 派生草案，而不是在代码里重抄一份
  样本量、SESOI 或策略 ID。合同变了，草案跟着变，不需要改这个文件。
* **完整性先于哈希**：缺任一冻结项就不产生哈希——否则一份残缺协议也能拿到看起来
  合法的 ``protocol_hash``，后面的 evidence guard 就失去了锚点。
* **内容寻址**：``protocol_hash`` 是 canonical JSON 的 SHA-256。任何字段变化都产生
  新哈希，按旧哈希签发的 assignment 随之失效（协议冻结后不可原地修改，spec §5）。
* **冻结即不可变**：``FrozenProtocol`` 是 frozen dataclass，payload 以只读映射暴露。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

#: CLI 与协议 schema 共用的 control-arm 闭集（DQ-302）。不维护第二套名称映射。
CONTROL_ARMS: tuple[str, ...] = ("linear", "threshold", "owner")

SCHEMA_VERSION = 1

ROOT = Path(__file__).resolve().parents[4]
CONTRACT_PATH = ROOT / "docs" / "experiments" / "H2-dual-track-contract.json"

#: FR-301 要求在首个正式样本前冻结的项。缺任一项都不得产生哈希。
REQUIRED_FIELDS: tuple[str, ...] = (
    "schema_version",
    "contract_id",
    "research_question",
    "hypothesis_sidedness",
    "outcome_families",
    "primary_estimand",
    "occurrence_role",
    "sesoi_by_family",
    "minimum_blocks",
    "policies",
    "control_arms",
    "window_contract",
    "tracks",
    "conclusion_syntax",
    "unblinding_rule",
)


class ProtocolError(ValueError):
    """H2 协议合同被违反。"""


class ProtocolIncomplete(ProtocolError):
    """草案缺少冻结项，因此不允许冻结。"""


class ProtocolDrift(ProtocolError):
    """协议内容在冻结之后发生了变化。"""


def _canonical_json(payload: dict[str, Any]) -> bytes:
    """稳定序列化：排序键、无多余空白、不转义非 ASCII。"""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def content_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def load_contract(path: Path | None = None) -> dict[str, Any]:
    target = path or CONTRACT_PATH
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - 环境性错误
        raise ProtocolError(f"无法读取双轨合同 {target}: {exc}") from exc


def draft_from_contract(
    *,
    contract_path: Path | None = None,
    minimum_blocks: int | None = None,
) -> dict[str, Any]:
    """从冻结的双轨合同派生协议草案。

    ``minimum_blocks`` 只用于测试和敏感性检查——它让调用方能构造一份**内容不同**
    的协议来验证哈希确实随内容变化，而不是在生产路径上放一个可以随手下调样本量的
    旋钮；合同本身声明 ``may_lower_minimum_blocks: false``，下调会被 ``freeze`` 拒绝。
    """
    contract = load_contract(contract_path)
    ai = contract["formal_ai_track"]
    owner = contract["owner_n_of_1_track"]
    shared = contract["shared_constraints"]

    return {
        "schema_version": SCHEMA_VERSION,
        "contract_id": contract["contract_id"],
        "research_question": contract["research_question"],
        "hypothesis_sidedness": "two-sided",
        "outcome_families": list(shared["outcome_families"]),
        "primary_estimand": ai["primary_estimand"],
        "occurrence_role": ai["occurrence_role"],
        "sesoi_by_family": dict(ai["sesoi_by_family"]),
        "minimum_blocks": ai["minimum_blocks"] if minimum_blocks is None else minimum_blocks,
        "contract_minimum_blocks": ai["minimum_blocks"],
        "policies": list(ai["conditions"]),
        "control_arms": list(CONTROL_ARMS),
        "window_contract": {
            "logical_ns_per_window": 1_000_000_000,
            "windows_per_scenario": 60,
            "owner_wall_clock_seconds": 8,
            "max_actions_per_window": 1,
            "timeout_decision": "NO_ACTION",
            "applies_to": list(CONTROL_ARMS),
        },
        "tracks": {
            "ai_formal": {
                "run_mode": ai["run_mode"],
                "evidence_class": ai["evidence_class"],
                "research_claim_eligible": ai["research_claim_eligible"],
                "experimental_unit": ai["experimental_unit"],
            },
            "owner_n_of_1": {
                "run_mode": owner["run_mode"],
                "evidence_class": owner["evidence_class"],
                "research_claim_eligible": owner["research_claim_eligible"],
                "formal_paired_blocks": owner["formal_paired_blocks"],
                "training_blocks": owner["training_blocks"],
            },
        },
        "conclusion_syntax": {
            "forbidden_shorthands": ["人类效应", "human effect"],
            "required_qualifiers": ["模型族", "参数范围", "seed 分布"],
        },
        "unblinding_rule": owner["unblinding_rule"],
    }


@dataclass(frozen=True, slots=True)
class FrozenProtocol:
    """内容寻址的冻结协议。payload 只读，改动必须走新版本。"""

    protocol_hash: str
    payload: MappingProxyType

    @property
    def contract_id(self) -> str:
        return self.payload["contract_id"]

    @property
    def minimum_blocks(self) -> int:
        return self.payload["minimum_blocks"]

    def verify(self) -> None:
        """重算哈希，确认 payload 没有被绕过 dataclass 改动。"""
        if content_hash(dict(self.payload)) != self.protocol_hash:
            raise ProtocolDrift("协议内容与冻结时的哈希不一致")

    def reference(self) -> dict[str, str]:
        return {"contract_id": self.contract_id, "protocol_hash": self.protocol_hash}


def _check_complete(draft: dict[str, Any]) -> None:
    missing = [field for field in REQUIRED_FIELDS if field not in draft]
    if missing:
        raise ProtocolIncomplete(f"协议缺少冻结项：{sorted(missing)}")

    families = draft["outcome_families"]
    sesoi = draft["sesoi_by_family"]
    if set(sesoi) != set(families):
        raise ProtocolIncomplete("每个结果家族都必须有 SESOI 条目")
    unset = sorted(name for name, value in sesoi.items() if value is None)
    if unset:
        raise ProtocolIncomplete(f"以下家族的 SESOI 尚未校准：{unset}")

    if draft["primary_estimand"] != "severity_paired_difference":
        raise ProtocolIncomplete("主要 estimand 必须是严重程度配对差（发生指标实测为零方差）")

    policies = draft["policies"]
    if len(policies) != 2 or len(set(policies)) != 2:
        raise ProtocolIncomplete(f"AI 轨必须有两条互不相同的策略，实际为 {policies}")

    if tuple(draft["control_arms"]) != CONTROL_ARMS:
        raise ProtocolIncomplete(f"control_arms 必须是冻结闭集 {CONTROL_ARMS}")

    floor = draft.get("contract_minimum_blocks")
    if isinstance(floor, int) and draft["minimum_blocks"] < floor:
        raise ProtocolIncomplete(f"block 数不得低于合同下限：{draft['minimum_blocks']} < {floor}")

    owner_track = draft["tracks"]["owner_n_of_1"]
    if owner_track["research_claim_eligible"]:
        raise ProtocolIncomplete("n=1 的所有者轨不得承担研究声明（SOP 原则 3）")


def freeze(draft: dict[str, Any]) -> FrozenProtocol:
    """校验完整性后冻结协议；缺项时不产生任何哈希。"""
    _check_complete(draft)
    payload = json.loads(_canonical_json(draft).decode("utf-8"))
    return FrozenProtocol(protocol_hash=content_hash(payload), payload=MappingProxyType(payload))


def accepts_assignment(protocol: FrozenProtocol, *, issued_under: str) -> bool:
    """assignment 只能在签发它的那一版协议下运行（spec §5 不变量）。"""
    return protocol.protocol_hash == issued_under
