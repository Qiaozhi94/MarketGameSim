"""T917 所有者会话客户端：把真人窗口接到冻结协议、市场内核与证据准入上。

职责边界（对齐 design.md §5/§6 与 T910/T911 的既有产物）：

* **窗口机制不在这里**——``session.py`` 的 ``FormalSession``/``Window`` 已被 T910
  的集成测试锁定；客户端只是驱动它：开窗 → 收集决定 → ``submit()`` → 关窗。
* **市场内核不在这里**——所有者场景是 ``run_one`` 的一次普通运行，目标插槽
  belief-0 的决策经 ``external_decision_sources`` 缝隙由本模块供给（见
  ``experiment/runner.py::_handle_external_decide``）。
* **证据准入在这里**——formal 会话完成才走 ``evidence_guard.admit`` 五把锁；
  中止/不完整的会话只写审计工件、永不准入；training 工件同样永不准入。

解盲（合同 ``unblinding_rule``）：工件里只有决定与摘要，**没有任何结果字段**
（严重程度、效应、p 值都不算）。结果计算是 T919/T921 的事，本模块不 import。

场景编号（``artifacts.ai_seed_for_scenario``）：所有者按冻结顺序
``owner_scenario_order`` 依次打 24 个正式场景，位置 p 的场景 id 是
``owner_scenario_order[p]``，seed 取同序 AI assignment 的 seed。

异常语义：内核在事务里吞掉一切异常并落 INTERNAL 中止，所以所有者中止不会以
异常形态冒泡出 ``run_one``——驱动器在源回调里先把会话状态机置为 ABORTED，
``run_owner_scenario`` 靠状态机识别中止并写审计工件。
"""

from __future__ import annotations

import dataclasses
import os
import queue
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from market_game_sim.experiment.h2 import artifacts, evidence_guard, runner, session
from market_game_sim.experiment.runner import run_one

#: 训练场景 seed 基址。H2 独占正式/备用区是 50000..50184（预注册 §9），训练
#: 场景用 40000..40005——永不重叠，训练数据也永不升级进正式证据。
TRAINING_SEED_BASE = 40_000
TRAINING_BLOCKS = 6

OWNER_TRACK = evidence_guard.OWNER_TRACK

#: 屏幕上展示给所有者的冻结观察子集字段（design.md §6：只显示冻结观察子集、
#: 本人状态、进度与倒计时）。
_DISPLAY_FIELDS = (
    "best_bid",
    "best_ask",
    "last_ticks",
    "position_units",
    "wallet_units",
    "margin_ratio_bp",
    "initial_price_ticks",
)


class OwnerClientError(RuntimeError):
    """所有者会话的前置条件被违反（重复开桌、乱序、文件冲突等）。"""


class OwnerAbort(RuntimeError):
    """所有者主动中止当前场景。会话记 ABORTED，工件只作审计、不进结果。"""


# --------------------------------------------------------------------------- #
# 决定输入源：脚本化（测试/重放）与交互式（真人 stdin）
# --------------------------------------------------------------------------- #

#: 输入源的规范签名：给定窗号、观察子集与窗口对象，返回一次决定。
#: ``{"kind": "NO_ACTION"}`` / ``{"kind": "MARKET", "side": "buy"|"sell",
#: "quantity_units": int}`` / ``None``（本窗放弃，等价 NO_ACTION）。
#: 抛 :class:`OwnerAbort` 表示所有者中止。
DecisionInput = Callable[[int, dict[str, Any], Any], dict[str, Any] | None]


def scripted_input(decisions: Sequence[dict[str, Any] | None]) -> DecisionInput:
    """固定决定序列，逐窗取一条，用尽后视为放弃。测试与重放走这里。"""
    items = list(decisions)

    def _ask(window_index: int, info: dict[str, Any], window) -> dict[str, Any] | None:
        return items[window_index] if window_index < len(items) else None

    return _ask


