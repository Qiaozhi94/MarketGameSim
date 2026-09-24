"""0.4.1 T975/T976 (FR-504 / IR-502 / TR-501 / SC-504 / AC-507): 外部信号注入。

量化交易者族的决策来自内核之外，但它的委托必须与其他族走**完全相同**的路径。
因此这里两面都要钉：

* **正面**：信号驱动的限价/市价委托真的进了撮合、成交、账本，并且从成交能沿
  ``decision_event_id`` / ``intent_id`` 回溯到决策记录里的信号来源与版本（TR-501）；
* **反面**：信号缺失、过期、非法、版本不匹配、源自身抛错——每一种都降级为不动作、
  带稳定原因码，且**内核继续推进**（IR-502）。一个坏掉的外部通道不得让市场停摆。
"""

from __future__ import annotations

import pytest

from market_game_sim.agent.scheduler import AgentSpec
from market_game_sim.agent.strategy_layer.external import (
    SIGNAL_INVALID,
    SIGNAL_MISSING,
    SIGNAL_NO_ACTION,
    SIGNAL_STALE,
    SIGNAL_VERSION_MISMATCH,
    fixed_sequence_source,
    signal_decision_source,
)
from market_game_sim.agent.strategy_layer.protocol import ExternalSignal
from market_game_sim.experiment.config import ExperimentConfig
from market_game_sim.experiment.runner import RunResult, run_one

QUANT_AGENT = "quant-0"
SIGNAL = ExternalSignal(source_id="alpha101_subset", signal_version="v1", value={"alpha": 1})
SECOND = 1_000_000_000


def _spec(agent_id: str = QUANT_AGENT) -> AgentSpec:
    return AgentSpec(
        agent_id=agent_id,
        role="quant_trader",
        strategy_family_id="external_quant",
        info_tier="I3",
        observe_interval_ns=SECOND,
        latency_ns=1_000_000,
        leverage_tier=5,
        initial_bp=2000,
        max_order_qty=10_000,
    )


def _market_maker() -> AgentSpec:
    return AgentSpec(
        agent_id="mm-0",
        role="inventory_market_maker",
        observe_interval_ns=100_000_000,
        latency_ns=5_000_000,
        is_market_maker=True,
        half_spread_ticks=5,
        quote_size=10_000,
        max_inventory=100_000,
        inventory_skew_k_bp=10_000,
    )


def _run(source, *, transactions: int = 400) -> RunResult:
    config = ExperimentConfig(
        seed=7,
        max_transactions=transactions,
        agent_specs=[_market_maker(), _spec()],
    )
    return run_one(config, world_overrides={"external_decision_sources": {QUANT_AGENT: source}})


def _decisions(result: RunResult) -> list[dict]:
    return [
        e
        for e in result.events
        if e["event_type"] == "AGENT_DECIDE" and e["agent_id"] == QUANT_AGENT
    ]


# --------------------------------------------------------------------------- #
# 正面：信号驱动的委托走既有路径，并可回溯到来源与版本
# --------------------------------------------------------------------------- #


def test_limit_intent_from_a_signal_reaches_the_book_and_traces_back():
    source = signal_decision_source(
        fixed_sequence_source(
            [
                (
                    0,
                    SIGNAL,
                    {
                        "order_type": "LIMIT",
                        "side": "BUY",
                        "quantity_units": 5_000,
                        "price_ticks": 10_050,
                    },
                )
            ]
        )
    )
    result = _run(source)

    orders = [
        e
        for e in result.events
        if e["event_type"] == "ORDER_ARRIVAL" and e["agent_id"] == QUANT_AGENT
    ]
    assert orders, "信号驱动的委托没有进入内核"
    assert orders[0]["order_type"] == "LIMIT"
    assert orders[0]["price_ticks"] == 10_050

    # TR-501：委托 -> 决策记录 -> 信号来源与版本
    decisions = {e["event_id"]: e for e in _decisions(result)}
    parent = decisions[orders[0]["decision_event_id"]]
    assert parent["internal_state"]["signal_source_id"] == "alpha101_subset"
    assert parent["internal_state"]["signal_version"] == "v1"
    assert parent["internal_state"]["strategy_family_id"] == "external_quant"
    assert any(i["intent_id"] == orders[0]["intent_id"] for i in parent["intents"])


