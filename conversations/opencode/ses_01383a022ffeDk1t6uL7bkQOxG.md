---
tool: "opencode"
tool_name: "OpenCode"
session_id: "ses_01383a022ffeDk1t6uL7bkQOxG"
title: "Map event log format and transactions (@explore subagent)"
project: "D:/Projects/market-game-sim"
model: "deepseek-v4-flash"
created_at: "2026-08-10T16:23:21Z"
updated_at: "2026-08-10T16:24:44Z"
tokens_input: 52120
tokens_output: 1295
cost: 0.0
parent_id: "ses_013854ed4ffeDL4uBdQiSBgfr5"
---

# Map event log format and transactions (@explore subagent)

## user · 2026-08-10T16:23:21Z

[CONTEXT] I'm implementing milestone 0.1.4 "replay and report" for the MarketGameSim Python project at D:\Projects\market-game-sim. The replay module must parse an event log (JSONL: RUN_HEADER + EVENT* + RUN_TRAILER) and rebuild per-frame state (account, orderbook, price) purely from the log, WITHOUT importing kernel/book/ledger/eventlog.

[GOAL] Understand the exact event log format, transaction types, and field semantics so I can write a standalone log reader and state rebuilder. I'll use this to implement T101 (log reader), T102 (state rebuild), T103 (frame sequence), and T401 (frame-consistency oracle).

[DOWNSTREAM] I will write replay/ modules that parse and rebuild state; I need the precise event schema.

[REQUEST] (1) Read docs/contracts/event-schema.md fully and report: the three top-level record types (RUN_HEADER/EVENT/RUN_TRAILER), the transaction types (especially ACCOUNT/BOOK bootstrap transactions and how transactions are sequenced with transaction_seq), the per-field account projection (11 fields, section 4.6.1), exchange projection (2 fields), price state (last_ticks), orderbook aggregation (price_ticks/quantity_units/order_count), and the SNAPSHOT/frame semantics (4.6.3). (2) Find the eventlog source code (likely src/market_game_sim/eventlog/) and report how events are serialized to JSONL, what the RUN_HEADER/RUN_TRAILER contain, and the transaction dispatch structure. (3) Report the digest helper at eventlog/digest.py (DIGEST_SIZE, blake2b) and how event digest hashes are computed. Return concrete code snippets and field lists.
<!-- OMO_INTERNAL_INITIATOR -->

## assistant · 2026-08-10T16:23:21Z

- **tool**: `glob({"pattern": "**/event-schema.md"})`
- **tool**: `glob({"pattern": "**/eventlog/**/*.py"})`
- **tool**: `glob({"pattern": "**/digest.py"})`
- **tool**: `grep({"pattern": "RUN_HEADER|RUN_TRAILER", "output_mode": "files_with_matches"})`