class InteractiveInput:
    """真人 stdin 适配器：后台线程读行，截止前轮询，迟到输入记录在案。

    读行线程跨平台（不依赖 select/msvcrt）；截止后的输入不进窗口，只进该窗
    ``late_rejected`` 记录——这是 TR-302"迟到输入稳定 WINDOW_CLOSED"在客户端
    的可见形态。解析失败在剩余时间内重试，不消耗提交机会。
    """

    def __init__(self, stdin=None, *, render=print) -> None:
        self._lines: queue.Queue[str] = queue.Queue()
        self._render = render
        self._stdin = stdin
        self._thread: threading.Thread | None = None

    def _start_reader(self) -> None:
        def _pump() -> None:
            stream = self._stdin
            if stream is None:
                import sys

                stream = sys.stdin
            for line in stream:
                self._lines.put(line.strip())

        self._thread = threading.Thread(target=_pump, daemon=True)
        self._thread.start()

    def __call__(self, window_index: int, info: dict[str, Any], window) -> dict[str, Any] | None:
        if self._thread is None:
            self._start_reader()
        self._render(f"--- 窗口 {window_index + 1} ---")
        self._render(" ".join(f"{k}={info.get(k)}" for k in _DISPLAY_FIELDS))
        while True:
            remaining = session.remaining_seconds(window)
            if remaining <= 0.0:
                return None
            try:
                line = self._lines.get(timeout=min(remaining, 0.2))
            except queue.Empty:
                continue
            if line in ("", "n", "no"):
                return {"kind": "NO_ACTION"}
            if line in ("q", "quit"):
                raise OwnerAbort("所有者在窗口内主动中止")
            parsed = _parse_order(line)
            if parsed is not None:
                return parsed
            self._render(f"无法理解输入 {line!r}；可用：b <数量> / s <数量> / 空行=不动 / q=中止")


def _parse_order(line: str) -> dict[str, Any] | None:
    parts = line.split()
    if len(parts) != 2:
        return None
    side_abbr, qty_raw = parts
    side = {"b": "buy", "buy": "buy", "s": "sell", "sell": "sell"}.get(side_abbr.lower())
    if side is None or not qty_raw.isdigit() or int(qty_raw) <= 0:
        return None
    return {"kind": "MARKET", "side": side, "quantity_units": int(qty_raw)}


# --------------------------------------------------------------------------- #
# 会话驱动：窗口状态机 + 外生决策缝
# --------------------------------------------------------------------------- #


class _SessionDriver:
    """把 :data:`DecisionInput` 适配成内核外生决策源，并记录每窗规范决定。"""

    def __init__(
        self,
        total_windows: int,
        ask: DecisionInput,
        *,
        window_duration_ns: int | None = None,
    ) -> None:
        self.formal = session.FormalSession(total_windows=total_windows)
        self._ask = ask
        self._window_duration_ns = window_duration_ns
        self.records: list[dict[str, Any]] = []
        self.late_rejected_total = 0

    def source(self, event: dict, world: dict) -> dict[str, Any]:
        """内核外生决策源（``external_decision_sources`` 缝隙的值）。"""
        window_index = int(event.get("_decision_index", 0))
        if window_index != self.formal.completed_windows:
            raise OwnerClientError(
                f"窗口错位：内核要求第 {window_index} 窗，会话状态机在第 "
                f"{self.formal.completed_windows} 窗"
            )
        window = self.formal.open_next_window(duration_ns=self._window_duration_ns)
        info = {key: event.get("_observed_information_set", {}).get(key) for key in _DISPLAY_FIELDS}
        intent_id: str | None = None
        side: str | None = None
        quantity: int | None = None
        late: list[str] = []
        try:
            decision = self._ask(window_index, info, window)
        except OwnerAbort:
            self.formal.abort(technical=False)
            raise
        if decision is not None and decision.get("kind") == "MARKET":
            candidate = f"owner-w{window_index:02d}"
            if self.formal.submit(session.OrderIntent(intent_id=candidate)) is session.ACCEPTED:
                intent_id = candidate
                side = decision["side"]
                quantity = decision["quantity_units"]
            else:
                # 迟到：拒绝且不补，窗口落定 NO_ACTION（TR-302）。
                late.append(candidate)
        self.formal.close_current_window()

        self.records.append(
            {
                "window_index": window_index,
                "window_id": window.window_id,
                "decision": intent_id or session.NO_ACTION,
                "submitted": intent_id is not None,
                "side": side,
                "quantity_units": quantity,
                "open_monotonic_ns": window.open_monotonic_ns,
                "deadline_monotonic_ns": window.deadline_monotonic_ns,
                "late_rejected": late,
            }
        )
        self.late_rejected_total += len(late)
        if intent_id is None:
            return {"kind": "NO_ACTION"}
        return {
            "kind": "MARKET",
            "side": side.upper(),
            "quantity_units": quantity,
            "intent_id": intent_id,
        }

    def finalize(self, *, kernel_completed: bool) -> None:
        """内核收尾后对齐会话状态机的终态。

        场景的真实窗数由共享事务预算涌现（v0.1.5 冻结 plan 的
        ``max_transactions`` 下，三条条件都只能得到 ~32/33 个决策窗；协议里
        冻结的 ``windows_per_scenario=60`` 是调度器上界，在当前预算下从不
        绑定——校准证据同样是这个预算下产生的，三臂一致，不许单臂抬高）。
        ``FormalSession`` 的 COMPLETED 规则是"完成窗数 >= 总窗数"，而总窗数
        只有跑完才知道，所以内核正常收尾后把 total 对齐到实际窗数，再按
        状态机自己的规则落定终态。
        """
        self.formal.total_windows = self.formal.completed_windows
        terminal_abort = self.formal.state in (
            session.SessionState.ABORTED,
            session.SessionState.TECHNICAL_ABORT,
        )
        if kernel_completed and not terminal_abort:
            self.formal.state = session.SessionState.COMPLETED


