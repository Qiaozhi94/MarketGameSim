---
kind: milestone-design
id: 0.1.5
version: "0.1"
doc_kind: design
created: 2026-08-14
updated: 2026-08-15
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

### T201 必须冻结的清单（代码前置，不得边实现边定）

上面两个 Adapter 签名只给出**接口形状**，不构成可实现的语义。以下每一项都会直接改变
实验结果，因此必须在 T201 里写进版本化 Contract 并配 golden vector，**不能留给实现者
在写代码时顺手决定**——那等于让实现细节反过来定义研究对象：

1. ~~**目标模型数学**~~ — **已冻结**于
   [`agent-strategy.md §5.2.1—§5.2.2`](../../../contracts/agent-strategy.md)：
   `risk_appetite` 作为偏好参数替代 `leverage_tier` 进入风险预算、linear 与 threshold
   （含滞回）的方程、取整与饱和方向、标准化沿用 v1。`θ_in/θ_out/k` 的取值属实验设计，
   在 T202 预注册冻结。
2. ~~**退化输入的确定行为**~~ — **已冻结**于 `agent-strategy.md §5.2.3`：mark 未定义
   跳过决策、`equity ≤ 0` 只允许减仓、EWMA 样本不足时目标为 0。
3. ~~**约束层边界**~~ — **已冻结**于 `agent-strategy.md §5.2.4`：挂单与预留费用计入
   占用、绑定判定用观察时刻快照、只裁剪规模不改方向（含穿零边界算例）。
4. **四个 V1 Schema**：`InformationSetV1`、`AgentInternalStateV1`、`DecisionEvidenceV1`、
   `StressProtocolV1` 的逐字段类型、可空性、取值域、版本字段与确定性序列化顺序。
   **序列化口径已定**：字段按名称字典序、整数不带前导零、`null` 显式写出、哈希复用
   0.1.4 的 blake2b/64 位小写十六进制。**`DecisionEvidenceV1` 只存外键与游标边界，
   不内嵌信息集副本**——内嵌会让日志体积随代理数增长，并制造第二份可能与 tape 不
   一致的真相。剩余逐字段表由 T201 产出。
5. **三运行族逐字段 allow/deny 矩阵**：每个配置字段在 `SPONTANEOUS`/`STRESS`/
   `BENCHMARK` 下是必需、可选还是禁止，以及拒绝信息里的字段路径格式。
   **立场已定：白名单**——未在矩阵中列出的字段一律拒绝。黑名单在新增配置字段时默认
   放行，而"默认放行"正是 `SPONTANEOUS` 最怕的注入路径。

第 1—3 项的语义已经冻结，T201 的剩余产出是**把它们变成参数化测试能直接消费的数据**：
golden vector（含 §5.2.4 的穿零算例）、逐字段 Schema 表、allow/deny 矩阵。

## 5. Runtime、Workflow 与并发

每次观察的顺序是**先消费、后推进游标**（与
[`agent-strategy.md §1`](../../../contracts/agent-strategy.md) 的"消费完成后才原子推进"
一致）：

1. 读取当前游标 `last_seen_market_event_id`，取本次观察的 `market_data_event_id`；
2. 消费半开区间 `(last_seen, current]` 内的公开成交，更新 EWMA、读取已完成 K 线；
3. 执行目标模型与制度约束，写出观察/决策证据事件；
4. **上述全部成功提交后**，才把游标原子推进到 `current`。

**游标推进必须与内部状态更新在同一次提交里生效，不得先推进后消费。** 若在第 2—3 步
之间失败，游标保持旧值，重试将重新消费同一区间——代价是需要保证 EWMA 与证据写入对
同一区间幂等（重试不得产生两份决策证据）；反过来若先推进游标，任何中途失败都会让
这段公开事件对该代理永久消失，而这类丢失在结果里表现为"该代理恰好没反应"，与正常
行为无法区分，事后也无法从日志辨认。

多个代理共享不可变公开 tape，但各自游标和内部状态独立；批量处理按代理稳定 ID 排序，
禁止索引位置承担身份语义。

四 cell 由同一冻结 seed plan 派生；`STRESS` 的协议事件键在四 cell 完全一致，不能读取
运行中结果。任何 cell 验证失败使整组配对证据失败。