def test_signal_driven_orders_settle_through_the_same_ledger_path():
    """FR-504：量化族的成交与其他族一样有分录与账本影响，不走任何旁路。"""
    source = signal_decision_source(
        fixed_sequence_source(
            [(0, SIGNAL, {"order_type": "MARKET", "side": "BUY", "quantity_units": 5_000})]
        )
    )
    result = _run(source)
    fills = [
        e
        for e in result.events
        if e["event_type"] == "TRADE_SETTLE" and e["taker_agent_id"] == QUANT_AGENT
    ]
    assert fills, "量化族没有成交"
    roles = {p["role"] for p in fills[0]["postings"]}
    assert roles == {"MAKER", "TAKER"}
    assert result.accounts[QUANT_AGENT].position_units > 0


# --------------------------------------------------------------------------- #
# 反面：每种异常都降级为不动作 + 稳定原因码，内核继续推进
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("source_factory", "expected"),
    [
        (lambda: signal_decision_source(lambda _a, _t: None), SIGNAL_MISSING),
        (
            lambda: signal_decision_source(
                fixed_sequence_source([(0, SIGNAL, None)]),
            ),
            SIGNAL_NO_ACTION,
        ),
        (
            lambda: signal_decision_source(
                fixed_sequence_source(
                    [(0, SIGNAL, {"order_type": "LIMIT", "side": "BUY", "quantity_units": 1})]
                )
            ),
            SIGNAL_INVALID,  # LIMIT 缺价格
        ),
        (
            lambda: signal_decision_source(
                fixed_sequence_source(
                    [(0, SIGNAL, {"order_type": "MARKET", "side": "UP", "quantity_units": 1})]
                )
            ),
            SIGNAL_INVALID,  # 方向不在闭集内
        ),
        (
            lambda: signal_decision_source(
                fixed_sequence_source([(0, SIGNAL, None)]), allowed_versions={"v2"}
            ),
            SIGNAL_VERSION_MISMATCH,
        ),
        (
            lambda: signal_decision_source(
                fixed_sequence_source(
                    [(0, SIGNAL, {"order_type": "MARKET", "side": "BUY", "quantity_units": 1})]
                ),
                max_age_ns=1,
            ),
            SIGNAL_STALE,
        ),
        (
            lambda: signal_decision_source(_raising_source),
            SIGNAL_INVALID,  # 源自身抛错
        ),
    ],
    ids=["missing", "no-action", "limit-without-price", "bad-side", "version", "stale", "raises"],
)
def test_every_failure_mode_degrades_without_stopping_the_kernel(source_factory, expected):
    result = _run(source_factory())
    assert result.terminated == "COMPLETED", "外部信号故障不得阻塞内核"
    decisions = _decisions(result)
    assert decisions, "降级路径也必须留下决策记录"
    assert {d["internal_state"]["external_reason_code"] for d in decisions} == {expected}
    assert all(d["intents"] == [] for d in decisions)
    assert not [
        e
        for e in result.events
        if e["event_type"] == "ORDER_ARRIVAL" and e["agent_id"] == QUANT_AGENT
    ]


def _raising_source(agent_id: str, now_ns: int):
    raise RuntimeError("upstream signal service is down")


def test_market_intent_with_a_price_is_refused_rather_than_guessed():
    """矛盾的意图（市价带价格）不猜测，按非法降级。"""
    source = signal_decision_source(
        fixed_sequence_source(
            [
                (
                    0,
                    SIGNAL,
                    {
                        "order_type": "MARKET",
                        "side": "BUY",
                        "quantity_units": 1,
                        "price_ticks": 10_000,
                    },
                )
            ]
        )
    )
    result = _run(source, transactions=120)
    assert {d["internal_state"]["external_reason_code"] for d in _decisions(result)} == {
        SIGNAL_INVALID
    }