# --------------------------------------------------------------------------- #
# 场景运行与工件
# --------------------------------------------------------------------------- #


def _owner_config(seed: int):
    """所有者场景配置：复用 AI 臂的冻结参数推导，只把目标插槽策略摘掉。

    ``goal_model_id=None`` 声明"这个插槽没有策略"——决策完全来自外生窗口源。
    其余（账户、保证金、做市商、窗口调度）与同 seed 的两条参照逐字段相同。
    """
    config = runner.build_config(seed, "linear")
    specs = [
        dataclasses.replace(spec, goal_model_id=None) if spec.agent_id == "belief-0" else spec
        for spec in config.agent_specs
    ]
    return dataclasses.replace(config, agent_specs=specs)


def _reference_digests(seed: int) -> dict[str, Any]:
    """同 seed 两条 WINDOW_MATCHED_POLICY_CONTROL 参照，先于处理运行生成并锁定。

    结果对 assignment/adjudication 不可见（design.md §5）：这里只留终止状态与
    事件流哈希，不计算也不落任何严重程度。
    """
    digests: dict[str, Any] = {}
    for arm in ("linear", "threshold"):
        result = run_one(runner.build_config(seed, arm))
        digests[arm] = {
            "policy_id": runner.ARM_TO_POLICY[arm],
            "terminated": result.terminated,
            "events_sha256": artifacts.canonical_digest(result.events),
        }
    return digests


def scenario_id_at(assignments: dict[str, Any], position: int) -> int:
    """冻结顺序里的第 p 个正式场景 id；越界一律拒绝。"""
    order = assignments["owner_scenario_order"]
    if not 0 <= position < len(order):
        raise OwnerClientError(f"正式场景位置 {position} 越界（冻结顺序共 {len(order)} 个）")
    return int(order[position])


