---
tool: "opencode"
tool_name: "OpenCode"
session_id: "ses_01a626453ffeQ8N47efOj1kjjp"
title: "Map experiment infrastructure APIs (@explore subagent)"
project: "D:/Projects/market-game-sim"
model: "deepseek-v4-flash"
created_at: "2026-08-09T08:22:19Z"
updated_at: "2026-08-09T08:25:35Z"
tokens_input: 46840
tokens_output: 5536
cost: 0.0
parent_id: "ses_01a6d8622ffei5cBRUTyC14Unq"
---

# Map experiment infrastructure APIs (@explore subagent)

## user · 2026-08-09T08:22:19Z

I'm implementing 0.1.3 task T001 (an admission gate that auto-verifies 0.1.2 exit conditions) for MarketGameSim at D:\Projects\market-game-sim. I need to understand the experiment orchestration layer to build on it.

GOAL: Map the public APIs of the experiment layer so I know what functions/classes to reuse for running and summarizing experiments, and how verification currently works.

DOWNSTREAM: I'll write new verifier code (T001) and reuse existing functions. I need exact function signatures and return shapes.

READ AND REPORT on these files in src/market_game_sim/:
1. experiment/runner.py — how batch runs happen, what it returns, how seeds/replicates handled, what manifest is written.
2. experiment/protocol.py — preregistration, arm/pair handling, pairing.
3. experiment/config.py — experiment config structure, run_id/cell_id if any.
4. experiment/stats.py — bootstrap, effect size, confidence intervals; note the existing bootstrap_proportion_diff signature (0.1.3 T601 says it must NOT be reused as-is for paired data — I need to know its current contract).
5. metrics/report.py — report generation, conditional conclusions.
6. metrics/validation.py — market validation matrix, what it checks.
7. verify.py — what the top-level verify entrypoint does.
8. kernel/runner.py — how a single simulation run executes and what artifacts it produces.

For each, report: key public functions/classes, their signatures, return types, and what files/artifacts they read or write. Be concrete and technical. Skip test files.
<!-- OMO_INTERNAL_INITIATOR -->

## assistant · 2026-08-09T08:22:19Z

- **tool**: `glob({"pattern": "src/market_game_sim/**/*.py"})`
- **tool**: `glob({"pattern": "src/market_game_sim/**/*.json"})`


> [reasoning] Let me start by exploring the directory structure and then reading the specific files requested.

Let me launch parallel tool calls to explore.
I'll map the experiment orchestration layer. Let me start by locating the files and reading them in parallel.

  <details><summary>tool output</summary>

  ```text
Found 60 file(s)

D:\Projects\market-game-sim\src\market_game_sim\experiment\runner.py
D:\Projects\market-game-sim\src\market_game_sim\metrics\report.py
D:\Projects\market-game-sim\src\market_game_sim\bench\leverage_seed.py
D:\Projects\market-game-sim\src\market_game_sim\book\matching.py
D:\Projects\market-game-sim\src\market_game_sim\bench\__main__.py
D:\Projects\market-game-sim\src\market_game_sim\bench\runner.py
D:\Projects\market-game-sim\src\market_game_sim\experiment\config.py
D:\Projects\market-game-sim\src\market_game_sim\bench\shock.py
D:\Projects\market-game-sim\src\market_game_sim\ledger\liquidation.py
D:\Projects\market-game-sim\src\market_game_sim\bench\population.py
D:\Projects\market-game-sim\src\market_game_sim\bench\coverage.py
D:\Projects\market-game-sim\src\market_game_s
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
Found 1 file(s)

D:\Projects\market-game-sim\src\market_game_sim\schema\event_fields.json
  ```
  </details>

## assistant · 2026-08-09T08:22:28Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\experiment\\runner.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\experiment\\protocol.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\experiment\\config.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\experiment\\stats.py"})`

