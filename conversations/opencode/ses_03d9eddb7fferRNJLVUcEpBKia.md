---
tool: "opencode"
tool_name: "OpenCode"
session_id: "ses_03d9eddb7fferRNJLVUcEpBKia"
title: "Phase 4 账户与记账实现 (@Sisyphus-Junior subagent)"
project: "D:/Projects/market-game-sim"
model: "glm-5.2"
created_at: "2026-08-02T12:09:33Z"
updated_at: "2026-08-02T12:11:18Z"
tokens_input: 77727
tokens_output: 1590
cost: 0.0
parent_id: "ses_03dca8ceeffer5HK1H5NpzxJb9"
---

# Phase 4 账户与记账实现 (@Sisyphus-Junior subagent)

## user · 2026-08-02T12:09:33Z

You are implementing **Phase 4** of milestone **0.1.1 (minimal deterministic kernel, no leverage)** in the project `D:\Projects\market-game-sim`. You must complete **all 9 Phase 4 tasks** in the dependency order below.

# EXISTING CODE (do not break)

Read these files first to understand current state:
- `src/market_game_sim/book/orderbook.py` — `Book`, `RestingOrder`, `Side` type
- `src/market_game_sim/book/matching.py` — `match_order(event, world, kernel)` handler, `_make_trade_settle()` builder. **Currently produces empty `postings` and `fees = 0`.** You must wire in real account/fee/postings logic.
- `src/market_game_sim/book/simulator.py` — `run_simulation(initial_book_levels, events)` integration
- `src/market_game_sim/kernel/runner.py` — `EventKernel` with `current_transaction_seq` property
- `src/market_game_sim/eventlog/digest.py` — blake2b digest
- `src/market_game_sim/eventlog/writer.py` — RUN_HEADER, RUN_TRAILER serializers
- `src/market_game_sim/eventlog/bootstrap.py` — snapshot payload builders (ACCOUNT + BOOK). **Note**: Phase 4 needs to extend this to build proper ACCOUNT snapshots with all agent fields.
- `src/market_game_sim/config/parser.py` — `ParsedConfig` (MarketConfig, FeesConfig, AgentConfig, MarginConfig)
- `src/market_game_sim/config/types.py` — `div_ceil`, `round_fee` (ADR-001 §3 fee rounding), `Price`, `Quantity`, `Cash`, `Bp`, `Nanos`
- `src/market_game_sim/schema/event_fields.json` — frozen schema source (do NOT modify). Read sections for TRADE_SETTLE.postings (TRADE_POSTING, WRITE_OFF_POSTING), MARGIN_CALL.postings, ORDER_ARRIVAL.reserved_delta_units
- `src/market_game_sim/schema/registry.py` — SchemaRegistry
- `src/market_game_sim/eventlog/termination.py` — TI-4/TI-5 classifier
- Tests that pass: 583/583. All must stay green.

# CONTRACT DOCUMENTS (read before implementing)

- `docs/contracts/margin-and-account.md` — primary contract for Phase 4 (§1 account fields, §2 entry_notional + PnL, §3 margin, §4 liquidation [0.1.2], §5 write-off [0.1.2], §6 funding, §7 initial state)
- `docs/contracts/acceptance-vectors.md` — 7 acceptance vectors for 0.1.1 (案例 1, 2, 3, 4, 5, 7b, 10). Case 6 (3x boundary), Case 7 (partial liquidation), Case 8 (state machine), Case 9 (write-off) are 0.1.2 scope. **Read the integer projected table in §4 carefully.**
- `docs/contracts/event-schema.md` — §4.2.1 TRADE_POSTING fields, §4.2.3 WRITE_OFF_POSTING fields, §4.2.2 MARGIN_CALL
- `docs/contracts/matching.md` — §2.1 maker price, §2.3 batch settlement, §3 remainder, §5 admission+matching order
- `docs/contracts/orderbook-vectors.md` — OB vectors from Phase 3
- `docs/product/metrics-dictionary.md` — §5.2 PnL bridge (uses `valuation_mark`)

# TASK LIST (all 9 Phase 4 tasks, in dependency order)

The full task definitions are in `specs/v0.1-belief-testing-laboratory/0.1.1-minimal-kernel/tasks.md` lines 212-241. Read that file first. Below is the summary.

**T401** [账户 §1] **账户实体** (no [TDD] tag): `wallet_units`, `position_units`, `entry_notional_units`, `reserved_units`, `realized_pnl_units`, `state`. **All fields present in dataclass**, margin logic stays empty (0.1.2 fills). Build `src/market_game_sim/ledger/account.py` with `Account` dataclass + `AccountState` enum (`ACTIVE`, `PENDING_LIQUIDATION`, `LIQUIDATED`). For 0.1.1, all accounts start in `ACTIVE` state.

**T402** [账户 §2.1] [TDD] **`entry_notional` 更新** (同向加仓 / 反向平仓 / **反向翻仓**): Use the §2.1 algorithm:
```text
同向 (sign(pos) == sign(Δpos) or pos == 0):
    entry_notional += Δpos × price          # Δpos 有符号
    realized_pnl   += 0

反向 (平掉部分或全部):
    closed          = min(|Δpos|, |pos|)
    avg_entry       = entry_notional / pos   # 有符号相除 (toward zero), 余数留 entry_notional
    realized_pnl   += closed × (price − avg_entry) × sign(pos)
    entry_notional -= closed × avg_entry × sign(pos)
    若反向超出 (翻转方向): 剩余部分按同向规则建新仓
```
`avg_entry` is the ONLY non-exact division in the system. Use `int(a/b)` (truncation toward zero) semantics. The remainder stays in `entry_notional` and gets digested on subsequent closes.

**T403** [账户 §2.2] [TDD] **未实现盈亏 + 双口径权益**:
```text
unrealized_pnl(mark) = position_units × mark − entry_notional_units
equity(mark)         = wallet_units + unrealized_pnl(mark)
risk_equity          = equity(risk_mark)         # 用于保证金、准入、强平
valuation_equity     = equity(valuation_mark)    # 用于报告、PnL 桥接
```
**两者不得互相替代**。Compute these as methods on `Account`:
- `unrealized_pnl(mark_ticks)` → int
- `equity(mark_ticks)` → int
- `risk_equity(risk_mark_ticks)` → int
- `valuation_equity(valuation_mark_half_ticks)` → int
- `margin_ratio_bp(risk_mark_ticks)` → int | None  (None when position == 0)

**T404** [ADR-001 §3] [TDD] **手续费**: 向上取整 (`div_ceil`), 方向恒不利于代理. 负 maker 费率（返佣）同样向上取整. 费用账户是**有符号**累计量. Use `round_fee(notional, bps)` from `config/types.py` (already implemented correctly). For 0.1.1: use the config's `maker_bps` and `taker_bps`. **Note**: `notional_cash_units = price_ticks × quantity_units × MULT` where `MULT = tick_size × min_quantity / cash_unit`. For BENCH-001 (tick_size=0.01, min_quantity=0.001, cash_unit=1e-8), MULT=1000. **Read `config/parser.py` to see how ParsedConfig exposes these values.**

**T405** [事件 Schema §4.2.1] [TDD] **账户分录 `postings`**: 长度恒为 2, 含 `*_delta` 与 `*_after`. Each `TRADE_SETTLE` carries `postings: [TRADE_POSTING(role=MAKER), TRADE_POSTING(role=TAKER)]`. **每次账户变动都由引发它的事件承载** (no separate ledger event). Read `event_fields.json` for the 15 fields of `TRADE_POSTING`.

**T406** [账户 §2.3] [TDD] **C1/C2 逐事件断言** (整数精确, 不得容差):
```text
[C1] Σ position_units(t) ≡ 0
[C2] Σ (wallet_units − entry_notional_units)(t) + exchange_fee_units(t) + exchange_risk_pnl_units(t) = Σ wallet_units(0)
```
**逐事件价值断言必须含 `entry_notional_delta`**:
`Σ(wallet_delta − entry_notional_delta) + 费用 + 风险 = 0`. 漏掉 `entry_notional` 会把合法的跨价换手判为失败.

**T407** [验收向量] [TDD] **案例 1—5、10 全部通过** (退出条件 E2). **案例 2 (三代理跨价换手) 为必测项**. 只做案例 1 会误证已推翻的旧等式. **案例 6, 7, 8, 9 不在 0.1.1 范围** (3x leverage / liquidation / write-off are 0.1.2).

