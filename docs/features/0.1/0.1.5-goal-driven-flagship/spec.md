---
kind: milestone
id: 0.1.5
parent: v0.1-belief-testing-laboratory
version: "0.1"
status: done
research_claim_status: established
research_claim_required: true
evidence_class: formal-research
research_evidence:
  - docs/experiments/0.1.5-evidence-index.json
gate_version: 1
created: 2026-08-14
updated: 2026-08-30
prerequisites:
  - 0.1.4
---

# 0.1.5：目标驱动代理与旗舰实验识别

> Spec: `spec.md` | Design: `design.md` | Tasks: `tasks.md`

## 0. 来源与意图

- **版本规格**：[`../spec.md`](../spec.md)（FR-021—FR-027、NFR-005、SC-009—SC-011）。
- **PRD 来源**：[`../../../market-game-sim-prd.md`](../../../market-game-sim-prd.md) §3.1、§12、§15。
- **上游决策**：[`ADR-003`](../../../decisions/003-goal-driven-agents-and-flagship-identification.md)。
- **Contract 来源**：[`agent-strategy.md`](../../../contracts/agent-strategy.md)、
  [`event-schema.md`](../../../contracts/event-schema.md)、
  [`degenerate-states.md`](../../../contracts/degenerate-states.md)。
- **一句话意图**：消除目标形成对制度处理的直接依赖，并用可审计的 `2 × 2` 设计建立或
  否定三类旗舰终点的正式研究声明。

## 1. 问题、目标与非目标

### 问题

当前目标仓位公式直接读取 `initial_bp/leverage_tier`，观察路径缺少逐代理增量公开 tape、
已完成 K 线和持久 EWMA；现有冲击与预置账户证据只能证明工程链路，不能识别制度约束
是否足以产生自发极端状态。

### 目标

- 将目标形成、制度可行域、订单准入和强平链分层并留下版本化证据。
- 冻结逐代理信息合同和 `SPONTANEOUS/STRESS/BENCHMARK` fail-closed 运行族。
- 以 `L × M` 四个制度 cell 和配对种子，对三个终点家族分别形成正式结论。

### 非目标

- 不实现完整效用最大化或在线学习。
- 不加入无价格冲击的外部承接池中介实验。
- 不把旧 0.1.2/0.1.3 工程示范重新标记为正式研究证据。

## 2. 用户场景

### US-501：运行自发涌现旗舰实验（Priority: P1）

作为市场机制研究者，我希望四个制度 cell 使用同一目标模型、偏好与配对随机路径，从零
仓位运行，以便把结果差异归因于 `L/M` 制度约束。

**独立测试**：提交含任一禁用注入字段的 `SPONTANEOUS` 配置必须在运行前被拒绝；合法
配置能生成四 cell manifest 与三终点家族结果。

### US-502：审计目标与约束链（Priority: P1）

作为复核者，我希望从成交回溯到信息游标、目标模型、约束前后仓位、订单与强平来源，
以便证明处理变量没有直接进入目标形成。

**独立测试**：改变非绑定制度参数不改变订单意图；约束绑定时只改变可执行规模。

### US-503：隔离压力与基准证据（Priority: P2）

作为研究者，我希望压力协议和工程基准不能混入旗舰证据，以便报告措辞与结论权限不会
因复用运行管线而漂移。

**独立测试**：跨运行族输入、provenance 或 evidence class 不匹配时，聚合器拒绝产物。

## 3. 范围与边界

### 范围内

- `risk_budget_linear_v1` 与 `risk_budget_threshold_v1` 两个目标模型。
- 全局公开成交 tape、逐代理游标、已完成 K 线、零成交 bar 和逐代理持久 EWMA。
- 三运行族、类型化 `StressProtocol`、决策审计字段、`2 × 2` 运行与三终点报告。
- 生命周期验证器、预注册、正式 evidence index 与结论守卫。

### 范围外

- 效用函数、RL/LLM、跨市场、外部承接池、真实账户或真实交易信号。

### 边界场景

- 未知信息字段、禁用注入字段、终点条件化冲击、跨族 provenance 一律 fail closed。
- 无成交 bar 继承前 close 且 `volume = 0`；没有任何成交时使用冷启动价格。
- 三个终点均可得到“支持”“不支持”或“证据不足”，不得为制造显著结果调整协议。

## 4. 需求

### 功能需求

- **FR-021**：`desired_position` 由 `risk_budget_linear_v1` 或
  `risk_budget_threshold_v1` 生成，不得读取 `L/M`、`leverage_tier`、`initial_bp`、
  `maint_bp` 或实验臂 ID；当前权益只作为私有状态参与风险预算。
