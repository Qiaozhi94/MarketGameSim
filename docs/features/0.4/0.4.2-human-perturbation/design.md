---
kind: milestone
id: 0.4.2
version: "0.4"
related_features:
  - 0.4.1
  - 0.3.2
topics:
  - human-perturbation
  - paired-seed-control
  - stability-effect-size
doc_kind: design
created: 2026-09-20
updated: 2026-09-20
---

# 0.4.2：人类扰动实验 - 技术设计

> Spec: [`spec.md`](spec.md) | Tasks: [`tasks.md`](tasks.md)

## 0. 输入与约束

- 行为真相源：[`spec.md`](spec.md)；本文不复制需求正文，只写实现方案与边界。
- 架构决策：[`ADR-010`](../../../decisions/010-market-ecology-research-pivot.md)（研究方向）、
  [`ADR-011`](../../../decisions/011-market-engine-trader-layering.md)（L1/L2 分层）、
  [`ADR-006`](../../../decisions/006-realtime-free-trading-owner-terminal.md)（自由连续交易）。
- 全局不变量（数值口径、事件因果链、确定性）由
  [`架构文档`](../../../market-game-sim-architecture.md) 与
  [`docs/contracts/`](../../../contracts/matching.md) 唯一拥有；本文只引用。
- 上游载体：`0.4.1` 的 `StrategyRoster` 装配与 live 市场推进语义；`0.3.2` 的 owner 终端
  与会话审计链。本里程碑不改两者的既有接口语义。
- 硬约束：不修改 L1 既有合同；不修改 0.4.1 已冻结的质量与 stylized facts 口径。

## 1. 技术概要与影响面

三件事按依赖顺序落地：

1. **会话 artifact 冻结**——新增 `experiment/perturbation/session.py`：`PerturbationSession`
   的写入、读取与校验入口，格式带版本号与内容哈希。**必须先于任何 owner 自由场次落地**。
2. **同种子对照运行**——新增 `experiment/perturbation/paired.py`：以同一 `StrategyRoster`
   与种子构建基线臂与有人类臂，人类动作由冻结的动作序列在逻辑时点回放。
3. **效应量报告**——新增 `metrics/stability_effect.py`：三个稳定性指标的两臂分布、
   效应量与不确定性区间；bootstrap/配对统计**复用** `experiment/stats.py` 的既有原语，
   不新发明第二套区间算法。

影响面：`experiment/h2/live_market.py`（接受回放动作源，沿用既有非阻塞注入路径）、
`experiment/h2/owner_web.py`（自由会话结束时导出冻结 artifact）。**不影响**
`experiment/h2/runner.py` 的 0.3.1 配对轨与 0.4.1 的质量门路径。

## 2. 架构与模块边界

```text
L1 交易引擎（不改）
  kernel/ book/ ledger/ eventlog/
        ▲ 与 AI 委托完全相同的撮合/账本/风控路径
        │
L2 交易者策略层（0.4.1，不改）
  agent/strategy_layer/
        ▲ StrategyRoster 装配
        │
人类扰动（本里程碑新增）
  experiment/perturbation/session.py   会话 artifact 冻结格式 + 校验入口
  experiment/perturbation/paired.py    同种子两臂运行与配对
  metrics/stability_effect.py          稳定性效应量与区间（复用 experiment/stats.py）
```

边界规则：人类动作只能通过既有的外部注入路径进入内核，与 AI 委托共用撮合与风控；
本里程碑不新增事件类型，只在既有决策记录里补参与者类别标识。

## 3. 数据模型与 Migration

- `PerturbationSession`（新增，JSON）：`format_version`、`session_id`、`arm`
  （`baseline` / `human`）、`roster_id`、`seed`、`engine_config_digest`、
  `actions[]`（逻辑时点、墙钟时间戳、动作类型、价格/数量、原因码）、
  `observation_digest[]`、`content_hash`。
- `PerturbationEffectReport`（新增，JSON）：`pair_set_id`、`metrics{}`（每指标两臂分布、
  效应量、区间、失效边界）、`degenerate[]`（退化判定）、`content_hash`。
  **退化时效应量字段缺省**（不是 0），避免零功效被读成零效应。
- 无既有数据迁移：两类 artifact 均为新增文件，不改写 0.3.2 owner 会话或 0.4.1 质量报告。
- 兼容规则：`format_version` 变更必须是显式改动；旧版本 artifact 按其声明的版本解析，
  不就地改写语义。

