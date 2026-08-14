---
kind: milestone-design
id: 0.1.5
version: "0.1"
doc_kind: design
created: 2026-08-14
updated: 2026-08-14
---

# 0.1.5：目标驱动代理与旗舰实验识别 - 设计

> Spec: `spec.md` | Tasks: `tasks.md`

## 0. 输入与约束

- 行为与验收真相源：[`spec.md`](spec.md)。
- 决策真相源：[`ADR-003`](../../../decisions/003-goal-driven-agents-and-flagship-identification.md)。
- 现有实现合同：[`agent-strategy.md`](../../../contracts/agent-strategy.md)、
  [`event-schema.md`](../../../contracts/event-schema.md)。
- 约束：先改版本化 Contract 与测试，再切换生产路径；旧日志只能作为工程示范读取。

## 1. 技术概要与影响面

新增纯目标模型层、制度约束层、逐代理市场数据游标与运行族验证器；扩展事件证据和实验
聚合器，复用既有撮合、账本、强平、扫描与报告基础设施。

- Agent：目标模型、私有状态、EWMA、意图生成。
- Runtime：公开 tape、游标、完成 K 线与观察调度。
- Experiment：运行族、`StressProtocolV1`、四 cell 配对计划。
- Evidence：决策链、provenance、evidence class、正式索引与报告守卫。

## 2. 架构与模块边界

```text
public market tape + completed bars + private state
  -> GoalModel (不得依赖制度字段)
  -> desired_position
  -> InstitutionalConstraint(L, M)
  -> executable_position
  -> OrderIntent -> admission -> matching -> risk/liquidation
```

运行族验证发生在构造 simulator 之前；目标模型只接收封闭的 `InformationSetV1` 与
`AgentInternalStateV1`。制度字段通过独立参数对象进入约束、准入和风险链。

## 3. 数据模型与 Migration

- `InformationSetV1`：公开事件区间、完成 K 线、盘口快照与允许的私有账户状态。
- `AgentInternalStateV1`：`last_seen_market_event_id`、逐代理 EWMA 与模型私有状态。
- `DecisionEvidenceV1`：目标模型版本、约束前后仓位、绑定原因与 provenance。
- `StressProtocolV1`：有限事件列表、方向、规模、时刻和版本；不含终点条件。
- 历史事件 Schema 只读兼容；新正式研究运行拒绝缺失版本或未知字段。

## 4. 接口、Contract 与 Event

### Adapter Contract

`GoalModel.decide(information_set, internal_state, preferences, rng) -> GoalDecision`，返回
`desired_position_units` 与更新后的私有状态。参数类型不暴露制度或实验臂字段。

`InstitutionalConstraint.apply(goal, account, market, policy) -> ExecutableDecision`，只裁剪
可执行目标并记录 `constraint_binding/reason`。

### Event / Trace Contract

观察、决策、订单、成交、风险与强平事件以稳定外键相连。`trigger_provenance` 为闭集；
`SPONTANEOUS` 中发现 `EXOGENOUS_STRESS` 时整次运行无资格进入研究证据。

## 5. Runtime、Workflow 与并发

每次观察先按事件 ID 推进该代理游标，再消费区间内公开成交、更新 EWMA、读取已完成 K 线，
最后执行目标模型和制度约束。多个代理共享不可变公开 tape，但各自游标和内部状态独立；
批量处理按代理稳定 ID 排序，禁止索引位置承担身份语义。

四 cell 由同一冻结 seed plan 派生；`STRESS` 的协议事件键在四 cell 完全一致，不能读取
运行中结果。任何 cell 验证失败使整组配对证据失败。

## 6. UI 与可观测性

不新增 UI。离线报告必须展示运行族、目标模型版本、`L/M` cell、三终点家族、排除原因、
evidence class 与研究声明资格；缺项时报告生成失败。

## 7. 失败、恢复、安全与兼容

- 非法字段、未知版本、跨族 provenance、证据越权均抛出可定位的验证错误。
- 正式运行以 manifest + 事件日志 + evidence index 恢复；不从部分聚合结果续写结论。
- 旧配置显式迁移为 `BENCHMARK`，不自动猜测运行族。
- 不连接真实账户，不生成真实交易信号；安全边界沿用 PRD 与 SOP。

## 8. 测试策略与验收映射

| 验收项 | 测试层级 | 计划文件 / 场景 | 关键断言 |
|---|---|---|---|
| `AC-001` | unit + architecture | `tests/unit/agent/` | 目标接口不可读取制度字段；绑定只裁剪 |
| `AC-002` | unit + integration | `tests/unit/agent/`、`tests/integration/` | 多代理游标互不串位，零成交 bar/EWMA 确定 |
| `AC-003`—`AC-004` | unit | `tests/unit/experiment/` | 三族允许/拒绝矩阵；协议有限且 cell 相同 |
| `AC-005` | integration | `tests/integration/` | 多成交链全部外键存在且顺序合法 |
| `AC-006`—`AC-010` | integration + formal run | `tests/integration/`、`docs/experiments/` | 四 cell、三家族、证据权限与复现闭环 |

## 9. 已确认决策与残余风险

| 决策 / 风险 | 结论或缓解 | 理由 | 替代方案 / 后续 |
|---|---|---|---|
| 信息消费 | 全局 tape + per-agent cursor | 公开信息一致，观察频率仍可异质 | 私有 tape 排除 |
| K 线空档 | 前 close + 零 volume | 连续、确定、无伪成交 | 缺失值排除 |
| 外部承接池 | 后移 | 非 v0.1 识别必需 | 后续中介实验 |
| 统计效力不足 | 报告证据不足 | 不以结果驱动扩样或调参 | 新预注册再研究 |

## 10. 待确认设计问题

无
