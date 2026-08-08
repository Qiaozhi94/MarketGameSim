---
tool: "opencode"
tool_name: "OpenCode"
session_id: "ses_03e345823ffe4GHofYTghZET5Y"
title: "Phase 2A: Core event kernel (@Sisyphus-Junior subagent)"
project: "D:/Projects/market-game-sim"
model: "glm-5.2"
created_at: "2026-08-02T09:26:17Z"
updated_at: "2026-08-02T09:27:15Z"
tokens_input: 55488
tokens_output: 888
cost: 0.0
parent_id: "ses_03e4b16adffeQtQ8QH80AJ5KuY"
---

# Phase 2A: Core event kernel (@Sisyphus-Junior subagent)

## user · 2026-08-02T09:26:17Z

## TASK
Implement Phase 2A of the market-game-sim 0.1.1: core event kernel (T201-T204e3). This covers the event queue system, priority classes, log keys, fail-stop semantics, and bootstrap snapshots.

## EXPECTED OUTCOME
All tasks T201-T204e3 complete with passing tests:
- `src/market_game_sim/kernel/__init__.py` + `src/market_game_sim/kernel/keys.py` - dual key system
- `src/market_game_sim/kernel/enums.py` - priority class enum
- `src/market_game_sim/kernel/queue.py` - event queue with monotonicity
- `src/market_game_sim/kernel/transaction.py` - transaction buffer with fail-stop
- `src/market_game_sim/kernel/bootstrap.py` - bootstrap snapshot barrier
- `src/market_game_sim/kernel/event_log.py` - event log writer with RUN_HEADER/EVENT/RUN_TRAILER
- `tests/unit/kernel/` - all unit tests

## REQUIRED TOOLS
- Read, Write, Edit, Bash (pytest), Glob, Grep
- Read existing code: `src/market_game_sim/config/types.py`, `src/market_game_sim/config/serialization.py`

## CONTEXT - READ THESE FIRST

### Key Documents (must read):
1. `docs/contracts/event-schema.md` - especially §1 (queue vs log keys), §1.1 (KR-006 monotonicity), §1.2 (backward jump whitelist), §1.4 (queue event vs transaction record), §1.5 (fail-stop), §4.6.3 (bootstrap snapshots), §3 (priority class frozen list), §6.1/§6.2 (RUN_HEADER/RUN_TRAILER)
2. `docs/adr/002-same-timestamp-event-scheduling.md` - dual key rationale, KR-006, zero-latency ban
3. `src/market_game_sim/config/types.py` - Price, Quantity, Cash, Bp, Nanos types

### Architecture
The kernel is a single-threaded discrete event simulator. Queue events are processed sequentially; each queue event executes an atomic transaction that may produce transaction records.

## DETAILED TASKS

### T201 [事件 Schema §1]: Dual Key System
Define two key types in `kernel/keys.py`:
```python
# queue_key = (timestamp, priority_class, enqueue_seq) — only for queue events
# log_key = (timestamp, transaction_seq, record_index) — for all log records
```
- `QueueKey`: namedtuple/dataclass with (timestamp: int, priority_class: int, enqueue_seq: int)
- `LogKey`: namedtuple/dataclass with (timestamp: int, transaction_seq: int, record_index: int)
- Both comparable (tuple comparison order)
- Three counters: `enqueue_seq` (global, increments on enqueue), `transaction_seq` (global, increments when queue event popped), `record_index` (per-transaction, starts at 0)

### T202 [事件 Schema §1.1] [TDD]: KR-006 Monotonicity
In `kernel/queue.py`, when enqueuing a new event `e'`:
```python
assert QueueKey(e') > QueueKey(current_queue_event)  # must hold
# If violated, raise exception → kernel terminates (fail-stop)
# NEVER silently reorder
```
Tests: 
- Normal enqueue (same timestamp, higher class, later enqueue_seq) → passes
- Violation (lower class without time advance) → exception raised
- edge cases: same timestamp same class but higher enqueue_seq → passes (enqueue_seq breaks ties)

### T203 [事件 Schema §1.2] [TDD]: Backward Jump Whitelist
Only two transitions can go back in priority_class:
1. `AGENT_DECIDE(4) → ORDER_ARRIVAL(0)` — agent communication delay `latency_ns ≥ 1`
2. `MARGIN_CALL(1) → ORDER_ARRIVAL(0)` — liquidation latency `liquidation_latency_ns ≥ 1`

Both MUST advance timestamp by ≥ 1 ns. Any other backward jump = defect, raise exception.
Tests: both whitelisted jumps with timestamp advance pass; unlisted backward jump fails.

### T204 [事件 Schema §3]: Priority Class Enum
In `kernel/enums.py`:
```python
class PriorityClass(IntEnum):
    ORDER_ARRIVAL = 0
    ORDER_CANCELLED = 0  # transaction record, same class label
    TRADE_SETTLE = 1
    MARGIN_CALL = 1
    MARKET_DATA_PUBLISH = 2
    AGENT_OBSERVE = 3
    AGENT_DECIDE = 4
    SNAPSHOT = 5
```

### T204b [事件 Schema §1.4] [TDD]: Queue Events vs Transaction Records
Only these are QUEUE EVENTS (go through the queue, get enqueue_seq, pop to execute):
- `ORDER_ARRIVAL`, `AGENT_OBSERVE`, `AGENT_DECIDE`, `SNAPSHOT`

These are TRANSACTION RECORDS (generated during transaction execution, written directly to log):
- `ORDER_CANCELLED`, `TRADE_SETTLE`, `MARGIN_CALL`, `MARKET_DATA_PUBLISH`

Tests: Verify that ORDER_ARRIVAL pops queue event, TRADE_SETTLE does not; verify transaction records cannot be enqueued.

### T204c [事件 Schema §1.4] [TDD]: Transaction Record Ordering + Buffered Write
Within a transaction, records are buffered and written in this frozen order:
```
r0: ORDER_ARRIVAL (parent, stored in buffer immediately)
r1..rp: TRADE_SETTLE + ORDER_CANCELLED (interleaved by matching order)
r(p+1)..rq: MARGIN_CALL × m (sorted by agent_id ascending)
r(q+1): MARKET_DATA_PUBLISH (only if book changed)
```

Rules:
- ALL records (including r0) are buffered, NOT written immediately
- `fill_count` is backfilled after matching loop ends, then entire buffer is written
- Three assertions:
  1. `MARKET_DATA_PUBLISH` is ALWAYS last record in transaction
  2. `accepted=false` transactions have ONLY r0
  3. Transactions that don't change the book skip `MARKET_DATA_PUBLISH`

Tests: verify record ordering, verify fill_count backfill, verify MARKET_DATA_PUBLISH position

### T204d [事件 Schema §1.5] [TDD]: Fail-Stop Semantics
When an exception occurs during transaction execution:
1. Kernel terminates entire run — NO rollback, NO resume
2. Transaction buffer (including r0) is DISCARDED — nothing appears in log
3. Write `RUN_TRAILER` with `terminated="ABORTED"`, `abort_code` (stable enum)

Fault injection test:
- Inject exception after first match in OB-4 scenario
- Assert: ① run terminates; ② log contains NO records from failed transaction; ③ trailer has `terminated=ABORTED` with stable `abort_code`; ④ `verify` rejects log with TI-4; ⑤ failed transaction's `transaction_seq` does NOT appear in log
- NO undo log or copy-on-write implementation — only visibility atomicity required

### T204e [事件 Schema §6.1/§6.2] [TDD]: Three Record Kinds
```python
class RecordKind(str, Enum):
    RUN_HEADER = "RUN_HEADER"
    EVENT = "EVENT"
    RUN_TRAILER = "RUN_TRAILER"
```

RUN_HEADER fields (§6.1, frozen):
- `record_kind`, `schema_version` (int), `run_id` (str), `code_version` (str), `config_hash` (str), `master_seed` (int), `started_at_wall` (str ISO 8601), `tick_size` (str decimal, NOT float), `min_quantity` (str decimal), `cash_unit` (str decimal)

RUN_TRAILER fields (§6.2, frozen):
- `record_kind`, `terminated` ("COMPLETED"|"ABORTED"), `abort_code` (null when COMPLETED), `abort_detail` (not used in judgment), `last_committed_transaction_seq` (int), `record_count` (int)

Byte-identical trailer vectors for both `terminated` values.

### T204e3 [事件 Schema §4.6.3] [TDD]: Mandatory Bootstrap Snapshots
At timestamp=0, pre-enqueue TWO real SNAPSHOT queue events:
- ACCOUNT snapshot: enqueue_seq=0
- BOOK snapshot: enqueue_seq=1

After popping, they become transaction_seq=1 and transaction_seq=2.
Business transactions start from transaction_seq=3.

Bootstrap barrier: startup must ONLY have these two events in queue. Any business event enqueue attempt before both snapshots are committed must raise exception (abort_code=INTERNAL). Barrier must NOT rely on enqueue_seq (if t=0 has class 0-4 events, class 5 snapshot would be behind them in priority).

Three test vectors:
1. Normal run with zero business transactions → exactly 2 EVENT records, last_committed_transaction_seq=2, COMPLETED
2. Second snapshot write fails → ABORTED, last_committed_transaction_seq=1 (not null)
3. Business event tries to enqueue during bootstrap → barrier rejects with INTERNAL

ACCOUNT snapshot MUST include ALL accounts (including those with no trades), sorted by agent_id ascending.