## 4. 接口、Contract 与 Event

- 会话写入/读取（IR-601）：`write_session(path, session)` / `load_session(path)` /
  `validate_session(payload)`；校验失败返回稳定原因码，不抛裸异常。
- 动作回放：`replay_actions(actions, market)` 按逻辑时点把动作投递到既有非阻塞注入
  路径；时点对不齐时返回稳定原因码并判失败，不静默丢弃动作。
- 事件（TR-601）：**不新增事件类型**。参与者类别（`human` / `ai`）写入既有决策记录的
  `internal_state`，因果链仍由 `intent_id` / `decision_event_id` 承载。
- 报告入口：`build_stability_effect_report(pairs)`；统计原语来自 `experiment/stats.py`。

## 5. Runtime、Workflow 与并发

- 基线臂：用 `StrategyRoster` + seed 构建纯 AI 市场，无任何外部注入，逐点记录指标序列。
- 有人类臂：同一 roster + seed，动作源为 owner 实时终端（采集）或冻结动作序列（回放）。
- 并发：终端 HTTP 线程与推进线程仍由 `LiveMarket.lock` 串行化；动作投递非阻塞，
  人类思考时间不阻塞内核推进（ADR-006 的连续市场前提）。
- 采集与回放的关系：实时采集产出动作序列，回放臂用同一序列重跑；两者的差异（如有）
  由 Q-604 裁决如何报告，不在设计阶段假定二者等价。

## 6. UI 与可观测性

- 沿用 0.3.2 终端页面，不做界面重做；会话结束时导出冻结 artifact。
- 可观测产物：会话 artifact 与效应量报告；退化判定在报告顶层可见。
- CLI：`python -m market_game_sim.experiment.perturbation.paired`（基线/回放两臂），
  命令与端口在 `RUN.md` 记录。

## 7. 失败、恢复、安全与兼容

- owner 中途离开或断线：立即落盘为完整短会话，`actions[]` 保留已发生动作，不回滚。
- 动作回放对不齐：判失败并给稳定原因码；不得跳过动作或改写时点。
- 任一臂退化（零成交、单边空簿）：报告输出退化判定，效应量字段缺省。
- 安全与边界：artifact 不含直接身份信息与凭据；不连接真实账户或外部网络；
  产物一律标注 `experiment-preview`，不进入任何既有 evidence index。

## 8. 测试策略与验收映射

| AC | 主要测试 | 层次 |
|---|---|---|
| AC-601 | artifact 冻结格式的正反校验（合法落盘 / 缺字段与错版本号被拒） | 单元 |
| AC-602 | 短会话与空会话仍产出完整 artifact | 单元 + 集成 |
| AC-603 | 同种子基线逐点复现；回放对不齐给原因码 | 集成 |
| AC-604 | 人类与 AI 委托并存的批量因果链与参与者标识 | 集成 |
| AC-605 | 效应量报告：有效对照 + 退化对照两种输入 | 单元 + 集成 |
| AC-606 | 画像/对错判定字段与身份信息的拒绝用例 | 单元 |
| AC-607 | 产物不进入 evidence index 的守卫 | 集成 |

既有回归：0.4.1 质量门、0.3.1 配对轨与 0.3.2 终端测试必须全绿。

## 9. 已确认决策与残余风险

- 已确认：命题形态为效应量命题；artifact 格式先于第一场冻结；不判对错、不做画像；
  统计原语复用 `experiment/stats.py`；不新增事件类型。
- 残余风险 1：owner 的单场行为不可重复，重放臂与原场可能不完全等价——处置由 Q-604 裁决，
  在裁决前不得把重放臂结果当作原场结果报告。
- 残余风险 2：N 太小导致零功效——缓解是 Q-603 的功效分析前置于正式配对运行，
  并在报告里如实标注功效不足，而不是把区间压在 0 上宣称「无影响」。
- 残余风险 3：证据级别升级冲动——Q-601 未闭合前，任何结论只能以 `experiment-preview`
  形态呈现。

## 10. 待确认设计问题

- [ ] DQ-601: 动作序列的时点基准取逻辑秒还是墙钟毫秒，两者在回放对齐上的取舍？
- [ ] DQ-602: 基线臂与有人类臂是否共享同一进程内的 RNG 流，还是各自独立构建？
- [ ] DQ-603: 效应量的区间算法取配对 bootstrap 还是解析近似，`experiment/stats.py` 现有哪一支可直接复用？
