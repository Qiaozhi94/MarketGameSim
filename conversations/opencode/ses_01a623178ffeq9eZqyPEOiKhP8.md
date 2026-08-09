---
tool: "opencode"
tool_name: "OpenCode"
session_id: "ses_01a623178ffeq9eZqyPEOiKhP8"
title: "Find TDD and exit-verification patterns (@explore subagent)"
project: "D:/Projects/market-game-sim"
model: "deepseek-v4-flash"
created_at: "2026-08-09T08:22:32Z"
updated_at: "2026-08-09T08:26:29Z"
tokens_input: 185912
tokens_output: 6223
cost: 0.0
parent_id: "ses_01a6d8622ffei5cBRUTyC14Unq"
---

# Find TDD and exit-verification patterns (@explore subagent)

## user · 2026-08-09T08:22:32Z

I'm starting 0.1.3 development (task T001) for MarketGameSim at D:\Projects\market-game-sim. T001 is [TDD] — I must write failing tests first. I need to understand the project's existing test conventions and how 0.1.2's exit conditions were verified, so my new code matches patterns.

GOAL: Learn the test/verification conventions so my T001 work is idiomatic and integrates cleanly.

DOWNSTREAM: I'll write new tests + a verifier module. I need to know naming conventions, fixtures, directory layout, and how "exit condition" checks are structured.

FIND AND REPORT:
1. How tests are organized (tests/unit, tests/integration, tests/property) — give the layout and an example of each kind's structure/conventions.
2. How the 0.1.2 exit conditions (E1-E7, KPI-005/006/007/009/010/011) are verified in tests — search tests/ for "KPI", "chain_depth", "bridge", "validation", "acceptance", "exit". List the specific test files and what they assert.
3. The integration tests tests/integration/test_experiment.py, test_cross_process_determinism.py, test_verify_liquidation.py, test_cold_start.py — summarize what each covers and how they invoke the runner.
4. How deterministic/hash equality tests are done (tests/unit/rng/test_determinism.py, tests/integration/test_cross_process_determinism.py) — the pattern for asserting byte-identical summaries.
5. Any existing fixture/helper modules for building configs or running simulations in tests (conftest.py?).
6. Look at docs/experiments/0.1.2-e6-demonstration-run.md and docs/reviews/RETROSPECTIVE.md to see how 0.1.2 exit conditions were documented as achieved — summarize what evidence each E1-E7 maps to.

Report concrete file paths, function names, and patterns. Be thorough but skip unrelated files.
<!-- OMO_INTERNAL_INITIATOR -->

## assistant · 2026-08-09T08:22:32Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim"})`
- **tool**: `glob({"pattern": "tests/**/*.py"})`
- **tool**: `glob({"pattern": "tests/**/conftest.py"})`
- **tool**: `glob({"pattern": "docs/experiments/0.1.2*"})`
- **tool**: `glob({"pattern": "docs/reviews/*.md"})`


> [reasoning] Let me start by exploring the project structure and gathering the relevant files. Let me launch parallel searches.

Let me start by understanding the directory layout.
<analysis>
**Literal Request**: Find and report on test/verification conventions for MarketGameSim — layout of tests (unit/integration/property), how 0.1.2 exit conditions (E1-E7, KPIs) are verified in tests, summaries of 4 specific integration test files, determinism/hash-equality patterns, fixture/helper modules, and evidence of exit-condition achievement from docs.
**Actual Need**: Before writing T001 failing tests + verifier module, understand idiomatic test structure, naming, fixtures, and how "exit condition" verification is done so the new code matches patterns and integrates cleanly.
**Success Looks Like**: Concrete absolute paths, function names, assertion patterns, fixture/helper usage, and documented evidence mapping for E1-E7. Caller can start writing tests immediately without follow-up questions.
</analysis>

Let me start with parallel exploration of the layout and key files.

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim</path>
<type>directory</type>
<entries>
.claude/
.code-review-graph/
.coverage
.editorconfig
.git/
.github/
.gitignore
.pytest_cache/
.ruff_cache/
.sisyphus/
.specify/
benchmarks/
CLAUDE.md
code-review-report.md
conversations/
data/
docs/
pyproject.toml
README.md
specs/
src/
tests/
tools/

(23 entries)
</entries>
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
Found 73 file(s)

D:\Projects\market-game-sim\tests\integration\test_experiment.py
D:\Projects\market-game-sim\tests\unit\metrics\test_report.py
D:\Projects\market-game-sim\tests\unit\bench\test_runner.py
D:\Projects\market-game-sim\tests\unit\bench\test_leverage_seed.py
D:\Projects\market-game-sim\tests\unit\book\test_chain_cascade.py
D:\Projects\market-game-sim\tests\unit\bench\test_shock.py
D:\Projects\market-game-sim\tests\unit\experiment\test_config.py
D:\Projects\market-game-sim\tests\unit\ledger\test_acceptance_vectors.py
D:\Projects\market-game-sim\tests\integration\test_cross_process_determinism.py
D:\Projects\market-game-sim\tests\unit\bench\test_population.py
D:\Projects\market-game-sim\tests\unit\bench\test_coverage.py
D:\Projects\market-game-sim\tests\unit\bench\test_calib.py

…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
No files found
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
Found 4 file(s)

D:\Projects\market-game-sim\docs\experiments\0.1.2-exit-evidence-index.json
D:\Projects\market-game-sim\docs\experiments\0.1.2-e6-demonstration-run.md
D:\Projects\market-game-sim\docs\experiments\0.1.2-e6-demonstration-run.json
D:\Projects\market-game-sim\docs\experiments\0.1.2-market-validation-protocol.md
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
Found 1 file(s)

