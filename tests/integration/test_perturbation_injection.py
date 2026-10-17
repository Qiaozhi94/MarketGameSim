"""0.4.2 T1124（AC-602、AC-603）：live 市场 owner 动作的确定性注入。

HTTP 线程只入队载荷；``advance()`` 持锁取出时分配动作序号、追加会话动作行、入队 owner
的观察，决策与委托由内核派生。规格见 docs/features/0.4/0.4.2-human-perturbation/spec.md
§3、§6，设计见 design.md §4、§5。
"""

from __future__ import annotations

import hashlib
import json
import pathlib

import pytest

from market_game_sim.eventlog.digest import rolling_digest_hex
from market_game_sim.evidence.chain_verifier import verify_decision_evidence_chain
from market_game_sim.experiment.h2.live_market import (
    DEFAULT_LIVE_ROSTER,
    HUMAN_AGENT,
    OWNER_SPEC,
    LiveMarket,
    build_market,
)
from market_game_sim.experiment.perturbation import session
from market_game_sim.experiment.roster import load_roster
from market_game_sim.schema.registry import get_registry

ROSTER_DIR = pathlib.Path("docs/experiments/0.4.3-rosters")
ANCHORED_ROSTER = "roster-2425a8200ca1a1e748a34a7e9d8b99ba"
WARMUP = 20


def _market(tmp_path, name="session.jsonl", clock=0):
    roster = load_roster(ROSTER_DIR, ANCHORED_ROSTER)
    ticks = iter(range(clock, clock + 10_000))
    return LiveMarket(
        roster=roster, session_path=tmp_path / name, wall_clock_ms=lambda: next(ticks)
    )


def _limit(market, offset):
    bid = market.view()["market"]["best_bid"]
    assert bid is not None
    return {
        "side": "BUY",
        "order_type": "LIMIT",
        "quantity_units": 3,
        "price_ticks": int(bid) - offset,
    }


_MARKET = {"side": "BUY", "order_type": "MARKET", "quantity_units": 2, "price_ticks": None}


def _owner(records, event_type):
    return [
        r for r in records if r.get("agent_id") == HUMAN_AGENT and r["event_type"] == event_type
    ]


def _digest(records):
    h = hashlib.blake2b(digest_size=16)
    for record in records:
        h.update(json.dumps(record, sort_keys=True, default=str).encode("utf-8"))
    return h.hexdigest()


def _strip_wall_clock(actions):
    return [{k: v for k, v in a.items() if k != "wall_clock_ms"} for a in actions]


def _push_during_next_kernel_run(market, payload):
    """确定性交错钩子：下一次 ``advance()`` 的第一次内核推进中途，HTTP 线程恰好提交一笔。

    ``push_order`` 不取锁（HTTP 线程从不取 ``LiveMarket.lock``），所以在 ``advance()``
    持锁推进时调用它，与真实线程在推进中途提交是同一条代码路径，但时点可控。
    """
    run = market.kernel.run
    fired = []

    def hooked(*args, **kwargs):
        if not fired:
            fired.append(market.push_order(payload))
        return run(*args, **kwargs)

    market.kernel.run = hooked
    market.advance()
    market.kernel.run = run
    assert fired == [{"accepted": True, "reason_code": "QUEUED"}]


