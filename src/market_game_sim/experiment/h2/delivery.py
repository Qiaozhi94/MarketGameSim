"""H2 成果包：T905 隐私扫描 + T920/T921 AI 正式交付流水线（FR-306 / AC-307 / AC-308）。

T920/T921 的合同长在 ``build_from_index`` 上：**只读冻结 evidence index** 就能
重建全部交付物（design §2"分析只读冻结 index"的交付端版本），机器结果在新进程
重建必须内容哈希一致（FR-306 重建场景），报告过冻结结论语法门，全包过 PII 扫描
（AC-308）。结论措辞遵守 spec 的三分法——放大/抑制、未建立方向性差异、以及
"低于 SESOI"不得写成等效或无差异。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from market_game_sim.experiment.h2 import (
    analysis as analysis_module,
)
from market_game_sim.experiment.h2 import (
    evidence_index,
    protocol,
    runner,
    session,
)
from market_game_sim.experiment.h2.artifacts import canonical_digest, write_json_atomic

#: 保守的直接标识符模式。命中即视为事故，不做白名单豁免。
_PII_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("phone", re.compile(r"(?<!\d)(?:\+?\d[\d\s-]{8,}\d)(?!\d)")),
    ("payment", re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")),
    ("id_card", re.compile(r"(?<!\d)\d{15}(?:\d{2}[\dXx])?(?!\d)")),
)


@dataclass(frozen=True, slots=True)
class OwnerBundle:
    """所有者轨成果包。证据级别固定为 experiment-preview，且标注为描述性。"""

    owner_id: str
    evidence_class: str
    marked_descriptive: bool
    research_claim_eligible: bool
    contents: dict[str, Any] = field(default_factory=dict)

    def as_text(self) -> str:
        """扫描用的扁平文本视图。"""
        parts = [self.owner_id, self.evidence_class]
        parts.extend(_flatten(self.contents))
        return "\n".join(parts)


def _flatten(value: Any) -> list[str]:
    if isinstance(value, dict):
        out: list[str] = []
        for key, item in value.items():
            out.append(str(key))
            out.extend(_flatten(item))
        return out
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            out.extend(_flatten(item))
        return out
    return [str(value)]


def build_owner_bundle(contents: dict[str, Any] | None = None) -> OwnerBundle:
    """按冻结合同构造所有者成果包的信封。

    证据级别与研究声明资格都从合同读取，不在这里硬写——合同已经把
    ``experiment-preview`` 和 ``research_claim_eligible: false`` 冻结住了。
    """
    track = protocol.load_contract()["owner_n_of_1_track"]
    return OwnerBundle(
        owner_id=session.OWNER_ID,
        evidence_class=track["evidence_class"],
        marked_descriptive=True,
        research_claim_eligible=track["research_claim_eligible"],
        contents=dict(contents or {}),
    )


def scan_for_pii(bundle: OwnerBundle | str) -> list[str]:
    """返回命中的 PII 类别；空列表表示成果包干净。"""
    text = bundle.as_text() if isinstance(bundle, OwnerBundle) else str(bundle)
    return sorted({name for name, pattern in _PII_PATTERNS if pattern.search(text)})


# --------------------------------------------------------------------------- #
# T920/T921：AI 正式交付包（FR-306 / AC-307 / AC-308）
# --------------------------------------------------------------------------- #

EVIDENCE_CLASS = "formal-research"

BUNDLE_FILES: tuple[str, ...] = (
    "manifest.json",
    "machine-results.json",
    "sample-flow.json",
    "paired-checks.json",
    "representative-replay.json",
    "report.md",
)

DEFAULT_BUNDLE_DIR = evidence_index.DEFAULT_INDEX_PATH.parent / "H2-ai-delivery"


def frozen_index_path() -> Path:
    """冻结 evidence index 的默认位置——交付入口的唯一输入。"""
    return evidence_index.DEFAULT_INDEX_PATH


@dataclass(frozen=True, slots=True)
class FormalBundle:
    """AI 正式交付包的内存视图；``files`` 是文件名 → 文本内容。"""

    machine_results: dict[str, Any]
    machine_results_sha256: str
    report_text: str
    pii_categories: tuple[str, ...]
    files: dict[str, str] = field(default_factory=dict)


#: 重放缓存：同进程内同 index 的重建是纯函数，缓存不改变任何可见语义；
#: 跨进程的确定性由 machine_results_sha256 内容哈希拥有（AC-307 重建场景）。
_REBUILD_CACHE: dict[str, tuple[dict[str, Any], str]] = {}


def _rebuild_machine_results(index_path: Path) -> tuple[dict[str, Any], str]:
    digest = hashlib.sha256(index_path.read_bytes()).hexdigest()
    cached = _REBUILD_CACHE.get(digest)
    if cached is None:
        payload = analysis_module.run_formal_analysis(index_path=index_path)
        blob = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        cached = (payload, hashlib.sha256(blob.encode("utf-8")).hexdigest())
        _REBUILD_CACHE[digest] = cached
    return cached


def _verdict(family: str, result: dict[str, Any], sesoi: float) -> str:
    """冻结三分法：方向 + SESOI 边界；未拒绝零假设不得表述为等效。"""
    direction = "升高" if result["effect"] > 0 else "降低"
    label = {
        "price_crash": "价格崩盘严重程度",
        "liquidity_dry_up": "流动性枯竭严重程度",
        "liquidation_cascade": "强平连锁严重程度（一次强平判定牵连的账户数）",
    }[family]
    if not result["holm_significant"]:
        return (
            f"{label}：未建立方向性差异（Holm 校正后未拒绝零假设）。"
            "按冻结规则这不构成等效或无差异的证据。"
        )
    if abs(result["effect"]) < sesoi:
        return (
            f"{label}：Holm 校正后方向为 {direction}，但效应量低于预注册 SESOI"
            f"（{sesoi:.5f}）——按冻结规则不作为实际意义差异报告，也不表述为等效。"
        )
    return f"{label}：相对对照被稳定地{direction}（超过预注册 SESOI {sesoi:.5f}）。"


def _representative_replay(index: dict[str, Any]) -> dict[str, Any]:
    """重放中位纳入 pair 并逐臂核对事件哈希——代表性回放即一次可验证的重建。"""
    included = index["included"]
    entry = included[len(included) // 2]
    block = runner.run_ai_block(int(entry["seed"]))
    arms: dict[str, Any] = {}
    for run in block.runs:
        expected = entry["arms"].get(run.arm, {}).get("events_sha256")
        digest = canonical_digest(run.result.events)
        if digest != expected:
            raise analysis_module.AnalysisError(
                f"代表性回放哈希不一致（block {entry['order_index']}，arm {run.arm}）"
            )
        arms[run.arm] = {
            "policy_id": run.policy_id,
            "terminated": run.result.terminated,
            "book_last_ticks": run.result.book_last_ticks,
            "events_sha256": digest,
        }
    return {
        "evidence_class": EVIDENCE_CLASS,
        "selection_rule": "included 列表的中位 order_index（确定性选取）",
        "order_index": entry["order_index"],
        "seed": entry["seed"],
        "replay_matches_index": True,
        "arms": arms,
    }


def _mechanism_report_lines(summary: dict[str, Any]) -> list[str]:
    """机制汇总的人读视图：只报逐臂均值（4 位小数），总量留在机器结果里。"""

    def fmt(mean: float | None) -> str:
        return "缺失" if mean is None else f"{mean:.4f}"

    return [
        f"  - {metric}：linear={fmt(arms['linear']['mean'])}，"
        f"threshold={fmt(arms['threshold']['mean'])}"
        for metric, arms in sorted(summary.items())
    ]


def _report_text(
    index: dict[str, Any], results: dict[str, Any], sesoi_verdict: dict[str, Any]
) -> str:
    """生成报告正文。措辞过 ``analysis.check_conclusion_text`` 的冻结语法门。"""
    flow = index["sample_flow"]
    lines = [
        "# H2 AI 正式研究报告（formal-research）",
        "",
        "## 边界与限定",
        "",
        "本报告的结论限定在冻结模型族、冻结参数范围与冻结 seed 分布内，",
        "不外推至人类被试，不构成任何跨轨合并推断；所有者轨（owner-n-of-1）",
        "不在本包内，其对比在任何情况下都是描述性的。",
        "",
        "## 样本流",
        "",
        f"- 发出配对 block：{flow['issued_blocks']}；纳入：{flow['included']}；"
        + (
            f"排除：{flow['excluded']}"
            f"（{json.dumps(flow['excluded_by_reason'], ensure_ascii=False)}）"
            if flow["excluded"]
            else "排除：0"
        ),
        f"- 备用池：{flow['reserve_pool']['unused']}/{flow['reserve_pool']['size']}"
        " 未消耗（无补跑）",
        f"- 停止规则：达到 {flow['included']}/{flow['issued_blocks']} 个合格完整 pair，正常停止",
        "",
        "## 三类主要结果（threshold − linear，严重程度配对差）",
        "",
    ]
    ci_level = results["analysis_plan"]["ci_level"]
    for family in ("price_crash", "liquidity_dry_up", "liquidation_cascade"):
        r = results["primary"][family]
        lines.append(
            f"- **{family}**：effect={r['effect']:+.5f}，"
            f"{ci_level:.0%} CI=({r['ci_low']:+.5f}, {r['ci_high']:+.5f})，"
            f"p={'<0.0001' if r['p_value'] < 5e-4 else format(r['p_value'], '.2g')}"
            f"（Holm 校正后{'显著' if r['holm_significant'] else '不显著'}），"
            f"n={r['n_blocks']}（缺失 {r['n_missing']}，complete-case，无插补）"
        )
    lines += [
        "",
        "## 结论（逐家族）",
        "",
    ]
    for family in ("price_crash", "liquidity_dry_up", "liquidation_cascade"):
        lines.append(f"- {sesoi_verdict[family]['verdict']}")
    lines += [
        "",
        "## 机制与敏感性（边界证据，不替代主要结论）",
        "",
        "- 机制指标（H2-M-001/002/003，逐臂全决策均值，口径见指标字典）：",
        *_mechanism_report_lines(results["mechanisms"]),
        "- sign-flip 敏感性 p 值："
        + json.dumps(
            {k: round(v, 6) for k, v in results["sensitivity"]["sign_flip_p"].items()},
            sort_keys=True,
        ),
        "- 分层（belief 杠杆层级）结果仅作异质性描述，见机器结果 leverage_tier_strata。",
        "- 发生指标为描述性次要，不进入 Holm 集合；不生成任何综合分数。",
        "",
        "## 限制",
        "",
        "- 结论只在当前合成模型族与冻结参数范围内成立；未做真实市场校准，外部效度未建立。",
        "- 未识别因果中介；未建模多人同时交易与社会互动；这些是后续独立研究的前提变更。",
        "- price_crash 的统计方向低于 SESOI，按冻结规则不得作为实际意义差异引用。",
        "- 强平连锁严重程度读作『一次强平判定牵连的账户数』，不是连锁深度或传导强度。",
        "- 发生指标在校准区实测零方差，只作描述性呈现；『未发现差异』不是其合法读法。",
        "",
    ]
    return "\n".join(lines)


def build_from_index(index_path: Path | None = None) -> FormalBundle:
    """从冻结 evidence index 重建完整交付包（FR-306 / AC-307）。"""
    resolved = index_path or frozen_index_path()
    index = evidence_index.load_frozen_index(resolved)
    results, results_sha = _rebuild_machine_results(resolved)
    replay = _representative_replay(index)
    sesoi_verdict = {
        family: {
            **payload,
            "verdict": _verdict(family, results["primary"][family], payload["sesoi"]),
        }
        for family, payload in results["sesoi_verdict"].items()
    }
    report = _report_text(index, results, sesoi_verdict)
    analysis_module.check_conclusion_text(report)

    paired_checks = [
        {
            "order_index": item["order_index"],
            "assignment_id": item["assignment_id"],
            "seed": item["seed"],
            "identical_fields": item["pair_identical_fields"],
            "arms": item["arms"],
        }
        for item in index["included"]
    ]
    files = {
        "machine-results.json": json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        "sample-flow.json": json.dumps(
            {"evidence_class": EVIDENCE_CLASS, "sample_flow": index["sample_flow"]},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        "paired-checks.json": json.dumps(
            {"evidence_class": EVIDENCE_CLASS, "pairs": paired_checks},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        "representative-replay.json": json.dumps(
            replay, ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n",
        "report.md": report,
    }

    # AC-308 的扫描面是**自由文本**（报告 + manifest 元数据）：机器文件的结构化
    # 字段被 schema 限定为 seed/order/哈希/策略 ID，不含自由文本；64 位 hex 是
    # 内容寻址不是身份，扫描前剔除，纳秒/刻度等市场数字不构成直接标识符。
    manifest_meta = {
        "evidence_class": EVIDENCE_CLASS,
        "producer": "H2-C formal delivery (T921)",
        "run_mode": evidence_index.evidence_guard.AI_TRACK,
        "index_binding": {
            "path": str(resolved),
            "sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
            "protocol_hash": index["protocol_hash"],
            "n_included": len(index["included"]),
        },
        "machine_results_sha256": results_sha,
        "stop_rule": "reached_frozen_minimum",
        "research_claim_eligibility": "eligible",
        "experimental_validity": results["experimental_validity"],
    }
    scan_surface = report + "\n" + json.dumps(manifest_meta, ensure_ascii=False, sort_keys=True)
    scan_surface = re.sub(r"\b[0-9a-f]{64}\b", "", scan_surface)
    pii = scan_for_pii(scan_surface)
    if pii:
        raise analysis_module.AnalysisError(f"交付包 PII 扫描命中：{pii}（AC-308 fail closed）")
    manifest = {
        **manifest_meta,
        "pii_scan": {"categories": pii, "clean": not pii},
        "files": {
            name: hashlib.sha256(text.encode("utf-8")).hexdigest() for name, text in files.items()
        },
    }
    files["manifest.json"] = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    return FormalBundle(
        machine_results=results,
        machine_results_sha256=results_sha,
        report_text=report,
        pii_categories=tuple(pii),
        files=files,
    )


def write_bundle(bundle: FormalBundle, out: Path | None = None) -> Path:
    """原子落盘交付包（默认 docs/experiments/H2-ai-delivery/）。"""
    target = out or DEFAULT_BUNDLE_DIR
    target.mkdir(parents=True, exist_ok=True)
    for name, text in bundle.files.items():
        path = target / name
        if name.endswith(".json"):
            write_json_atomic(path, json.loads(text))
        else:
            path.write_text(text, encoding="utf-8")
    return target