**T407b** [验收向量 7b] [TDD] **`reserved_units` 四组场景**. **0.1.1 只需算出并记录该值** (准入判定桩恒通过), 0.1.2 才接入拒绝逻辑. Read acceptance-vectors §3 case 7b for the 4 scenarios and their integer expected values.

**T408** [指标字典 §5.2] [TDD] **PnL 桥接逐事件残差为 0**, 用 `valuation_mark` (**不是** `risk_mark`).

# IMPLEMENTATION REQUIREMENTS (MUST DO)

1. **TDD first for all [TDD] tasks**: Write failing test BEFORE the implementation. Run it (red), then implement, run again (green).

2. **No breaking changes**: All 583 existing tests must still pass. This includes the OB vectors — their `postings` is currently empty, your new code must produce non-empty postings that don't break OB vector assertions (which don't check posting values).

3. **Stdlib only in domain layer** (KR-005): `ledger/`, `book/`, `kernel/`, `eventlog/`, `rng/` must not import numpy, pandas, etc.

4. **Integer-only arithmetic**: All amounts in minimum units. `notional_cash_units = price_ticks × quantity_units × MULT` where MULT is an integer (1000 for BENCH-001). Use `div_ceil` from `config/types.py` for fee/initial_margin rounding.

5. **Multi-account world**: The handler's `world` dict now holds `{book, accounts: dict[agent_id, Account], exchange_fee_units: int, exchange_risk_pnl_units: int, config, market, last_ticks, last_valuation_mark_half_ticks}`. The simulator builds `accounts` from `ParsedConfig.agents`. Each agent starts with `wallet_units=initial_wallet_units, position_units=0, entry_notional_units=0, reserved_units=0, realized_pnl_units=0, state=ACTIVE, liquidation_generation=0, chain_id=null, chain_depth=0`.

6. **Modify `book/matching.py`** to:
   - Compute real `notional_cash_units` using MULT
   - Compute real `maker_fee_cash_units` and `taker_fee_cash_units` using `round_fee` with config's `maker_bps` / `taker_bps`
   - Update accounts on each TRADE_SETTLE using T402's algorithm
   - Emit 2-element `postings` array (TRADE_POSTING × 2) with all 15 fields per posting
   - Update `exchange_fee_units` by adding `maker_fee + taker_fee` (which can be net positive — fees go to exchange)
   - Compute and record `reserved_delta_units` on r0 (ORDER_ARRIVAL)
   - For 0.1.1, **admission check is a stub** (always pass), but `reserved_after` must be computed and recorded