def test_fields_assigned_at_drain_under_deterministic_interleaving(tmp_path):
    """AC-603：
    同一 advance 内多笔提交、提交恰在推进中途两类交错下，
    order_id、时间戳与 submitted_at 只由 advance 序号、动作序号与载荷决定且不重复
    """
    a = _market(tmp_path, "a.jsonl", clock=0)
    b = _market(tmp_path, "b.jsonl", clock=50_000)
    for market in (a, b):
        for _ in range(WARMUP):
            market.advance()
    payloads = [_limit(a, 30), _MARKET, _limit(a, 40)]
    assert payloads[0] == _limit(b, 30)

    # A：三笔在同一 advance 之前提交；第四笔在下一次 advance 的推进中途提交。
    for payload in payloads:
        a.push_order(payload)
    a.advance()
    _push_during_next_kernel_run(a, _MARKET)
    a.advance()
    a.advance()

    # B：同样的取出时点，但墙钟不同、第四笔在两次 advance 之间提交。
    for payload in payloads:
        b.push_order(payload)
    b.advance()
    b.advance()
    b.push_order(_MARKET)
    b.advance()
    b.advance()

    records_a, records_b = a.kernel.committed_records, b.kernel.committed_records
    assert _digest(records_a) == _digest(records_b), "取出时点相同，事件流必须逐位相同"
    assert [x["advance_index"] for x in a.session.actions] == [WARMUP] * 3 + [WARMUP + 2]
    assert _strip_wall_clock(a.session.actions) == _strip_wall_clock(b.session.actions)
    assert [x["wall_clock_ms"] for x in a.session.actions] != [
        x["wall_clock_ms"] for x in b.session.actions
    ]

    arrivals = _owner(records_a, "ORDER_ARRIVAL")
    decides = {r["event_id"]: r for r in _owner(records_a, "AGENT_DECIDE")}
    assert len(arrivals) == 4
    order_ids = [r["order_id"] for r in arrivals]
    assert len(set(order_ids)) == 4
    assert all(
        oid == f"o-{HUMAN_AGENT}-{r['decision_event_id']}-0"
        for oid, r in zip(order_ids, arrivals, strict=True)
    )
    stamps = [r["timestamp"] for r in arrivals]
    assert stamps == sorted(stamps) and len(set(stamps)) == 4
    for arrival in arrivals:
        decide = decides[arrival["decision_event_id"]]
        assert arrival["submitted_at"] == decide["timestamp"]
        assert arrival["timestamp"] == decide["timestamp"] + OWNER_SPEC.latency_ns
        assert decide["internal_state"]["participant_class"] == "human"
    assert len({r["submitted_at"] for r in arrivals}) == 4
    verify_decision_evidence_chain(records_a)

    # 反向：同样的载荷晚一次 advance 取出，派生字段随之改变——字段确实由取出序号决定。
    c = _market(tmp_path, "c.jsonl")
    for _ in range(WARMUP + 1):
        c.advance()
    for payload in payloads:
        c.push_order(payload)
    c.advance()
    late = [r["timestamp"] for r in _owner(c.kernel.committed_records, "ORDER_ARRIVAL")]
    assert late and late[0] != stamps[0]
    assert [x["advance_index"] for x in c.session.actions] == [WARMUP + 1] * 3


def test_action_journal_appended_per_accepted_action(tmp_path):
    """AC-602：每受理一笔动作立即追加日志，记录取出它的 advance 序号"""
    market = _market(tmp_path)
    path = tmp_path / "session.jsonl"
    for _ in range(WARMUP):
        market.advance()
    assert session.load_session(path).actions == ()

    # 格式校验不通过：当场拒绝，不入队、不入日志。
    bad = {"side": "BUY", "order_type": "MARKET", "quantity_units": 0, "price_ticks": None}
    assert market.push_order(bad) == {"accepted": False, "reason_code": "INVALID_INPUT"}
    assert market.push_order(_MARKET) == {"accepted": True, "reason_code": "QUEUED"}
    assert session.load_session(path).actions == (), "入队不是受理：取出前不写日志"

    market.advance()
    check = session.load_session(path)
    assert check.ok and check.status == session.UNSEALED
    assert [(x["advance_index"], x["action_seq"], x["kind"]) for x in check.actions] == [
        (WARMUP, 1, "MARKET")
    ]
    assert check.actions[0]["payload"] == {"side": "BUY", "quantity_units": 2}
    assert len(_owner(market.kernel.committed_records, "AGENT_OBSERVE")) == 1

    market.advance()
    sealed = market.seal_session()
    assert sealed is not None and market.seal_session() is None
    check = session.load_session(path)
    assert check.ok and check.status == session.SEALED
    assert check.seal["end_advance_index"] == WARMUP + 2
    records = market.kernel.committed_records
    assert check.seal["event_digest"] == rolling_digest_hex(records, get_registry())
    assert [x["action_seq"] for x in check.seal["observation_digests"]] == [1]


