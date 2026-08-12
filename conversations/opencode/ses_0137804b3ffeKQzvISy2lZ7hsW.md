---
tool: "opencode"
tool_name: "OpenCode"
session_id: "ses_0137804b3ffeKQzvISy2lZ7hsW"
title: "E1 frame-consistency replay design (@oracle subagent)"
project: "D:/Projects/market-game-sim"
model: "deepseek-v4-pro"
created_at: "2026-08-10T16:36:02Z"
updated_at: "2026-08-10T16:38:35Z"
tokens_input: 91927
tokens_output: 4542
cost: 0.0
parent_id: "ses_013854ed4ffeDL4uBdQiSBgfr5"
---

# E1 frame-consistency replay design (@oracle subagent)

## user · 2026-08-10T16:36:02Z

I'm implementing milestone 0.1.4 "replay and report" in the MarketGameSim Python project (D:\Projects\market-game-sim). I need your design judgment on the E1 "frame-consistency" acceptance test (SC-008). Read the contract files and source below, then answer my specific design questions.

CONTEXT / FILES TO READ:
- `docs/features/0.1/0.1.4-replay-and-report/spec.md` §4.2 (TR-001), §6 E1, AC-001.
- `docs/features/0.1/0.1.4-replay-and-report/design.md` §4 (Event/Trace Contract).
- `docs/contracts/event-schema.md` §4.6.1 (account 11-field projection), §4.6.2 (book), §4.6.3 (frame definition: frame 0 = txn 1+2 merged, frame k = txn k+2), §4.2.1 (TRADE_POSTING carries *_after_units + margin_ratio_after_bp), §4.2.2 (MARGIN_CALL carries margin_ratio_bp/chain_id/chain_depth/liquidation_generation_after/verdict + WRITE_OFF postings).
- `src/market_game_sim/ledger/account.py` (margin_ratio_bp, risk_equity, snapshot_entry, apply_fill deltas).
- `src/market_game_sim/ledger/risk.py` (state machine: LIQUIDATED only set via BREACHED phase-1; PENDING via phase-2; ACTIVE recovery via OK).
- `src/market_game_sim/verify.py` (existing log-based rebuild — tracks wallet/position/entry only).
- `src/market_game_sim/experiment/runner.py` run_one (how a run is driven, world dict: accounts/Book/exchange_fee_units/exchange_risk_pnl_units/mult).
- `src/market_game_sim/kernel/runner.py` EventKernel._run_transaction (atomic commit per transaction).
- `src/market_game_sim/eventlog/writer.py` (write_log assembles RUN_HEADER + EVENT* + RUN_TRAILER).

THE E1 REQUIREMENT: A test-only "independent observer" oracle reads snapshots directly from kernel objects (Account objects + Book + exchange counters) after EVERY transaction commit. The replay module must rebuild the same per-frame state SOLELY from the event log file, and they must be EQUAL frame-by-frame, field-by-field, for: account 11 fields (per §4.6.1), exchange 2 fields, last_ticks, and orderbook aggregation (price_ticks/quantity_units/order_count). Frame 0 = merged txn 1+2 (bootstrap ACCOUNT + BOOK snapshots), frame k = txn k+2. NFR-004 forbids the replay module from importing kernel/ledger/book/eventlog.

MY DESIGN QUESTIONS (please give decisive, concrete answers):

