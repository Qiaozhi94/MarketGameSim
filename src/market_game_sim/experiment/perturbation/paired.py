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

import argparse
import hashlib
import json
import pathlib
import sys
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from market_game_sim.experiment.h2.live_market import HUMAN_AGENT, LiveMarket, ReplayError
from market_game_sim.experiment.perturbation import carrier, session
from market_game_sim.experiment.roster import StrategyRoster, load_roster
from market_game_sim.metrics.market_quality import FAIL, QUALITY_THRESHOLDS, _quality_verdict
from market_game_sim.metrics.quality_run import measure_quality
from market_game_sim.metrics.stability_effect import (
    WINDOW_END_NS,
    ArmMeasurement,
    build_effect_report,
    measure_arm,
    original_case,
    pair_window_start,
)

#: SC-501 里与种子无关的一项（墙钟性能取决于机器），不用来判定「载体在该种子上失效」。
_MACHINE_ITEMS = frozenset({"wall_seconds_per_logical_second"})

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
    #: 基线臂上未通过的 SC-501 市场项（失效边界「载体 SC-501 失效的种子」）；人类臂为 None。
    sc501_failed: tuple[str, ...] | None = None

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
    sc501_failed = None
    if arm == BASELINE and measurement is not None:
        quality = measure_quality(
            records, window_start=start, window_end=window_end_ns, wall_seconds=0.0
        )
        sc501_failed = tuple(
            item
            for item in QUALITY_THRESHOLDS
            if item not in _MACHINE_ITEMS and _quality_verdict(item, quality.get(item)) == FAIL
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
        sc501_failed=sc501_failed,
    )


def arm_summary(run: ArmRun) -> dict[str, Any]:
    """效应量报告（``stability_effect.build_effect_report``）要的一臂摘要。"""
    return {
        "run_digest": run.event_digest,
        "aborted": run.aborted,
        "logical_ns": run.logical_ns,
        "measurement": run.measurement,
        "sc501_failed": list(run.sc501_failed) if run.sc501_failed is not None else None,
        "out_of_window_actions": run.out_of_window_actions,
        "cancel_outcomes": list(run.cancel_outcomes),
    }


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


# --------------------------------------------------------------------------- #
# 正式配对（T1129 / T1132）：只读预注册
# --------------------------------------------------------------------------- #


def _failed_arm(code: str) -> dict[str, Any]:
    return {
        "run_digest": None,
        "aborted": None,
        "logical_ns": None,
        "measurement": None,
        "sc501_failed": None,
        "out_of_window_actions": 0,
        "cancel_outcomes": [],
        "failure": code,
    }


def _pair_seed(args: tuple[pathlib.Path, int, int | None, int]) -> dict[str, Any]:
    """一个开环种子：基线臂定 W0，人类臂按 advance 序号回放同一段动作并推进到窗口终点。"""
    treatment_path, seed, start_override, end = args
    check = session.load_session(treatment_path)
    baseline = run_baseline(
        carrier.carrier_roster(seed), window_end_ns=end, window_start_ns=start_override
    )
    if baseline.window_start_ns is None:
        human = _failed_arm("BASELINE_WINDOW_NOT_ESTABLISHED")
    else:
        try:
            human = arm_summary(
                replay_open_loop(
                    check, seed, window_start_ns=baseline.window_start_ns, window_end_ns=end
                )
            )
        except ReplayError as exc:
            # 无法按序号投递：该种子判失败并留原因码，不跳过动作、不改写时点。
            human = _failed_arm(exc.code)
    return {
        "seed": seed,
        "replay_mode": OPEN_LOOP_REPLAY,
        "baseline": arm_summary(baseline),
        "human": human,
    }


def _original(
    check: session.SessionCheck,
    roster_dir: pathlib.Path,
    start_override: int | None,
    end: int,
) -> dict[str, Any]:
    header = check.header
    assert header is not None
    if check.status != session.SEALED:
        return original_case(
            session_id=header["session_id"],
            seed=header["seed"],
            replay_ok=False,
            replay_reason=SESSION_UNSEALED,
            baseline=None,
            human=None,
            out_of_window_actions=0,
        )
    baseline = run_baseline(
        roster_for(header["roster_id"], roster_dir),
        window_end_ns=end,
        window_start_ns=start_override,
    )
    replay = replay_same_seed(
        check, roster_dir=roster_dir, window_start_ns=baseline.window_start_ns, window_end_ns=end
    )
    return original_case(
        session_id=header["session_id"],
        seed=header["seed"],
        replay_ok=replay.ok,
        replay_reason=replay.reason_code,
        baseline=baseline.measurement,
        human=replay.run.measurement if replay.ok and replay.run else None,
        out_of_window_actions=replay.run.out_of_window_actions if replay.run else 0,
    )


