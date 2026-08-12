---
tool: "opencode"
tool_name: "OpenCode"
session_id: "ses_0136e4807ffevnOBhW0IlWITQ7"
title: "Implement replay module 0.1.4 (@Sisyphus-Junior subagent)"
project: "D:/Projects/market-game-sim"
model: "glm-5.2"
created_at: "2026-08-10T16:46:40Z"
updated_at: "2026-08-10T16:47:30Z"
tokens_input: 74712
tokens_output: 1393
cost: 0.0
parent_id: "ses_013854ed4ffeDL4uBdQiSBgfr5"
---

# Implement replay module 0.1.4 (@Sisyphus-Junior subagent)

## user · 2026-08-10T16:46:40Z

[TASK] Implement the `replay/` module for milestone 0.1.4 "replay and report" in the MarketGameSim Python project at D:\Projects\market-game-sim. This implements tasks T101/T102/T103/T201/T202/T203/T204 + verification T401/T402, exit conditions E1/E2/E3/E6, and acceptance criteria AC-001/002/003/006/005. Deliver production code + passing tests.

[CONTEXT — READ THESE FIRST, IN THIS ORDER]
- `docs/features/0.1/0.1.4-replay-and-report/spec.md` — §2 US-004/US-005, §3 (single-file HTML, kernel boundary §3.2, downsampling §3.3), §4 FR-019/FR-020/NFR-004/TR-001(§4.2), §6 E1-E6 + AC-001..006, §7.
- `docs/features/0.1/0.1.4-replay-and-report/design.md` — §4 (API/CLI contract + Event/Trace Contract), §8, §9.
- `docs/features/0.1/0.1.4-replay-and-report/tasks.md` — T101..T204, T401..T405.
- `docs/contracts/event-schema.md` — §1.5 (TI-4/TI-5), §4.2.1 (TRADE_POSTING), §4.2.2 (MARGIN_CALL), §4.2.3 (WRITE_OFF_POSTING), §4.6 (SNAPSHOT: §4.6.1 ACCOUNT 11-field, §4.6.2 BOOK aggregation, §4.6.3 frame definition + bootstrap), §4.7 (ORDER_CANCELLED), §6 (RUN_HEADER/RUN_TRAILER).
- `docs/research/metrics-dictionary.md` §1.9 + §1.9.1 (K-line definition: bar_ns=60s base, periods 5/15/60 min, only completed bars, left-closed right-open [k*bar_ns,(k+1)*bar_ns), empty bar uses prev close, before-first-trade uses initial_price, timestamp==(k+1)*bar_ns belongs to bar k+1).
- `docs/contracts/degenerate-states.md` — TI-4/TI-5 definitions.
- Source to UNDERSTAND (do not import from replay/): `src/market_game_sim/verify.py` (existing log-based rebuild), `src/market_game_sim/ledger/account.py` (apply_fill deltas, snapshot_entry, margin_ratio_bp, risk_equity, unrealized_pnl_at_risk_mark), `src/market_game_sim/ledger/risk.py` (state machine), `src/market_game_sim/book/orderbook.py` (Book class), `src/market_game_sim/kernel/runner.py` (EventKernel._run_transaction atomic commit), `src/market_game_sim/experiment/runner.py` (run_one: world dict = {book, accounts, exchange_fee_units, exchange_risk_pnl_units, mult, ...}), `src/market_game_sim/eventlog/writer.py` (build_run_header, write_log), `src/market_game_sim/eventlog/digest.py` (DIGEST_SIZE=32), `src/market_game_sim/bench/__main__.py` (CLI argparse pattern).

# ===== DESIGN DECISIONS (from E1 design consultation — FOLLOW THESE EXACTLY) =====

## Frame definition (T103, E1)
- Frame 0 = txn 1 (ACCOUNT bootstrap SNAPSHOT) + txn 2 (BOOK bootstrap SNAPSHOT) merged. Frame k (k>=1) = complete state after txn k+2 commits.
- A run with T committed transactions (T>=2) has T-1 frames (frame 0..T-2). T=2 (zero business txns) → 1 frame.
- Frame boundary = transaction boundary.

## Account 11-field reconstruction (T102/T103)
Replay must reproduce, per account per frame: `agent_id, wallet_units, position_units, entry_notional_units, reserved_units, realized_pnl_units, state, margin_ratio_bp, liquidation_generation, chain_id, chain_depth`.
- Initialize all accounts from bootstrap ACCOUNT SNAPSHOT (txn 1) — carries all 11 fields.
- On TRADE_SETTLE TRADE_POSTING (agent_id match): wallet_units=wallet_after_units; position_units=position_after_units; entry_notional_units=entry_notional_after_units; realized_pnl_units+=realized_pnl_delta_units; reserved_units+=reserved_delta_units.
- On MARGIN_CALL: margin_ratio_bp and maintenance are recorded; set margin_ratio_bp=mc.margin_ratio_bp, chain_id=mc.chain_id, chain_depth=mc.chain_depth, liquidation_generation=mc.liquidation_generation_after; state per verdict: PENDING_LIQUIDATION→PENDING_LIQUIDATION, OK→ACTIVE, BREACHED→LIQUIDATED. On BREACHED, the WRITE_OFF_POSTING (role ACCOUNT) sets wallet_units += wallet_delta_units (→0) and state LIQUIDATED.
- On ORDER_ARRIVAL / ORDER_CANCELLED: reserved_units += reserved_delta_units.
- **state is ONLY ever changed by MARGIN_CALL verdicts + bootstrap** (confirmed: LIQUIDATED only via BREACHED). No other transitions needed.
- **margin_ratio_bp is RECOMPUTED at each frame** (NOT taken from stale recorded values): margin_ratio_bp = None if position_units==0 else floor(risk_equity*10000/notional) where notional=|position_units|*last_ticks*mult and risk_equity = wallet_units + (position_units*last_ticks*mult - entry_notional_units). Use the frame's last_ticks as risk_mark. This formula MUST be reimplemented inside replay/ (you may NOT import ledger.account — NFR-004).

