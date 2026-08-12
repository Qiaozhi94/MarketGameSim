---
kind: milestone
id: 0.1.4
parent: v0.1-belief-testing-laboratory
version: "0.1"
status: in-progress
gate_version: 1
created: 2026-08-01
updated: 2026-08-11
prerequisites:
  - 0.1.3
---

# 0.1.4：回放与报告

> Spec: `spec.md` | Design: `design.md` | Tasks: `tasks.md`

## 0. 来源与意图

- **版本规格**：`../spec.md`（FR-019、FR-020、SC-008、SC-006）。
- **PRD 来源**：`../../market-game-sim-prd.md`（PR-018—PR-020、KPI-012）。
- **架构来源**：`../../market-game-sim-architecture.md`（L4 呈现与报告层）、
  `../design.md`（v0.1 / D-7 回放架构定位）。
- **Contract 来源**：`../../contracts/event-schema.md`（日志结构、帧、快照）、
  `../../research/metrics-dictionary.md`（K 线周期、PnL 桥接）、
  `../../contracts/degenerate-states.md`（经济终点与技术无效）。
- **功能类型**：user-facing / data-model / validation
- **规格模式**：full
- **变更类型**：ADDED
- **一句话意图**：把事件日志变成可读的逐帧回放与总结报告，证明日志自包含，且不引入
  第二个真源。

## 1. 问题、目标与非目标

### 问题

FR-019、FR-020、SC-008、PR-018—PR-020、KPI-012 是 **v0.1 的必选需求**，但此前
0.1.1 把它们标为「0.1.2」、0.1.2 标为「0.1.3 或按需」、0.1.3 又标为「后续展示阶段」
——三个里程碑可以全部签收，而完整 v0.1 仍未交付这些能力。**不能用「按需」表示必选
需求的归属**（封板审计 P0-O03）。

### 目标

**把事件日志变成人能看懂的东西，且不引入第二个真源。** 回放器是事件日志的消费者，
与内核完全解耦（v0.1 / D-7）。它证明的不只是「好看」，而是一件有研究价值的事：
**日志确实自包含**——若回放能仅凭日志还原整段仿真，那么日志就足以支撑任何后续分析，
不必保留内核。

### 非目标

- 在线实时渲染（**v0.1 / D-7 已排除**——离散事件仿真中「实时」无物理意义）；
- 人在环交互；
- 多运行对比看板（属 v0.2+）。

## 2. 用户场景

### US-004：观察杠杆连锁（沿用版本规格）

作为研究者，我可以在不同杠杆上限分布与维持保证金率下，观察下跌是否自我强化，并
**通过回放器逐帧查看**强平连锁的规模与深度（版本规格 US-4）。

**为什么是这个优先级**：回放器把已记录的强平连锁变成可逐帧检查的可视化，直接支撑
US-4 的连锁规模观测。

**独立测试**：逐帧一致性验收（E1）保证回放与原始运行逐帧相等，不依赖其他场景。

**验收场景**：

1. Given 一次已记录运行的事件日志，when 用回放器打开，then 能逐帧还原价格、订单簿、
   账户与强平事件。

### US-005：追溯任一成交（沿用版本规格）

作为研究者，我可以从任一成交追溯到代理的观察、信念权重、决策与账户变化（版本规格
US-5），并通过回放器逐帧观察这些状态如何演变。

**为什么是这个优先级**：回放器提供时间维度上的逐帧观察，使因果追溯更直观。

**独立测试**：K 线与总结报告（E3、E4）分别独立验收。

**验收场景**：

1. Given 事件日志，when 逐帧推进到某成交，then 能观察到引发它的观察—决策—账户变化。

## 3. 范围与边界

### 3.1 范围内

- **单文件 HTML 回放器**：以事件日志为唯一输入，逐帧呈现价格、订单簿、账户与强平；
  数据内联嵌入产物本身，不产生 `fetch`、不依赖 CDN 或外部字体（离线打开验收 E2）。