### T204e2 [事件 Schema §1.5] [TDD]: Termination Discrimination (TI-4 vs TI-5)
Two-phase judgment, structure before semantics:
- Phase 1: JSON completeness / first+last records exist / record_count matches → any failure = TI-5, STOP (don't read terminated)
- Phase 2: (only if Phase 1 passes) check terminated → ABORTED = TI-4

Three tests:
1. Inject exception → TI-4
2. Normal log truncated (cut last line) → TI-5
3. ABORTED log then truncated → MUST be TI-5 (not TI-4) — composite case

Both reject entire log, but diagnostic codes differ.

## MUST DO
- Read the contract documents listed above BEFORE implementing
- Use `src/market_game_sim/config/types.py` (Nanos, etc.) for time and value types
- Use `src/market_game_sim/config/serialization.py` for canonical JSON writing
- ALL assertions in tests must be exact (integer equality, exact string match)

## MUST NOT DO
- NO float anywhere in domain code
- NO third-party imports (stdlib only, KR-005)
- NO silent reordering of queue events
- NO rollback or undo log (fail-stop only)
- Do NOT implement matching, order book, or account logic
- Do NOT modify config/ files or existing tests
<!-- OMO_INTERNAL_INITIATOR -->

## assistant · 2026-08-02T09:26:17Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\docs\\contracts\\event-schema.md"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\docs\\adr\\002-same-timestamp-event-scheduling.md"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\config\\types.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\config\\serialization.py"})`


> [reasoning] Let me start by understanding the task. I need to implement Phase 2A of the market-game-sim 0.1.1, which covers the core event kernel (T201-T204e3). This is a complex task with multiple sub-tasks.

Let me first read the key documents and existing code to understand the context, then implement the tasks.

Let me start by exploring the codebase structure and reading the required documents.
我将先阅读所需文档和现有代码，然后再进行实现。

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
8: [ADR-001](../adr/001-numeric-and-serialization-contract.md)、
9: [ADR-002](../adr/002-same-timestamp-event-scheduling.md)、
10: [指标字典](../product/metrics-dictionary.md)
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
21: - `timestamp`：整数纳秒逻辑时间（KR-0
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\docs\adr\002-same-timestamp-event-scheduling.md</path>
<type>file</type>
<content>
1: # ADR-002：同时间戳事件调度与因果链的强制表达
2: 
3: 日期：2026-07-30  
4: 状态：Accepted（2026-08-01 修订为 queue key / log key 双键）
5: 关联规格：[`../../specs/v0.1-belief-testing-laboratory/spec.md`](../../specs/v0.1-belief-testing-laboratory/spec.md)  
6: 解决问题：PRD Q-012  
7: 关联决策：v0.1 规格 D-5（离散事件内核）  
8: 关联文档：[事件 Schema](../contracts/event-schema.md)
9: 
10: ## 背景
11: 
12: ### 1. 全序键的单调性未被保证
13: 
14: 修订前的 KR-003 曾定义事件全序键为 `(timestamp, priority_class, seq)`，event-schema §3 规定
15: 「数值越小越先处理」。但事件是在处理其他事件的过程中产生的：
16: 
17: - `AGENT_DECIDE`（class 4）产生订单意图，形成 `ORDER_ARRIVAL`（class 0）；
18: - `TRADE_SETTLE`（class 1）触发 `MARKET_DATA_PUBLISH`（class 2）；
19: - `AGENT_OBSERVE`（class 3）触发同一代理的 `AGENT_DECIDE`（class 4）。
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\config\types.py</path>
<type>file</type>
<content>
1: """T101: Immutable integer value objects (ADR-001 §1).
2: 
3: All domain amounts — price, quantity, cash, basis points, time — are carried
4: as Python ``int`` in minimum units.  ``float`` is forbidden at construction
5: time; ``decimal.Decimal`` is used only during config parsing (T102) and never
6: enters a value object.
7: 
8: These types are intentionally minimal: they wrap an ``int``, reject ``float``,
9: and are frozen.  Arithmetic is done on the raw ``int`` via the exposed
10: attribute; the wrapper exists to prevent accidental float contamination and
11: to make unit intent explicit at API boundaries.
12: """
13: 
14: from __future__ import annotations
15: 
16: from dataclass
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

## assistant · 2026-08-02T09:26:25Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\docs\\contracts\\event-schema.md", "limit": 400, "offset": 848})`
- **tool**: `glob({"pattern": "src/market_game_sim/**/*.py"})`
- **tool**: `glob({"pattern": "tests/**/*.py"})`


> [reasoning] Let me read the rest of the event-schema.md document (it was capped at 847 lines), and also explore the existing project structure.
让我阅读事件 schema 的其余部分并探索项目结构。

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
861: 因果外键（ADR-002 §3）使下列路径完全在日志内可解析，无需重放：
862: 
863: ```text
864: trade_id
865:   → caused_by_event_id        （ORDER_ARRIVAL：哪笔订单触发了撮合）
866:   → maker_order_id / taker_order_id
867:   → intent_id                 （哪个意图产生了该订单）
868:   → decision_event_id         （哪次决策产生了该意图）
869:   → observation_event_id      （该决策基于哪次观察）
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
Found 7 file(s)

D:\Projects\market-game-sim\src\market_game_sim\config\validator.py
D:\Projects\market-game-sim\src\market_game_sim\config\types.py
D:\Projects\market-game-sim\src\market_game_sim\config\parser.py
D:\Projects\market-game-sim\src\market_game_sim\config\serialization.py
D:\Projects\market-game-sim\src\market_game_sim\config\__init__.py
D:\Projects\market-game-sim\src\market_game_sim\schema\__init__.py
D:\Projects\market-game-sim\src\market_game_sim\__init__.py
[Agent Usage Reminder]

You called a search/fetch tool directly without leveraging specialized agents.

RECOMMENDED: Use task with explore/librarian agents for better results:

```
// Parallel exploration - fire multiple agents simultaneously
task(subagent_type="explore", load_skills=[], prompt="Find all files matching
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
Found 6 file(s)

D:\Projects\market-game-sim\tests\unit\config\test_validator.py
D:\Projects\market-game-sim\tests\unit\config\test_types.py
D:\Projects\market-game-sim\tests\unit\config\test_serialization.py
D:\Projects\market-game-sim\tests\unit\config\test_parser.py
D:\Projects\market-game-sim\tests\unit\config\__init__.py
D:\Projects\market-game-sim\tests\unit\test_contract_sources.py
[Agent Usage Reminder]

You called a search/fetch tool directly without leveraging specialized agents.

RECOMMENDED: Use task with explore/librarian agents for better results:

```
// Parallel exploration - fire multiple agents simultaneously
task(subagent_type="explore", load_skills=[], prompt="Find all files matching pattern X")
task(subagent_type="explore", load_skills=[], prompt="Search for implementa
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T09:26:34Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\schema\\__init__.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\config\\__init__.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\tests\\unit\\config\\test_types.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\__init__.py"})`


> [reasoning] Now I have a good understanding of the documents. Let me explore the existing code structure more, including the schema directory and the config validator, to understand the patterns used.
我来查看一下现有的代码结构，包括 schema 目录，并查看一个现有的测试以了解其模式。

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\schema\__init__.py</path>
<type>file</type>
<content>


(End of file - total 0 lines)
</content>
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\config\__init__.py</path>
<type>file</type>
<content>
1: """Config package: immutable value objects, YAML parser, validator, canonical serialization.
2: 
3: ADR-001 合同的实现：金额与数量以最小单位整数承载，配置经 Decimal 解析，
4: 序列化逐字节确定。
5: """

(End of file - total 5 lines)
</content>
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\tests\unit\config\test_types.py</path>
<type>file</type>
<content>
1: """T101 tests: immutable integer value objects and division helpers."""
2: 
3: from __future__ import annotations
4: 
5: import dataclasses
6: from decimal import Decimal
7: 
8: import pytest
9: 
10: from market_game_sim.config.types import (
11:     Bp,
12:     Cash,
13:     Nanos,
14:     Price,
15:     Quantity,
16:     div_ceil,
17:     div_floor,
18:     div_round_toward_zero,
19:     round_fee,
20: )
21: 
22: # --------------------------------------------------------------------------- #
23: # Value-object construction
24: # --------------------------------------------------------------------------- #
25: 
26: 
27: @pytest.mark.parametrize(
28:     "cls, attr",
29:     [
30:       
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\__init__.py</path>
<type>file</type>
<content>
1: """MarketGameSim: multi-agent financial market game simulation."""
2: 
3: __version__ = "0.1.0"

(End of file - total 3 lines)
</content>
  ```
  </details>

## assistant · 2026-08-02T09:26:41Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\tests\\unit\\test_contract_sources.py"})`
- **tool**: `glob({"pattern": "specs/v0.1-belief-testing-laboratory/0.1.1-minimal-kernel/**"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\config\\validator.py"})`


> [reasoning] Let me also look at the test_contract_sources.py to understand any contract source verification tests, and check the tasks.md to understand the task structure.
我来查看一下 `contract sources` 测试和 0.1.1 的 `tasks.md`，以更好地理解结构。

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\tests\unit\test_contract_sources.py</path>
<type>file</type>
<content>
1: """真源自校验：`tools/validate_contract_sources.py` 的 pytest 入口。
2: 
3: 同一套判据有两个触发点，**共用同一份实现**（不是两份手抄逻辑）：
4: 
5: - CI 的 `contract-sources` job：不装任何依赖，最先跑，失败即中止后续；
6: - 本地 `pytest`：开发者不必记住还有个脚本要跑。
7: 
8: **本文件的重点是负向变异测试。** 只断言「当前仓库通过」无法证明校验器在挡任何东西
9: ——删掉一段校验逻辑，happy-path 测试仍然全绿。第 36 章正是这样发现
10: `ORDER_CANCELLED.order_type` 漂移的：CI 绿着，而 JSON 与文档已经不一致。
11: 
12: 因此下面每个 `mutate_*` 都**先破坏一处真源，再断言校验器给出预期错误**。
13: 新增校验规则时应同时新增一条变异，否则那条规则等于没有被测试。
14: """
15: 
16: from __future__ import annotations
17: 
18: import copy
19: import importlib.util
20: import json
21: import pathlib
22: import sys
23: 
24: import pytest
25: 
26: ROOT = pathlib.Path(__file__).resolve().parents[2]
27: VALIDATOR = ROOT / 
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
Found 2 file(s)

D:\Projects\market-game-sim\specs\v0.1-belief-testing-laboratory\0.1.1-minimal-kernel\tasks.md
D:\Projects\market-game-sim\specs\v0.1-belief-testing-laboratory\0.1.1-minimal-kernel\spec.md
[Agent Usage Reminder]

You called a search/fetch tool directly without leveraging specialized agents.

RECOMMENDED: Use task with explore/librarian agents for better results:

```
// Parallel exploration - fire multiple agents simultaneously
task(subagent_type="explore", load_skills=[], prompt="Find all files matching pattern X")
task(subagent_type="explore", load_skills=[], prompt="Search for implementation of Y")
task(subagent_type="librarian", load_skills=[], prompt="Lookup documentation for Z")

// Then continue your work while they run in background
// System will notify you when e
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\config\validator.py</path>
<type>file</type>
<content>
1: """T103: Config validation (ADR-001 §2, v0.1 spec).
2: 
3: Checks semantic constraints that the parser cannot enforce on its own:
4:   - ``tick_size × min_quantity`` must be an integer multiple of ``cash_unit``
5:     (ensures notional amounts are exact integers, no rounding on trades).
6:   - ``latency_ns ≥ 1`` for every agent (KR-006: events must advance time).
7:   - ``leverage_tier_distribution`` values sum to 10 000 per agent.
8:   - ``max_transactions ≥ 2`` (bootstrap snapshots are transactions 1 and 2).
9:   - No pre-configured initial resting orders (v0.1 initial book is empty).
10:   - ``grace_ns == 0`` (v0.1 mandatory; non-zero is rejected).
11:   - ``liquidation_latenc
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T09:26:48Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\specs\\v0.1-belief-testing-laboratory\\0.1.1-minimal-kernel\\tasks.md"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\config\\parser.py"})`


> [reasoning] Let me look at the tasks.md for the 0.1.1 milestone to understand the specific task structure better, and check the existing parser.py for the ParsedConfig structure.
让我读取 `0.1.1` 的 `tasks.md` 和 `parser.py`，以了解 `config` 结构和任务定义。

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\specs\v0.1-belief-testing-laboratory\0.1.1-minimal-kernel\tasks.md</path>
<type>file</type>
<content>
1: # 0.1.1：最小确定性内核（无杠杆） · 任务拆解
2: 
3: **对应里程碑**：[`spec.md`](spec.md)  
4: **状态**：Ready（P0-I01/I02、P0-K01—K03、P0-L01/L02 均已于 2026-08-01 关闭）
5: 
6: ## 约定
7: 
8: - 每个任务标注 `[合同引用]`——实现前先读该节，实现后对照验收；
9: - **测试先行**：带 `[TDD]` 的任务，先写失败的测试再写实现；
10: - 任务顺序即依赖顺序，同一 Phase 内可并行的标 `[P]`；
11: - **任务编号只在本文件内唯一**。引用其他里程碑的任务时必须带里程碑前缀
12:   （写 `0.1.2 T104`，不写 `T104`）——各里程碑的编号为 `T0xx`—`T7xx` 且**互相重复**，
13:   裸编号会指向错误任务。
14: 
15: ---
16: 
17: ## Phase 1：数值与配置基础
18: 
19: - [ ] **T101** `[ADR-001 §1]` 定义整数值对象：`Price`、`Quantity`、`Cash`、`Bp`、
20:       `Nanos`。全部不可变，禁止浮点构造。
21: - [ ] **T102** `[ADR-001 §2]` `[TDD]` 配置解析：YAML 领域量必须为**字符串**，
22:       经 `Decimal` 转最小单位整数。**收到 float 
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\config\parser.py</path>
<type>file</type>
<content>
1: """T102: YAML config parser with strict Decimal->int conversion (ADR-001 §2).
2: 
3: Domain quantities in YAML must be quoted strings (e.g. ``tick_size: "0.01"``).
4: A bare float is rejected immediately -- no ``str()`` fallback, because that
5: would silently introduce a binary rounding step.
6: 
7: Integer fields (counts, nanoseconds, basis-point margins) carry no precision
8: risk and are read as plain ints.
9: """
10: 
11: from __future__ import annotations
12: 
13: from dataclasses import dataclass, field
14: from decimal import Decimal, InvalidOperation
15: from pathlib import Path
16: from typing import Any
17: 
18: import yaml
19: 
20: 
21: class ConfigParseError(Exception):
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T09:27:01Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\pyproject.toml"})`
- **tool**: `glob({"pattern": "tests/**/__init__.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\tests\\unit\\config\\test_serialization.py"})`


> [reasoning] Now I have a good understanding. Let me look at the pyproject.toml to understand the test setup, and check the existing test structure for config tests to follow the patterns.
我来检查一下 `pyproject.toml` 和现有的测试 `__init__.py` 文件以了解测试设置。

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\pyproject.toml</path>
<type>file</type>
<content>
1: [build-system]
2: requires = ["hatchling"]
3: build-backend = "hatchling.build"
4: 
5: [project]
6: name = "market-game-sim"
7: version = "0.1.0"
8: description = "Reproducible multi-agent limit-order-book market simulation"
9: readme = "README.md"
10: requires-python = ">=3.11"
11: dependencies = ["pyyaml>=6"]
12: 
13: [project.optional-dependencies]
14: dev = [
15:   "pytest>=8",
16:   "pytest-cov>=5",
17:   "ruff>=0.6",
18: ]
19: 
20: [tool.hatch.build.targets.wheel]
21: packages = ["src/market_game_sim"]
22: 
23: [tool.pytest.ini_options]
24: addopts = "-ra --strict-markers"
25: testpaths = ["tests"]
26: 
27: [tool.ruff]
28: line-length = 100
29: target-version = "py311"
30: 
31: [tool.ruff.lint]
32:
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
Found 1 file(s)

D:\Projects\market-game-sim\tests\unit\config\__init__.py
[Agent Usage Reminder]

You called a search/fetch tool directly without leveraging specialized agents.

RECOMMENDED: Use task with explore/librarian agents for better results:

```
// Parallel exploration - fire multiple agents simultaneously
task(subagent_type="explore", load_skills=[], prompt="Find all files matching pattern X")
task(subagent_type="explore", load_skills=[], prompt="Search for implementation of Y")
task(subagent_type="librarian", load_skills=[], prompt="Lookup documentation for Z")

// Then continue your work while they run in background
// System will notify you when each completes
```

WHY:
- Agents can perform deeper, more thorough searches
- Background tasks run in parallel, saving time
- Speci
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\tests\unit\config\test_serialization.py</path>
<type>file</type>
<content>
1: """T104 tests: canonical JSONL serialization (ADR-001 §7).
2: 
3: Verifies byte-deterministic serialization:
4:   - Integer literals as JSON integers (not strings, not floats)
5:   - Missing values as null (not NaN, Infinity, empty string)
6:   - UTF-8 encoding, NFC normalization, ensure_ascii=false
7:   - Keys sorted by codepoint, separators=(",", ":")
8:   - One LF per event, no CRLF, no trailing whitespace
9:   - Two serializations of the same object are byte-identical
10: """
11: 
12: from __future__ import annotations
13: 
14: import json
15: 
16: import pytest
17: 
18: from market_game_sim.config.serialization import (
19:     SerializationError,
20:     canonical_serialize
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T09:27:15Z


> [reasoning] Now I have a comprehensive understanding of the codebase, contracts, and existing patterns. Let me create a todo list and start implementing the kernel module.

Let me summarize what I need to build:

1. **T201 - Dual Key System** (`kernel/keys.py`):
   - `QueueKey`: (timestamp: int, priority_class: int, enqueue_seq: int) - comparable via tuple comparison
   - `LogKey`: (timestamp: int, transaction_seq: int, record_index: int) - comparable via tuple comparison
   - Three counters: `enqueue_seq` (global, increments on enqueue), `transaction_seq` (global, increments when queue event popped), `record_index` (per-transaction, starts at 0)

2. **T202 - KR-006 Monotonicity** (`kernel/queue.py`):
   - When enqueuing a new event `e'`: `assert QueueKey(e') > QueueKey(current_queue_event)`
   - If violated, raise exception -> kernel terminates (fail-stop)
   - NEVER silently reorder
   - Tests: Normal enqueue passes; violation raises exception; edge cases pass

3. **T203 - Backward Jump Whitelist** (`kernel/queue.py`):
   - Only two transitions can go back in priority_class:
     1. `AGENT_DECIDE(4) -> ORDER_ARRIVAL(0)` with latency_ns ≥ 1
     2. `MARGIN_CALL(1) -> ORDER_ARRIVAL(0)` with liquidation_latency_ns ≥ 1
   - Both MUST advance timestamp by ≥ 1 ns
   - Any other backward jump = defect, raise exception
   - Tests: both whitelisted jumps with timestamp advance pass; unlisted backward jump fails

4. **T204 - Priority Class Enum** (`kernel/enums.py`):
   ```python
   class PriorityClass(IntEnum):
       ORDER_ARRIVAL = 0
       ORDER_CANCELLED = 0  # transaction record, same class label
       TRADE_SETTLE = 1
       MARGIN_CALL = 1
       MARKET_DATA_PUBLISH = 2
       AGENT_OBSERVE = 3
       AGENT_DECIDE = 4
       SNAPSHOT = 5
   ```

5. **T204b - Queue Events vs Transaction Records** (`kernel/queue.py`):
   - Queue events: ORDER_ARRIVAL, AGENT_OBSERVE, AGENT_DECIDE, SNAPSHOT (go through queue, get enqueue_seq)
   - Transaction records: ORDER_CANCELLED, TRADE_SETTLE, MARGIN_CALL, MARKET_DATA_PUBLISH (generated during transaction execution, written directly to log)
   - Tests: ORDER_ARRIVAL pops queue event, TRADE_SETTLE does not; transaction records cannot be enqueued

6. **T204c - Transaction Record Ordering + Buffered Write** (`kernel/transaction.py`):
   - Within a transaction, records are buffered and written in frozen order:
     ```
     r0: ORDER_ARRIVAL (parent, stored in buffer immediately)
     r1..rp: TRADE_SETTLE + ORDER_CANCELLED (interleaved by matching order)
     r(p+1)..rq: MARGIN_CALL × m (sorted by agent_id ascending)
     r(q+1): MARKET_DATA_PUBLISH (only if book changed)
     ```
   - ALL records (including r0) are buffered, NOT written immediately
   - `fill_count` is backfilled after matching loop ends, then entire buffer is written
   - Three assertions:
     1. `MARKET_DATA_PUBLISH` is ALWAYS last record in transaction
     2. `accepted=false` transactions have ONLY r0
     3. Transactions that don't change the book skip `MARKET_DATA_PUBLISH`
   - Tests: verify record ordering, verify fill_count backfill, verify MARKET_DATA_PUBLISH position

7. **T204d - Fail-Stop Semantics** (`kernel/transaction.py`):
   - When an exception occurs during transaction execution:
     1. Kernel terminates entire run - NO rollback, NO resume
     2. Transaction buffer (including r0) is DISCARDED - nothing appears in log
     3. Write `RUN_TRAILER` with `terminated="ABORTED"`, `abort_code` (stable enum)
   - Fault injection test:
     - Inject exception after first match in OB-4 scenario
     - Assert: ① run terminates; ② log contains NO records from failed transaction; ③ trailer has `terminated=ABORTED` with stable `abort_code`; ④ `verify` rejects log with TI-4; ⑤ failed transaction's `transaction_seq` does NOT appear in log
   - NO undo log or copy-on-write implementation - only visibility atomicity required

8. **T204e - Three Record Kinds** (`kernel/event_log.py`):
   ```python
   class RecordKind(str, Enum):
       RUN_HEADER = "RUN_HEADER"
       EVENT = "EVENT"
       RUN_TRAILER = "RUN_TRAILER"
   ```
   - RUN_HEADER fields (§6.1, frozen): record_kind, schema_version (int), run_id (str), code_version (str), config_hash (str), master_seed (int), started_at_wall (str ISO 8601), tick_size (str decimal, NOT float), min_quantity (str decimal), cash_unit (str decimal)
   - RUN_TRAILER fields (§6.2, frozen): record_kind, terminated ("COMPLETED"|"ABORTED"), abort_code (null when COMPLETED), abort_detail (not used in judgment), last_committed_transaction_seq (int), record_count (int)
   - Byte-identical trailer vectors for both `terminated` values.

9. **T204e3 - Mandatory Bootstrap Snapshots** (`kernel/bootstrap.py`):
   - At timestamp=0, pre-enqueue TWO real SNAPSHOT queue events:
     - ACCOUNT snapshot: enqueue_seq=0
     - BOOK snapshot: enqueue_seq=1
   - After popping, they become transaction_seq=1 and transaction_seq=2
   - Business transactions start from transaction_seq=3
   - Bootstrap barrier: startup must ONLY have these two events in queue. Any business event enqueue attempt before both snapshots are committed must raise exception (abort_code=INTERNAL). Barrier must NOT rely on enqueue_seq
   - Three test vectors:
     1. Normal run with zero business transactions -> exactly 2 EVENT records, last_committed_transaction_seq=2, COMPLETED
     2. Second snapshot write fails -> ABORTED, last_committed_transaction_seq=1 (not null)
     3. Business event tries to enqueue during bootstrap -> barrier rejects with INTERNAL
   - ACCOUNT snapshot MUST include ALL accounts (including those with no trades), sorted by agent_id ascending.

10. **T204e2 - Termination Discrimination (TI-4 vs TI-5)** (`kernel/event_log.py` or separate verifier):
    - Two-phase judgment, structure before semantics:
      - Phase 1: JSON completeness / first+last records exist / record_count matches -> any failure = TI-5, STOP (don't read terminated)
      - Phase 2: (only if Phase 1 passes) check terminated -> ABORTED = TI-4
    - Three tests:
      1. Inject exception -> TI-4
      2. Normal log truncated (cut last line) -> TI-5
      3. ABORTED log then truncated -> MUST be TI-5 (not TI-4) - composite case

Now, looking at the task description more carefully, the expected outcome lists these files:
- `src/market_game_sim/kernel/__init__.py` + `src/market_game_sim/kernel/keys.py` - dual key system
- `src/market_game_sim/kernel/enums.py` - priority class enum
- `src/market_game_sim/kernel/queue.py` - event queue with monotonicity
- `src/market_game_sim/kernel/transaction.py` - transaction buffer with fail-stop
- `src/market_game_sim/kernel/bootstrap.py` - bootstrap snapshot barrier
- `src/market_game_sim/kernel/event_log.py` - event log writer with RUN_HEADER/EVENT/RUN_TRAILER
- `tests/unit/kernel/` - all unit tests

The abort codes from the spec (§6.2):
- QUEUE_KEY_MONOTONICITY - KR-006 violation (§1.1)
- CLASS_REGRESSION_NOT_WHITELISTED - backward jump not in §1.2 whitelist
- CONSERVATION_BREACH - C1/C2 violated
- ILLEGAL_STATE_TRANSITION - account state machine illegal transition
- CONFIG_INVARIANT - config validation violated at runtime
- INTERNAL - other kernel exceptions

Now, I need to be careful about scope. The task says:
- Do NOT implement matching, order book, or account logic
- Do NOT modify config/ files or existing tests

So I'm implementing the kernel infrastructure, not the actual matching/orderbook/account logic. The transaction buffer is a generic buffer that holds records. The fault injection test would inject an exception via a callback/hook.

Let me think about the design:

### keys.py
- `QueueKey` namedtuple: (timestamp, priority_class, enqueue_seq)
- `LogKey` namedtuple: (timestamp, transaction_seq, record_index)
- A `Counter` class to manage the three counters

### enums.py
- `PriorityClass(IntEnum)` with the frozen list
- `RecordKind(str, Enum)` with RUN_HEADER, EVENT, RUN_TRAILER
- `AbortCode(str, Enum)` with the stable error codes
- `Terminated(str, Enum)` with COMPLETED, ABORTED
- `EventType(str, Enum)` - the event types
- `SnapshotType(str, Enum)` - ACCOUNT, BOOK
- Helper sets: QUEUE_EVENT_TYPES, TRANSACTION_RECORD_TYPES

### queue.py
- `EventQueue` class that manages the priority queue
- Monotonicity assertion on enqueue
- Backward jump whitelist check
- Bootstrap barrier check

### transaction.py
- `TransactionBuffer` class that buffers records
- Methods to add records, backfill fill_count, commit (write to log)
- Methods to discard on failure
- Record ordering assertions

### bootstrap.py
- `BootstrapBarrier` class
- Methods to create the two initial snapshots
- Barrier check that rejects business event enqueue before both snapshots committed

### event_log.py
- `EventLogWriter` class
- Methods to write RUN_HEADER, EVENT, RUN_TRAILER
- A verifier function for termination discrimination (TI-4 vs TI-5)

Let me now think about the test structure. The tests need to be in `tests/unit/kernel/`. Let me create:
- `tests/unit/kernel/__init__.py`
- `tests/unit/kernel/test_keys.py` - T201
- `tests/unit/kernel/test_queue.py` - T202, T203, T204b
- `tests/unit/kernel/test_enums.py` - T204
- `tests/unit/kernel/test_transaction.py` - T204c, T204d
- `tests/unit/kernel/test_event_log.py` - T204e, T204e2
- `tests/unit/kernel/test_bootstrap.py` - T204e3

Now let me think more carefully about the design details.

For the queue, I need to use `heapq` from stdlib. The queue stores events keyed by `QueueKey`. 

Wait, I need to think about what an "event" is. Since I'm not implementing the full event types with all fields, I'll create a lightweight representation. Let me think...

Actually, looking at the task more carefully, the kernel is infrastructure. The events themselves will have fields defined by the schema (T204f registry). But for T201-T204e3, I'm implementing the queue, transaction buffer, bootstrap, and event log infrastructure.

Let me design a minimal event representation that the queue can work with. The queue needs to know:
- timestamp
- priority_class (or event_type that maps to priority_class)
- enqueue_seq (assigned by the queue)

For the transaction buffer, records need:
- event_type
- record_index (assigned by the buffer)
- other fields (just stored as a dict)

For the event log writer, records are dicts that get serialized.

Let me think about the abort codes and how exceptions map to them. I'll create a `KernelAbort` exception that carries an `abort_code`.

Let me design the modules:

#### enums.py
```python
from enum import Enum, IntEnum

class PriorityClass(IntEnum):
    ORDER_ARRIVAL = 0
    ORDER_CANCELLED = 0  # transaction record, same class label
    TRADE_SETTLE = 1
    MARGIN_CALL = 1
    MARKET_DATA_PUBLISH = 2
    AGENT_OBSERVE = 3
    AGENT_DECIDE = 4
    SNAPSHOT = 5

class EventType(str, Enum):
    ORDER_ARRIVAL = "ORDER_ARRIVAL"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    TRADE_SETTLE = "TRADE_SETTLE"
    MARGIN_CALL = "MARGIN_CALL"
    MARKET_DATA_PUBLISH = "MARKET_DATA_PUBLISH"
    AGENT_OBSERVE = "AGENT_OBSERVE"
    AGENT_DECIDE = "AGENT_DECIDE"
    SNAPSHOT = "SNAPSHOT"

# Mapping from event type to priority class
EVENT_TYPE_TO_PRIORITY_CLASS = {
    EventType.ORDER_ARRIVAL: PriorityClass.ORDER_ARRIVAL,
    EventType.ORDER_CANCELLED: PriorityClass.ORDER_CANCELLED,
    EventType.TRADE_SETTLE: PriorityClass.TRADE_SETTLE,
    EventType.MARGIN_CALL: PriorityClass.MARGIN_CALL,
    EventType.MARKET_DATA_PUBLISH: PriorityClass.MARKET_DATA_PUBLISH,
    EventType.AGENT_OBSERVE: PriorityClass.AGENT_OBSERVE,
    EventType.AGENT_DECIDE: PriorityClass.AGENT_DECIDE,
    EventType.SNAPSHOT: PriorityClass.SNAPSHOT,
}

QUEUE_EVENT_TYPES = frozenset({
    EventType.ORDER_ARRIVAL,
    EventType.AGENT_OBSERVE,
    EventType.AGENT_DECIDE,
    EventType.SNAPSHOT,
})

TRANSACTION_RECORD_TYPES = frozenset({
    EventType.ORDER_CANCELLED,
    EventType.TRADE_SETTLE,
    EventType.MARGIN_CALL,
    EventType.MARKET_DATA_PUBLISH,
})

class RecordKind(str, Enum):
    RUN_HEADER = "RUN_HEADER"
    EVENT = "EVENT"
    RUN_TRAILER = "RUN_TRAILER"

class Terminated(str, Enum):
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"

class AbortCode(str, Enum):
    QUEUE_KEY_MONOTONICITY = "QUEUE_KEY_MONOTONICITY"
    CLASS_REGRESSION_NOT_WHITELISTED = "CLASS_REGRESSION_NOT_WHITELISTED"
    CONSERVATION_BREACH = "CONSERVATION_BREACH"
    ILLEGAL_STATE_TRANSITION = "ILLEGAL_STATE_TRANSITION"
    CONFIG_INVARIANT = "CONFIG_INVARIANT"
    INTERNAL = "INTERNAL"

class SnapshotType(str, Enum):
    ACCOUNT = "ACCOUNT"
    BOOK = "BOOK"
```

Wait, there's an issue with `PriorityClass(IntEnum)`. Python's `IntEnum` doesn't allow two members to have the same value by default - actually it does, but the second one becomes an alias for the first. Let me check...

Actually, in Python's `IntEnum` (which inherits from `Enum`), if two members have the same value, the second one becomes an alias. So `ORDER_CANCELLED` would be an alias for `ORDER_ARRIVAL`. That means `PriorityClass.ORDER_CANCELLED` would actually be `PriorityClass.ORDER_ARRIVAL`. 

Hmm, but the task says:
```python
class PriorityClass(IntEnum):
    ORDER_ARRIVAL = 0
    ORDER_CANCELLED = 0  # transaction record, same class label
    ...
```

This is fine for the priority class enum because `ORDER_CANCELLED` is a transaction record (not a queue event), so it doesn't need to be a distinct priority class for queue ordering. The alias behavior is actually correct - they share the same class value. But we need to be careful: `PriorityClass(0)` would return `ORDER_ARRIVAL` (the first defined), not `ORDER_CANCELLED`. And `PriorityClass.ORDER_CANCELLED is PriorityClass.ORDER_ARRIVAL` would be `True`.

Actually, this is a problem. The event type enum is separate from the priority class enum. `EventType.ORDER_CANCELLED` is distinct from `EventType.ORDER_ARRIVAL`. The mapping from event type to priority class gives both the same class (0). That's the design: event types are distinct, but their priority class (for queue ordering purposes) can be the same. Since `ORDER_CANCELLED` is a transaction record and never goes through the queue, its priority class is just a label.

So the aliasing in `PriorityClass` is actually fine and even desirable. Let me keep it as the task specifies.

But wait, for the `EVENT_TYPE_TO_PRIORITY_CLASS` mapping, if I use `PriorityClass.ORDER_CANCELLED`, it will actually be `PriorityClass.ORDER_ARRIVAL`. That's fine - they have the same value (0).

Actually, let me reconsider. The task says to use `IntEnum`. But having aliases means `PriorityClass.ORDER_CANCELLED` is not a separate member. Let me think about whether this matters for the tests...

For T204, the test just needs to verify the enum values. `PriorityClass.ORDER_ARRIVAL == 0` and `PriorityClass.ORDER_CANCELLED == 0` both work even with aliasing. The only issue is iteration: `list(PriorityClass)` would not include `ORDER_CANCELLED` (aliases are excluded from iteration). But we can use `PriorityClass.__members__` to get all names including aliases.

I think this is fine. The spec says ORDER_CANCELLED shares class 0 with ORDER_ARRIVAL - it's a label, not a distinct class. The aliasing correctly represents this.

Now let me think about the backward jump whitelist (T203). The check is on priority_class regression. When enqueuing a new event, if the new event's priority_class is lower than the current event's priority_class (backward jump), we need to check:
1. Is it `AGENT_DECIDE(4) -> ORDER_ARRIVAL(0)`? If so, timestamp must advance by ≥ 1.
2. Is it `MARGIN_CALL(1) -> ORDER_ARRIVAL(0)`? If so, timestamp must advance by ≥ 1.
3. Any other backward jump = defect.

Wait, but MARGIN_CALL is a transaction record, not a queue event. How can it produce a queue event? The spec says:
> `MARGIN_CALL` 事务记录 -> `ORDER_ARRIVAL`（强平单）| 当前订单事务 -> 0 | 风控下单延迟 `liquidation_latency_ns` | ≥ 1

So during the processing of an ORDER_ARRIVAL transaction (which was a queue event), a MARGIN_CALL record is produced, and that MARGIN_CALL may trigger a new ORDER_ARRIVAL (the liquidation order) to be enqueued. The "current" event being processed is the ORDER_ARRIVAL that triggered the margin call. But the backward jump is from class 1 (MARGIN_CALL record) to class 0 (ORDER_ARRIVAL queue event).

Hmm, actually I think the check should be based on what's producing the new event. The current queue event has a priority class. The new event being enqueued has a priority class. If new < current (backward), check the whitelist.

But the whitelist mentions MARGIN_CALL -> ORDER_ARRIVAL, where MARGIN_CALL is class 1. The current queue event being processed would be ORDER_ARRIVAL (class 0). So the "producer" of the new event is the MARGIN_CALL record (class 1), not the current queue event (class 0).

Wait, let me re-read the spec more carefully:

§1.2:
| 跳转 | class | 跨越时间由谁承担 | 下限 |
|---|---|---|---|
| `AGENT_DECIDE` -> `ORDER_ARRIVAL` | 4 -> 0 | 代理通信延迟 `latency_ns` | ≥ 1 |
| `MARGIN_CALL` 事务记录 -> `ORDER_ARRIVAL`（强平单） | 当前订单事务 -> 0 | 风控下单延迟 `liquidation_latency_ns` | ≥ 1 |

So the second row says "当前订单事务 -> 0", meaning the current order transaction (class 0) produces a MARGIN_CALL record (class 1), which then produces a new ORDER_ARRIVAL (class 0). The backward jump is from class 1 to class 0.

But wait, the "current queue event" is the ORDER_ARRIVAL (class 0). The new event is also ORDER_ARRIVAL (class 0). That's not a backward jump (0 -> 0 is not backward).

Hmm, I think the check is more nuanced. Let me re-read §1.1:

> 事务处理期间新入队的队列事件 `e'` 必须满足：`queue_key(e') > queue_key(current_queue_event)`

So the check is `queue_key(e') > queue_key(current)`. The current queue event is the one being processed. If we're processing an ORDER_ARRIVAL (class 0), and we enqueue a new ORDER_ARRIVAL (class 0), the queue_key comparison is `(t', 0, seq') > (t, 0, seq)`. Since `seq' > seq` (enqueue_seq is monotonically increasing), this passes even at the same timestamp.

So when does a backward jump happen? It happens when the current queue event has a higher class number, and the new event has a lower class number. For example:
- Current: AGENT_DECIDE (class 4), New: ORDER_ARRIVAL (class 0) -> backward (4 -> 0)
- Current: MARGIN_CALL... but MARGIN_CALL is not a queue event!

Wait, I think I need to reconsider. The current queue event determines the class for comparison. When we're processing an AGENT_DECIDE (class 4) and enqueue an ORDER_ARRIVAL (class 0), that's a 4->0 backward jump. This is the first whitelist entry.

For the MARGIN_CALL case: MARGIN_CALL is a transaction record produced during an ORDER_ARRIVAL transaction. The ORDER_ARRIVAL is the current queue event (class 0). The MARGIN_CALL triggers a new ORDER_ARRIVAL (class 0). So it's 0 -> 0, which is NOT a backward jump in terms of queue_key comparison.

Hmm, but the spec says:
> 第二行是 2026-08-01 检视补入的：强平单同样是 `ORDER_ARRIVAL`(class 0)，由 `MARGIN_CALL`(class 1) 产生，因此**也是回退**。

So the spec considers MARGIN_CALL(1) -> ORDER_ARRIVAL(0) as a "backward jump" even though MARGIN_CALL is a transaction record, not a queue event. The "current" context is the MARGIN_CALL record (class 1), not the parent ORDER_ARRIVAL queue event (class 0).

I think the check needs to track the "producer class" - the class of the record/event that's producing the new queue event. When a MARGIN_CALL record (class 1) produces an ORDER_ARRIVAL (class 0), the producer class is 1 (from MARGIN_CALL), and the new event class is 0. That's a 1->0 backward jump.

But when the current queue event (ORDER_ARRIVAL, class 0) directly produces another ORDER_ARRIVAL (class 0), the producer class is 0, and that's not a backward jump.

So the design should be:
- Track the current queue event (for queue_key monotonicity check).
- When enqueuing, also track the "producer context" - what's producing this event. If the producer is a transaction record with a higher class than the new event, check the whitelist.

Actually, let me re-think this. The queue_key monotonicity check (T202) is simple: `queue_key(e') > queue_key(current)`. The backward jump check (T203) is about which transitions are allowed to go backward in class.

For the queue_key check, the comparison is between the new event and the current queue event. If the current queue event is class 4 (AGENT_DECIDE) and the new event is class 0 (ORDER_ARRIVAL) at the same timestamp, then `queue_key(e') = (t, 0, seq')` and `queue_key(current) = (t, 4, seq)`. Is `(t, 0, seq') > (t, 4, seq)`? No! Because 0 < 4. So the queue_key check would fail.

But the whitelist says AGENT_DECIDE -> ORDER_ARRIVAL is allowed if timestamp advances. So if the new event has `t' > t`, then `(t', 0, seq') > (t, 4, seq)` because `t' > t`. That passes the queue_key check.

So the queue_key monotonicity check already handles this: a backward class jump at the same timestamp fails the check. The whitelist (T203) adds an additional check: even if the timestamp advances (making queue_key monotonic), the specific backward jump must be in the whitelist.

Wait, but if the timestamp advances, the queue_key check passes. So why do we need the whitelist? Let me re-read...

§1.2:
> **每一个回退 class 的跳转都必须跨越至少 1 ns，且必须列在下表中。** 表外出现回退即为实现缺陷或 schema 遗漏，不得临时加 1 ns 绕过。

So the whitelist is: if there's a class regression (new class < current class), then:
1. The timestamp MUST advance by ≥ 1 ns (this is also enforced by queue_key check, since same-timestamp with lower class would fail).
2. The specific transition must be in the whitelist.

So the whitelist check is an additional constraint on top of queue_key monotonicity. Even if the queue_key is monotonic (because timestamp advanced), if the backward jump is not in the whitelist, it's a defect.

Now, for the MARGIN_CALL -> ORDER_ARRIVAL case: the current queue event is ORDER_ARRIVAL (class 0). A MARGIN_CALL record (class 1) is produced during this transaction. The MARGIN_CALL triggers a new ORDER_ARRIVAL (class 0) to be enqueued. The queue_key check: current is (t, 0, seq), new is (t + liquidation_latency_ns, 0, seq'). Since t + latency > t, this passes. But is there a class regression? Current class is 0, new class is 0. No regression!

So the "producer" of the new event matters. The MARGIN_CALL record (class 1) is the producer, and the new ORDER_ARRIVAL (class 0) is a regression from 1 to 0.

I think the design needs to track the "producer class" when enqueuing. The enqueue method should accept information about what's producing the event (the producer's event type or priority class), and check the whitelist based on that.

Let me design this:

```python
def enqueue(self, event, producer_class: PriorityClass = None):
    # ... queue_key check ...
    
    # Backward jump whitelist check
    current_class = self._current_event_class  # class of the queue event being processed
    new_class = event.priority_class
    
    # The "effective producer class" for backward jump check
    # If producer_class is specified (e.g., MARGIN_CALL producing ORDER_ARRIVAL),
    # use that; otherwise use the current queue event's class.
    effective_producer_class = producer_class if producer_class is not None else current_class
    
    if new_class < effective_producer_class:
        # This is a backward jump - check whitelist
        self._check_backward_jump(effective_producer_class, new_class, event.timestamp, current_timestamp)
```

Actually, I think I'm overcomplicating this. Let me re-read the spec one more time.

§1.1:
> 推论：新入队事件若回到更小的 class，`timestamp` 必须前进。因此 `AGENT_DECIDE` 产生的普通订单和 `MARGIN_CALL` 产生的强平订单都必须带非零延迟。

So:
- AGENT_DECIDE (current queue event, class 4) produces ORDER_ARRIVAL (class 0). Backward: 4 -> 0.
- MARGIN_CALL (transaction record, class 1) produces ORDER_ARRIVAL (class 0). Backward: 1 -> 0.

In both cases, the "producer" is the thing that's generating the new event. For AGENT_DECIDE, the producer is the current queue event itself (class 4). For MARGIN_CALL, the producer is a transaction record (class 1) generated during the current queue event's transaction.

So the backward jump check is based on the "producer class" vs the "new event class". The producer class is:
- For AGENT_DECIDE -> ORDER_ARRIVAL: producer is AGENT_DECIDE (class 4), the current queue event.
- For MARGIN_CALL -> ORDER_ARRIVAL: producer is MARGIN_CALL (class 1), a transaction record.

The queue_key monotonicity check uses the current queue event's key, not the producer's key. But the backward jump check uses the producer's class.

So I need to track:
1. The current queue event (for queue_key monotonicity).
2. The "producer context" for backward jump check - this could be the current queue event, or a transaction record being processed within the current queue event's transaction.

Let me design the enqueue API to accept a `producer_class` parameter:

```python
def enqueue(self, event, producer_class: int | None = None) -> int:
    """Enqueue a new event. Returns the assigned enqueue_seq.
    
    producer_class: the priority class of the producer. If None, uses the
    current queue event's class. For MARGIN_CALL producing ORDER_ARRIVAL,
    pass PriorityClass.MARGIN_CALL (1).
    """
```

Actually, let me think about this differently. The kernel processes one queue event at a time. During that processing, it may:
1. Generate transaction records (TRADE_SETTLE, MARGIN_CALL, etc.)
2. Enqueue new queue events (ORDER_ARRIVAL, AGENT_OBSERVE, AGENT_DECIDE, SNAPSHOT)

When enqueueing, the "current context" is the current queue event plus any transaction records being generated. The backward jump is determined by comparing the new event's class to the class of whatever is producing it.

For the implementation, I think the cleanest approach is:
- The queue tracks the "current queue event" (the one being processed).
- When enqueueing, the caller specifies the "producer event type" (what's producing this new event).
- The backward jump check compares the producer's class to the new event's class.

Let me look at what the tests need:

T203 tests:
- both whitelisted jumps with timestamp advance pass
- unlisted backward jump fails

For the whitelisted jumps:
1. AGENT_DECIDE(4) -> ORDER_ARRIVAL(0) with timestamp advance ≥ 1: pass
2. MARGIN_CALL(1) -> ORDER_ARRIVAL(0) with timestamp advance ≥ 1: pass

For the unlisted backward jump:
- e.g., MARKET_DATA_PUBLISH(2) -> ORDER_ARRIVAL(0) - but MARKET_DATA_PUBLISH is a transaction record, not a queue event. So this would be a producer class of 2 producing a class 0 event. That's not in the whitelist.

Actually, wait. The producer can be either a queue event or a transaction record. The key is: what class is producing the new queue event?

For case 1: AGENT_DECIDE is a queue event (class 4). It's the current queue event being processed. It produces ORDER_ARRIVAL (class 0). The producer class is 4.

For case 2: MARGIN_CALL is a transaction record (class 1). It's produced during the current ORDER_ARRIVAL transaction. The MARGIN_CALL record produces ORDER_ARRIVAL (class 0). The producer class is 1.

So the enqueue method needs to know the producer class. Let me design it as:

```python
def enqueue(self, event_type: EventType, timestamp: int, producer_class: int | None = None) -> int:
    """Enqueue a new queue event.
    
    Args:
        event_type: must be a QUEUE_EVENT_TYPE
        timestamp: event timestamp in nanoseconds
        producer_class: priority class of the producer. If None, uses the
            current queue event's class.
    
    Returns:
        The assigned enqueue_seq.
    
    Raises:
        KernelAbort: if queue_key monotonicity is violated, backward jump
            is not whitelisted, or bootstrap barrier rejects.
    """
```

Hmm, but the task says I should NOT implement matching, order book, or account logic. So the queue and transaction are infrastructure. The actual event creation will be done by the matching engine (T301+) and agent logic.

Let me keep the design simple and focused on the infrastructure. The queue takes events with (event_type, timestamp, ...) and manages the queue_key. The backward jump check takes the producer class.

Now, let me think about the event representation. Since I'm not implementing the full event schema, I'll use a simple dataclass or named tuple for queue events:

```python
@dataclass(frozen=True)
class QueueEvent:
    event_type: EventType
    timestamp: int
    enqueue_seq: int
    # Additional payload can be attached by the caller
    payload: dict | None = None
    
    @property
    def queue_key(self) -> QueueKey:
        return QueueKey(self.timestamp, EVENT_TYPE_TO_PRIORITY_CLASS[self.event_type].value, self.enqueue_seq)
```

Actually, let me think about this more carefully. The task says the queue assigns enqueue_seq. So the event is created without enqueue_seq, and the queue assigns it. Let me have the queue create the full event with the assigned seq.

Actually, for simplicity, let me have the queue store events as tuples of (QueueKey, event_data) and use heapq.

Let me think about the test requirements more carefully:

T202 tests:
- Normal enqueue (same timestamp, higher class, later enqueue_seq) -> passes
  - Wait, "higher class" means higher number? In priority terms, lower number = higher priority. But the spec says "数值越小越先处理" (smaller number processed first). So class 0 is processed before class 4.
  - The test says "same timestamp, higher class, later enqueue_seq -> passes". I think "higher class" means numerically higher (e.g., class 4 vs class 0). At the same timestamp, a class 4 event has a higher queue_key than a class 0 event (because 4 > 0). So enqueuing a class 4 event when the current is class 0 passes.
  
  Wait, actually the test description is a bit ambiguous. Let me re-read:
  "Normal enqueue (same timestamp, higher class, later enqueue_seq) -> passes"
  
  I think this means: current event is at (t, class_A, seq_A), and we enqueue (t, class_B, seq_B) where class_B > class_A and seq_B > seq_A. The queue_key comparison: (t, class_B, seq_B) > (t, class_A, seq_A) because class_B > class_A. This passes.
  
- Violation (lower class without time advance) -> exception raised
  - Current event is at (t, class_A, seq_A), and we enqueue (t, class_B, seq_B) where class_B < class_A. The queue_key comparison: (t, class_B, seq_B) > (t, class_A, seq_A)? No, because class_B < class_A. This fails.
  
- edge cases: same timestamp same class but higher enqueue_seq -> passes
  - Current event is at (t, class_A, seq_A), and we enqueue (t, class_A, seq_B) where seq_B > seq_A. The queue_key comparison: (t, class_A, seq_B) > (t, class_A, seq_A) because seq_B > seq_A. This passes.

OK, so the queue_key monotonicity check is straightforward tuple comparison.

Now for T203:
- AGENT_DECIDE(4) -> ORDER_ARRIVAL(0) with timestamp advance ≥ 1: pass
  - Current queue event is AGENT_DECIDE at (t, 4, seq). New event is ORDER_ARRIVAL at (t+1, 0, seq'). 
  - queue_key check: (t+1, 0, seq') > (t, 4, seq) -> True (t+1 > t).
  - Backward jump check: producer class 4 -> new class 0, whitelist entry exists, timestamp advanced by 1. Pass.
  
- MARGIN_CALL(1) -> ORDER_ARRIVAL(0) with timestamp advance ≥ 1: pass
  - Current queue event is ORDER_ARRIVAL at (t, 0, seq). During its transaction, MARGIN_CALL (class 1) is produced, which triggers a new ORDER_ARRIVAL at (t+1, 0, seq').
  - queue_key check: (t+1, 0, seq') > (t, 0, seq) -> True (t+1 > t, but even at same t it would pass since seq' > seq).
  - Backward jump check: producer class 1 (MARGIN_CALL) -> new class 0 (ORDER_ARRIVAL), whitelist entry exists, timestamp advanced by 1. Pass.

- Unlisted backward jump fails
  - e.g., Some producer of class 2 (MARKET_DATA_PUBLISH) -> ORDER_ARRIVAL(0). Not in whitelist. Fail.
  - Or: AGENT_DECIDE(4) -> AGENT_OBSERVE(3). 4 -> 3 is backward, not in whitelist. Fail.

Wait, AGENT_OBSERVE(3) -> AGENT_DECIDE(4) is forward (3 -> 4), not backward. And AGENT_DECIDE(4) -> AGENT_OBSERVE(3) would be backward (4 -> 3), which is not in the whitelist. Let me check the spec...

§1.2:
> `AGENT_OBSERVE` -> `AGENT_DECIDE` 是 class 3 -> 4 的队列跳转，允许同时间戳、间隔为 0。

So 3 -> 4 (forward) is allowed at same timestamp. 4 -> 3 (backward) is not mentioned in the whitelist, so it would be a defect.

For the test, I could use: MARKET_DATA_PUBLISH(2) -> ORDER_ARRIVAL(0) as the unlisted backward jump. But MARKET_DATA_PUBLISH is a transaction record, not a queue event. It could be a producer that tries to enqueue an ORDER_ARRIVAL. The backward jump from 2 to 0 is not in the whitelist.

Or I could use: AGENT_DECIDE(4) -> AGENT_OBSERVE(3). Both are queue events. 4 -> 3 is backward, not in whitelist.

Actually, let me think about which backward jumps could conceivably happen:
- ORDER_ARRIVAL(0) -> any lower class: there's nothing lower than 0, so no backward jump from ORDER_ARRIVAL.
- TRADE_SETTLE(1) -> ORDER_ARRIVAL(0): backward 1->0. Not in whitelist (MARGIN_CALL->ORDER_ARRIVAL is, but TRADE_SETTLE->ORDER_ARRIVAL isn't). But TRADE_SETTLE is a transaction record, and it doesn't produce new queue events in normal operation.
- MARGIN_CALL(1) -> ORDER_ARRIVAL(0): whitelisted.
- MARKET_DATA_PUBLISH(2) -> ORDER_ARRIVAL(0): backward 2->0. Not whitelisted.
- AGENT_OBSERVE(3) -> ORDER_ARRIVAL(0): backward 3->0. Not whitelisted. But AGENT_OBSERVE doesn't produce ORDER_ARRIVAL.
- AGENT_DECIDE(4) -> ORDER_ARRIVAL(0): whitelisted.
- AGENT_DECIDE(4) -> AGENT_OBSERVE(3): backward 4->3. Not whitelisted.
- AGENT_DECIDE(4) -> TRADE_SETTLE(1): backward 4->1. But TRADE_SETTLE is not a queue event.
- AGENT_DECIDE(4) -> MARKET_DATA_PUBLISH(2): backward 4->2. But MARKET_DATA_PUBLISH is not a queue event.

So the only queue events that can be enqueued are: ORDER_ARRIVAL(0), AGENT_OBSERVE(3), AGENT_DECIDE(4), SNAPSHOT(5).

The possible backward jumps (producer class -> new queue event class):
- 1 -> 0 (MARGIN_CALL -> ORDER_ARRIVAL): whitelisted
- 2 -> 0 (MARKET_DATA_PUBLISH -> ORDER_ARRIVAL): not whitelisted
- 2 -> ... hmm, MARKET_DATA_PUBLISH doesn't produce queue events
- 3 -> 0 (AGENT_OBSERVE -> ORDER_ARRIVAL): not whitelisted, but AGENT_OBSERVE doesn't produce ORDER_ARRIVAL
- 4 -> 0 (AGENT_DECIDE -> ORDER_ARRIVAL): whitelisted
- 4 -> 3 (AGENT_DECIDE -> AGENT_OBSERVE): not whitelisted
- 5 -> 0 (SNAPSHOT -> ORDER_ARRIVAL): not whitelisted, but SNAPSHOT doesn't produce events
- 5 -> 3 (SNAPSHOT -> AGENT_OBSERVE): not whitelisted
- 5 -> 4 (SNAPSHOT -> AGENT_DECIDE): not whitelisted

For testing, I'll use:
1. AGENT_DECIDE(4) -> ORDER_ARRIVAL(0) with timestamp advance: pass
2. MARGIN_CALL(1) -> ORDER_ARRIVAL(0) with timestamp advance: pass (producer_class = MARGIN_CALL)
3. AGENT_DECIDE(4) -> AGENT_OBSERVE(3) with timestamp advance: fail (not whitelisted)

Now let me think about the design of the queue more carefully.

The queue needs:
- `enqueue(event_type, timestamp, producer_class=None, payload=None)` -> enqueue_seq
- `pop()` -> (event, transaction_seq) - pops the next event and assigns transaction_seq
- `peek()` -> event (look at the next event without popping)
- `__len__()` -> number of events in queue

The queue tracks:
- `_heap`: list of (QueueKey, counter, event_data) for heapq
- `_enqueue_seq`: global counter, increments on each enqueue
- `_transaction_seq`: global counter, increments on each pop
- `_current_key`: the QueueKey of the last popped event (for monotonicity check)
- `_bootstrap_done`: whether bootstrap is complete

Wait, actually, for the queue_key monotonicity check, the spec says:
> 事务处理期间新入队的队列事件 `e'` 必须满足：`queue_key(e') > queue_key(current_queue_event)`

So the check is against the current queue event being processed (the last popped event). If no event has been popped yet (empty queue at start), what do we compare against? The bootstrap events are enqueued first, so the first enqueue doesn't have a "current" event to compare against.

I think the check should be:
- If there's no current event (first enqueue), skip the check.
- Otherwise, compare queue_key(e') > queue_key(current).

But actually, the spec says "事务处理期间新入队的队列事件" - "events enqueued DURING transaction processing". So the check only applies when we're processing a transaction (i.e., during the execution of a popped event). Enqueuing the bootstrap events at startup (before any event is popped) doesn't need the check.

Hmm, but that's hard to distinguish in the API. Let me think...

Actually, the bootstrap events are enqueued before the kernel starts processing. The kernel's main loop pops an event, processes its transaction (which may enqueue new events), and repeats. The monotonicity check applies to events enqueued during transaction processing.

For the API, I can have:
- `enqueue(event_type, timestamp, ...)` - the main enqueue method, applies monotonicity check if there's a current event.
- The bootstrap enqueues can set a flag to bypass the check, or the check simply doesn't apply when there's no current event.

I'll go with: if there's no current event (no event has been popped yet), skip the monotonicity check. This is correct because the check is "during transaction processing", and if nothing has been popped, we're not processing a transaction.

Wait, but what about the bootstrap barrier? The barrier says: any business event enqueue before both snapshots are committed must raise exception. So during bootstrap, only SNAPSHOT events can be enqueued (by the bootstrap setup), and business events are rejected.

Let me design the bootstrap barrier:
- `BootstrapBarrier` class with `is_done` property.
- `mark_done()` called after both snapshots are committed.
- `check_can_enqueue_business_event()` raises if not done.

The queue's enqueue method checks the barrier: if the event is a business event (not SNAPSHOT) and bootstrap is not done, raise KernelAbort(INTERNAL).

Actually, the bootstrap snapshots are enqueued by the bootstrap module, not by business logic. So the barrier check is: if the event_type is not SNAPSHOT and bootstrap is not done, reject. The bootstrap module enqueues SNAPSHOT events directly, bypassing the barrier (or the barrier allows SNAPSHOT events).

Let me now think about the transaction buffer (T204c, T204d).

The transaction buffer:
- `start_transaction(transaction_seq, timestamp)` - starts a new transaction, resets record_index.
- `add_parent_record(record)` - adds the r0 record (ORDER_ARRIVAL or other queue event parent).
- `add_trade_settle(record)` - adds a TRADE_SETTLE record.
- `add_order_cancelled(record)` - adds an ORDER_CANCELLED record.
- `add_margin_call(record)` - adds a MARGIN_CALL record (added to the margin_call batch).
- `set_market_data_publish(record)` - sets the MARKET_DATA_PUBLISH record (only if book changed).
- `backfill_fill_count(count)` - backfills fill_count on all TRADE_SETTLE records.
- `commit()` - writes all records to the log in the frozen order.
- `discard()` - discards all records (on failure).

The frozen order:
```
r0: parent record (ORDER_ARRIVAL, etc.)
r1..rp: TRADE_SETTLE + ORDER_CANCELLED (interleaved by matching order)
r(p+1)..rq: MARGIN_CALL × m (sorted by agent_id ascending)
r(q+1): MARKET_DATA_PUBLISH (only if book changed)
```

For the interleaving of TRADE_SETTLE and ORDER_CANCELLED, they're added in the order they occur during matching. So the buffer just appends them as they come.

For MARGIN_CALL, they're sorted by agent_id ascending. So the buffer collects them and sorts before writing.

For MARKET_DATA_PUBLISH, it's always last (if present).

The buffer assigns record_index:
- r0: record_index = 0
- r1..rp: record_index = 1, 2, ...
- r(p+1)..rq: record_index = p+1, ..., q
- r(q+1): record_index = q+1

The assertions:
1. MARKET_DATA_PUBLISH is ALWAYS last record in transaction (if present).
2. accepted=false transactions have ONLY r0.
3. Transactions that don't change the book skip MARKET_DATA_PUBLISH.

For the fill_count backfill: after the matching loop, the caller calls `backfill_fill_count(count)` to set the fill_count on all TRADE_SETTLE records.

Now for T204d (fail-stop):
- When an exception occurs during transaction execution, the buffer is discarded.
- The log writer writes a RUN_TRAILER with terminated=ABORTED and abort_code.
- The failed transaction's records don't appear in the log.

The fault injection test: inject an exception after the first match. The test needs to:
1. Set up a transaction with some records.
2. Inject an exception.
3. Assert the run terminates.
4. Assert the log contains no records from the failed transaction.
5. Assert the trailer has terminated=ABORTED with abort_code.
6. Assert the failed transaction's transaction_seq doesn't appear in the log.

For the fault injection, I can use a callback/hook that's called at specific points and can raise an exception.

Now let me think about the event log writer (T204e, T204e2).

The event log writer:
- `write_run_header(fields)` - writes the RUN_HEADER record.
- `write_event(record)` - writes an EVENT record.
- `write_run_trailer(fields)` - writes the RUN_TRAILER record.
- `close()` - finalizes the log.

The RUN_HEADER fields (§6.1):
- record_kind: "RUN_HEADER"
- schema_version: int (2)
- run_id: str
- code_version: str
- config_hash: str
- master_seed: int
- started_at_wall: str (ISO 8601)
- tick_size: str (decimal, NOT float)
- min_quantity: str (decimal)
- cash_unit: str (decimal)
- run_mode: "benchmark" | "research" | "interactive"
- information_set_mode: "digest" | "full"

Wait, the task description lists fewer fields:
> RUN_HEADER fields (§6.1, frozen):
> - `record_kind`, `schema_version` (int), `run_id` (str), `code_version` (str), `config_hash` (str), `master_seed` (int), `started_at_wall` (str ISO 8601), `tick_size` (str decimal, NOT float), `min_quantity` (str decimal), `cash_unit` (str decimal)

It doesn't mention `run_mode` and `information_set_mode`. But the spec §6.1 includes them. Let me include all fields from the spec to be complete, but the task description focuses on the key ones. Actually, looking at the task more carefully, it says "RUN_HEADER fields (§6.1, frozen)" and lists specific fields. The spec has additional fields (run_mode, information_set_mode). I'll include all fields from the spec.

Wait, let me re-read the task:
> RUN_HEADER fields (§6.1, frozen):
> - `record_kind`, `schema_version` (int), `run_id` (str), `code_version` (str), `config_hash` (str), `master_seed` (int), `started_at_wall` (str ISO 8601), `tick_size` (str decimal, NOT float), `min_quantity` (str decimal), `cash_unit` (str decimal)

It lists 10 fields. The spec §6.1 has 12 fields (adding run_mode and information_set_mode). Since the task says "frozen" and lists specific fields, I'll include exactly those plus the ones from the spec. Let me include all 12 from the spec to be safe, since the task references §6.1.

Actually, the task says to read the contract documents. The spec §6.1 clearly lists all fields including run_mode and information_set_mode. I'll include them all.

For RUN_TRAILER fields (§6.2):
- record_kind: "RUN_TRAILER"
- terminated: "COMPLETED" | "ABORTED"
- abort_code: null when COMPLETED, stable enum when ABORTED
- abort_detail: string | null (not used in judgment)
- last_committed_transaction_seq: int | null
- record_count: int

For T204e2 (termination discrimination):
- Phase 1: JSON completeness / first+last records exist / record_count matches -> any failure = TI-5
- Phase 2: (only if Phase 1 passes) check terminated -> ABORTED = TI-4

I'll implement a `verify_log(log_bytes) -> VerificationResult` function that does the two-phase check.

The result should indicate:
- TI-4: structure OK, terminated=ABORTED
- TI-5: structure broken
- OK: structure OK, terminated=COMPLETED

Let me think about what "structure" means:
1. Every line is valid JSON (no truncation).
2. First line is RUN_HEADER (record_kind == "RUN_HEADER").
3. Last line is RUN_TRAILER (record_kind == "RUN_TRAILER").
4. record_count in RUN_TRAILER == actual number of lines.

If any of these fail -> TI-5.

If all pass -> check terminated:
- COMPLETED -> OK
- ABORTED -> TI-4

Now for the bootstrap (T204e3):

The bootstrap module:
- `create_bootstrap_snapshots(queue)` - enqueues the two SNAPSHOT events at timestamp=0.
  - ACCOUNT snapshot: enqueue_seq=0
  - BOOK snapshot: enqueue_seq=1
- `BootstrapBarrier` - tracks whether both snapshots are committed.
  - `mark_account_committed()` - called after ACCOUNT snapshot transaction commits.
  - `mark_book_committed()` - called after BOOK snapshot transaction commits.
  - `is_done` - True when both are committed.
  - `check_can_enqueue(event_type)` - raises if business event before bootstrap is done.

The three test vectors:
1. Normal run with zero business transactions -> exactly 2 EVENT records, last_committed_transaction_seq=2, COMPLETED
2. Second snapshot write fails -> ABORTED, last_committed_transaction_seq=1 (not null)
3. Business event tries to enqueue during bootstrap -> barrier rejects with INTERNAL

For test vector 2, the "second snapshot write fails" means the BOOK snapshot transaction fails. The ACCOUNT snapshot has already committed (transaction_seq=1), so last_committed_transaction_seq=1. The BOOK snapshot's transaction_seq=2 is discarded.

For test vector 3, a business event tries to enqueue before both snapshots are committed. The barrier rejects with INTERNAL.

The ACCOUNT snapshot must include ALL accounts, sorted by agent_id ascending. Since I'm not implementing account logic, I'll provide a way to pass the account data to the snapshot.

OK, I think I have enough understanding now