- **FR-022**：每代理只消费 `(last_seen_market_event_id, market_data_event_id]` 内的公开
  成交与已完成全局 K 线，维护自己的持久 EWMA；信息集和内部状态 Schema 版本化且封闭。
  **游标只在该区间被完整消费且内部状态与证据事件成功提交后才原子推进**；中途失败时
  游标保持旧值，重试重新消费同一区间且对该区间幂等。
- **FR-023**：运行配置必须声明且只声明一个运行族。`SPONTANEOUS` 拒绝
  `agent_signals`、`extra_positions`、`extra_events`、合成冲击账户和结果条件化订单；
  `STRESS` 只接受有限、版本化、四 cell 相同的 `StressProtocol`；`BENCHMARK` 证据不可
  进入研究结论。
- **FR-024**：正式旗舰实验必须运行 `L(low/high) × M(low/high)` 四 cell，并按崩盘、
  暴涨、流动性枯竭三个终点家族分别执行预注册推断、方向不对称分析和报告。
- **FR-025**：决策证据至少包含 `goal_model_id/version`、`desired_position_units`、
  `executable_position_units`、`constraint_binding/reason` 与 `trigger_provenance`，并能沿
  因果外键回溯到观察、订单、成交、风险与强平。
- **FR-026**：只有 `SPONTANEOUS` 的正式预注册运行可产出 `formal-research` 证据；研究
  声明建立时必须登记 evidence index，旧工程示范、压力和基准产物不得越权。
- **FR-027**：R1—R5 每个成果门都必须由单条命令生成成果包（`RUN.md`、`manifest.json`、
  `replay.html`、`summary.md`），manifest 记录代码版本、配置哈希、种子计划与
  `evidence_class`；`engineering-demonstration` 与 `experiment-preview` 成果包的报告
  必须携带“不可作结论”声明，且不得写入正式 evidence index。**R5 的总结报告、限制说明、
  evidence index 与代表性回放必须提交进 `docs/experiments/`**，不得只存在于被 git 忽略
  的 `artifacts/`。

### 数据 / 实体需求

- **DR-501**：`InformationSetV1`、`AgentInternalStateV1`、`DecisionEvidenceV1` 与
  `StressProtocolV1` 必须有闭集字段、版本和确定性序列化。
- **DR-502**：正式 evidence index 必须保存配置哈希、代码版本、种子计划、预注册引用、
  三终点结果与 evidence class。

### 事件 / Trace 需求

- **TR-501**：代理观察与决策事件必须记录游标边界、Schema 版本及 FR-025 的审计字段。
- **TR-502**：触发来源只允许 `ENDOGENOUS_AGENT`、`LIQUIDATION`、`EXOGENOUS_STRESS`；
  `SPONTANEOUS` 不得出现 `EXOGENOUS_STRESS`。

### API / 接口需求

- **IR-501**：运行入口在执行前验证运行族与其允许字段，错误必须包含字段路径和拒绝原因。
- **IR-502**：报告入口按运行族和 evidence class 授权结论模板，禁止隐式降级或跨族聚合。

### UX 需求

不适用：本里程碑只修改仿真、证据与离线报告合同，不新增交互界面。

### 非功能需求

- **NFR-005**：相同代码、配置、种子与公开事件序列必须产生相同游标、EWMA、目标、约束
  结果和报告；未知字段与非法 provenance 必须拒绝。

## 5. 生命周期与不变量

```text
draft -> ready-for-development  三件套与 Contract 变更（T201）评审通过
ready-for-development -> in-progress  0.1.4 已 done，按 tasks 顺序实施
in-progress -> review  代码、正反回归测试、正式运行入口和证据 Schema 完成
review -> done  E1—E7、全部 AC、统一门禁与正式证据复核通过
not-established -> established  status=done 且 evidence_class: formal-research
                               且 research_evidence 列出存在的正式证据路径
```

**预注册门（T202）与生命周期门正交**：预注册冻结**不是**进入 `ready-for-development`
的条件，但在它冻结之前，只允许产出 `engineering-demonstration`（R1—R2 与运行族/证据
权限实现）；T213 起的统计实现、`experiment-preview`（R3）与任何 `formal-research`
产物一律阻塞。两个门的作用域不同：生命周期门管"能不能开工"，预注册门管"能不能声称"。