Let me read all 8 target files in parallel.

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
13: from market_game_sim.agent.scheduler import AgentSpec
14: from market_game_sim.book.matching import match_order
15: from market_game_sim.book.orderbook import Book
16: from market_game_sim.eventlog.bootstrap import (
17:     build_account_payload_from_accounts,
18:  
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\experiment\protocol.py</path>
<type>file</type>
<content>
1: """T603 (方法论 §9.3/§10.1/§10.3): three-zone experiment protocol enforcement.
2: 
3: 校准区 -> 冻结验证区 -> 信念实验区，顺序固定、不可跳过或回退（§10.1"验证顺序
4: 不可颠倒"）。进入冻结验证区后，除预注册的单一处理维度（``treatment_field``，
5: 默认 ``leverage_tier``）外，全部配置字段被冻结为快照；后续任何一次调用如果
6: 配置字段偏离快照，判定为协议违规：``raise ProtocolViolation`` 并向审计日志
7: 追加一条记录（fail-stop，不静默继续，呼应内核自身对因果链/schema 违规的处理
8: 哲学，见 kernel/scheduling.py）。
9: 
10: 信念实验区声明的处理维度取值集合，必须与校准区实际试过的取值集合不相交
11: （§10.3"信念实验区预注册，与校准区不重叠"）——防止"校准时刚好看到某个杠杆
12: 倍数表现不错，就拿它当信念实验的处理值"这种数据窥探（data snooping）。
13: """
14: 
15: from __future__ import annotations
16: 
17: import dataclasses
18: import json
19: from collections.abc import Iterable
20: from datetime import UTC, datetime
21: f
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
<path>D:\Projects\market-game-sim\src\market_game_sim\experiment\stats.py</path>
<type>file</type>
<content>
1: """T604/T605 (方法论 §9.2/§10.2/§10.5): paired-experiment statistics.
2: 
3: * :func:`bootstrap_proportion_diff` -- effect size + CI for the difference
4:   in economic-endpoint rate between a paired control/treatment group
5:   (方法论 §10.2's "效应量（含置信区间）").
6: * :func:`holm_bonferroni` -- step-down multiple-comparison correction
7:   (T604), for when more than one metric/hypothesis is tested at once.
8: * :func:`build_conditional_conclusion` -- formats a bootstrap result into
9:   方法论 §10.2's required conditional-proposition text ("在参与者结构 S、
10:   参数区间 R 与 N 个随机种子下...").
11: 
12: This is the reporting/statistics layer, not the core domain kernel bound by
13: ADR-001's no-float/hash-o
…[truncated]
  ```
  </details>

## assistant · 2026-08-09T08:22:47Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\metrics\\report.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\metrics\\validation.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\verify.py"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\kernel\\runner.py"})`

Now let me read the remaining 4 files in parallel.

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\metrics\report.py</path>
<type>file</type>
<content>
1: """T505: Two-part report (退化状态 §4.0).
2: 
3: Part 1: economic endpoint rate and severity.
4: Part 2: continuous metrics conditional on no endpoint.
5: """
6: 
7: from __future__ import annotations
8: 
9: from dataclasses import dataclass, field
10: 
11: from market_game_sim.ledger.account import Account
12: from market_game_sim.metrics.liquidation import LiquidationMetrics, RunClassification
13: 
14: 
15: @dataclass
16: class EndpointPart:
17:     total_runs: int
18:     runs_with_endpoint: int
19:     rate: float
20:     by_code: dict[str, int] = field(default_factory=dict)
21:     breach_count: int = 0
22:     avg_liquidation_volume_ratio: float = 0.0
23:     n_samples: int = 0
2
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\metrics\validation.py</path>
<type>file</type>
<content>
1: """T606 (KPI-005): market validation matrix.
2: 
3: Implements the 0.1.2 pre-registered protocol
4: (``docs/experiments/0.1.2-market-validation-protocol.md``, T002) for the
5: 6 features PRD §12 requires KPI-005 to declare PASS/FAIL/NOT_APPLICABLE for.
6: 
7: This is the reporting/statistics layer (ADR-001's no-float rule is scoped to
8: the domain kernel, not here) -- uses ``statistics.NormalDist`` for asymptotic
9: normal-approximation significance tests, no scipy dependency.
10: """
11: 
12: from __future__ import annotations
13: 
14: import math
15: from dataclasses import dataclass, field
16: from statistics import NormalDist
17: 
18: from market_game_sim.experiment.stats 
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

## assistant · 2026-08-09T08:23:05Z

- **tool**: `grep({"pattern": "def (classify_run|compute_liquidation_metrics)|^class (RunClassification|LiquidationMetrics)|    is_economic_endpoint|    is_technical_invalid|    economic_endpoint_codes|    breached", "path": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\metrics\\liquidation.py", "output_mode": "content"})`
- **tool**: `glob({"pattern": "specs/v0.1-belief-testing-laboratory/0.1.3-robustness/**"})`
- **tool**: `grep({"pattern": "def (sample_market_series|sample_agent_series|compute_price_impact)|^class (MarketSample|ImpactSample|AgentSample)", "path": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\metrics\\sampling.py", "output_mode": "content"})`


> [reasoning] I have all 8 files. Let me also quickly check a few supporting pieces that the T001 verifier will need: metrics/liquidation.py (RunClassification, LiquidationMetrics, classify_run, compute_liquidation_metrics), metrics/sampling.py (sample_market_series, compute_price_impact), and the 0.1.3 tasks.md for T001 context. But the task asked specifically to map the 8 files. Let me quickly check the liquidation metrics signature since it's central to the verify gate, and also confirm the 0.1.3 T001 task description for what exit conditions to verify.

Let me check the 0.1.3 tasks.md for T001 and the metrics/liquidation.py since RunResult and reports rely heavily on it. These are directly relevant to the downstream verifier.
I have all 8 target files. Let me quickly pull two supporting pieces the T001 verifier will depend on: the `RunClassification`/`LiquidationMetrics` types (returned by `RunResult`) and the T001 task spec.

  <details><summary>tool output</summary>

  ```text
Found 8 match(es) in 1 file(s)

D:\Projects\market-game-sim\src\market_game_sim\metrics\liquidation.py
  17: class LiquidationMetrics:
  35: def compute_liquidation_metrics(events: list[dict]) -> LiquidationMetrics:
  77: class RunClassification:
  80: is_technical_invalid: bool = False
  82: is_economic_endpoint: bool = False
  83: economic_endpoint_codes: list[str] = field(default_factory=list)
  84: breached: bool = False
  96: def classify_run(
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
Found 2 file(s)

D:\Projects\market-game-sim\specs\v0.1-belief-testing-laboratory\0.1.3-robustness\tasks.md
D:\Projects\market-game-sim\specs\v0.1-belief-testing-laboratory\0.1.3-robustness\spec.md
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
Found 6 match(es) in 1 file(s)

D:\Projects\market-game-sim\src\market_game_sim\metrics\sampling.py
  21: class MarketSample:
  34: class AgentSample:
  51: def sample_market_series(
  122: def sample_agent_series(
  183: class ImpactSample:
  206: def compute_price_impact(events: list[dict], mult: int = 1000) -> list[ImpactSample]:
  ```
  </details>

## assistant · 2026-08-09T08:23:26Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\specs\\v0.1-belief-testing-laboratory\\0.1.3-robustness\\tasks.md"})`
- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\metrics\\liquidation.py", "offset": 17, "limit": 150})`

Let me read the T001 task spec and the key signatures in liquidation.py and sampling.py.

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
<path>D:\Projects\market-game-sim\src\market_game_sim\metrics\liquidation.py</path>
<type>file</type>
<content>
17: class LiquidationMetrics:
18:     """Aggregate liquidation statistics (指标字典 §4.1)."""
19: 
20:     total_liquidations: int = 0
21:     total_volume: int = 0
22:     liquidation_volume: int = 0
23:     chain_depth_counts: dict[int, int] = field(default_factory=Counter)
24:     chain_size_by_id: dict[str, int] = field(default_factory=dict)
25:     bankruptcy_total: int = 0
26:     breach_volume_units: int = 0
27: 
28:     @property
29:     def liquidation_volume_ratio(self) -> float:
30:         if self.total_volume == 0:
31:             return 0.0
32:         return self.liquidation_volume / self.total_volume
33: 
34: 
35: def compute_liquidation_metrics(events: list[dict]) ->
…[truncated]
  ```
  </details>

## assistant · 2026-08-09T08:23:43Z

- **tool**: `read({"filePath": "D:\\Projects\\market-game-sim\\src\\market_game_sim\\metrics\\sampling.py", "offset": 21, "limit": 45})`
- **tool**: `grep({"output_mode": "content", "path": "D:\\Projects\\market-game-sim\\specs\\v0.1-belief-testing-laboratory\\0.1.2-leverage-and-first-experiment\\spec.md", "pattern": "E[1-7]", "head_limit": 40})`


> [reasoning] I have everything needed. Let me also check the sampling.py signatures to be complete on the report side. Actually I have enough. Let me also note the 0.1.2 spec exit conditions (E1-E7). Let me quickly check the 0.1.2 spec for E1-E7 since T001 must verify them. Let me grep.
Let me quickly grab the sampling.py signatures and the 0.1.2 exit conditions (E1–E7) that T001 must auto-verify.

  <details><summary>tool output</summary>

  ```text
<path>D:\Projects\market-game-sim\src\market_game_sim\metrics\sampling.py</path>
<type>file</type>
<content>
21: class MarketSample:
22:     timestamp: int
23:     last_ticks: int | None
24:     mid_ticks: int | None
25:     spread_ticks: int | None
26:     bid_depth_k: int
27:     ask_depth_k: int
28:     volume_since_last: int
29:     cancel_count_since_last: int
30:     trade_count_since_last: int
31: 
32: 
33: @dataclass
34: class AgentSample:
35:     timestamp: int
36:     agent_id: str
37:     wallet_units: int
38:     position_units: int
39:     entry_notional_units: int
40:     margin_ratio_bp: int | None
41:     leverage_bp: int | None
42:     realized_pnl_units: int
43: 
44: 
45: def compute_burn_in(bar_ns: int, n_max: int, w_max: int) -> int:
46:     """Burn-in window in nanosec
…[truncated]
  ```
  </details>

  <details><summary>tool output</summary>

  ```text
Found 7 match(es) in 1 file(s)

D:\Projects\market-game-sim\specs\v0.1-belief-testing-laboratory\0.1.2-leverage-and-first-experiment\spec.md
  52: | E1 | [验收向量](../../../docs/contracts/acceptance-vectors.md)**十个案例全部通过**（0.1.1 已过 1—5、10，本阶段补 6—9） |
  53: | E2 | 强平连锁可测量：`chain_depth`、强平量占比、连锁规模分布均有输出 |
  54: | E3 | 一项**预注册**实验完成，可从配置哈希追溯到条件性结论 |
  55: | E4 | 报告分两部分给出：经济终点发生率与严重度、条件于未发生终点的连续指标 |
  56: | E5 | BENCH-001 归一化耗时达标，且**覆盖断言全满足**（强平、连锁各至少 1 次） |
  57: | E6 | KPI-005、KPI-007、KPI-010、KPI-011 达标 |
  58: | E7 | KPI-006：独立验证器机器验证成交两侧订单的因果链（T506）——代理来源订单验证「观察—信念—决策」链，强平来源订单验证「风控决定（MARGIN_CALL）」链；同一次真实研究运行须同时覆盖两种分支，不止步于十个静态验收案例。同一次验证一并断言 KPI-009（个体 PnL 桥接残差逐事件恒为 0，T503）成立 |
  ```
  </details>

## assistant · 2026-08-09T08:23:59Z


> [reasoning] I now have complete coverage. Let me write the report. I have all signatures needed.

Let me compile the structured results.
I have everything needed to map the full experiment orchestration layer. Here is the report.

<results>
<files>
- D:\Projects\market-game-sim\src\market_game_sim\experiment\runner.py - multi-seed batch runner, `RunResult`, `run_paired`/`run_multi_seed`/`run_one`, report builders. Central entry for running+summarizing experiments.
- D:\Projects\market-game-sim\src\market_game_sim\experiment\protocol.py - `ExperimentProtocol` three-zone preregistration guard, `ProtocolStage`, `ProtocolViolation`.
- D:\Projects\market-game-sim\src\market_game_sim\experiment\config.py - `ExperimentConfig` dataclass + `compute_config_hash` (no run_id/cell_id here yet — those are 0.1.3 T202).
- D:\Projects\market-game-sim\src\market_game_sim\experiment\stats.py - `bootstrap_proportion_diff` (current contract, flagged by T601 as not reusable as-is for paired data), `holm_bonferroni`, `build_conditional_conclusion`.
- D:\Projects\market-game-sim\src\market_game_sim\metrics\report.py - `build_report`/`build_endpoint_part`/`build_continuous_part` (two-part report), `build_zero_sum_declaration` (KPI-011).
- D:\Projects\market-game-sim\src\market_game_sim\metrics\validation.py - 6-item KPI-005 matrix, `build_market_validation_matrix`, per-feature `check_*` functions.
- D:\Projects\market-game-sim\src\market_game_sim\verify.py - top-level `verify_log` + `check_causal_references` (independent, no-kernel reconstruction).
- D:\Projects\market-game-sim\src\market_game_sim\kernel\runner.py - `EventKernel` single-run execution engine.
- D:\Projects\market-game-sim\src\market_game_sim\metrics\liquidation.py - `RunClassification`, `LiquidationMetrics`, `classify_run`, `compute_liquidation_metrics` (types embedded in `RunResult`; essential for T001).
- D:\Projects\market-game-sim\src\market_game_sim\metrics\sampling.py - `sample_market_series`, `sample_agent_series`, `compute_price_impact`, and the `MarketSample`/`AgentSample`/`ImpactSample` dataclasses.
- D:\Projects\market-game-sim\specs\v0.1-belief-testing-laboratory\0.1.3-robustness\tasks.md - T001 spec text + the full 0.1.3 task matrix (T601 bootstrap note, T202 run_id/cell_id contract).
- D:\Projects\market-game-sim\specs\v0.1-belief-testing-laboratory\0.1.2-leverage-and-first-experiment\spec.md - E1–E7 exit conditions T001 must auto-verify.
</files>

<answer>
Here is the concrete API map, per file. Note upfront: **T001's "exit conditions / manifest / summary" live in the 0.1.2 spec + its experiment artifacts, not in 0.1.2 source** — `runner.py` computes everything in-memory but does not write a manifest or raw-log jsonl to disk in the paths I read. `verify_log()` is the only code that reads a persisted jsonl. So T001 will need a manifest/artifact source that the current layer does not yet produce to a fixed path.

## 1. experiment/runner.py
Entry points for running + summarizing. All in-memory; no manifest written to disk here.

- `run_one(config: ExperimentConfig, protocol: ExperimentProtocol | None = None) -> RunResult`
  Builds accounts (from agent_specs + extra_accounts + extra_positions), bootstraps an `EventKernel(run_id=f"exp-s{config.seed}")`, wires `_dispatch_agents`, runs with `max_transactions=config.max_transactions`, then computes liquidation metrics, `check_c1_c2`, `check_causal_references`, and `classify_run(...)`. **No jsonl is serialized** — it reads `kernel.committed_records` in memory.
- `run_multi_seed(base_config: ExperimentConfig, seeds: list[int], protocol=None) -> list[RunResult]` — clones the config per seed, returns one `RunResult` per seed.
- `run_paired(control, treatment, seeds, treatment_field="leverage_tier", structure_desc="", param_range_desc="", n_resamples=10_000, bootstrap_seed=0) -> tuple[list[RunResult], list[RunResult], dict]` — static parity check (`check_paired_parity`) + dynamic shared-randomness check (`check_shared_randomness_parity`), then runs both arms, bootstraps endpoint-rate effect, builds a conditional conclusion, and returns a `comparison` dict (the shape T001 will most want):
  - `n_seeds`, `treatment_field`,
  - `control_config_hash` / `treatment_config_hash` (from `compute_config_hash`),
  - `control: {n_completed, n_endpoint}`, `treatment: {n_completed, n_endpoint}`,
  - `endpoint_rate_effect: ProportionDiffResult` (as dict),
  - `conditional_conclusion: str`.
- `build_study_report(results: list[RunResult]) -> dict` — two-part endpoint/continuous report + impact + `market_validation` + per-seed `zero_sum`. Returned keys: `endpoint{rate,by_code,breach_count,n_endpoint_samples,mean_margin_ratio_bp,mean_leverage_bp}`, `continuous{n_samples,mean_margin_ratio_bp}`, `impact{n_taker_orders,mean_impact_bp}`, `technical_invalid_rate`, `n_runs`, `n_completed`, `market_validation`, `zero_sum`.
- `build_market_validation_report(results, sample_interval_ns=1_000_000_000) -> dict` — per-seed `{"per_seed": {seed: matrix.as_dict()}}`; skips technical-invalid runs.
- `check_paired_parity(control, treatment, treatment_field="leverage_tier") -> str | None`, `check_shared_randomness_parity(c_results, t_results) -> str | None` — reusable by T001/T403-style diff validation.
- `RunResult` dataclass fields: `seed:int, terminated:str, abort_code:str|None, events:list[dict], book_last_ticks:int|None, accounts:dict[str,Account], liquidation_metrics:LiquidationMetrics, classification:RunClassification, group_label:str, book_operation_count:int, initial_baseline:dict[str,int], exchange_fee_units:int, exchange_risk_pnl_units:int`.
- Imports from verify.py: `from market_game_sim.verify import check_causal_references`.

## 2. experiment/protocol.py
- `ProtocolStage(Enum)`: `CALIBRATION`, `FROZEN_VALIDATION`, `BELIEF_EXPERIMENT`.
- `ProtocolViolation(Exception)` — fail-stop, callers must not swallow.
- `class ExperimentProtocol`:
  - `__init__(self, treatment_field="leverage_tier", audit_log_path="docs/experiments/protocol-audit.jsonl")`
  - `record_calibration_trial(config) -> None` (CALIBRATION only; collects treatment values tried)
  - `freeze_calibration(config) -> None` (CALIBRATION → FROZEN_VALIDATION; snapshots all fields except treatment_field)
  - `enter_belief_experiment(belief_treatment_values: Iterable[Any]) -> None` (FROZEN_VALIDATION → BELIEF_EXPERIMENT; rejects values overlapping calibration)
  - `check_config(config) -> None` (validates config vs. stage lock before running; no-op in CALIBRATION)
  - `_audit(violation, field_name, detail)` — appends a JSON line to `audit_log_path`.
  - State attrs: `stage`, `treatment_field`, `audit_log_path`.

## 3. experiment/config.py
- `@dataclass ExperimentConfig` fields: `seed:int, max_transactions:int, initial_price_ticks:int=10000, mult:int=1000, maker_bps:int=-1, taker_bps:int=5, maint_bp:int=500, target_bp:int=1000, liquidation_latency_ns:int=1_000_000, agent_specs:list[AgentSpec]=[], agent_signals:dict[str,int]={}, group_label:str="control", extra_accounts:dict[str,int]={}, extra_events:list[dict]=[], extra_positions:dict[str,dict[str,int]]={}`.
- **No `run_id`/`cell_id` fields here.** Those are 0.1.3 T202 concepts (`cell_id = H(normalized cell incl. treatment; excludes seed/replicate_id)`, `run_id = H(cell_id + seed + replicate_id)`). The runner currently keys a run only by `config.seed` and a synthetic `EventKernel(run_id="exp-s{seed}")`.
- `compute_config_hash(config: ExperimentConfig) -> str` — blake2b over canonical sorted-key JSON of `asdict(config)`. Stable, cross-process. This is the E3 traceability link T001 must match against.

## 4. experiment/stats.py
- `@dataclass ProportionDiffResult`: `control_rate, treatment_rate, diff, ci_low, ci_high, ci_level, n_control, n_treatment, n_resamples, seed`; property `ci_excludes_zero -> bool`.
- `bootstrap_proportion_diff(control_outcomes: list[bool], treatment_outcomes: list[bool], n_resamples=10_000, ci_level=0.95, seed=0) -> ProportionDiffResult`. **Current contract: resamples each arm independently** (`rng.randrange(n_c)` / `rng.randrange(n_t)` separately), computes `diff = treatment_rate - control_rate`, sorts resampled diffs, takes percentile CI. Deterministic via locally-seeded `random.Random(seed)`.
  - **T601 explicitly forbids reusing this as-is for 0.1.3 paired data**: it says bootstrap must resample whole `pair_id` units, not each arm independently; a new by-pair resampling implementation is required. So do NOT call `bootstrap_proportion_diff` for the 0.1.3 paired effect — reuse `ProportionDiffResult` and `build_conditional_conclusion` shapes if convenient, but the resampling core needs a new paired function.
- `holm_bonferroni(p_values: dict[str,float], alpha=0.05) -> dict[str,bool]` — step-down correction.
- `build_conditional_conclusion(result: ProportionDiffResult, structure_desc:str, param_range_desc:str, failure_condition_desc:str="", metric_name:str="经济终点率") -> str` — emits §10.2 conditional-proposition text.

## 5. metrics/report.py
- `@dataclass EndpointPart` / `@dataclass ContinuousPart` / `@dataclass TwoPartReport`.
- `build_endpoint_part(classifications, metrics_list, endpoint_samples=None) -> EndpointPart` — Part 1 (rate + by_code + breach_count + severity).
- `build_continuous_part(valid_samples) -> ContinuousPart` — Part 2 (conditional on no endpoint; includes `valid_sample_note` when null ratios >30%).
- `build_report(classifications, metrics_list, valid_samples, endpoint_samples=None) -> TwoPartReport` — assembles both parts + `technical_invalid_rate`.
- `@dataclass ZeroSumDeclaration`: `total_pnl_units, expected_negative_fees_units, residual_units, per_agent_pnl_units:dict[str,int], declaration_text:str`.
- `build_zero_sum_declaration(accounts: dict[str,Account], initial_baseline: dict[str,int], exchange_fee_units:int, exchange_risk_pnl_units:int) -> ZeroSumDeclaration` (KPI-011). `initial_baseline` must be wallet−entry at t=0. Residual should be 0 (reported, not asserted).

## 6. metrics/validation.py
- Constants: `MIN_SAMPLE_POINTS=2000`, `MAX_FILL_RATIO=0.30`, `ACF_LAGS=5`, `VOL_WINDOW=30`, `ALPHA=0.05`, `MIN_TAKER_ORDERS=40`, `MAX_RELATIVE_SPREAD=0.05`, `RANGE_COVERAGE=0.95`.
- `@dataclass ValidationItem`: `name, verdict("PASS"|"FAIL"|"NOT_APPLICABLE"), statistic, p_value, threshold_desc, evidence`; `as_dict()`.
- `@dataclass MarketValidationMatrix`: `items: dict[str,ValidationItem], fill_ratio, fill_ratio_ok, alpha`; `as_dict()`.
- `build_market_validation_matrix(market_samples: list[MarketSample], impact_samples: list[ImpactSample], liquidation_metrics: LiquidationMetrics) -> MarketValidationMatrix` — the 6-item matrix (fat_tails, return_autocorrelation, volatility_clustering, price_impact_nonlinearity, spread_depth_regime, liquidation_chain). Many items short-circuit to NOT_APPLICABLE if fill_ratio >30% or n below thresholds.
- Individual checks (`check_fat_tails`, `check_return_autocorrelation`, `check_volatility_clustering`, `check_price_impact_nonlinearity`, `check_spread_depth_regime`, `check_liquidation_chain`) plus helpers `compute_log_returns`, `compute_fill_ratio`, `acf`, `excess_kurtosis`, `apply_family_correction`.

## 7. verify.py
- `verify_log(path: str|Path, mult=1000) -> dict` — reads a jsonl event log, reconstructs book+account WITHOUT importing kernel/ledger, and returns `{"success": bool, ...}`. On failure: `{"success": False, "error": "TI-5"|"TI-4", "detail": ...}`. On success returns `success, termination, last_committed_transaction_seq, event_count, account_count, c1_pass, causal_chain_pass, kpi006_agent_covered, kpi006_liquidation_covered, kpi009_bridge_ok`. This is the independent verifier that consumes persisted jsonl (KPI-006/KPI-009) — but it only runs against a file; `run_one` produces no file, so T001's "原始日志" leg must either call this on a persisted log or reuse its in-memory helpers.
- `check_causal_references(events: list[dict]) -> str | None` — pure in-memory causal-chain check (TI-1). Reused by runner.
- Helpers: `_rebuild`, `_check_c2`, `_check_kpi009_bridge`, `_check_kpi006`, `digest_events(records) -> str` (blake2b over EVENT records — useful for "摘要匹配" in T001).
- Imports `bridge_trade` from `metrics.bridge` (KPI-009 pure function).

## 8. kernel/runner.py
- `TransactionHandler = Callable[[dict, dict, "EventKernel"], list[dict]]`.
- `class EventKernel`: `__init__(run_id="run", schema_version=2)`.
  - `bootstrap(account_payload, book_payload) -> None` (must precede enqueue/run).
  - `enqueue(event) -> None` (rejects non-queue types, enforces monotonicity + class-regression).
  - `run(handler, world, max_transactions) -> None` — loop till queue empty / max_transactions / abort. On `KernelAbort` → `terminated="ABORTED"` + `abort_code`; else `terminated="COMPLETED"`.
  - Read-only props: `committed_records -> list[dict]` (defensive copies), `last_committed_transaction_seq`, `processed_transactions`, `terminated`, `abort_code`, `abort_detail`, `bootstrap_done`, `current_transaction_seq`, `queue_empty`.
  - `build_trailer(record_count) -> dict` — RUN_TRAILER used by the T205 writer.
- Artifacts: the kernel itself writes **no files**; it accumulates `_committed_records` in memory (these become `RunResult.events`). Persisting to jsonl is delegated to `eventlog/writer.py` (T205), which is not invoked by the experiment runner.
</answer>

<next_steps>
For T001 (auto-verify 0.1.2 E1–E7 exit conditions from 0.1.2 spec + machine truth), the concrete gaps to close:

1. Decide the manifest/artifact source. The current layer computes everything in memory (`RunResult`, `build_study_report`, `build_market_validation_report`, `verify_log` on files) but `run_one`/`run_multi_seed` never persist a manifest or a jsonl log. T001 needs a stable on-disk location + format to "read back and match summaries". Look at `eventlog/writer.py` (T205) for the jsonl writer, and check whether a 0.1.2 manifest already exists under `docs/experiments/` — if not, that's the first thing T001 must define (or reuse an existing artifact if one is committed).

2. For "原始日志" verification, use `verify_log(path)` (file-based, KPI-006/KPI-009) and `digest_events` for摘要匹配; for "条件性结论" matching use `compute_config_hash` (E3) and `build_study_report`/`run_paired`'s `comparison` dict.

3. For "市场验证矩阵", reuse `build_market_validation_matrix` via `build_market_validation_report(results)` and match the per-seed matrix dicts.

4. Do NOT reuse `bootstrap_proportion_diff` for 0.1.3 paired effect size (T601) — plan a new by-`pair_id` resampler; you may reuse `ProportionDiffResult` + `build_conditional_conclusion` shapes.

5. `run_id`/`cell_id` do not exist yet — that's 0.1.3 T202 (not part of T001). Don't depend on them in T001.
</next_steps>
</results>