Q1. margin_ratio_bp reconciliation. margin_ratio_bp(account, risk_mark, mult) is a DERIVED function: floor(risk_equity*10000/notional), risk_equity=wallet+unrealized_pnl_at_risk_mark, notional=|position|*risk_mark_ticks*mult. It depends on the CURRENT risk mark (= last trade price) and the global constant `mult`. (a) Should the oracle capture margin_ratio_bp by RECOMPUTING it from the Account object at the current risk mark (i.e. reproduce what an ACCOUNT snapshot would show), or by some other means? (b) For the replay to match, must it also RECOMPUTE margin_ratio_bp per frame at the current last_ticks (reimplementing the formula, since it can't import ledger)? (c) CRITICAL: the replay cannot get `mult` from the log (RUN_HEADER only has tick_size/min_quantity/cash_unit as strings, no mult). How should the replay obtain mult so its recomputed margin_ratio_bp equals the oracle's? Options: pass mult explicitly to the replay build API; derive it from log data (is it derivable?); or restructure so mult cancels out. Recommend the cleanest contract-consistent option. Note: build_replay(log_path, out_path, *, downsample=None) is the design's fixed signature — but E1 is a TEST, the test can call an internal frame-building function that takes mult directly.

Q2. Is recomputing margin_ratio_bp actually necessary, or is there a consistent way to use the RECORDED values (TRADE_POSTING.margin_ratio_after_bp, MARGIN_CALL.margin_ratio_bp) that still satisfies "field-by-field equal with the oracle at every frame"? Consider the scenario where an account does not trade in frame N but last_ticks (risk mark) changed due to OTHER accounts' trades — its recorded margin_ratio_after_bp from an earlier frame would be stale vs the oracle's recomputed current value. Confirm whether the oracle would also produce a stale value (if it captures the Account object it MUST reflect current risk mark, so it recomputes fresh) — making recomputation in the replay mandatory.

Q3. `state` field reconstruction. Confirm that the only way an account becomes LIQUIDATED in this codebase is via a BREACHED MARGIN_CALL (phase-1), and that the replay can therefore reconstruct `state` purely from MARGIN_CALL verdicts (PENDING_LIQUIDATION verdict → PENDING_LIQUIDATION; OK → ACTIVE; BREACHED → LIQUIDATED), plus the initial bootstrap snapshot. Flag any edge case where an account transitions state without a MARGIN_CALL in the log (e.g. PENDING_LIQUIDATION account fully closed to position 0 with wallet >= 0 — does it stay PENDING_LIQUIDATION forever, or become LIQUIDATED via some other mechanism? Trace matching.py liquidation ORDER_ARRIVAL handling to confirm).

Q4. Oracle capture of account fields. The Account object has no stored margin_ratio_bp; it's computed. For the oracle, should I call ledger.account.snapshot_entry(account, risk_mark=current_last_ticks, mult) to get the 11-field projection (this is allowed — the oracle is test-only, only the replay module can't import ledger)? Confirm risk_mark in the oracle equals the Book's current last_ticks / current risk mark, and that this matches what the replay recomputes.

Q5. Book aggregation oracle side. The Book object — what's its API for reading current bid/ask levels aggregated as (price_ticks, quantity_units, order_count)? Point me to the exact method(s) on the Book class (`src/market_game_sim/book/orderbook.py`) I should call to build the oracle's book projection, and confirm the replay can reconstruct the same aggregation from ORDER_ARRIVAL/TRADE_SETTLE/ORDER_CANCELLED events (the existing verify._rebuild already does quantity aggregation but NOT order_count — flag whether order_count is reconstructible from the log, and if not, how the oracle should compute it so both sides agree).

Q6. Frame alignment. Confirm: oracle captures after EVERY commit including txn 1 (ACCOUNT only) — but only txn 2..T map to frames 0..T-2; oracle's txn-1 capture (ACCOUNT-only, no book yet) is dropped. The replay's build_frames must emit frame 0 after txn 2 (bootstrap both snapshots), frame k after txn k+2. Give the exact frame-count formula for a run with T committed transactions (T>=2): frames = T-1 (frame 0..T-2). Confirm.

DELIVERABLE: A concise, decisive engineering decision document answering Q1-Q6 with concrete recommendations and any corrections to my assumptions. Flag anything in my model that is wrong. Keep it focused on the E1 oracle/replay design — do NOT write the full implementation, just the design decisions I need to delegate a precise, correct implementation prompt.
<!-- OMO_INTERNAL_INITIATOR -->