## Book reconstruction (T102/T103) + order_count
- Reconstruct bids/asks aggregation from order lifecycle events. Track individual resting orders by order_id: on ORDER_ARRIVAL(action=SUBMIT, order_type=LIMIT, accepted=true) insert order (side, price_ticks, quantity_units); on TRADE_SETTLE reduce the maker_order_id's remaining qty by quantity_units; on ORDER_CANCELLED mark cancelled qty (order gone). An order contributes to a price level iff remaining qty > 0.
- Per price level emit: price_ticks, quantity_units (sum of remaining qty), order_count (number of distinct orders with remaining qty>0 at that price).
- bids sorted by price_ticks DESCENDING; asks ASCENDING.
- last_ticks = last trade price (from TRADE_SETTLE.price_ticks) inherited across frames when no trade this frame; null before first trade.

## Exchange 2-field projection
- exchange = {fee_cash_units, risk_pnl_units}. fee_cash_units accumulates from TRADE_SETTLE (taker_fee_cash_units + maker_fee_cash_units? — check event-schema §4.2/TRADE_SETTLE for the exact fee fields; reconcile with world["exchange_fee_units"] semantics); risk_pnl_units accumulates from MARGIN_CALL WRITE_OFF_POSTING (role EXCHANGE_RISK) risk_pnl_delta_units. Bootstrap ACCOUNT SNAPSHOT payload has `exchange` object with both — initialize from there.

## mult (CRITICAL)
- mult is NOT derivable from the RUN_HEADER (ADR-001 forbids float derivation). The INTERNAL frame builder takes mult as a parameter: `_build_frames(events: list[dict], mult: int) -> list[Frame]`. This is the test-facing API for E1.
- The PUBLIC `build_replay(log_path, out_path, *, downsample=None)` does NOT take mult (uses recorded display values, not E1 comparison).
- The E1 test passes `config.mult` (default 1000) to `_build_frames`.

## Oracle (E1 test, tests/integration/test_replay_frame_consistency.py)
- Subclass EventKernel overriding `_run_transaction(self, event, handler, world)` to call super() then capture a projection of `world` (accounts/Book/exchange/mult). world is passed as an argument to _run_transaction.
- Oracle projection per frame (discard the txn-1 ACCOUNT-only capture; frames start after txn 2): for each Account object call `ledger.account.snapshot_entry(acct, risk_mark=book.last_ticks, mult=world["mult"])` (test can import ledger — only replay/ and report/ modules cannot). Book projection via a NEW `Book.level_aggregates()` method (see below) + book.last_ticks. exchange from world["exchange_fee_units"]/world["exchange_risk_pnl_units"].
- Add `Book.level_aggregates()` to `src/market_game_sim/book/orderbook.py` (purely additive, ~15 lines) returning {"bids":[{"price_ticks":p,"quantity_units":sum(q),"order_count":len(deque)}...], "asks":[...]} with bids descending/asks ascending. This is required so the oracle can read order_count.
- Produce the log for the replay by monkeypatching `market_game_sim.experiment.runner.EventKernel` to the OracleKernel subclass, calling run_one(cfg), then writing a log file from result.events (committed EVENT records) prefixed with a RUN_HEADER (build_run_header with valid strings) and suffixed with a RUN_TRAILER ({"record_kind":"RUN_TRAILER","terminated":...,"last_committed_transaction_seq":<max txn>,"record_count":len(events)+2}). The reader must accept this log.

# ===== MODULE STRUCTURE (create under src/market_game_sim/replay/) =====
- `__init__.py` — docstring, no forbidden imports.
- `reader.py` — T101 `read_log(path: Path) -> LogData` (LogData: header, events, trailer, run_id). Parse JSONL, validate RUN_HEADER first / RUN_TRAILER last / record_count. REJECT TI-4 (terminated==ABORTED) and TI-5 (structural corruption) — raise a clear exception. MUST NOT import kernel/eventlog/etc (parse JSONL directly).
- `state.py` — T102: `RebuiltState` dataclass (accounts dict, book dict, exchange dict, last_ticks) + `apply_event(state, event)` incremental updater + `initial_state_from_bootstrap(events)`.
- `frames.py` — T103: `Frame` dataclass (frame_index, transaction_seq|None, last_ticks, accounts, exchange, book) + `_build_frames(events: list[dict], mult: int) -> list[Frame]` (internal, mult param) + `build_frames_from_log(log: LogData, mult: int) -> list[Frame]`.
- `kline.py` — T203: `build_klines(events, period_ns, bar_ns=60_000_000_000) -> list[Kline]` (only completed bars, left-closed right-open, empty bar→prev close, pre-first-trade→initial_price). Kline fields: open/high/low/close/volume/trade_count.
- `downsample.py` — T204: `DownsampleRule` + `apply_downsample(frames, rule)` returning sampled frames + a visible rule description.
- `html.py` — T201/T202: `render_replay_html(log, frames, klines, downsample_desc=None) -> str` (single-file, inline data as embedded JSON, NO fetch/CDN/external fonts, self-contained JS+CSS; shows price curve, orderbook depth, account equity/position, liquidation-frame annotations, a timeline indexed by timestamp; supports drag-to-seek, variable speed, pause).
- `generate.py` — T201: `build_replay(log_path: Path, out_path: Path, *, downsample: DownsampleRule | None = None) -> None` (read log, build frames/klines, downsample if given, render HTML, write atomically to temp then replace; raise on failure). CLI `python -m market_game_sim.replay.generate --log <path> --out <out.html> [--downsample <rule>]` via argparse + `if __name__=="__main__"`.

