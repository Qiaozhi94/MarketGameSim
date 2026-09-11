"""T917 采样工件的公共落盘约定：规范化摘要、原子写、冻结台账加载。

正式采样的两类工件（AI block、所有者会话）共享三条纪律：

* **原子写**：先写临时文件再 ``os.replace``——裁决器或 evidence index 冻结读到的
  要么是完整文件，要么没有文件，绝不读半截 JSON。
* **规范化摘要**：市场事件流不进工件（体积大且分析可从冻结 seed 确定性重放），
  进工件的是它的 SHA-256，用于证明"重放与我当时锁定的状态一致"。
* **单一真源加载**：分配表只从冻结归档 ``assignments.json`` 读取，任何调用方都
  不自己算 seed。
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
ASSIGNMENTS_PATH = ROOT / "docs" / "experiments" / "H2-formal-freeze" / "assignments.json"

#: 正式采样的默认落盘根。artifacts/ 在 .gitignore 里——采样证据靠 evidence index
#: 冻结进仓，不靠把原始工件提交进 git。
DEFAULT_FORMAL_ROOT = ROOT / "artifacts" / "h2" / "formal"
DEFAULT_TRAINING_ROOT = ROOT / "artifacts" / "h2" / "training"


def canonical_digest(payload: Any) -> str:
    """规范化 JSON 的 SHA-256。键排序 + 紧凑分隔符，与协议内容哈希同族。"""
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def write_json_atomic(path: Path, payload: Any) -> None:
    """先写临时文件再原子替换；失败时目标路径保持原样（可能不存在，但绝不半截）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def load_assignments(path: Path | None = None) -> dict[str, Any]:
    """加载冻结分配表。文件缺失或状态非 FROZEN 一律 fail-closed。"""
    target = path or ASSIGNMENTS_PATH
    if not target.exists():
        raise FileNotFoundError(f"冻结分配表不存在：{target}（先跑 T916 formal freeze）")
    payload = json.loads(target.read_text(encoding="utf-8"))
    if payload.get("status") != "FROZEN":
        raise ValueError(f"分配表状态 {payload.get('status')!r} 不是 FROZEN")
    return payload


def ai_seed_for_scenario(assignments: dict[str, Any], scenario_id: int) -> int:
    """所有者场景 id -> AI 配对同款 seed。

    design.md §3：每个所有者 block 另配**同 seed**的两条 WINDOW_MATCHED_POLICY_CONTROL
    参照。冻结归档里 ``owner_scenario_order`` 的元素就是 ``ai_assignments`` 的
    ``order_index``，二者 1:1 对应同一条 seed——这是"同 seed"唯一可以在数据上
    成立的读法，客户端不再另立一套编号。
    """
    by_index = {item["order_index"]: item for item in assignments["ai_assignments"]}
    entry = by_index.get(scenario_id)
    if entry is None:
        raise KeyError(f"owner_scenario_order 引用了不存在的 order_index {scenario_id}")
    return int(entry["seed"])


def verify_formal_bindings(table: dict[str, Any] | None = None) -> dict[str, Any]:
    """T917 正式采样的统一前置：两把锁都必须过，任一漂移 fail-closed。

    1. **归档完整性锁（T916）**：``formal_freeze.verify_archive()`` 逐文件核对
       freeze-manifest、protocol.json、assignments.json、预注册与分析代码哈希，
       并确认 assignments 绑定的正是归档协议哈希——分配表确实是那一份冻结协议
       签发的。
    2. **合同级漂移锁**：``evidence_guard.admit`` 内部对照的是
       ``freeze(draft_from_contract())`` 的**基础协议哈希**——它挡的是"双轨合同
       在冻结后被改动"这类漂移。基础哈希与归档哈希是两个不同层的对象
       （归档协议 = 基础协议 + 预注册/机制/分配计划扩展），各自验各自的锁。
    3. **首样本时间门**：归档声明的 ``first_formal_sample_allowed_after`` 未到
       不允许开跑。

    任何一处不过都抛异常；调用方必须在跑第一个正式样本**之前**调用本函数。
    """
    from datetime import UTC, datetime

    from market_game_sim.experiment.h2 import formal_freeze, protocol

    manifest = formal_freeze.verify_archive()
    table = table or load_assignments()
    if table["protocol_hash"] != manifest["protocol_hash"]:
        raise ValueError(
            "分配表协议哈希与冻结归档不一致："
            f"{table['protocol_hash']} != {manifest['protocol_hash']}"
        )
    allowed_after = manifest["first_formal_sample_allowed_after"]
    if datetime.now(UTC) < datetime.fromisoformat(allowed_after):
        raise ValueError(f"冻结门未开：首个正式样本须晚于 {allowed_after}")
    contract_hash = protocol.freeze(protocol.draft_from_contract()).protocol_hash
    return {
        "archive_protocol_hash": table["protocol_hash"],
        "contract_protocol_hash": contract_hash,
        "first_formal_sample_allowed_after": allowed_after,
    }