def run_owner_scenario(
    stage: str,
    position: int,
    ask: DecisionInput,
    *,
    out_root: Path | None = None,
    window_duration_ns: int | None = None,
    assignments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """跑一个所有者场景（training 或 formal），返回已落盘的会话工件。

    正式场景的前置条件全部 fail-closed：分配表 FROZEN、位置不越序、前面的
    位置都已完成（冻结顺序不许挑）、每场景一个活动会话（文件锁）、准入五把锁。
    中止或不完整的正式会话写审计工件（``admitted=false`` + 排除原因），按
    预注册 §7 不进入分析。
    """
    if stage not in ("training", "formal"):
        raise OwnerClientError(f"stage 必须是 training 或 formal，收到 {stage!r}")
    table = assignments or artifacts.load_assignments()
    bindings = artifacts.verify_formal_bindings(table) if stage == "formal" else None
    contract = runner.OWNER_WINDOW_CONTRACT
    horizon_ns = int(contract["windows_per_scenario"]) * int(contract["logical_ns_per_window"])

    if stage == "formal":
        scenario_id = scenario_id_at(table, position)
        seed = artifacts.ai_seed_for_scenario(table, scenario_id)
        out_dir = out_root or artifacts.DEFAULT_FORMAL_ROOT / "owner"
        artifact_path = out_dir / f"scenario-{position:02d}-id-{scenario_id:02d}.json"
        if artifact_path.exists():
            raise OwnerClientError(f"场景已存在：{artifact_path}（正式场景不得重打）")
        _require_formal_prefix(table, position, out_dir)
    else:
        if not 0 <= position < TRAINING_BLOCKS:
            raise OwnerClientError(f"训练场景位置 {position} 越界（共 {TRAINING_BLOCKS} 个）")
        scenario_id = position
        seed = TRAINING_SEED_BASE + position
        out_dir = out_root or artifacts.DEFAULT_TRAINING_ROOT / "owner"
        artifact_path = out_dir / f"training-{position:02d}.json"

    out_dir.mkdir(parents=True, exist_ok=True)
    lock_path = out_dir / f".scenario-{position:02d}.lock"
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise OwnerClientError(
            f"场景 {position} 已有活动会话（锁 {lock_path.name} 存在）"
        ) from None
    os.close(lock_fd)

    try:
        references = _reference_digests(seed) if stage == "formal" else None
        driver = _SessionDriver(
            int(contract["windows_per_scenario"]),
            ask,
            window_duration_ns=window_duration_ns,
        )
        result = run_one(
            _owner_config(seed),
            world_overrides={
                "external_decision_sources": {"belief-0": driver.source},
                "run_horizon_ns": horizon_ns,
            },
        )
        driver.finalize(kernel_completed=result.terminated == "COMPLETED")
        completed = (
            result.terminated == "COMPLETED"
            and driver.formal.state is session.SessionState.COMPLETED
        )
        if stage == "formal" and completed:
            evidence_guard.admit(
                run_mode=OWNER_TRACK,
                stage=stage,
                protocol_hash=bindings["contract_protocol_hash"],
                pair_complete=True,
            )
        payload = _session_payload(
            stage=stage,
            scenario_id=scenario_id,
            seed=seed,
            table=table,
            driver=driver,
            run_result=result,
            references=references,
            horizon_ns=horizon_ns,
            admitted=stage == "formal" and completed,
            contract_protocol_hash=bindings["contract_protocol_hash"] if bindings else None,
        )
        artifacts.write_json_atomic(artifact_path, payload)
    finally:
        os.unlink(lock_path)
    return payload


def _require_formal_prefix(table: dict[str, Any], position: int, out_dir: Path) -> None:
    """冻结顺序不许挑：第 p 个场景开打前，0..p-1 必须都已有工件。"""
    for earlier in range(position):
        earlier_id = scenario_id_at(table, earlier)
        path = out_dir / f"scenario-{earlier:02d}-id-{earlier_id:02d}.json"
        if not path.exists():
            raise OwnerClientError(f"冻结顺序被跳过：位置 {earlier}（场景 {earlier_id}）尚未完成")


def _session_payload(
    *,
    stage: str,
    scenario_id: int,
    seed: int,
    table: dict[str, Any],
    driver: _SessionDriver,
    run_result,
    references: dict[str, Any] | None,
    horizon_ns: int,
    admitted: bool,
    contract_protocol_hash: str | None,
) -> dict[str, Any]:
    """会话工件。**没有任何结果字段**（解盲合同）；墙钟只作依从性诊断。"""
    return {
        "schema_version": 1,
        "run_mode": OWNER_TRACK,
        "evidence_class": "experiment-preview",
        "stage": stage,
        "scenario_id": scenario_id,
        "seed": seed,
        "protocol_hash": table["protocol_hash"],
        "contract_protocol_hash": contract_protocol_hash,
        "admitted": admitted,
        "window_contract": {
            "windows_per_scenario": int(runner.OWNER_WINDOW_CONTRACT["windows_per_scenario"]),
            "logical_ns_per_window": int(runner.OWNER_WINDOW_CONTRACT["logical_ns_per_window"]),
            "owner_wall_clock_seconds": int(
                runner.OWNER_WINDOW_CONTRACT["owner_wall_clock_seconds"]
            ),
            "run_horizon_ns": horizon_ns,
        },
        "session": {
            "final_state": str(driver.formal.state),
            "completed_windows": driver.formal.completed_windows,
            "late_rejected_total": driver.late_rejected_total,
            "decisions": driver.records,
        },
        "market_run": None
        if run_result is None
        else {
            "terminated": run_result.terminated,
            "abort_code": run_result.abort_code,
            "events_sha256": artifacts.canonical_digest(run_result.events),
            "book_last_ticks": run_result.book_last_ticks,
        },
        "references_digests": references,
        "owner_pseudonym": session.OWNER_ID,
    }


def replay_owner_scenario(payload: dict[str, Any]) -> bool:
    """处理重放：从记录的决定重跑会话状态机与市场场景，三处必须一致。

    状态机终态、每窗规范决定、市场事件流 SHA-256。重放不等墙钟——脚本源
    即刻提交，窗口给 5 秒只是留出执行余量（与 ``run_fixed_session`` 同一套路）。
    """
    records = payload["session"]["decisions"]
    scripted = [
        {"kind": "MARKET", "side": item["side"], "quantity_units": item["quantity_units"]}
        if item["submitted"]
        else None
        for item in records
    ]
    driver = _SessionDriver(
        len(scripted), scripted_input(scripted), window_duration_ns=5_000_000_000
    )
    result = run_one(
        _owner_config(payload["seed"]),
        world_overrides={
            "external_decision_sources": {"belief-0": driver.source},
            "run_horizon_ns": payload["window_contract"]["run_horizon_ns"],
        },
    )
    driver.finalize(kernel_completed=result.terminated == "COMPLETED")
    state_ok = driver.formal.state is session.SessionState.COMPLETED
    core_keys = ("window_index", "decision", "submitted", "side", "quantity_units")
    decisions_ok = [{key: item[key] for key in core_keys} for item in driver.records] == [
        {key: item[key] for key in core_keys} for item in records
    ]
    market_ok = (
        result.terminated == "COMPLETED"
        and artifacts.canonical_digest(result.events) == payload["market_run"]["events_sha256"]
    )
    return state_ok and decisions_ok and market_ok