- **K 线视图**：周期定义见指标字典 §1.9，仅使用**已完成**的 K 线。
- **总结报告**：一次运行的指标汇总、PnL 桥接、经济终点与技术无效统计。
- **逐帧一致性验收**：SC-008 / KPI-012：回放状态与原运行逐帧相等。

### 3.2 与内核的边界（解耦不变量）

回放器与报告是事件日志的**只读消费者**：与内核之间只有**日志文件**这一条通路，
不反向导入内核模块——可执行断言见 §4 的 NFR-004（四类禁止导入模块的封闭清单）。
这条边界划定的是「范围」而非「实现细节」：即使回放器逐帧结果完全正确，只要它
导入了内核模块，就已经引入了第二个真源，属于范围违规而非功能缺陷。

### 3.3 降采样与大日志边界

大日志允许降采样，但降采样比例与规则必须写入产物并在页面上可见；**E1 逐帧一致性
验收在未降采样的完整日志上执行**，降采样产物不得用于该项验收。

### 3.4 范围外

- 在线实时渲染、人在环交互、多运行对比看板（后移 v0.2+）。

### 3.5 边界场景

- 空簿/单边簿下的回放与 K 线呈现。

## 4. 需求

### 功能需求

- **FR-019**：提供单文件 HTML 回放器，以事件日志为唯一输入逐帧呈现价格、订单簿、
  代理状态与**强平事件**，支持拖拽、变速与暂停。回放与报告同源，仿真内核不依赖
  呈现层（版本规格 FR-019）。
- **FR-020**：提供 K 线视图，周期定义见指标字典 §1.9（版本规格 FR-020）。
- **PR-018**：单文件 HTML 离线打开可用，无任何外部请求。
- **PR-019**：总结报告含条件性结论、效应量、置信区间与失效边界，且全部数值消费
  上游 artifact，**不自行重算**。
- **PR-020**：K 线视图与指标字典 §1.9 的周期定义一致，且只用已完成 K 线。

### 4.1 报告输入 artifact 与 manifest 合同（唯一真源是 `report_artifacts.json`）

报告的输入是一份 artifact manifest，列出被消费的冻结产物及其哈希。10 类 artifact 的
字段 Schema 唯一真源是 `src/market_game_sim/schema/report_artifacts.json`；本表是
人类可读索引，两者由 `tools/validate_contract_sources.py` 双向核对，禁止另抄一份
字段清单。

| artifact_id | producer |
|---|---|
| `market_metrics` | 0.1.2 T501 |
| `agent_metrics` | 0.1.2 T501 |
| `liquidation_metrics` | 0.1.2 T502 |
| `pnl_bridge` | 0.1.2 T503 |
| `sample_classification` | 0.1.2 T504 |
| `effect_sizes` | 0.1.2 T604 |
| `conditional_conclusion` | 0.1.2 T605 |
| `robustness_effects` | 0.1.3 T601 |
| `robustness_conclusion` | 0.1.3 T604 |
| `negative_results` | 0.1.3 T606 |

**manifest 结构**（唯一真源是 `report_artifacts.json` 的 `manifest_schema` 键；本节
是人类可读索引，两者同样由 `tools/validate_contract_sources.py` 双向核对）：

- 顶层封闭字段：`manifest_version`（整数）、`artifact_root`（字符串，manifest 文件
  唯一的产物根目录来源——不作为报告入口的额外参数出现，见 design.md §4）、
  `artifacts`（数组，元素见下）。
- **完备性**：`artifacts` 数组必须恰好为上表 10 类 `artifact_id` 各声明一条，
  一一对应、不重不漏；registry 中存在但 manifest 未声明的 `artifact_id` 即判定
  为「必备件缺失」。