把预注册塞进 `ready-for-development` 会让 R1 这种纯工程包装也被研究前置卡住，与
[`PRD §15`](../../../market-game-sim-prd.md#15-交付路线图) 的 `R1 → R5` 顺序直接冲突；
而完全不设门则会让统计实现先看到模型行为再定口径。

不变量：目标模型不读取制度处理；三运行族互斥；四 cell 仅 `L/M` 不同；三终点不合成；
工程示范不建立研究声明；预注册冻结前不产出预览或正式研究证据；任何未知或越权输入
fail closed。

## 6. 成功与验收

### 成功标准

- **SC-009**：目标/约束解耦与逐代理信息合同通过静态、正反和确定性测试。
- **SC-010**：四 cell 正式运行分别输出三个终点家族的效应、不确定性与失效边界。
- **SC-011**：正式结论可完整回溯，且压力/基准/旧示范产物无法进入旗舰证据。

### 退出条件

| ID | 条件 |
|---|---|
| E1 | 两目标模型与制度字段解耦，非绑定/绑定约束正反测试通过。 |
| E2 | 公开 tape、逐代理游标、完成 K 线、零成交 bar、持久 EWMA 与封闭 Schema 通过确定性测试。 |
| E3 | 三运行族及 `StressProtocolV1` 的允许/拒绝矩阵与 provenance 测试通过。 |
| E4 | 0.1.2 T404—T407 的迁移任务完成，观察—目标—约束—订单—成交—强平链可审计。 |
| E5 | `L × M` 四 cell 和三终点家族预注册、配对运行、分别推断与报告完成。 |
| E6 | evidence index 仅引用 `formal-research` 自发运行；里程碑达到 `done / established`。 |
| E7 | R1—R5 五个成果门各自产出可单命令重建的成果包，`evidence_class` 正确且预览/示范产物携带“不可作结论”声明。 |

### 验收清单

- [x] **AC-001** (`FR-021`, `SC-009`): 目标层没有制度字段依赖，约束正反测试通过。
- [x] **AC-002** (`FR-022`, `DR-501`, `TR-501`, `NFR-005`, `SC-009`): 信息游标、K 线与
      EWMA 确定性通过；观察/决策事件记录游标边界与封闭 Schema 版本；**故障注入测试证明
      消费中途失败后重试不丢公开事件、不产生重复决策证据**。
- [x] **AC-003** (`FR-023`, `IR-501`, `NFR-005`): 三运行族非法输入和未知字段均 fail
      closed，且拒绝信息包含字段路径与原因。
- [x] **AC-004** (`FR-023`, `DR-501`): `StressProtocolV1` 有限、版本化、确定性序列化，
      且四 cell 逐事件一致。
- [x] **AC-005** (`FR-025`, `TR-501`, `TR-502`): 全部成交的目标—约束—订单—风险因果链
      机器可验证；`trigger_provenance` 为闭集且 `SPONTANEOUS` 无 `EXOGENOUS_STRESS`。
- [x] **AC-006** (`FR-024`, `SC-010`): `2 × 2` 配对计划和三终点预注册冻结。
- [x] **AC-007** (`FR-024`, `SC-010`): 三终点分别输出效应量、不确定性与方向不对称。
- [x] **AC-008** (`FR-026`, `IR-502`, `SC-011`): benchmark/stress/旧示范证据越权测试被
      拒绝，报告入口不做隐式降级或跨族聚合。
- [x] **AC-009** (`FR-026`, `DR-502`, `SC-011`): 正式 evidence index 完整（配置哈希、
      代码版本、种子计划、预注册引用、三终点结果与 evidence class）且所有路径存在。
- [x] **AC-010** (`NFR-005`): `python tools/verify.py` 全绿且正式运行可由 manifest 复现。
- [x] **AC-011** (`FR-027`, `NFR-005`): R1—R5 每个成果包可由单条命令重建，manifest 的
      `evidence_class` 与运行族一致，示范/预览报告携带“不可作结论”声明。
- [x] **AC-012** (`FR-027`, `SC-011`): **同一条命令**在 clean checkout（不含
      `artifacts/`）中同时生成 R5 成果包与仓库内交付入口；生成后非开发者从 README 两次
      点击内到达总结报告、代表性回放、限制说明与 evidence index，四者均为仓库内已提交
      路径、链接全部有效、回放离线可开。

## 7. 测试、依赖与决策

### 测试策略

- 单元测试覆盖目标模型禁用字段、游标边界、零成交 bar、EWMA 和运行族字段矩阵。
- 集成测试覆盖多代理/多成交批量因果链、四 cell 配对和跨族证据拒绝。
- 正式实验使用冻结预注册与 evidence index；单次运行不建立结论。

### 依赖

- 上游：0.1.4、ADR-003、代理策略/事件/退化状态合同。
- 下游：v0.1 根规格收口与 `releases/0.1.md`。

### 决策与风险

| 决策 / 风险 | 结论或缓解 | 理由 | 后续 |
|---|---|---|---|
| 目标模型 | linear 主模型 + threshold 稳健性 | 结构不同且实现边界可控 | 效用模型后移 |
| 三终点多重推断 | 三个独立家族 | 避免合成掩盖方向与机制 | 预注册各自校正 |
| 研究可能无显著结果 | 接受负面/证据不足结论 | 可证伪性要求 | 不按结果调参 |

## 8. 待确认问题

无