# ===== TESTS (create these files) =====
- `tests/unit/replay/test_log_reader.py` (T101): accept a valid 3-record-structure log; reject TI-4 (ABORTED trailer) and TI-5 (missing trailer / record_count mismatch / not RUN_HEADER first). Test BOTH accept and reject sides per repo convention.
- `tests/unit/replay/test_state_rebuild.py` (T102): build a small synthetic events list (bootstrap ACCOUNT+BOOK snapshots + a TRADE_SETTLE + a MARGIN_CALL + ORDER_ARRIVAL/ORDER_CANCELLED) and assert the reconstructed accounts (wallet/position/entry/state etc.) and book aggregation (incl. order_count, multi-order same-price case).
- `tests/unit/replay/test_frame_sequence.py` (T103): assert frame count = T-1, frame 0 merges txn1+2, frame k = txn k+2; zero-business-txn run → 1 frame.
- `tests/unit/replay/test_kline.py` (T203, AC-003): period from metrics-dictionary; only completed bars; empty bar→prev close; pre-first-trade→initial_price; left-closed right-open boundary (timestamp==(k+1)*bar_ns → bar k+1).
- `tests/unit/replay/test_frame_presentation.py` (T202, AC-006): assert the HTML string contains price-curve/orderbook/account/liquidation elements; and that presentation data includes drag/velocity/pause control hooks and liquidation frames are marked. (Static/string-level assertions on the generated HTML — no browser needed.)
- `tests/unit/replay/test_downsampling.py` (T204): downsample reduces frame count; ratio/rule visible in output; downsample product NOT used for frame-consistency.
- `tests/unit/replay/test_no_kernel_import.py` (T402, AC-005): AST-scan every .py under src/market_game_sim/replay/ and assert NO import of kernel/book/ledger/eventlog (mirror tests/unit/test_core_imports.py mechanism). Test all 4 forbidden module categories explicitly.
- `tests/integration/test_replay_offline_single_file.py` (T201, AC-002): generate a replay HTML from a real small run's log; assert it's a single file with no `fetch(` / `http` / `cdn` / external font references; contains inline data.
- `tests/integration/test_replay_frame_consistency.py` (T401, AC-001/E1): the Oracle approach above. Run a real small simulation (ExperimentConfig with a market maker + 1-2 belief agents, max_transactions ~40-60 so it completes quickly and has real trades+possibly liquidations), capture oracle frames via OracleKernel, write the log, build replay frames via `_build_frames(events, mult)`, assert frame count equal AND frame keys equal AND every frame's fields equal field-by-field (accounts 11 fields per account, exchange 2, last_ticks, book aggregation 3 fields per level). If a specific frame differs, give a clear assertion message naming frame index and field.

# ===== REPO CONVENTIONS (MUST FOLLOW) =====
- ruff: line-length 100, selects E/F/I/B/UP/SIM. `from __future__ import annotations`. Type hints. Python 3.11. Match style of `src/market_game_sim/verify.py`.
- NO new dependencies (stdlib only).
- No `assert` for control flow that must survive `python -O` — raise proper exceptions.
- replay/ MUST NOT import kernel/, book/, ledger/, eventlog/ (NFR-004/E5). This includes NOT importing market_game_sim.verify if it transitively imports forbidden modules — check: verify.py imports `market_game_sim.metrics.bridge` which is allowed, but to be safe REIMPLEMENT the reconstruction inside replay/state.py and frames.py rather than importing verify.
- Follow the existing test naming/structure conventions (see tests/integration/test_experiment.py).

# ===== VERIFICATION REQUIRED (do all, in this order) =====
1. `python -m pytest tests/unit/replay/ tests/integration/test_replay_offline_single_file.py tests/integration/test_replay_frame_consistency.py -q` until green.
2. `ruff check src/market_game_sim/replay src/market_game_sim/book/orderbook.py tests/unit/replay tests/integration/test_replay_offline_single_file.py tests/integration/test_replay_frame_consistency.py` and `ruff format --check` on the same — fix ALL violations.
3. Also run the full book test suite to ensure the new `Book.level_aggregates()` didn't break anything: `python -m pytest tests/unit/book -q`.
4. Report: files created, public API signatures, how the E1 oracle was wired (kernel subclass + log production), and confirmation pytest+ruff are green for your files + book suite passes.

[MUST NOT DO]
- Do NOT modify files outside: `src/market_game_sim/replay/`, `src/market_game_sim/book/orderbook.py` (only to ADD level_aggregates — do not alter existing methods), `tests/unit/replay/`, `tests/integration/test_replay_offline_single_file.py`, `tests/integration/test_replay_frame_consistency.py`. Do NOT touch report/ (already done), spec/tasks/design docs, verify.py, pyproject.toml, tools/.
- Do NOT run `python tools/verify.py` (the whole-repo gate — I will run it). Run only the scoped pytest+ruff above.
- Do NOT import kernel/book/ledger/eventlog from replay/ code (tests MAY import them for the oracle).
- Do NOT modify existing Book methods or any other existing code.
<!-- OMO_INTERNAL_INITIATOR -->

## assistant · 2026-08-10T16:46:40Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\docs\\features\\0.1\\0.1.4-replay-and-report\\spec.md"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\docs\\features\\0.1\\0.1.4-replay-and-report\\design.md"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\docs\\features\\0.1\\0.1.4-replay-and-report\\tasks.md"})`


> [reasoning] Let me start by understanding the task. This is a large implementation task for a `replay/` module in the MarketGameSim project. Let me break it down:

1. First, I need to read the context documents to understand the spec, design, and tasks.
2. Then understand the existing source code structure.
3. Implement the replay module with all the specified files.
4. Write tests.
5. Verify with pytest and ruff.

Let me start by reading the key documents in order as specified. I'll do this in parallel where possible.

Let me start with the spec, design, tasks, and event-schema docs. These are independent reads.

Actually, let me be strategic. I'll fire up parallel explore agents for the docs and source code understanding, while I read the most critical docs myself.

Wait, the anti-duplication rule says once I delegate exploration, I should NOT do the same search myself. But here I need to deeply understand the context to implement. Let me think about the best approach.

Given the complexity, I'll:
1. Read the spec, design, tasks docs myself (critical for implementation)
2. Read the event-schema, metrics-dictionary, degenerate-states docs myself
3. Read the source files to understand (verify.py, account.py, risk.py, orderbook.py, runner.py, experiment/runner.py, eventlog/writer.py, eventlog/digest.py, bench/__main__.py)

These are all reads, not searches. Let me batch them efficiently.