def run_pairing(
    treatment_path: str | pathlib.Path,
    *,
    preregistration_path: str | pathlib.Path | None = None,
    pinned_sha256: str | None = None,
    power_report_path: str | pathlib.Path | None = None,
    roster_dir: pathlib.Path = carrier.ROSTER_DIR,
    window_start_ns: int | None = None,
    window_end_ns: int = WINDOW_END_NS,
    jobs: int = 1,
) -> dict[str, Any]:
    """一个处理会话的正式配对与效应量报告（spec FR-602 / FR-603）。

    唯一的预注册读取点是 ``preregistration.begin_pairing``：缺失、未钉住、哈希不一致、功效
    报告被改或处理会话不在其中即 fail closed。配对集合（开环种子清单）只取自预注册文件，
    报告写出前再核一次预注册未变。``window_start_ns`` 只供测试用短窗口驱动。
    """
    from market_game_sim.experiment.perturbation import preregistration as prereg_mod

    kwargs: dict[str, Any] = {"pinned_sha256": pinned_sha256}
    if power_report_path is not None:
        kwargs["power_report_path"] = power_report_path
    prereg_path = pathlib.Path(preregistration_path or prereg_mod.PREREGISTRATION_PATH)
    prereg, sha = prereg_mod.begin_pairing(prereg_path, **kwargs)
    if prereg["carrier"]["count"] != carrier.CARRIER_COUNT or (
        prereg["carrier"]["sensitivity_x1000"] != carrier.CARRIER_SENSITIVITY_X1000
    ):
        raise PairingError(ROSTER_MISMATCH, "预注册的载体与 carrier.py 不符")
    path = pathlib.Path(treatment_path)
    check = load_treatment(path)
    entry = prereg_mod.require_treatment(prereg, check)

    work = [(path, int(seed), window_start_ns, window_end_ns) for seed in prereg["open_loop_seeds"]]
    if jobs <= 1:
        pairs = [_pair_seed(item) for item in work]
    else:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            pairs = list(pool.map(_pair_seed, work))
    case = _original(check, roster_dir, window_start_ns, window_end_ns)
    prereg_mod.verify_preregistration(sha, prereg_path)
    return build_effect_report(
        pairs=pairs,
        original_cases=[case],
        preregistration=prereg,
        preregistration_sha256=sha,
        treatment=entry,
        label=OPEN_LOOP_LABEL,
        carrier_disclaimer=carrier.CARRIER_DISCLAIMER,
    )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _run_json(run: ArmRun) -> dict[str, Any]:
    m = run.measurement
    return {
        "roster_id": run.roster_id,
        "seed": run.seed,
        "arm": run.arm,
        "replay_mode": run.replay_mode,
        "evidence_class": "experiment-preview",
        "run_mode": "interactive",
        "advances": run.advances,
        "logical_ns": run.logical_ns,
        "aborted": run.aborted,
        "window_start_ns": run.window_start_ns,
        "event_digest": run.event_digest,
        "metrics": dict(m.metrics) if m is not None else None,
        "degenerate": list(m.degenerate) if m is not None else None,
        "sc501_failed": list(run.sc501_failed) if run.sc501_failed is not None else None,
        "out_of_window_actions": run.out_of_window_actions,
        "cancel_outcomes": list(run.cancel_outcomes),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m market_game_sim.experiment.perturbation.paired"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    baseline = sub.add_parser("baseline", help="无人类基线臂（全窗口）")
    baseline.add_argument("--seed", type=int, required=True)
    replay = sub.add_parser("replay", help="同种子重放：与封口记录逐位比对")
    replay.add_argument("--session", required=True)
    pair = sub.add_parser("pair", help="正式配对与效应量报告（只读已钉住的预注册）")
    pair.add_argument("--session", required=True)
    pair.add_argument("--jobs", type=int, default=1)
    for p in (baseline, replay, pair):
        p.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    if args.command == "baseline":
        payload: dict[str, Any] = _run_json(run_baseline(carrier.carrier_roster(args.seed)))
    elif args.command == "replay":
        result = replay_same_seed(load_treatment(args.session))
        payload = {
            "ok": result.ok,
            "reason_code": result.reason_code,
            "detail": result.detail,
            "run": _run_json(result.run) if result.run else None,
        }
    else:
        payload = run_pairing(args.session, jobs=args.jobs)
    pathlib.Path(args.out).write_text(
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(args.out)
    return 0 if args.command != "replay" or payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
