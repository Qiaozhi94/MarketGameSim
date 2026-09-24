"""0.4.1 T978（成果门 H2-E3，SC-504 / AC-507 / AC-508）：量化族运行 artifact。

跑一个**含量化交易者族**的纯 AI 市场：该族的决策来自固定信号序列（本里程碑不依赖
alphamill 运行时，其 M3 未开工），委托与其他族走完全相同的撮合、账本与风控路径。

产物携带单向边界声明并在落盘前自检（`external.check_artifact_boundary`）：缺声明或
出现可被误用为策略有效性证据的字段即抛错，不落盘。**沙盘盈亏永不构成策略有效性证据，
也永不回流 alphamill 证据链**（ADR-011 §决策 5）。
"""

from __future__ import annotations

import argparse
import copy
import json
import pathlib
import sys
from collections.abc import Mapping
from typing import Any

from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.agent.strategy_layer.external import (
    boundary_declaration,
    check_artifact_boundary,
    fixed_sequence_source,
    signal_decision_source,
)
from market_game_sim.agent.strategy_layer.protocol import ExternalSignal

QUANT_FAMILY_ID = "external_quant"
QUANT_SIGNAL_SOURCE = "alpha101_timeseries_subset"
QUANT_SIGNAL_VERSION = "fixed-seq-v1"
SECOND_NS = 1_000_000_000


def quant_specs(count: int = 3) -> list[AgentSpec]:
    """量化交易者族的 AgentSpec：信息集 I3（外部信号通道），其余与其他族同形。"""
    return [
        AgentSpec(
            agent_id=f"{QUANT_FAMILY_ID}-{i}",
            role="quant_trader",
            strategy_family_id=QUANT_FAMILY_ID,
            info_tier="I3",
            observe_interval_ns=5 * SECOND_NS,
            latency_ns=50_000_000,
            leverage_tier=5,
            initial_bp=2000,
            max_order_qty=2_000,
        )
        for i in range(count)
    ]


