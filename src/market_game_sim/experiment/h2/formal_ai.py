"""T917 AI 轨正式采样：按冻结分配表顺序跑 168 个配对 block。

纪律全部来自冻结对象，本模块不持有任何研究参数：

* **顺序与 seed**：``assignments.json`` 的 ``ai_assignments``（order_index 0..167，
  seed 50000..50167）——补跑走 T914 的备用池流程，不在这里。
* **配对合同**：``runner.run_ai_block`` + ``runner.validate_pair``（T907）。
* **准入**：每 block 过 ``evidence_guard.admit`` 五把锁（协议哈希漂移即 fail
  closed），拒绝路径零落盘。
* **断点续跑**：按工件存在性跳过已完成 block——正式采样可能跨天分批，重启
  不重打。工件只存配对校验与事件流摘要，分析（T919）从冻结 seed 确定性重放。
* **内存**：一次只持一个 block——0.1.5 重跑的教训（ADR-005 观察项）：全量
  批跑在事件流序列化上会 MemoryError，这里从结构上不允许积累。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from market_game_sim.experiment.h2 import artifacts, evidence_guard, runner
from market_game_sim.experiment.h2.artifacts import canonical_digest, write_json_atomic

AI_TRACK = evidence_guard.AI_TRACK


def block_artifact_path(out_dir: Path, order_index: int, seed: int) -> Path:
    return out_dir / f"block-{order_index:03d}-seed-{seed}.json"


def sample_ai_blocks(
    *,
    count: int,
    out_dir: Path | None = None,
    assignments: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """按冻结顺序采样至多 ``count`` 个未完成的 AI block，返回本轮工件列表。

    ``count`` 是分批的批量，不是样本量——总量由冻结分配表（168）拥有，跑完
    即自然停止。协议哈希漂移或配对违约会让当轮直接抛错，绝不带病落盘。
    """
    table = assignments or artifacts.load_assignments()
    target_dir = out_dir or artifacts.DEFAULT_FORMAL_ROOT / "ai"
    target_dir.mkdir(parents=True, exist_ok=True)

    bindings = artifacts.verify_formal_bindings(table)
    written: list[dict[str, Any]] = []
    for entry in table["ai_assignments"]:
        if len(written) >= count:
            break
        order_index = int(entry["order_index"])
        seed = int(entry["seed"])
        path = block_artifact_path(target_dir, order_index, seed)
        if path.exists():
            continue

        block = runner.run_ai_block(seed)
        report = runner.validate_pair(block)
        payload = {
            "schema_version": 1,
            "run_mode": AI_TRACK,
            "evidence_class": "formal-research",
            "stage": "formal",
            "assignment_id": entry["assignment_id"],
            "order_index": order_index,
            "seed": seed,
            "protocol_hash": table["protocol_hash"],
            "contract_protocol_hash": bindings["contract_protocol_hash"],
            "pair": {
                "identical_fields": sorted(report.identical_fields),
                "disclosed_differences": {
                    key: list(value) for key, value in report.disclosed_differences.items()
                },
            },
            "runs": [
                {
                    "arm": item.arm,
                    "policy_id": item.policy_id,
                    "terminated": item.result.terminated,
                    "abort_code": item.result.abort_code,
                    "events_sha256": canonical_digest(item.result.events),
                    "book_last_ticks": item.result.book_last_ticks,
                }
                for item in block.runs
            ],
        }
        # 准入在落盘前：五把锁任一不过就抛异常，临时文件都不会出现。
        # protocol_hash 传合同级基础哈希（guard 校验的就是这一层）；归档绑定
        # 由上面的 verify_formal_bindings 拥有。
        evidence_guard.admit(
            run_mode=AI_TRACK,
            stage="formal",
            protocol_hash=bindings["contract_protocol_hash"],
            pair_complete=True,
        )
        write_json_atomic(path, payload)
        written.append(payload)
    return written


def completed_block_count(out_dir: Path | None = None) -> int:
    """已完成（工件在盘）的 block 数——停止规则的检查依据。"""
    target_dir = out_dir or artifacts.DEFAULT_FORMAL_ROOT / "ai"
    if not target_dir.exists():
        return 0
    return sum(1 for path in sorted(target_dir.glob("block-*.json")))
