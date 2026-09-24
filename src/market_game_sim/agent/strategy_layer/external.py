"""0.4.1 T975/T976 (FR-504 / IR-502 / TR-501 / AC-507): 外部信号注入接口。

量化交易者族的决策来自**内核之外**的信号源（Alpha101 纯时序子集、将来的 alphamill
产出）。本模块把一个信号源包装成 ``world["external_decision_sources"]`` 缝隙要的可调用
对象，使这类委托与其他族走**完全相同**的撮合、账本与风控路径（FR-504）。

三条硬约束，都是 IR-502 的字面要求：

* **非阻塞**：源必须立刻返回。信号缺失、过期、非法、版本不匹配时**降级为不动作**并带
  稳定原因码，**不得阻塞内核**——所有者轨那种「内核在事务内等真人 8 秒」的阻塞式用法
  是它自己的实现（`owner_client`），不是本接口的语义，两者共存互不影响；
* **不新增事件类型**：决策仍写进既有 `AGENT_DECIDE`，信号来源与版本记在 `internal_state`
  里（TR-501），委托仍由 `intent_id` / `decision_event_id` 连入既有因果链；
* **沙盘边界**：本接口只消费外部信号，**不回流**任何沙盘结果（ADR-011 §决策 5）。

降级原因码是闭集，写进决策记录，便于事后分辨「策略没信号」与「信号通道坏了」：
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from market_game_sim.agent.strategy_layer.protocol import ExternalSignal, StrategyLayerError

#: 信号通道未给出任何值（源返回 None）。
SIGNAL_MISSING = "SIGNAL_MISSING"
#: 信号比本次决策旧超过 ``max_age_ns``——过期信号不得驱动委托。
SIGNAL_STALE = "SIGNAL_STALE"
#: 信号结构非法（缺字段、类型错、方向/数量不合法）。
SIGNAL_INVALID = "SIGNAL_INVALID"
#: 信号版本不在装配声明的允许集合内。
SIGNAL_VERSION_MISMATCH = "SIGNAL_VERSION_MISMATCH"
#: 源正常返回，但该信号本身就是「不交易」。
SIGNAL_NO_ACTION = "SIGNAL_NO_ACTION"

DEGRADE_REASONS = frozenset(
    {
        SIGNAL_MISSING,
        SIGNAL_STALE,
        SIGNAL_INVALID,
        SIGNAL_VERSION_MISMATCH,
        SIGNAL_NO_ACTION,
    }
)

SIDES = frozenset({"BUY", "SELL"})
ORDER_TYPES = frozenset({"MARKET", "LIMIT"})

#: 信号源：给定 ``(agent_id, timestamp_ns)`` **立刻**返回一个信号或 ``None``。
SignalFetch = Callable[[str, int], "TimedSignal | None"]


@dataclass(frozen=True)
class TimedSignal:
    """一个带产生时刻的外部信号。

    ``signal`` 携带 ``source_id`` / ``signal_version``（TR-501 的追溯字段），
    ``produced_at_ns`` 用于判定过期——用信号自己的时刻而不是取用时刻，否则一个
    卡住的源会永远看起来是新鲜的。
    """

    signal: ExternalSignal
    produced_at_ns: int
    intent: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.signal, ExternalSignal):
            raise StrategyLayerError("INVALID_SIGNAL", "signal must be an ExternalSignal")
        if type(self.produced_at_ns) is not int:
            raise StrategyLayerError("INVALID_SIGNAL", "produced_at_ns must be an int")


def _degraded(reason: str, signal: ExternalSignal | None) -> dict[str, Any]:
    out: dict[str, Any] = {"kind": "NO_ACTION", "reason_code": reason}
    if signal is not None:
        out["signal"] = {
            "source_id": signal.source_id,
            "signal_version": signal.signal_version,
        }
    return out


def _validated_intent(
    intent: Mapping[str, Any], *, agent_id: str, decision_index: int
) -> dict[str, Any] | None:
    """把信号携带的委托意图规范化；任何不合法处返回 ``None``（由调用方降级）。"""
    order_type = intent.get("order_type", "MARKET")
    side = intent.get("side")
    quantity = intent.get("quantity_units")
    price = intent.get("price_ticks")
    if side not in SIDES or order_type not in ORDER_TYPES:
        return None
    if type(quantity) is not int or quantity <= 0:
        return None
    if order_type == "LIMIT":
        if type(price) is not int or price <= 0:
            return None
    elif price is not None:
        return None  # MARKET 带价格是矛盾的意图，不猜测
    return {
        "kind": order_type,
        "side": side,
        "quantity_units": quantity,
        "price_ticks": price if order_type == "LIMIT" else None,
        "intent_id": intent.get("intent_id") or f"{agent_id}-ext{decision_index}",
    }


def signal_decision_source(
    fetch: SignalFetch,
    *,
    allowed_versions: frozenset[str] | set[str] | None = None,
    max_age_ns: int | None = None,
) -> Callable[[dict, dict], dict[str, Any]]:
    """把信号源包装成 ``external_decision_sources`` 缝隙要的决策回调。

    返回的回调**永不抛异常、永不阻塞**：源自身抛错也被收敛成
    ``SIGNAL_INVALID`` 降级——一个坏掉的外部通道不能让整个内核停摆（IR-502）。
    """

    def decide(event: dict, world: dict) -> dict[str, Any]:
        agent_id = event.get("agent_id", "")
        decision_index = event.get("_decision_index", 0)
        now_ns = int(event.get("timestamp", 0))
        try:
            timed = fetch(agent_id, now_ns)
        except Exception:  # 源是外部代码：它的故障不得成为内核的故障
            return _degraded(SIGNAL_INVALID, None)
        if timed is None:
            return _degraded(SIGNAL_MISSING, None)
        if not isinstance(timed, TimedSignal):
            return _degraded(SIGNAL_INVALID, None)
        signal = timed.signal
        if allowed_versions is not None and signal.signal_version not in allowed_versions:
            return _degraded(SIGNAL_VERSION_MISMATCH, signal)
        if max_age_ns is not None and now_ns - timed.produced_at_ns > max_age_ns:
            return _degraded(SIGNAL_STALE, signal)
        if timed.intent is None:
            return _degraded(SIGNAL_NO_ACTION, signal)
        intent = _validated_intent(timed.intent, agent_id=agent_id, decision_index=decision_index)
        if intent is None:
            return _degraded(SIGNAL_INVALID, signal)
        intent["signal"] = {
            "source_id": signal.source_id,
            "signal_version": signal.signal_version,
        }
        return intent

    return decide


#: T977（NFR-503 / AC-508）：量化族产物必须携带的单向边界声明。写成常量而不是
#: 每处即兴措辞——它是 ADR-011 §决策 5 的执行面，不是文案。
ONE_WAY_BOUNDARY = {
    "evidence_class": "engineering-demonstration",
    "not_strategy_evidence": (
        "沙盘内的盈亏、胜率、回撤不构成任何策略有效性的证据：合成市场没有真实市场的"
        "微观结构，用它给实盘策略背书会污染 alphamill 的「可信 Alpha」判据"
    ),
    "no_backflow_to_alphamill": (
        "本产物及其任何派生量不得进入 alphamill 的证据链；反向亦然——alphamill 的历史"
        "回测表现不构成该策略在本沙盘中行为的预期（ADR-011 §决策 5，单向消费）"
    ),
    "not_in_evidence_index": ("本产物不进入任何 evidence index，不建立研究声明（spec NFR-503）"),
}

#: 禁止出现在量化族产物里的字段名：它们会让沙盘结果看起来像策略有效性证据。
FORBIDDEN_PERFORMANCE_FIELDS = frozenset(
    {"sharpe", "win_rate", "pnl", "alpha_score", "backtest_return", "max_drawdown"}
)


def boundary_declaration() -> dict[str, str]:
    """单向边界声明的副本（调用方写进自己的 artifact 顶层）。"""
    return dict(ONE_WAY_BOUNDARY)


def check_artifact_boundary(payload: Mapping[str, Any]) -> None:
    """产物自检：边界声明齐全、且不含可被误用为策略有效性证据的字段。

    fail closed：缺声明或带禁用字段直接抛错，不是打印警告——AC-508 要的是
    「不得进入证据链」这件事有机器执行力。
    """
    declared = payload.get("one_way_boundary")
    if not isinstance(declared, Mapping) or set(declared) != set(ONE_WAY_BOUNDARY):
        missing = sorted(set(ONE_WAY_BOUNDARY) - set(declared or {}))
        raise StrategyLayerError(
            "MISSING_BOUNDARY_DECLARATION",
            f"量化族产物必须带完整的 one_way_boundary（缺 {missing}）",
        )
    for key, value in ONE_WAY_BOUNDARY.items():
        if declared[key] != value:
            raise StrategyLayerError(
                "ALTERED_BOUNDARY_DECLARATION", f"one_way_boundary.{key} 被改写"
            )
    offending = sorted(FORBIDDEN_PERFORMANCE_FIELDS & _all_keys(payload))
    if offending:
        raise StrategyLayerError(
            "PERFORMANCE_FIELD_IN_ARTIFACT",
            f"量化族产物不得包含可被误用为策略有效性证据的字段：{offending}",
        )


def _all_keys(payload: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            keys.add(str(key))
            keys |= _all_keys(value)
    elif isinstance(payload, list | tuple):
        for item in payload:
            keys |= _all_keys(item)
    return keys


def fixed_sequence_source(
    entries: list[tuple[int, ExternalSignal, Mapping[str, Any] | None]],
) -> SignalFetch:
    """固定信号序列（T977 的验收用：不依赖 alphamill 运行时）。

    ``entries`` 是 ``(produced_at_ns, signal, intent_or_None)``，按时刻升序消费：
    每次取**不晚于当前时刻**的最后一条。用完即持续返回最后一条，过期与否由
    :func:`signal_decision_source` 的 ``max_age_ns`` 判定，本函数不代它决定。
    """
    ordered = sorted(entries, key=lambda item: item[0])

    def fetch(agent_id: str, now_ns: int) -> TimedSignal | None:
        current = None
        for produced_at, signal, intent in ordered:
            if produced_at > now_ns:
                break
            current = TimedSignal(signal=signal, produced_at_ns=produced_at, intent=intent)
        return current

    return fetch