def test_stale_signal_ages_by_its_own_timestamp_not_by_fetch_time():
    """过期判定用信号自己的产生时刻——否则卡住的源会永远看起来新鲜。"""
    fetch = fixed_sequence_source(
        [(0, SIGNAL, {"order_type": "MARKET", "side": "BUY", "quantity_units": 1})]
    )
    decide = signal_decision_source(fetch, max_age_ns=5 * SECOND)
    fresh = decide({"agent_id": QUANT_AGENT, "timestamp": SECOND}, {})
    stale = decide({"agent_id": QUANT_AGENT, "timestamp": 10 * SECOND}, {})
    assert fresh["kind"] == "MARKET"
    assert stale == {
        "kind": "NO_ACTION",
        "reason_code": SIGNAL_STALE,
        "signal": {"source_id": "alpha101_subset", "signal_version": "v1"},
    }


def test_unknown_decision_kind_degrades_instead_of_raising():
    """IR-502：源返回未知类型时内核照常推进，并记 EXTERNAL_DECISION_INVALID。"""
    result = _run(lambda event, world: {"kind": "TELEPORT"})
    assert result.terminated == "COMPLETED"
    assert {d["internal_state"]["external_reason_code"] for d in _decisions(result)} == {
        "EXTERNAL_DECISION_INVALID"
    }


# --------------------------------------------------------------------------- #
# T977/T978 (NFR-503 / AC-508 / SC-504)：单向边界声明与可消费 artifact
# --------------------------------------------------------------------------- #


def test_quant_artifact_carries_the_one_way_boundary_and_self_checks():
    from market_game_sim.experiment.quant_family_run import run_quant_family

    artifact = run_quant_family(logical_seconds=120)
    boundary = artifact["one_way_boundary"]
    assert boundary["evidence_class"] == "engineering-demonstration"
    assert "不构成任何策略有效性的证据" in boundary["not_strategy_evidence"]
    assert "不得进入 alphamill 的证据链" in boundary["no_backflow_to_alphamill"]
    assert "不进入任何 evidence index" in boundary["not_in_evidence_index"]
    # SC-504：信号来源与版本随 artifact 落盘，因果链样本可回溯
    assert artifact["signal"]["signal_version"] == "fixed-seq-v1"
    assert artifact["activity"]["orders"] > 0
    for link in artifact["causal_chain_sample"]:
        assert link["decision_event_id"] and link["intent_id"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda a: a.pop("one_way_boundary"),
        lambda a: a["one_way_boundary"].pop("no_backflow_to_alphamill"),
        lambda a: a["one_way_boundary"].__setitem__("not_strategy_evidence", "随便写的"),
        lambda a: a["activity"].__setitem__("sharpe", 1.8),
        lambda a: a["activity"].__setitem__("win_rate", 0.63),
    ],
    ids=["no-declaration", "partial", "rewritten", "sharpe", "win-rate"],
)
def test_artifact_without_a_valid_boundary_is_refused(mutate):
    """AC-508：边界声明缺失/被改写，或出现绩效字段，落盘前就抛错。"""
    from market_game_sim.agent.strategy_layer.external import check_artifact_boundary
    from market_game_sim.agent.strategy_layer.protocol import StrategyLayerError
    from market_game_sim.experiment.quant_family_run import run_quant_family

    artifact = run_quant_family(logical_seconds=60)
    check_artifact_boundary(artifact)  # 原样必须通过
    mutate(artifact)
    with pytest.raises(StrategyLayerError) as exc:
        check_artifact_boundary(artifact)
    assert exc.value.code in {
        "MISSING_BOUNDARY_DECLARATION",
        "ALTERED_BOUNDARY_DECLARATION",
        "PERFORMANCE_FIELD_IN_ARTIFACT",
    }


def test_quant_artifact_never_enters_an_evidence_index():
    """NFR-503：量化族产物不得出现在任何 evidence index 里。"""
    import json
    import pathlib

    from market_game_sim.experiment.quant_family_run import QUANT_FAMILY_ID

    root = pathlib.Path(__file__).resolve().parents[2] / "docs" / "experiments"
    for path in root.glob("*evidence-index*.json"):
        blob = json.dumps(json.loads(path.read_text(encoding="utf-8")), ensure_ascii=False)
        assert QUANT_FAMILY_ID not in blob, path.name
        assert "quant-family" not in blob, path.name