## 6. UI 与可观测性

不新增 UI。离线报告必须展示运行族、目标模型版本、`L/M` cell、三终点家族、排除原因、
evidence class 与研究声明资格；缺项时报告生成失败。

成果包（`FR-027`）默认落在被 git 忽略的 `artifacts/showcase/<gate>/`（`<gate>` 为
`R1`—`R5`，另有 `latest` 符号别名指向最近一次运行），固定包含 `RUN.md`（重建命令与
边界声明）、`manifest.json`（代码版本、配置哈希、种子计划、`evidence_class`）、
`replay.html` 与 `summary.md`。

**R5 交付入口不得链接被忽略目录**：`artifacts/` 在 clean checkout 里不存在，README
指过去必然断链，而断链只有在别人克隆仓库时才会发现。因此 R5 必须把三类产物提交进
仓库：

| 产物 | 仓库内路径 | 说明 |
|---|---|---|
| 总结报告与限制说明 | `docs/experiments/0.1.5-flagship-report.md` | 正式结论、效应量、失效边界 |
| evidence index | `docs/experiments/0.1.5-evidence-index.json` | `formal-research` 证据清单 |
| 代表性回放 | `docs/experiments/0.1.5-representative-replay.html` | 单文件、离线可开、降采样后 ≤ 5 MB |

代表性回放**提交进仓库**而不是只留重建命令：R5 的受众按定义是非开发者，"先装依赖再
跑一条命令"对他们等于不可达。5 MB 上限由生成器在 R4 阶段校验，超限时降采样并在页面
上标注降采样比例（0.1.4 §3.3 已有该机制）。其余成果包（R1—R4）仍只留在 `artifacts/`，
以 `RUN.md` 的单命令重建。`evidence_class` 取值与生命周期约束由
[`docs/features/README.md`](../../README.md) 拥有，成果包只引用不重定义；
`engineering-demonstration` 与 `experiment-preview` 的报告必须由生成器写入
“不可作结论”声明，缺失即生成失败，不允许仅在人工措辞上约束。

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
| `AC-011` | integration | `tests/integration/test_showcase_bundle.py`、`test_goal_driven_showcase.py`、`test_flagship_preview.py` | 单命令重建成果包；manifest `evidence_class` 与运行族一致；预览/示范带“不可作结论”声明 |
| `AC-012` | integration | `tests/integration/test_delivery_entry.py` | clean checkout（不含 `artifacts/`）中 README → 报告/回放/限制说明/evidence index 深度 ≤ 2、链接全部有效、回放离线可开且 ≤ 5 MB |

## 9. 已确认决策与残余风险

| 决策 / 风险 | 结论或缓解 | 理由 | 替代方案 / 后续 |
|---|---|---|---|
| 信息消费 | 全局 tape + per-agent cursor | 公开信息一致，观察频率仍可异质 | 私有 tape 排除 |
| K 线空档 | 前 close + 零 volume | 连续、确定、无伪成交 | 缺失值排除 |
| 外部承接池 | 后移 | 非 v0.1 识别必需 | 后续中介实验 |
| 统计效力不足 | 报告证据不足 | 不以结果驱动扩样或调参 | 新预注册再研究 |
| 风险预算来源 | `risk_appetite` 偏好参数，与 `leverage_tier` 独立抽取 | 保住"权益是私有状态"的同时，把制度放大器退回约束层 | 效用模型后移 |
| `L` 水平 | low `{2x,3x,5x}` / high `{10x,20x,50x}` | 50x 对应约 2% 回撤即触及爆仓，是"能出事但不必然出事"的位置；3x—10x 跨度在机制上偏小 | 若三家族均无效应，先查是否规模不足再改设计 |
| `M` 水平 | low `300bp` / high `700bp` | 0.1.3 参数扫描实测强平率 0→31→805，失效边界落在 `[500,700]`，该取值跨过已知边界 | 边界不插值为精确临界值 |
| `L/M` 正式冻结时点 | T202 预注册 | 本表只是设计输入，预注册才是研究口径的真源 | — |

## 10. 待确认设计问题

无