> [reasoning] Let me start by understanding the structure and finding the relevant files. Let me launch parallel searches.

  <details><summary>tool output</summary>

  ```text
Found 1 file(s)

D:\Projects\market-game-sim\docs\contracts\event-schema.md
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
Found 11 file(s)

D:\Projects\market-game-sim\src\market_game_sim\eventlog\bootstrap.py
D:\Projects\market-game-sim\tests\unit\eventlog\test_termination.py
D:\Projects\market-game-sim\tests\unit\eventlog\test_digest.py
D:\Projects\market-game-sim\tests\unit\eventlog\test_writer.py
D:\Projects\market-game-sim\tests\unit\eventlog\test_record_kinds.py
D:\Projects\market-game-sim\tests\unit\eventlog\test_bootstrap.py
D:\Projects\market-game-sim\src\market_game_sim\eventlog\digest.py
D:\Projects\market-game-sim\src\market_game_sim\eventlog\writer.py
D:\Projects\market-game-sim\tests\unit\eventlog\__init__.py
D:\Projects\market-game-sim\src\market_game_sim\eventlog\termination.py
D:\Projects\market-game-sim\src\market_game_sim\eventlog\__init__.py
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
Found 1 file(s)

D:\Projects\market-game-sim\src\market_game_sim\eventlog\digest.py
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
Found 45 match(es) in 45 file(s)

D:\Projects\market-game-sim\benchmarks\BENCH-001.yaml

D:\Projects\market-game-sim\conversations\timeline.md

D:\Projects\market-game-sim\docs\research\metrics-dictionary.md

D:\Projects\market-game-sim\conversations\opencode\ses_03e4b16adffeQtQ8QH80AJ5KuY.md

D:\Projects\market-game-sim\conversations\opencode\ses_03e4820e6ffeyiuCCpuH1ZpiS0.md

D:\Projects\market-game-sim\conversations\opencode\ses_03e345823ffe4GHofYTghZET5Y.md

D:\Projects\market-game-sim\tests\unit\test_verify.py

D:\Projects\market-game-sim\conversations\opencode\ses_03e33ccadffe4gCUzhcF6R5Ff4.md

D:\Projects\market-game-sim\conversations\opencode\ses_03de106b7ffe8mle4yIDv9euEU.md

D:\Projects\market-game-sim\conversations\opencode\ses_03dca8ceeffer5HK1H5NpzxJb9.md

D:\Projects\market-g
…[truncated]
  ```
  </details>

## assistant · 2026-08-10T16:23:30Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\docs\\contracts\\event-schema.md"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\eventlog\\digest.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\eventlog\\writer.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\eventlog\\bootstrap.py"})`


> [reasoning] Let me read the key files: event-schema.md, digest.py, writer.py, bootstrap.py, termination.py, eventlog/__init__.py, and the task file for 0.1.4.

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

## assistant · 2026-08-10T16:23:37Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\docs\\contracts\\event-schema.md", "offset": 848})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\eventlog\\termination.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\eventlog\\__init__.py"})`