- `artifacts` 数组每个元素声明以下**七个封闭字段**，逐 artifact 一条：
  1. `artifact_id`（字符串）——须在 registry 中存在；
  2. `path`（字符串）——相对 `artifact_root` 的路径；
  3. `format`（字符串）——须与 registry 声明一致；
  4. `schema_version`（整数）——须与 registry 声明一致；
  5. `producer`（字符串）——须与 registry 声明一致，供溯源；
  6. `hash_algorithm`（字符串，**枚举唯一值 `blake2b`**）——机器 Schema 冻结为
     单元素枚举，不接受其他算法；
  7. `hash`（字符串，**固定 64 位十六进制小写摘要**）——对 `path` 指向文件的字节
     内容计算 `blake2b(digest_size=32)`，与事件摘要哈希（KPI-002，事件 Schema
     §7，`eventlog/digest.py::DIGEST_SIZE`）同一 digest_size，而非
     `config_hash`（事件 Schema §6.1）用于配置指纹的 `digest_size=16`——两者
     用途不同（文件内容完整性 vs 配置指纹去重），不得混用同一长度。
- **额外数据件扫描**：递归扫描 `artifact_root` 目录下全部常规文件；任一文件的相对
  路径未出现在任何 manifest 条目的 `path` 字段中，即判定为「未声明数据件」。
- **五类失败**（与 T302 五类负向夹具、design.md `failure.code` 一一对应），任一
  出现即报告生成失败（不降级为部分报告）：必备件缺失（含 manifest 遗漏 registry
  中某 `artifact_id`）/ 哈希不符 / `schema_version` 错版 / 必备字段缺失或类型
  错误（含 `hash_algorithm` 不等于 `blake2b`）/ 出现未声明额外数据件。

### 4.2 事件 / Trace 需求（oracle 设计）

- **TR-001**：逐帧一致性 oracle 由测试专用独立 observer 提供，只作期望值输入，绝不
  喂给回放器。oracle 的帧与字段规则唯一真源在 design.md §4（Event / Trace
  Contract）：bootstrap 两个连续事务（ACCOUNT 在 `transaction_seq=b`、BOOK 在
  `b+1`，见事件 Schema §4.6.3 的可判定快照规则）合并为第 0 帧，此后第 k 帧对应
  `transaction_seq = b + k`（bootstrap 屏障完整实现后 `b=2`，即 `k + 2`）；判等字段为
  账户 11 项（事件 Schema §4.6.1）、交易所
  2 项（事件 Schema §4.6.1）、最近成交价 `last_ticks`（价格状态，事件 Schema
  §4.6.2）与订单簿聚合三项 `price_ticks`/`quantity_units`/`order_count`（同上
  §4.6.2）。判等顺序：先比帧数与帧键集合相等，再逐帧比对上述字段集合；任一字段
  不等即判定不一致。

### 非功能需求

- **NFR-004**（沿用）：回放器与报告**不导入** `kernel/`、`book/`、`ledger/`、
  `eventlog/`（v0.1 / D-7、§3.2）。

## 5. 生命周期与不变量

- 回放器是只读消费者：读日志 → 内联生成单文件 HTML；报告读 manifest → 核对哈希 →
  生成总结报告。
- 缺件行为（五类失败，定义见 §4.1）：必备件缺失、哈希不符、`schema_version` 错版、
  必备字段缺失或类型错误、出现未声明额外数据件 → **报告生成失败**，不降级为
  「部分报告」。

不变量：

- 回放重建状态 == 独立 observer 快照，逐帧逐字段相等（SC-008）。
- 回放器与内核之间只有日志文件这一条通路（§3.2）。
- 报告层不自行重算统计或聚合。

## 6. 成功与验收

### 成功标准

- **SC-008**（沿用）：回放器仅以事件日志为输入还原整段仿真，与原运行逐帧一致。
- **SC-006**（沿用，订单簿逐帧切片）：订单簿逐帧自包含。

### 退出条件

