---
tool: "opencode"
tool_name: "OpenCode"
session_id: "ses_03dabe95effezJzUy29E25zw2k"
title: "Phase 3 订单簿与撮合实现 (@Sisyphus-Junior subagent)"
project: "D:/Projects/market-game-sim"
model: "glm-5.2"
created_at: "2026-08-02T11:55:18Z"
updated_at: "2026-08-02T12:07:57Z"
tokens_input: 122378
tokens_output: 58424
cost: 0.0
parent_id: "ses_03dca8ceeffer5HK1H5NpzxJb9"
---

# Phase 3 订单簿与撮合实现 (@Sisyphus-Junior subagent)

## user · 2026-08-02T11:55:18Z

You are implementing **Phase 3** of milestone **0.1.1 (minimal deterministic kernel, no leverage)** in the project `D:\Projects\market-game-sim`. You must complete **all 8 Phase 3 tasks** in the dependency order below.

# EXISTING CODE (do not break)

Read these files first to understand current state:
- `src/market_game_sim/kernel/runner.py` — `EventKernel` with `TransactionHandler = Callable[[dict, dict, EventKernel], list[dict]]` callback. The kernel manages queue, transaction_seq, buffered atomic write, fail-stop, bootstrap. **You must inject the matching engine as a handler.**
- `src/market_game_sim/kernel/keys.py` — QueueKey, LogKey, PriorityClass
- `src/market_game_sim/kernel/scheduling.py` — KR-006 monotonicity, class regression whitelist
- `src/market_game_sim/kernel/abort.py` — KernelAbort, ABORT_CODES
- `src/market_game_sim/schema/registry.py` — SchemaRegistry, EVENT_TYPES, QUEUE_EVENTS, TRANSACTION_RECORDS
- `src/market_game_sim/schema/event_fields.json` — frozen schema source (do NOT modify)
- `src/market_game_sim/eventlog/writer.py` — RUN_HEADER, RUN_TRAILER serializers
- `src/market_game_sim/eventlog/digest.py` — blake2b digest
- `src/market_game_sim/eventlog/termination.py` — TI-4/TI-5 classifier
- `src/market_game_sim/eventlog/bootstrap.py` — snapshot payload builders
- `src/market_game_sim/config/parser.py` — ParsedConfig (MarketConfig, FeesConfig)
- `src/market_game_sim/config/types.py` — Price, Quantity, Cash, Bp, Nanos, div_ceil
- Tests that pass: 453/453. All must stay green.

# CONTRACT DOCUMENTS (read before implementing)

- `docs/contracts/matching.md` — primary contract for Phase 3 (§1 簿结构, §2 成交, §3 剩余处理, §4 自成交, §5 撮合顺序, §6 空簿/单边簿, §7 确定性)
- `docs/contracts/orderbook-vectors.md` — 8 acceptance vectors (OB-1—OB-7, OB-9a) with **exact integer expected values**
- `docs/contracts/event-schema.md` — §1.4 record order, §1.5 fail-stop, §4.2 fields, §4.7 cancel reasons
- `docs/contracts/degenerate-states.md` — §1 empty book / single-side

# TASK LIST (all 8 Phase 3 tasks, in dependency order)

The full task definitions are in `specs/v0.1-belief-testing-laboratory/0.1.1-minimal-kernel/tasks.md` lines 174-210. Read that file first. Below is the summary.

## Group A — 簿结构 + 撮合核心

**T301** [撮合 §1.1] [TDD] **订单簿结构**: 买方按 `price_ticks` 降序、卖方按升序；同价位按到达事务的 `transaction_seq` 升序。**禁止依赖字典遍历顺序**。Build a `Book` data structure in `src/market_game_sim/book/orderbook.py`. Use `SortedDict` from `sortedcontainers` (already a transitive dep of pytest) OR a plain `dict` with explicit sorted keys OR a list of (price, fifo_queue) — choose the one that's simplest, stdlib-only. **Actually**: prefer a `dict[price] -> deque[(order_id, agent_id, qty, txn_seq)]` plus a sorted-keys list maintained on insert/remove. Stdlib only.

**T302** [撮合 §2.1] [TDD] **成交价取 maker 挂单价**. Assertion: 买单限价 101 吃卖价 100 → 成交于 100. This is a unit test on the matching function.

**T303** [撮合 §2.2] [TDD] **跨档拆分**: 一张单吃多档 → 多个 TRADE_SETTLE, `caused_by_event_id` 相同、共享 `transaction_seq`、`record_index` 递增、`valuation_mark` **逐笔推进** (not整批共用). The kernel already backfills `fill_count` and assigns `record_index`; the matching engine must produce one `TRADE_SETTLE` per consumed level.

**T304** [撮合 §3] [事件 Schema §4.7] [TDD] **剩余处理**: 限价单挂入簿 (**保留到达事务的 `transaction_seq`** as the time-priority key, **不产生任何记录**); 市价单按 IOC 全额撤销并写 `ORDER_CANCELLED` (`reason=IOC_REMAINDER`, `price_ticks=null`). **挂入与撤销的不对称是有意的** (OB-5 vs OB-6): 撤销是主动状态变化, 挂入只是订单未被消耗的默认归宿.

**T305** [撮合 §4] [事件 Schema §4.7] [TDD] **自成交阻止 (cancel-resting)**: 撮合时遇到 `maker_agent_id == taker_agent_id` → 撤销簿上旧单并写 `ORDER_CANCELLED` (`reason=SELF_TRADE_PREVENTION`), taker 继续吃下一档、不消耗数量. **不是** `ORDER_ARRIVAL(action=CANCEL)` — 那是代理主动撤单指令, 属队列事件. 这里的是撮合过程的撤单**结果**, 是事务记录.

**T306** [撮合 §5] **准入与撮合的固定顺序**:
```text
1. 制度钩子校验 (v0.1 / D-1) — stub for 0.1.1 (always pass)
2. tick / min_quantity 对齐检查 — stub (always pass)
3. 初始保证金检查 (账户合同 §3.3) — stub (always pass), BUT **call point must be present** and `reserved_units` must be calculated by formula and written to a posting (T407b)
4. 撮合 (§2), 逐档生成 TRADE_SETTLE
5. 剩余部分按 §3 处理 (挂单 or 撤销)
6. 整批结算后执行两阶段风险检查 (§2.3) — stub for 0.1.1
7. 盘口变化则生成 MARKET_DATA_PUBLISH (恒为事务最后一条)
```
**Stub call points must all be in place**; `reserved_units` computed per formula even though 0.1.1 always passes admission.

**T306b** [撮合 §1.2] [事件 Schema §1.5] [TDD] **撮合事务的可见性原子性**: `ORDER_ARRIVAL` 弹出时在单个事务内完成撮合、逐笔结算、剩余处理、风险检查. 事务内账户变化立即生效, 其他事务观察不到中间态. **只做可见性原子性, 不做失败回滚** (T204d handles fail-stop). **Acceptance test**: 一张大单跨三档 → 三笔 `TRADE_SETTLE` (`fill_index` 0/1/2, `fill_count` 3) + **仅一次**整批风险检查. Expected values per [orderbook-vectors.md](../../../docs/contracts/orderbook-vectors.md) OB-4.

**T307** [撮合 §6] [退化 §1] [TDD] **空簿与单边簿**: 市价单 IOC 撤销, `mid` 未定义时 `valuation_mark` 退化为 `last`, 首笔成交前退化为 `initial_price` (= 20000 half-ticks in OB vectors).

## Group B — Acceptance vectors

**T308** [订单簿向量 OB-1—OB-7、OB-9a] [TDD] **八条订单簿向量全部通过** (退出条件 E3). Assert event sequence (including `MARKET_DATA_PUBLISH` 的存在与位置), `record_index`, `fill_index`/`fill_count`, 逐笔 `valuation_mark`/`risk_mark`, `ORDER_CANCELLED` 字段, 事务后簿状态, 全部为整数比较, **禁止容差断言**. **OB-8 与 OB-9b 不在 0.1.1 范围内** — 依赖杠杆账户, 属 0.1.2.

**Important**: The 8 vectors OB-1 through OB-7 plus OB-9a each have **full integer expected values** in `docs/contracts/orderbook-vectors.md`. Read every vector table carefully. For each vector, you must assert:
1. Exact event sequence (kind + `record_index`)
2. Each `TRADE_SETTLE` field: `price_ticks`, `quantity_units`, `maker_order_id`, `fill_index`, `fill_count`, `vm_before`, `vm_after`, `risk_mark`
3. `ORDER_CANCELLED` fields: `cancelled_qty_units`, `price_ticks`, `side`, `reason`
4. Post-transaction book state: aggregate qty per price level
5. All `log_key` strictly increasing

# IMPLEMENTATION REQUIREMENTS (MUST DO)

1. **TDD first for all [TDD] tasks**: Write failing test BEFORE the implementation. Run it (red), then implement, run again (green). For T301-T307, the unit tests are on individual invariants. For T308, build a single comprehensive test file with 8 vector scenarios.

2. **No breaking changes**: All 453 existing tests must still pass.

3. **Stdlib only in domain layer** (KR-005): `book/`, `kernel/`, `eventlog/`, `ledger/`, `rng/` must not import numpy, pandas, sortedcontainers, etc. Only stdlib. Use `dict` + `list` + `deque` for the book structure.

4. **Integer-only arithmetic in book/matching**: No float. All amounts in minimum units. Use `int` for ticks, units, half-ticks.

5. **Inject matching engine as `EventKernel` handler**: The matching logic should be a function `(event, world, kernel) -> records` (matches `TransactionHandler` signature from `kernel/runner.py`). The `world` dict holds the `Book` instance and account state (for T406, but 0.1.1 only needs the book).

6. **Build helper that runs an event list and returns all committed records**: This is the integration point. Write `src/market_game_sim/book/simulator.py` (or similar) with a function like:
```python
def run_simulation(
    initial_book_levels: list[BookLevel],  # resting orders at t=0 (post-bootstrap)
    events: list[dict],                     # ORDER_ARRIVAL events to enqueue
    parsed_config: ParsedConfig | None = None,
) -> tuple[list[dict], Book]:
    """Returns (committed_records, final_book). Bootstrap is called internally."""
```
For OB-1, the initial_book_levels are empty (the bootstrap book snapshot is empty per v0.1). Then events A, B, C are enqueued and processed. For OB-9a, the initial_book_levels contain the two resting sell orders (s1, s2), then A and B buy orders are processed.

7. **For OB vectors that need pre-existing resting orders**: Pass them as `initial_book_levels` to the simulator. The simulator should:
   - Create the EventKernel
   - Build empty ACCOUNT + BOOK snapshots for bootstrap
   - For each resting order in `initial_book_levels`, directly insert into the book (no event, no transaction) — this represents "the book has these resting orders when the run starts"
   - Enqueue and run the business events
   - Return the committed records and final book

8. **Use the schema registry** for all event field lookups. The matching engine must produce `TRADE_SETTLE` records with all required fields per `event_fields.json` §4.2.1. Same for `ORDER_CANCELLED` (§4.7) and `MARKET_DATA_PUBLISH` (§4.3).

9. **Field reference** — TRADE_SETTLE fields (from event_fields.json):
   - event_type, schema_version, run_id, timestamp, transaction_seq, record_index, event_id, priority_class, enqueue_seq
   - event_type-specific: trade_id, taker_order_id, taker_agent_id, maker_order_id, maker_agent_id, price_ticks, quantity_units, fill_index, fill_count, valuation_mark_before_half_ticks, valuation_mark_after_half_ticks, risk_mark_ticks, caused_by_event_id
10. **Field reference** — ORDER_CANCELLED fields:
    - event_type, schema_version, run_id, timestamp, transaction_seq, record_index, event_id, priority_class, enqueue_seq
    - event_type-specific: order_id, agent_id, side, order_type, price_ticks, cancelled_qty_units, reason, caused_by_event_id
11. **Field reference** — MARKET_DATA_PUBLISH fields:
    - event_type, schema_version, run_id, timestamp, transaction_seq, record_index, event_id, priority_class, enqueue_seq
    - event_type-specific: best_bid_ticks, best_ask_ticks, depth_changed (bool), k_level_snapshot (array of price+half_spread book levels? or simpler)
    - **For 0.1.1**: include best_bid, best_ask, depth levels, mid_half_ticks. Look at event_fields.json MARKET_DATA_PUBLISH section.
12. **valuation_mark** = mid in half-ticks. When both sides present: `(best_bid + best_ask)`. When one side empty: `last_ticks × 2`. Before first trade: `initial_price_ticks × 2`. So `initial_price_ticks=10000` → `vm=20000` half-ticks. These computations happen at the time of each fill (逐笔推进).

13. **risk_mark** = price_ticks of the current trade (per §2.2 last paragraph).

14. **`book` factor for single-side book**: §6 says `book` factor takes full bias ±1 when single-side. For 0.1.1, this is **recorded** in valuation_mark logic but doesn't affect matching.

15. **Reserved units** (T407b): per task "0.1.1 只需算出并记录该值" — for ORDER_ARRIVAL, compute `reserved_units = ceil(price_ticks * quantity_units * initial_margin_bp / 10_000)`. For 0.1.1 the margin check stub always passes, but the value must be recorded in the r0 (or in a separate field). Look at `reserved_delta_units` on ORDER_ARRIVAL — set it to the reserved amount for this order.

16. **Use existing helpers**: `div_ceil` from `config/types.py` for fee/quantity rounding. The matching engine should not duplicate rounding logic.

17. **Create files in the right location**:
    - `src/market_game_sim/book/__init__.py`
    - `src/market_game_sim/book/orderbook.py` — `Book`, `BookLevel`, `RestingOrder`
    - `src/market_game_sim/book/matching.py` — `match_order(event, book, world, kernel)` matching handler; `compute_reserved_units(order, market_config)` helper
    - `src/market_game_sim/book/simulator.py` — `run_simulation(initial_levels, events, market_config, agents)` integration
    - `tests/unit/book/test_orderbook.py` — T301, T307 unit tests
    - `tests/unit/book/test_matching.py` — T302-T306, T306b unit tests
    - `tests/unit/book/test_simulator.py` — T306b integration test (3 levels)
    - `tests/unit/book/test_orderbook_vectors.py` — T308 (8 vectors)
    - `tests/unit/book/test_self_trade.py` — T305 dedicated test

18. **Update tasks.md**: Mark each completed task as `[x]`. Lines 174-210 in `tasks.md`.

19. **Run `python -m pytest tests/ -x --tb=short` at the end**: All tests (453 old + new) must pass.

# MUST NOT DO

1. **Do NOT modify** `event_fields.json` — it's a frozen contract source.
2. **Do NOT modify** `kernel/runner.py` core semantics. You MAY add helper methods, but the existing T204b/c/d/e3 invariants must be preserved.
3. **Do NOT import numpy/pandas/sortedcontainers/etc.** in `book/`.
4. **Do NOT use floats** in book/matching. All ticks, units, half-ticks are int.
5. **Do NOT use `hash()`** for ordering. Use `transaction_seq` directly.
6. **Do NOT skip OB-9a** — it's the OB-9a = T204b acceptance; re-test it under T308 with the full matching engine (not the Phase 2 stub).
7. **Do NOT commit** — leave to user.

# EXPECTED OUTCOME

- All 8 Phase 3 tasks (T301-T308) implemented
- 8 acceptance vectors in T308 all pass with integer-exact assertions
- New tests added (estimate: 80-150 new tests for unit + 8 for vectors)
- `python -m pytest tests/ -x --tb=short` shows 100% pass
- `tasks.md` updated with `[x]` for the 8 completed tasks
- A summary report listing: (a) what you implemented, (b) new test count, (c) any contract defects (do NOT fix them), (d) design decisions made

# TOOLS

- `read`, `write`, `edit`, `bash` (Python and pytest), `grep`, `glob`
- `lsp_diagnostics` after edits
- `task(task_id=...)` if you need to continue across calls

# WORK APPROACH

1. Read `specs/v0.1-belief-testing-laboratory/0.1.1-minimal-kernel/tasks.md` lines 174-210
2. Read `docs/contracts/matching.md` in full
3. Read `docs/contracts/orderbook-vectors.md` in full (all 8 vectors + section 3 expected assertions)
4. Read `docs/contracts/event-schema.md` sections §1.4, §1.5, §4.2, §4.3, §4.7
5. Read `src/market_game_sim/schema/event_fields.json` sections for TRADE_SETTLE, ORDER_CANCELLED, MARKET_DATA_PUBLISH
6. Read existing `kernel/runner.py` to understand the handler signature
7. Read existing `config/parser.py` and `config/types.py` for MarketConfig, FeesConfig, div_ceil
8. Implement Book data structure + tests (T301)
9. Implement matching engine: price priority, time priority, maker price (T302-T303)
10. Implement remainder handling: LIMIT rest vs MARKET IOC (T304)
11. Implement self-trade prevention: cancel-resting (T305)
12. Wire up the order pipeline: admission stubs → matching → remainder → risk stub → market data (T306, T306b)
13. Implement empty/single-side book handling (T307)
14. Build simulator helper that runs a list of events
15. Write 8 acceptance vector tests (T308) — this is the integration test that ties everything together
16. Run full test suite, fix any breakage
17. Update tasks.md
18. Final pytest run + lsp_diagnostics
19. Report back

You have full context. Begin.
<!-- OMO_INTERNAL_INITIATOR -->

## assistant · 2026-08-02T11:55:18Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\specs\\v0.1-belief-testing-laboratory\\0.1.1-minimal-kernel\\tasks.md", "offset": 170, "limit": 50})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\docs\\contracts\\matching.md"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\docs\\contracts\\orderbook-vectors.md"})`


> [reasoning] Let me start by understanding the project structure and reading the key files mentioned in the task. I'll begin with reading the contract documents and existing code.

Let me start by exploring the codebase systematically.
我将首先阅读所有关键合同文档和现有代码文件，以便在进行任何实现之前建立完整的心智模型。

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\specs\v0.1-belief-testing-laboratory\0.1.1-minimal-kernel\tasks.md</path>
<type>file</type>
<content>
170:       非空数组必须产生不同的哈希输入。
171: 
172: ## Phase 3：订单簿与撮合
173: 
174: - [ ] **T301** `[撮合 §1.1]` `[TDD]` 订单簿结构：买降序/卖升序，同价按到达事务
175:       `transaction_seq` 升序。
176:       **禁止依赖字典遍历顺序**。
177: - [ ] **T302** `[撮合 §2.1]` `[TDD]` **成交价取 maker 挂单价**，非 taker 限价。
178:       用例：买单限价 101 吃卖价 100 → 成交于 100。
179: - [ ] **T303** `[撮合 §2.2]` `[TDD]` **跨档拆分**：一张单吃多档 → 多个
180:       `TRADE_SETTLE`，`caused_by_event_id` 相同、共享 `transaction_seq`、`record_index` 递增、
181:       `valuation_mark` **逐笔推进**（不是整批共用）。
182: - [ ] **T304** `[撮合 §3]` `[事件 Schema §4.7]` `[TDD]` 剩余处理：限价单挂入簿
183:       （**保留到达事务的 `transaction_seq`**，且**不产生任何记录**）；市价单按 IOC
184:       全额撤销并写 `ORDER_CANCELLED`
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\docs\contracts\matching.md</path>
<type>file</type>
<content>
1: # 撮合合同：订单簿与成交生成
2: 
3: **适用范围**：跨规格实现合同（当前交付规格 v0.1）  
4: **状态**：Stable（变更须记 ADR 并提升 `schema_version`）  
5: **创建日期**：2026-08-01　**更新日期**：2026-08-02  
6: **支撑需求**：v0.1 / FR-001—FR-003；PRD / PR-001  
7: **关联**：[事件 Schema](event-schema.md)、[账户与保证金](margin-and-account.md)、
8: [代理策略](agent-strategy.md)、[退化状态](degenerate-states.md)
9: 
10: ## 0. 本文为什么必须存在
11: 
12: 此前文档只说「价格时间优先的限价订单簿」，但**没有定义**：taker 吃 maker 时按谁的
13: 价成交、一张订单跨多档时产生几个 `TRADE_SETTLE`、限价单未成交部分的去向。
14: 
15: 这些是 0.1.1 第一天就会撞上的问题，且每一个都有多种合法实现。不定死，实现者的选择会
16: 直接改变成交价序列、`last` 的取值、乃至强平触发时点。
17: 
18: ## 1. 订单簿结构与定序
19: 
20: ### 1.1 价格时间优先
21: 
22: - **价格优先**：买方按 `price_ticks` **降序**、卖方按**升序**排队；
23: - **时间优先**：同价位内按订单到达事务的 **`transaction_se
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\docs\contracts\orderbook-vectors.md</path>
<type>file</type>
<content>
1: # 订单簿验收向量
2: 
3: **适用范围**：跨规格实现合同（当前交付规格 v0.1）  
4: **状态**：Stable（变更须同步[撮合合同](matching.md)）  
5: **创建日期**：2026-08-01　**更新日期**：2026-08-02  
6: **支撑需求**：v0.1 / FR-001—FR-003、SC-001；PRD / PR-001  
7: **关联**：[撮合](matching.md)、[事件 Schema](event-schema.md)、
8: [账户验收向量](acceptance-vectors.md)
9: 
10: ## 0. 用途
11: 
12: [撮合合同](matching.md) §8 的验收要点此前只有**场景描述**，没有期望值——
13: 实现者会写出自己认为对的测试，然后测试通过。本文补齐每条的**完整期望状态**：
14: 事件序列、每条记录的 `record_index`、成交价与量、`fill_index` / `fill_count`、
15: 逐笔 `valuation_mark` 与 `risk_mark`、以及事务后的簿状态。
16: 
17: 与[账户验收向量](acceptance-vectors.md)互补：那份管账本，这份管簿与撮合。
18: **两份都是实现的裁判**，实现与本表不符时以本表为准，除非能证明本表违反撮合合同。
19: 
20: ## 1. 公共约定
21: 
22: ```text
23: tick_size = 0.01        
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T11:55:26Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\kernel\\runner.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\kernel\\keys.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\kernel\\scheduling.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\kernel\\abort.py"})`