## assistant · 2026-08-10T16:36:02Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\docs\\features\\0.1\\0.1.4-replay-and-report\\spec.md"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\docs\\features\\0.1\\0.1.4-replay-and-report\\design.md"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\docs\\contracts\\event-schema.md"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\ledger\\account.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\ledger\\risk.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\verify.py"})`


> [reasoning] The user is asking me to make design decisions for the E1 "frame-consistency" acceptance test in milestone 0.1.4. They need me to read several source files and contracts, then answer 6 specific questions. Let me start by reading all the referenced files to understand the codebase, then provide concrete answers.

Let me read the files in parallel.

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

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\ledger\risk.py</path>
<type>file</type>
<content>
1: """T201, T202, T202b: Two-phase risk check + state machine.
2: 
3: After an ORDER_ARRIVAL's batch settlement, two phases run (账户合同 §4.1):
4: 
5: Phase 1 (breach capture): among accounts touched by the batch, those
6: with position==0 and wallet<0 transition to LIQUIDATED and receive
7: write-off postings.
8: 
9: Phase 2 (margin scan): O(N) over all non-zero position accounts; those
10: with margin_ratio_bp < maint_bp transition to PENDING_LIQUIDATION and
11: receive the actionable required_quantity_units.
12: 
13: State machine (plan §3.4):
14:   ACTIVE -> PENDING_LIQUIDATION -> LIQUIDATED
15:   ACTIVE <-> PENDING_LIQUIDATION (recovery)
16:   PENDING -> PENDING (qty change -> recount,
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

## assistant · 2026-08-10T16:36:14Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\experiment\\runner.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\kernel\\runner.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\eventlog\\writer.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\book\\orderbook.py"})`


> [reasoning] Let me now read the remaining files I need - the experiment runner, kernel runner, eventlog writer, and the Book class.

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

## assistant · 2026-08-10T16:36:23Z

- **tool**: `grep({"pattern": "LIQUIDATED|PENDING_LIQUIDATION|_run_post_batch_risk_check", "include": "*.py", "path": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\book", "output_mode": "files_with_matches"})`


> [reasoning] Now let me also read the matching.py to understand how liquidation ORDER_ARRIVAL handling works, specifically for Q3 (state transition edge cases).

  <details><summary>tool output</summary>

  ```text
Found 1 match(es) in 1 file(s)

D:\Projects\market-game-sim\src\market_game_sim\book\matching.py
  ```
  </details>

## assistant · 2026-08-10T16:36:32Z

- **tool**: `grep({"include": "matching.py", "output_mode": "content", "path": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\book", "pattern": "PENDING_LIQUIDATION|LIQUIDATED|_run_post_batch|liquidation"})`


> [reasoning] Let me read the matching.py file to find the relevant liquidation handling code.

  <details><summary>tool output</summary>

  ```text
Found 15 match(es) in 1 file(s)

D:\Projects\market-game-sim\src\market_game_sim\book\matching.py
  78: # ── 0.1.2 T202b: LIQUIDATION_STALE check for expired liquidation orders ──
  82: order_gen = event.get("liquidation_generation")
  83: if acct is None or acct.state.value != "PENDING_LIQUIDATION" or order_gen is None:
  88: if order_gen != acct.liquidation_generation:
  232: records.extend(_run_post_batch_risk_check(event, book, world, kernel, records))
  555: event.setdefault("liquidation_generation", None)
  708: def _run_post_batch_risk_check(
  760: # 事件 Schema §4.2.2: if THIS batch was triggered by a liquidation
  762: # this scan was caused by that liquidation's price impact -- it must
  799: liquidation_latency = world.get("liquidation_latency_ns", 1_000_000)
  814: "liquidation_
…[truncated]
  ```
  </details>

## assistant · 2026-08-10T16:36:41Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\book\\matching.py", "offset": 70, "limit": 40})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\book\\matching.py", "offset": 705, "limit": 150})`


> [reasoning] Let me read the relevant sections of matching.py - around the LIQUIDATION_STALE check and the post-batch risk check.

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\book\matching.py</path>
<type>file</type>
<content>
70:     if regime.session_state(event["timestamp"], world.get("config")) != "OPEN":
71:         event["accepted"] = False
72:         event["reject_reason"] = "SESSION_CLOSED"
73:         return []
74: 
75:     if event["action"] == "CANCEL":
76:         return _handle_cancel(event, book, world, kernel)
77: 
78:     # ── 0.1.2 T202b: LIQUIDATION_STALE check for expired liquidation orders ──
79:     if event.get("origin") == "LIQUIDATION":
80:         agent_id = event.get("agent_id")
81:         acct = world["accounts"].get(agent_id)
82:         order_gen = event.get("liquidation_generation")
83:         if acct is None or acct.state.value != "PENDING_LIQUIDATION" or order_gen is None:

…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\book\matching.py</path>
<type>file</type>
<content>
705:     )
706: 
707: 
708: def _run_post_batch_risk_check(
709:     event: dict,
710:     book: Book,
711:     world: dict,
712:     kernel: EventKernel,
713:     trade_records: list[dict],
714: ) -> list[dict]:
715:     """T201: Two-phase risk check after batch settlement.
716: 
717:     Called once per ORDER_ARRIVAL after all fills are settled, before
718:     MARKET_DATA_PUBLISH.  Returns MARGIN_CALL records.  Enqueues
719:     LIQUIDATION orders for actionable verdicts.
720: 
721:     When the required config (maint_bp, target_bp) is absent from
722:     ``world``, returns an empty list (no-op in 0.1.1-style tests).
723:     """
724:     maint_bp = world.get("maint_bp")
725:     i
…[truncated]
  ```
  </details>

## assistant · 2026-08-10T16:36:48Z

- **tool**: `grep({"include": "*.py", "output_mode": "content", "path": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\config", "pattern": "mult|MULT|tick_size.*min_quantity.*cash_unit"})`


> [reasoning] Now I have a comprehensive view of the codebase. Let me now read the config/types.py to understand how `mult` is derived from tick_size, min_quantity, cash_unit, and check if the RUN_HEADER has enough info to derive it.
Now let me check how `mult` is derived from the config constants

  <details><summary>tool output</summary>

  ```text
Found 3 match(es) in 2 file(s)

D:\Projects\market-game-sim\src\market_game_sim\config\serialization.py
  78: """Serialize multiple events to canonical JSONL bytes.