Let me start with the most important docs first - the spec, design, and tasks for 0.1.4.
I'll start by reading the critical context documents in parallel, then explore the source code structure before implementing.

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\docs\features\0.1\0.1.4-replay-and-report\spec.md</path>
<type>file</type>
<content>
1: ---
2: kind: milestone
3: id: 0.1.4
4: parent: v0.1-belief-testing-laboratory
5: version: "0.1"
6: status: ready-for-development
7: gate_version: 1
8: created: 2026-08-01
9: updated: 2026-08-09
10: prerequisites:
11:   - 0.1.3
12: ---
13: 
14: # 0.1.4：回放与报告
15: 
16: > Spec: `spec.md` | Design: `design.md` | Tasks: `tasks.md`
17: 
18: ## 0. 来源与意图
19: 
20: - **版本规格**：`../spec.md`（FR-019、FR-020、SC-008、SC-006）。
21: - **PRD 来源**：`../../market-game-sim-prd.md`（PR-018—PR-020、KPI-012）。
22: - **架构来源**：`../../market-game-sim-architecture.md`（L4 呈现与报告层）、
23:   `../design.md`（v0.1 / D-7 回放架构定位）。
24: - **Contract 来源**：`../../contracts/event-schema.md`（日志结构、帧、快照）、
25:   `../../resear
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\docs\features\0.1\0.1.4-replay-and-report\design.md</path>
<type>file</type>
<content>
1: ---
2: kind: milestone
3: id: 0.1.4
4: parent: v0.1-belief-testing-laboratory
5: version: "0.1"
6: related_features: []
7: topics: [replay, report]
8: doc_kind: design
9: gate_version: 1
10: created: 2026-08-09
11: updated: 2026-08-09
12: prerequisites:
13:   - 0.1.3
14: ---
15: 
16: # 0.1.4：回放与报告 - 设计
17: 
18: > Spec: `spec.md` | Tasks: `tasks.md`
19: 
20: ## 0. 输入与约束
21: 
22: - **行为契约**：`spec.md`（FR-019/FR-020/SC-008，退出条件 E1—E5）。
23: - **架构来源**：`docs/features/0.1/design.md`（L4 呈现与报告层，只读事件日志，D-7）。
24: - **上游 Contract**：`docs/contracts/event-schema.md`（日志结构、帧、快照）、
25:   `docs/research/metrics-dictionary.md`（K 线周期、PnL 桥接）、
26:   `docs/contracts/degenerate-states.md`（经济
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\docs\features\0.1\0.1.4-replay-and-report\tasks.md</path>
<type>file</type>
<content>
1: ---
2: kind: milestone
3: id: 0.1.4
4: parent: v0.1-belief-testing-laboratory
5: version: "0.1"
6: related_features: []
7: topics: [replay, report]
8: doc_kind: tasks
9: gate_version: 1
10: created: 2026-08-01
11: updated: 2026-08-09
12: prerequisites:
13:   - 0.1.3
14: ---
15: 
16: # 0.1.4：回放与报告 - 任务
17: 
18: > Spec: `spec.md` | Design: `design.md`
19: 
20: ## 0. 来源与执行规则
21: 
22: - 行为与验收真相源：`spec.md`（FR-019/FR-020/SC-008，退出条件 E1—E5）。
23: - 技术方案与边界：`design.md`。
24: - 每个任务标注 `[合同引用]`，实现前先读对应章节，实现后以合同为裁判。
25: - 带 `[TDD]` 的任务先写失败测试；同一 Phase 内可并行项标 `[P]`。
26: - **任务编号只在本文件内唯一**；引用其他里程碑任务时必须带里程碑前缀
27:   （写 `0.1.1 T603`，不写 `T603`）。
28: - 完成且验证后立即把 `[ ]` 改为 `[x]`。
29: 
30: ##
…[truncated]
  ```
  </details>

## assistant · 2026-08-10T16:46:51Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\docs\\contracts\\event-schema.md"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\verify.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\ledger\\account.py"})`


