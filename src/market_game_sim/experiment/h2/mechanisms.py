"""T913：机制指标计算、因果追溯与缺失语义（FR-305 / TR-302 / AC-306）。

三类机制口径（激进订单、流动性撤回、风险减仓）的**唯一权威定义**在
``docs/research/metrics-dictionary.md`` §8——本文件只引用那份文档的版本号与指标 ID，
不在这里另写一套公式（design.md 的明文要求）。

计算不依赖决策来源是所有者还是策略：``decision_event_id`` 到订单、成交、撤单的因果
外键回溯对两者用的是同一套事件 schema，T917 接入真实所有者事件时复用本模块，不必
另写一套。因果链校验复用既有的
``evidence/chain_verifier.py``（同一份闭包逻辑用于强平连锁审计与 KPI-006 追溯链，
不重复实现一遍）。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from market_game_sim.evidence.chain_verifier import (
    ChainVerificationError,
    verify_decision_evidence_chain,
)

#: 与 metrics-dictionary.md 头部「文档版本」保持一致；那份文档改了这里必须跟着改，
#: 反之亦然——两者只能有一个唯一真源，本文件的字符串是对它的引用，不是独立定义。
METRICS_DICTIONARY_VERSION = "0.2.0"
METRICS_DICTIONARY_PATH = "docs/research/metrics-dictionary.md"

MECHANISMS: tuple[str, ...] = ("aggressive_orders", "liquidity_withdrawal", "risk_reduction")

#: 三类机制的 ID/公式/单位/窗口——与 metrics-dictionary.md §8 表格逐字对应。
_DEFINITIONS: dict[str, dict[str, str]] = {
    "aggressive_orders": {
        "metric_id": "H2-M-001",
        "formula": (
            "该决策 SUBMIT 订单引发的 TRADE_SETTLE 中，该决策代理一侧 "
            "postings[].role=TAKER 的 |position_delta_units| 之和"
        ),
        "unit": "quantity_units",
        "window": "该决策的 AGENT_DECIDE 到其全部因果后续事件在日志序上结算完毕",
    },
    "liquidity_withdrawal": {
        "metric_id": "H2-M-002",
        "formula": (
            "该决策 CANCEL 指令触发的 ORDER_CANCELLED（reason=AGENT_REQUEST）的 "
            "cancelled_qty_units 之和"
        ),
        "unit": "quantity_units",
        "window": "同上",
    },
    "risk_reduction": {
        "metric_id": "H2-M-003",
        "formula": (
            "abs(position_before) - abs(position_after)；"
            "position_after = position_before + Σ position_delta_units（该决策自身成交）"
        ),
        "unit": "position_units",
        "window": "同上",
    },
}


class MechanismsError(RuntimeError):
    """机制指标合同被违反。"""


class CausalChainBroken(MechanismsError):
    """机制值依赖的事件链缺失或断裂——按冻结规则标记缺失，不推断补值（AC-306）。"""


@dataclass(frozen=True, slots=True)
class MechanismDefinition:
    """一个机制指标的权威定义，只引用指标字典的版本与 ID。"""

    name: str
    metric_id: str
    formula: str
    unit: str
    window: str
    dictionary_version: str
    formula_source: str


def definition(name: str) -> MechanismDefinition:
    if name not in _DEFINITIONS:
        raise MechanismsError(f"未知机制指标：{name!r}，合法值为 {MECHANISMS}")
    entry = _DEFINITIONS[name]
    return MechanismDefinition(
        name=name,
        metric_id=entry["metric_id"],
        formula=entry["formula"],
        unit=entry["unit"],
        window=entry["window"],
        dictionary_version=METRICS_DICTIONARY_VERSION,
        formula_source=METRICS_DICTIONARY_PATH,
    )


@dataclass(frozen=True, slots=True)
class MechanismValue:
    """一次决策在一个机制指标上的取值。

    ``is_missing`` 与 ``value == 0`` 严格区分（metrics-dictionary.md §8 的缺失语义
    条款）：0 是"这次决策没有产生该行为"的真实观测，缺失是"无法判定"。
    """

    mechanism: str
    decision_event_id: str
    value: float | None
    is_missing: bool
    imputed: bool
    evidence_event_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MechanismRow:
    """``build_table()`` 的一行：一个决策 × 三个机制，带可追溯性字段（TR-302）。"""

    decision_event_id: str
    agent_id: str
    input_seq: int
    intent_id: str | None
    values: dict[str, MechanismValue]

    @property
    def evidence_event_ids(self) -> tuple[str, ...]:
        seen: list[str] = []
        for value in self.values.values():
            for eid in value.evidence_event_ids:
                if eid not in seen:
                    seen.append(eid)
        return tuple(seen)


def _log_key(event: dict) -> tuple[int, int, int]:
    return (event["timestamp"], event["transaction_seq"], event["record_index"])


def _index_by_id(events: Sequence[dict]) -> dict[str, dict]:
    return {e["event_id"]: e for e in events if e.get("event_id")}


def _orders_for_decision(events: Sequence[dict], decision_event_id: str) -> list[dict]:
    return [
        e
        for e in events
        if e.get("event_type") == "ORDER_ARRIVAL"
        and e.get("decision_event_id") == decision_event_id
    ]


def _aggressive_orders(
    events: Sequence[dict], decision_event_id: str, agent_id: str, submit_ids: set[str]
) -> MechanismValue:
    total = 0
    evidence: list[str] = []
    for e in events:
        if e.get("event_type") != "TRADE_SETTLE":
            continue
        if e.get("caused_by_event_id") not in submit_ids:
            continue
        for posting in e.get("postings", []):
            if posting.get("agent_id") == agent_id and posting.get("role") == "TAKER":
                total += abs(posting.get("position_delta_units", 0))
                evidence.append(e["event_id"])
    return MechanismValue(
        "aggressive_orders", decision_event_id, float(total), False, False, tuple(evidence)
    )


def _liquidity_withdrawal(
    events: Sequence[dict], decision_event_id: str, cancel_ids: set[str]
) -> MechanismValue:
    total = 0
    evidence: list[str] = []
    for e in events:
        if e.get("event_type") != "ORDER_CANCELLED":
            continue
        if e.get("reason") != "AGENT_REQUEST":
            continue
        if e.get("caused_by_event_id") not in cancel_ids:
            continue
        total += e.get("cancelled_qty_units", 0)
        evidence.append(e["event_id"])
    return MechanismValue(
        "liquidity_withdrawal", decision_event_id, float(total), False, False, tuple(evidence)
    )


def _risk_reduction(
    events: Sequence[dict], decision_event_id: str, agent_id: str, submit_ids: set[str]
) -> MechanismValue:
    own_trades: list[tuple[tuple[int, int, int], int, str]] = []
    for e in events:
        if e.get("event_type") != "TRADE_SETTLE":
            continue
        if e.get("caused_by_event_id") not in submit_ids:
            continue
        for posting in e.get("postings", []):
            if (
                posting.get("agent_id") == agent_id
                and posting.get("posting_type") == "TRADE_POSTING"
            ):
                own_trades.append(
                    (_log_key(e), posting.get("position_delta_units", 0), e["event_id"])
                )

    if not own_trades:
        # 决策没有产生任何成交：仓位不变，恒为 0——真实观测，不是缺失。
        return MechanismValue("risk_reduction", decision_event_id, 0.0, False, False, ())

    earliest_key = min(key for key, _, _ in own_trades)
    position_before = 0
    for e in events:
        if e.get("event_type") != "TRADE_SETTLE":
            continue
        key = _log_key(e)
        if key >= earliest_key:
            continue
        for posting in e.get("postings", []):
            if (
                posting.get("agent_id") == agent_id
                and posting.get("posting_type") == "TRADE_POSTING"
            ):
                position_before += posting.get("position_delta_units", 0)

    delta = sum(d for _, d, _ in own_trades)
    position_after = position_before + delta
    value = float(abs(position_before) - abs(position_after))
    evidence = tuple(eid for _, _, eid in own_trades)
    return MechanismValue("risk_reduction", decision_event_id, value, False, False, evidence)


def compute(events: Sequence[dict], mechanism: str, decision_event_id: str) -> MechanismValue:
    """从事件链计算一个决策的一项机制值。

    **只有决策事件本身无法解析**时才标记缺失（AC-306 的反面用例）；决策已解析但
    没有产生任何订单（代理选择不动作）是一个**真实的零观测**，不是缺失——两者的
    区别正是 metrics-dictionary.md §8 缺失语义条款要锁定的东西，不推断也不补值，
    但也不能把"确定没有"错记成"不知道"。
    """
    if mechanism not in MECHANISMS:
        raise MechanismsError(f"未知机制指标：{mechanism!r}，合法值为 {MECHANISMS}")

    by_id = _index_by_id(events)
    decision = by_id.get(decision_event_id)
    if decision is None or decision.get("event_type") != "AGENT_DECIDE":
        return MechanismValue(mechanism, decision_event_id, None, True, False, ())

    orders = _orders_for_decision(events, decision_event_id)
    agent_id = decision.get("agent_id")
    submit_ids = {o["event_id"] for o in orders if o.get("action") == "SUBMIT"}
    cancel_ids = {o["event_id"] for o in orders if o.get("action") == "CANCEL"}

    if mechanism == "aggressive_orders":
        if not submit_ids:
            return MechanismValue(mechanism, decision_event_id, 0.0, False, False, ())
        return _aggressive_orders(events, decision_event_id, agent_id, submit_ids)
    if mechanism == "liquidity_withdrawal":
        if not cancel_ids:
            return MechanismValue(mechanism, decision_event_id, 0.0, False, False, ())
        return _liquidity_withdrawal(events, decision_event_id, cancel_ids)
    if not submit_ids:
        return MechanismValue(mechanism, decision_event_id, 0.0, False, False, ())
    return _risk_reduction(events, decision_event_id, agent_id, submit_ids)


def sample_without_decision_event() -> tuple[list[dict], str]:
    """构造一份不含目标决策事件的最小事件列表，用于测试缺失路径。"""
    events = [
        {
            "event_type": "ORDER_ARRIVAL",
            "event_id": "e1_0",
            "agent_id": "belief-0",
            "action": "SUBMIT",
            "decision_event_id": "e0_0",  # 指向一个从未出现在日志里的决策
            "timestamp": 0,
            "transaction_seq": 1,
            "record_index": 0,
        }
    ]
    return events, "e0_0"


def build_table(events: Sequence[dict], *, agent_id: str) -> tuple[MechanismRow, ...]:
    """从完整事件链构建一个代理的机制表：每个决策一行，三个机制各一列。

    先跑既有的 ``verify_decision_evidence_chain``（同一套闭包校验强平连锁审计与
    KPI-006 追溯链复用的那套）；链路断裂时不产出任何部分结果，原样转译为
    ``CausalChainBroken``——机制表不能建立在一份自身已知损坏的日志上。
    """
    try:
        verify_decision_evidence_chain(events)
    except ChainVerificationError as exc:
        raise CausalChainBroken(str(exc)) from exc

    decisions = [
        e for e in events if e.get("event_type") == "AGENT_DECIDE" and e.get("agent_id") == agent_id
    ]
    decisions.sort(key=_log_key)

    rows: list[MechanismRow] = []
    for decision in decisions:
        decision_id = decision["event_id"]
        orders = _orders_for_decision(events, decision_id)
        intent_id = orders[0].get("intent_id") if orders else None
        values = {mechanism: compute(events, mechanism, decision_id) for mechanism in MECHANISMS}
        rows.append(
            MechanismRow(
                decision_event_id=decision_id,
                agent_id=agent_id,
                input_seq=len(rows),
                intent_id=intent_id,
                values=values,
            )
        )
    return tuple(rows)


def build_table_from_result(result: Any, *, agent_id: str) -> tuple[MechanismRow, ...]:
    """便捷入口：直接从 ``RunResult`` 构建机制表。"""
    return build_table(result.events, agent_id=agent_id)