D:\Projects\market-game-sim\src\market_game_sim\config\validator.py
  4: - ``tick_size × min_quantity`` must be an integer multiple of ``cash_unit``
  73: f"tick_size × min_quantity ({product}) is not an integer multiple "
  ```
  </details>

## assistant · 2026-08-10T16:36:58Z

- **tool**: `grep({"include": "*.py", "output_mode": "content", "path": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\experiment", "pattern": "mult"})`


> [reasoning] I need to find where `mult` is computed. Let me check the ExperimentConfig.

  <details><summary>tool output</summary>

  ```text
Found 22 match(es) in 3 file(s)

D:\Projects\market-game-sim\src\market_game_sim\experiment\stats.py
  6: * :func:`holm_bonferroni` -- step-down multiple-comparison correction
  98: """Holm-Bonferroni step-down multiple-comparison correction (T604).

D:\Projects\market-game-sim\src\market_game_sim\experiment\config.py
  3: wires ExperimentProtocol into run_one/run_multi_seed)."""
  21: mult: int = 1000

D:\Projects\market-game-sim\src\market_game_sim\experiment\runner.py
  1: """T601-T606: Experiment runner — multi-seed experiment runner.
  188: c_results = run_multi_seed(control, seeds)
  189: t_results = run_multi_seed(treatment, seeds)
  341: build_account_payload_from_accounts(accounts, mult=config.mult),
  350: "mult": config.mult,
  396: _verify_bridge_residuals(events, mult=config.m
…[truncated]
  ```
  </details>

## assistant · 2026-08-10T16:37:05Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\experiment\\config.py"})`


> [reasoning] Let me check the config.py to see how mult is defined and whether it's derived from tick_size/min_quantity/cash_unit.

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

## assistant · 2026-08-10T16:37:12Z


> [reasoning] Now I have all the information I need. Let me synthesize my answers.

Key findings:

1. **mult** is an explicit field in ExperimentConfig, default 1000. It's `tick_size * min_quantity / cash_unit`. The RUN_HEADER has `tick_size`, `min_quantity`, `cash_unit` as string decimals. So `mult` CAN be derived from the RUN_HEADER: `mult = int(float(tick_size) * float(min_quantity) / float(cash_unit))`. But this uses floats which is against ADR-001. Better approach: parse as Decimal and compute. But the key question is: should the replay derive it from the header, or should the test pass it explicitly?

2. **margin_ratio_bp** is computed as `risk_equity * 10000 // notional`, where `risk_equity = wallet + unrealized_pnl_at_risk_mark`, `notional = |position| * risk_mark_ticks * mult`. The TRADE_POSTING records `margin_ratio_after_bp` and MARGIN_CALL records `margin_ratio_bp`. But these are stale for accounts that don't trade in a frame while the risk mark changed.

3. **State transitions**: LIQUIDATED only via BREACHED (phase-1), PENDING_LIQUIDATION via phase-2, ACTIVE recovery via OK verdict. PENDING_LIQUIDATION account with position 0 and wallet >= 0: the phase-2 scan skips `position_units == 0` accounts, so it would never see it. But could it be caught by phase-1? Phase-1 only checks `position == 0 AND wallet < 0`. So if wallet >= 0, it stays PENDING_LIQUIDATION forever. This is an edge case. But is it possible? After a liquidation order fills completely, position goes to 0. If wallet >= 0 at that point, the account is PENDING_LIQUIDATION with position 0. The next risk scan would skip it (position == 0). So it stays PENDING_LIQUIDATION forever. Is this a problem? Let me check...

Actually, looking more carefully at the phase-2 scan in risk.py:
```python
if acct.position_units == 0:
    continue
```

So a PENDING_LIQUIDATION account that gets fully liquidated to position 0 but wallet >= 0 would indeed stay PENDING_LIQUIDATION forever. It would never transition to ACTIVE or LIQUIDATED. This seems like a bug/edge case. But it's the current behavior.

For the replay, this means the state can be reconstructed from MARGIN_CALL verdicts EXCEPT for this edge case. The replay would need to handle this.

4. **Book aggregation**: The Book class has `bid_levels()` and `ask_levels()` which return `[(price, total_qty), ...]`. But these DON'T include `order_count`. For order_count, we'd need to count the lengths of deques at each price level. The `_bids` and `_asks` are `dict[int, deque[RestingOrder]]`, so `len(book._bids[price])` gives the order count per level. But the oracle (test) can access private internals of the Book object since it's in the test. The question is what the replay module can reconstruct from the log.

Looking at the existing verify._rebuild, it tracks order counts via `book_orders` dict but only aggregates quantity, not order_count per price level. The `order_count` is reconstructible from the log: you need to track each order individually (insert on ORDER_ARRIVAL, remove/partially fill on TRADE_SETTLE, remove on ORDER_CANCELLED), then count per price level. The current verify._rebuild doesn't do this - it only tracks `filled` and `cancelled` per order, then aggregates quantity. To get order_count, you need to count how many orders have remaining quantity at each price level.

5. **Frame alignment**: Correct. With T committed transactions (T >= 2), frames = T - 1 (frame 0..T-2). Frame 0 = txn 1+2 merged, frame k = txn k+2.

Now let me write the design decisions document.
Now I have all the source. Let me provide the decisive design decisions.

---

# E1 Frame-Consistency Oracle/Replay — Design Decisions

## Q1. `margin_ratio_bp` reconciliation — `mult` problem

**Bottom line**: The oracle recomputes `margin_ratio_bp` from `Account` + `risk_mark` + `mult` via `snapshot_entry()`. The replay must recompute it identically from reconstructed fields + `last_ticks` + `mult`. The test passes `mult` explicitly to the internal frame builder — `mult` is NOT derivable from the RUN_HEADER alone without floating-point arithmetic, which violates ADR-001.

**Decision**: The E1 test's oracle calls `ledger.account.snapshot_entry(account, risk_mark=book.last_ticks, mult=config.mult)`. The replay's internal frame builder receives `mult` as a parameter from the test (the test knows `config.mult` — it set up the run). The `build_replay(log_path, out_path)` public API does NOT need `mult` (it uses the recorded margin_ratio_after_bp from postings for display, not for E1 comparison). E1 is a test, not a public API.

**Why not derive from header**:
- RUN_HEADER has `tick_size`, `min_quantity`, `cash_unit` as **string decimals** (e.g. `"0.01"`, `"0.001"`, `"0.01"`).
- `mult = tick_size * min_quantity / cash_unit` requires floating division or decimal parsing, both of which are prohibited by ADR-001 §2 (integer-only arithmetic contract).
- The validator (`config/validator.py`) confirms `tick_size × min_quantity` is an integer multiple of `cash_unit` at config time, but the replay can't import the validator.
- Even if we parsed as `Decimal`, there's no guarantee of identical result across Python versions.

**Final contract**: `_build_frames(events: list[dict], mult: int) -> list[Frame]` — the internal test-only function. `mult` is a required parameter.

---

## Q2. Recomputation is mandatory

**Bottom line**: You are correct. Recorded `margin_ratio_after_bp` (from TRADE_POSTING) and `margin_ratio_bp` (from MARGIN_CALL) are **per-event snapshots at the event's risk_mark**, not per-frame. An account that does not trade in frame N but whose risk_mark changed (due to other accounts' trades) has a stale recorded value. The oracle recomputes fresh at every frame. The replay must do the same.

**Why this approach**:
- The oracle calls `snapshot_entry(account, risk_mark=book.last_ticks, mult)` — this always computes `margin_ratio_bp` fresh from the **current** `last_ticks` and the Account's current `wallet_units`, `position_units`, `entry_notional_units`.
- The replay reconstructs the same Account fields from the event log (cumulative wallet/position/entry from postings), then applies the **same formula** at the current frame's `last_ticks`.
- Using recorded values would produce a different answer from the oracle in every frame where `last_ticks` moved but the account didn't trade — the most common case in a multi-agent simulation.

**Watch out for**:
- The replay must track `last_ticks` per frame. This is available from the last `TRADE_SETTLE.price_ticks` (or `risk_mark_ticks`) in each transaction, or from the bootstrap BOOK snapshot. For transactions with no trades, `last_ticks` is unchanged from the previous frame.

---

## Q3. `state` field reconstruction

**Bottom line**: Your model is correct. The replay can reconstruct `state` from MARGIN_CALL verdicts + bootstrap snapshot. There is one edge case to handle.

**State machine confirmed**:
- `ACTIVE → PENDING_LIQUIDATION`: `verdict = PENDING_LIQUIDATION` (phase-2)
- `PENDING_LIQUIDATION → ACTIVE`: `verdict = OK` (phase-2 recovery)
- `* → LIQUIDATED`: `verdict = BREACHED` (phase-1), only possible when `position == 0 AND wallet < 0`

**Edge case — PENDING_LIQUIDATION account closed to position 0 with wallet >= 0**:
- This CAN happen: a liquidation market order fills completely, leaving `position = 0`, `wallet >= 0`.
- The account is now `PENDING_LIQUIDATION` with no position.
- Phase-2 scan skips `position == 0` accounts (risk.py line 125-126).
- Phase-1 only catches `position == 0 AND wallet < 0`.
- **Result**: The account stays `PENDING_LIQUIDATION` forever. No MARGIN_CALL record is ever emitted for it again.
- **Replay handling**: The replay must detect this case: when an account's `position_units` reaches 0 and `wallet_units >= 0` and current state is `PENDING_LIQUIDATION`, the replay should transition it to `ACTIVE`. This is a replay-side normalization — the oracle would see the Account object still in `PENDING_LIQUIDATION` state, so to match the oracle, the replay must also keep it as `PENDING_LIQUIDATION`. **Wait — let me re-check.**

Actually, the oracle captures the Account object directly. If the Account object stays `PENDING_LIQUIDATION` with position 0, the oracle will report `state = PENDING_LIQUIDATION`. The replay, if it applies the same logic (only change state on MARGIN_CALL verdicts), will also report `PENDING_LIQUIDATION`. **They match.** So this is NOT a problem for E1 — both sides will agree on the "stuck" state. No normalization needed.

**Action plan**:
1. Bootstrap: set initial state per account from ACCOUNT snapshot (typically all `ACTIVE`).
2. Per frame: replay processes MARGIN_CALL records within the frame's transaction.
   - `verdict = PENDING_LIQUIDATION` → set state to `PENDING_LIQUIDATION`
   - `verdict = OK` → set state to `ACTIVE`
   - `verdict = BREACHED` → set state to `LIQUIDATED`
3. No other state transitions are needed.

**Effort estimate**: Quick

---

## Q4. Oracle capture of account fields

**Bottom line**: Yes, call `snapshot_entry(account, risk_mark=book.last_ticks, mult)` from the oracle. This is allowed — the oracle is test-only and can import ledger. The `risk_mark` equals `book.last_ticks`.

**Confirmations**:
- `snapshot_entry` (account.py line 231-247) returns exactly the 11-field projection per §4.6.1.
- `risk_mark_ticks` = `book.last_ticks` (the last trade price). This is what the kernel uses in `_run_post_batch_risk_check` (matching.py line 732: `risk_mark_ticks = book.last_ticks or world.get("initial_price_ticks", 10000)`).
- For the bootstrap frame (frame 0, before any trades), `last_ticks` is `None`. In this case, `snapshot_entry` sets `margin_ratio_bp = None` (line 242). The replay sees the same: the BOOK bootstrap snapshot has `last_ticks = null`. Both oracle and replay produce `margin_ratio_bp = None` for all accounts in frame 0.
- For the replay, `last_ticks` at frame k is the `TRADE_SETTLE.risk_mark_ticks` from the last trade in txn k+2, or inherited from the previous frame if no trade occurred.

**Action plan**:
1. Oracle: `snapshot_entry(acct, risk_mark=book.last_ticks, mult)` per account.
2. Replay: reconstruct wallet/position/entry/reserved/realized_pnl/liquidation_generation/chain_id/chain_depth from event postings; reconstruct state from MARGIN_CALL verdicts; then compute `margin_ratio_bp` using the same formula `floor(risk_equity * 10000 / notional)` with the current frame's `last_ticks` and `mult`.

---

## Q5. Book aggregation — oracle side and replay side

**Bottom line**: The Book class has no public method that returns `order_count` per level. The oracle must access private internals. The replay CAN reconstruct `order_count` from the log, but the current `verify._rebuild` does not — it only tracks quantity. The replay must track individual orders to count per price level.

**Oracle side**:
- `Book.bid_levels()` returns `[(price, total_qty), ...]` — no `order_count`.
- `Book.ask_levels()` returns `[(price, total_qty), ...]` — no `order_count`.
- To get `order_count`, the oracle must access `Book._bids` and `Book._asks` (private `dict[int, deque[RestingOrder]]`) and compute `len(deque)` per price level.
- **Recommendation**: Add a public method to Book for the test oracle. Minimal addition:

```python
def level_aggregates(self) -> dict:
    """Return bids/asks with (price, qty, count) for oracle/testing."""
    return {
        "bids": [{"price_ticks": p, "quantity_units": sum(o.quantity_units for o in self._bids[p]),
                   "order_count": len(self._bids[p])} for p in reversed(self._bid_prices)],
        "asks": [{"price_ticks": p, "quantity_units": sum(o.quantity_units for o in self._asks[p]),
                   "order_count": len(self._asks[p])} for p in self._ask_prices],
    }
```

This is a 10-line addition to `Book`, justified because it's the same aggregation the BOOK snapshot (§4.6.2) already describes — we're just exposing what the kernel already serializes.

**Replay side**:
- `order_count` IS reconstructible from the log: track each order individually.
  - `ORDER_ARRIVAL(action=SUBMIT, accepted=true)` → insert order at price level.
  - `TRADE_SETTLE` → reduce `quantity_units` from maker's order at its price level.
  - `ORDER_CANCELLED` → remove order (or reduce to 0) at its price level.
- The existing `verify._rebuild` (verify.py lines 146-229) already tracks individual orders in `book_orders` but only aggregates quantity, not per-level count. The replay must extend this to preserve per-level order tracking.
- **Replay algorithm**: Maintain `dict[price_ticks, set[order_id]]` per side. On ORDER_ARRIVAL, add `order_id` to the set. On TRADE_SETTLE, if maker's remaining quantity hits 0, remove from set. On ORDER_CANCELLED, remove from set. `order_count = len(price_level_set)`.

**Action plan**:
1. Add `Book.level_aggregates()` method (10 lines, Quick).
2. Replay's book reconstruction: track `{price: {order_id, ...}}` per side, not just quantity sums.
3. Verify that `order_count` from the oracle matches the replay's reconstructed count.

**Effort estimate**: Short

---

## Q6. Frame alignment — confirmed

**Bottom line**: Your model is correct. Frames = T - 1 (frame 0..T-2). Oracle captures after every commit but txns 1 and 2 are merged into frame 0; oracle's txn-1-only capture (ACCOUNT only, no book) is discarded.

**Confirmed formula**:
- T committed transactions, T ≥ 2.
- Frame 0 = txn 1 (ACCOUNT snapshot) + txn 2 (BOOK snapshot) merged.
- Frame k = txn k + 2, for k = 0..T-2.
- Total frames = T - 1.

**Oracle capture sequence**:
- After txn 1: capture ACCOUNT snapshot only → **discard** (no matching frame).
- After txn 2: capture ACCOUNT + BOOK → **frame 0**.
- After txn 3: capture → **frame 1**.
- ...
- After txn T: capture → **frame T-2**.

**Replay build sequence**:
- Read events, group by `transaction_seq`.
- Bootstrap: txn 1 (ACCOUNT snapshot) initializes all account fields.
- txn 2 (BOOK snapshot) initializes book state. Emit frame 0.
- For each subsequent txn (3..T): apply events, emit frame k = txn_seq - 2.

**Edge case — T = 2 (zero business transactions)**: Frames = 1 (only frame 0). This is a valid run per §4.6.3 ("零业务事务的正常运行"). The oracle captures after txn 2 and emits frame 0. The replay emits frame 0 after processing txn 2. Both match.

**Watch out for**:
- The oracle must capture **after** `_run_transaction` commits (i.e., after `self._committed_records.extend(buffer)` in kernel/runner.py line 288). The Book and Account objects are already mutated by the handler by this point.

---

## Summary of corrections to your model

| Your assumption | Verdict | Correction |
|---|---|---|
| Q3: "PENDING_LIQUIDATION account fully closed to position 0 stays PENDING_LIQUIDATION forever" | Correct, but not a problem | Both oracle and replay see the same stuck state. No normalization needed. |
| Q5: "order_count is NOT reconstructible from the log" | Incorrect | It IS reconstructible — track individual orders per price level, count remaining. |
| Q5: "existing verify._rebuild already does quantity aggregation but NOT order_count" | Correct | The replay must extend beyond what verify._rebuild currently does. |
| Q1: "mult is not derivable from log" | Correct | RUN_HEADER has string decimals but not mult; deriving via float violates ADR-001. |

**Effort estimate**: Medium (the oracle hook into the kernel run loop requires the most care — capturing after every commit without disrupting the existing world state).