D:\Projects\market-game-sim\docs\reviews\RETROSPECTIVE.md
  ```
  </details>

## assistant · 2026-08-09T08:22:53Z

- **tool**: `glob({"pattern": "**/conftest.py"})`
- **tool**: `grep({"pattern": "KPI", "path": "D:\\Projects\\market-game-sim\\tests", "output_mode": "content", "head_limit": 60})`
- **tool**: `grep({"pattern": "exit|acceptance|chain_depth|bridge", "path": "D:\\Projects\\market-game-sim\\tests", "output_mode": "files_with_matches"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\pyproject.toml"})`


> [reasoning] No conftest.py found at tests/ level. Let me check for conftest.py anywhere, and look at the key files. Let me check the tests directory structure, pyproject.toml for test config, and search for KPI/exit conditions in tests.

Let me launch parallel reads and searches.
No `conftest.py` at `tests/` level. Let me check for conftest anywhere, read the key integration tests, and search for KPI/exit-condition references in tests.

  <details><summary>tool output</summary>

  ```text
No files found
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
Found 24 match(es) in 10 file(s)

D:\Projects\market-game-sim\tests\integration\test_experiment.py
  606: """T606 (KPI-005): build_study_report must surface a per-seed market
  638: """KPI-011 (PRD §13.4): build_study_report must surface a per-seed

D:\Projects\market-game-sim\tests\integration\test_verify_liquidation.py
  1: """§1.11 integration: real liquidation log → verify_log must pass (KPI-006/E7)."""
  56: the independent verifier including KPI-006 checks.
  95: # Explicit origin="" on non-agent orders so KPI-006 only checks LIQUIDATION path

D:\Projects\market-game-sim\tests\unit\test_verify.py
  104: """§1.8 (T506/KPI-006): regression coverage for ``_check_kpi006``.
  109: KPI-006-compliant -- so a log with mostly dangling
  274: assert "KPI-006" in result["detail"]
  281: "this s
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
Found 24 match(es) in 24 file(s)

D:\Projects\market-game-sim\tests\unit\test_verify.py

D:\Projects\market-game-sim\tests\unit\bench\test_shock.py

D:\Projects\market-game-sim\tests\unit\test_contract_sources.py

D:\Projects\market-game-sim\tests\unit\bench\test_coverage.py

D:\Projects\market-game-sim\tests\unit\bench\test_runner.py

D:\Projects\market-game-sim\tests\unit\bench\test_leverage_seed.py

D:\Projects\market-game-sim\tests\unit\book\test_chain_cascade.py

D:\Projects\market-game-sim\tests\unit\schema\test_registry_parity.py

D:\Projects\market-game-sim\tests\unit\schema\test_posting_union.py

D:\Projects\market-game-sim\tests\unit\book\test_liquidation_stale.py

D:\Projects\market-game-sim\tests\unit\schema\test_constraint_fixtures.py

D:\Projects\market-game-sim\tests\unit\bo
…[truncated]
  ```
  </details>

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
17:   # 固定到 minor 版本：CI 用 `pip install -e ".[dev]"` 每次拉最新，2026-08-09
18:   # 就因为0.15->0.16的默认行为变化（markdown内嵌代码块格式化默认启用）在没有
19:   # 任何本仓库代码变更的情况下把CI的ruff job搞红——linter版本漂移不该成为
20:   # CI失败的来源，锁定范围换取可重复性。
21:   "ruff>=0.16,<0.17",
22: ]
23: 
24: [tool.hatch.build.targets.wheel]
25: packages = ["src/market_
…[truncated]
  ```
  </details>

## assistant · 2026-08-09T08:23:15Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\tests\\integration\\test_experiment.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\tests\\integration\\test_cross_process_determinism.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\tests\\integration\\test_verify_liquidation.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\tests\\integration\\test_cold_start.py"})`


> [reasoning] There's no conftest.py anywhere. Let me look at the tests directory layout, and read the key integration test files, the determinism tests, and the metric tests. Let me also read the docs.

Let me read the 4 integration test files, the determinism tests, test_verify.py, test_validation.py, and the docs.
No `conftest.py` anywhere — so tests are self-contained with inline helpers. Let me read the key integration tests, determinism tests, verifier tests, and the docs.

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
<path>D:\Projects\market-game-sim\tests\integration\test_cross_process_determinism.py</path>
<type>file</type>
<content>
1: """T704 (0.1.2 附加门槛): cross-process determinism.
2: 
3: Verified this had zero test coverage: no existing test re-runs the same
4: config/seed and compares outputs, and CI's own comment
5: (.github/workflows/ci.yml) explicitly says the real cross-process,
6: different-PYTHONHASHSEED check "由 0.1.1 T602 / 退出条件 E4 负责" without
7: ever pointing at an implementation -- ``PYTHONHASHSEED=0`` in CI only makes
8: an existing ``hash()`` misuse reproducible within one run, it proves
9: nothing about cross-process reproducibility on its own (reference-machine.md
10: §3).
11: 
12: This spawns ``tools/determinism_probe.py`` as two real subprocesses with
13: different ``PYTHONHASHSE
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\tests\integration\test_verify_liquidation.py</path>
<type>file</type>
<content>
1: """§1.11 integration: real liquidation log → verify_log must pass (KPI-006/E7)."""
2: 
3: from __future__ import annotations
4: 
5: import json
6: 
7: from market_game_sim.book.matching import match_order
8: from market_game_sim.book.orderbook import Book
9: from market_game_sim.eventlog.bootstrap import (
10:     build_account_payload_from_accounts,
11:     build_book_payload,
12: )
13: from market_game_sim.kernel.runner import EventKernel
14: from market_game_sim.ledger.account import Account
15: from market_game_sim.verify import verify_log
16: 
17: MULT = 1000
18: CASH = 10**8
19: P100 = 10000
20: 
21: 
22: def _limit(oid: str, aid: str, side: str, price: int, qty: int, 
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\tests\integration\test_cold_start.py</path>
<type>file</type>
<content>
1: """T407: End-to-end cold-start verification.
2: 
3: Order of events in cold start (代理策略 §3.2):
4: 1. Market maker first observation
5: 2. Market maker places bilateral quotes
6: 3. Book has bid/ask
7: 4. Belief agent observes, decides
8: 5. Belief agent's order crosses the spread
9: 6. First trade happens
10: 7. risk_mark switches from initial_price to last
11: """
12: 
13: from __future__ import annotations
14: 
15: import pytest
16: 
17: from market_game_sim.agent.handler import (
18:     handle_agent_decide,
19:     handle_agent_observe,
20: )
21: from market_game_sim.agent.scheduler import AgentSpec
22: from market_game_sim.book.matching import match_order
23: from market_game_s
…[truncated]
  ```
  </details>

## assistant · 2026-08-09T08:23:34Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\tests\\unit\\rng\\test_determinism.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\tests\\unit\\test_verify.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\tests\\unit\\metrics\\test_validation.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\tools\\determinism_probe.py"})`


> [reasoning] Now let me read the determinism unit test, test_verify.py, test_validation.py, and the docs. Let me also check the tools/determinism_probe.py. And check tests for a helper/fixture pattern. There's no conftest, so helpers are inline per-file.

Let me read the remaining key files in parallel.
Now let me read the determinism unit test, verifier tests, market validation tests, and the docs.

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\tests\unit\rng\test_determinism.py</path>
<type>file</type>
<content>
1: """T602 (SC-002): Determinism across different PYTHONHASHSEED values."""
2: 
3: import os
4: import subprocess
5: import sys
6: 
7: from market_game_sim.book.simulator import run_simulation
8: from market_game_sim.ledger.account import Account
9: from market_game_sim.verify import digest_events
10: 
11: 
12: def _make_simulation() -> list[dict]:
13:     accounts = {
14:         "A": Account("A", 100000000000),
15:         "B": Account("B", 100000000000),
16:         "C": Account("C", 100000000000),
17:     }
18:     events = [
19:         {
20:             "event_type": "ORDER_ARRIVAL",
21:             "timestamp": 100,
22:             "agent_id": "B",
23:             "order_id": "o1"
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\tests\unit\test_verify.py</path>
<type>file</type>
<content>
1: """T603 (SC-006): Independent verifier tests."""
2: 
3: import json
4: 
5: from market_game_sim.book.simulator import run_simulation
6: from market_game_sim.ledger.account import Account
7: from market_game_sim.verify import verify_log
8: 
9: 
10: def _sim_log(abort: bool = False) -> list[dict]:
11:     accounts = {
12:         "A": Account("A", 100000000000),
13:         "B": Account("B", 100000000000),
14:     }
15:     events = [
16:         {
17:             "event_type": "ORDER_ARRIVAL",
18:             "timestamp": 100,
19:             "agent_id": "B",
20:             "order_id": "o1",
21:             "action": "SUBMIT",
22:             "side": "SELL",
23:             "order_type": "LIMI
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\tests\unit\metrics\test_validation.py</path>
<type>file</type>
<content>
1: """T606 (KPI-005): market validation matrix tests.
2: 
3: Covers every branch of ``metrics/validation.py`` with a positive (expected
4: verdict reached) and a negative (opposite verdict/NOT_APPLICABLE) case, per
5: CLAUDE.md's regression-test rule.
6: """
7: 
8: from __future__ import annotations
9: 
10: import math
11: import random
12: 
13: from market_game_sim.metrics.liquidation import LiquidationMetrics
14: from market_game_sim.metrics.sampling import ImpactSample, MarketSample
15: from market_game_sim.metrics.validation import (
16:     MAX_FILL_RATIO,
17:     MIN_SAMPLE_POINTS,
18:     MIN_TAKER_ORDERS,
19:     ValidationItem,
20:     _pearson,
21:     acf,
22:     apply_fam
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\tools\determinism_probe.py</path>
<type>file</type>
<content>
1: """T704 (0.1.2 附加门槛): cross-process determinism probe.
2: 
3: Runs a fixed small experiment and prints a JSON summary (event digest +
4: classification + liquidation metrics + study report) to stdout. Intended to
5: be invoked as a subprocess with different ``PYTHONHASHSEED`` values so a
6: test can assert the two outputs are byte-identical -- proving reproducibility
7: does not accidentally depend on Python's per-process hash randomization
8: (benchmarks/reference-machine.md §3: 摘要哈希一律使用 hashlib, 不得依赖内置
9: ``hash()``/``set``/``dict`` 遍历顺序).
10: 
11: Usage::
12: 
13:     PYTHONHASHSEED=0 python tools/determinism_probe.py
14:     PYTHONHASHSEED=1 python tools/determinism_probe.py
15: 
16: Wall
…[truncated]
  ```
  </details>

## assistant · 2026-08-09T08:23:49Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\docs\\experiments\\0.1.2-e6-demonstration-run.md"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\docs\\experiments\\0.1.2-exit-evidence-index.json"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\docs\\reviews\\RETROSPECTIVE.md"})`
- **tool**: `glob({"pattern": "specs/v0.1-belief-testing-laboratory/0.1.3-robustness/**"})`


> [reasoning] Now let me read the docs: the e6-demonstration-run.md, the exit-evidence-index.json, and RETROSPECTIVE.md. Let me also look at the 0.1.3 spec/tasks to understand T001.

Let me read these in parallel.
Now let me read the docs for exit-condition evidence and the 0.1.3 spec/tasks for T001.

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\docs\experiments\0.1.2-e6-demonstration-run.md</path>
<type>file</type>
<content>
1: # E6 达标示范运行——KPI-005/007/010/011 联合验证
2: 
3: **性质**：这**不是**一次预注册的信念检验研究（没有走 `ExperimentProtocol` 三区
4: 流程，也不产出可外推的信念结论）。它是 0.1.2 退出条件 E6 要求的"在真实研究
5: 运行下"证据——证明 KPI-005/007/010/011 各自的产出机制不仅存在、有单测，而是
6: 能在一次真实（非 BENCH-001 性能基准、非 `bench/leverage_seed.py` 人工预置杠杆
7: 账户）的配对实验上一起正确运行。
8: 
9: **运行日期**：2026-08-09　**原始结果**：
10: [`0.1.2-e6-demonstration-run.json`](0.1.2-e6-demonstration-run.json)
11: 
12: ## 配置
13: 
14: - 参与者：2 个做市商 + 20 个散户（真实决策循环，非人工预置仓位）
15: - 单维度对照（方法论 §10.5）：`leverage_tier` control=3x，treatment=10x，
16:   其余全部字段逐位相同（`check_paired_parity` 静态校验 + `check_shared_
17:   randomness_parity` 动态校验均通过）
18: - 5 个随机种子（`[1,2,3,4,5]`），`max_transactions=30000`
19: - 通过 `run_
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\docs\experiments\0.1.2-exit-evidence-index.json</path>
<type>file</type>
<content>
1: {
2:   "_meta": {
3:     "purpose": "T705: 0.1.2 退出检查清单（E1-E7 + 附加门槛）的机器可读证据索引",
4:     "spec": "specs/v0.1-belief-testing-laboratory/0.1.2-leverage-and-first-experiment/tasks.md",
5:     "generated": "2026-08-08",
6:     "last_updated": "2026-08-09",
7:     "generated_by": "第17轮修复报告 docs/reviews/2026-08-08j-v0.1.2-fix-verification-round17.md 之后的核查；第18/19/20/21轮补充E5标定与E6达标",
8:     "overall_status": "0.1.2 全部退出条件（E1-E7 + 附加门槛）已勾选，2026-08-09 达成",
9:     "note": "status=met 表示已有可重复运行的测试/机制证据；status=not_met 表示机制可能存在但尚无真实运行的达标结果；status=partially_met 表示复合条件中部分子项已达标、部分仍未（见该条目notes的具体拆分）；本索引只记录已验证事实，不预判未做的工作"
10:   },
11:   "items": [
12:     {
13:       "id": "E1",
14:       "d
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\docs\reviews\RETROSPECTIVE.md</path>
<type>file</type>
<content>
1: # 检视复盘记录
2: 
3: > 每完成一个检视循环(`stop_condition_met` 全部满足)追加一条,不建立新文件。
4: > 循环进行中的报告见同目录 `CURRENT-doc.md` / `CURRENT-code.md`(按
5: > `report_type` 分文件,同一时间可以有多个并行);循环内的逐轮细节不再保留
6: > 独立文件,需要时用 `git log --follow -p` 在本文件历史或已删除的
7: > `docs/reviews/2026-08-*` 提交记录里找回。
8: 
9: ---
10: 
11: ## 循环 0: 0.1.1 方向重构与设计文档检视
12: 
13: - **report_type**: doc-review
14: - **周期**: 2026-07-31 → 2026-08-02(37章/轮,含首次检视+多轮复审)
15: - **收尾状态**: 0.1.1 全面 Go;除 P1-U01 外全部关闭
16: - **测试覆盖变化**: 校验器测试由 3 个(全 happy path)扩为 23 个(20 个负向变异)
17: 
18: **遗留一条故意保持开放的项,需要在后续里程碑主动捡回来**:
19: 
20: | ID | 标题 | 严重度 | 分类 | 根因/症状 | 来源 | 状态 | 修复方案 | 回归测试 | 首次出现轮次 | 修复轮次 | 模式标签 |
21: |---|---|---|---|---|---|---|---|---|---|---|---|
22: | P1-U
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
Found 2 file(s)

D:\Projects\market-game-sim\specs\v0.1-belief-testing-laboratory\0.1.3-robustness\tasks.md
D:\Projects\market-game-sim\specs\v0.1-belief-testing-laboratory\0.1.3-robustness\spec.md
  ```
  </details>

## assistant · 2026-08-09T08:24:03Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\specs\\v0.1-belief-testing-laboratory\\0.1.3-robustness\\tasks.md"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\tests\\property\\test_random_orders.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\tests\\unit\\ledger\\test_acceptance_vectors.py", "limit": 80})`


> [reasoning] Let me read the 0.1.3 tasks.md and spec.md to understand T001 specifically, plus check the verify.py source to understand verify_log return keys. Also let me look at the tests/unit/ledger/test_acceptance_vectors.py structure to understand the acceptance vector test convention (E1). And check the tests directory layout structure (no __init__ in integration and property). Let me check the property test and one acceptance vector test.

Let me read the 0.1.3 tasks.md (focus on T001), the acceptance vectors test header, and the property test.
Let me read the 0.1.3 tasks (T001), the acceptance-vectors test structure (E1), and the property test.

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\specs\v0.1-belief-testing-laboratory\0.1.3-robustness\tasks.md</path>
<type>file</type>
<content>
1: # 0.1.3：模型稳健性 · 任务拆解
2: 
3: **对应里程碑**：[`spec.md`](spec.md)  
4: **状态**：Ready（0.1.2 退出证据已达成；T001 仍需自动复核准入证据后才展开后续任务）
5: 
6: ## 约定
7: 
8: - 0.1.3 检验结论对模型选择的敏感性，不以“找出显著结果”为目标；
9: - 所有扫描、消融、替代映射和留出复核方案必须在读取对应结果前冻结；
10: - 带 `[TDD]` 的任务先写失败测试；同一 Phase 内可并行项标 `[P]`；
11: - 负结果、方向反转和仅在狭窄区域成立都属于有效产出，不得触发事后改假设。
12: 
13: ---
14: 
15: ## Phase 0：准入、基线冻结与稳健性协议
16: 
17: - [ ] **T001** `[0.1.2 退出清单]` `[TDD]` 建立 0.1.3 启动门：从 0.1.2 spec/机器真源
18:       生成并自动验证全部退出条件（当前 E1—E7，不得手抄范围）、完整 manifest、原始
19:       日志、市场验证矩阵和条件性结论均可读取且摘要匹配。
20: - [ ] **T002** `[方法论 §9.4/§10.3]` 冻结 0.1.2 基线：代码 commit、协议、配置、种子、
21:       行为映射和指标定义。后续变更必须产生新基线 ID，不得覆盖 0.1.2 结果。
22: - [ ] **T003** `[0.1.3
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\tests\property\test_random_orders.py</path>
<type>file</type>
<content>
1: """T605: Property test — random order flow with C1/C2 invariants.
2: 
3: Multiple seeds (3, 42, 99, 123) to cover diverse order patterns.
4: """
5: 
6: import random
7: 
8: from market_game_sim.book.simulator import run_simulation
9: from market_game_sim.ledger.account import Account
10: from market_game_sim.ledger.conservation import check_c1_c2
11: 
12: 
13: def _rand_events(n: int, seed: int = 42) -> list[dict]:
14:     rng = random.Random(seed)
15:     events: list[dict] = []
16:     for i in range(n):
17:         side = rng.choice(["BUY", "SELL"])
18:         price = rng.randint(50, 200)  # in absolute price, converted to ticks
19:         qty = rng.randint(1, 50)  # in absolut
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\tests\unit\ledger\test_acceptance_vectors.py</path>
<type>file</type>
<content>
1: """T407/T408: acceptance vectors 1-5, 10 + PnL bridge (acceptance-vectors.md).
2: 
3: Integer-exact assertions against §4 (integer projection table) and §3
4: (step-by-step expected state).  C1/C2 verified per-event by replaying
5: the postings.  PnL bridge residual verified per-event == 0 using
6: valuation_mark (metrics-dictionary §5.2).
7: 
8: BENCH-001: MULT=1000, cash_unit=1e-8.
9:   price 100.00 -> 10000 ticks ; qty 10 -> 10000 units ; cash 1000 -> 1e11.
10: """
11: 
12: from __future__ import annotations
13: 
14: from typing import Any
15: 
16: from market_game_sim.book.matching import match_order
17: from market_game_sim.book.orderbook import Book
18: from market_gam
…[truncated]
  ```
  </details>

## assistant · 2026-08-09T08:24:19Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\verify.py"})`
- **tool**: `grep({"pattern": "T001|准入|启动门|0.1.2 退出", "path": "D:\\Projects\\market-game-sim\\specs\\v0.1-belief-testing-laboratory\\0.1.3-robustness\\spec.md", "output_mode": "content"})`
- **tool**: `glob({"pattern": "tests/**/__init__.py"})`


> [reasoning] I now have a very comprehensive picture. Let me verify the verify_log return keys and check the src/verify.py structure briefly to understand what a verifier module looks like (since T001 involves building a verifier module). Also check the 0.1.3 spec.md for the T001 "准入" details. Let me check the verify.py source and the spec.md quickly.

Let me also confirm test directory structure — check for __init__.py in tests/integration and tests/property (not present in glob results for integration/property - they had no __init__.py listed; only unit has __init__.py). Actually glob showed no __init__.py in tests/integration or tests/property. So integration and property are flat without packages. Unit has __init__.py in each subdir.

Let me quickly check verify.py source and spec.md for T001 details.
Let me examine the verifier source and the 0.1.3 spec's T001 准入 detail, plus check the tests dir structure for `__init__.py` placement.

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
Found 1 match(es) in 1 file(s)

D:\Projects\market-game-sim\specs\v0.1-belief-testing-laboratory\0.1.3-robustness\spec.md
  6: **状态**：Ready（0.1.2 退出证据已达成；实现从 T001 自动复核准入证据开始）
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
Found 9 file(s)

D:\Projects\market-game-sim\tests\unit\bench\__init__.py
D:\Projects\market-game-sim\tests\unit\experiment\__init__.py
D:\Projects\market-game-sim\tests\unit\metrics\__init__.py
D:\Projects\market-game-sim\tests\unit\ledger\__init__.py
D:\Projects\market-game-sim\tests\unit\book\__init__.py
D:\Projects\market-game-sim\tests\unit\schema\__init__.py
D:\Projects\market-game-sim\tests\unit\eventlog\__init__.py
D:\Projects\market-game-sim\tests\unit\kernel\__init__.py
D:\Projects\market-game-sim\tests\unit\config\__init__.py
  ```
  </details>

## assistant · 2026-08-09T08:24:34Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\.github\\workflows\\ci.yml"})`


> [reasoning] I now have all the information I need. Let me verify the src directory layout for the verifier module placement (to know where a 0.1.3 verifier would live) and check CI workflow for the test commands. Let me quickly check the src structure and .github/workflows/ci.yml.

Actually, I have enough. Let me do a quick check on the src tree and CI for completeness of the reporting.
Let me confirm the source tree layout and CI test config for completeness.

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim</path>
<type>directory</type>
<entries>
__init__.py
__pycache__/
agent/
bench/
book/
config/
eventlog/
experiment/
hook/
kernel/
ledger/
metrics/
rng/
schema/
verify.py

(15 entries)
</entries>
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\.github\workflows\ci.yml</path>
<type>file</type>
<content>
1: name: CI
2: 
3: on:
4:   push:
5:     branches: [main]
6:   pull_request:
7: 
8: # 同一分支的新提交取消仍在跑的旧任务，避免排队浪费。
9: concurrency:
10:   group: ${{ github.workflow }}-${{ github.ref }}
11:   cancel-in-progress: true
12: 
13: # 供应链加固：本工作流只读仓库，不需要写权限。
14: permissions:
15:   contents: read
16: 
17: jobs:
18:   # 真源自校验放在最前，且【不安装任何依赖】——它只用标准库。
19:   # 两份机器真源自相矛盾时，后面的 lint 与测试都没有意义，因此这一步失败即中止。
20:   contract-sources:
21:     name: 真源自校验
22:     runs-on: ubuntu-latest
23:     steps:
24:       - uses: actions/checkout@v7
25:       - uses: actions/setup-python@v7
26:         with:
27:           python-version: "3.11"
28:       - name: 校验 event_fields.json 与 traceability.json
29:         run: python tools/vali
…[truncated]
  ```
  </details>

## assistant · 2026-08-09T08:24:50Z


> [reasoning] I have everything I need. Let me compose the structured report. Let me also confirm the digest_events usage pattern and verify the `tests/integration` and `tests/property` have no `__init__.py` (confirmed — only unit subdirs have them).

Now I'll compose the final report addressing all 6 questions.
I have everything needed. Here is the complete report.

<results>
<files>
- D:\Projects\market-game-sim\pyproject.toml - test config: `testpaths=["tests"]`, `addopts="-ra --strict-markers"`; ruff `line-length=100`, `extend-exclude=["*.md"]`
- D:\Projects\market-game-sim\tests\unit\test_verify.py - **the model for T001's verifier tests** (KPI-006/009 regression via `verify_log`)
- D:\Projects\market-game-sim\tests\integration\test_verify_liquidation.py - real-kernel liquidation log → `verify_log` (E7/KPI-006)
- D:\Projects\market-game-sim\tests\integration\test_experiment.py - experiment runner wiring + KPI-005/011 report assertions (E3/E6)
- D:\Projects\market-game-sim\tests\integration\test_cross_process_determinism.py - byte-identical cross-process determinism (附加门槛/E4)
- D:\Projects\market-game-sim\tests\integration\test_cold_start.py - end-to-end kernel dispatch pipeline (T407)
- D:\Projects\market-game-sim\tests\unit\rng\test_determinism.py - in-process + cross-PYTHONHASHSEED digest equality (E4/T602)
- D:\Projects\market-game-sim\tests\unit\metrics\test_validation.py - KPI-005 six-item matrix, positive+negative per branch
- D:\Projects\market-game-sim\tests\unit\ledger\test_acceptance_vectors.py - E1 ten integer-exact acceptance vectors
- D:\Projects\market-game-sim\tests\property\test_random_orders.py - property/random-order pattern
- D:\Projects\market-game-sim\tools\determinism_probe.py - subprocess probe emitting JSON summary used by determinism test
- D:\Projects\market-game-sim\src\market_game_sim\verify.py - `verify_log`, `digest_events`, `check_causal_references` — the existing independent verifier T001 builds on
- D:\Projects\market-game-sim\docs\experiments\0.1.2-exit-evidence-index.json - machine-readable E1-E7 + 附加门槛 evidence index
- D:\Projects\market-game-sim\docs\experiments\0.1.2-e6-demonstration-run.md - E6 KPI-005/007/010/011 real-run evidence
- D:\Projects\market-game-sim\docs\reviews\RETROSPECTIVE.md - how E1-E7 were verified; the "marked-done-not-implemented" failure pattern to avoid
- D:\Projects\market-game-sim\specs\v0.1-belief-testing-laboratory\0.1.3-robustness\tasks.md - **T001 spec** (lines 17-19): gate from 0.1.2 exit list + manifests + raw logs + matrix + conditional conclusion all readable & digest-matched
</files>

<answer>

## 1. Test layout & conventions

Three top-level dirs (only `unit` has package `__init__.py`; `integration`/`property` are flat — no `__init__.py`, so integration/property tests are independent modules):

```
tests/
  unit/            # one __init__.py per subpackage (book/, ledger/, metrics/, ...)
    ledger/test_acceptance_vectors.py    (E1)
    metrics/test_validation.py           (KPI-005)
    metrics/test_report.py               (KPI-011, E4)
    metrics/test_liquidation.py          (E2)
    rng/test_determinism.py              (E4)
    test_verify.py                       (E7/KPI-006/009)
  integration/     # flat, no __init__ — real kernel/runner end-to-end
    test_experiment.py, test_cross_process_determinism.py,
    test_verify_liquidation.py, test_cold_start.py
  property/        # flat — randomized order flow invariants
    test_random_orders.py
```

Conventions observed everywhere:
- **Docstring first line = the task id + requirement**, e.g. `"""T603 (SC-006): Independent verifier tests."""`, `"""T606 (KPI-005): market validation matrix tests."""`. T001 files should follow `"""T001 (0.1.2 退出清单): ..."""`.
- **Module-level `_helper` functions** build fixtures inline (no `conftest.py` exists anywhere in the repo — verified via glob). E.g. `_mm_spec()`, `_belief_spec()`, `_limit()`, `_run()`, `_samples()`.
- **Positive AND negative cases per branch** (CLAUDE.md regression rule): each verdict has both a pass test and a fail/NOT_APPLICABLE test (see `test_validation.py`).
- **Multi-record batch cases** required for shared-scan logic (see `test_verify_liquidation.py` two-account batch, lines 125-208).
- Class grouping for related regressions: `class TestVerify`, `class TestKpi006Regression`, `class TestKpi009Regression` with `@staticmethod` fixture builders.

Unit example (`test_validation.py`): pure-function inputs built by `_samples()`, asserts `item.verdict == "PASS"/"FAIL"/"NOT_APPLICABLE"`. Integration example (`test_cold_start.py`): `EventKernel.bootstrap(...)` + `kernel.enqueue(...)` + `kernel.run(_dispatch, world, max_transactions=N)`, asserts `kernel.terminated == "COMPLETED"` and final world/book state. Property example (`test_random_orders.py`): seeded `random.Random(seed)` over several seeds asserting C1/C2 invariants and strictly-increasing log keys.

## 2. How 0.1.2 exit conditions are verified in tests

| Exit | Tests that assert it | What they assert |
|---|---|---|
| **E1** (ten acceptance vectors) | `tests/unit/ledger/test_acceptance_vectors.py` — classes `TestCase1SamePriceOpen` ... `TestCase10Funding` | Integer-exact expected values from `acceptance-vectors.md` tables |
| **E2** (liquidation metrics) | `tests/unit/metrics/test_liquidation.py::test_margin_call_pending_liquidation_counted_in_chain_depth`, `..._liquidation_volume_ratio_computes_correctly`, `..._bankruptcy_total_counts_only_breached_not_pending` | `compute_liquidation_metrics` chain_depth_counts / volume ratio / bankruptcy counts |
| **E3** (config-hash traceability) | `tests/integration/test_experiment.py::test_run_paired_comparison_carries_traceable_config_hashes` | `comparison["control_config_hash"] == compute_config_hash(control)`, distinct for distinct configs |
| **E4** (two-part report) | `tests/unit/metrics/test_report.py` | `build_endpoint_part` + `build_continuous_part` |
| **E5** (bench coverage) | `tests/unit/bench/test_runner.py::TestCalibratedFullScale`, `tests/unit/book/test_chain_cascade.py` | calibrated-coverage run matches golden counts; chain_depth wiring |
| **E6** (KPI-005/007/010/011) | `tests/integration/test_experiment.py::test_build_study_report_includes_market_validation_matrix` (six items, all NOT_APPLICABLE on toy run) + `..._includes_zero_sum_declaration` (residual==0, "不是研究发现" text, per-agent pnl); `tests/unit/metrics/test_validation.py` (matrix branches); `tests/unit/metrics/test_report.py` (KPI-011) | `build_study_report` surfaces `market_validation.per_seed` and `zero_sum` |
| **E7** (KPI-006 chain + KPI-009 per-event) | `tests/unit/test_verify.py::TestKpi006Regression` (per-order chain, deeper hops, same-transaction_seq) and `TestKpi009Regression` (corrupt `price_ticks` → `"KPI-009"` in `result["detail"]`); `tests/integration/test_verify_liquidation.py` | `verify_log()` returns `{"success":..., "error":"TI-5", "detail":..., "kpi006_agent_covered":True, "kpi006_liquidation_covered":True, "kpi009_bridge_ok":True}`; fail with `"KPI-006"`/`"KPI-009"` in `detail` |

Note: `verify_log` (in `src/market_game_sim/verify.py`) is the existing **independent verifier** — it reconstructs state from a log without importing kernel/ledger, returns `{"success", "error", "detail", "c1_pass", "causal_chain_pass", "kpi006_*_covered", "kpi009_bridge_ok"}`, and exposes pure helpers `digest_events(records)` (blake2b) and `check_causal_references(events)`. **T001's "verifier module" should extend/match this pattern.**

## 3. The four integration tests

- **`test_experiment.py`** (697 lines): drives `experiment/runner.py` — `run_one(config, protocol=...)`, `run_multi_seed(cfg, seeds)`, `run_paired(control, treatment, seeds, treatment_field="leverage_tier")`, `build_study_report`, `build_market_validation_report`, `check_paired_parity`, `check_shared_randomness_parity`. Uses dataclass `replace(...)` to vary one field; `monkeypatch` to force conservation/causal failures and surface `TI-3`/`TI-1`. Also covers KPI-005/011 report surfaces.
- **`test_cross_process_determinism.py`**: spawns `tools/determinism_probe.py` as two real subprocesses with `PYTHONHASHSEED="0"` vs `"1"` and asserts `out_a == out_b` (byte-identical); negative guard `test_output_is_not_trivially_empty`; `test_event_digests_differ_between_the_two_seeds` sanity check.
- **`test_verify_liquidation.py`**: builds a real liquidation scenario through `EventKernel` + `match_order`, writes a `RUN_HEADER`+records+`RUN_TRAILER` JSONL to `tmp_path`, then asserts `verify_log(log_path)["success"]` and `kpi006_liquidation_covered`. The batch test (`..._multi_account_same_batch_passes_verify`) asserts each LIQUIDATION order's `decision_event_id` references its own `MARGIN_CALL`.
- **`test_cold_start.py`**: end-to-end `_dispatch` routing (ORDER_ARRIVAL→`match_order`, AGENT_OBSERVE→`handle_agent_observe`, AGENT_DECIDE→`handle_agent_decide`) through `EventKernel`; asserts market-maker first-quote best_bid/ask, first-trade flips `risk_mark`, causal event ordering `AGENT_DECIDE < ORDER_ARRIVAL < TRADE_SETTLE`, and order-independence of enqueue sequence.

## 4. Determinism / hash-equality pattern

Two levels:
- **In-process** (`tests/unit/rng/test_determinism.py::test_same_run_same_hash`): `digest_events(r1) == digest_events(r2)` for two identical simulation runs.
- **Cross-process** (`test_cross_process_determinism.py` + `test_determinism.py::test_cross_pythonhashseed_determinism`): run the same scenario in separate subprocesses with **different** `PYTHONHASHSEED` values and assert byte-identical output. `tools/determinism_probe.py` is the reusable probe: `json.dumps(payload, sort_keys=True)` with blake2b event digests, classification, liquidation metrics (with `dict(sorted(...))` to normalize ordering), and `build_study_report`. `digest_events` uses `hashlib.blake2b(digest_size=32)` over `json.dumps(r, sort_keys=True)`. Rule: **all summary hashing via `hashlib`, never built-in `hash()`/`set`/`dict` iteration order** (`benchmarks/reference-machine.md §3`).

## 5. Fixtures/helpers

**There is no `conftest.py` anywhere** (glob across the whole repo returned nothing). All fixtures are **inline module-level functions per test file**, re-declared per file (helpers like `_mm_spec`, `_belief_spec`, `_limit`, `_run`, `_bootstrap_world`, `_dispatch`, `_sim_log` are duplicated across test files — this is the accepted convention here). pytest built-ins used: `tmp_path`, `monkeypatch`; `pytest.raises(..., match=...)` for error paths. Standard fixtures come from the kernel bootstrap helpers: `market_game_sim.eventlog.bootstrap.build_account_payload_from_accounts` / `build_book_payload`, and `market_game_sim.ledger.account.Account`. Real configs come from `ExperimentConfig` + `AgentSpec`. For T001, follow suit: define a local `_...` helper (or small local class) rather than introducing conftest.

## 6. Documented evidence for E1-E7 achievement

`docs/experiments/0.1.2-exit-evidence-index.json` is the authoritative machine-readable mapping (T705). Each E maps to concrete test paths / source functions:
- **E1** → 11 `test_acceptance_vectors.py::TestCase*` classes (integer-exact).
- **E2** → `metrics/liquidation.py::compute_liquidation_metrics` + `classify_run` + `test_liquidation.py` chain/volume/bankruptcy tests.
- **E3** → `experiment/config.py::compute_config_hash` + `test_experiment.py::test_run_paired_comparison_carries_traceable_config_hashes`.
- **E4** → `metrics/report.py::build_endpoint_part` + `build_continuous_part` + `test_report.py`.
- **E5** → `bench/` package + `test_runner.py::TestCalibratedFullScale` + `book/matching.py::_run_post_batch_risk_check` (chain_depth fix) + `benchmarks/BENCH-001.yaml` (golden 29310) + `tools/formal_calibration.py`.
- **E6** → `metrics/validation.py`, `experiment/stats.py::build_conditional_conclusion`, `metrics/report.py::build_zero_sum_declaration`, `docs/experiments/0.1.2-e6-demonstration-run.md` (+ `.json`), `test_report.py`, `test_experiment.py`. The e6 run proves the four KPIs on a real `run_paired` study (2 MM + 20 retail, leverage_tier 3x vs 10x, 5 seeds, 30k transactions): KPI-005 matrix honestly `NOT_APPLICABLE` (below 2000-sample floor), KPI-007 conditional conclusion in methodology §10.2 format, KPI-010 via 5 independent seeds, KPI-011 `residual_units == 0` on all 10 runs.
- **E7** → `experiment/runner.py::run_one` (unconditional `_verify_bridge_residuals` at line 336, `check_causal_references` at line 346) + `verify.py::check_causal_references` + `test_verify.py`.
- **附加门槛** → CI `--cov-fail-under=90` (book+ledger 93%), `tools/determinism_probe.py`, `test_cross_process_determinism.py`.

`docs/reviews/RETROSPECTIVE.md` (循环 1) documents the 21-round verification and the recurring **`marked-done-not-implemented`** failure — components tested in isolation but never wired into the real call chain (chain-depth parent link, KPI-011, §6.2 requote). **T001's gate exists precisely to catch this**: it must auto-verify the 0.1.2 exit list from the machine source rather than hand-copying the scope, and assert manifests/logs/matrix/conditional-conclusion are readable with matching digests.

## T001-specific guidance (from `tasks.md` lines 17-19)

T001 is `[TDD]` + `[0.1.2 退出清单]`: build a startup gate that (a) reads E1-E7 from the 0.1.2 spec/machine-truth sources (not hardcoded), and (b) verifies full manifest, raw logs, market-validation matrix, and conditional conclusion are all readable and digest-matched. Write the failing tests first (they'll reference the 0.1.2 exit-evidence-index.json and the verifier's read/digest functions that don't exist yet). Reuse `verify.py::digest_events` and `check_causal_references` as the digest/verification primitives; follow the `_helper`-in-module, positive+negative, and multi-record conventions above. Also note `RETROSPECTIVE.md` 循环 2 flagged `0.1.2-gate-not-satisfied` as already resolved — the 0.1.2 exit evidence index is now `status=met`, so T001's gate has real source data to consume.
</answer>

<next_steps>
1. Read `specs/v0.1-belief-testing-laboratory/0.1.3-robustness/tasks.md` T001 + `spec.md` (lines around "状态" for the 准入 requirement context).
2. Read `docs/experiments/0.1.2-exit-evidence-index.json` fully — it is the machine-truth your gate must parse.
3. Model your verifier on `src/market_game_sim/verify.py` (`verify_log`/`digest_events`/`check_causal_references`) and place tests in `tests/unit/` (verifier logic) + `tests/integration/` (end-to-end gate) with no conftest — inline `_`-prefixed helpers.
4. Write failing tests first (docstring `"""T001 (0.1.2 退出清单): ..."""`), each with positive + negative + multi-record cases per CLAUDE.md.
5. Run `pytest`, `ruff check .`, `ruff format --check .` locally before committing (per CLAUDE.md/CI).
</next_steps>
</results>