def test_invalid_cancel_found_after_enqueue_is_dropped_without_journal(tmp_path):
    """AC-602：
    入队后才判定的无效撤单（反查不到 order_id）被丢弃，不进内核、不入动作日志；
    同批里有效的动作照常处理
    """
    market = _market(tmp_path)
    for _ in range(WARMUP):
        market.advance()
    market.push_order(_limit(market, 30))
    market.push_order(_MARKET)
    market.advance()
    market.advance()
    resting = market.view()["account"]["active_orders"]
    assert len(resting) == 1
    target = resting[0]["order_id"]
    market_order = _owner(market.kernel.committed_records, "ORDER_ARRIVAL")[1]["order_id"]
    ai_order = next(
        r["order_id"]
        for r in market.kernel.committed_records
        if r["event_type"] == "ORDER_ARRIVAL" and r["agent_id"] != HUMAN_AGENT
    )

    for bogus in ("no-such-order", ai_order, market_order):
        assert market.push_cancel(bogus) == {"accepted": True, "reason_code": "QUEUED"}
    assert market.push_cancel(target) == {"accepted": True, "reason_code": "QUEUED"}
    market.push_order(_MARKET)
    market.advance()
    market.advance()

    actions = market.session.actions
    assert [x["kind"] for x in actions] == ["LIMIT", "MARKET", "CANCEL", "MARKET"]
    assert actions[2]["payload"] == {"target_action_seq": 1}
    records = market.kernel.committed_records
    cancels = [r for r in _owner(records, "ORDER_ARRIVAL") if r["action"] == "CANCEL"]
    assert [r["target_order_id"] for r in cancels] == [target]
    assert len(_owner(records, "AGENT_OBSERVE")) == len(actions) == 4
    assert not market.view()["account"]["active_orders"], "有效撤单照常生效"
    verify_decision_evidence_chain(records)


#: 改动前（T1124 之前的源码）实测的纯 AI 事件流摘要：同一装配推进 120 次 advance 后全部
#: 已提交记录的 blake2b-128（与 metrics/anchored_market.run 同口径）。
_PURE_AI_DIGESTS = {
    "seed7": ("6ba64b8bd36a087d790b78e252234947", 93635),
    "default_roster_0.4.1": ("6e592010c59bffef4c30743c410f27db", 153726),
    "anchored_roster_0.4.3": ("91d914ef09dfb4abd613ddbb45c391f5", 152897),
}


@pytest.mark.parametrize("label", sorted(_PURE_AI_DIGESTS))
def test_pure_ai_runs_keep_recorded_digests(label):
    """AC-603：注册 owner 代理规格后，纯 AI 运行的 0.4.1/0.4.3 入库摘要不变"""
    if label == "seed7":
        market = LiveMarket(seed=7)
    elif label == "default_roster_0.4.1":
        market = LiveMarket(roster=DEFAULT_LIVE_ROSTER)
    else:
        market = build_market(7, str(ROSTER_DIR / f"{ANCHORED_ROSTER}.json"))
    assert market.world["agent_specs"][HUMAN_AGENT] is OWNER_SPEC
    assert HUMAN_AGENT in market.world["external_decision_sources"]
    assert HUMAN_AGENT not in {spec.agent_id for spec in market.config.agent_specs}
    for _ in range(120):
        market.advance()
    records = market.kernel.committed_records
    assert (_digest(records), len(records)) == _PURE_AI_DIGESTS[label]
    assert not [r for r in records if r.get("agent_id") == HUMAN_AGENT]


def test_owner_spec_latency_moves_time_forward():
    """决策（类 4）→ 委托（类 0）是优先级类回退：owner 延迟为 0 会触发 KernelAbort。"""
    assert OWNER_SPEC.latency_ns >= 1


def test_session_needs_a_roster_and_never_overwrites(tmp_path):
    with pytest.raises(ValueError):
        LiveMarket(seed=7, session_path=tmp_path / "s.jsonl")
    with pytest.raises(ValueError):
        build_market(7, None, str(tmp_path / "s.jsonl"))
    _market(tmp_path)
    with pytest.raises(FileExistsError):
        _market(tmp_path)