> [reasoning] Let me read the rest of event-schema.md (from line 848), and the termination.py, eventlog/__init__.py, and the RUN_HEADER/RUN_TRAILER sections. Let me also look at the runner.py for the dispatch structure and transaction_seq.
Let me read the rest of the schema doc and the remaining eventlog source files.

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
<path>D:\Projects\market-game-sim\src\market_game_sim\eventlog\termination.py</path>
<type>file</type>
<content>
1: """T204e2: Termination classification -- TI-4 vs TI-5.
2: 
3: [事件 Schema §1.5] 先结构后语义
4: [退化状态 §4.1] TI-4 / TI-5 互斥
5: 
6: A log is classified in two phases; the order is fixed:
7: 
8: Phase 1 (structure) -- any failure -> **TI-5**:
9:   - Every line is valid JSON (no truncation, no parse error).
10:   - First record is ``RUN_HEADER``, last is ``RUN_TRAILER``.
11:   - ``record_count`` equals the actual number of lines.
12: 
13: Phase 2 (semantics) -- only when phase 1 passes:
14:   - ``terminated = COMPLETED`` -> **VALID**.
15:   - ``terminated = ABORTED``   -> **TI-4**.
16: 
17: A log with ``ABORTED`` trailer that is also truncated is **TI-5**,
18: not TI-4: when the structu
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\eventlog\__init__.py</path>
<type>file</type>
<content>
1: """Event log layer: writer (T205), digest (T206/T206b), termination (T204e2), bootstrap (T204e3)."""

(End of file - total 1 lines)
</content>
  ```
  </details>

## assistant · 2026-08-10T16:23:46Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\kernel\\runner.py"})`
- **tool**: `glob({"pattern": "**/config/serialization.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\docs\\features\\0.1\\0.1.4-replay-and-report\\tasks.md"})`


> [reasoning] Now I need the transaction dispatch structure. That's in kernel/runner.py (EventKernel, TransactionHandler). Let me read that. Also look at the 0.1.4 tasks file for context on T101/T102/T103/T401. And the serialization module.
Now let me read the kernel runner (dispatch structure), the serialization module, and the 0.1.4 tasks file for context.

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
Found 1 file(s)

D:\Projects\market-game-sim\src\market_game_sim\config\serialization.py
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

## assistant · 2026-08-10T16:24:03Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\config\\serialization.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\schema\\registry.py"})`


> [reasoning] I have almost everything. Let me read serialization.py for canonical_serialize/serialize_event. Also check the schema registry for EVENT_COMMON fields and QUEUE_EVENTS, and the 0.1.4 design.md for state rebuild expectations. Let me also check ledger/account snapshot_entry and the schema event_fields.json to know exact field ordering. Let me read serialization.py and registry.py.
Let me read the serialization module and the schema registry to complete the picture.

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

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\schema\registry.py</path>
<type>file</type>
<content>
1: """T204f: Field registry -- loads ``event_fields.json`` as the single source of truth.
2: 
3: This module loads the canonical field schema (事件 Schema E-002 同步强制) and
4: provides query interfaces consumed by:
5: 
6: - **T205** (event log writer): serialization field set and order per record kind.
7: - **T206** (event digest hash): E-002 hash projection -- which leaf fields are
8:   ``HASH_INCLUDE`` vs ``HASH_EXCLUDE``.
9: - **T206b** (hash coverage check): ``required == include ∪ exclude`` and the
10:   two sets are disjoint.
11: 
12: The registry **never** embeds a second field declaration -- it only loads and
13: queries the JSON.  Pure stdlib (KR-005): ``json`` + ``importlib.res
…[truncated]
  ```
  </details>

## assistant · 2026-08-10T16:24:19Z

- **tool**: `grep({"pattern": "EVENT_COMMON|RUN_HEADER|RUN_TRAILER", "include": "event_fields.json", "output_mode": "content", "path": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\schema"})`
- **tool**: `grep({"pattern": "snapshot_entry|def snapshot", "include": "*.py", "output_mode": "content", "path": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\ledger"})`


> [reasoning] I have comprehensive info now. Let me also glance at the EVENT_COMMON fields and the 0.1.4 design.md for state rebuild specifics, and ledger/account snapshot_entry. Let me quickly check event_fields.json for EVENT_COMMON field list and the design.md. Actually, I have enough. But let me confirm EVENT_COMMON fields and the design.md state rebuild approach. Let me grep EVENT_COMMON in event_fields.json.

Actually I have enough to give a comprehensive answer. Let me check the design.md for the 0.1.4 state rebuild intent quickly and EVENT_COMMON. Let me do a quick grep.

  <details><summary>tool output</summary>

  ```text
Found 8 match(es) in 1 file(s)

D:\Projects\market-game-sim\src\market_game_sim\schema\event_fields.json
  27: "note": "字段一律【恒存在】：required 只有 always，序列化不得省略任何字段（事件 Schema §9）。条件性表达的是【值】而非【是否存在】，写在结构化 constraints 中，不使用自然语言。constraints 的 then 取 null | non_null；when 为可判定谓词。hash 对 RUN_HEADER / RUN_TRAILER 恒为 HASH_EXCLUDE。",
  142: "RUN_HEADER",
  144: "RUN_TRAILER"
  147: "RUN_HEADER": {
  154: "RUN_HEADER"
  237: "RUN_TRAILER": {
  244: "RUN_TRAILER"
  329: "EVENT_COMMON": {
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
Found 3 match(es) in 2 file(s)

D:\Projects\market-game-sim\src\market_game_sim\ledger\account.py
  231: def snapshot_entry(account: Account, risk_mark_ticks: int | None, mult: int) -> dict[str, Any]:

D:\Projects\market-game-sim\src\market_game_sim\ledger\__init__.py
  13: snapshot_entry,
  47: "snapshot_entry",
  ```
  </details>

## assistant · 2026-08-10T16:24:33Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\schema\\event_fields.json", "offset": 329, "limit": 60})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\ledger\\account.py", "offset": 225, "limit": 40})`


> [reasoning] Let me read the EVENT_COMMON structure in event_fields.json and the snapshot_entry function in account.py.

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\schema\event_fields.json</path>
<type>file</type>
<content>
329:     "EVENT_COMMON": {
330:       "kind": "event_common",
331:       "fields": {
332:         "record_kind": {
333:           "value_type": "enum",
334:           "enum": [
335:             "EVENT"
336:           ],
337:           "nullable": false,
338:           "required": "always",
339:           "hash": "HASH_EXCLUDE"
340:         },
341:         "schema_version": {
342:           "value_type": "int",
343:           "nullable": false,
344:           "required": "always",
345:           "hash": "HASH_INCLUDE"
346:         },
347:         "event_id": {
348:           "value_type": "str",
349:           "nullable": false,
350:           "required": "always",
351:         
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\ledger\account.py</path>
<type>file</type>
<content>
225:     """``ceil(10000 / leverage_tier)`` (账户合同 §3.1, §3.1.1 向上)."""
226:     if leverage_tier <= 0:
227:         raise ValueError(f"leverage_tier must be positive, got {leverage_tier}")
228:     return div_ceil(10000, leverage_tier)
229: 
230: 
231: def snapshot_entry(account: Account, risk_mark_ticks: int | None, mult: int) -> dict[str, Any]:
232:     """Build an ``ACCOUNT_SNAPSHOT_ENTRY`` dict from an account (event Schema §4.6.1)."""
233:     return {
234:         "agent_id": account.agent_id,
235:         "wallet_units": account.wallet_units,
236:         "position_units": account.position_units,
237:         "entry_notional_units": account.entry_notional_units,
238:         "r
…[truncated]
  ```
  </details>

## assistant · 2026-08-10T16:24:44Z


> [reasoning] I have comprehensive information. Let me check the 0.1.4 design.md briefly to understand the state rebuild intent, and also the frame definition. Actually I have plenty. Let me quickly check the 0.1.4 design.md for the state rebuild approach and import boundary, so the answer is complete. Let me grep for T101/T102/T103 in design.md. Actually I have enough from tasks.md and the schema. Let me give the final answer.

I have all the information needed. Let me compose the comprehensive answer.
I have gathered comprehensive information from the schema contract, the eventlog source, the kernel runner dispatch, the digest helper, the serialization module, the schema registry, and the 0.1.4 tasks. Here is the complete report.

<results>
<files>
- /docs/contracts/event-schema.md - The canonical event schema contract (schema_version=2). Covers log keys, priority classes, all 8 event types, bootstrap/frame semantics, run metadata, E-002 hash projection, serialization. Read this first.
- /src/market_game_sim/kernel/runner.py - EventKernel: the transaction dispatch engine. Shows how transaction_seq, record_index, event_id, enqueue_seq, EVENT_COMMON fields are assigned; r0 construction; fill_index/fill_count backfill; RUN_TRAILER build.
- /src/market_game_sim/eventlog/writer.py - T205: builds RUN_HEADER dict and writes header+events+trailer as JSONL lines.
- /src/market_game_sim/eventlog/bootstrap.py - T204e3/T405: builds the ACCOUNT and BOOK snapshot payloads (frame 0 content).
- /src/market_game_sim/eventlog/digest.py - T206/T206b: blake2b digest helper (DIGEST_SIZE=32), E-002 projection, rolling_digest.
- /src/market_game_sim/eventlog/termination.py - T204e2: TI-4 vs TI-5 classification (phase 1 structure, phase 2 semantics). Needed for T101's log rejection.
- /src/market_game_sim/config/serialization.py - T104: canonical JSONL serializer (sorted keys, no whitespace, integers only, LF-terminated lines). Parsing side just needs json.loads per line.
- /src/market_game_sim/schema/registry.py - SchemaRegistry: QUEUE_EVENTS, TRANSACTION_RECORDS, priority_class map, EVENT_COMMON field definitions, E-002 hash projection, serialization_fields.
- /src/market_game_sim/schema/event_fields.json - The normative machine-readable schema (single source of truth for field sets).
- /src/market_game_sim/ledger/account.py - snapshot_entry(): produces the 11-field ACCOUNT_SNAPSHOT_ENTRY.
- /docs/features/0.1/0.1.4-replay-and-report/tasks.md - T101/T102/T103/T401 task definitions and verify targets.
</files>

<answer>
Here is the precise event log format you need for the standalone replay/reader. The contract source of truth is `docs/contracts/event-schema.md`; the machine-readable field truth is `schema/event_fields.json`.

## 1. Top-level record types (Section 6)

A JSONL file is exactly:
```
RUN_HEADER          exactly one, first line
EVENT * N           at least 2; first two are t=0 ACCOUNT/BOOK SNAPSHOTs
RUN_TRAILER         at most one, last line
```
All records discriminated by top-level `record_kind` in {"RUN_HEADER","EVENT","RUN_TRAILER"}. Only `EVENT` records participate in the digest hash.

**RUN_HEADER (Section 6.1)** — `build_run_header()` in writer.py:
`record_kind`="RUN_HEADER", `schema_version`=2, `run_id`, `code_version` (git SHA, +`-dirty`), `config_hash` (blake2b hex of canonical config), `master_seed` (int), `started_at_wall` (RFC3339 str), `tick_size`/`min_quantity`/`cash_unit` (STRING decimals like "0.01", NOT floats), `run_mode` ("benchmark"|"research"|"interactive"), `information_set_mode` ("digest"|"full").

**RUN_TRAILER (Section 6.2)** — `build_trailer()` in runner.py:
`record_kind`="RUN_TRAILER", `terminated` ("COMPLETED"|"ABORTED"), `abort_code` (null if COMPLETED; else one of QUEUE_KEY_MONOTONICITY / CLASS_REGRESSION_NOT_WHITELISTED / CONSERVATION_BREACH / ILLEGAL_STATE_TRANSITION / CONFIG_INVARIANT / INTERNAL), `abort_detail` (free text, never parsed), `last_committed_transaction_seq` (int|null; equals max transaction_seq seen in log — assert this), `record_count` (total records incl header+trailer — assert equals actual line count).

T101 must reject TI-4/TI-5 logs using `termination.classify_log()`: Phase 1 (structure: every line valid JSON, first=RUN_HEADER, last=RUN_TRAILER, record_count==line count) then Phase 2 (ABORTED→TI-4, else VALID). Order is fixed.

## 2. EVENT common fields + transaction sequencing

**EVENT_COMMON** (on every EVENT, assigned in `_build_record()` runner.py): `record_kind`="EVENT", `schema_version`, `event_id` (format `f"e{transaction_seq}_{record_index}"`), `run_id`, `timestamp` (int ns), `transaction_seq`, `record_index`, `priority_class` (0-5), `event_type`. Queue events also carry `enqueue_seq` (int, set to `null`/omitted for transaction records — it's set to `None` for non-r0 records).

**Sequencing** (`_run_transaction()` runner.py):
- `transaction_seq` increments once per popped queue event (starts at 1).
- `record_index`: r0 (the parent queue event) = 0; transaction records = 1,2,... in order. All records in one transaction share the same `transaction_seq`.
- r0 `event_id` = `e{txn}_{0}`; handlers reference it as `caused_by_event_id`.
- `fill_index`/`fill_count` on TRADE_SETTLE are backfilled after matching (fill_count = number of TRADE_SETTLEs in the transaction).
- Buffered atomic write: a transaction is committed all-or-nothing (records buffered, never partially written).

**Frozen transaction record order (Section 1.4)**: r0 (ORDER_ARRIVAL), then matching records (TRADE_SETTLE/ORDER_CANCELLED interleaved), then MARGIN_CALLs (batch-end scan, by agent_id ascending), then optionally MARKET_DATA_PUBLISH (always last, only if book changed). `accepted=false` transactions contain only r0.

**8 event types, priority class map (registry.priority_class):**
- class 0: ORDER_ARRIVAL (queue), ORDER_CANCELLED (transaction record)
- class 1: TRADE_SETTLE (record), MARGIN_CALL (record)
- class 2: MARKET_DATA_PUBLISH (record)
- class 3: AGENT_OBSERVE (queue)
- class 4: AGENT_DECIDE (queue)
- class 5: SNAPSHOT (queue)

QUEUE_EVENTS = {ORDER_ARRIVAL, AGENT_OBSERVE, AGENT_DECIDE, SNAPSHOT}; TRANSACTION_RECORDS = {ORDER_CANCELLED, TRADE_SETTLE, MARGIN_CALL, MARKET_DATA_PUBLISH}.

## 3. Bootstrap / ACCOUNT / BOOK transactions (frame 0, Section 4.6.3)

Kernel pre-enqueues two SNAPSHOT queue events at t=0: ACCOUNT (enqueue_seq=0 → transaction_seq=1) then BOOK (enqueue_seq=1 → transaction_seq=2). Business transactions start at transaction_seq=3. Frame definition (Section 4.6.3 "帧的定义"): **frame 0 = the state after transaction_seq=1 and 2; frame k = state after transaction_seq=k+2 commits.** Frame boundaries are transaction boundaries, not record boundaries.

The ACCOUNT snapshot payload (bootstrap.py `build_account_payload`) = `{"accounts": [...], "exchange": {"fee_cash_units": int, "risk_pnl_units": int}}`. Accounts sorted by agent_id codepoint ascending. Includes ALL accounts (even never-traded) because C1/C2 conservation needs the full set and the replayer can't infer a never-traded account from postings.

**ACCOUNT_SNAPSHOT_ENTRY — 11 leaf fields (closed, Section 4.6.1):** `agent_id` (str), `wallet_units` (int), `position_units` (int, signed), `entry_notional_units` (int), `reserved_units` (int), `realized_pnl_units` (int), `state` (ACTIVE|PENDING_LIQUIDATION|LIQUIDATED), `margin_ratio_bp` (int, NULL when no position), `liquidation_generation` (int), `chain_id` (str|null, non-null only when PENDING_LIQUIDATION), `chain_depth` (int|null, same). Produced by `ledger/account.snapshot_entry()`. The exchange risk account is NOT in `accounts` — it lives in `payload.exchange` (2 fields: `fee_cash_units`, `risk_pnl_units`).

**BOOK snapshot payload** (`build_book_payload`): `{"bids": [...], "asks": [...], "last_ticks": int|null}`. `last_ticks` is null before first trade. v0.1 initial book is ALWAYS empty (no pre-seeded orders). Each `BOOK_LEVEL` = 3 fields: `price_ticks` (int), `quantity_units` (int, aggregated), `order_count` (int). Bids sorted by price descending, asks ascending.

## 4. Price state / orderbook aggregation for rebuild

`MARKET_DATA_PUBLISH` (Section 4.3) carries the book summary: `best_bid`, `best_ask`, `bid_depth_k`, `ask_depth_k`, `last`. Undefined values are `null` (never NaN). For rebuilding the per-level book you apply the order lifecycle: rested quantity = `ORDER_ARRIVAL.quantity_units` − Σ `TRADE_SETTLE.quantity_units` − Σ `ORDER_CANCELLED.cancelled_qty_units` (per order_id), rested price = `ORDER_ARRIVAL.price_ticks` (Section 4.7). RESTED orders produce no record — they are the default destiny of unconsumed orders.

## 5. Digest helper (digest.py) — needed for T401 oracle / determinism checks

- `DIGEST_SIZE = 32` (blake2b).
- `event_digest(event, registry)`: blake2b over `canonical_serialize(event_hash_input(...))` of the E-002 projection.
- `event_hash_input()` = EVENT_COMMON included fields ∪ event-type-specific included fields. Excluded: `record_kind`, `event_id`, `run_id`, and causal FK/implementation fields (`trade_id`, `information_set`, `internal_state`, `submitted_at`, `observation_event_id`, `decision_event_id`, `intent_id`, `caused_by_event_id`, `market_data_event_id`, `risk_mark_event_id`).
- `rolling_digest(events, registry)`: feeds each event's digest into one rolling blake2b in log_key order. Only EVENT records.
- Canonical serialization (serialization.py): integers only, sorted keys, no whitespace separators, NFC, ensure_ascii=False, LF per line.

Per-event HASH_INCLUDE lists are in Section 7 E-002 (e.g. TRADE_POSTING all 15 leaves, WRITE_OFF_POSTING all 8 leaves; SNAPSHOT = `snapshot_type` + `payload`).

## 6. Dispatch structure in the kernel (what you must NOT import, only mirror in logic)

The `replay/` module must not import `kernel/`, `ledger/`, `book/`, or `eventlog/` (T402 import check, tasks line 83). The dispatch is `EventKernel._run_transaction()` (runner.py): pop queue event → `handler(event, world, kernel)` returns records → build r0 → backfill fill_index/count → assign record_index → validate order → commit. Your replayer replaces this: iterate log in log_key order `(timestamp, transaction_seq, record_index)`, group records by transaction_seq, apply state changes per record.

Key state-rebuild inputs per record:
- ACCOUNT changes come from `TRADE_SETTLE.postings` (2 TRADE_POSTINGs, order `[MAKER, TAKER]`), `ORDER_ARRIVAL.reserved_delta_units`, and `MARGIN_CALL.postings` (2 WRITE_OFF_POSTINGs, order `[ACCOUNT, EXCHANGE_RISK]` only when verdict=BREACHED, else []).
- TRADE_POSTING (15 fields): posting_type, agent_id, role, wallet_delta_units, position_delta_units, entry_notional_delta_units, realized_pnl_delta_units, fee_delta_units, reserved_delta_units, wallet_after_units, position_after_units, entry_notional_after_units, equity_after_units, margin_ratio_after_bp, risk_pnl_delta_units (always 0 for trades).
- WRITE_OFF_POSTING (8 fields): posting_type, role, agent_id, wallet_delta_units, wallet_after_units, position_after_units, entry_notional_after_units, risk_pnl_delta_units. ACCOUNT side: wallet_delta = −wallet_before (positive), wallet_after=0, pos=0, entry_notional=0, risk_pnl=0; EXCHANGE_RISK side: agent_id=null, wallet_delta=0, wallet_after/pos/entry_notional=null, risk_pnl_delta=wallet_before (negative). C2 conservation: the two deltas sum to zero.

For T103 frame sequence: emit one frame per distinct `transaction_seq` (frames 1..N correspond to transaction_seq 1..N), each being the full post-transaction state (accounts + book + price). Frame 0/1 = transaction_seq 1, frame 2 = transaction_seq 2, frame k = transaction_seq k. T401 compares every such frame field-by-field against a test-only oracle that reads live kernel state directly (never the log's SNAPSHOT records).
</answer>

<next_steps>
1. Implement the log reader: parse each line with `json.loads` (canonical output is just standard JSON per line), discriminate by `record_kind`, and implement the TI-4/TI-5 rejection logic exactly as in `termination.py` (structural phase before semantic phase).
2. For state rebuild, seed frame 0 from the two SNAPSHOT events (ACCOUNT entry list + BOOK payload + `exchange`), then apply per-transaction: order additions/cancellations to the book, postings to accounts, MARGIN_CALL write-offs, and update `last_ticks` from TRADE_SETTLE/price changes.
3. For T401, use `event_digest`/`rolling_digest` and the E-002 projection (via `schema/registry.py` `hash_include_leaves`/`get_leaf_fields`) only if you need determinism checks; the core requirement is per-field frame equality against a live-kernel observer, not the hash.
4. Verify against the exact field lists by reading `schema/event_fields.json` (the normative source) for the specific event type structures you consume, and run `python tools/verify.py` before committing (per repo convention). Note the replayer must NOT import kernel/ledger/book/eventlog (T402), so read field sets from the JSON/registry, not from those modules.
</next_steps>
</results>