> [reasoning] Now let me read the event-schema, metrics-dictionary, and degenerate-states docs, plus the source files I need to understand. Let me batch these reads.
Now reading the contract docs and key source files in parallel.

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\docs\contracts\event-schema.md</path>
<type>file</type>
<content>
1: # 事件 Schema 与优先级类别
2: 
3: **适用范围**：跨规格实现合同（当前交付规格 v0.1）  
4: **状态**：Stable（跨规格实现合同；变更须记 ADR 并提升 `schema_version`）  
5: **创建日期**：2026-07-29　**更新日期**：2026-08-02  
6: **支撑需求**：v0.1 / FR-004、FR-008、FR-015、KR-001—KR-006；PRD / KPI-002、KPI-006  
7: **关联**：
8: [ADR-001](../decisions/001-numeric-and-serialization-contract.md)、
9: [ADR-002](../decisions/002-same-timestamp-event-scheduling.md)、
10: [指标字典](../research/metrics-dictionary.md)
11: 
12: ## 1. 队列顺序与日志顺序
13: 
14: 队列调度和事务日志解决的是两个不同问题，使用两把键：
15: 
16: ```text
17: queue_key = (timestamp, priority_class, enqueue_seq)       # 只决定队列事件何时弹出
18: log_key   = (timestamp, transaction_seq, record_index)     # 决定日志、哈希与重放顺序
19: ```
20: 
21: - `timestamp`：
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\verify.py</path>
<type>file</type>
<content>
1: """T603 (SC-006): Independent event log verifier.
2: 
3: Reconstructs book + account state from an event log WITHOUT importing
4: ``kernel/`` or ``ledger/`` — proving the log is self-contained.
5: 
6: Termination discrimination: structural first (TI-5), then semantic (TI-4).
7: 
8: 0.1.2 extensions (T506 / KPI-006):
9: - WRITE_OFF_POSTING handling (was skipped)
10: - MARGIN_CALL field validation
11: - exchange_risk_pnl in C2
12: - Causal chain coverage check (AGENT + LIQUIDATION)
13: 
14: 0.1.2 extension (T503 / KPI-009):
15: - PnL bridge residual check (metrics.bridge.bridge_trade is a pure function
16:   of posting/valuation-mark data, not a kernel/ledger reconstruction, so
17:   importi
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\ledger\account.py</path>
<type>file</type>
<content>
1: """T401-T403: Account entity, entry_notional update, and dual-notch equity.
2: 
3: [账户 §1]   Account fields (all minimum-unit integers, ADR-001 §1).
4: [账户 §2.1] entry_notional update: same-direction / reverse / flip.
5: [账户 §2.2] unrealized_pnl + risk_equity / valuation_equity (dual notch).
6: 
7: Stdlib only (KR-005). Integer-only arithmetic. No floats.
8: 
9: Units reminder (BENCH-001):
10:     MULT = tick_size * min_quantity / cash_unit = 1000
11:     notional_cash_units = price_ticks * qty_units * MULT
12:     entry_notional_units is in cash_units (includes MULT).
13:     risk_mark is in ticks (integer); valuation_mark is in half-ticks
14:     (best_bid + best_ask, an integer 
…[truncated]
  ```
  </details>

## assistant · 2026-08-10T16:46:59Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\book\\orderbook.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\kernel\\runner.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\experiment\\runner.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\eventlog\\writer.py"})`


> [reasoning] Good. Now I need to read more source files: orderbook.py, kernel/runner.py, experiment/runner.py, eventlog/writer.py, eventlog/digest.py, bench/__main__.py, plus the metrics-dictionary §1.9 and degenerate-states docs. Let me batch these.

Also let me read the rest of event-schema.md (from line 848).
Reading the remaining source files and docs in parallel.

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\book\orderbook.py</path>
<type>file</type>
<content>
1: """T301/T307: Price-time priority order book (stdlib only, KR-005).
2: 
3: [撮合 §1.1] 买方按 price_ticks 降序、卖方按升序；同价位按 transaction_seq 升序。
4: [撮合 §6]   空簿与单边簿的 valuation_mark 退化规则。
5: [撮合 §7]   确定性：不依赖字典遍历顺序、对象哈希。
6: 
7: Structure:
8:   - ``_bids`` / ``_asks``: ``dict[int, deque[RestingOrder]]`` mapping
9:     price_ticks to a FIFO queue of orders at that level.
10:   - ``_bid_prices`` / ``_ask_prices``: sorted ``list[int]`` (ascending)
11:     maintained via ``bisect.insort`` on level creation and ``list.remove``
12:     on level depletion.  Best bid = last element; best ask = first element.
13: 
14: Within a price level, orders are appended to the right and consumed from
15: the left
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\kernel\runner.py</path>
<type>file</type>
<content>
1: """T204b/c/d + T204e3: Minimal deterministic event kernel runner.
2: 
3: [事件 Schema §1.4] 队列事件 vs 事务记录；事务内记录顺序 + 缓冲写出
4: [事件 Schema §1.5] fail-stop 失败语义：不回滚、不续跑
5: [事件 Schema §4.6.3] 强制初态快照 + bootstrap 屏障
6: 
7: This runner is **minimal**: it manages the queue, transaction sequencing,
8: buffered atomic write, and fail-stop -- but delegates matching/account
9: logic to a caller-provided ``handler`` callback.  Phase 3 (T301-T307)
10: will supply the real matching engine; Phase 2 tests inject a tiny
11: matching stub to exercise the invariants (OB-9a, OB-4 fault injection).
12: 
13: Key invariants enforced here:
14: 
15: * **§1.4 queue/record split**: only ``ORDER_ARRIVAL``/``AGENT_OB
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\experiment\runner.py</path>
<type>file</type>
<content>
1: """T601-T606: Experiment runner — multi-seed experiment runner.
2: 
3: Bootstraps the kernel, schedules observations, runs, and collects metrics
4: and classification for a configurable number of seeds.
5: """
6: 
7: from __future__ import annotations
8: 
9: import dataclasses
10: from dataclasses import dataclass, field
11: 
12: from market_game_sim.agent.handler import handle_agent_decide, handle_agent_observe
13: from market_game_sim.agent.mapping import get_mapping
14: from market_game_sim.agent.scheduler import AgentSpec
15: from market_game_sim.agent.strategy import target_position
16: from market_game_sim.book.matching import match_order
17: from market_game_sim.book.orde
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\eventlog\writer.py</path>
<type>file</type>
<content>
1: """T205: Event log writer + run metadata header.
2: 
3: [事件 Schema §6-§9] 事件日志写入器
4: [事件 Schema §6.1] RUN_HEADER (tick_size/min_quantity/cash_unit as string decimals)
5: [事件 Schema §6.2] RUN_TRAILER
6: [事件 Schema §4.6.3] bootstrap snapshots written as first two EVENTs
7: 
8: Writes a complete event log file:
9: 
10:   ``RUN_HEADER`` (exactly one, first line)
11:   ``EVENT`` × N  (at least 2: bootstrap ACCOUNT + BOOK snapshots)
12:   ``RUN_TRAILER`` (exactly one, last line)
13: 
14: Uses the canonical serializer from T104 (ADR-001 §7).  Handles fail-stop
15: (T204d): if the kernel aborts, the writer still writes the header +
16: committed records + ``ABORTED`` trailer.  Handles boo
…[truncated]
  ```
  </details>

## assistant · 2026-08-10T16:47:04Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\docs\\contracts\\event-schema.md", "offset": 848})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\eventlog\\bootstrap.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\experiment\\config.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\bench\\__main__.py"})`


> [reasoning] Now let me read the remaining files: eventlog/digest.py, eventlog/bootstrap.py, bench/__main__.py, config/types.py, the metrics-dictionary §1.9, degenerate-states, and the rest of event-schema.md (from line 848). Also I need to look at the existing test_core_imports.py to understand the import-check mechanism, and the experiment config.
Reading more source files and the rest of the event-schema doc.

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\docs\contracts\event-schema.md</path>
<type>file</type>
<content>
848: 挂入量 = ORDER_ARRIVAL.quantity_units − Σ TRADE_SETTLE.quantity_units
849:         − Σ ORDER_CANCELLED.cancelled_qty_units（同一 order_id）
850: 挂入价 = ORDER_ARRIVAL.price_ticks
851: ```
852: 
853: 重放器据此可完整重建簿。为一个可推导的状态新增记录类型，只会增加 schema 面积与
854: 哈希字段集合，且**挂入不是状态变化的原因，而是订单未被消耗的默认归宿**——撤销
855: 则相反，它是一次主动的状态变化，因此必须留痕。
856: 
857: ## 5. 因果链与引用完整性（KPI-006）
858: 
859: ### 5.1 追溯路径
860: 
861: 因果外键（ADR-002 §3）使下列路径完全在日志内可解析，无需重放。**成交的 maker/taker
862: 两侧分别按各自触发订单的 `origin` 走不同分支**——代理来源订单验证「观察→信念→决策」
863: 链，强平来源订单验证「风控决定」链，二者不可混用、也不得把强平单伪装成代理决策：
864: 
865: **`origin = AGENT`**：
866: 
867: ```text
868: trade_id
869:   → caused_by_event_id        （ORDER_ARRIVAL：哪笔订单触发了撮合）
870:   → maker_order_id / taker_
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\eventlog\bootstrap.py</path>
<type>file</type>
<content>
1: """T204e3 + T405: Bootstrap snapshot helpers.
2: 
3: [事件 Schema §4.6.3] 强制初态快照
4: 
5: Builds the two ``SNAPSHOT`` payloads that the kernel pre-enqueues at
6: ``t=0``: ``ACCOUNT`` (all accounts, sorted by ``agent_id`` codepoint
7: ascending) and ``BOOK`` (initial empty book with ``last_ticks=null``).
8: 
9: The ``ACCOUNT`` snapshot **must** include every account -- even those
10: that never trade -- because C1/C2 conservation sums need the full set
11: and the replayer cannot infer the existence of a never-traded account
12: from trade postings alone.
13: """
14: 
15: from __future__ import annotations
16: 
17: from collections.abc import Mapping
18: from typing import Any
19: 

…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\experiment\config.py</path>
<type>file</type>
<content>
1: """ExperimentConfig -- split out of runner.py so experiment/protocol.py (T603)
2: can import it without a runner.py<->protocol.py circular import (runner.py
3: wires ExperimentProtocol into run_one/run_multi_seed)."""
4: 
5: from __future__ import annotations
6: 
7: import hashlib
8: import json
9: from dataclasses import asdict, dataclass, field
10: 
11: from market_game_sim.agent.scheduler import AgentSpec
12: 
13: 
14: @dataclass
15: class ExperimentConfig:
16:     """Runtime configuration for one experiment run."""
17: 
18:     seed: int
19:     max_transactions: int
20:     initial_price_ticks: int = 10000
21:     mult: int = 1000
22:     maker_bps: int = -1
23:     taker_b
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\bench\__main__.py</path>
<type>file</type>
<content>
1: """CLI entry point (benchmarks/README.md §5):
2: 
3:     python -m market_game_sim.bench --config benchmarks/BENCH-001.yaml
4:     python -m market_game_sim.bench --calibrate
5: 
6: Prints a JSON report to stdout; does not write back into BENCH-001.yaml or
7: reference-machine.md -- freezing ``book_operations_golden`` / the reference
8: CALIB-001 timing is a separate, deliberate action requiring the
9: hardware-locking protocol in reference-machine.md §2 (not something this
10: CLI should do unattended on every run).
11: """
12: 
13: from __future__ import annotations
14: 
15: import argparse
16: import json
17: import sys
18: from statistics import median
19: 
20: from market_game
…[truncated]
  ```
  </details>

## assistant · 2026-08-10T16:47:13Z

- **tool**: `grep({"pattern": "§1\\.9|1\\.9|K.?line|kline|bar_ns|K 线", "path": "D:\\Projects\\market-game-sim\\docs\\research\\metrics-dictionary.md", "output_mode": "content", "head_limit": 60})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\tests\\unit\\test_core_imports.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\tests\\integration\\test_experiment.py", "limit": 80})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\eventlog\\digest.py"})`


> [reasoning] Now let me read the metrics-dictionary §1.9 (K-line definition), the degenerate-states doc, the existing import check test, and the existing integration test for patterns. Also need to look at the eventlog/digest.py for DIGEST_SIZE.
Reading the metrics-dictionary K-line section, degenerate-states, existing import test, and existing integration test patterns.

  <details><summary>tool output</summary>

  ```text
Found 15 match(es) in 1 file(s)

D:\Projects\market-game-sim\docs\research\metrics-dictionary.md
  128: ### 1.9 K 线周期（Q-012）
  130: **K 线以逻辑时间定义，基础周期 `bar_ns = 60 秒`**，可聚合为 5 / 15 / 60 分钟。
  137: 价格统计量、只在成交时更新；K 线以逻辑时间计（§1.4），因为它服务于等间隔检验。
  140: 每根 K 线记录：`open` / `high` / `low` / `close` / `volume` / `trade_count`。
  142: 并计入前值填充比例（§2）——跳过空 K 线会使序列不再等间隔，破坏检验前提。
  151: 第一版为 24/7 连续市场，K 线序列不间断。股票式制度引入后须补充收盘跨越与隔夜跳空
  154: #### 1.9.1 时间原点、区间归属与观察边界（0.1.2 起）
  159: **区间左闭右开**：`bar k = [k × bar_ns, (k + 1) × bar_ns)`。恰好落在边界上的成交
  160: 按左闭规则**归属新一根**：`timestamp == (k + 1) × bar_ns` 的成交属于 `bar k+1`，
  163: **观察可见性**：设 `idx(t) = floor(t / bar_ns)`；某观察在时间戳 `t` 只能看到
  170: 不依赖到达顺序或 wall-clock；上一段的可见性规则是该顺序在 K 线聚合上的直接推论，
  183: 不取更早的一笔——采样点集合本身按 `t = j × Δt`（`j` 从 0 起）生成，与 K 线的
  184: 区间归属规则（§1.9.1）各自
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\tests\unit\test_core_imports.py</path>
<type>file</type>
<content>
1: """T604 (KR-005): core domain layer has no third-party imports."""
2: 
3: import ast
4: import pathlib
5: 
6: import pytest
7: 
8: ROOT = pathlib.Path(__file__).resolve().parents[2]
9: SRC = ROOT / "src" / "market_game_sim"
10: 
11: FORBIDDEN = {
12:     "numpy",
13:     "pandas",
14:     "scipy",
15:     "matplotlib",
16:     "sklearn",
17:     "torch",
18:     "tensorflow",
19:     "jax",
20:     "tqdm",
21:     "rich",
22:     "sortedcontainers",
23:     "networkx",
24:     "sympy",
25: }
26: 
27: ALLOWED_EXTERNAL = {
28:     "yaml",
29:     "__future__",
30:     "dataclasses",
31:     "typing",
32:     "collections",
33:     "enum",
34:     "hashlib",
35:     "json",
36:     "pathlib
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\tests\integration\test_experiment.py</path>
<type>file</type>
<content>
1: """T601-T606: Experiment runner tests."""
2: 
3: from __future__ import annotations
4: 
5: from dataclasses import replace
6: 
7: import pytest
8: 
9: from market_game_sim.agent.scheduler import AgentSpec
10: from market_game_sim.experiment.protocol import ExperimentProtocol, ProtocolViolation
11: from market_game_sim.experiment.runner import (
12:     ExperimentConfig,
13:     RunResult,
14:     build_market_validation_report,
15:     build_study_report,
16:     check_paired_parity,
17:     check_shared_randomness_parity,
18:     run_multi_seed,
19:     run_one,
20:     run_paired,
21: )
22: from market_game_sim.ledger.account import Account
23: from market_game_sim.metrics.liquida
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\eventlog\digest.py</path>
<type>file</type>
<content>
1: """T206 / T206b: Event digest hash (KPI-002).
2: 
3: [事件 Schema §7] 事件摘要哈希
4: [事件 Schema E-002] 参与摘要哈希的字段（封闭清单）
5: 
6: Computes ``hashlib.blake2b`` over the E-002 hash projection of each
7: event.  The projection selects ``HASH_INCLUDE`` leaf fields (per event
8: type) and excludes causal foreign keys + ``event_id`` (``HASH_EXCLUDE``).
9: 
10: Uses ``hashlib.blake2b`` (NOT Python's built-in ``hash()`` which is
11: salted per process).  The hash input is the canonical serialization
12: (ADR-001 §7: sorted keys, no whitespace, NFC, ``ensure_ascii=False``)
13: of the projected dict.
14: 
15: T206b exercises :meth:`SchemaRegistry.check_coverage` for all 8 event
16: types: ``required =
…[truncated]
  ```
  </details>

## assistant · 2026-08-10T16:47:22Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\docs\\research\\metrics-dictionary.md", "offset": 125, "limit": 75})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\docs\\contracts\\degenerate-states.md"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\config\\serialization.py"})`


> [reasoning] Let me read the K-line section of the metrics dictionary in detail (lines 128-200), and the degenerate-states doc for TI-4/TI-5, plus the existing report/ module to understand patterns, and the config/serialization.py.
Let me read the K-line section and degenerate-states doc in detail.

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\docs\research\metrics-dictionary.md</path>
<type>file</type>
<content>
125: （ADR-001 §3）。本文所有以十进制书写的指标定义，均指其最小单位整数在报告层还原后
126: 的值。
127: 
128: ### 1.9 K 线周期（Q-012）
129: 
130: **K 线以逻辑时间定义，基础周期 `bar_ns = 60 秒`**，可聚合为 5 / 15 / 60 分钟。
131: 
132: 选逻辑时间而非成交笔数的理由：技术因子（动量、均线、MACD 一族）与统计检验都假定
133: 等间隔观测；按成交笔数分箱会使活跃时段被过度加权，同一「100 笔」在不同活跃度下
134: 跨越的真实时间差异极大。
135: 
136: **与半衰期 τ 的轴不同，不可混用**：τ 以成交笔数计（§1.5，事件时间轴），因为锚是
137: 价格统计量、只在成交时更新；K 线以逻辑时间计（§1.4），因为它服务于等间隔检验。
138: 两者换算需经该运行的实测平均成交率，且换算结果逐运行不同。
139: 
140: 每根 K 线记录：`open` / `high` / `low` / `close` / `volume` / `trade_count`。
141: **周期内无成交时不跳过该根**，`open=high=low=close=` 前一根的 `close`，`volume=0`，
142: 并计入前值填充比例（§2）——跳过空 K 线会使序列不再等间隔，破坏检验前提。
143: 
144: **首笔成交之前**（即全局尚无任何成交，不存在「前一根 close」）：`open=high=low=
145: close=ini
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\docs\contracts\degenerate-states.md</path>
<type>file</type>
<content>
1: # 退化状态行为定义
2: 
3: **适用范围**：跨规格实现合同（当前交付规格 v0.1）  
4: **状态**：Stable（跨规格实现合同；变更须记 ADR 并提升 `schema_version`）  
5: **创建日期**：2026-07-29  
6: **支撑需求**：v0.1 / FR-007、FR-018、SC-005；PRD / KPI-005  
7: **关联**：[v0.1 规格](../features/0.1/spec.md)、[指标字典](../research/metrics-dictionary.md)
8: 
9: ## 0. 原则
10: 
11: 加密式制度（v0.1 / D-1）不引入涨跌停或熔断，允许崩盘、暴涨与流动性枯竭自由涌现。
12: 
13: **「允许极端」不等于「未定义」。** 本文为每种退化状态指定确定行为，使仿真产出**有
14: 研究价值的极端样本**，而不是未定义状态、异常终止或静默的错误状态。
15: 
16: 「未定义的量」（如单边簿下的 `mid`）与「未定义的状态」是两回事：前者是合法且必须
17: 被记录的观测结果，在日志中以 `null` 表达、在分析层才成为 NaN
18: （[ADR-001](../decisions/001-numeric-and-serialization-contract.md) §6）；后者是
19: 本文要消除的对象。
20: 
21: ## 1. 订单簿退化
22: 
23: ### 1.1 空订单簿上的市价单
24: 
25: **市价单按 I
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\config\serialization.py</path>
<type>file</type>
<content>
1: """T104: Canonical JSONL serialization (ADR-001 §7).
2: 
3: Produces byte-deterministic JSON following a subset of RFC 8785 (JSON
4: Canonicalization Scheme):
5: 
6:   - Numeric values are JSON **integers** -- ``float`` is rejected.
7:   - Missing values are ``null`` (never NaN, Infinity, or empty string).
8:   - Booleans are ``true`` / ``false``.
9:   - Encoding is UTF-8 without BOM; strings are NFC-normalized;
10:     non-ASCII is **not** escaped (``ensure_ascii=False``).
11:   - Object keys are sorted by Unicode code point (``sort_keys=True``).
12:   - Separators are exactly ``,`` and ``:`` (no whitespace).
13:   - Each event occupies one line terminated by a single LF (no
…[truncated]
  ```
  </details>

## assistant · 2026-08-10T16:47:30Z


> [reasoning] Now I have a solid understanding of the codebase. Let me also check if there's a report/ module already done (since the task says "Do NOT touch report/ (already done)") and look at the existing test structure to match conventions. Let me also look at how agent scheduler works for the oracle test config, and the ledger/risk.py state machine.

Actually, I have enough context now. Let me look at a couple more things:
1. The existing `report/` module to understand the pattern (but not touch it)
2. The AgentSpec for the oracle test config
3. A quick look at the existing conftest.py if any

Let me now plan the implementation:

## Plan

### 1. `src/market_game_sim/book/orderbook.py` - Add `level_aggregates()` method
Purely additive, returns `{"bids": [...], "asks": [...]}` with price_ticks, quantity_units, order_count.

### 2. `src/market_game_sim/replay/__init__.py` - docstring only

### 3. `src/market_game_sim/replay/reader.py` - T101 Log reader
- `read_log(path: Path) -> LogData`
- `LogData` dataclass: header, events, trailer, run_id
- Parse JSONL, validate RUN_HEADER first, RUN_TRAILER last, record_count
- Reject TI-4 (ABORTED) and TI-5 (structural corruption)
- NO imports from kernel/eventlog

### 4. `src/market_game_sim/replay/state.py` - T102 State rebuild
- `RebuiltState` dataclass: accounts dict, book dict, exchange dict, last_ticks
- `apply_event(state, event)` - incremental updater
- `initial_state_from_bootstrap(events)` - initialize from bootstrap SNAPSHOTs
- Must reimplement margin_ratio_bp computation (no imports from ledger)

### 5. `src/market_game_sim/replay/frames.py` - T103 Frame sequence
- `Frame` dataclass: frame_index, transaction_seq|None, last_ticks, accounts, exchange, book
- `_build_frames(events: list[dict], mult: int) -> list[Frame]` - internal, mult param
- `build_frames_from_log(log: LogData, mult: int) -> list[Frame]`

### 6. `src/market_game_sim/replay/kline.py` - T203 K-line
- `build_klines(events, period_ns, bar_ns=60_000_000_000) -> list[Kline]`
- `Kline` dataclass: open/high/low/close/volume/trade_count
- Only completed bars, left-closed right-open, empty bar->prev close, pre-first-trade->initial_price

### 7. `src/market_game_sim/replay/downsample.py` - T204
- `DownsampleRule` + `apply_downsample(frames, rule)`

### 8. `src/market_game_sim/replay/html.py` - T201/T202
- `render_replay_html(log, frames, klines, downsample_desc=None) -> str`
- Single file, inline data, no fetch/CDN/external fonts

### 9. `src/market_game_sim/replay/generate.py` - T201
- `build_replay(log_path, out_path, *, downsample=None) -> None`
- CLI via argparse

### Tests:
- tests/unit/replay/test_log_reader.py
- tests/unit/replay/test_state_rebuild.py
- tests/unit/replay/test_frame_sequence.py
- tests/unit/replay/test_kline.py
- tests/unit/replay/test_frame_presentation.py
- tests/unit/replay/test_downsampling.py
- tests/unit/replay/test_no_kernel_import.py
- tests/integration/test_replay_offline_single_file.py
- tests/integration/test_replay_frame_consistency.py

Let me think through some key design decisions:

### Frame definition (T103, E1)
- Frame 0 = txn 1 (ACCOUNT bootstrap SNAPSHOT) + txn 2 (BOOK bootstrap SNAPSHOT) merged
- Frame k (k>=1) = complete state after txn k+2 commits
- A run with T committed transactions (T>=2) has T-1 frames (frame 0..T-2)

So the events list contains all EVENT records. I need to group them by transaction_seq.
- txn 1: SNAPSHOT ACCOUNT
- txn 2: SNAPSHOT BOOK
- txn 3..N: business transactions

Frame 0 = state after applying txn 1 + txn 2
Frame k (k>=1) = state after applying txn 1..txn (k+2)

So frames = [state after txns 1..2], [state after txns 1..3], ..., [state after txns 1..T]
That's T-1 frames total (indices 0..T-2).

### State rebuild
The `RebuiltState` needs to track:
- accounts: dict[str, dict with 11 fields]
- book orders: dict[order_id, {side, price_ticks, quantity_units, filled, cancelled}]
- exchange: {fee_cash_units, risk_pnl_units}
- last_ticks: int | None

From the design decisions:
- Initialize all accounts from bootstrap ACCOUNT SNAPSHOT (txn 1) - carries all 11 fields
- On TRADE_SETTLE TRADE_POSTING: update wallet, position, entry_notional, realized_pnl, reserved
- On MARGIN_CALL: set margin_ratio_bp, chain_id, chain_depth, liquidation_generation, state per verdict
- On ORDER_ARRIVAL / ORDER_CANCELLED: reserved_units += reserved_delta_units
- state ONLY changed by MARGIN_CALL verdicts + bootstrap
- margin_ratio_bp is RECOMPUTED at each frame

Wait, let me re-read the design decisions carefully:

> ## Account 11-field reconstruction (T102/T103)
> Replay must reproduce, per account per frame: `agent_id, wallet_units, position_units, entry_notional_units, reserved_units, realized_pnl_units, state, margin_ratio_bp, liquidation_generation, chain_id, chain_depth`.
> - Initialize all accounts from bootstrap ACCOUNT SNAPSHOT (txn 1) - carries all 11 fields.
> - On TRADE_SETTLE TRADE_POSTING (agent_id match): wallet_units=wallet_after_units; position_units=position_after_units; entry_notional_units=entry_notional_after_units; realized_pnl_units+=realized_pnl_delta_units; reserved_units+=reserved_delta_units.
> - On MARGIN_CALL: margin_ratio_bp and maintenance are recorded; set margin_ratio_bp=mc.margin_ratio_bp, chain_id=mc.chain_id, chain_depth=mc.chain_depth, liquidation_generation=mc.liquidation_generation_after; state per verdict: PENDING_LIQUIDATION->PENDING_LIQUIDATION, OK->ACTIVE, BREACHED->LIQUIDATED. On BREACHED, the WRITE_OFF_POSTING (role ACCOUNT) sets wallet_units += wallet_delta_units (->0) and state LIQUIDATED.
> - On ORDER_ARRIVAL / ORDER_CANCELLED: reserved_units += reserved_delta_units.
> - **state is ONLY ever changed by MARGIN_CALL verdicts +