> [reasoning] Good, I now have the contract documents. Let me read the existing code to understand the current state.
现在让我并行读取现有的内核代码、模式（schema）和配置：

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
<path>D:\Projects\market-game-sim\src\market_game_sim\kernel\keys.py</path>
<type>file</type>
<content>
1: """T201 + T204: Dual ordering keys and frozen priority classes.
2: 
3: 事件 Schema §1 defines two independent ordering keys:
4: 
5: * ``queue_key = (timestamp, priority_class, enqueue_seq)``
6:     decides when a queue event pops.  Only queue events (§1.4) carry one.
7: * ``log_key = (timestamp, transaction_seq, record_index)``
8:     decides log order, hash order and replay order.  Every record carries one.
9: 
10: Three monotonic counters with **distinct scopes and allocation moments**
11: (事件 Schema §1):
12: 
13: * ``enqueue_seq``      allocated at enqueue time, global across the run.
14: * ``transaction_seq``  allocated when a queue event pops, global across the run.
15: * ``record_
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\kernel\scheduling.py</path>
<type>file</type>
<content>
1: """T202 + T203: Queue scheduling invariants (事件 Schema §1.1, §1.2).
2: 
3: Two invariants guard the event queue.  Both are fail-stop (§1.5): violation
4: means the kernel has a bug, and the run terminates with a specific
5: ``abort_code`` rather than silently reordering events.
6: 
7: * **KR-006 monotonicity (T202)**: every newly enqueued event must have a
8:   ``queue_key`` strictly greater than the current queue event's key.  The
9:   check happens at **enqueue time**, not at pop time -- a violated event
10:   must never enter the queue.
11: 
12: * **Class-regression whitelist (T203)**: when a new event's
13:   ``priority_class`` is lower than the producing event's class (a
14
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\kernel\abort.py</path>
<type>file</type>
<content>
1: """事件 Schema §6.2 稳定错误码与内核终止异常。
2: 
3: ``abort_code`` 是写入 ``RUN_TRAILER`` 的稳定枚举，新增须提升
4: ``schema_version``。``abort_detail`` 含异常消息与栈，不参与任何判定。
5: 
6: ``KernelAbort`` 是 fail-stop 的载体：事务中抛出时，内核终止整个运行，
7: 不回滚、不续跑（§1.5）。失败事务的缓冲整体丢弃（含 ``r0``），
8: 日志尾部写 ``terminated=ABORTED``。
9: """
10: 
11: from __future__ import annotations
12: 
13: from typing import Literal
14: 
15: AbortCode = Literal[
16:     "QUEUE_KEY_MONOTONICITY",
17:     "CLASS_REGRESSION_NOT_WHITELISTED",
18:     "CONSERVATION_BREACH",
19:     "ILLEGAL_STATE_TRANSITION",
20:     "CONFIG_INVARIANT",
21:     "INTERNAL",
22: ]
23: 
24: ABORT_CODES: tuple[str, ...] = (
25:     "QUEUE_KEY_MONOTONICITY",
26:     "CLASS_REGRESSION_NOT
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T11:55:33Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\schema\\registry.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\config\\types.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\config\\parser.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\eventlog\\bootstrap.py"})`


> [reasoning] Now let me read the schema registry, event fields, config types, and other relevant files.
现在让我读取 schema registry、event_fields.json、config 以及现有的测试：

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

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\eventlog\bootstrap.py</path>
<type>file</type>
<content>
1: """T204e3: Bootstrap snapshot helpers.
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
17: from typing import Any
18: 
19: 
20: def build_account_snapshot_entry(
21: 
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T11:55:38Z

- **tool**: `bash({"command": "python -c \"import json; data=json.load(open('src/market_game_sim/schema/event_fields.json', encoding='utf-8')); import sys; json.dump(data['structures'], sys.stdout, indent=2, ensure_ascii=False)\" 2>&1 | head -300"})`
- **tool**: `glob({"pattern": "tests/**/*.py"})`


> [reasoning] Now let me read the event_fields.json (just the relevant sections) and the existing kernel tests to understand the test patterns used:
现在让我读取 `event_fields.json` 以及现有的 kernel 测试，以了解其模式：

  <details><summary>tool output</summary>

  ```text
[31;1mhead: [31;1mThe term 'head' is not recognized as a name of a cmdlet, function, script file, or executable program.[0m
[31;1m[31;1mCheck the spelling of the name, or if a path was included, verify that the path is correct and try again.[0m
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
Found 20 file(s)

D:\Projects\market-game-sim\tests\unit\schema\test_registry_parity.py
D:\Projects\market-game-sim\tests\unit\eventlog\test_writer.py
D:\Projects\market-game-sim\tests\unit\kernel\test_event_kernel.py
D:\Projects\market-game-sim\tests\unit\eventlog\test_termination.py
D:\Projects\market-game-sim\tests\unit\eventlog\test_digest.py
D:\Projects\market-game-sim\tests\unit\schema\test_bidirectional_consistency.py
D:\Projects\market-game-sim\tests\unit\schema\test_constraint_fixtures.py
D:\Projects\market-game-sim\tests\unit\eventlog\test_bootstrap.py
D:\Projects\market-game-sim\tests\unit\eventlog\test_record_kinds.py
D:\Projects\market-game-sim\tests\unit\schema\test_posting_union.py
D:\Projects\market-game-sim\tests\unit\schema\__init__.py
D:\Projects\market-game-sim\tests\un
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T11:55:47Z

- **tool**: `bash({"command": "python -c \"\nimport json\ndata = json.load(open('src/market_game_sim/schema/event_fields.json', encoding='utf-8'))\nstructs = data['structures']\n# Print TRADE_SETTLE, ORDER_CANCELLED, MARKET_DATA_PUBLISH, ORDER_ARRIVAL\nfor et in ['ORDER_ARRIVAL', 'TRADE_SETTLE', 'ORDER_CANCELLED', 'MARKET_DATA_PUBLISH', 'BOOK_LEVEL', 'BOOK_PAYLOAD', 'EVENT_COMMON']:\n    print('=== ' + et + ' ===')\n    print(json.dumps(structs.get(et, {}), indent=2, ensure_ascii=False))\n    print()\n\""})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\tests\\unit\\kernel\\test_event_kernel.py"})`


> [reasoning] Let me read the event_fields.json directly to understand the structure - I'll use Python to extract just the relevant event types:
让我阅读 event_fields.json 的相关部分以及现有的内核测试：

  <details><summary>tool output</summary>

  ```text
=== ORDER_ARRIVAL ===
{
  "kind": "event",
  "priority_class": 0,
  "queueing": "queue_event",
  "fields": {
    "agent_id": {
      "value_type": "str",
      "nullable": false,
      "required": "always",
      "hash": "HASH_INCLUDE"
    },
    "order_id": {
      "value_type": "str",
      "nullable": false,
      "required": "always",
      "hash": "HASH_INCLUDE"
    },
    "action": {
      "value_type": "enum",
      "enum": [
        "SUBMIT",
        "CANCEL"
      ],
      "nullable": false,
      "required": "always",
      "hash": "HASH_INCLUDE"
    },
    "target_order_id": {
      "value_type": "str",
      "nullable": true,
      "required": "always",
      "hash": "HASH_INCLUDE",
      "constraints": [
        {
          "when": {
       
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\tests\unit\kernel\test_event_kernel.py</path>
<type>file</type>
<content>
1: """T204b/c/d: Event kernel behavior -- queue vs transaction records,
2: buffered atomic write, and fail-stop semantics.
3: 
4: [事件 Schema §1.4] 队列事件 vs 事务记录
5: [事件 Schema §1.4] 事务内记录顺序 + 缓冲写出
6: [事件 Schema §1.5] fail-stop 失败语义
7: [订单簿向量 OB-9a] 同时间戳双订单看到已提交状态
8: """
9: 
10: from __future__ import annotations
11: 
12: import copy
13: from typing import Any
14: 
15: import pytest
16: 
17: from market_game_sim.eventlog.bootstrap import (
18:     build_account_payload,
19:     build_account_snapshot_entry,
20:     build_book_payload,
21: )
22: from market_game_sim.eventlog.termination import classify_log
23: from market_game_sim.eventlog.writer import build_run_header, serialize_log
24
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T11:55:53Z

- **tool**: `bash({"command": "cd /d D:\\Projects\\market-game-sim && python -m pytest tests/ --co -q 2>&1 | findstr /C:\"test\" /C:\"error\" | findstr /V /C:\"::\""})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\eventlog\\writer.py", "limit": 60})`


> [reasoning] Now I have a thorough understanding. Let me check the event-schema.md sections §1.4, §1.5, §4.2, §4.3, §4.7 and the degenerate-states.md §1. But actually, the matching.md and orderbook-vectors.md already gave me the full picture. Let me also check the writer and digest to understand serialization.

Let me now also look at the degenerate-states.md §1 and event-schema.md §1.4/§1.5 to make sure I have all the context I need. But the contracts I've already read are quite detailed. Let me also peek at the writer to understand how records are built.

Actually, I have enough context now. Let me think about the design.

## Design

### Book structure (T301)

Per the task instructions, prefer `dict[price] -> deque[(order_id, agent_id, qty, txn_seq)]` plus a sorted-keys list maintained on insert/remove. Stdlib only.

Actually, let me think more carefully. The book needs:
- bids: price descending, same price by transaction_seq ascending
- asks: price ascending, same price by transaction_seq ascending

Since within a price level orders are appended in arrival order (transaction_seq ascending), and we always consume from the front, a `deque` per price level works perfectly as a FIFO queue. The transaction_seq is monotonic, so appending maintains the order automatically.

For the sorted keys:
- bids: we need descending order, so best bid = max price
- asks: we need ascending order, so best ask = min price

I'll use a simple approach:
- `bids: dict[int, deque[RestingOrder]]` where we maintain a sorted list of keys descending
- `asks: dict[int, deque[RestingOrder]]` where we maintain a sorted list of keys ascending

Actually, to keep it really simple and stdlib-only, I can use `bisect` on a list of price keys. Let me think:
- For asks: keep `ask_prices: list[int]` sorted ascending. Use `bisect.insort` to insert. Best ask = `ask_prices[0]`.
- For bids: keep `bid_prices: list[int]` sorted descending. I can keep a list sorted ascending and reverse, OR keep a list sorted descending and use a custom bisect. Actually, simplest: keep `bid_prices: list[int]` sorted ascending (same as asks), then best bid = `bid_prices[-1]`.

Wait, but then removing a price level when empty requires removing from the list. `list.remove` is O(n) but that's fine for 0.1.1.

Actually let me reconsider. The simplest stdlib-only approach that's clean:

```python
class Book:
    def __init__(self):
        self._bids: dict[int, deque[RestingOrder]] = {}  # price -> queue
        self._asks: dict[int, deque[RestingOrder]] = {}  # price -> queue
        self._bid_prices: list[int] = []  # sorted descending
        self._ask_prices: list[int] = []  # sorted ascending
        self.last_ticks: int | None = None
```

For insertion:
- Insert into the dict's deque (append right)
- If price not in list, use bisect to insert maintaining sort order

For best bid: `self._bid_prices[0]` if descending, or `self._bid_prices[-1]` if ascending. Let me keep bid_prices sorted descending (so best bid is index 0) and ask_prices sorted ascending (best ask is index 0). This is symmetric and clean.

To insert into a descending list with bisect, I can negate the price: `bisect.insort(self._bid_prices_neg, -price)` and best bid = `-self._bid_prices_neg[0]`. Hmm, that's a bit ugly. 

Alternative: just keep both as ascending and access bid best as [-1]. When iterating bids for display, reverse. This is clean and bisect works directly.

Let me go with:
- `_bid_prices: list[int]` sorted ascending (best bid = last element)
- `_ask_prices: list[int]` sorted ascending (best ask = first element)

Insert: `bisect.insort(prices, price)` — but only if price not already in list.
Remove: `prices.remove(price)` when level becomes empty.

Actually wait, there's a subtlety. `bisect.insort` on a list is O(n) for the insert anyway. So I could just as easily maintain a sorted list without bisect. But bisect gives O(log n) search + O(n) insert, which is fine.

Let me design the RestingOrder:

```python
@dataclass
class RestingOrder:
    order_id: str
    agent_id: str
    side: str  # BUY or SELL
    order_type: str  # LIMIT
    price_ticks: int
    quantity_units: int
    transaction_seq: int  # time-priority key
```

Book operations needed:
- `insert(order)` - add a resting order
- `best_bid()` -> int | None
- `best_ask()` -> int | None
- `peek_opposite(side)` -> best price of opposite side
- `pop_maker(side)` -> RestingOrder (consume from front of best level's deque, remove level if empty)
- `consume(order, qty)` - reduce quantity, remove if zero
- `cancel(order)` - remove a specific order (for self-trade)
- `aggregate_level(side, price)` -> total qty at that price
- `book_state()` -> list of (price, qty) for bids descending and asks ascending

Actually, for the matching engine, I need to:
1. Get the best maker order on the opposite side
2. Check if it's a self-trade
3. If self-trade, cancel the maker (remove from book), write ORDER_CANCELLED, continue
4. Otherwise, fill at maker price, reduce quantities

Let me think about the matching flow:

```
def match_order(event, world, kernel):
    book = world["book"]
    taker_side = event["side"]  # BUY or SELL
    taker_agent = event["agent_id"]
    taker_order_id = event["order_id"]
    taker_qty = event["quantity_units"]
    limit_price = event["price_ticks"]  # None for MARKET
    
    opposite = "SELL" if taker_side == "BUY" else "BUY"
    
    records = []
    fills = []  # for backfilling fill_count later (kernel does this)
    remaining = taker_qty
    vm_before = book.valuation_mark(initial_price_ticks)  # current vm
    
    while remaining > 0:
        maker = book.peek_best(opposite)
        if maker is None:
            break
        # Check price crossing
        if taker_side == "BUY":
            if limit_price is not None and maker.price_ticks > limit_price:
                break
        else:
            if limit_price is not None and maker.price_ticks < limit_price:
                break
        # Check self-trade
        if maker.agent_id == taker_agent:
            # cancel-resting
            book.remove_order(maker)
            records.append(make_order_cancelled(maker, "SELF_TRADE_PREVENTION", event))
            continue  # don't consume qty
        # Fill
        fill_qty = min(remaining, maker.quantity_units)
        vm_before_this = vm_before
        # Execute fill
        maker.quantity_units -= fill_qty
        remaining -= fill_qty
        if maker.quantity_units == 0:
            book.remove_order(maker)
        book.last_ticks = maker.price_ticks
        vm_after_this = book.valuation_mark(initial_price_ticks)
        vm_before = vm_after_this  # for next iteration
        records.append(make_trade_settle(...))
    
    # Remainder handling
    if remaining > 0:
        if event["order_type"] == "LIMIT":
            # Rest in book with original transaction_seq
            book.insert(RestingOrder(
                order_id=taker_order_id,
                agent_id=taker_agent,
                side=taker_side,
                order_type="LIMIT",
                price_ticks=limit_price,
                quantity_units=remaining,
                transaction_seq=kernel.current_transaction_seq,  # the ORDER_ARRIVAL's txn_seq
            ))
            # No record produced
        else:  # MARKET
            records.append(make_order_cancelled_ioc(event, remaining))
    
    # Market data publish if book changed
    if book_changed:
        records.append(make_market_data_publish(book))
    
    return records
```

Wait, I need to be careful about `valuation_mark`. Let me re-read the contract:

From orderbook-vectors.md §1:
```
两侧皆有报价：vm = best_bid_ticks + best_ask_ticks
任一侧为空　：vm = last_ticks × 2
首笔成交之前：vm = initial_price_ticks × 2 = 20000
```

So vm is computed in half-ticks:
- Both sides present: `best_bid + best_ask` (sum, not average — because these are already in ticks, and mid = (bid+ask)/2 in ticks, so mid in half-ticks = bid+ask)
- One side empty: `last_ticks × 2` (mid = last in ticks, so mid in half-ticks = last × 2)
- Before first trade (last is None): `initial_price_ticks × 2`

Important note from OB-5/OB-6: `vm_after` measures the market **right after this fill completes**, but **before the taker's remainder is rested**. So after eating the only ASK level, both sides might be empty, and vm_after = last × 2.

Let me trace OB-4 to verify my understanding:

OB-4: Pre-existing: M sells 100×2, 101×2, 102×2; N buys 99×10.
So before T's order:
- bids: [(99, 10000)]  (N's buy at 99, qty 10 = 10000 units)
- asks: [(100, 2000), (101, 2000), (102, 2000)]
- last = None (no trade yet) — wait, but N's buy didn't match because there were no asks when... 

Hmm, wait. Actually the "pre-existing" orders are set up before T's order. But if N's buy at 99 is in the book, and M's sells at 100/101/102 are also in the book, there's no crossing (99 < 100), so no trade. last = None.

But wait, OB-4 says `vm_before=19900` for the first fill. 19900 = 99×100 + 100×100 = 9900 + 10000 = 19900. That's `best_bid + best_ask = 9900 + 10000 = 19900`. So both sides are present before T's order. And last is None but that doesn't matter because both sides are present.

Actually wait, initial_price_ticks = 10000, so initial_price × 2 = 20000. But vm_before for the first fill is 19900, not 20000. That's because both sides ARE present (bid=99, ask=100), so we use `best_bid + best_ask = 9900 + 10000 = 19900`, not the initial_price fallback.

The "首笔成交之前：vm = initial_price_ticks × 2 = 20000" only applies when both sides are NOT present (or rather, when we can't compute mid from the book). Let me re-read:

```
两侧皆有报价：vm = best_bid_ticks + best_ask_ticks
任一侧为空　：vm = last_ticks × 2
首笔成交之前：vm = initial_price_ticks × 2 = 20000
```

So the priority is:
1. If both sides have quotes: `best_bid + best_ask`
2. Else if last exists (at least one trade has happened): `last × 2`
3. Else (no trade yet, at least one side empty): `initial_price × 2`

Let me verify with OB-1:
- Before C's sell (tx 3): bids = [(10100, 5000), (10000, 5000)], asks = []. last = None.
- C sells 3000 at 10000, matches o2 (buy at 10100). 
- vm_before: asks is empty, last is None -> initial_price × 2 = 20000. ✓
- After fill: o2 has 2000 remaining, still in bids. asks still empty. last = 10100.
- vm_after: asks empty, last = 10100 -> 10100 × 2 = 20200. ✓

OB-3:
- Before B's buy (tx 2): asks = [(10000, 5000)], bids = []. last = None.
- vm_before: bids empty, last None -> initial_price × 2 = 20000. ✓
- After fill: asks = [(10000, 2000)], bids empty. last = 10000.
- vm_after: bids empty, last = 10000 -> 10000 × 2 = 20000. ✓

OB-4 trace:
- Pre: bids = [(9900, 10000)], asks = [(10000, 2000), (10100, 2000), (10200, 2000)]. last = None.
- T buys 5000 at 10200.
- Fill 1: eat a1 at 10000, qty 2000.
  - vm_before: both sides present -> 9900 + 10000 = 19900. ✓
  - After: asks = [(10100, 2000), (10200, 2000)], bids unchanged. last = 10000.
  - vm_after: both sides present -> 9900 + 10100 = 20000. ✓
- Fill 2: eat a2 at 10100, qty 2000.
  - vm_before: both sides present -> 9900 + 10100 = 20000. ✓
  - After: asks = [(10200, 2000)], bids unchanged. last = 10100.
  - vm_after: both sides present -> 9900 + 10200 = 20100. ✓
- Fill 3: eat a3 at 10200, qty 1000 (only 1000 of 2000 consumed).
  - vm_before: both sides present -> 9900 + 10200 = 20100. ✓
  - After: asks = [(10200, 1000)], bids unchanged. last = 10200.
  - vm_after: both sides present -> 9900 + 10200 = 20100. ✓ (best_ask didn't change because a3 still has 1000 remaining)

Great, my understanding is correct.

Now let me verify OB-5:
- Pre: asks = [(10000, 2000)], bids = []. last = None.
- T buys 5000 at 10000 (LIMIT).
- Fill 1: eat s1 at 10000, qty 2000.
  - vm_before: bids empty, last None -> initial_price × 2 = 20000. ✓
  - After fill: asks = [], bids empty (taker remainder not yet rested). last = 10000.
  - vm_after: both sides empty, last = 10000 -> 10000 × 2 = 20000. ✓
- Remainder: 3000 units, LIMIT -> rest in book at 10000.
- After rest: bids = [(10000, 3000)], asks = [].
- MARKET_DATA_PUBLISH: best_bid=10000, best_ask=null. ✓

OB-6 (MARKET version):
- Same as OB-5 but T buys 5000 MARKET (price_ticks=null).
- Fill 1: same as OB-5.
- Remainder: 3000 units, MARKET -> IOC cancel.
  - ORDER_CANCELLED: order_id=T's order, cancelled_qty=3000, price_ticks=null (market order), side=BUY, order_type=MARKET, reason=IOC_REMAINDER. ✓
- After cancel: both sides empty.
- MARKET_DATA_PUBLISH: best_bid=null, best_ask=null. ✓

OB-7 (self-trade):
- Pre: s1 = A sells 100×2 (10000, 2000), s2 = B sells 101×2 (10100, 2000). 
- T = A buys 101×3 (10100, 3000).
- Matching:
  - Best ask = s1 at 10000. A is taker, s1.agent_id = A = taker_agent. SELF-TRADE!
  - Cancel s1: ORDER_CANCELLED(order_id=s1, agent_id=A, cancelled_qty=2000, price_ticks=10000, side=SELL, order_type=LIMIT, reason=SELF_TRADE_PREVENTION). record_index=1.
  - Taker qty unchanged (3000).
  - Next best ask = s2 at 10100. s2.agent_id = B ≠ A. 
  - Price check: taker limit 10100 >= maker 10100. Cross!
  - Fill: qty = min(3000, 2000) = 2000. 
    - vm_before: bids empty, last None -> initial_price × 2 = 20000. ✓
    - After: s2 consumed, asks = []. last = 10100.
    - vm_after: both sides empty (taker remainder not rested yet), last = 10100 -> 20200. ✓
    - TRADE_SETTLE: price=10100, qty=2000, maker=s2, fill_index=0, fill_count=1, risk_mark=10100. record_index=2.
  - Remainder: 3000-2000=1000, LIMIT -> rest at 10100.
  - After rest: bids = [(10100, 1000)], asks = [].
  - MARKET_DATA_PUBLISH: best_bid=10100, best_ask=null. record_index=3.

This matches the expected OB-7 output. ✓

Now, the record_index assignment: the kernel assigns record_index starting from 1 for the first record returned by the handler (r0 is index 0). So the handler returns records in order, and the kernel assigns indices 1, 2, 3, ...

For OB-7, the handler returns:
1. ORDER_CANCELLED (s1, self-trade) -> record_index=1
2. TRADE_SETTLE (s2) -> record_index=2
3. MARKET_DATA_PUBLISH -> record_index=3

The kernel backfills fill_index and fill_count on TRADE_SETTLE records. Since there's only 1 TRADE_SETTLE, fill_index=0, fill_count=1.

Now, about the `caused_by_event_id`: The kernel builds r0 with `event_id = f"e{txn_seq}_{0}"`. So for transaction_seq=3, r0's event_id = "e3_0". The TRADE_SETTLE and ORDER_CANCELLED records should have `caused_by_event_id` pointing to this r0 event_id.

But wait — the handler runs before r0 is built (the handler returns records, then the kernel builds r0). So the handler doesn't know the event_id yet. Looking at the kernel code:

```python
records = handler(event, world, self)
# ...
r0 = self._build_record(event, txn_seq, 0, event.get("_enqueue_seq"))
buffer.append(r0)
# ...
for idx, r in enumerate(records, start=1):
    buffer.append(self._build_record(r, txn_seq, idx, None))
```

So the handler can't set `caused_by_event_id` because it doesn't know the event_id. But the schema requires it. Hmm.

Looking at the existing test stub, it doesn't set `caused_by_event_id` either. Let me check if the kernel backfills it... No, it doesn't. 

So either:
1. The handler needs to know the transaction_seq to construct the event_id, OR
2. The kernel should backfill `caused_by_event_id`, OR
3. The handler sets it to a placeholder and the kernel fixes it.

Actually, the handler receives the kernel as a parameter. But `kernel._transaction_seq` is private. However, `kernel.last_committed_transaction_seq` gives the PREVIOUS transaction_seq, and the current one is `last_committed + 1` (or 1 if None). But that's fragile.

Wait, let me look at the kernel more carefully. In `_run_transaction`:
```python
self._transaction_seq += 1
txn_seq = self._transaction_seq
self._current_event = event
# ...
records = handler(event, world, self)
```

So when the handler runs, `self._transaction_seq` is already set to the current transaction_seq. But it's a private attribute. I could add a property to expose it.

Actually, looking at the task description: "The kernel already backfills `fill_count` and assigns `record_index`". It doesn't mention backfilling `caused_by_event_id`. Let me add a property to expose the current transaction_seq, and the handler can compute `caused_by_event_id = f"e{txn_seq}_0"`.

Wait, but the task says "Do NOT modify kernel/runner.py core semantics. You MAY add helper methods". So I can add a property `current_transaction_seq` to the kernel.

Let me add:
```python
@property
def current_transaction_seq(self) -> int:
    return self._transaction_seq
```

Then in the handler:
```python
caused_by = f"e{kernel.current_transaction_seq}_0"
```

This is safe because `_transaction_seq` is set at the start of `_run_transaction` before the handler is called.

Actually, let me also check: does `event_id` use the format `f"e{txn_seq}_{record_idx}"`? Yes: `record["event_id"] = f"e{txn_seq}_{record_idx}"`. So r0's event_id = `f"e{txn_seq}_0"`. The handler can construct this.

Now, about `trade_id`: The schema says it's a str, HASH_EXCLUDE. It should be unique per trade. I'll generate it as `f"t{txn_seq}_{fill_index}"` or similar.

Now let me think about the `notional_cash_units`, `maker_fee_cash_units`, `taker_fee_cash_units`. The task says "本文不含账户与手续费" for the OB vectors. But the TRADE_SETTLE schema requires these fields. For 0.1.1, I think we can set them to 0 or compute them. The task says "Use `div_ceil` from `config/types.py` for fee/quantity rounding. The matching engine should not duplicate rounding logic."

Actually, looking at the OB vectors, they don't assert on notional/fees. So I can compute them correctly using the formula:
- `notional_cash_units = price_ticks * quantity_units` (this is the cash notional in tick×unit units)

Wait, actually what's the cash unit? The config has `cash_unit` as a Decimal. The notional in cash units would be `price_ticks * quantity_units * tick_size * min_quantity / cash_unit`. But that involves Decimal division...

Hmm, for 0.1.1, since the OB vectors don't assert on notional/fees, and the task says "本文不含账户与手续费", I think I should compute them but the values don't matter for the OB vector assertions. Let me compute them properly:

Actually, looking at the existing test stub:
```python
"notional_cash_units": fill["price_ticks"] * fill["quantity_units"],
"maker_fee_cash_units": 0,
"taker_fee_cash_units": 0,
```

So the stub just uses `price × qty` for notional and 0 for fees. For 0.1.1, since there's no account/fee logic yet (that's Phase 4), I'll follow the same pattern. The fees will be computed properly in Phase 4 with the account engine.

Actually, let me reconsider. The task says "Use `div_ceil` from `config/types.py` for fee/quantity rounding." But fees require the fee bps from config, and 0.1.1's OB vectors don't test fees. The matching engine should compute fees using `round_fee(notional, bps)` from config/types.py. But for 0.1.1, maybe I should compute them correctly since the config is available.

Let me look at the notional computation more carefully. The `notional_cash_units` is the cash value of the trade. In this system:
- `price_ticks` is price in tick units (tick_size = 0.01)
- `quantity_units` is quantity in min_quantity units (min_quantity = 0.001)
- `cash_unit` is the cash unit (e.g., 0.01)

So `notional = price × quantity = (price_ticks × tick_size) × (quantity_units × min_quantity)`. In cash units: `notional_cash_units = notional / cash_unit = (price_ticks × tick_size × quantity_units × min_quantity) / cash_unit`.

For the OB vectors: tick_size = 0.01, min_quantity = 0.001, cash_unit = 0.01.
`notional_cash_units = (price_ticks × 0.01 × quantity_units × 0.001) / 0.01 = price_ticks × quantity_units × 0.001`

But this would be a float... and we need integers. Let me think about this differently.

Actually, I think for 0.1.1, the notional and fees can be computed but they're not asserted in the OB vectors. The important thing is that the fields are present. Let me compute them using integer arithmetic with the config's Decimal values converted to int relationships.

Actually, this is getting complicated. Let me look at what the existing stub does and just follow that pattern for now. The stub uses `price_ticks * quantity_units` for notional and 0 for fees. This is technically wrong (the units don't match), but since 0.1.1 doesn't test account/fee values, and the task says "本文不含账户与手续费", I'll do the same. Phase 4 (T401+) will fix the notional/fee computation when the account engine is built.

Wait, but I need to be more careful. Let me re-read the task requirements:

"16. Use existing helpers: div_ceil from config/types.py for fee/quantity rounding. The matching engine should not duplicate rounding logic."

This suggests I should use div_ceil for fee computation. But the fee computation requires `round_fee(notional, bps)` which requires knowing the notional in cash units and the fee bps.

For 0.1.1, I think the approach is:
1. Compute `notional_cash_units` properly using integer arithmetic
2. Compute fees using `round_fee(notional, maker_bps)` and `round_fee(notional, taker_bps)`
3. But since there are no accounts in 0.1.1, the postings array will be empty

Actually, let me look at this from a practical standpoint. The OB vectors only assert on:
- event_type, record_index
- TRADE_SETTLE: price_ticks, quantity_units, maker_order_id, fill_index, fill_count, vm_before, vm_after, risk_mark
- ORDER_CANCELLED: cancelled_qty_units, price_ticks, side, reason
- Post-transaction book state
- log_key monotonicity

They do NOT assert on notional_cash_units, maker_fee, taker_fee, postings, trade_id, caused_by_event_id.

So I can set these to reasonable values. For notional, I'll compute `price_ticks * quantity_units` (which is in tick×unit space, not真正的 cash units, but it's an integer and present). For fees, I'll compute them properly using round_fee if the config is available, or 0 if not.

Actually, let me just compute fees properly. The config has maker_bps and taker_bps. If I have a ParsedConfig, I can compute:
```python
notional = price_ticks * quantity_units  # tick×unit units
maker_fee = round_fee(notional, maker_bps)
taker_fee = round_fee(notional, taker_bps)
```

But the notional units are wrong... `price_ticks * quantity_units` is in "tick × min_qty" units, not in cash units. To get cash units, I'd need to multiply by tick_size and min_quantity and divide by cash_unit. But those are Decimals.

For 0.1.1, let me keep it simple: set notional_cash_units = price_ticks * quantity_units, fees = 0. This matches the existing test stub. Phase 4 will fix the units when accounts are implemented. The OB vectors don't assert on these fields.

Actually, I realize I should think about this differently. The task says to build a `run_simulation` function that takes an optional `ParsedConfig`. If no config is provided, I'll use default values. Let me define default market config values matching the OB vector conventions:

```python
DEFAULT_INITIAL_PRICE_TICKS = 10000
DEFAULT_TICK_SIZE = Decimal("0.01")
DEFAULT_MIN_QUANTITY = Decimal("0.001")
DEFAULT_CASH_UNIT = Decimal("0.01")
DEFAULT_FEES = FeesConfig(maker_bps=0, taker_bps=0)
```

With 0 fees, the fee computation is trivially 0. And for notional, I'll use `price_ticks * quantity_units` for now.

OK let me now plan the implementation:

### Files to create:

1. `src/market_game_sim/book/__init__.py`
2. `src/market_game_sim/book/orderbook.py` - Book, RestingOrder
3. `src/market_game_sim/book/matching.py` - match_order handler, compute_reserved_units
4. `src/market_game_sim/book/simulator.py` - run_simulation

### Files to create (tests):

5. `tests/unit/book/__init__.py`
6. `tests/unit/book/test_orderbook.py` - T301, T307
7. `tests/unit/book/test_matching.py` - T302-T306, T306b
8. `tests/unit/book/test_simulator.py` - T306b integration
9. `tests/unit/book/test_orderbook_vectors.py` - T308 (8 vectors)
10. `tests/unit/book/test_self_trade.py` - T305

### Files to modify:

11. `src/market_game_sim/kernel/runner.py` - add `current_transaction_seq` property
12. `specs/.../tasks.md` - mark tasks [x]

Let me start implementing. I'll follow TDD: write tests first, run them (red), implement, run again (green).

Actually, the task says to write failing tests first. But given the scale of this task (8 tasks, many tests), let me be pragmatic. I'll write the implementation and tests together for each component, then run the full suite. The TDD requirement is that tests exist and pass, and that they test the right invariants. I'll make sure all tests are comprehensive.

Wait, the task explicitly says "TDD first for all [TDD] tasks: Write failing test BEFORE the implementation. Run it (red), then implement, run again (green)." Let me follow this properly, at least for the key components.

Actually, given the complexity, let me be smart about this. I'll:
1. Write the Book class + tests, run (some pass, some fail)
2. Write the matching engine + tests
3. Write the simulator + tests
4. Write the OB vector tests
5. Run everything

Let me start with the Book structure and its tests.

Actually, let me think about the design more carefully before coding.

### Book design

```python
from __future__ import annotations
from dataclasses import dataclass, field
from collections import deque
import bisect

@dataclass
class RestingOrder:
    """A resting order in the book."""
    order_id: str
    agent_id: str
    side: str  # "BUY" or "SELL"
    order_type: str  # "LIMIT"
    price_ticks: int
    quantity_units: int
    transaction_seq: int  # time-priority key (KR-003)

class Book:
    """Price-time priority order book (T301).
    
    Bids: price descending (best = highest), same price by transaction_seq ascending.
    Asks: price ascending (best = lowest), same price by transaction_seq ascending.
    
    No dict iteration order dependency. Stdlib only (KR-005).
    """
    
    def __init__(self, initial_price_ticks: int = 10000) -> None:
        self._bids: dict[int, deque[RestingOrder]] = {}
        self._asks: dict[int, deque[RestingOrder]] = {}
        # Sorted price lists for O(log n) lookup
        self._bid_prices: list[int] = []  # sorted ascending
        self._ask_prices: list[int] = []  # sorted ascending
        self.last_ticks: int | None = None
        self._initial_price_ticks = initial_price_ticks
    
    def insert(self, order: RestingOrder) -> None:
        """Insert a resting order into the book."""
        book = self._bids if order.side == "BUY" else self._asks
        prices = self._bid_prices if order.side == "BUY" else self._ask_prices
        price = order.price_ticks
        if price not in book:
            book[price] = deque()
            bisect.insort(prices, price)
        book[price].append(order)
    
    def best_bid(self) -> int | None:
        if not self._bid_prices:
            return None
        return self._bid_prices[-1]  # highest
    
    def best_ask(self) -> int | None:
        if not self._ask_prices:
            return None
        return self._ask_prices[0]  # lowest
    
    def best_opposite(self, side: str) -> int | None:
        if side == "BUY":
            return self.best_ask()
        return self.best_bid()
    
    def peek_best_maker(self, side: str) -> RestingOrder | None:
        """Peek at the best maker order on the given side (the side we're matching against)."""
        book = self._bids if side == "BUY" else self._asks
        prices = self._bid_prices if side == "BUY" else self._ask_prices
        if not prices:
            return None
        best_price = prices[-1] if side == "BUY" else prices[0]
        return book[best_price][0]  # front of queue
    
    def consume_front(self, side: str, qty: int) -> tuple[RestingOrder, int]:
        """Consume qty from the front maker order on the given side.
        Returns (maker_order, fill_qty). Removes the order if fully consumed."""
        ...
    
    def remove_order(self, order: RestingOrder) -> None:
        """Remove a specific order from the book (for self-trade cancellation)."""
        ...
    
    def valuation_mark_half_ticks(self) -> int:
        """Compute valuation_mark in half-ticks (§6)."""
        bb = self.best_bid()
        ba = self.best_ask()
        if bb is not None and ba is not None:
            return bb + ba
        if self.last_ticks is not None:
            return self.last_ticks * 2
        return self._initial_price_ticks * 2
    
    def aggregate_levels(self) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
        """Return (bids, asks) where each is [(price, total_qty), ...].
        Bids sorted descending, asks sorted ascending."""
        ...
```

Wait, I need to be careful with `peek_best_maker` and `consume_front`. The matching engine needs to:
1. Peek at the best maker
2. Decide if it's a self-trade
3. If self-trade, remove the entire order
4. If not, fill partially or fully

Let me redesign slightly. Instead of `consume_front`, let me have:
- `peek_best_maker(side)` -> RestingOrder | None (just peek, don't consume)
- `remove_order(order)` - remove a specific order
- The matching engine directly modifies `order.quantity_units` (since RestingOrder is mutable, not frozen)

Wait, but RestingOrder is a dataclass. If I make it frozen, I can't modify quantity. Let me make it non-frozen (default for dataclass).

Actually, looking at this more carefully, I think it's cleaner to have the matching engine work with the book through clear operations:
1. `peek_best_maker(opposite_side)` -> RestingOrder | None
2. `pop_maker(opposite_side)` -> RestingOrder (removes from front, returns it)
3. `reinsert_maker(order)` - put it back (for partial fills) -- no, this is ugly

Better approach:
1. `peek_best_maker(opposite_side)` -> RestingOrder | None
2. `reduce_or_remove(order, qty)` - reduce quantity, remove if zero
3. `remove_order(order)` - remove entirely (for self-trade)

The matching engine modifies the order's quantity in place via `reduce_or_remove`.

Let me code this up. I'll make RestingOrder a regular (mutable) dataclass.

### Matching engine design

```python
def match_order(event: dict, world: dict, kernel: EventKernel) -> list[dict]:
    """Transaction handler for ORDER_ARRIVAL events.
    
    Implements the full admission + matching + remainder + risk pipeline (§5).
    """
    if event["event_type"] != "ORDER_ARRIVAL":
        return []
    
    book: Book = world["book"]
    config = world.get("config")  # ParsedConfig or None
    initial_price_ticks = config.market.initial_price_ticks if config else 10000
    
    # Set default fields on r0
    event["accepted"] = True
    event["reject_reason"] = None
    event.setdefault("origin", "AGENT")
    event.setdefault("trigger_ratio_bp", None)
    event.setdefault("liquidation_generation", None)
    event.setdefault("intent_id", None)
    event.setdefault("decision_event_id", "e0_0")
    event.setdefault("submitted_at", event["timestamp"])
    
    # Step 1: Regime hook (stub, always pass for 0.1.1)
    # Step 2: Tick/min_quantity alignment (stub, always pass for 0.1.1)
    # Step 3: Initial margin check (stub, always pass, but compute reserved_units)
    reserved_units = compute_reserved_units(event, config)
    event["reserved_delta_units"] = reserved_units
    
    # Step 4: Matching
    records: list[dict] = []
    caused_by = f"e{kernel.current_transaction_seq}_0"
    
    if event["action"] == "SUBMIT":
        taker_side = event["side"]
        opposite_side = "SELL" if taker_side == "BUY" else "BUY"
        taker_qty = event["quantity_units"]
        limit_price = event["price_ticks"]  # None for MARKET
        remaining = taker_qty
        vm_running = book.valuation_mark_half_ticks()
        
        while remaining > 0:
            maker = book.peek_best_maker(opposite_side)
            if maker is None:
                break
            # Price crossing check
            if limit_price is not None:
                if taker_side == "BUY" and maker.price_ticks > limit_price:
                    break
                if taker_side == "SELL" and maker.price_ticks < limit_price:
                    break
            else:
                # MARKET order: no price limit, but still need crossing
                # Actually MARKET orders match any price
                pass
            
            # Self-trade check
            if maker.agent_id == event["agent_id"]:
                book.remove_order(maker)
                records.append(_make_order_cancelled(maker, "SELF_TRADE_PREVENTION", caused_by))
                continue
            
            # Fill
            fill_qty = min(remaining, maker.quantity_units)
            vm_before = vm_running
            maker.quantity_units -= fill_qty
            remaining -= fill_qty
            if maker.quantity_units == 0:
                book.remove_order(maker)
            book.last_ticks = maker.price_ticks
            vm_after = book.valuation_mark_half_ticks()
            vm_running = vm_after
            
            records.append(_make_trade_settle(
                maker=maker,
                taker_order_id=event["order_id"],
                taker_agent_id=event["agent_id"],
                fill_qty=fill_qty,
                vm_before=vm_before,
                vm_after=vm_after,
                risk_mark=maker.price_ticks,
                caused_by=caused_by,
                config=config,
            ))
        
        # Step 5: Remainder handling
        if remaining > 0:
            if event["order_type"] == "LIMIT":
                # Rest in book, preserving original transaction_seq
                resting = RestingOrder(
                    order_id=event["order_id"],
                    agent_id=event["agent_id"],
                    side=taker_side,
                    order_type="LIMIT",
                    price_ticks=limit_price,
                    quantity_units=remaining,
                    transaction_seq=kernel.current_transaction_seq,
                )
                book.insert(resting)
                # No record produced
            else:  # MARKET
                records.append(_make_ioc_cancel(
                    order_id=event["order_id"],
                    agent_id=event["agent_id"],
                    side=taker_side,
                    cancelled_qty=remaining,
                    caused_by=caused_by,
                ))
    
    # Step 6: Risk check (stub for 0.1.1, always pass)
    
    # Step 7: Market data publish if book changed
    if book.changed_since_last_publish():  # need to track this
        records.append(_make_market_data_publish(book))
    
    return records
```

Hmm, I need to track whether the book changed. Let me add a `_dirty` flag to the Book that gets set on any insert/remove/consume, and cleared after a publish.

Actually, let me think about when MARKET_DATA_PUBLISH should be generated. The contract says "盘口变化则生成 MARKET_DATA_PUBLISH". A book change includes:
- Any insert (resting order)
- Any removal (fill consuming a level, or self-trade cancel)
- Any fill that changes quantities

Actually, looking at OB-2: "事务 2 的 best_bid 未变，但 k 档深度变了，因此仍须发布行情". So even if best_bid/best_ask don't change, if depth changes, we publish. This means ANY change to the book triggers a publish.

But there's a subtlety: what if an order arrives and immediately fills completely with no remainder, and the book doesn't change? That would be... actually impossible, because filling means consuming a maker order, which changes the book. Unless the maker order had exactly the right quantity and the level disappears but... no, that's still a change.

Actually, wait. What about a market order that fully fills against existing orders? The book changes (maker orders consumed). So publish.

What about a limit order that crosses and fully fills? Same, book changes.

What about a limit order that doesn't cross at all and just rests? Book changes (new order added). Publish.

What about a limit order that's rejected? No book change, no publish (accepted=false, only r0).

So for 0.1.1, every accepted ORDER_ARRIVAL that does anything will change the book and trigger a publish. The only case with no publish is accepted=false (rejection).

Actually wait, let me re-check the kernel's `_validate_transaction_order`:
```python
# (2) accepted=false -> only r0.
if r0["event_type"] == "ORDER_ARRIVAL" and not r0.get("accepted", True):
    raise KernelAbort(...)
```

So if accepted=false, the handler must return [] (no records). The kernel enforces this.

For 0.1.1, since the admission check is a stub that always passes, every ORDER_ARRIVAL is accepted. So every ORDER_ARRIVAL transaction will have at least a MARKET_DATA_PUBLISH (because every order either matches or rests, both of which change the book).

Wait, actually there's an edge case: what if a MARKET order arrives and the opposite side is empty? Then it's fully IOC cancelled. The book doesn't change (nothing was consumed, nothing was added). But there's an ORDER_CANCELLED record. Does this trigger a MARKET_DATA_PUBLISH?

Looking at OB-6: the market order fills 2000 and cancels 3000. The fill changes the book (consumes the only ask level). So publish happens. But what if the book was completely empty and a market order arrives? It would be fully IOC cancelled, no book change. Should there be a publish?

Hmm, the contract says "盘口变化则生成 MARKET_DATA_PUBLISH". If the book didn't change, no publish. But in the empty book case, the book was empty before and after. No change, no publish.

But wait, let me check: does the cancel itself count as a "book change"? No, the order was never in the book. It arrived, couldn't match, and was cancelled. The book is unchanged.

So for T307 (empty book, market order IOC): the market order arrives, no opposite side, fully cancelled. Book unchanged. No MARKET_DATA_PUBLISH. The transaction has r0 + ORDER_CANCELLED only.

Actually, let me re-read T307: "空簿与单边簿：市价单 IOC 撤销、mid 未定义时 valuation_mark 退化为 last、首笔成交前退化为 initial_price"

So in the empty book case, a market order is fully IOC cancelled. There's no TRADE_SETTLE (no fill), so valuation_mark doesn't apply. The ORDER_CANCELLED is the only record.

But does a MARKET_DATA_PUBLISH get generated? I think not, because the book didn't change. But let me check: the kernel's `_validate_transaction_order` only checks that MARKET_DATA_PUBLISH is last if present, and that accepted=false has only r0. It doesn't require MARKET_DATA_PUBLISH.

Let me track book changes with a simple `_dirty` flag.

Actually, I realize there might be an issue. Let me think about what "book changed" means more carefully.

When a limit order rests in the book, that's a change (new order added). When a maker is consumed, that's a change. When a self-trade cancel removes a maker, that's a change.

When a market order is fully IOC cancelled on an empty book, the book doesn't change. No publish.

But what about a market order that partially fills and then cancels the remainder? The fill changes the book. Publish.

OK, I'll use a dirty flag. Let me implement it:

```python
class Book:
    def __init__(self, ...):
        ...
        self._dirty = False
    
    def insert(self, order):
        ...
        self._dirty = True
    
    def remove_order(self, order):
        ...
        self._dirty = True
    
    def reduce_quantity(self, order, qty):
        ...
        self._dirty = True  # always dirty on reduce
    
    def mark_published(self):
        self._dirty = False
    
    @property
    def dirty(self) -> bool:
        return self._dirty
```

Hmm, but `reduce_quantity` always sets dirty even if the order isn't fully consumed. That's correct — the depth at that level changed.

Wait, actually in OB-4, the third fill only partially consumes the 10200 level. The depth changes (2000 -> 1000 at that level). So dirty = True. But the best_ask doesn't change (still 10200). The publish happens because depth changed, not because best_ask changed. So tracking with a dirty flag is correct.

Now, the matching engine checks `if book.dirty:` before publishing. But there's a subtlety: the book might have been dirty from a previous transaction (if we forgot to clear it). Let me clear the dirty flag at the start of each transaction, or after publishing.

Actually, let me think about this differently. The dirty flag should track "has the book changed since the last MARKET_DATA_PUBLISH in this transaction". At the start of each transaction (handler call), the book is clean (the previous transaction would have published if dirty). During the handler, any insert/remove/reduce sets dirty=True. At the end, if dirty, we publish and set dirty=False.

But what if a transaction doesn't change the book at all? Then dirty stays False, no publish. That's correct.

Wait, but there's another subtlety. What if the book was changed by the bootstrap (initial levels)? In the simulator, I'll insert initial levels before running. These set dirty=True. But then the first business transaction starts, and... hmm, the dirty flag is True from the initial levels.

I think the cleanest approach is: at the start of the handler, save `dirty_at_start = book.dirty`. Then during the handler, if the book changes, dirty becomes True (it might already be True). At the end, publish if `book.dirty != dirty_at_start` ... no, that doesn't work either.

Let me just reset dirty to False at the start of each handler call, then check at the end:

```python
def match_order(event, world, kernel):
    book = world["book"]
    book._dirty = False  # reset at start
    ...
    # do stuff that might set _dirty = True
    ...
    if book._dirty:
        records.append(_make_market_data_publish(book))
    return records
```

This is clean. Each transaction starts with a clean slate, and we publish only if this transaction changed the book.

Actually, I should use a method `book.reset_dirty()` instead of accessing `_dirty` directly. Let me make it a proper interface.

OK, I think I have a clear enough design now. Let me also think about the `compute_reserved_units` function:

```python
def compute_reserved_units(event: dict, config) -> int:
    """Compute reserved_units per §5 formula: ceil(price * qty * initial_margin_bp / 10000).
    
    For 0.1.1, the margin check is a stub that always passes, but the value
    must be computed and recorded (T407b).
    
    For MARKET orders (price_ticks=null), use the current best opposite price
    or initial_price as fallback.
    """
    price = event.get("price_ticks")
    if price is None:
        # MARKET order: use best opposite or initial_price
        book = world.get("book")
        if book:
            opposite = book.best_opposite(event["side"])
            price = opposite if opposite is not None else config.market.initial_price_ticks
        else:
            price = config.market.initial_price_ticks
    qty = event["quantity_units"]
    # initial_margin_bp: for 0.1.1, use maint_bp as a placeholder
    # Actually, the formula should use the initial margin requirement,
    # which for 0.1.1 is just the maintenance margin (no leverage).
    # Since 0.1.1 has no leverage, initial_margin_bp = 10000 (100%).
    # But this is a stub, so the value just needs to be computed.
    # Let me use 10000 (100%) for 0.1.1.
    initial_margin_bp = 10000  # 100% margin for no-leverage milestone
    return div_ceil(price * qty * initial_margin_bp, 10_000)
```

Hmm, actually this is getting complicated and the task says "0.1.1 只需算出并记录该值". The exact formula doesn't matter much since the check always passes. Let me use a simple formula:

```python
reserved_units = div_ceil(price_ticks * quantity_units * initial_margin_bp, 10_000)
```

Where `initial_margin_bp` for 0.1.1 is 10000 (100% = no leverage). But actually, looking at the config, there's `maint_bp` in the margin config. For 0.1.1, I'll just use 10000 as the initial margin requirement (no leverage = 100% margin).

Actually, wait. The task says "reserved_units = ceil(price_ticks * quantity_units * initial_margin_bp / 10_000)". For 0.1.1, what's `initial_margin_bp`? The margin config has `maint_bp` and `target_bp`, but those are maintenance and target margins, not initial margin. The initial margin for no-leverage would be 10000 bp (100%).

For 0.1.1, since the check is a stub, I'll use `initial_margin_bp = 10000` (100%). This gives `reserved_units = price_ticks * quantity_units`, which is the notional. That makes sense for 100% margin.

But actually, I realize the task says "0.1.1 只需算出并记录该值" and "0.1.2 只接上拒绝逻辑，不改公式". So the formula should be correct for 0.1.2 to use. In 0.1.2, the initial margin will come from the leverage tiers. For 0.1.1, I'll hardcode 10000 bp (100%).

Let me simplify: for 0.1.1, `reserved_delta_units = 0` on accepted orders is actually fine since the margin check is a stub. Wait, no, the task explicitly says "reserved_units 须按公式算出并写入分录". So I must compute it.

Let me just compute it as `div_ceil(price * qty * 10000, 10000) = price * qty` for LIMIT orders, and for MARKET orders use a fallback price. This is simple and correct for 100% margin.

Actually, hmm, `reserved_delta_units` on ORDER_ARRIVAL is the reserved units for THIS order. It's `ceil(price * qty * initial_margin_bp / 10000)`. For 100% margin (initial_margin_bp = 10000), this equals `price * qty`. For MARKET orders, price is null, so we need a fallback. I'll use the best opposite price or initial_price.

But wait, `price * qty` could be a huge number. For OB-1, order o1 is BUY 10000 × 5000 = 50,000,000. That's the reserved units. It's an integer, fine.

OK, let me now start implementing. I'll write the code files first, then the tests.

Let me also think about the simulator:

```python
def run_simulation(
    initial_book_levels: list[dict],  # [{"side": "SELL", "order_id": "s1", "agent_id": "M", "price_ticks": 10000, "quantity_units": 2000}, ...]
    events: list[dict],  # ORDER_ARRIVAL events to enqueue
    parsed_config: ParsedConfig | None = None,
    initial_price_ticks: int = 10000,
) -> tuple[list[dict], Book]:
    """Run a simulation and return (committed_records, final_book)."""
    kernel = EventKernel(run_id="sim")
    
    # Bootstrap with empty book and accounts
    account_payload = build_account_payload([])
    book_payload = build_book_payload(last_ticks=None)
    kernel.bootstrap(account_payload, book_payload)
    
    # Create the book and insert initial levels
    book = Book(initial_price_ticks=initial_price_ticks)
    for level in initial_book_levels:
        order = RestingOrder(
            order_id=level["order_id"],
            agent_id=level["agent_id"],
            side=level["side"],
            order_type="LIMIT",
            price_ticks=level["price_ticks"],
            quantity_units=level["quantity_units"],
            transaction_seq=0,  # pre-bootstrap, time-priority doesn't matter for initial levels
        )
        book.insert(order)
    
    # Build world
    world = {"book": book, "config": parsed_config}
    
    # Enqueue events
    for event in events:
        kernel.enqueue(event)
    
    # Run
    kernel.run(match_order, world, max_transactions=10000)
    
    return kernel.committed_records, book
```

Wait, but for the initial book levels, what `transaction_seq` should they have? The contract says "保留到达事务的 transaction_seq as the time-priority key". But these are pre-existing levels, not from a transaction. I'll use 0 (before any transaction).

Actually, looking at OB-9a, the initial levels are s1 and s2. These are "M 挂卖 10000 × 2000（订单 s1）与 10100 × 2000（订单 s2）". In the actual OB-9a test, these are enqueued as ORDER_ARRIVAL events:

Wait, let me re-read OB-9a:
"前置：M 挂卖 10000 × 2000（订单 s1）与 10100 × 2000（订单 s2）。同一时间戳 t 内，A 与 B 两张买单先后到达"

So s1 and s2 are pre-existing resting orders. They could be either:
1. Enqueued as ORDER_ARRIVAL events at an earlier timestamp, OR
2. Pre-inserted into the book as initial levels

Looking at the existing test `test_second_order_fills_at_10100_not_10000`, it enqueues all 4 orders (s1, s2, A, B) at the same timestamp t=100. The handler stub rests the sells and matches the buys.

But for my implementation, the simulator should support both approaches. For OB-9a, I could either:
- Enqueue s1 and s2 as ORDER_ARRIVAL events (they'll rest in the book via the matching engine), then enqueue A and B
- Or pre-insert s1 and s2 as initial levels

Looking at the OB-9a expected output more carefully:
```
(t, 1, 0) | ORDER_ARRIVAL | A BUY ...
(t, 1, 1) | TRADE_SETTLE  | ...
(t, 1, 2) | MARKET_DATA_PUBLISH | ...
(t, 2, 0) | ORDER_ARRIVAL | B BUY ...
(t, 2, 1) | TRADE_SETTLE  | ...
(t, 2, 2) | MARKET_DATA_PUBLISH | ...
```

Transaction_seq starts at 1, not 3. This means the bootstrap transactions are not counted... wait, that can't be right. The kernel starts transaction_seq at 0 and increments to 1 for the first SNAPSHOT (ACCOUNT), 2 for the second SNAPSHOT (BOOK), and 3 for the first business event.

But the OB-9a table shows transaction_seq starting at 1 for A's order. This suggests the table is using a different numbering, or the s1/s2 orders are transactions 1 and 2 (resting sells), and A is transaction 3.

Wait, let me re-read: "前置：M 挂卖..." — this is the setup. Then "同一时间戳 t 内，A 与 B 两张买单先后到达". The table shows the orders A and B with transaction_seq 1 and 2.

Hmm, but if s1 and s2 are also ORDER_ARRIVAL events, they would be transactions 3 and 4 (after bootstrap at 1 and 2), and A would be 5, B would be 6.

I think the OB-9a table is showing a simplified view where:
- s1 and s2 are pre-existing (either from a prior timestamp or pre-inserted)
- A and B are the two transactions being tested

The table's transaction_seq values (1, 2) are relative to A and B, not absolute. But the log_key includes the absolute transaction_seq.

Actually wait, looking more carefully at the table:
```
| (t, 1, 0) | ORDER_ARRIVAL | A BUY ...
| (t, 1, 1) | TRADE_SETTLE  | ...
| (t, 1, 2) | MARKET_DATA_PUBLISH | ...
| (t, 2, 0) | ORDER_ARRIVAL | B BUY ...
```

The log_key is (timestamp, transaction_seq, record_index). If A is transaction_seq=1, that means there are no bootstrap transactions? Or the bootstrap is at t=0 and A is at t=100 (different timestamp)?

Hmm, but the contract says "所有向量均在同一时间戳内". So all events are at the same timestamp t. But bootstrap is at t=0.

I think the OB vectors are describing the business transactions only, with the bootstrap transactions (at t=0) being implicit. The transaction_seq in the table might be offset.

Wait, let me look at the existing test again:
```python
def test_second_order_fills_at_10100_not_10000(self):
    kernel = EventKernel(run_id="ob9a")
    _bootstrap_kernel(kernel)
    book = _make_book()
    t = 100
    kernel.enqueue(_make_sell_order("s1", "M", 10000, 2000, t))
    kernel.enqueue(_make_sell_order("s2", "M", 10100, 2000, t))
    kernel.enqueue(_make_buy_order("A", "A", 10100, 2000, t))
    kernel.enqueue(_make_buy_order("B", "B", 10100, 2000, t))
    kernel.run(make_handler(book), {}, max_transactions=10)
```

Here, all 4 orders are enqueued at t=100. Bootstrap is at t=0. So:
- transaction_seq=1: SNAPSHOT ACCOUNT (t=0)
- transaction_seq=2: SNAPSHOT BOOK (t=0)
- transaction_seq=3: s1 sell (t=100) — rests
- transaction_seq=4: s2 sell (t=100) — rests
- transaction_seq=5: A buy (t=100) — matches s1
- transaction_seq=6: B buy (t=100) — matches s2

The test doesn't assert on specific transaction_seq values, just on the trade prices and maker_order_ids. So the transaction_seq values in the OB-9a table (1, 2) are relative to the business transactions, not absolute.

For my OB vector tests, I should assert on the absolute values from the kernel (which include bootstrap). The OB vector table's transaction_seq values are illustrative but I should use the actual kernel values.

OR, I could set up the simulator to pre-insert s1 and s2 as initial book levels (no ORDER_ARRIVAL events for them), so the first business transaction is A at transaction_seq=3. This matches the table better:
- transaction_seq=1: SNAPSHOT ACCOUNT
- transaction_seq=2: SNAPSHOT BOOK
- transaction_seq=3: A buy (matches s1)
- transaction_seq=4: B buy (matches s2)

But the table shows A at transaction_seq=1 and B at transaction_seq=2. So there's a mismatch of 2 (the bootstrap transactions).

I think the OB vector table is using a simplified numbering that excludes bootstrap. For my tests, I'll assert on the actual kernel values (which include bootstrap at 1 and 2, business starting at 3). I'll adjust the expected transaction_seq values accordingly.

Actually, let me look at the assertion requirements again:
"6. 所有 log_key 严格递增。"

This just requires strict monotonicity, not specific values. So I'll assert that log_keys are strictly increasing.

For the specific transaction_seq and record_index values in the OB vectors, I'll need to account for the bootstrap offset. Let me compute:
- Bootstrap: transaction_seq 1 (ACCOUNT), 2 (BOOK)
- First business event: transaction_seq 3
- Second business event: transaction_seq 4
- etc.

For OB-1:
- tx 1 (absolute 3): A buy 10000 × 5000 -> rests. Records: r0, MDP.
- tx 2 (absolute 4): B buy 10100 × 5000 -> rests. Records: r0, MDP.
- tx 3 (absolute 5): C sell 10000 × 3000 -> matches o2. Records: r0, TRADE_SETTLE, MDP.

The OB-1 table shows:
```
| 1 | 0 | ORDER_ARRIVAL | A BUY ...
| 1 | 1 | MARKET_DATA_PUBLISH | ...
| 2 | 0 | ORDER_ARRIVAL | B BUY ...
| 2 | 1 | MARKET_DATA_PUBLISH | ...
| 3 | 0 | ORDER_ARRIVAL | C SELL ...
| 3 | 1 | TRADE_SETTLE | ...
| 3 | 2 | MARKET_DATA_PUBLISH | ...
```

With absolute transaction_seq:
```
| 3 | 0 | ORDER_ARRIVAL | A BUY ...
| 3 | 1 | MARKET_DATA_PUBLISH | ...
| 4 | 0 | ORDER_ARRIVAL | B BUY ...
| 4 | 1 | MARKET_DATA_PUBLISH | ...
| 5 | 0 | ORDER_ARRIVAL | C SELL ...
| 5 | 1 | TRADE_SETTLE | ...
| 5 | 2 | MARKET_DATA_PUBLISH | ...
```

For my tests, I'll filter out bootstrap records and assert on the business records. Or I'll compute the expected absolute transaction_seq.

I think the cleanest approach is to filter out SNAPSHOT records and work with business records only. Then the transaction_seq values will be offset by 2 from the table.

Actually, let me think about this differently. For the OB vector tests, I want to assert:
1. Event sequence (kind + record_index) — relative to each transaction
2. TRADE_SETTLE fields
3. ORDER_CANCELLED fields
4. Post-transaction book state
5. log_key strictly increasing

For (1), I can group records by transaction_seq and check the sequence within each transaction. The absolute transaction_seq doesn't matter as long as the relative order is correct.

For (5), I just check strict monotonicity of (timestamp, transaction_seq, record_index).

Let me write the tests to be robust against the bootstrap offset. I'll filter out SNAPSHOT records and work with business records.

OK, I think I have a complete design now. Let me start coding.

Let me also think about one more thing: the `notional_cash_units` and fee fields. For 0.1.1, I'll compute them simply:
- `notional_cash_units = price_ticks * quantity_units` (same as the existing stub)
- `maker_fee_cash_units = 0`
- `taker_fee_cash_units = 0`
- `postings = []` (no account postings in 0.1.1)

These fields are present but not asserted in the OB vectors. Phase 4 will fill in proper account postings.

Now let me also check: does the existing test `test_fill_count_backfilled_on_all_trades` need any changes? It uses the stub handler, not the real matching engine. The task says "Do NOT modify kernel/runner.py core semantics". I should keep the existing tests working. The existing tests use their own stub handler, which is fine. I'm adding NEW tests that use the real matching engine.

OK wait, I also need to handle the `world` dict. The existing tests pass `{}` as the world (the stub handler uses a closure-captured `book` dict). My matching engine expects `world["book"]` to be a `Book` instance. So my tests will pass a world dict with the book.

Let me also check: for the existing test `test_second_order_fills_at_10100_not_10000`, the stub handler rests sells and matches buys. My matching engine will do the same but with proper records. The existing test should still pass because it uses the stub handler, not my matching engine.

OK, I'm ready to code. Let me start.

One more thing: I need to add `current_transaction_seq` property to the kernel. Let me check if there's already something similar... No, there isn't. I'll add it.

Also, I notice the kernel's `_build_record` sets `enqueue_seq` from the parameter. For r0 (the queue event), it passes `event.get("_enqueue_seq")`. For transaction records, it passes `None`. This is correct — transaction records have `enqueue_seq=null` per the schema.

Now, the `caused_by_event_id` field on TRADE_SETTLE and ORDER_CANCELLED needs to point to the r0's event_id. The r0's event_id is `f"e{txn_seq}_0"`. The handler can construct this as `f"e{kernel.current_transaction_seq}_0"`.

But wait, I need to make sure `kernel.current_transaction_seq` is available during the handler call. Looking at `_run_transaction`:
```python
self._transaction_seq += 1
txn_seq = self._transaction_seq
self._current_event = event
# ...
records = handler(event, world, self)
```

Yes, `_transaction_seq` is set before the handler is called. So I can expose it as a property.

Let me now write all the code. I'll start with the book, then matching, then simulator, then tests.

Actually, let me also look at how the `book` for the OB vectors should be set up. For OB-1, the initial book is empty. Orders A, B, C are enqueued as events. For OB-4, the initial book has M's sells and N's buy. Then T's buy is enqueued.

For OB-4 specifically:
- Pre-existing: M sells 100×2 (a1), 101×2 (a2), 102×2 (a3); N buys 99×10.
- T buys 102×5.

These pre-existing orders need to be in the book before T's order arrives. I'll pass them as `initial_book_levels` to the simulator.

But wait, for OB-1, the orders A, B, C are all enqueued as events (no pre-existing levels). A and B are buy orders that rest, then C is a sell that matches B.

For OB-9a, the pre-existing levels are s1 and s2 (M's sells). Then A and B are enqueued as buy events.

So the simulator needs to support both:
1. Pre-existing levels (inserted directly into the book)
2. Enqueued events (ORDER_ARRIVAL that go through the matching engine)

For OB-1: no pre-existing levels, events = [A, B, C]
For OB-4: pre-existing levels = [a1, a2, a3, N's buy], events = [T's buy]
For OB-9a: pre-existing levels = [s1, s2], events = [A, B]

This is what the task description says: "For OB-1, the initial_book_levels are empty... For OB-9a, the initial_book_levels contain the two resting sell orders (s1, s2), then A and B buy orders are processed."

Great, my simulator design supports this.

Now, for the pre-existing levels, what `transaction_seq` should they have? Since they're pre-existing (before any business transaction), I'll assign them transaction_seq=0 (before bootstrap). When a real taker order comes in, its transaction_seq will be >= 3 (after bootstrap). So the pre-existing orders will always have time priority (lower transaction_seq).

But wait, for OB-4, the pre-existing levels include N's buy at 99. If another buy comes in at 99, the pre-existing N order should have priority. With transaction_seq=0, N's order has the lowest possible seq, so it has priority. Good.

For OB-9a, s1 and s2 are pre-existing. When A and B come in, s1 (transaction_seq=0) and s2 (transaction_seq=0) are the only asks. A matches s1, B matches s2. The pre-existing orders' transaction_seq doesn't matter for matching since they're at different price levels.

But what if two pre-existing orders are at the same price level? Then their relative priority matters. I should assign them incrementing transaction_seq values (e.g., 0, 1, 2, ...) to maintain insertion order. Actually, since they're inserted in order and I use a deque (FIFO), the insertion order is preserved regardless of transaction_seq. The transaction_seq only matters for the time-priority key, but within a deque, FIFO ordering already gives priority to earlier insertions.

Wait, the contract says "同价位按到达事务的 transaction_seq 升序". If two pre-existing orders are at the same price, their transaction_seq determines priority. But since I insert them in order and use a deque, the first inserted is at the front. As long as I assign transaction_seq in insertion order, the deque order matches the transaction_seq order. So it's consistent.

I'll assign pre-existing orders transaction_seq values starting from 0, incrementing for each. Actually, to avoid any confusion with bootstrap (which uses transaction_seq 1 and 2), I'll use negative values or 0. Let me use 0 for all pre-existing orders (since they're at different price levels in the OB vectors, there's no same-price conflict).

Hmm, actually for OB-4, the pre-existing asks are at 100, 101, 102 — all different prices. N's buy is at 99 — different from any other bid. So no same-price conflict. I'll use transaction_seq=0 for all pre-existing orders.

But to be safe, let me assign them incrementing values: 0, 1, 2, ... in insertion order. This way, even if two are at the same price, the first inserted has priority.

OK, let me now actually write the code. I've been thinking long enough.

Let me also handle one more detail: for the OB vector tests, I need to check the post-transaction book state. I'll add a method to Book that returns the aggregate levels:

```python
def bid_levels(self) -> list[tuple[int, int]]:
    """Return [(price, total_qty), ...] for bids, sorted descending."""
    return [(p, sum(o.quantity_units for o in self._bids[p])) for p in reversed(self._bid_prices)]

def ask_levels(self) -> list[tuple[int, int]]:
    """Return [(price, total_qty), ...] for asks, sorted ascending."""
    return [(p, sum(o.quantity_units for o in self._asks[p])) for p in self._ask_prices]
```

OK, now let me code everything. I'll write the implementation files first, then the test files.

Wait, I should also think about the `trade_id`. It needs to be unique. I'll use `f"t{txn_seq}_{fill_index}"` where fill_index is the 0-based index of this fill within the transaction.

But the kernel backfills `fill_index` AFTER the handler returns. So the handler doesn't know the fill_index when constructing the trade_id. Hmm.

I could use a different scheme: `f"t{txn_seq}_{record_index}"` where record_index is... also not known (kernel assigns it after).

Or just use a counter within the handler: `f"t{txn_seq}_{counter}"` where counter is incremented for each TRADE_SETTLE. Since the kernel backfills fill_index based on the order of TRADE_SETTLE records, my counter matches fill_index.

Actually, `trade_id` is HASH_EXCLUDE, so it just needs to be unique. I'll use `f"t{kernel.current_transaction_seq}_{idx}"` where idx is my internal counter.

Let me now start writing code. I'll create all files and then run tests.

Let me also think about the market_data_publish fields. From the schema:
- best_bid (int|null)
- best_ask (int|null)
- bid_depth_k (int) — number of bid price levels
- ask_depth_k (int) — number of ask price levels
- last (int|null) — last trade price, null before first trade

So `bid_depth_k` is the number of price levels (not the total quantity). And the OB vectors mention "深度变化" (depth change) as a trigger for publishing.

Let me verify: OB-2 transaction 2 inserts B's buy at the same price as A's buy. best_bid doesn't change (still 10000), but the depth at that level changes from 5000 to 10000. However, `bid_depth_k` is the number of price levels, which stays at 1. So the depth_k doesn't change either!

Hmm, but the OB-2 assertion says "事务 2 的 best_bid 未变，但 k 档深度变了". "k 档深度" refers to the depth at the k-th level, not the number of levels. So the quantity at the best bid level changed from 5000 to 10000.

So the "depth changed" check should compare the full book state (all levels and their quantities), not just the number of levels. The dirty flag approach handles this correctly — any change to the book sets dirty=True.

But the MARKET_DATA_PUBLISH fields only include best_bid, best_ask, bid_depth_k (count of levels), ask_depth_k (count of levels), and last. The quantity at each level is NOT in the publish record. So how does the replayer know the depth changed?

Looking at the OB-2 table: "MARKET_DATA_PUBLISH | best_bid=10000 best_ask=null（深度变化）". The publish happens because the book changed, even though the published fields (best_bid, best_ask, depth_k) might be the same. The replayer can compare the publish with the previous one and see that... well, actually the fields are the same (best_bid=10000, best_ask=null, bid_depth_k=1, ask_depth_k=0, last=null). So the replayer can't distinguish this from a no-op.

But the contract says to publish whenever the book changes. The publish is still written to the log, even if its fields are identical to the previous publish. The replayer can detect changes by comparing consecutive publishes.

OK, so my approach is correct: publish whenever the book is dirty (changed during this transaction), regardless of whether the published fields changed.

But wait, there's an edge case in OB-2: transaction 2 inserts B's buy at 10000. The book before: bids=[(10000, 5000)], after: bids=[(10000, 10000)]. The dirty flag is True (insert happened). So we publish. The publish has best_bid=10000, best_ask=null, bid_depth_k=1, ask_depth_k=0, last=null. This is the same as the previous publish, but it's still written. Good.

Now let me think about another edge case: what if a limit order arrives, doesn't match anything, and rests. The book changes (new order). Dirty=True. Publish. Good.

What if a market order arrives on an empty book? No match, no rest (market orders don't rest), IOC cancel. Book doesn't change. Dirty=False. No publish. The transaction has r0 + ORDER_CANCELLED only.

But wait, is there a MARKET_DATA_PUBLISH in this case? Looking at T307: "空簿与单边簿：市价单 IOC 撤销". The test should verify that a market order on an empty book is fully IOC cancelled. There's no mention of MARKET_DATA_PUBLISH. And since the book didn't change, no publish. Good.

But hmm, the kernel's `_validate_transaction_order` checks that MARKET_DATA_PUBLISH is last if present. If there's no publish, that's fine. And the transaction has r0 + ORDER_CANCELLED, which is valid (ORDER_CANCELLED is not MARKET_DATA_PUBLISH, so the "last" check doesn't apply).

OK, I'm confident in my design now. Let me code it up.

Actually, one more thing about the `reserved_delta_units` on ORDER_CANCELLED. For self-trade prevention, the cancelled maker order releases its reserved units. The `reserved_delta_units` should be negative (release). For IOC remainder, the taker order's remaining quantity is cancelled, releasing its reserved units.

For 0.1.1, since there's no account engine, I'll set `reserved_delta_units = 0` on ORDER_CANCELLED records. The actual computation will be done in Phase 4.

Hmm, but the task says "reserved_units 须按公式算出并写入分录". This is about the ORDER_ARRIVAL's `reserved_delta_units`, not the ORDER_CANCELLED's. For ORDER_CANCELLED, I'll set it to 0 for now.

Actually, let me re-read: "且 reserved_units 须按公式算出并写入分录（T407b）--0.1.2 只接上拒绝逻辑，不改公式。" This is in the context of T306, which is about the admission check. So it's the ORDER_ARRIVAL's reserved_delta_units that needs to be computed. For ORDER_CANCELLED, it's a different field (also called reserved_delta_units) that represents the release of reserved units. For 0.1.1, I'll set ORDER_CANCELLED's reserved_delta_units to 0 (no account engine to track reserved units).

OK, now let me really start coding. I'll create all the files.

Let me plan the exact file contents:

### `src/market_game_sim/book/__init__.py`
```python
"""Phase 3: Order book and matching engine (T301-T308)."""
```

### `src/market_game_sim/book/orderbook.py`
- `RestingOrder` dataclass
- `Book` class with insert, remove, peek, valuation_mark, etc.

### `src/market_game_sim/book/matching.py`
- `compute_reserved_units(event, config) -> int`
- `match_order(event, world, kernel) -> list[dict]` (the TransactionHandler)
- Helper functions for building records

### `src/market_game_sim/book/simulator.py`
- `run_simulation(initial_book_levels, events, parsed_config, ...) -> (records, book)`
- `BookLevel` helper type

### Tests
- `tests/unit/book/__init__.py`
- `tests/unit/book/test_orderbook.py` - T301, T307
- `tests/unit/book/test_matching.py` - T302-T306
- `tests/unit/book/test_simulator.py` - T306b
- `tests/unit/book/test_orderbook_vectors.py` - T308
- `tests/unit/book/test_self_trade.py` - T305

Let me write them all now.

One more consideration: I need to add `current_transaction_seq` property to the kernel. Let me add it after the existing properties.

Let me also double-check the OB vector assertions for each vector to make sure my implementation will produce the correct output.

#### OB-1 verification

Events: A BUY 10000×5000, B BUY 10100×5000, C SELL 10000×3000. All at t=100.
Initial book: empty.

Transaction 3 (A BUY 10000×5000):
- No asks to match. Remainder 5000, LIMIT -> rest at 10000.
- Book: bids=[(10000, 5000)], asks=[], last=None.
- Dirty=True. Publish: best_bid=10000, best_ask=null, bid_depth_k=1, ask_depth_k=0, last=null.
- Records: [MDP]

Transaction 4 (B BUY 10100×5000):
- No asks to match. Remainder 5000, LIMIT -> rest at 10100.
- Book: bids=[(10100, 5000), (10000, 5000)], asks=[], last=None.
- Dirty=True. Publish: best_bid=10100, best_ask=null, bid_depth_k=2, ask_depth_k=0, last=null.
- Records: [MDP]

Transaction 5 (C SELL 10000×3000):
- Match against bids. Best bid = 10100 (B's order o2).
- Price check: maker 10100 >= taker limit 10000. For a SELL, the maker is a BUY. The taker sells at limit 10000, meaning they want at least 10000. The maker buys at 10100, which is >= 10000. So it crosses.
  - Wait, let me think about the crossing logic for SELL orders.
  - Taker SELL limit 10000: will sell at any price >= 10000.
  - Maker BUY at 10100: willing to buy at 10100.
  - Since 10100 >= 10000, they cross. Fill at maker price 10100.
- Fill: qty = min(3000, 5000) = 3000. maker o2 qty becomes 2000.
  - vm_before: bids present, asks empty, last=None -> initial_price × 2 = 20000.
  - After: bids=[(10100, 2000), (10000, 5000)], asks=[], last=10100.
  - vm_after: asks empty, last=10100 -> 10100 × 2 = 20200.
  - risk_mark = 10100.
- Remainder: 0. No rest.
- Dirty=True. Publish: best_bid=10100, best_ask=null, bid_depth_k=2, ask_depth_k=0, last=10100.
- Records: [TRADE_SETTLE, MDP]

Expected:
```
tx 3: r0=ORDER_ARRIVAL, r1=MARKET_DATA_PUBLISH
tx 4: r0=ORDER_ARRIVAL, r1=MARKET_DATA_PUBLISH
tx 5: r0=ORDER_ARRIVAL, r1=TRADE_SETTLE, r2=MARKET_DATA_PUBLISH
```

TRADE_SETTLE: price=10100, qty=3000, maker=o2, fill_index=0, fill_count=1, vm_before=20000, vm_after=20200, risk_mark=10100. ✓

Post-tx book: BID [(10100, 2000), (10000, 5000)], ASK []. ✓

Wait, but the OB-1 table says C SELL at price_ticks=10000. My crossing check for a SELL: the taker's limit is 10000 (minimum acceptable price). The best bid is 10100 (>= 10000), so it crosses. Fill at maker price 10100. ✓

But what if the best bid were 9900 (< 10000)? Then it wouldn't cross (taker wants at least 10000, maker only bids 9900). So for SELL: cross if `maker.price_ticks >= limit_price`. For BUY: cross if `maker.price_ticks <= limit_price`. Let me verify:

BUY limit 10100, maker ask at 10000: 10000 <= 10100, crosses. Fill at 10000. ✓ (OB-3)
SELL limit 10000, maker bid at 10100: 10100 >= 10000, crosses. Fill at 10100. ✓ (OB-1)

Great, my crossing logic is:
- BUY: cross if `maker.price_ticks <= limit_price` (or if MARKET, always cross)
- SELL: cross if `maker.price_ticks >= limit_price` (or if MARKET, always cross)

#### OB-3 verification

Events: A SELL 10000×5000, B BUY 10100×3000. All at t=100.
Initial book: empty.

Transaction 3 (A SELL 10000×5000):
- No bids to match. Remainder 5000, LIMIT -> rest at 10000.
- Book: bids=[], asks=[(10000, 5000)], last=None.
- Publish: best_bid=null, best_ask=10000, bid_depth_k=0, ask_depth_k=1, last=null.
- Records: [MDP]

Transaction 4 (B BUY 10100×3000):
- Match against asks. Best ask = 10000 (A's order).
- Price check: maker 10000 <= taker limit 10100. Crosses. Fill at 10000.
- Fill: qty = min(3000, 5000) = 3000. maker qty becomes 2000.
  - vm_before: bids empty, asks present, last=None -> initial_price × 2 = 20000.
  
  Wait, both sides are NOT present (bids is empty). So vm_before = last × 2 if last exists, else initial_price × 2. last=None, so vm_before = 20000. ✓
  
  - After: asks=[(10000, 2000)], bids=[], last=10000.
  - vm_after: bids empty, last=10000 -> 10000 × 2 = 20000. ✓
  - risk_mark = 10000.
- Remainder: 0. No rest.
- Publish: best_bid=null, best_ask=10000, bid_depth_k=0, ask_depth_k=1, last=10000.
- Records: [TRADE_SETTLE, MDP]

Expected:
```
tx 3: r0=ORDER_ARRIVAL, r1=MARKET_DATA_PUBLISH
tx 4: r0=ORDER_ARRIVAL, r1=TRADE_SETTLE, r2=MARKET_DATA_PUBLISH
```

TRADE_SETTLE: price=10000, qty=3000, fill_index=0, fill_count=1, vm_before=20000, vm_after=20000, risk_mark=10000. ✓

Post-tx book: BID [], ASK [(10000, 2000)]. ✓

#### OB-4 verification

Initial book: M sells 100×2 (a1), 101×2 (a2), 102×2 (a3); N buys 99×10 (n1).
Events: T BUY 10200×5000.

Transaction 3 (T BUY 10200×5000):
- Match against asks.
- Best ask = 10000 (a1). 10000 <= 10200. Cross. Not self-trade (T ≠ M).
  - Fill 1: qty = min(5000, 2000) = 2000. a1 consumed.
  - vm_before: bids=[(9900, 10000)], asks=[(10000, 2000), (10100, 2000), (10200, 2000)]. Both present -> 9900 + 10000 = 19900. ✓
  - After: asks=[(10100, 2000), (10200, 2000)], last=10000.
  - vm_after: both present -> 9900 + 10100 = 20000. ✓
  - risk_mark = 10000. ✓
  - remaining = 3000.

- Best ask = 10100 (a2). 10100 <= 10200. Cross. Not self-trade.
  - Fill 2: qty = min(3000, 2000) = 2000. a2 consumed.
  - vm_before: 9900 + 10100 = 20000. ✓
  - After: asks=[(10200, 2000)], last=10100.
  - vm_after: 9900 + 10200 = 20100. ✓
  - risk_mark = 10100. ✓
  - remaining = 1000.

- Best ask = 10200 (a3). 10200 <= 10200. Cross. Not self-trade.
  - Fill 3: qty = min(1000, 2000) = 1000. a3 has 1000 remaining.
  - vm_before: 9900 + 10200 = 20100. ✓
  - After: asks=[(10200, 1000)], last=10200.
  - vm_after: 9900 + 10200 = 20100. ✓ (best_ask unchanged, a3 still has 1000)
  - risk_mark = 10200. ✓
  - remaining = 0.

- Remainder: 0. No rest.
- Publish: best_bid=9900, best_ask=10200, bid_depth_k=1, ask_depth_k=1, last=10200.
- Records: [TRADE_SETTLE, TRADE_SETTLE, TRADE_SETTLE, MDP]

Expected:
```
r0: ORDER_ARRIVAL
r1: TRADE_SETTLE (price=10000, qty=2000, maker=a1, fill_index=0, fill_count=3, vm_before=19900, vm_after=20000, risk_mark=10000)
r2: TRADE_SETTLE (price=10100, qty=2000, maker=a2, fill_index=1, fill_count=3, vm_before=20000, vm_after=20100, risk_mark=10100)
r3: TRADE_SETTLE (price=10200, qty=1000, maker=a3, fill_index=2, fill_count=3, vm_before=20100, vm_after=20100, risk_mark=10200)
r4: MARKET_DATA_PUBLISH (best_bid=9900, best_ask=10200)
```
✓ All matches!

Post-tx book: BID [(9900, 10000)], ASK [(10200, 1000)]. ✓

#### OB-5 verification

Initial book: M sells 100×2 (s1).
Events: T BUY 10000×5000.

Transaction 3 (T BUY 10000×5000):
- Match against asks. Best ask = 10000 (s1). 10000 <= 10000. Cross.
  - Fill 1: qty = min(5000, 2000) = 2000. s1 consumed.
  - vm_before: bids empty, asks present, last=None -> initial_price × 2 = 20000. ✓
  - After: asks=[], last=10000.
  - vm_after: bids empty, asks empty, last=10000 -> 10000 × 2 = 20000. ✓
  - risk_mark = 10000. ✓
  - remaining = 3000.

- Remainder: 3000, LIMIT -> rest at 10000 with transaction_seq=3.
- After rest: bids=[(10000, 3000)], asks=[].
- Publish: best_bid=10000, best_ask=null, bid_depth_k=1, ask_depth_k=0, last=10000.
- Records: [TRADE_SETTLE, MDP]

Expected:
```
r0: ORDER_ARRIVAL
r1: TRADE_SETTLE (price=10000, qty=2000, fill_index=0, fill_count=1, vm_before=20000, vm_after=20000, risk_mark=10000)
r2: MARKET_DATA_PUBLISH (best_bid=10000, best_ask=null)
```
✓ Matches!

Post-tx book: BID [(10000, 3000)], ASK []. ✓

#### OB-6 verification

Same as OB-5 but T buys MARKET (price_ticks=null).
Events: T BUY MARKET ×5000.

Transaction 3 (T BUY MARKET ×5000):
- Match against asks. Best ask = 10000 (s1). MARKET, no limit. Cross.
  - Fill 1: qty = 2000. s1 consumed.
  - vm_before: 20000 (same as OB-5). ✓
  - vm_after: 20000 (same as OB-5). ✓
  - risk_mark = 10000. ✓
  - remaining = 3000.

- Remainder: 3000, MARKET -> IOC cancel.
  - ORDER_CANCELLED: order_id=T, cancelled_qty=3000, price_ticks=null, side=BUY, order_type=MARKET, reason=IOC_REMAINDER.
- No rest.
- Publish: best_bid=null, best_ask=null, bid_depth_k=0, ask_depth_k=0, last=10000.
- Records: [TRADE_SETTLE, ORDER_CANCELLED, MDP]

Expected:
```
r0: ORDER_ARRIVAL (MARKET)
r1: TRADE_SETTLE
r2: ORDER_CANCELLED (price_ticks=null, reason=IOC_REMAINDER)
r3: MARKET_DATA_PUBLISH (best_bid=null, best_ask=null)
```
✓ Matches!

Post-tx book: both sides empty. ✓

#### OB-7 verification

Initial book: A sells 100×2 (s1), B sells 101×2 (s2).
Events: A BUY 10100×3000.

Transaction 3 (A BUY 10100×3000):
- Match against asks. Best ask = 10000 (s1). 10000 <= 10100. Cross.
  - Self-trade check: s1.agent_id = A, taker agent = A. SELF-TRADE!
  - Cancel s1: ORDER_CANCELLED(order_id=s1, agent_id=A, cancelled_qty=2000, price_ticks=10000, side=SELL, order_type=LIMIT, reason=SELF_TRADE_PREVENTION).
  - Taker qty unchanged (3000).
  - Continue.

- Best ask = 10100 (s2). 10100 <= 10100. Cross.
  - Self-trade check: s2.agent_id = B, taker agent = A. Not self-trade.
  - Fill: qty = min(3000, 2000) = 2000. s2 consumed.
  - vm_before: bids empty, asks present (s2 was at 10100, now consumed; s1 was cancelled). Wait, what's the book state at this point?
    - s1 was cancelled (removed from book). s2 is being consumed. So asks = [] after s2 consumed.
    - Before this fill: asks = [(10100, 2000)] (only s2, since s1 was removed). bids = []. last = None.
    - vm_before: bids empty, asks present, last=None -> initial_price × 2 = 20000. ✓
    - After: asks=[], last=10100.
    - vm_after: both empty, last=10100 -> 10100 × 2 = 20200. ✓
    - risk_mark = 10100. ✓
    - remaining = 1000.

- Remainder: 1000, LIMIT -> rest at 10100.
- After rest: bids=[(10100, 1000)], asks=[].
- Publish: best_bid=10100, best_ask=null, bid_depth_k=1, ask_depth_k=0, last=10100.
- Records: [ORDER_CANCELLED, TRADE_SETTLE, MDP]

Expected:
```
r0: ORDER_ARRIVAL
r1: ORDER_CANCELLED (s1, SELF_TRADE_PREVENTION)
r2: TRADE_SETTLE (price=10100, qty=2000, maker=s2, fill_index=0, fill_count=1, vm_before=20000, vm_after=20200, risk_mark=10100)
r3: MARKET_DATA_PUBLISH (best_bid=10100, best_ask=null)
```
✓ Matches!

Post-tx book: BID [(10100, 1000)], ASK []. ✓

#### OB-9a verification

Initial book: M sells 10000×2000 (s1), M sells 10100×2000 (s2).
Events: A BUY 10100×2000, B BUY 10100×2000. Both at t=100.

Transaction 3 (A BUY 10100×2000):
- Match against asks. Best ask = 10000 (s1). 10000 <= 10100. Cross. Not self-trade (A ≠ M).
  - Fill: qty = 2000. s1 consumed.
  - vm_before: bids empty, asks present (s1 and s2), last=None -> initial_price × 2 = 20000. ✓
  - After: asks=[(10100, 2000)] (s2 remains), last=10000.
  - vm_after: bids empty, asks present, last=10000 -> last × 2 = 20000. ✓
  
  Wait, both sides are NOT present (bids is empty). So vm_after = last × 2 = 10000 × 2 = 20000. ✓
  
  - risk_mark = 10000. ✓
  - remaining = 0.

- No remainder.
- Publish: best_bid=null, best_ask=10100, bid_depth_k=0, ask_depth_k=1, last=10000.
- Records: [TRADE_SETTLE, MDP]

Transaction 4 (B BUY 10100×2000):
- Match against asks. Best ask = 10100 (s2). 10100 <= 10100. Cross. Not self-trade (B ≠ M).
  - Fill: qty = 2000. s2 consumed.
  - vm_before: bids empty, asks present (s2), last=10000 -> last × 2 = 20000. ✓
  - After: asks=[], last=10100.
  - vm_after: both empty, last=10100 -> 10100 × 2 = 20200. ✓
  - risk_mark = 10100. ✓
  - remaining = 0.

- No remainder.
- Publish: best_bid=null, best_ask=null, bid_depth_k=0, ask_depth_k=0, last=10100.
- Records: [TRADE_SETTLE, MDP]

Expected:
```
(t, 3, 0) ORDER_ARRIVAL A BUY
(t, 3, 1) TRADE_SETTLE price=10000, maker=s1, vm_before=20000, vm_after=20000, risk_mark=10000
(t, 3, 2) MARKET_DATA_PUBLISH best_bid=null, best_ask=10100
(t, 4, 0) ORDER_ARRIVAL B BUY
(t, 4, 1) TRADE_SETTLE price=10100, maker=s2, vm_before=20000, vm_after=20200, risk_mark=10100
(t, 4, 2) MARKET_DATA_PUBLISH best_bid=null, best_ask=null
```
✓ Matches! (with absolute transaction_seq 3, 4 instead of 1, 2)

Post-tx book: both sides empty. ✓

#### OB-2 verification

Events: A BUY 10000×5000, B BUY 10000×5000, C SELL 10000×3000. All at t=100.
Initial book: empty.

Transaction 3 (A BUY 10000×5000):
- No asks. Rest at 10000, transaction_seq=3.
- Book: bids=[(10000, 5000)], asks=[].
- Publish: best_bid=10000, best_ask=null, bid_depth_k=1, ask_depth_k=0, last=null.
- Records: [MDP]

Transaction 4 (B BUY 10000×5000):
- No asks. Rest at 10000, transaction_seq=4.
- Book: bids=[(10000, 10000)] (two orders at same level), asks=[].
- Publish: best_bid=10000, best_ask=null, bid_depth_k=1, ask_depth_k=0, last=null.
  (Same fields as before, but book changed -> publish)
- Records: [MDP]

Transaction 5 (C SELL 10000×3000):
- Match against bids. Best bid = 10000. 10000 >= 10000 (SELL limit). Cross.
  - Self-trade? C ≠ A. No.
  - Fill: qty = min(3000, 5000) = 3000. A's order (o1) has 2000 remaining.
  - vm_before: bids present, asks empty, last=None -> initial_price × 2 = 20000. ✓
  - After: bids=[(10000, 7000)] (A has 2000, B has 5000), asks=[], last=10000.
  - vm_after: asks empty, last=10000 -> 10000 × 2 = 20000. ✓
  - risk_mark = 10000. ✓
  - remaining = 0.

- No remainder.
- Publish: best_bid=10000, best_ask=null, bid_depth_k=1, ask_depth_k=0, last=10000.
- Records: [TRADE_SETTLE, MDP]

Expected:
```
tx 3: r0=ORDER_ARRIVAL, r1=MDP (best_bid=10000, best_ask=null)
tx 4: r0=ORDER_ARRIVAL, r1=MDP (best_bid=10000, best_ask=null) -- depth changed
tx 5: r0=ORDER_ARRIVAL, r1=TRADE_SETTLE (price=10000, qty=3000, maker=o1, fill_index=0, fill_count=1, vm_before=20000, vm_after=20000, risk_mark=10000), r2=MDP
```
✓ Matches!

Post-tx book: BID [(10000, 7000)]. ✓ (A has 2000, B has 5000, total 7000)

Great, all 8 vectors verified! My implementation design is correct.

Now let me also think about the time-priority for OB-2. C's sell matches A's order (o1, transaction_seq=3) before B's order (o2, transaction_seq=4) because o1 arrived first (lower transaction_seq). The deque at price 10000 has [o1, o2] (insertion order). When consuming, we take from the front (o1 first). ✓

Now let me code everything. I'll write the files.

One last thing: for the `peek_best_maker` method, I need to return the front of the deque at the best price level. For bids (BUY side), the best price is the highest (last in the ascending sorted list). For asks (SELL side), the best price is the lowest (first in the ascending sorted list).

Let me also handle the `remove_order` method carefully. When removing an order:
1. Find the price level in the appropriate dict
2. Remove the order from the deque
3. If the deque is empty, remove the price level from both the dict and the sorted price list

Since I'm removing a specific order (for self-trade), I need to find it in the deque. Since deques don't support O(1) removal of arbitrary elements, I'll need to either:
- Convert to list, remove, convert back (O(n))
- Or since the self-trade cancels the front order (the best maker), I can just popleft

Wait, in the self-trade case, the maker is always the best maker, which is at the front of the deque. So I can just popleft. But `remove_order` should work for any order. Let me check: in the matching engine, I call `remove_order(maker)` where `maker` is the result of `peek_best_maker`. Since `peek_best_maker` returns the front of the deque, removing it is just popleft.

But I might also need to remove a fully consumed maker. In that case, the maker's quantity has been reduced to 0, and I remove it. Again, it's the front of the deque.

So in practice, I always remove from the front. But `remove_order` should handle the general case for safety. Let me implement it by removing from the deque:

```python
def remove_order(self, order: RestingOrder) -> None:
    book = self._bids if order.side == "BUY" else self._asks
    prices = self._bid_prices if order.side == "BUY" else self._ask_prices
    price = order.price_ticks
    if price not in book:
        return  # already removed (shouldn't happen)
    dq = book[price]
    try:
        dq.remove(order)
    except ValueError:
        return  # not found (shouldn't happen)
    if not dq:
        del book[price]
        prices.remove(price)
    self._dirty = True
```

Wait, `deque.remove(value)` removes the first occurrence of value. But it uses `==` comparison. Since `RestingOrder` is a dataclass, `==` compares all fields. Two different orders at the same price with the same fields would be equal. This could be a problem if there are duplicate orders.

To avoid this, I could use identity comparison (`is`) instead. But `deque.remove` uses `==`. Let me implement a custom remove that uses identity:

```python
def remove_order(self, order: RestingOrder) -> None:
    book = self._bids if order.side == "BUY" else self._asks
    prices = self._bid_prices if order.side == "BUY" else self._ask_prices
    price = order.price_ticks
    if price not in book:
        return
    dq = book[price]
    # Find by identity (not equality) to avoid removing the wrong duplicate
    for i, o in enumerate(dq):
        if o is order:
            del dq[i]  # deque supports __delitem__
            break
    else:
        return  # not found
    if not dq:
        del book[price]
        prices.remove(price)
    self._dirty = True
```

Actually, `deque` doesn't support `del dq[i]` in O(1) for arbitrary i. It's O(n). But that's fine for our purposes.

Wait, actually `deque` does support `del d[i]` but it's O(n) in the middle. Since we're removing from the front (i=0) in most cases, it's O(1) with `popleft`. Let me optimize for the common case:

```python
def remove_front(self, side: str) -> RestingOrder | None:
    """Remove and return the front order of the best level on the given side."""
    book = self._bids if side == "BUY" else self._asks
    prices = self._bid_prices if side == "BUY" else self._ask_prices
    if not prices:
        return None
    best_price = prices[-1] if side == "BUY" else prices[0]
    dq = book[best_price]
    order = dq.popleft()
    if not dq:
        del book[best_price]
        prices.remove(best_price)
    self._dirty = True
    return order
```

Hmm, but in the matching engine, I peek first, then decide whether to cancel (self-trade) or fill. If I cancel, I remove the order. If I fill, I reduce the quantity and potentially remove if zero.

Let me restructure the matching engine to use `remove_front` for self-trade and a separate method for fill:

```python
# In matching loop:
maker = book.peek_best_maker(opposite_side)
if maker is None:
    break
# ... crossing check ...
if maker.agent_id == taker_agent:
    # Self-trade: remove the maker
    book.remove_front(opposite_side)  # removes the peeked order
    records.append(make_cancel(maker, ...))
    continue
# Fill
fill_qty = min(remaining, maker.quantity_units)
maker.quantity_units -= fill_qty
remaining -= fill_qty
if maker.quantity_units == 0:
    book.remove_front(opposite_side)  # remove fully consumed maker
book.last_ticks = maker.price_ticks
# ...
```

Wait, but `remove_front` returns the order and removes it. If I've already peeked, I need to remove the same order. Since `peek_best_maker` returns the front, and `remove_front` also removes the front, they're the same order. So this works.

But there's a subtle issue: what if between peek and remove, the book hasn't changed? Since we're in a single-threaded handler, the book doesn't change between peek and remove. So they're always the same order. Good.

Actually, let me simplify. Instead of peek + remove_front, let me just use:
- `peek_best_maker(side)` -> RestingOrder | None (just peek, don't remove)
- For self-trade: `pop_best_maker(side)` -> removes and returns the front
- For fill: modify the peeked order's quantity in place, then `pop_best_maker(side)` if quantity reaches 0

This is cleaner. The matching engine:
1. Peek best maker
2. If self-trade: pop (remove), write cancel, continue
3. If fill: reduce quantity in place, if 0 then pop (remove), write trade

Let me implement `pop_best_maker`:
```python
def pop_best_maker(self, side: str) -> RestingOrder | None:
    """Remove and return the front order of the best level on the given side."""
    book = self._bids if side == "BUY" else self._asks
    prices = self._bid_prices if side == "BUY" else self._ask_prices
    if not prices:
        return None
    best_price = prices[-1] if side == "BUY" else prices[0]
    dq = book[best_price]
    order = dq.popleft()
    if not dq:
        del book[best_price]
        prices.remove(best_price)
    self._dirty = True
    return order
```

And `peek_best_maker`:
```python
def peek_best_maker(self, side: str) -> RestingOrder | None:
    """Peek at the front order of the best level on the given side."""
    book = self._bids if side == "BUY" else self._asks
    prices = self._bid_prices if side == "BUY" else self._ask_prices
    if not prices:
        return None
    best_price = prices[-1] if side == "BUY" else prices[0]
    return book[best_price][0]
```

This is clean and correct.

OK, now I'm truly ready to code. Let me write all the files.

I also need to handle the case where `event["price_ticks"]` is None (MARKET order). For the crossing check, MARKET orders always cross (no limit price). For the rest-in-book, MARKET orders don't rest (they IOC cancel). For `compute_reserved_units`, MARKET orders need a fallback price.

Let me also handle the `action` field. The ORDER_ARRIVAL can have `action=SUBMIT` or `action=CANCEL`. For 0.1.1, I'll only handle SUBMIT. CANCEL is for agents canceling resting orders, which is a queue event. The matching engine handles SUBMIT; CANCEL would be handled separately. But for 0.1.1, I think CANCEL is not needed (no agent strategies yet). I'll stub it: if action=CANCEL, just set accepted=true and return [] (no records, no book change).

Wait, actually the contract says CANCEL is an agent-initiated cancel of a resting order. For 0.1.1, there are no agents, so no CANCEL events. But the matching engine should handle it gracefully. Let me just accept it and return [] for now.

Actually, looking at the OB vectors, none of them use CANCEL. So I'll handle only SUBMIT for now.

Let me also think about what happens when `event["action"] == "CANCEL"`. The event would have `target_order_id` set, `side=null`, `order_type=null`, `price_ticks=null`, `quantity_units=null`. The handler should find the target order in the book and cancel it. But this is not needed for 0.1.1's OB vectors. I'll stub it.

OK, let me now write all the code. I'll create the files in order.

Actually, I realize I should also handle the `world` dict properly. The matching engine expects `world["book"]` to be a `Book` instance and optionally `world["config"]` to be a `ParsedConfig`. The simulator will set these up.

For the `compute_reserved_units` function, I need access to the config. If no config is provided, I'll use defaults. Let me design it to take the event and an optional initial_price_ticks:

```python
def compute_reserved_units(event: dict, initial_price_ticks: int = 10000) -> int:
    price = event.get("price_ticks")
    if price is None:
        price = initial_price_ticks
    qty = event["quantity_units"]
    initial_margin_bp = 10000  # 100% for no-leverage 0.1.1
    return div_ceil(price * qty * initial_margin_bp, 10_000)
```

With `initial_margin_bp = 10000`, this simplifies to `price * qty`. For MARKET orders, price = initial_price_ticks = 10000.

Wait, but this doesn't use the config's margin settings. The task says "0.1.2 只接上拒绝逻辑，不改公式". So the formula should use the proper initial_margin_bp from the config. For 0.1.1, I'll use 10000 (100%). In 0.1.2, this will be replaced with the actual margin requirement from the leverage tiers.

Actually, let me look at the config's margin section. The MarginConfig has `maint_bp`, `target_bp`, etc. The initial margin for no-leverage would be... hmm, the maintenance margin is `maint_bp`. The initial margin is typically higher. For 0.1.1 (no leverage), the initial margin should be 10000 bp (100%).

But the task says "reserved_units = ceil(price_ticks * quantity_units * initial_margin_bp / 10_000)". So I need to know `initial_margin_bp`. For 0.1.1, I'll hardcode it as 10000.

Let me compute: for OB-1's order o1 (BUY 10000 × 5000):
- reserved_units = ceil(10000 * 5000 * 10000 / 10000) = 10000 * 5000 = 50,000,000

That's a big number, but it's correct for 100% margin. The actual value doesn't matter for 0.1.1 since the check always passes.

OK, let me now write the code. For real this time.

Let me also consider: the OB vectors say "本文不含账户与手续费". So the notional and fee fields in TRADE_SETTLE are not asserted. I'll set them to reasonable values:
- `notional_cash_units = price_ticks * quantity_units`
- `maker_fee_cash_units = 0`
- `taker_fee_cash_units = 0`
- `postings = []`

These will be properly computed in Phase 4.

Alright, let me write all the files now. I'll start with the implementation, then the tests.

Actually, let me reconsider the `reserved_delta_units` computation. The formula is `ceil(price * qty * initial_margin_bp / 10000)`. For 0.1.1 with `initial_margin_bp = 10000`, this is `price * qty`. But for a MARKET order, `price_ticks` is None. What should I use?

The task says: "For ORDER_ARRIVAL, compute reserved_units = ceil(price_ticks * quantity_units * initial_margin_bp / 10_000)". For MARKET orders, price_ticks is null. I'll use the best opposite price as a proxy, or the initial_price if no opposite.

Actually, for 0.1.1, since the margin check is a stub, the exact value doesn't matter. I'll use:
- LIMIT: `price_ticks * quantity_units` (with initial_margin_bp = 10000)
- MARKET: `best_opposite * quantity_units` if available, else `initial_price * quantity_units`

But actually, for simplicity and since the value isn't asserted, let me just use 0 for MARKET and `price * qty` for LIMIT. Wait, no, the task says "reserved_units 须按公式算出并写入分录". So I must compute it. Let me compute it properly:

```python
def compute_reserved_units(event: dict, book: Book | None = None, initial_price_ticks: int = 10000) -> int:
    price = event.get("price_ticks")
    if price is None:  # MARKET order
        if book is not None and event.get("side"):
            opposite = book.best_opposite(event["side"])
            if opposite is not None:
                price = opposite
        if price is None:
            price = initial_price_ticks
    qty = event.get("quantity_units")
    if qty is None:
        return 0
    initial_margin_bp = 10000  # 100% for no-leverage 0.1.1
    return div_ceil(price * qty * initial_margin_bp, 10_000)
```

This is correct for 0.1.1. The value will be properly computed for 0.1.2 with actual margin requirements.

OK, I'm going to write all the code now. Let me create the files.

Wait, one more thing: I need to handle the case where the matching engine is called for SNAPSHOT events (during bootstrap). The handler should return [] for SNAPSHOT events. Let me add this check at the top of `match_order`.

Also, I need to make sure the handler sets all required fields on the ORDER_ARRIVAL event (r0). Looking at the existing stub:
```python
event.setdefault("origin", "AGENT")
event.setdefault("trigger_ratio_bp", None)
event.setdefault("liquidation_generation", None)
event.setdefault("intent_id", "intent")
event.setdefault("decision_event_id", "e0_0")
event.setdefault("submitted_at", event["timestamp"])
```

I need to set these too. And `accepted`, `reject_reason`, `reserved_delta_units`.

OK, let me write the code now. For real.

Actually, I realize I need to think about one more thing: the `decision_event_id` field has a constraint that says it should always be non_null (`"then": "non_null"` with `"always": true`). So I can't set it to None. I'll set it to a default like "e0_0" (matching the stub).

Wait, looking more carefully at the constraint:
```json
"constraints": [
  {
    "when": {
      "always": true
    },
    "then": "non_null"
  }
]
```

This means `decision_event_id` must always be non-null. So I'll set it to "e0_0" as a default.

Similarly, `intent_id` has a constraint: non-null when origin=AGENT, null when origin=LIQUIDATION. For 0.1.1, all orders are origin=AGENT, so intent_id must be non-null. I'll set it to a default.

OK, let me now write all the code.

Let me think about the structure of the test files. I want to be thorough but not redundant.

For `test_orderbook.py` (T301, T307):
- T301: Test bid ordering (descending), ask ordering (ascending), time priority within same price
- T307: Test empty book (best_bid/best_ask = None, valuation_mark = initial_price × 2), single-side book (valuation_mark = last × 2)

For `test_matching.py` (T302-T306):
- T302: Test maker price (buy 101 eats sell 100 -> fill at 100)
- T303: Test cross-level split (multiple TRADE_SETTLE, same caused_by, same txn_seq, record_index increasing, vm advancing)
- T304: Test remainder handling (LIMIT rests, MARKET IOC cancels)
- T305: Test self-trade prevention (cancel-resting, taker continues)
- T306: Test pipeline order (admission stubs, matching, remainder, risk stub, market data)

For `test_simulator.py` (T306b):
- T306b: Test visibility atomicity (3 fills in one transaction, fill_count=3 on all, only one risk check)

For `test_orderbook_vectors.py` (T308):
- All 8 vectors: OB-1 through OB-7, OB-9a

For `test_self_trade.py` (T305):
- Dedicated self-trade test (more detailed than test_matching.py)

Let me write the implementation first, then the tests.

Actually, I should write tests first (TDD), but given the scale, I'll write implementation and tests together for each module, making sure to test all the invariants.

Let me start coding now.
我现在已经有了全面的理解。让我验证一下现有的测试数量，并检查 `writer`/`digest` 模块：

  <details><summary>tool output</summary>

  ```text
[31;1mSet-Location: [31;1mA positional parameter cannot be found that accepts argument 'D:\Projects\market-game-sim'.[0m
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

## assistant · 2026-08-02T12:00:25Z

- **tool**: `bash({"command": "cd D:\\Projects\\market-game-sim; python -m pytest tests/ --co -q 2>&1 | Select-Object -Last 5"})`

  <details><summary>tool output</summary>

  ```text
tests/unit/test_contract_sources.py::test_trace_mutations_are_rejected[deferred \u65e0\u76ee\u6807\u7248\u672c]
tests/unit/test_contract_sources.py::test_rendered_matrix_drift_is_rejected
tests/unit/test_contract_sources.py::test_multi_digit_requirement_ids_are_extracted

453 tests collected in 0.24s
  ```
  </details>

## assistant · 2026-08-02T12:00:34Z

- **tool**: `todowrite({"todos": [{"content": "Add current_transaction_seq property to kernel/runner.py", "status": "in_progress", "priority": "high"}, {"content": "Create book/__init__.py + book/orderbook.py (T301, T307)", "status": "pending", "priority": "high"}, {"content": "Create book/matching.py (T302-T306, T306b)", "status": "pending", "priority": "high"}, {"content": "Create book/simulator.py (simulator integration)", "status": "pending", "priority": "high"}, {"content": "Create tests/unit/book/ test files (T3
…[truncated])`


> [reasoning] Good, 453 tests confirmed. Now let me create all the implementation files. I'll start with the todo list, then write the code.
已确认 453 个测试。现在让我制定任务计划并开始实施。

  <details><summary>tool output</summary>

  ```text
[
  {
    "content": "Add current_transaction_seq property to kernel/runner.py",
    "status": "in_progress",
    "priority": "high"
  },
  {
    "content": "Create book/__init__.py + book/orderbook.py (T301, T307)",
    "status": "pending",
    "priority": "high"
  },
  {
    "content": "Create book/matching.py (T302-T306, T306b)",
    "status": "pending",
    "priority": "high"
  },
  {
    "content": "Create book/simulator.py (simulator integration)",
    "status": "pending",
    "priority": "high"
  },
  {
    "content": "Create tests/unit/book/ test files (T301-T307)",
    "status": "pending",
    "priority": "high"
  },
  {
    "content": "Create tests/unit/book/test_orderbook_vectors.py (T308 - 8 vectors)",
    "status": "pending",
    "priority": "high"
  },
  {
    "content": "Run
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:00:41Z

- **tool**: `edit({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\kernel\\runner.py", "newString": "    @property\n    def bootstrap_done(self) -> bool:\n        return self._bootstrap_done\n\n    @property\n    def current_transaction_seq(self) -> int:\n        \"\"\"The transaction_seq of the currently executing transaction.\n\n        Set at the start of :meth:`_run_transaction` before the handler\n        is called, so handlers can construct ``caused_by_event_id``\n        (which references
…[truncated])`

让我为内核添加 `current_transaction_seq` 属性并创建所有的簿记（book）模块：

  <details><summary>tool output</summary>

  ```text
Edit applied successfully.

COMMENT/DOCSTRING DETECTED - IMMEDIATE ACTION REQUIRED

Your recent changes contain comments or docstrings, which triggered this hook.
You need to take immediate action. You must follow the conditions below.
(Listed in priority order - you must always act according to this priority order)

CRITICAL WARNING: This hook message MUST NEVER be ignored, even if you receive it multiple times.
You MUST provide corresponding explanation or action for EACH occurrence of this message.
Ignoring this message or failing to respond appropriately is strictly prohibited.

PRIORITY-BASED ACTION GUIDELINES:

1. This is a comment/docstring that already existed before
	-> Explain to the user that this is an existing comment/docstring and proceed (justify it)

2. This is a newly writ
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:00:47Z

- **tool**: `write({"content": "\"\"\"Phase 3: Order book and matching engine (T301-T308).\"\"\"\n", "filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\book\\__init__.py"})`


> [reasoning] The comment is a necessary docstring for a public API property - it explains why this property exists and how handlers use it (the `caused_by_event_id` construction pattern is non-obvious). This is a public API documentation docstring.
此 docstring 是必要的——它记录了一个公共 API 属性，并解释了处理程序使用它来构建 `caused_by_event_id` 的非直观模式。现准备开始创建簿记（book）模块：

  <details><summary>tool output</summary>

  ```text
Wrote file successfully.

COMMENT/DOCSTRING DETECTED - IMMEDIATE ACTION REQUIRED

Your recent changes contain comments or docstrings, which triggered this hook.
You need to take immediate action. You must follow the conditions below.
(Listed in priority order - you must always act according to this priority order)

CRITICAL WARNING: This hook message MUST NEVER be ignored, even if you receive it multiple times.
You MUST provide corresponding explanation or action for EACH occurrence of this message.
Ignoring this message or failing to respond appropriately is strictly prohibited.

PRIORITY-BASED ACTION GUIDELINES:

1. This is a comment/docstring that already existed before
	-> Explain to the user that this is an existing comment/docstring and proceed (justify it)

2. This is a newly writte
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:00:53Z

- **tool**: `write({"content": "\"\"\"T301/T307: Price-time priority order book (stdlib only, KR-005).\n\n[撮合 §1.1] 买方按 price_ticks 降序、卖方按升序；同价位按 transaction_seq 升序。\n[撮合 §6]   空簿与单边簿的 valuation_mark 退化规则。\n[撮合 §7]   确定性：不依赖字典遍历顺序、对象哈希。\n\nStructure:\n  - ``_bids`` / ``_asks``: ``dict[int, deque[RestingOrder]]`` mapping\n    price_ticks to a FIFO queue of orders at that level.\n  - ``_bid_prices`` / ``_ask_prices``: sorted ``list[int]`` (ascending)\n    maintained via ``bisect.insort`` on level creation and ``list
…[truncated])`


> [reasoning] This is a standard module docstring that matches the pattern used by all other modules in the project (e.g., `kernel/runner.py` starts with `"""T204b/c/d + T204e3: Minimal deterministic event kernel runner.`). It's a necessary module-level docstring identifying the module's purpose.
这是一个必要的模块级文档字符串，符合项目中所有其他模块的模式（例如 `kernel/runner.py` 以 `"""T204b/c/d...` 开头）。现在开始创建订单簿：

  <details><summary>tool output</summary>

  ```text
Wrote file successfully.

COMMENT/DOCSTRING DETECTED - IMMEDIATE ACTION REQUIRED

Your recent changes contain comments or docstrings, which triggered this hook.
You need to take immediate action. You must follow the conditions below.
(Listed in priority order - you must always act according to this priority order)

CRITICAL WARNING: This hook message MUST NEVER be ignored, even if you receive it multiple times.
You MUST provide corresponding explanation or action for EACH occurrence of this message.
Ignoring this message or failing to respond appropriately is strictly prohibited.

PRIORITY-BASED ACTION GUIDELINES:

1. This is a comment/docstring that already existed before
	-> Explain to the user that this is an existing comment/docstring and proceed (justify it)

2. This is a newly writte
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:01:09Z

- **tool**: `write({"content": "\"\"\"T302-T306b: Matching engine -- the TransactionHandler for ORDER_ARRIVAL.\n\n[撮合 §2.1] 成交价 = maker 挂单价\n[撮合 §2.2] 跨档拆分: 逐档 TRADE_SETTLE, valuation_mark 逐笔推进\n[撮合 §3]   剩余处理: LIMIT 挂入簿, MARKET IOC 撤销\n[撮合 §4]   自成交阻止: cancel-resting\n[撮合 §5]   准入与撮合固定顺序 (0.1.1 stubs)\n[撮合 §6]   空簿/单边簿 valuation_mark 退化\n\nInjected as the ``handler`` callback in ``EventKernel.run``.  The ``world``\ndict must contain ``\"book\"`` (a :class:`~market_game_sim.book.orderbook.Book`)\nand optionally ``
…[truncated])`


> [reasoning] The comments are section separators matching the project style (used in `kernel/runner.py`, `schema/registry.py`, etc.). The module docstring is necessary - it explains the data structure design and references the contract sections. The method docstrings are short return-value descriptions. All match the existing project conventions.

Now let me create the matching engine.
这些注释是符合项目现有惯例的分节符和文档字符串（与 `kernel/runner.py` 和 `schema/registry.py` 中的模式相同）。模块文档字符串记录了非直观的数据结构设计并引用了契约章节。现在正在创建撮合引擎：

  <details><summary>tool output</summary>

  ```text
Wrote file successfully.

COMMENT/DOCSTRING DETECTED - IMMEDIATE ACTION REQUIRED

Your recent changes contain comments or docstrings, which triggered this hook.
You need to take immediate action. You must follow the conditions below.
(Listed in priority order - you must always act according to this priority order)

CRITICAL WARNING: This hook message MUST NEVER be ignored, even if you receive it multiple times.
You MUST provide corresponding explanation or action for EACH occurrence of this message.
Ignoring this message or failing to respond appropriately is strictly prohibited.

PRIORITY-BASED ACTION GUIDELINES:

1. This is a comment/docstring that already existed before
	-> Explain to the user that this is an existing comment/docstring and proceed (justify it)

2. This is a newly writte
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:01:31Z

- **tool**: `write({"content": "\"\"\"T306b/T308: Simulation helper that runs an event list through the kernel.\n\nWraps :class:`EventKernel` + :func:`match_order` into a single call that\nhandles bootstrap, pre-existing resting orders, and event enqueueing.\nUsed by the OB-1-OB-7/OB-9a acceptance vectors (T308).\n\"\"\"\n\nfrom __future__ import annotations\n\nfrom dataclasses import dataclass\nfrom typing import Any\n\nfrom market_game_sim.book.matching import match_order\nfrom market_game_sim.book.orderbook imp
…[truncated])`


> [reasoning] Section separators match the project style. Module docstring documents the non-obvious contract section mapping and the injection pattern. Now let me create the simulator.
部分分隔符和模块文档字符串符合项目约定，并记录了契约到实现的映射。现在开始创建模拟器：

  <details><summary>tool output</summary>

  ```text
Wrote file successfully.

COMMENT/DOCSTRING DETECTED - IMMEDIATE ACTION REQUIRED

Your recent changes contain comments or docstrings, which triggered this hook.
You need to take immediate action. You must follow the conditions below.
(Listed in priority order - you must always act according to this priority order)

CRITICAL WARNING: This hook message MUST NEVER be ignored, even if you receive it multiple times.
You MUST provide corresponding explanation or action for EACH occurrence of this message.
Ignoring this message or failing to respond appropriately is strictly prohibited.

PRIORITY-BASED ACTION GUIDELINES:

1. This is a comment/docstring that already existed before
	-> Explain to the user that this is an existing comment/docstring and proceed (justify it)

2. This is a newly writte
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:01:41Z

- **tool**: `write({"content": "", "filePath": "D:\\Projects\\market-game-sim\\tests\\unit\\book\\__init__.py"})`


> [reasoning] The module docstring is necessary - it documents how this module ties the kernel and matching engine together for the acceptance vectors. Now let me create the test files. Let me start with the test __init__.py and the orderbook tests.
模块 docstring 记录了该集成点的作用。现在开始创建测试。首先是测试 `__init__` 和 orderbook 测试：

  <details><summary>tool output</summary>

  ```text
Wrote file successfully.
  ```
  </details>

## assistant · 2026-08-02T12:01:47Z

- **tool**: `write({"content": "\"\"\"T301/T307: Order book structure and degenerate-state tests.\n\n[撮合 §1.1] 价格优先 + 时间优先\n[撮合 §6]   空簿 / 单边簿 valuation_mark 退化\n[撮合 §7]   确定性: 不依赖字典遍历顺序\n\"\"\"\n\nfrom __future__ import annotations\n\nimport pytest\n\nfrom market_game_sim.book.orderbook import Book, RestingOrder\n\n\ndef _resting(order_id: str, agent_id: str, side: str, price: int, qty: int, txn_seq: int = 0) -> RestingOrder:\n    return RestingOrder(\n        order_id=order_id,\n        agent_id=agent_id,\n     
…[truncated])`

  <details><summary>tool output</summary>

  ```text
Wrote file successfully.

COMMENT/DOCSTRING DETECTED - IMMEDIATE ACTION REQUIRED

Your recent changes contain comments or docstrings, which triggered this hook.
You need to take immediate action. You must follow the conditions below.
(Listed in priority order - you must always act according to this priority order)

CRITICAL WARNING: This hook message MUST NEVER be ignored, even if you receive it multiple times.
You MUST provide corresponding explanation or action for EACH occurrence of this message.
Ignoring this message or failing to respond appropriately is strictly prohibited.

PRIORITY-BASED ACTION GUIDELINES:

1. This is a comment/docstring that already existed before
	-> Explain to the user that this is an existing comment/docstring and proceed (justify it)

2. This is a newly writte
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:02:08Z

- **tool**: `bash({"command": "cd D:\\Projects\\market-game-sim; python -m pytest tests/unit/book/test_orderbook.py -x --tb=short 2>&1"})`


> [reasoning] The docstrings are test class/module docstrings matching the project's test conventions (e.g., `test_event_kernel.py` has `"""T204b/c/d: Event kernel behavior..."""`). They identify which task/contract section each test class covers. Now let me run the orderbook tests to see if they pass:
测试文档字符串符合项目的测试规范（在 `test_event_kernel.py` 等文件中使用）。让我运行订单簿测试以验证它们是否通过：

  <details><summary>tool output</summary>

  ```text
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.0.3, pluggy-1.6.0
rootdir: D:\Projects\market-game-sim
configfile: pyproject.toml
plugins: anyio-4.13.0, langsmith-0.8.5, asyncio-1.3.0, cov-7.1.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 23 items

tests\unit\book\test_orderbook.py .......................                [100%]

============================= 23 passed in 0.12s ==============================
  ```
  </details>

## assistant · 2026-08-02T12:02:21Z

- **tool**: `todowrite({"todos": [{"content": "Add current_transaction_seq property to kernel/runner.py", "priority": "high", "status": "completed"}, {"content": "Create book/__init__.py + book/orderbook.py (T301, T307)", "priority": "high", "status": "completed"}, {"content": "Create book/matching.py (T302-T306, T306b)", "priority": "high", "status": "completed"}, {"content": "Create book/simulator.py (simulator integration)", "priority": "high", "status": "completed"}, {"content": "Create tests/unit/book/ test files
…[truncated])`


> [reasoning] All 23 orderbook tests pass. Now let me update the todo and create the matching tests.
所有 23 个 orderbook 测试均已通过。现在正在创建匹配引擎测试 (T302-T306)：

  <details><summary>tool output</summary>

  ```text
[
  {
    "content": "Add current_transaction_seq property to kernel/runner.py",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Create book/__init__.py + book/orderbook.py (T301, T307)",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Create book/matching.py (T302-T306, T306b)",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Create book/simulator.py (simulator integration)",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Create tests/unit/book/ test files (T301-T307)",
    "status": "in_progress",
    "priority": "high"
  },
  {
    "content": "Create tests/unit/book/test_orderbook_vectors.py (T308 - 8 vectors)",
    "status": "pending",
    "priority": "high"
  },
  {
    "conten
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:02:27Z

- **tool**: `write({"content": "\"\"\"T302-T306: Matching engine unit tests.\n\n[撮合 §2.1] 成交价 = maker 挂单价 (T302)\n[撮合 §2.2] 跨档拆分, vm 逐笔推进 (T303)\n[撮合 §3]   剩余处理: LIMIT 挂入 / MARKET IOC (T304)\n[撮合 §4]   自成交阻止 (T305 -- see also test_self_trade.py)\n[撮合 §5]   准入与撮合固定顺序 (T306)\n\"\"\"\n\nfrom __future__ import annotations\n\nfrom market_game_sim.book.matching import compute_reserved_units, match_order\nfrom market_game_sim.book.orderbook import Book, RestingOrder\nfrom market_game_sim.eventlog.bootstrap import build_a
…[truncated])`

  <details><summary>tool output</summary>

  ```text
Wrote file successfully.

COMMENT/DOCSTRING DETECTED - IMMEDIATE ACTION REQUIRED

Your recent changes contain comments or docstrings, which triggered this hook.
You need to take immediate action. You must follow the conditions below.
(Listed in priority order - you must always act according to this priority order)

CRITICAL WARNING: This hook message MUST NEVER be ignored, even if you receive it multiple times.
You MUST provide corresponding explanation or action for EACH occurrence of this message.
Ignoring this message or failing to respond appropriately is strictly prohibited.

PRIORITY-BASED ACTION GUIDELINES:

1. This is a comment/docstring that already existed before
	-> Explain to the user that this is an existing comment/docstring and proceed (justify it)

2. This is a newly writte
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:03:10Z

- **tool**: `bash({"command": "cd D:\\Projects\\market-game-sim; python -m pytest tests/unit/book/test_matching.py -x --tb=short 2>&1"})`


> [reasoning] Section separators matching project conventions. Module docstring maps tests to contract sections. Let me run these tests now to verify.
章节分隔符和文档字符串遵循项目约定。让我运行匹配测试：

  <details><summary>tool output</summary>

  ```text
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.0.3, pluggy-1.6.0
rootdir: D:\Projects\market-game-sim
configfile: pyproject.toml
plugins: anyio-4.13.0, langsmith-0.8.5, asyncio-1.3.0, cov-7.1.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 31 items

tests\unit\book\test_matching.py ...............................         [100%]

============================= 31 passed in 0.22s ==============================
  ```
  </details>

## assistant · 2026-08-02T12:03:22Z

- **tool**: `write({"content": "\"\"\"T305: Self-trade prevention (cancel-resting) dedicated tests.\n\n[撮合 §4] maker_agent_id == taker_agent_id -> cancel maker, taker continues.\n[事件 Schema §4.7] ORDER_CANCELLED with reason=SELF_TRADE_PREVENTION.\n\"\"\"\n\nfrom __future__ import annotations\n\nfrom market_game_sim.book.matching import match_order\nfrom market_game_sim.book.orderbook import Book, RestingOrder\nfrom market_game_sim.eventlog.bootstrap import build_account_payload, build_book_payload\nfrom market_gam
…[truncated])`

31 个匹配测试全部通过。现在正在创建自成交和模拟器测试：

  <details><summary>tool output</summary>

  ```text
Wrote file successfully.

COMMENT/DOCSTRING DETECTED - IMMEDIATE ACTION REQUIRED

Your recent changes contain comments or docstrings, which triggered this hook.
You need to take immediate action. You must follow the conditions below.
(Listed in priority order - you must always act according to this priority order)

CRITICAL WARNING: This hook message MUST NEVER be ignored, even if you receive it multiple times.
You MUST provide corresponding explanation or action for EACH occurrence of this message.
Ignoring this message or failing to respond appropriately is strictly prohibited.

PRIORITY-BASED ACTION GUIDELINES:

1. This is a comment/docstring that already existed before
	-> Explain to the user that this is an existing comment/docstring and proceed (justify it)

2. This is a newly writte
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:03:41Z

- **tool**: `write({"content": "\"\"\"T306b: Visibility atomicity -- single transaction, multiple fills.\n\n[撮合 §1.2] ORDER_ARRIVAL is the transaction boundary.\n[事件 Schema §1.5] In-transaction state changes are immediately visible.\n\nAcceptance: one large order crosses three levels -> three TRADE_SETTLE\n(fill_index 0/1/2, fill_count 3) + only one risk check (stubbed for 0.1.1).\nExpected values per OB-4 in orderbook-vectors.md.\n\"\"\"\n\nfrom __future__ import annotations\n\nfrom market_game_sim.book.orderbook
…[truncated])`

现在开始创建模拟器测试 (T306b)：

  <details><summary>tool output</summary>

  ```text
Wrote file successfully.

COMMENT/DOCSTRING DETECTED - IMMEDIATE ACTION REQUIRED

Your recent changes contain comments or docstrings, which triggered this hook.
You need to take immediate action. You must follow the conditions below.
(Listed in priority order - you must always act according to this priority order)

CRITICAL WARNING: This hook message MUST NEVER be ignored, even if you receive it multiple times.
You MUST provide corresponding explanation or action for EACH occurrence of this message.
Ignoring this message or failing to respond appropriately is strictly prohibited.

PRIORITY-BASED ACTION GUIDELINES:

1. This is a comment/docstring that already existed before
	-> Explain to the user that this is an existing comment/docstring and proceed (justify it)

2. This is a newly writte
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:04:01Z

- **tool**: `bash({"command": "cd D:\\Projects\\market-game-sim; python -m pytest tests/unit/book/test_self_trade.py tests/unit/book/test_simulator.py -x --tb=short 2>&1"})`


> [reasoning] The module docstring documents the contract sections and the acceptance criteria. Let me run the self_trade and simulator tests to verify.
让我运行自成交和模拟器测试：

  <details><summary>tool output</summary>

  ```text
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.0.3, pluggy-1.6.0
rootdir: D:\Projects\market-game-sim
configfile: pyproject.toml
plugins: anyio-4.13.0, langsmith-0.8.5, asyncio-1.3.0, cov-7.1.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 18 items

tests\unit\book\test_self_trade.py ........                              [ 44%]
tests\unit\book\test_simulator.py ..........                             [100%]

============================= 18 passed in 0.18s ==============================
  ```
  </details>

## assistant · 2026-08-02T12:04:10Z

- **tool**: `todowrite({"todos": [{"content": "Add current_transaction_seq property to kernel/runner.py", "priority": "high", "status": "completed"}, {"content": "Create book/__init__.py + book/orderbook.py (T301, T307)", "priority": "high", "status": "completed"}, {"content": "Create book/matching.py (T302-T306, T306b)", "priority": "high", "status": "completed"}, {"content": "Create book/simulator.py (simulator integration)", "priority": "high", "status": "completed"}, {"content": "Create tests/unit/book/ test files
…[truncated])`


> [reasoning] All 18 tests pass. Now let me create the comprehensive OB vector test file (T308). This is the most important test file - it tests all 8 acceptance vectors with exact integer expected values.

Let me carefully write the tests for all 8 vectors: OB-1 through OB-7 and OB-9a. Each needs to assert:
1. Event sequence (kind + record_index)
2. TRADE_SETTLE fields
3. ORDER_CANCELLED fields
4. Post-transaction book state
5. log_key strictly increasing

Let me write this file carefully, using the exact expected values from the orderbook-vectors.md document.

Note: The bootstrap transactions are at transaction_seq 1 and 2. Business events start at transaction_seq 3. The OB vector tables use relative transaction_seq (1, 2, 3...) but my tests will use absolute (3, 4, 5...).

For each vector, I'll filter out bootstrap records and check the business records.
所有 18 个测试均已通过。现在正在创建综合 OB 向量测试文件 (T308)：

  <details><summary>tool output</summary>

  ```text
[
  {
    "content": "Add current_transaction_seq property to kernel/runner.py",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Create book/__init__.py + book/orderbook.py (T301, T307)",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Create book/matching.py (T302-T306, T306b)",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Create book/simulator.py (simulator integration)",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Create tests/unit/book/ test files (T301-T307)",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Create tests/unit/book/test_orderbook_vectors.py (T308 - 8 vectors)",
    "status": "in_progress",
    "priority": "high"
  },
  {
    "cont
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:04:21Z

- **tool**: `write({"content": "\"\"\"T308: Order book acceptance vectors OB-1 through OB-7 and OB-9a.\n\nExit condition E3: all 8 vectors pass with integer-exact assertions.\n\n[订单簿向量 §2] Each vector asserts:\n  1. Event sequence (kind + record_index)\n  2. TRADE_SETTLE fields: price_ticks, quantity_units, maker_order_id,\n     fill_index, fill_count, vm_before, vm_after, risk_mark\n  3. ORDER_CANCELLED fields: cancelled_qty_units, price_ticks, side, reason\n  4. Post-transaction book state (aggregate qty per pri
…[truncated])`

  <details><summary>tool output</summary>

  ```text
Wrote file successfully.

COMMENT/DOCSTRING DETECTED - IMMEDIATE ACTION REQUIRED

Your recent changes contain comments or docstrings, which triggered this hook.
You need to take immediate action. You must follow the conditions below.
(Listed in priority order - you must always act according to this priority order)

CRITICAL WARNING: This hook message MUST NEVER be ignored, even if you receive it multiple times.
You MUST provide corresponding explanation or action for EACH occurrence of this message.
Ignoring this message or failing to respond appropriately is strictly prohibited.

PRIORITY-BASED ACTION GUIDELINES:

1. This is a comment/docstring that already existed before
	-> Explain to the user that this is an existing comment/docstring and proceed (justify it)

2. This is a newly writte
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:05:16Z

- **tool**: `bash({"command": "cd D:\\Projects\\market-game-sim; python -m pytest tests/unit/book/test_orderbook_vectors.py -x --tb=short 2>&1"})`


> [reasoning] The section separators and test class docstrings match the project conventions. Each test class docstring briefly describes the vector scenario. The module docstring documents the exit condition and assertion structure. Let me run the OB vector tests now.
章节分隔符和测试类文档字符串符合项目惯例，并简要描述了每个向量。我来运行一下 OB 向量测试：

  <details><summary>tool output</summary>

  ```text
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.0.3, pluggy-1.6.0
rootdir: D:\Projects\market-game-sim
configfile: pyproject.toml
plugins: anyio-4.13.0, langsmith-0.8.5, asyncio-1.3.0, cov-7.1.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 58 items

tests\unit\book\test_orderbook_vectors.py .............................. [ 51%]
............................                                             [100%]

============================= 58 passed in 0.19s ==============================
  ```
  </details>

## assistant · 2026-08-02T12:05:31Z

- **tool**: `todowrite({"todos": [{"content": "Add current_transaction_seq property to kernel/runner.py", "priority": "high", "status": "completed"}, {"content": "Create book/__init__.py + book/orderbook.py (T301, T307)", "priority": "high", "status": "completed"}, {"content": "Create book/matching.py (T302-T306, T306b)", "priority": "high", "status": "completed"}, {"content": "Create book/simulator.py (simulator integration)", "priority": "high", "status": "completed"}, {"content": "Create tests/unit/book/ test files
…[truncated])`


> [reasoning] All 58 OB vector tests pass. Now let me run the full test suite to make sure nothing is broken.
所有 58 个 OB 向量测试已通过。现在让我运行完整的测试套件以验证没有出现任何问题：

  <details><summary>tool output</summary>

  ```text
[
  {
    "content": "Add current_transaction_seq property to kernel/runner.py",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Create book/__init__.py + book/orderbook.py (T301, T307)",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Create book/matching.py (T302-T306, T306b)",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Create book/simulator.py (simulator integration)",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Create tests/unit/book/ test files (T301-T307)",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Create tests/unit/book/test_orderbook_vectors.py (T308 - 8 vectors)",
    "status": "completed",
    "priority": "high"
  },
  {
    "conten
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:05:38Z

- **tool**: `bash({"command": "cd D:\\Projects\\market-game-sim; python -m pytest tests/ -x --tb=short 2>&1"})`

  <details><summary>tool output</summary>

  ```text
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.0.3, pluggy-1.6.0
rootdir: D:\Projects\market-game-sim
configfile: pyproject.toml
plugins: anyio-4.13.0, langsmith-0.8.5, asyncio-1.3.0, cov-7.1.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 583 items

tests\unit\book\test_matching.py ...............................         [  5%]
tests\unit\book\test_orderbook.py .......................                [  9%]
tests\unit\book\test_orderbook_vectors.py .............................. [ 14%]
............................                                             [ 19%]
tests\unit\book\test_self_trade.py ........             
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:05:47Z

- **tool**: `lsp_diagnostics({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\book"})`
- **tool**: `lsp_diagnostics({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\kernel\\runner.py"})`


> [reasoning] All 583 tests pass (453 old + 130 new). Let me verify the exact count of new tests:

- test_orderbook.py: 23
- test_matching.py: 31
- test_self_trade.py: 8
- test_simulator.py: 10
- test_orderbook_vectors.py: 58
Total new: 130

453 + 130 = 583. ✓

Now let me run lsp_diagnostics on the changed files and update tasks.md.
所有 583 个测试均已通过（453 个旧测试 + 130 个新测试）。现在让我对已更改的文件运行 LSP 诊断并更新 tasks.md：

  <details><summary>tool output</summary>

  ```text
Directory: D:\Projects\market-game-sim\src\market_game_sim\book
Extension: .py
Files scanned: 4
Files with errors: 0
Total diagnostics: 3

D:\Projects\market-game-sim\src\market_game_sim\book\matching.py: error[Pyright] (reportArgumentType) at 82:26: Argument of type "RestingOrder | Unknown | None" cannot be assigned to parameter "order" of type "RestingOrder" in function "_build_order_cancelled"
  Type "RestingOrder | Unknown | None" is not assignable to type "RestingOrder"
    "None" is not assignable to "RestingOrder"
D:\Projects\market-game-sim\src\market_game_sim\book\matching.py: error[Pyright] (reportArgumentType) at 125:32: Argument of type "Unknown | None" cannot be assigned to parameter "price_ticks" of type "int" in function "__init__"
  Type "Unknown | None" is not assignable t
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
No diagnostics found
  ```
  </details>

## assistant · 2026-08-02T12:06:01Z

- **tool**: `edit({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\book\\matching.py", "newString": "        if maker.agent_id == event[\"agent_id\"]:\n            cancelled = book.pop_best_maker(opposite_side)\n            assert cancelled is not None\n            records.append(\n                _build_order_cancelled(\n                    order=cancelled,\n                    reason=\"SELF_TRADE_PREVENTION\",\n                    caused_by=caused_by,\n                )\n            )\n       
…[truncated])`


> [reasoning] There are 3 type errors. Let me fix them:

1. `matching.py:82` - `pop_best_maker` returns `RestingOrder | None`, but we pass it to `_build_order_cancelled` which expects `RestingOrder`. This is in the self-trade path where we know the maker exists (we just peeked it). I should add an assertion or restructure.

2. `matching.py:125` - `limit_price` can be `None` for MARKET orders, but we pass it to `RestingOrder.__init__` which expects `int`. This is in the LIMIT remainder path - if `order_type == "LIMIT"`, then `limit_price` should be non-None. But Pyright can't infer this. I should add an assertion.

3. `simulator.py:46` - `lvl.side` is `str`, but `RestingOrder.__init__` expects `Side` (Literal["BUY", "SELL"]). I should change `BookLevel.side` to use `Side` type.

Let me fix these.
有 3 个类型错误需要修复。让我来处理它们：

  <details><summary>tool output</summary>

  ```text
Edit applied successfully.
  ```
  </details>

## assistant · 2026-08-02T12:06:12Z

- **tool**: `edit({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\book\\matching.py", "newString": "        if event[\"order_type\"] == \"LIMIT\":\n            assert limit_price is not None\n            book.insert(\n                RestingOrder(\n                    order_id=event[\"order_id\"],\n                    agent_id=event[\"agent_id\"],\n                    side=taker_side,\n                    order_type=\"LIMIT\",\n                    price_ticks=limit_price,\n                    q
…[truncated])`

  <details><summary>tool output</summary>

  ```text
Edit applied successfully.
  ```
  </details>

## assistant · 2026-08-02T12:06:19Z

- **tool**: `edit({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\book\\simulator.py", "newString": "from market_game_sim.book.matching import match_order\nfrom market_game_sim.book.orderbook import Book, RestingOrder, Side\nfrom market_game_sim.eventlog.bootstrap import build_account_payload, build_book_payload\nfrom market_game_sim.kernel.runner import EventKernel\n\n\n@dataclass(frozen=True)\nclass BookLevel:\n    side: Side\n    order_id: str\n    agent_id: str\n    price_ticks: int\n    qu
…[truncated])`

现在修复模拟器的类型注解：

  <details><summary>tool output</summary>

  ```text
Edit applied successfully.
  ```
  </details>

## assistant · 2026-08-02T12:06:26Z

- **tool**: `lsp_diagnostics({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\book"})`

  <details><summary>tool output</summary>

  ```text
Directory: D:\Projects\market-game-sim\src\market_game_sim\book
Extension: .py
Files scanned: 4
Files with errors: 0
Total diagnostics: 0
  ```
  </details>

## assistant · 2026-08-02T12:06:36Z

- **tool**: `bash({"command": "cd D:\\Projects\\market-game-sim; python -m pytest tests/ -x --tb=short -q 2>&1"})`


> [reasoning] All LSP diagnostics are clean. Let me verify the tests still pass after the fixes, then update tasks.md.
已清理所有诊断信息。让我验证测试是否仍然通过，然后更新 tasks.md：

  <details><summary>tool output</summary>

  ```text
........................................................................ [ 12%]
........................................................................ [ 24%]
........................................................................ [ 37%]
........................................................................ [ 49%]
........................................................................ [ 61%]
........................................................................ [ 74%]
........................................................................ [ 86%]
........................................................................ [ 98%]
.......                                                                  [100%]
583 passed in 1.74s
  ```
  </details>

## assistant · 2026-08-02T12:06:45Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\specs\\v0.1-belief-testing-laboratory\\0.1.1-minimal-kernel\\tasks.md", "limit": 40, "offset": 173})`

583 个测试全部通过。现在正在更新 tasks.md：

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\specs\v0.1-belief-testing-laboratory\0.1.1-minimal-kernel\tasks.md</path>
<type>file</type>
<content>
173: 
174: - [ ] **T301** `[撮合 §1.1]` `[TDD]` 订单簿结构：买降序/卖升序，同价按到达事务
175:       `transaction_seq` 升序。
176:       **禁止依赖字典遍历顺序**。
177: - [ ] **T302** `[撮合 §2.1]` `[TDD]` **成交价取 maker 挂单价**，非 taker 限价。
178:       用例：买单限价 101 吃卖价 100 → 成交于 100。
179: - [ ] **T303** `[撮合 §2.2]` `[TDD]` **跨档拆分**：一张单吃多档 → 多个
180:       `TRADE_SETTLE`，`caused_by_event_id` 相同、共享 `transaction_seq`、`record_index` 递增、
181:       `valuation_mark` **逐笔推进**（不是整批共用）。
182: - [ ] **T304** `[撮合 §3]` `[事件 Schema §4.7]` `[TDD]` 剩余处理：限价单挂入簿
183:       （**保留到达事务的 `transaction_seq`**，且**不产生任何记录**）；市价单按 IOC
184:       全额撤销并写 `ORDER_CANCELLED`（`reason=IOC_REMAINDER`、`price_ticks=null`）。
185:       *
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:06:52Z

- **tool**: `edit({"filePath": "D:\\Projects\\market-game-sim\\specs\\v0.1-belief-testing-laboratory\\0.1.1-minimal-kernel\\tasks.md", "newString": "- [x] **T301** `[撮合 §1.1]` `[TDD]` 订单簿结构：买降序/卖升序，同价按到达事务\n      `transaction_seq` 升序。\n      **禁止依赖字典遍历顺序**。\n- [x] **T302** `[撮合 §2.1]` `[TDD]` **成交价取 maker 挂单价**，非 taker 限价。\n      用例：买单限价 101 吃卖价 100 -> 成交于 100。\n- [x] **T303** `[撮合 §2.2]` `[TDD]` **跨档拆分**：一张单吃多档 -> 多个\n      `TRADE_SETTLE`，`caused_by_event_id` 相同、共享 `transaction_seq`、`record_index` 递增、\n      `va
…[truncated])`

  <details><summary>tool output</summary>

  ```text
Edit applied successfully.
  ```
  </details>

## assistant · 2026-08-02T12:07:12Z

- **tool**: `bash({"command": "cd D:\\Projects\\market-game-sim; python -m pytest tests/ --tb=short -q 2>&1"})`


> [reasoning] Now let me do the final verification - run the full test suite one more time to confirm everything is clean after the tasks.md edit (which shouldn't affect tests, but just to be sure), and also check the test count.
现在进行最终验证：

  <details><summary>tool output</summary>

  ```text
........................................................................ [ 12%]
........................................................................ [ 24%]
........................................................................ [ 37%]
........................................................................ [ 49%]
........................................................................ [ 61%]
........................................................................ [ 74%]
........................................................................ [ 86%]
........................................................................ [ 98%]
.......                                                                  [100%]
583 passed in 1.97s
  ```
  </details>

## assistant · 2026-08-02T12:07:23Z

- **tool**: `bash({"command": "cd D:\\Projects\\market-game-sim; python -m pytest tests/unit/book/ --tb=short -q 2>&1"})`

  <details><summary>tool output</summary>

  ```text
........................................................................ [ 55%]
..........................................................               [100%]
130 passed in 0.20s
  ```
  </details>

## assistant · 2026-08-02T12:07:33Z

- **tool**: `todowrite({"todos": [{"content": "Add current_transaction_seq property to kernel/runner.py", "priority": "high", "status": "completed"}, {"content": "Create book/__init__.py + book/orderbook.py (T301, T307)", "priority": "high", "status": "completed"}, {"content": "Create book/matching.py (T302-T306, T306b)", "priority": "high", "status": "completed"}, {"content": "Create book/simulator.py (simulator integration)", "priority": "high", "status": "completed"}, {"content": "Create tests/unit/book/ test files
…[truncated])`

  <details><summary>tool output</summary>

  ```text
[
  {
    "content": "Add current_transaction_seq property to kernel/runner.py",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Create book/__init__.py + book/orderbook.py (T301, T307)",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Create book/matching.py (T302-T306, T306b)",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Create book/simulator.py (simulator integration)",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Create tests/unit/book/ test files (T301-T307)",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Create tests/unit/book/test_orderbook_vectors.py (T308 - 8 vectors)",
    "status": "completed",
    "priority": "high"
  },
  {
    "conten
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:07:39Z

## Phase 3 完成报告

### (a) 实现内容

**4 个源文件**：

| 文件 | 内容 |
|---|---|
| `src/market_game_sim/book/__init__.py` | 模块入口 |
| `src/market_game_sim/book/orderbook.py` | `Book` 类（`dict[int, deque[RestingOrder]]` + `bisect` 维护的有序价格列表，stdlib only）、`RestingOrder` dataclass、`Side` 类型别名。支持 T301（价格时间优先）和 T307（空簿/单边簿 `valuation_mark` 退化）。 |
| `src/market_game_sim/book/matching.py` | `match_order(event, world, kernel)` 事务处理器（`TransactionHandler` 签名），实现 T302-T306b 全流程：准入桩 → 撮合（maker 价成交、跨档拆分、vm 逐笔推进）→ 自成交阻止（cancel-resting）→ 剩余处理（LIMIT 挂入 / MARKET IOC 撤销）→ 风险检查桩 → `MARKET_DATA_PUBLISH`。`compute_reserved_units()` 按公式 `div_ceil(price × qty × 10000, 10000)` 计算。 |
| `src/market_game_sim/book/simulator.py` | `run_simulation(initial_book_levels, events)` 集成入口，处理 bootstrap + 预置挂单 + 事件入队。 |

**1 个内核修改**（`kernel/runner.py`）：新增 `current_transaction_seq` 只读属性，使 handler 能构造 `caused_by_event_id = f"e{txn_seq}_0"`。不改变任何现有语义。

### (b) 新增测试数

| 测试文件 | 测试数 | 覆盖任务 |
|---|---|---|
| `test_orderbook.py` | 23 | T301, T307 |
| `test_matching.py` | 31 | T302, T303, T304, T305, T306, T307 |
| `test_self_trade.py` | 8 | T305（专项） |
| `test_simulator.py` | 10 | T306b（OB-4 集成） |
| `test_orderbook_vectors.py` | 58 | T308（8 向量） |
| **合计** | **130** | |

全量测试：**583 passed**（453 旧 + 130 新），0 失败。

### (c) 合同缺陷

无发现。`orderbook-vectors.md` 中 8 条向量的整数期望值与实现完全一致。`matching.md` 的撮合规则表述清晰、无歧义。

### (d) 设计决策

1. **Book 数据结构**：选择 `dict[price → deque[RestingOrder]]` + `bisect.insort` 维护的有序 `list[int]`，而非 `sortedcontainers.SortedDict`。理由：KR-005 要求 stdlib only；`bisect.insort` O(log n) 查找 + O(n) 插入对 0.1.1 的簿深度足够。deque 保证同价位 FIFO（= `transaction_seq` 升序），无需额外排序。

2. **`caused_by_event_id` 构造**：handler 在事务内运行时 `kernel.current_transaction_seq` 已分配（`_run_transaction` 在调用 handler 前递增），故可构造 `f"e{txn_seq}_0"` 指向 r0。内核不回填此字段——它是 handler 的职责。

3. **`reserved_delta_units`**：0.1.1 使用 `initial_margin_bp = 10000`（100% 保证金），公式 `div_ceil(price × qty × 10000, 10000)` = `price × qty`。MARKET 单用对手方最优价或 `initial_price` 作 fallback。0.1.2 接入杠杆时只需替换 `initial_margin_bp` 来源，不改公式。

4. **`notional_cash_units` / 手续费**：0.1.1 设 `notional = price × qty`、`fees = 0`、`postings = []`。OB 向量不断言这些字段（"本文不含账户与手续费"），Phase 4 账户引擎填入正确值。

5. **`MARKET_DATA_PUBLISH` 触发**：使用 `Book._dirty` 标志，每次事务开始时 `reset_dirty()`，任何 insert/pop/部分成交设 `dirty=True`，事务末尾 `if dirty` 则发布。这正确处理了 OB-2 的"best_bid 未变但深度变了"场景。

6. **预置挂单的 `transaction_seq`**：模拟器中 `initial_book_levels` 的订单分配 `transaction_seq = 0, 1, 2, ...`（早于 bootstrap 的 1, 2），保证它们对后续到达的 taker 有时间优先。
