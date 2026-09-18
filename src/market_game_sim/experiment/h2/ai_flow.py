"""0.3.2 owner 终端的确定性 AI 行情流量（工程演示，非研究 agent 轨）。

生成与 ``HumanAdapter`` 事件契约同构的 AGENT_DECIDE + ORDER_ARRIVAL 流：每逻辑秒
AI 做市代理在随机游走中间价附近换报价（撤旧挂新），AI 吃单代理按概率市价穿过
盘口产生公开成交（tape → K 线）。随机性用 blake2b 计数器模式，跨平台可复现。

这不是 0.3.1 的研究 agent 家族（alphamill `FactorDef` 等，见 notes §7 DQ-J），
仅用于 owner Web 终端 preview 的"AI 已在交易中"行情预热与实时流动。
"""

from __future__ import annotations

import hashlib
from typing import Any

_PREVIEW_AGENTS = ("ai-alpha", "ai-noise")


def _draw(seed: str) -> float:
    """确定性 [0,1) 抽样（blake2b 计数器模式）。"""

    digest = hashlib.blake2b(seed.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") / 2**64


def _decision_evidence(agent_id: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "goal_model_id": agent_id,
        "goal_model_version": 1,
        "desired_position_units": 0,
        "executable_position_units": 0,
        "constraint_binding": False,
        "constraint_reason": None,
        "trigger_provenance": "ENDOGENOUS_AGENT",
        "observation_event_id": "e2_0",
        "cursor_from_event_id": "e2_0",
        "cursor_to_event_id": "e2_0",
    }


class AiFlowGenerator:
    """按逻辑秒生成 AI 委托事件流；同 seed 同秒数输出逐字节一致。"""

    def __init__(
        self,
        *,
        seed: int = 7,
        mid_ticks: int = 10_000,
        walk_ticks: int = 12,
        quote_span_ticks: int = 8,
        taker_probability: float = 0.45,
    ) -> None:
        self.seed = seed
        self.mid_ticks = mid_ticks
        self.walk_ticks = walk_ticks
        self.quote_span_ticks = quote_span_ticks
        self.taker_probability = taker_probability
        self._open_quote_orders: dict[str, str] = {}  # side -> order_id

    def seed_accounts(self) -> dict[str, int]:
        """AI 代理的初始资金（HumanAdapter 上下文账户）。"""

        return {agent: 5_000_000 for agent in _PREVIEW_AGENTS}

    def events_for_second(self, second_index: int) -> list[dict[str, Any]]:
        """该逻辑秒的 [decide, arrival, decide, arrival, ...] 事件流。"""

        events: list[dict[str, Any]] = []
        base_ns = second_index * 1_000_000_000
        seq = second_index * 10

        def emit(
            agent_id: str,
            action: str,
            *,
            side: str | None = None,
            order_type: str | None = None,
            price_ticks: int | None = None,
            quantity_units: int | None = None,
            order_id: str | None = None,
            cancel_target: str | None = None,
        ) -> None:
            nonlocal seq
            intent_id = f"ai-intent-{second_index}-{seq}"
            decision_id = f"ai-decision-{second_index}-{seq}"
            events.append(
                {
                    "event_type": "AGENT_DECIDE",
                    "timestamp": base_ns + seq * 1_000,
                    "agent_id": agent_id,
                    "rule_id": "ai-preview",
                    "intents": [
                        {
                            "intent_id": intent_id,
                            "action": action,
                            "side": side,
                            "order_type": order_type,
                            "price_ticks": price_ticks,
                            "quantity_units": quantity_units,
                        }
                    ],
                    "observation_event_id": "e2_0",
                    "decision_evidence": _decision_evidence(agent_id),
                    "internal_state": {"second": second_index, "seq": seq},
                    "decision_event_id": decision_id,
                }
            )
            arrival: dict[str, Any] = {
                "event_type": "ORDER_ARRIVAL",
                "timestamp": base_ns + seq * 1_000 + 500,
                "agent_id": agent_id,
                "order_id": order_id or f"ai-cancel-{second_index}-{seq}",
                "action": "SUBMIT" if action == "SUBMIT" else "CANCEL",
                "side": side,
                "order_type": order_type,
                "price_ticks": price_ticks,
                "quantity_units": quantity_units,
                "origin": "AGENT",
                "intent_id": intent_id,
                "decision_event_id": decision_id,
                "submitted_at": base_ns + seq * 1_000,
            }
            if cancel_target is not None:
                arrival["target_order_id"] = cancel_target
            events.append(arrival)
            seq += 1

        # 1) 中间价随机游走（确定性）
        step = int(round((_draw(f"{self.seed}:walk:{second_index}") - 0.5) * 2 * self.walk_ticks))
        self.mid_ticks = max(1, self.mid_ticks + step)

        # 2) AI 做市：双边撤旧挂新（围绕新中间价 ±span），游走带动整个报价
        for quote_side, sign in (("BUY", -1), ("SELL", +1)):
            prev = self._open_quote_orders.get(quote_side)
            if prev is not None:
                emit("ai-maker", "CANCEL", cancel_target=prev)
            new_quote_id = f"ai-quote-{quote_side}-{second_index}"
            price = self.mid_ticks + sign * self.quote_span_ticks
            quantity = 5 + int(_draw(f"{self.seed}:q:{quote_side}:{second_index}") * 10)
            emit(
                "ai-maker",
                "SUBMIT",
                side=quote_side,
                order_type="LIMIT",
                price_ticks=price,
                quantity_units=quantity,
                order_id=new_quote_id,
            )
            self._open_quote_orders[quote_side] = new_quote_id

        # 3) AI 吃单：按概率市价穿过盘口（产生公开成交）
        if _draw(f"{self.seed}:taker:{second_index}") < self.taker_probability:
            taker = _PREVIEW_AGENTS[
                int(_draw(f"{self.seed}:ta:{second_index}") * len(_PREVIEW_AGENTS))
            ]
            taker_side = "BUY" if _draw(f"{self.seed}:ts:{second_index}") < 0.55 else "SELL"
            quantity = 1 + int(_draw(f"{self.seed}:tq:{second_index}") * 4)
            emit(
                taker,
                "SUBMIT",
                side=taker_side,
                order_type="MARKET",
                price_ticks=None,
                quantity_units=quantity,
                order_id=f"ai-take-{second_index}",
            )
        return events
