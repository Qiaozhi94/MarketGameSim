"""0.4.2 T1126 / T1129（FR-602 / NFR-601 / TR-601 / IR-601）：同种子对照的两臂与两种回放。

* **无人类基线臂**：载体清单 + 种子构建纯 AI 市场，不注入任何动作；同装配同种子逐点可复现。
* **同种子重放臂**：在原场种子上按 ``advance`` 序号投递会话动作行，推进到封口的
  ``end_advance_index`` 后比对封口记录的事件摘要与 owner 观察摘要，不一致即
  ``REPLAY_DIVERGED``（fail closed，该会话不进入配对）。
* **开环跨种子回放臂**（T1129）：同一段动作序列按 ``advance`` 序号投到预注册的其他种子上，
  推进到 5700 逻辑秒；报告中标注为「固定订单流扰动」。

一臂跑完立即在配对窗口上测量（``metrics/stability_effect.py``），事件流随即丢弃：全窗口
运行有数百万条记录，不在内存里同时留两臂。
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from market_game_sim.experiment.h2.live_market import HUMAN_AGENT, LiveMarket, ReplayError
from market_game_sim.experiment.perturbation import carrier, session
from market_game_sim.experiment.roster import StrategyRoster, load_roster
from market_game_sim.metrics.stability_effect import (
    WINDOW_END_NS,
    ArmMeasurement,
    measure_arm,
    pair_window_start,
)

BASELINE = "baseline"
HUMAN = "human"
ORIGINAL = "original"
SAME_SEED_REPLAY = "same_seed_replay"
OPEN_LOOP_REPLAY = "open_loop_replay"

#: 开环结果在报告里的强制标签（spec FR-602）：不表述为人类对市场的反应。
OPEN_LOOP_LABEL = "固定订单流扰动"

# 回放 / 配对的稳定原因码。
REPLAY_DIVERGED = "REPLAY_DIVERGED"
SESSION_INVALID = "SESSION_INVALID"
SESSION_UNSEALED = "SESSION_UNSEALED"
ROSTER_MISMATCH = "ROSTER_MISMATCH"

# 撤单在本次运行里的结局（T1129；不改内核撤单语义，只从事件流归类并留痕）。
CANCELLED = "CANCELLED"
TARGET_NOT_ACTIVE = "TARGET_NOT_ACTIVE"
TARGET_UNRESOLVED = "TARGET_UNRESOLVED"
NOT_PROCESSED = "NOT_PROCESSED"


class PairingError(Exception):
    """会话、清单或预注册不满足配对前提；``code`` 为稳定原因码。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class ArmRun:
    """一臂的运行摘要；事件流本身不保留。"""

    roster_id: str
    seed: int
    arm: str
    replay_mode: str
    advances: int
    logical_ns: int
    aborted: str | None
    window_start_ns: int | None
    measurement: ArmMeasurement | None
    event_digest: str
    observation_digests: tuple[dict[str, Any], ...]
    price_series_digest: str
    actions: int = 0
    out_of_window_actions: int = 0
    cancel_outcomes: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    @property
    def window_complete(self) -> bool:
        """推进到窗口终点（或在窗口内中止）才有可比的指标。"""
        return self.measurement is not None


@dataclass(frozen=True)
class ReplayResult:
    ok: bool
    reason_code: str | None
    detail: str | None
    run: ArmRun | None


def roster_for(roster_id: str, directory: pathlib.Path = carrier.ROSTER_DIR) -> StrategyRoster:
    return load_roster(directory, roster_id)


def _digest_json(value: Any) -> str:
    return hashlib.blake2b(
        json.dumps(value, sort_keys=True, default=str).encode("utf-8"), digest_size=16
    ).hexdigest()