| # | 条件 | 判据来源 |
|---|---|---|
| E1 | **逐帧一致性**：回放器仅以日志为输入，重建的价格、订单簿、账户状态与原运行**逐帧逐字段相等**。第一帧取自强制初态快照（事件 Schema §4.6.3） | SC-008 / KPI-012 / PR-018 |
| E2 | 产物为单文件 HTML，**离线打开可用**，无任何外部请求 | §3.1 / PR-018；用断网环境验收 |
| E3 | K 线视图与指标字典 §1.9 的周期定义一致，且只用已完成 K 线 | FR-020 / PR-020 |
| E4 | **总结报告**含条件性结论、效应量、置信区间与失效边界，且全部数值消费 §4.1 的上游 artifact，**不自行重算** | PR-019 |
| E5 | 回放器与报告**不导入** `kernel/`、`ledger/`、`book/`、`eventlog/` | §3.2；导入检查测试 |
| E6 | **交互控制与强平呈现**：回放器逐帧呈现价格曲线、订单簿深度、账户权益与仓位，支持拖拽定位到任意帧、变速与暂停；发生强平的帧在页面上有可见标注 | FR-019 |

### 验收清单

- [x] **AC-001** (`SC-008`, `KPI-012`, `PR-018`): 逐帧一致性——回放重建的价格、订单簿、
  账户状态与原运行**逐帧逐字段相等**。第一帧取自强制初态快照（事件 Schema §4.6.3）—
  tests: `tests/integration/test_replay_frame_consistency.py`
- [x] **AC-002** (`PR-018`): 产物为单文件 HTML，**离线打开可用**，无任何外部请求—
  自动测试 `tests/integration/test_replay_offline_single_file.py` 已通过；真实浏览器
  断网验收由 `tools/t403_offline_check.js` 验证通过（2026-08-12，零外部请求/零控制台错误）
  tests: `tests/integration/test_replay_offline_single_file.py`
- [x] **AC-003** (`FR-020`, `PR-020`): K 线视图与指标字典 §1.9 周期定义一致，且只用已
  完成 K 线 — tests: `tests/unit/replay/test_kline.py`
- [x] **AC-004** (`PR-019`): 总结报告含条件性结论、效应量、置信区间与失效边界，且全部
  数值消费 §4.1 上游 artifact，**不自行重算** — tests: `tests/integration/test_report_artifacts.py`
- [x] **AC-005** (`NFR-004`): 回放器与报告**不导入** `kernel/`、`ledger/`、`book/`、
  `eventlog/` — tests: `tests/unit/replay/test_no_kernel_import.py`
- [x] **AC-006** (`FR-019`, `E6`): 逐帧呈现价格曲线、订单簿深度、账户权益与仓位；
  支持拖拽定位到任意帧、变速播放与暂停；发生强平的帧带有可见标注 —
  tests: `tests/unit/replay/test_frame_presentation.py`

## 7. 测试、依赖与决策

### 测试策略

- 单元测试：K 线视图、导入检查、artifact manifest 校验。
- 集成测试：逐帧一致性（独立 observer oracle）、单文件离线验收、总结报告数值来源。
- 真实环境：断网环境手动验收单文件离线打开。

### 依赖

- 上游 Contract：`event-schema.md`、`metrics-dictionary.md`、`degenerate-states.md`。
- 上游 artifact：`report_artifacts.json` registry 与 0.1.2/0.1.3 产出的三类冻结产物。
- 下游消费者：`verify`（0.1.1 T603）与实验证据归档。

### 决策与风险

| 决策 / 风险 | 结论或缓解 | 理由 | 后续 |
|---|---|---|---|
| 回放器悄悄重新实现撮合，形成第二真源 | E5 导入检查挡不住重新实现；**E1 逐帧一致性才是真正防线** | 重新实现且不一致会立刻失败 | 不一致即失败 |
| 单文件内联大日志导致产物过大、浏览器卡死 | §3.3 允许降采样 | 产物可归档 | 一致性验收在完整日志做 |
| 报告数值与上游产物不一致 | E4 消费 §4.1 三类冻结 artifact 并核对哈希 | 报告层不自行重算 | manifest/registry/实际三方一致 |
| 逐帧 oracle 取自日志自身，形成循环自证 | E1 期望值**必须**由测试专用独立 observer 提供 | 见 §4.2 | 两条独立路径结果相等 |

## 8. 待确认问题

无