def fixed_signal_plan(agent_ids: list[str], *, logical_seconds: int) -> dict[str, Any]:
    """冻结的信号序列：每 20 逻辑秒一个方向翻转，逐代理错开相位。

    固定序列而不是随机——本 artifact 要可重放，而且「量化族的行为」必须来自声明的
    信号，不是来自本模块的即兴随机数。
    """
    plan: dict[str, Any] = {}
    for index, agent_id in enumerate(agent_ids):
        entries = []
        for step in range(logical_seconds // 20 + 1):
            at_ns = (step * 20 + index * 3) * SECOND_NS
            side = "BUY" if (step + index) % 2 == 0 else "SELL"
            entries.append(
                {
                    "produced_at_ns": at_ns,
                    "intent": {
                        "order_type": "LIMIT" if step % 3 else "MARKET",
                        "side": side,
                        "quantity_units": 1_000,
                        "price_ticks": 10_000 + (50 if side == "BUY" else -50)
                        if step % 3
                        else None,
                    },
                }
            )
        plan[agent_id] = entries
    return plan


def _sources(plan: Mapping[str, Any]) -> dict[str, Any]:
    out = {}
    for agent_id, entries in plan.items():
        signal = ExternalSignal(
            source_id=QUANT_SIGNAL_SOURCE,
            signal_version=QUANT_SIGNAL_VERSION,
            value={"plan": "fixed-sequence"},
        )
        out[agent_id] = signal_decision_source(
            fixed_sequence_source(
                [(int(e["produced_at_ns"]), signal, e["intent"]) for e in entries]
            ),
            allowed_versions={QUANT_SIGNAL_VERSION},
        )
    return out


def run_quant_family(*, logical_seconds: int = 300, seed: int = 7) -> dict[str, Any]:
    """跑含量化族的市场，返回可消费 artifact（已自检边界声明）。"""
    from market_game_sim.experiment.h2.live_market import DEFAULT_LIVE_ROSTER, LiveMarket

    roster = copy.deepcopy(DEFAULT_LIVE_ROSTER)
    roster["seed"] = seed
    market = LiveMarket(roster=roster)
    quant = quant_specs()
    plan = fixed_signal_plan([spec.agent_id for spec in quant], logical_seconds=logical_seconds)

    # 量化族挂在既有装配之上：账户、观察调度、external 缝隙都用既有机制。
    from market_game_sim.ledger.account import Account

    for spec in quant:
        market.accounts[spec.agent_id] = Account(agent_id=spec.agent_id, wallet_units=10**13)
        market.world["agent_specs"][spec.agent_id] = spec
        market.world["agent_initial_bp"][spec.agent_id] = spec.initial_bp
        market.kernel.enqueue(
            {
                "event_type": "AGENT_OBSERVE",
                "timestamp": 0,
                "agent_id": spec.agent_id,
                "observed_at": 0,
                "market_data_event_id": "e1_0",
                "information_set": {},
            }
        )
    market.world["external_decision_sources"] = _sources(plan)

    while market.logical_ns < logical_seconds * SECOND_NS and not market.dead:
        market.advance()

    events = market.kernel.committed_records
    quant_ids = {spec.agent_id for spec in quant}
    orders = [
        e
        for e in events
        if e.get("event_type") == "ORDER_ARRIVAL" and e.get("agent_id") in quant_ids
    ]
    fills = [
        e
        for e in events
        if e.get("event_type") == "TRADE_SETTLE"
        and (e.get("taker_agent_id") in quant_ids or e.get("maker_agent_id") in quant_ids)
    ]
    decisions = [
        e
        for e in events
        if e.get("event_type") == "AGENT_DECIDE" and e.get("agent_id") in quant_ids
    ]
    reasons: dict[str, int] = {}
    for record in decisions:
        code = (record.get("internal_state") or {}).get("external_reason_code")
        if code:
            reasons[code] = reasons.get(code, 0) + 1

    artifact = {
        "schema_version": 1,
        "one_way_boundary": boundary_declaration(),
        "run": {
            "roster_id": market.roster_id,
            "seed": seed,
            "logical_seconds": round(market.logical_ns / SECOND_NS, 3),
            "quant_agents": sorted(quant_ids),
        },
        "signal": {
            "source_id": QUANT_SIGNAL_SOURCE,
            "signal_version": QUANT_SIGNAL_VERSION,
            "plan": "fixed-sequence（不依赖 alphamill 运行时）",
        },
        "activity": {
            "decisions": len(decisions),
            "orders": len(orders),
            "fills_involving_quant": len(fills),
            "degrade_reason_counts": reasons,
        },
        "causal_chain_sample": [
            {
                "order_id": order["order_id"],
                "intent_id": order["intent_id"],
                "decision_event_id": order["decision_event_id"],
                "order_type": order["order_type"],
                "side": order["side"],
            }
            for order in orders[:5]
        ],
    }
    check_artifact_boundary(artifact)
    return artifact


def main(argv: list[str] | None = None) -> int:
    """``python -m market_game_sim.experiment.quant_family_run --seconds 300``."""
    parser = argparse.ArgumentParser(description="Run the market with the external quant family")
    parser.add_argument("--seconds", type=int, default=300)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", default="artifacts/0.4.1/quant")
    args = parser.parse_args(argv)

    artifact = run_quant_family(logical_seconds=args.seconds, seed=args.seed)
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"quant-family-s{args.seed}.json"
    path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"量化族运行 artifact: {path}")
    activity = artifact["activity"]
    print(f"  委托 {activity['orders']}，参与成交 {activity['fills_involving_quant']}")
    print(f"  降级计数 {activity['degrade_reason_counts'] or '无'}")
    print(f"  边界声明: {artifact['one_way_boundary']['not_in_evidence_index']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