def _cancel_outcomes(
    records: Sequence[Mapping[str, Any]], actions: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    decides: dict[int, Mapping[str, Any]] = {}
    cancel_arrivals: dict[str, Mapping[str, Any]] = {}
    cancelled_by: set[str] = set()
    for r in records:
        if r.get("agent_id") != HUMAN_AGENT:
            continue
        kind = r.get("event_type")
        if kind == "AGENT_DECIDE":
            seq = (r.get("internal_state") or {}).get("owner_action_seq")
            if seq is not None:
                decides[int(seq)] = r
        elif kind == "ORDER_ARRIVAL" and r.get("action") == "CANCEL":
            cancel_arrivals[r["decision_event_id"]] = r
        elif kind == "ORDER_CANCELLED" and r.get("reason") == "AGENT_REQUEST":
            cancelled_by.add(r.get("caused_by_event_id", ""))
    out = []
    for action in actions:
        if action["kind"] != "CANCEL":
            continue
        seq = int(action["action_seq"])
        decide = decides.get(seq)
        if decide is None:
            outcome = NOT_PROCESSED
        elif (decide.get("internal_state") or {}).get("external_reason_code") == (
            "CANCEL_TARGET_UNRESOLVED"
        ):
            outcome = TARGET_UNRESOLVED
        else:
            arrival = cancel_arrivals.get(decide["event_id"])
            outcome = (
                CANCELLED
                if arrival is not None and arrival["event_id"] in cancelled_by
                else TARGET_NOT_ACTIVE
            )
        out.append(
            {
                "action_seq": seq,
                "target_action_seq": int(action["payload"]["target_action_seq"]),
                "outcome": outcome,
            }
        )
    return out


def _out_of_window(
    records: Sequence[Mapping[str, Any]],
    actions: Sequence[Mapping[str, Any]],
    start: int | None,
    end: int,
) -> int:
    """观察时间戳落在 ``[W0, W_end]`` 之外（或没来得及处理）的动作数（spec §3 边界场景）。"""
    if not actions:
        return 0
    stamps = {
        int(r["information_set"]["owner_action_seq"]): int(r["timestamp"])
        for r in records
        if r.get("event_type") == "AGENT_OBSERVE" and r.get("agent_id") == HUMAN_AGENT
    }
    return sum(
        1
        for a in actions
        if start is None
        or (ts := stamps.get(int(a["action_seq"]))) is None
        or not start <= ts <= end
    )


def run_arm(
    roster: StrategyRoster,
    *,
    arm: str,
    replay_mode: str,
    actions: Sequence[Mapping[str, Any]] = (),
    end_advance_index: int | None = None,
    window_start_ns: int | None = None,
    window_end_ns: int = WINDOW_END_NS,
) -> ArmRun:
    """跑一臂并在配对窗口上测量。

    给 ``end_advance_index`` 时推进到该序号为止（同种子重放）；否则推进到逻辑时间越过
    ``window_end_ns``。``window_start_ns`` 缺省时按本臂事件流求 ``W0``（基线臂）；人类臂
    必须传入基线臂的 ``W0``，两臂同窗。推进到窗口终点之前就停下的臂没有指标
    （``measurement is None``），中止的臂带 ``KERNEL_ABORT``。
    """
    market = LiveMarket(roster=roster)
    market.schedule_actions(actions)
    while market.dead is None:
        if end_advance_index is not None:
            if market.advance_index >= end_advance_index:
                break
        elif market.logical_ns >= window_end_ns:
            break
        market.advance()
    records = market.kernel.committed_records
    start = window_start_ns if window_start_ns is not None else pair_window_start(records)
    reached_end = market.dead is not None or market.logical_ns >= window_end_ns
    measurement = None
    if start is not None and start < window_end_ns and reached_end:
        measurement = measure_arm(
            records,
            window_start=start,
            window_end=window_end_ns,
            aborted=market.dead is not None,
        )
    event_digest, observations = market.seal_digests()
    return ArmRun(
        roster_id=roster.roster_id,
        seed=roster.seed,
        arm=arm,
        replay_mode=replay_mode,
        advances=market.advance_index,
        logical_ns=market.logical_ns,
        aborted=market.dead,
        window_start_ns=start,
        measurement=measurement,
        event_digest=event_digest,
        observation_digests=tuple(observations),
        price_series_digest=_digest_json(market.price_series),
        actions=len(actions),
        out_of_window_actions=_out_of_window(records, actions, start, window_end_ns),
        cancel_outcomes=tuple(_cancel_outcomes(records, actions)),
    )


def run_baseline(
    roster: StrategyRoster,
    *,
    window_end_ns: int = WINDOW_END_NS,
    window_start_ns: int | None = None,
) -> ArmRun:
    """无人类基线臂：不注入任何动作。"""
    return run_arm(
        roster,
        arm=BASELINE,
        replay_mode=ORIGINAL,
        window_start_ns=window_start_ns,
        window_end_ns=window_end_ns,
    )


def load_treatment(path: str | pathlib.Path) -> session.SessionCheck:
    check = session.load_session(path)
    if not check.ok:
        raise PairingError(SESSION_INVALID, f"{path}: {check.reason_code} {check.detail}")
    return check


def replay_same_seed(
    check: session.SessionCheck,
    *,
    roster_dir: pathlib.Path = carrier.ROSTER_DIR,
    window_start_ns: int | None = None,
    window_end_ns: int = WINDOW_END_NS,
) -> ReplayResult:
    """在原场种子上重放到封口序号，摘要逐位一致才算原场个案（spec FR-602 ①、Q-604）。"""
    if not check.ok:
        return ReplayResult(False, SESSION_INVALID, check.reason_code, None)
    if check.status != session.SEALED:
        return ReplayResult(False, SESSION_UNSEALED, "未封口会话没有可比的事件摘要", None)
    header, seal = check.header, check.seal
    assert header is not None and seal is not None
    roster = roster_for(header["roster_id"], roster_dir)
    if roster.seed != header["seed"]:
        return ReplayResult(False, ROSTER_MISMATCH, "头记录的种子与清单不符", None)
    try:
        run = run_arm(
            roster,
            arm=HUMAN,
            replay_mode=SAME_SEED_REPLAY,
            actions=check.actions,
            end_advance_index=seal["end_advance_index"],
            window_start_ns=window_start_ns,
            window_end_ns=window_end_ns,
        )
    except ReplayError as exc:
        return ReplayResult(False, REPLAY_DIVERGED, f"{exc.code}: {exc}", None)
    if run.event_digest != seal["event_digest"]:
        return ReplayResult(False, REPLAY_DIVERGED, "事件摘要与封口记录不一致", run)
    if list(run.observation_digests) != list(seal["observation_digests"]):
        return ReplayResult(False, REPLAY_DIVERGED, "owner 观察摘要与封口记录不一致", run)
    return ReplayResult(True, None, None, run)


def replay_open_loop(
    check: session.SessionCheck,
    seed: int,
    *,
    window_start_ns: int,
    window_end_ns: int = WINDOW_END_NS,
) -> ArmRun:
    """开环跨种子回放：同一段动作序列按 ``advance`` 序号投到 ``seed`` 上，推进到窗口终点。

    ``window_start_ns`` 取该种子基线臂的 ``W0``。未封口会话同样可作开环处理（spec §3）。
    动作序号已过而无法投递时抛 ``ReplayError``（``REPLAY_ACTION_LATE``），不跳过动作。
    """
    if not check.ok:
        raise PairingError(SESSION_INVALID, str(check.reason_code))
    return run_arm(
        carrier.carrier_roster(seed),
        arm=HUMAN,
        replay_mode=OPEN_LOOP_REPLAY,
        actions=check.actions,
        window_start_ns=window_start_ns,
        window_end_ns=window_end_ns,
    )