7. **Build `src/market_game_sim/ledger/`**:
   - `__init__.py`
   - `account.py` — `Account` dataclass, `AccountState` enum, `apply_fill(account, side, price_ticks, qty_units, is_taker: bool) -> dict` returning delta fields
   - `conservation.py` — `check_c1_c2(accounts, exchange_fee_units, exchange_risk_pnl_units, initial_wallet_sum) -> tuple[bool, str]`. Returns `(pass, detail)`. **Per-event** (assert after each TRADE_SETTLE).
   - `fees.py` — `compute_fees(price_ticks, qty_units, maker_bps, taker_bps, market) -> tuple[int, int, int]` returning `(notional_cash_units, maker_fee_cash_units, taker_fee_cash_units)`
   - `reserved.py` — `compute_reserved_after(account, active_orders, risk_mark_ticks, market, margin_config) -> int`. Total worst-case reservation. For 0.1.1 this is `div_ceil(|position| * risk_mark * 10000 / 10000) + sum(fee_worst_case_for_active_orders)`. (Since 0.1.1 has 100% margin, it's essentially `|position| * risk_mark + fee_buffer`.)

8. **Build proper ACCOUNT snapshot in bootstrap**:
   - `eventlog/bootstrap.py` needs to emit a real ACCOUNT payload with all agents' full state
   - For 0.1.1, all agents have `state=ACTIVE, position=0, entry_notional=0, etc.`
   - The snapshot must include ALL agents including those that never trade (C1/C2 sum needs the full set)
   - Sort by `agent_id` codepoint ascending

9. **Notional computation**:
```python
MULT = 1000  # tick_size * min_quantity / cash_unit for BENCH-001
notional_cash_units = price_ticks * quantity_units * MULT
```
For other configs, compute MULT from the Decimal values, but as integer for BENCH-001 it should be 1000. Read `config/parser.py` MarketConfig to see how to compute this integer.

10. **For Case 7b (reserved_units scenarios)**: Read acceptance-vectors §3 case 7b carefully. The 4 scenarios require:
    - Track `active_orders` (currently resting LIMIT orders) per agent
    - When an order is enqueued (r0 processed), compute new `reserved_after` and set `reserved_delta_units` = new - old
    - When an order is matched/consumed, similarly update
    - The integer expected values are huge (100000000000 = 1e11) — this is correct for cash_unit=1e-8

11. **Test organization**:
    - `tests/unit/ledger/test_account.py` — T401, T402, T403 unit tests
    - `tests/unit/ledger/test_fees.py` — T404 unit tests
    - `tests/unit/ledger/test_conservation.py` — T406 unit tests (C1, C2 per event)
    - `tests/unit/ledger/test_reserved.py` — T407b unit tests
    - `tests/unit/ledger/test_acceptance_vectors.py` — T407 (cases 1-5, 10) + T408 (PnL bridge)
    - `tests/unit/ledger/test_bootstrap_account.py` — bootstrap includes all accounts

12. **For OB vectors from Phase 3**: They currently pass with empty `postings` and `fees=0`. After Phase 4, `postings` will be non-empty and `fees` non-zero. **The OB vector tests don't assert on posting values, so they should still pass.** But verify by running them after each change.

13. **Update tasks.md**: Mark each completed task as `[x]`. Lines 212-241.

14. **Run `python -m pytest tests/ -x --tb=short` at the end**: All tests (583 old + new) must pass.

# MUST NOT DO

1. **Do NOT modify** `event_fields.json` — it's a frozen contract source.
2. **Do NOT modify** `kernel/runner.py`, `eventlog/writer.py`, `eventlog/digest.py`, `eventlog/termination.py` — Phase 2/3 invariants must be preserved.
3. **Do NOT add liquidation logic** (T408, PENDING_LIQUIDATION, LIQUIDATED state transitions, write-off) — these are 0.1.2.
4. **Do NOT add 3x leverage admission** (Case 6 from acceptance-vectors) — 0.1.2.
5. **Do NOT add funding rate** (Case 10 just verifies the mechanism is reserved; `funding_rate_bp=0` so it's trivially zero) — keep funding logic out of code, just leave `exchange_fee_units` unchanged for funding.
6. **Do NOT import numpy/pandas/etc.** in `ledger/`.
7. **Do NOT use floats** in account/fees/postings/conservation. All ints.
8. **Do NOT commit** — leave to user.

# EXPECTED OUTCOME

- All 9 Phase 4 tasks (T401-T408 + T407b) implemented
- Cases 1, 2, 3, 4, 5, 7b, 10 from acceptance-vectors pass with integer-exact assertions
- C1 / C2 conservation verified per-event for all cases
- New tests added (estimate: 100-200 new tests)
- `python -m pytest tests/ -x --tb=short` shows 100% pass
- `tasks.md` updated with `[x]` for the 9 completed tasks
- A summary report listing: (a) what you implemented, (b) new test count, (c) any contract defects (do NOT fix them), (d) design decisions made

# TOOLS

- `read`, `write`, `edit`, `bash` (Python and pytest), `grep`, `glob`
- `lsp_diagnostics` after edits
- `task(task_id=...)` if needed

# WORK APPROACH

1. Read `specs/v0.1-belief-testing-laboratory/0.1.1-minimal-kernel/tasks.md` lines 212-241
2. Read `docs/contracts/margin-and-account.md` in full
3. Read `docs/contracts/acceptance-vectors.md` in full
4. Read `docs/contracts/event-schema.md` §4.2.1, §4.2.3
5. Read `event_fields.json` sections for TRADE_POSTING (15 fields), MARGIN_CALL, ACCOUNT_SNAPSHOT_ENTRY
6. Read `config/parser.py` and `config/types.py` to understand ParsedConfig and fee rounding
7. Read existing `book/matching.py` to understand the current handler structure
8. Read existing `book/simulator.py` to understand the integration point
9. Read existing `eventlog/bootstrap.py` to extend with proper ACCOUNT snapshots
10. Build `ledger/account.py` (T401) + tests
11. Build `entry_notional` update logic (T402) + tests
12. Build equity methods (T403) + tests
13. Build fee computation (T404) + tests
14. Build `ledger/fees.py` with notional + maker/taker fee logic
15. Build `ledger/conservation.py` with C1/C2 check
16. Build `ledger/reserved.py` with reserved_units computation
17. Modify `book/matching.py` to use the new ledger functions and emit real postings
18. Modify `eventlog/bootstrap.py` to include all agent accounts in ACCOUNT snapshot
19. Build acceptance vector tests (T407) — 7 cases with integer-exact assertions
20. Build reserved_units tests (T407b) — 4 scenarios with integer-exact assertions
21. Build PnL bridge test (T408) — per-event residual = 0
22. Run full test suite, fix any breakage (especially Phase 3 OB vectors)
23. Update tasks.md
24. Final pytest run + lsp_diagnostics
25. Report back

You have full context. Begin.
<!-- OMO_INTERNAL_INITIATOR -->

## assistant · 2026-08-02T12:09:33Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\specs\\v0.1-belief-testing-laboratory\\0.1.1-minimal-kernel\\tasks.md", "offset": 200, "limit": 60})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\docs\\contracts\\margin-and-account.md"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\docs\\contracts\\acceptance-vectors.md"})`


> [reasoning] Let me start by understanding the project structure and reading the key files mentioned in the task. This is a complex multi-phase implementation task, so I'll need to be methodical.

Let me begin by reading the task definitions and contract documents.
我将先阅读必要的上下文文件，以了解当前的状态和需求。

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\specs\v0.1-belief-testing-laboratory\0.1.1-minimal-kernel\tasks.md</path>
<type>file</type>
<content>
200:       `fill_count` 3）+ **仅一次**整批风险检查。期望值见
201:       [订单簿向量](../../../docs/contracts/orderbook-vectors.md) OB-4。
202: - [x] **T307** `[撮合 §6]`、`[退化 §1]` `[TDD]` 空簿与单边簿：市价单 IOC 撤销、
203:       `mid` 未定义时 `valuation_mark` 退化为 `last`、首笔成交前退化为
204:       `initial_price`。
205: - [x] **T308** `[订单簿向量 OB-1-OB-7、OB-9a]` `[TDD]` **八条订单簿向量全部通过**
206:       （退出条件 E3）。断言事件序列（**含 `MARKET_DATA_PUBLISH` 的存在与位置**）、
207:       `record_index`、`fill_index`/`fill_count`、逐笔 `valuation_mark`/`risk_mark`、
208:       `ORDER_CANCELLED` 字段与事务后簿状态，**全部为整数比较，禁止容差断言**。
209:       **OB-8 与 OB-9b 不在 0.1.1 范围内**--它们依赖杠杆账户与保证金判定，
210:       属 0.1.2（`0.1.2 T201` / `0.1.2 T104`）。
211: 

…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\docs\contracts\margin-and-account.md</path>
<type>file</type>
<content>
1: # 账户与保证金合同（线性永续合约）
2: 
3: **适用范围**：跨规格实现合同（当前交付规格 v0.1）  
4: **状态**：Stable（变更须记 ADR 并评估既有实验可比性）  
5: **创建日期**：2026-08-01  
6: **支撑需求**：v0.1 / FR-004—FR-008；PRD / PR-004—PR-007  
7: **关联**：[事件 Schema](event-schema.md)、[退化状态](degenerate-states.md)、
8: [代理策略](agent-strategy.md)、[指标字典](../product/metrics-dictionary.md)、
9: [ADR-001](../adr/001-numeric-and-serialization-contract.md)
10: 
11: ## 0. 为什么是永续合约
12: 
13: 此前文档语义混合：制度名为 `crypto_perp_free`（永续），账本却按现金与库存交割
14: （现货），退化状态要求「现金不得为负」，而预冻结规则要求冻结**全额**名义金额——
15: 那样根本无法杠杆买入。本文选定**线性永续合约**并消除该矛盾。
16: 
17: 选它而非杠杆现货的理由：
18: 
19: | 性质 | 永续 | 杠杆现货 |
20: |---|---|---|
21: | 净持仓 | **恒为 0**（每笔成交产生一多一空） | 非零，随初始配置而定 |
22: | 权益守恒 | **精确成立**（见 §2.3
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\docs\contracts\acceptance-vectors.md</path>
<type>file</type>
<content>
1: # 账户引擎验收向量
2: 
3: **适用范围**：跨规格实现合同（当前交付规格 v0.1）  
4: **状态**：Stable（变更须同步[账户与保证金合同](margin-and-account.md)）  
5: **创建日期**：2026-08-01  
6: **支撑需求**：v0.1 / SC-001；PRD / KPI-001  
7: **关联**：[账户与保证金](margin-and-account.md)、[事件 Schema](event-schema.md)、
8: [指标字典](../product/metrics-dictionary.md)
9: 
10: ## 0. 用途与地位
11: 
12: 本文是账户合同 §9 最小验收包的**完整期望值表**，语言无关。
13: 
14: 它同时是三样东西：**合同的可执行验证**（数字对不上说明合同有洞）、**0.1.1 的测试
15: 用例**、以及**实现的唯一裁判**。实现与本表不符时，**以本表为准**——除非能证明本表
16: 本身违反账户合同，那种情况下先修合同再重算本表。
17: 
18: 「实现时补齐」是被明确排除的做法：那等于让代码反向决定合同。
19: 
20: ## 1. 单位与配置
21: 
22: 全部取自 `benchmarks/BENCH-001.yaml`：
23: 
24: ```text
25: tick_size = 0.01      min_quantity = 0.001      cash_unit = 1e-8
26: MULT =
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:09:38Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\book\\matching.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\book\\simulator.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\config\\parser.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\config\\types.py"})`


> [reasoning] I now have a good understanding of the task. Let me read more key files to understand the existing code.
让我读取现有的代码文件，以了解当前的结构。

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\book\matching.py</path>
<type>file</type>
<content>
1: """T302-T306b: Matching engine -- the TransactionHandler for ORDER_ARRIVAL.
2: 
3: [撮合 §2.1] 成交价 = maker 挂单价
4: [撮合 §2.2] 跨档拆分: 逐档 TRADE_SETTLE, valuation_mark 逐笔推进
5: [撮合 §3]   剩余处理: LIMIT 挂入簿, MARKET IOC 撤销
6: [撮合 §4]   自成交阻止: cancel-resting
7: [撮合 §5]   准入与撮合固定顺序 (0.1.1 stubs)
8: [撮合 §6]   空簿/单边簿 valuation_mark 退化
9: 
10: Injected as the ``handler`` callback in ``EventKernel.run``.  The ``world``
11: dict must contain ``"book"`` (a :class:`~market_game_sim.book.orderbook.Book`)
12: and optionally ``"config"`` (a :class:`ParsedConfig`).
13: """
14: 
15: from __future__ import annotations
16: 
17: from typing import Any
18: 
19: from market_game_sim.book.orderbook import Book, Rest
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\book\simulator.py</path>
<type>file</type>
<content>
1: """T306b/T308: Simulation helper that runs an event list through the kernel.
2: 
3: Wraps :class:`EventKernel` + :func:`match_order` into a single call that
4: handles bootstrap, pre-existing resting orders, and event enqueueing.
5: Used by the OB-1-OB-7/OB-9a acceptance vectors (T308).
6: """
7: 
8: from __future__ import annotations
9: 
10: from dataclasses import dataclass
11: from typing import Any
12: 
13: from market_game_sim.book.matching import match_order
14: from market_game_sim.book.orderbook import Book, RestingOrder, Side
15: from market_game_sim.eventlog.bootstrap import build_account_payload, build_book_payload
16: from market_game_sim.kernel.runner import EventKerne
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

## assistant · 2026-08-02T12:09:42Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\book\\orderbook.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\eventlog\\bootstrap.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\kernel\\runner.py"})`


> [reasoning] Now let me read the orderbook.py, bootstrap.py, event_fields.json (the relevant parts), and other key files.
现在让我读取 orderbook、bootstrap 以及 schema 文件。

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

## assistant · 2026-08-02T12:09:47Z

- **tool**: `bash({"command": "find \"D:/Projects/market-game-sim/src/market_game_sim/schema\" -type f | head -20"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\schema\\registry.py"})`

现在让我查看 `event_fields.json` 架构，重点关注 `TRADE_POSTING`、`MARGIN_CALL` 和 `ACCOUNT_SNAPSHOT_ENTRY`。

  <details><summary>tool output</summary>

  ```text
[31;1mhead: [31;1mThe term 'head' is not recognized as a name of a cmdlet, function, script file, or executable program.[0m
[31;1m[31;1mCheck the spelling of the name, or if a path was included, verify that the path is correct and try again.[0m
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

## assistant · 2026-08-02T12:09:53Z

- **tool**: `grep({"output_mode": "files_with_matches", "path": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\schema", "pattern": "TRADE_POSTING|WRITE_OFF_POSTING|ACCOUNT_SNAPSHOT_ENTRY|EXCHANGE_SNAPSHOT|MARGIN_CALL"})`
- **tool**: `glob({"pattern": "tests/**/*.py"})`

现在让我读取 `event_fields.json` 以获取 `TRADE_POSTING` 结构以及订单簿向量 (OB vectors)。

  <details><summary>tool output</summary>

  ```text
Found 2 match(es) in 2 file(s)

D:\Projects\market-game-sim\src\market_game_sim\schema\registry.py

D:\Projects\market-game-sim\src\market_game_sim\schema\event_fields.json

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
- Agents
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
Found 26 file(s)

D:\Projects\market-game-sim\tests\unit\book\test_orderbook_vectors.py
D:\Projects\market-game-sim\tests\unit\book\test_simulator.py
D:\Projects\market-game-sim\tests\unit\book\test_self_trade.py
D:\Projects\market-game-sim\tests\unit\book\test_matching.py
D:\Projects\market-game-sim\tests\unit\book\test_orderbook.py
D:\Projects\market-game-sim\tests\unit\book\__init__.py
D:\Projects\market-game-sim\tests\unit\schema\test_registry_parity.py
D:\Projects\market-game-sim\tests\unit\eventlog\test_writer.py
D:\Projects\market-game-sim\tests\unit\kernel\test_event_kernel.py
D:\Projects\market-game-sim\tests\unit\eventlog\test_termination.py
D:\Projects\market-game-sim\tests\unit\eventlog\test_digest.py
D:\Projects\market-game-sim\tests\unit\schema\test_bidirectional_consistency.
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:09:58Z

- **tool**: `grep({"output_mode": "content", "path": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\schema\\event_fields.json", "pattern": "\"TRADE_POSTING\"|\"WRITE_OFF_POSTING\"|\"ACCOUNT_SNAPSHOT_ENTRY\"|\"EXCHANGE_SNAPSHOT\"|\"ACCOUNT_PAYLOAD\"|\"MARGIN_CALL\"|\"ORDER_ARRIVAL\"|\"TRADE_SETTLE\""})`

  <details><summary>tool output</summary>

  ```text
Found 18 match(es) in 1 file(s)

D:\Projects\market-game-sim\src\market_game_sim\schema\event_fields.json
  386: "ORDER_ARRIVAL",
  388: "TRADE_SETTLE",
  389: "MARGIN_CALL",
  421: "ORDER_ARRIVAL": {
  806: "TRADE_SETTLE": {
  897: "element_structure": "TRADE_POSTING",
  927: "MARGIN_CALL": {
  1014: "element_structure": "WRITE_OFF_POSTING",
  1210: "ACCOUNT": "ACCOUNT_PAYLOAD",
  1308: "TRADE_POSTING": {
  1315: "TRADE_POSTING"
  1419: "WRITE_OFF_POSTING": {
  1427: "WRITE_OFF_POSTING"
  1545: "ACCOUNT_PAYLOAD": {
  1550: "element_structure": "ACCOUNT_SNAPSHOT_ENTRY",
  1563: "element_structure": "EXCHANGE_SNAPSHOT",
  1570: "ACCOUNT_SNAPSHOT_ENTRY": {
  1693: "EXCHANGE_SNAPSHOT": {

[Agent Usage Reminder]

You called a search/fetch tool directly without leveraging specialized agents.

R
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:10:06Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\schema\\event_fields.json", "limit": 220, "offset": 806})`

我来读取 schema JSON 的相关部分。

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\schema\event_fields.json</path>
<type>file</type>
<content>
806:     "TRADE_SETTLE": {
807:       "kind": "event",
808:       "priority_class": 1,
809:       "queueing": "transaction_record",
810:       "fields": {
811:         "maker_order_id": {
812:           "value_type": "str",
813:           "nullable": false,
814:           "required": "always",
815:           "hash": "HASH_INCLUDE"
816:         },
817:         "taker_order_id": {
818:           "value_type": "str",
819:           "nullable": false,
820:           "required": "always",
821:           "hash": "HASH_INCLUDE"
822:         },
823:         "maker_agent_id": {
824:           "value_type": "str",
825:           "nullable": false,
826:           "required": "always",
827
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:10:13Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\schema\\event_fields.json", "limit": 220, "offset": 1300})`

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\schema\event_fields.json</path>
<type>file</type>
<content>
1300:         "intent_id": {
1301:           "value_type": "str",
1302:           "nullable": false,
1303:           "required": "always",
1304:           "hash": "HASH_EXCLUDE"
1305:         }
1306:       }
1307:     },
1308:     "TRADE_POSTING": {
1309:       "kind": "nested",
1310:       "leaf_field_count": 15,
1311:       "fields": {
1312:         "posting_type": {
1313:           "value_type": "enum",
1314:           "enum": [
1315:             "TRADE_POSTING"
1316:           ],
1317:           "nullable": false,
1318:           "required": "always",
1319:           "hash": "HASH_INCLUDE"
1320:         },
1321:         "agent_id": {
1322:           "value_type": "str",
132
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:10:18Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\schema\\event_fields.json", "limit": 220, "offset": 1520})`

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\schema\event_fields.json</path>
<type>file</type>
<content>
1520:           "constraints": [
1521:             {
1522:               "when": {
1523:                 "field": "role",
1524:                 "equals": "ACCOUNT"
1525:               },
1526:               "then": "non_null"
1527:             },
1528:             {
1529:               "when": {
1530:                 "field": "role",
1531:                 "equals": "EXCHANGE_RISK"
1532:               },
1533:               "then": "null"
1534:             }
1535:           ]
1536:         },
1537:         "risk_pnl_delta_units": {
1538:           "value_type": "int",
1539:           "nullable": false,
1540:           "required": "always",
1541:           "hash": "HASH_INCLUDE"

…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:10:22Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\schema\\event_fields.json", "limit": 170, "offset": 421})`


> [reasoning] Now let me look at the ORDER_ARRIVAL fields (especially `reserved_delta_units`) and understand the current matching test structure.
让我读取 `ORDER_ARRIVAL` 字段和现有的匹配测试。

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\schema\event_fields.json</path>
<type>file</type>
<content>
421:     "ORDER_ARRIVAL": {
422:       "kind": "event",
423:       "priority_class": 0,
424:       "queueing": "queue_event",
425:       "fields": {
426:         "agent_id": {
427:           "value_type": "str",
428:           "nullable": false,
429:           "required": "always",
430:           "hash": "HASH_INCLUDE"
431:         },
432:         "order_id": {
433:           "value_type": "str",
434:           "nullable": false,
435:           "required": "always",
436:           "hash": "HASH_INCLUDE"
437:         },
438:         "action": {
439:           "value_type": "enum",
440:           "enum": [
441:             "SUBMIT",
442:             "CANCEL"
443:           ],
444
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:10:29Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\schema\\event_fields.json", "limit": 230, "offset": 591})`

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\schema\event_fields.json</path>
<type>file</type>
<content>
591:           "hash": "HASH_INCLUDE",
592:           "constraints": [
593:             {
594:               "when": {
595:                 "field": "accepted",
596:                 "equals": false
597:               },
598:               "then": "non_null"
599:             },
600:             {
601:               "when": {
602:                 "field": "accepted",
603:                 "equals": true
604:               },
605:               "then": "null"
606:             }
607:           ]
608:         },
609:         "reserved_delta_units": {
610:           "value_type": "int",
611:           "nullable": false,
612:           "required": "always",
613:           "hash": "HASH
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:10:32Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\tests\\unit\\book\\test_orderbook_vectors.py", "limit": 100})`

现在让我查看一下现有的匹配测试（matching tests）和 `orderbook_vectors`，以了解其结构。

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\tests\unit\book\test_orderbook_vectors.py</path>
<type>file</type>
<content>
1: """T308: Order book acceptance vectors OB-1 through OB-7 and OB-9a.
2: 
3: Exit condition E3: all 8 vectors pass with integer-exact assertions.
4: 
5: [订单簿向量 §2] Each vector asserts:
6:   1. Event sequence (kind + record_index)
7:   2. TRADE_SETTLE fields: price_ticks, quantity_units, maker_order_id,
8:      fill_index, fill_count, vm_before, vm_after, risk_mark
9:   3. ORDER_CANCELLED fields: cancelled_qty_units, price_ticks, side, reason
10:   4. Post-transaction book state (aggregate qty per price level)
11:   5. All log_key strictly increasing
12: 
13: All comparisons are integer-exact. No tolerance assertions.
14: 
15: Bootstrap transactions (SNAPSHOT ACCOUNT/BOOK) are at 
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:10:39Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\tests\\unit\\book\\test_matching.py", "limit": 100})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\tests\\unit\\eventlog\\test_bootstrap.py"})`

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\tests\unit\book\test_matching.py</path>
<type>file</type>
<content>
1: """T302-T306: Matching engine unit tests.
2: 
3: [撮合 §2.1] 成交价 = maker 挂单价 (T302)
4: [撮合 §2.2] 跨档拆分, vm 逐笔推进 (T303)
5: [撮合 §3]   剩余处理: LIMIT 挂入 / MARKET IOC (T304)
6: [撮合 §4]   自成交阻止 (T305 -- see also test_self_trade.py)
7: [撮合 §5]   准入与撮合固定顺序 (T306)
8: """
9: 
10: from __future__ import annotations
11: 
12: from market_game_sim.book.matching import compute_reserved_units, match_order
13: from market_game_sim.book.orderbook import Book, RestingOrder
14: from market_game_sim.eventlog.bootstrap import build_account_payload, build_book_payload
15: from market_game_sim.kernel.runner import EventKernel
16: 
17: 
18: def _make_book(initial_price: int = 10000) -> Book:
19:     return Book(init
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\tests\unit\eventlog\test_bootstrap.py</path>
<type>file</type>
<content>
1: """T204e3: Forced initial snapshots (bootstrap barrier).
2: 
3: [事件 Schema §4.6.3] 强制初态快照
4: 
5: At t=0, two SNAPSHOT queue events are pre-enqueued (ACCOUNT enqueue_seq=0,
6: BOOK enqueue_seq=1); after popping they form transaction_seq=1 and 2;
7: business transactions start from 3.  Bootstrap barrier: any business
8: enqueue before both snapshots commit raises KernelAbort(INTERNAL).
9: ACCOUNT snapshot must include ALL accounts sorted by agent_id codepoint ascending.
10: """
11: 
12: from __future__ import annotations
13: 
14: import pytest
15: 
16: from market_game_sim.eventlog.bootstrap import (
17:     build_account_payload,
18:     build_account_snapshot_entry,
19:     build_b
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:10:44Z

- **tool**: `bash({"command": "cd /d D:\\Projects\\market-game-sim && python -m pytest tests/ --tb=no -q 2>&1 | tail -20"})`
- **tool**: `grep({"output_mode": "content", "path": "D:\\Projects\\market-game-sim\\docs\\product\\metrics-dictionary.md", "pattern": "5.2|PnL|valuation_mark|桥接|bridge|残差"})`

现在让我运行现有的测试套件以确认基准，并查看 `metrics-dictionary` 以了解 PnL 桥接。

  <details><summary>tool output</summary>

  ```text
[31;1mSet-Location: [31;1mA positional parameter cannot be found that accepts argument 'D:\Projects\market-game-sim'.[0m
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
Found 31 match(es) in 1 file(s)

D:\Projects\market-game-sim\docs\product\metrics-dictionary.md
  178: | **估值标记价** `valuation_mark` | 用于权益、未实现 PnL 与会计桥接（§5.2）。取 `mid`；`mid` 未定义时退化为 `last` | 两者皆无时未定义 |
  182: 若用于强平判定，一次报价就可能触发强平（代理策略 §3.3）；`valuation_mark` 用 `mid`，
  183: 因为它是更好的公允价估计，且**若估值也用 `last`，会使 §5.2 的 `Spread` 与 `Impact`
  186: 事件日志须记录 `valuation_mark_before` 与 `valuation_mark_after`
  187: （事件 Schema §4.2），使会计桥接可仅凭日志重放。
  243: | 权益 | `钱包 + 未实现 PnL` |
  244: | 已实现 PnL | 平仓部分的累计损益，不含未平仓部分 |
  245: | 未实现 PnL | `仓位 × mark − 开仓成本`（账户合同 §2.2） |
  246: | 总 PnL | 已实现 + 未实现 |
  269: | 穿仓额 | `exchange_risk_pnl_units` 的累计值，**有符号，损失为负**（账户合同 §5.2） |
  350: **个体账户另须桥接检验**（§5.2）：全局恒等式捕捉不到「A 少了 B 多了」之外的错误，
  351: 个体桥接才能定位到具体账户。
  353: ### 5.2 PnL 会计桥接（FR-017）
  355: 权益变动必须被**完整、互斥地**分解为五项，**残差恒为
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:10:50Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\docs\\product\\metrics-dictionary.md", "limit": 130, "offset": 340})`

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\docs\product\metrics-dictionary.md</path>
<type>file</type>
<content>
340: 
341: 即 **`Σequity` 不随 mark 变动**，恒等于 C2 左侧第一项。这是永续相对杠杆现货的核心
342: 收益：现货下净持仓非零，`Σ权益` 随价格漂移；永续下多空两侧的重估自动抵消。
343: 
344: 已验算：5 代理 6 笔跨价换手（含反向平仓与手续费），`mark` 取 50 / 100 / 200 时
345: `Σequity` 恒为 4997.366。
346: 
347: **守恒测试必须包含三代理跨价换手**（A 建仓 → A 平给 C → B 仍持仓）。只用一对多空
348: 且从不更换对手方的用例，会让已被推翻的「Σwallet = 常数」看起来成立。
349: 
350: **个体账户另须桥接检验**（§5.2）：全局恒等式捕捉不到「A 少了 B 多了」之外的错误，
351: 个体桥接才能定位到具体账户。
352: 
353: ### 5.2 PnL 会计桥接（FR-017）
354: 
355: 权益变动必须被**完整、互斥地**分解为五项，**残差恒为 0**：
356: 
357: ```text
358: Δequity = Spread + Impact + Revaluation + Funding − Fees
359: ```
360: 
361: 其中 `signed_qty` 买入为正、卖出为负；**`vm` 为估值标记价 `valuation_mark`（§3.1），
362: 不是风险标记价**：
363: 
364: | 项 | 公式 | 含义 |
365: |---|---|---|
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:10:54Z

- **tool**: `glob({"pattern": "benchmarks/*.yaml"})`
- **tool**: `bash({"command": "python -m pytest tests/ --tb=no -q 2>&1 | Select-Object -Last 5", "workdir": "D:\\Projects\\market-game-sim"})`


> [reasoning] I now have a complete picture. Let me run the existing tests to confirm the baseline, then start implementing.

Let me look at the benchmark config file BENCH-001 to verify the constants.
让我检查一下 BENCH-001 的 config，并运行基准测试。

  <details><summary>tool output</summary>

  ```text
Found 1 file(s)

D:\Projects\market-game-sim\benchmarks\BENCH-001.yaml
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
- Specializ
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
........................................................................ [ 74%]
........................................................................ [ 86%]
........................................................................ [ 98%]
.......                                                                  [100%]
583 passed in 1.54s
  ```
  </details>

## assistant · 2026-08-02T12:11:04Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\benchmarks\\BENCH-001.yaml"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\docs\\contracts\\matching.md"})`

583 个测试通过。让我阅读 BENCH-001 config 和 matching contract，以完全理解 MULT。

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\benchmarks\BENCH-001.yaml</path>
<type>file</type>
<content>
1: # BENCH-001：性能基准配置（加密式制度）
2: #
3: # 用途：PRD / KPI-004、v0.1 / NFR-003 的性能门槛载体。
4: # 这是**性能基准**，不是研究基准——参与者构成只求覆盖代码路径，不追求统计特征。
5: # 研究用的基准市场配置由 0.1.2 实验协议定义（待制定，见 0.1.2 T002/T003）。
6: #
7: # 第一版只有加密式一套制度（v0.1 / D-1）。股票式配置随收盘、T+2、熔断一并后移。
8: #
9: # 状态：规格产物。字段名构成实现契约，实现时如需调整须同步本文与 event-schema.md。
10: # 本配置在首次实现完成后须按实测吞吐量校准一次（见 README.md §4）。
11: #
12: # 数值书写约定（ADR-001 §2）：所有非整数领域量写成带引号的字符串，由 Decimal 解析。
13: # 裸写 0.01 会被 yaml.safe_load 解析为 float，使「禁止 float 中转」在第一步失效。
14: # 整数（计数、纳秒时长、种子、万分数、分位点）无精度问题，照常书写。
15: 
16: benchmark_id: BENCH-001
17: 
18: # 两个版本号，含义完全不同，不得混用（P1-O04）：
19: #   config_schema_version —— 本 YAML 配置格式的版本，由基准运行器消费
20: #   event_schema_version  —— 事件日志格式版本，由内核写入 RUN_HEADER 并由验证器消费
2
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

## assistant · 2026-08-02T12:11:09Z

- **tool**: `grep({"output_mode": "content", "path": "D:\\Projects\\market-game-sim\\docs\\contracts\\agent-strategy.md", "pattern": "11.1|reserved|worst_long|worst_short|fee_part|margin_part"})`


> [reasoning] Now I have enough understanding. Let me also look at the agent-strategy §11.1 for reserved_units formula to understand case 7b fully.
让我查看 `agent-strategy.md` §11.1 以获取保留公式。

  <details><summary>tool output</summary>

  ```text
Found 11 match(es) in 1 file(s)

D:\Projects\market-game-sim\docs\contracts\agent-strategy.md
  462: ### 11.1 保证金占用：总占用口径
  464: `reserved_units` 的语义是**当前持仓与全部活动挂单在最坏情形下占用的保证金总额**
  469: worst_long  = position + Σ(所有活动买单数量)      # 全部买单成交
  470: worst_short = position − Σ(所有活动卖单数量)      # 全部卖单成交
  471: worst_qty   = max(|worst_long|, |worst_short|)
  476: margin_part = ceil(worst_qty × reservation_mark × initial_bp / 10000)
  479: # 费用上界分两段，缺任一段都会低估（见下方「fee_part 的两段」）
  484: fee_part      = fee_immediate + fee_resting
  486: reserved_units = margin_part + fee_part
  489: **`fee_part` 的两段**：候选单经预撮合后分成**立即成交**与**入簿剩余**两部分，
  514: - **持仓部分包含在内**——因此准入式**不得**再写成 `equity − reserved_units`

[Agent Usage Reminder]

You called a search/fetch tool directly without leveraging specialized agents.

REC
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:11:14Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\docs\\contracts\\agent-strategy.md", "limit": 70, "offset": 460})`

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\docs\contracts\agent-strategy.md</path>
<type>file</type>
<content>
460: ## 11. 挂单保证金占用与自成交
461: 
462: ### 11.1 保证金占用：总占用口径
463: 
464: `reserved_units` 的语义是**当前持仓与全部活动挂单在最坏情形下占用的保证金总额**
465: （含手续费上界），**不是「挂单额外占用的部分」**。这个口径与账户合同 §3.3 的准入式
466: 配套，两者必须一起读。
467: 
468: ```text
469: worst_long  = position + Σ(所有活动买单数量)      # 全部买单成交
470: worst_short = position − Σ(所有活动卖单数量)      # 全部卖单成交
471: worst_qty   = max(|worst_long|, |worst_short|)
472: reservation_mark = max(risk_mark,
473:                        所有活动及候选限价单的 price_ticks,
474:                        候选单预撮合得到的全部 maker 成交价)
475: 
476: margin_part = ceil(worst_qty × reservation_mark × initial_bp / 10000)
477: fee_rate    = max(taker_bps, maker_bps, 0)
478: 
479: # 费用上界分两段，缺任一段都会低估（见下方「fee_part 的两段」）
480: fe
…[truncated]
  ```
  </details>

## assistant · 2026-08-02T12:11:18Z


> [reasoning] Now I have full context. Let me also look at the existing `test_matching.py` structure for how it handles `compute_reserved_units` to understand the test patterns and see if there's an existing `__init__.py` for `tests/unit/ledger/`.

Let me also look at one OB vector test to see the postings assertion level.

Let me now plan the implementation.

## Understanding the scope

The task is **Phase 4** of milestone 0.1.1. I need to:

1. **T401**: Build `ledger/account.py` with `Account` dataclass + `AccountState` enum
2. **T402**: Implement `entry_notional` update algorithm (same-direction add, opposite close, flip)
3. **T403**: Implement `unrealized_pnl`, `equity`, `risk_equity`, `valuation_equity`, `margin_ratio_bp` methods on `Account`
4. **T404**: Fee computation with `round_fee` and `div_ceil`
5. **T405**: `TRADE_POSTING` × 2 with all 15 fields per posting
6. **T406**: C1/C2 per-event assertions (integer exact)
7. **T407**: Acceptance cases 1-5, 10 pass (integer-exact)
8. **T407b**: `reserved_units` 4 scenarios (case 7b)
9. **T408**: PnL bridge per-event residual = 0 (using `valuation_mark`)

## Key implementation plan

### 1. `ledger/account.py` (T401-T403)

```python
@dataclass
class Account:
    agent_id: str
    wallet_units: int
    position_units: int
    entry_notional_units: int
    reserved_units: int
    realized_pnl_units: int
    state: AccountState
    liquidation_generation: int
    chain_id: str | None
    chain_depth: int
    
    def unrealized_pnl(mark_ticks: int) -> int:
        return self.position_units * mark_ticks - self.entry_notional_units
    
    def equity(mark_ticks: int) -> int:
        return self.wallet_units + self.unrealized_pnl(mark_ticks)
    
    def risk_equity(risk_mark_ticks: int) -> int:
        return self.equity(risk_mark_ticks)
    
    def valuation_equity(valuation_mark_half_ticks: int) -> int:
        # valuation_mark is in half_ticks, so convert to ticks
        return self.equity(valuation_mark_half_ticks // 2)  # ???
```

Wait - the valuation_mark is stored as half_ticks because the mid could be a half-tick. So `valuation_mark_half_ticks` is `bb + ba` (an even number when prices are integers... but could be odd if bb and ba differ by an odd amount? Actually prices are integers so bb+ba is always an integer; if bb=100 and ba=101, the mid is 100.5 which needs half-tick representation: 201 half_ticks). So to convert half_ticks to ticks: `half_ticks // 2` would truncate. But the mid could be a half-tick value (e.g. 100.5), so we need to handle this carefully.

Actually looking at the contract:
```text
unrealized_pnl(mark) = position_units × mark − entry_notional_units
```

Here `mark` is in ticks. For `valuation_mark`, it can be a half-tick value. So we need:
```text
unrealized_pnl(valuation_mark_half_ticks) = position_units × (valuation_mark_half_ticks / 2) − entry_notional_units
```

But this involves division. The cleanest integer formulation:
```text
unrealized_pnl_half = position_units × valuation_mark_half_ticks − 2 × entry_notional_units
# This gives PnL in half-cash-units (twice the actual value)
```

Hmm, but equity should be in cash units. Let me re-read.

Looking at `metrics-dictionary.md`:
- `equity = wallet + position × vm − entry_notional`

All in consistent units. If `vm` is in half-ticks, then `position × vm` is in (position_units × half-ticks). For this to be in cash units, we need to divide by 2 (since 1 tick = 2 half-ticks, and cash_unit = tick_size × min_quantity / MULT).

Wait, let me think again. The unit conversion is:
- `notional_cash_units = price_ticks × quantity_units × MULT`

So `price_ticks × quantity_units` gives `notional_cash_units / MULT`. For MULT=1000:
- `price_ticks × quantity_units = notional_cash_units / 1000`

So if we want `position × mark` in cash units, we need `position_units × mark_ticks × MULT`.

But the contract formula says:
```text
unrealized_pnl(mark) = position_units × mark − entry_notional_units
```

This is treating `position_units × mark` as being in the same units as `entry_notional_units`. But `entry_notional_units` is in cash units (per the table in acceptance-vectors.md case 1: `entry_delta=+100000000000` for position=+10000 at price=10000 ticks).

Let me verify: Case 1: A buys 10 @ 100. In units: qty=10000 (10/0.001), price=10000 ticks (100/0.01).
- `entry_delta = +100000000000` (1e11)
- `position_delta = +10000`
- `MULT = 1000`
- `notional_cash_units = price_ticks × qty_units × MULT = 10000 × 10000 × 1000 = 1e11` ✓

So `entry_notional_units` IS `notional_cash_units = price × qty × MULT`.

Now `unrealized_pnl(mark) = position_units × mark − entry_notional_units`:
- This must be: `position_units × mark_ticks × MULT − entry_notional_units`
- Or equivalently: `notional(position, mark) − entry_notional`

So the formula uses `MULT` implicitly. The "mark" in the contract formula is in cash units per position unit, i.e., `mark_ticks × MULT`.

Actually no. Let me re-read more carefully. The formula says `position_units × mark`. If `mark` is in ticks, then `position_units × mark_ticks` is in (qty × ticks) units, not cash units. To get cash units we multiply by MULT.

So the actual implementation must be:
```python
def unrealized_pnl(self, mark_ticks: int, mult: int) -> int:
    return self.position_units * mark_ticks * mult - self.entry_notional_units
```

OR the formula is implicitly using a "mark in cash-per-position-unit" which is `mark_ticks × MULT`.

Hmm, let me check case 2: After ②, A has position=0, entry=0, wallet=1100 (in human). The integer projection says A `(+10000000000,−10000,−100000000000)` meaning `wallet_delta=+1e10, position_delta=-1e4, entry_delta=-1e11`.

Wait, `wallet_delta=+1e10`? wallet was 1000 (human) = 1e11 cash_units (1000 / 1e-8 = 1e11). So wallet went from 1e11 to 1.1e11, delta = +1e10. That matches "+100" human = 100 / 1e-8 = 1e10 cash_units. ✓

So for unrealized_pnl: `position_units × mark − entry_notional_units`. For A after ②: position=0, so unrealized_pnl = -entry = 0 (since entry=0). For C: position=+10000, entry=+110000000000, mark=11000 ticks (110.00). 
- `unrealized_pnl = 10000 × 11000 × MULT − 110000000000 = 10000 × 11000 × 1000 − 1.1e11 = 1.1e11 − 1.1e11 = 0` ✓ (since C just opened at 110, mark=110, no PnL yet)

For B: position=-10000, entry=-100000000000, mark=11000.
- `unrealized_pnl = -10000 × 11000 × 1000 − (-1e11) = -1.1e11 + 1e11 = -1e10` (= -100 human)
- `equity = wallet + unrealized = 1000 + (-100) = 900` (human) ... but the table says B equity... let me check. Actually the table only gives equity for case 1. For case 2 it gives margin_ratio: B `8181 bp`.
- `margin_ratio_bp = risk_equity × 10000 / notional = 900 × 10000 / (10000 × 11000 / 100) = 900 × 10000 / 110000 = 818.18...` 

Wait that's not matching. Let me recompute in integer.
- B: position=-10 (human) = -10000 units, entry=-1000 (human) = -1e11 cash_units, wallet=1000 (human) = 1e11 cash_units, risk_mark=110 (human) = 11000 ticks.
- `notional = |position| × risk_mark × MULT = 10000 × 11000 × 1000 = 1.1e11` cash_units (= 1100 human)
- `unrealized_pnl = position × mark × MULT − entry = (-10000) × 11000 × 1000 − (-1e11) = -1.1e11 + 1e11 = -1e10` (= -100 human)
- `risk_equity = wallet + unrealized = 1e11 + (-1e10) = 9e10` (= 900 human)
- `margin_ratio_bp = floor(risk_equity × 10000 / notional) = floor(9e10 × 10000 / 1.1e11) = floor(9e14 / 1.1e11) = floor(8181.81...) = 8181` ✓

So the implementation needs `MULT`. The `unrealized_pnl(mark_ticks)` method needs to know MULT.

But the contract says `unrealized_pnl(mark) = position_units × mark − entry_notional_units`. This is treating `mark` as already being in "cash per position unit" units = `mark_ticks × MULT`. 

I think the cleanest approach is: the method takes `mark_ticks` and the Account stores or is passed `mult`. Or we make MULT a parameter.

Actually, looking more carefully at the formula and the "integer projection" table: it seems the convention is that `mark` in the formula is `mark_ticks × MULT` (cash-per-position-unit). But that's awkward.

Let me look at how the existing code uses `notional`:
```python
notional = maker.price_ticks * fill_qty  # in matching.py
```

Wait, that's `price_ticks × qty_units` WITHOUT the MULT! And the schema field is `notional_cash_units`. Let me check... Actually the current matching.py has:
```python
notional = maker.price_ticks * fill_qty
return {
    ...
    "notional_cash_units": notional,
    "maker_fee_cash_units": 0,
    "taker_fee_cash_units": 0,
    ...
```

So currently `notional_cash_units = price_ticks × qty_units` (no MULT). But the acceptance-vectors §1 says `notional_cash_units = price_ticks × |qty_units| × 1000`.

So the current code is WRONG (Phase 3 stub with no real fee logic). I need to fix this to include MULT.

OK so my Account methods need MULT. The cleanest way: pass `mult` as a parameter to the methods, OR store `mult` on the Account. Since Account is a dataclass and MULT is a market-level constant (same for all accounts in a run), I'll pass it as a parameter.

Actually, looking at the contract formula again: `unrealized_pnl(mark) = position_units × mark − entry_notional_units`. If we interpret `mark` as `mark_ticks × MULT` (i.e., "mark in cash-per-position-unit"), then the formula works directly. But that's a weird interpretation.

Let me re-read the contract §2.2:
```text
unrealized_pnl(mark) = position_units × mark − entry_notional_units
```

And §2.1:
```text
entry_notional += Δpos × price
```

So `entry_notional` is accumulated as `Δpos × price`. If `price` is in ticks and `Δpos` in units, then `entry_notional` is in (units × ticks). But we said `entry_notional_units` is in cash_units...

There's an implicit `MULT` factor. The contract is written in "human-readable" form where `price` implicitly includes the conversion. In implementation, we need to be explicit.

I'll define the Account methods to take `mark_ticks` and `mult`:
```python
def unrealized_pnl(self, mark_ticks: int, mult: int) -> int:
    return self.position_units * mark_ticks * mult - self.entry_notional_units
```

Actually, to keep the contract formula clean and match the task description which says:
- `unrealized_pnl(mark_ticks)` -> int
- `equity(mark_ticks)` -> int
- `risk_equity(risk_mark_ticks)` -> int
- `valuation_equity(valuation_mark_half_ticks)` -> int
- `margin_ratio_bp(risk_mark_ticks)` -> int | None

The task says the methods take `mark_ticks`. So either MULT is stored on the Account, or it's a global, or the formula is different.

Wait — let me re-read the task:
> **T403** [账户 §2.2] [TDD] **未实现盈亏 + 双口径权益**:
> ```text
> unrealized_pnl(mark) = position_units × mark − entry_notional_units
> equity(mark)         = wallet_units + unrealized_pnl(mark)
> ```

And then:
> Compute these as methods on `Account`:
> - `unrealized_pnl(mark_ticks)` -> int
> - `equity(mark_ticks)` -> int
> - `risk_equity(risk_mark_ticks)` -> int
> - `valuation_equity(valuation_mark_half_ticks)` -> int
> - `margin_ratio_bp(risk_mark_ticks)` -> int | None  (None when position == 0)

So the method signatures are given. The `mark_ticks` parameter... hmm. 

Looking at the acceptance vectors case 2: B has position=-10000, entry=-1e11, and margin_ratio_bp=8181. If `unrealized_pnl(mark_ticks=11000)` = `position × mark_ticks − entry` = `-10000 × 11000 − (-1e11)` = `-1.1e8 + 1e11` = `9.9e10`... that's not -1e10.

So the formula `position_units × mark_ticks` doesn't work directly. We need `position_units × mark_ticks × MULT`.

OK so I think the cleanest approach is:
1. Store `mult` on the Account (as a field), OR
2. Make the methods take `mult` as a second parameter, OR  
3. Define `mark_ticks` in the method signature to actually mean "mark in cash-per-position-unit" (i.e., `mark_ticks × MULT`)

Option 3 is confusing. Option 1 adds a non-domain field to the dataclass. Option 2 deviates from the task's method signatures.

Actually, wait. Let me re-read the task more carefully:

> **T403** ... Compute these as methods on `Account`:
> - `unrealized_pnl(mark_ticks)` -> int

Hmm, but the task also says:
> **Notional computation**:
> ```python
> MULT = 1000  # tick_size * min_quantity / cash_unit for BENCH-001
> notional_cash_units = price_ticks * quantity_units * MULT
> ```

So MULT is definitely needed. I think the best approach is to store `mult` on the Account as a field. It's a market constant but having it on the account makes the methods self-contained. Or... I could make it a module-level configurable.

Actually, looking at the task's world dict description:
> The handler's `world` dict now holds `{book, accounts: dict[agent_id, Account], exchange_fee_units: int, exchange_risk_pnl_units: int, config, market, last_ticks, last_valuation_mark_half_ticks}`.

So `config` and `market` are in the world. The matching handler can pass `mult` when calling account methods. But for the Account methods to be self-contained (as the task requires), I think storing `mult` on the Account is cleanest.

Wait, actually — I realize the issue. The contract formula `position_units × mark` is using "mark" in a unit where `position × mark` gives cash units directly. That means `mark` is in "cash per position unit" = `mark_ticks × MULT`. But the method parameter is named `mark_ticks`...

I think there's a slight ambiguity. Let me just store `mult` on the Account. It's the most practical solution. The Account dataclass can have a `mult` field that's set at construction.

Actually, let me reconsider. The task says:
> **All fields present in dataclass**, margin logic stays empty (0.1.2 fills). Build `src/market_game_sim/ledger/account.py` with `Account` dataclass + `AccountState` enum

The fields listed are: `wallet_units`, `position_units`, `entry_notional_units`, `reserved_units`, `realized_pnl_units`, `state`. Plus from §1: `liquidation_generation`, `chain_id`, `chain_depth`.

So `mult` is NOT one of the domain fields. I should NOT add it as a domain field. Instead, I'll pass it as a parameter.

Let me look at the task's method signatures again:
> - `unrealized_pnl(mark_ticks)` -> int

Hmm. But this can't work without MULT. Unless... the contract formula is actually using a different unit convention.

Wait, let me re-examine. Maybe `entry_notional_units` is NOT in cash_units but in (qty × ticks) units (i.e., "notional WITHOUT the MULT factor")?

Looking at case 1 integer projection:
> 1 成交 | A posting `(wallet_delta=0, position_delta=+10000, entry_delta=+100000000000)`

`entry_delta = +1e11`. If this is `price_ticks × qty_units = 10000 × 10000 = 1e8`, that's NOT 1e11. If it's `price_ticks × qty_units × MULT = 10000 × 10000 × 1000 = 1e11`, that IS 1e11. ✓

So `entry_notional_units` IS in cash_units (includes MULT).

And `notional_cash_units = price_ticks × qty_units × MULT = 1e11`. ✓

So for `unrealized_pnl = position × mark − entry_notional` to work with `mark` in ticks:
`position_units × mark_ticks × MULT − entry_notional_units`

The method needs MULT. I'll add `mult` as a parameter. The task's method signature `unrealized_pnl(mark_ticks)` is a simplification; I'll implement it as `unrealized_pnl(mark_ticks, mult)` or store mult.

Actually, you know what, let me just store `mult` on the Account. It's not a "domain field" per se, but it's a necessary piece of market context. I'll make it a field with a default. Or better: I'll make the methods take `mult` as a parameter, and the task's signature is just shorthand.

Hmm, but the task explicitly says "Compute these as methods on Account: unrealized_pnl(mark_ticks) -> int". Let me follow that literally but add mult as a second param. The task description is a guide, not a strict API spec. The tests I write will define the actual API.

Decision: methods take `mult` as a second parameter. `unrealized_pnl(mark_ticks, mult)`, `equity(mark_ticks, mult)`, etc. This keeps the Account pure (no market config stored on it) and the methods are self-contained given the mult parameter.

Actually wait — for `valuation_equity(valuation_mark_half_ticks)`, the valuation mark is in half-ticks. So:
```python
def valuation_equity(self, valuation_mark_half_ticks: int, mult: int) -> int:
    # vm in half-ticks; position × vm_half × MULT / 2 = position × vm_half × MULT // 2
    # But we need exact integer arithmetic
    return self.wallet_units + (self.position_units * valuation_mark_half_ticks * mult - 2 * self.entry_notional_units) // 2
```

Hmm, but division by 2 could lose a half-cash-unit. Let me think...

`unrealized_pnl = position × vm − entry_notional` where `vm` is in cash-per-position-unit.
`vm_cash_per_pos = vm_half_ticks × MULT / 2`
`unrealized_pnl = position × vm_half_ticks × MULT / 2 − entry_notional`

In integer: `position × vm_half_ticks × MULT` is always even? Let's see: `vm_half_ticks = bb + ba`. If both are even or both odd, sum is even. If one even one odd, sum is odd. Prices are integers (ticks), so `bb` and `ba` are integers. Their sum can be odd (e.g., bb=100, ba=101, sum=201).

So `position × vm_half_ticks × MULT / 2` might not be an integer. But `entry_notional` is always an integer (cash units). So `unrealized_pnl` might be a half-cash-unit?

Actually no. The equity should always be in integer cash units because:
- `wallet` is integer
- `entry_notional` is integer  
- `position × mark` should be integer when mark is the actual mark (not half-tick)

The issue is only with `valuation_mark` which can be a half-tick. In that case, `position × vm_half / 2` could be a half-integer. But since we're computing equity for reporting, we need to handle this.

Looking at the PnL bridge formula in metrics-dictionary §5.2:
```text
equity = wallet + position × vm − entry_notional
```

And the examples use Decimal with half values (e.g., `vm_after=100.5`). So in the decimal world, equity can be a half-cash-unit.

But in integer world, we need to track half-cash-units. The cleanest way: compute equity in half-cash-units when using valuation_mark:
```python
def valuation_equity(self, valuation_mark_half_ticks: int, mult: int) -> int:
    # Returns equity in half-cash-units to preserve precision
    return 2 * self.wallet_units + self.position_units * valuation_mark_half_ticks * mult - 2 * self.entry_notional_units
```

Hmm but that changes the unit. Actually, I think for 0.1.1, we can just use integer division (truncate) since the PnL bridge test uses `valuation_mark` and checks residual = 0. If we truncate, the residual won't be exactly 0.

Let me look at the PnL bridge test requirement more carefully. The task says:
> **T408** [指标字典 §5.2] [TDD] **PnL 桥接逐事件残差为 0**, 用 `valuation_mark` (**不是** `risk_mark`).

And the bridge formula:
```text
Δequity = Spread + Impact + Revaluation + Funding − Fees
```

where:
- `Spread = signed_qty × (vm_before − trade_price)`
- `Impact = signed_qty × (vm_after − vm_before)`
- `Revaluation = position_before × (vm_after − vm_before)`

All these use `vm` which is in half-ticks. `signed_qty × (vm_before − trade_price)`: `vm_before` is half-ticks, `trade_price` is ticks. To subtract, convert: `trade_price_half = trade_price × 2`. Then `vm_before − trade_price_half` is in half-ticks. `signed_qty × half_ticks` is in (qty × half_ticks). To get cash units: `× MULT / 2`.

So the bridge naturally works in half-cash-units. If we compute everything in half-cash-units, the residual should be exactly 0 (no truncation).

Actually, I think the cleanest approach is:
- `equity(mark_ticks, mult)` returns cash units (integer, since mark_ticks is integer)
- `valuation_equity(valuation_mark_half_ticks, mult)` returns cash units, using integer division

But for the PnL bridge, we need half-cash-unit precision. So maybe I should compute the bridge in half-cash-units.

Let me think about this differently. The PnL bridge is:
```
Δequity = Spread + Impact + Revaluation + Funding − Fees
```

If I compute each term in half-cash-units (multiply everything by 2), then:
- `Spread_half = signed_qty × (vm_before_half − 2 × trade_price) × MULT`
- `Impact_half = signed_qty × (vm_after_half − vm_before_half) × MULT`
- `Revaluation_half = position_before × (vm_after_half − vm_before_half) × MULT`
- `Funding_half = 2 × funding` (0 for 0.1.1)
- `Fees_half = 2 ×
