---
kind: milestone
id: 0.4.2
version: "0.4"
related_features:
  - 0.4.1
  - 0.4.3
  - 0.3.2
topics:
  - human-perturbation
  - paired-seed-control
  - stability-effect-size
doc_kind: design
created: 2026-09-20
updated: 2026-10-15
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
- 上游载体：`0.4.1` 的 `StrategyRoster` 装配、live 市场推进语义与 owner 终端页面；`0.4.3`
  的价值投资者族与扫描格装配。本里程碑不改两者的既有接口语义。
- 硬约束：不修改 L1 既有合同；不修改 0.4.1 已冻结的质量与 stylized facts 口径。
- 0.3.2 的 `experiment/h2/owner_web.py` 已归档，且跑在另一套引擎（`AiFlowGenerator` +
  `InteractiveRuntime`）上，**不是**本里程碑的影响面；0.2.1 的 `interactive/journal.py` 只服务
  `InteractiveRuntime`，同样不复用。

## 1. 技术概要与影响面

按依赖顺序落地：

1. **会话 artifact 冻结**——新增 `experiment/perturbation/session.py`：`PerturbationSession`
   的写入、读取与校验入口，格式带版本号与内容哈希。**必须先于任何 owner 自由场次落地**。
2. **注入路径确定性修复**——改 `experiment/h2/live_market.py`：委托时间戳与 `submitted_at`
   改在 `advance()` 持锁取出时分配，`order_id` 序号在锁内递增，每条动作记录取出时的
   `advance` 序号；会话结束与断线时落盘 artifact。纯 AI 运行不经过这条路径，0.4.1/0.4.3
   的入库产物与摘要不受影响（由既有回归门证明）。
3. **载体与预热**——载体 C 的 roster 按种子用 `experiment/roster.py::save_roster` 落盘到
   `docs/experiments/0.4.2-rosters/`；live 市场新增预热：开放终端前连续调用 `advance()` 而不
   等待 `--tick-seconds`，推进到 0.4.1 的统计窗口起点。
4. **同种子对照与回放**——新增 `experiment/perturbation/paired.py`：以同一装配参数与种子
   构建基线臂与有人类臂；有人类臂的动作按 `advance` 序号在推进循环中投递（同种子重放 /
   开环跨种子回放）。
5. **效应量报告**——新增 `metrics/stability_effect.py`：四个稳定性指标的两臂分布、逐种子
   差值、效应量与区间。盘口可用率与大波动频次调用 0.4.1 既有实现（`quality_run.py` 的
   `two_sided_book_uptime`、`instability.py` 的分钟变动与强平连锁扫描，后者补窗口参数）；
   配对 bootstrap 原语加在 `experiment/stats.py`（见 DQ-603）。

影响面：`experiment/h2/live_market.py`（注入确定性、artifact 导出、预热、回放动作源）、
`metrics/instability.py`（扫描函数增加可选窗口参数，缺省行为不变）、`experiment/stats.py`
（新增配对 bootstrap 原语）。**不影响** `experiment/h2/runner.py` 的 0.3.1 配对轨与 0.4.1、
0.4.3 的质量门路径。

## 2. 架构与模块边界

```text
L1 交易引擎（不改）
  kernel/ book/ ledger/ eventlog/
        ▲ 与 AI 委托完全相同的撮合/账本/风控路径
        │
L2 交易者策略层（0.4.1 / 0.4.3，不改）
  agent/strategy_layer/            StrategyRoster 装配（含价值族）
        ▲
        │
live 市场（0.4.1，本里程碑改注入路径）
  experiment/h2/live_market.py     advance() 持锁取出 → 分配时间戳 → 记录 advance 序号
        ▲
        │
人类扰动（本里程碑新增）
  experiment/perturbation/session.py   会话 artifact 冻结格式 + 校验入口
  experiment/perturbation/paired.py    同种子两臂运行、同种子重放、开环回放与配对
  metrics/stability_effect.py          四指标效应量与区间（统计原语在 experiment/stats.py）
```

边界规则：人类动作只能通过既有的外部注入路径进入内核，与 AI 委托共用撮合与风控；
本里程碑不新增事件类型，只在既有决策记录里补参与者类别标识。

## 3. 数据模型与 Migration

- `PerturbationSession`（新增，JSON）：`format_version`、`session_id`、`arm`
  （`baseline` / `human`）、`replay_mode`（`original` / `same_seed_replay` / `open_loop_replay`）、
  `roster_id`、`seed`、`engine_config_digest`、`actions[]`（`advance_index`、`timestamp_ns`、
  `submitted_at_ns`、`order_id`、动作类型与载荷、`wall_clock`、受理原因码）、
  `observation_digest[]`、`event_digest`（原场事件摘要）、`content_hash`。
- `PerturbationPreregistration`（新增，JSON，单一文件）：功效分析报告引用、N、开环回放
  种子清单、最小可检出效应；sha256 由测试钉住，配对入口只读该文件。
- `PerturbationEffectReport`（新增，JSON）：`preregistration_sha256`、`pair_set_id`、
  `pairs[]`（种子、两臂运行标识、回放模式）、`metrics{}`（每指标两臂分布、逐种子差值、
  效应量、区间、失效边界）、`original_cases[]`、`degenerate[]`、`out_of_window_actions`、
  `content_hash`。**退化时效应量字段缺省**（不是 0），避免零功效被读成零效应。
- 无既有数据迁移：各类 artifact 均为新增文件，不改写 0.3.2 owner 会话或 0.4.1/0.4.3 质量报告。
- 兼容规则：`format_version` 变更必须是显式改动；旧版本 artifact 按其声明的版本解析，
  不就地改写语义。

## 4. 接口、Contract 与 Event

- 会话写入/读取（IR-601）：`write_session(path, session)` / `load_session(path)` /
  `validate_session(payload)`；校验失败返回稳定原因码，不抛裸异常。
- 动作回放：`replay_actions(actions, market)` 在推进循环中，于每次 `advance()` 取出阶段投递
  `advance_index` 等于当前序号的动作，按记录顺序入队；同种子重放结束后比较事件摘要，
  不一致返回 `REPLAY_DIVERGED`；动作序号早于当前序号（无法投递）返回稳定原因码并判失败，
  不得跳过动作或改写时点。
- 事件（TR-601）：**不新增事件类型**。参与者类别（`human` / `ai`）写入既有决策记录的
  `internal_state`，因果链仍由 `intent_id` / `decision_event_id` 承载。
- 报告入口：`build_stability_effect_report(pairs, preregistration)`；统计原语来自 `experiment/stats.py`。

## 5. Runtime、Workflow 与并发

- 基线臂：用 `StrategyRoster` + seed 构建纯 AI 市场，无任何外部注入，逐点记录指标序列。
- 有人类臂：同一装配参数 + seed，动作源为 owner 实时终端（采集）或冻结动作序列（回放）。
- 预热：live 市场启动后先不等待墙钟连续推进到窗口起点 `max(冷启动退出, 3660 s)`，期间终端
  只读、拒绝下单；起点不成立（仍有代理处于冷启动锚）时拒绝开放并给原因码。之后按
  `--tick-seconds` 节拍推进，窗口终点 5700 s 约对应 35—40 分钟墙钟。
- 并发：终端 HTTP 线程只把载荷放入队列，不读 `logical_ns`、不扫描内核队列、不分配序号；
  时间戳、`submitted_at` 与 `order_id` 全部在 `advance()` 持 `LiveMarket.lock` 取出时分配。
  人类思考时间不阻塞内核推进（ADR-006 的连续市场前提）。
- 采集与回放的关系：实时采集产出带 `advance_index` 的动作序列；由于落地点只由序号与载荷
  决定，同种子重放应与原场逐位一致，不一致即视为实现缺陷（`REPLAY_DIVERGED`），不作为
  可报告的「差异」（spec Q-604）。

## 6. UI 与可观测性

- 沿用 0.4.1 live 市场自带的 owner 终端页面，不做界面重做；预热期间页面显示预热进度并禁用
  下单；会话结束时导出冻结 artifact。
- 可观测产物：会话 artifact、功效分析报告、预注册文件与效应量报告；退化判定与载体未达标
  声明在报告顶层可见。
- CLI：`python -m market_game_sim.experiment.perturbation.paired`（基线/重放/开环三种运行），
  命令与端口在 `RUN.md` 记录。

## 7. 失败、恢复、安全与兼容

- owner 中途离开或断线：立即落盘为完整短会话，`actions[]` 保留已发生动作，不回滚。
- 同种子重放与原场不一致：`REPLAY_DIVERGED`，fail closed，该会话不进入配对。
- 动作回放无法投递（序号已过）：判失败并给稳定原因码；不得跳过动作或改写时点。
- 预注册文件缺失或哈希不一致：配对入口 fail closed。
- 任一臂退化（窗口内零成交、单边空簿）：报告输出退化判定，效应量字段缺省。
- 安全与边界：artifact 不含直接身份信息与凭据；不连接真实账户或外部网络；
  产物一律标注 `experiment-preview`，不进入任何既有 evidence index。

## 8. 测试策略与验收映射

| AC | 主要测试 | 层次 |
|---|---|---|
| AC-601 | artifact 冻结格式的正反校验（合法落盘 / 缺字段与错版本号被拒） | 单元 |
| AC-602 | 短会话与空会话仍产出完整 artifact | 单元 + 集成 |
| AC-603 | 同种子基线逐点复现；同种子重放逐位一致与篡改判失败；并发注入的确定性 | 集成 |
| AC-604 | 人类与 AI 委托并存的批量因果链与参与者标识 | 集成 |
| AC-605 | 效应量报告：有效对照 + 退化对照两种输入；回撤/涨幅窗口起点重置 | 单元 + 集成 |
| AC-606 | 画像/对错判定字段与身份信息的拒绝用例 | 单元 |
| AC-607 | 产物不进入 evidence index 的守卫 | 集成 |
| AC-608 | 载体清单哈希与参数；预热前拒单、预热后开放、起点不成立时拒绝开放 | 集成 |
| AC-609 | 预注册文件缺失/哈希不一致时配对入口 fail closed | 单元 |

既有回归：0.4.1 质量门、0.4.3 锚定市场门、0.3.1 配对轨与 0.3.2 终端测试必须全绿。

## 9. 已确认决策与残余风险

- 已确认：命题形态为效应量命题；artifact 格式先于第一场冻结；不判对错、不做画像；
  不新增事件类型；分析单元为种子、主效应量取开环回放（spec Q-601—Q-604）。
- 残余风险 1：开环回放把动作与市场状态的对应关系打断——限价单的绝对价格在其他种子上
  可能远离盘口。缓解是报告标签强制写「固定订单流扰动」，并逐场列出原场个案作对照。
- 残余风险 2：N 太小导致零功效——缓解是功效分析前置于正式配对运行（SC-605），并在报告里
  如实标注功效不足，而不是把区间压在 0 上宣称「无影响」。
- 残余风险 3：载体 C 在 20 个功效种子之外的种子上可能停摆或钉死——这类种子作为退化或
  失效边界如实报告，不替换种子。
- 残余风险 4：证据级别升级冲动——任何结论只能以 `experiment-preview` 形态呈现，升级须另立预注册。

## 10. 待确认设计问题

- [x] DQ-601: 动作序列的时点基准取逻辑秒还是墙钟毫秒，两者在回放对齐上的取舍？ — 决策：owner 2026-10-15 裁决以 `advance` 序号 + 分配的逻辑纳秒时间戳为对齐基准，墙钟只作辅助字段；仅记录屏幕上的逻辑秒不足以逐位重放（委托实际落在取出时刻之后的安全时点）。
- [x] DQ-602: 基线臂与有人类臂是否共享同一进程内的 RNG 流，还是各自独立构建？ — 决策：owner 2026-10-15 裁决两臂各自独立构建；市场对装配参数 + 种子完全确定，独立构建与共享等价且更易隔离。
- [x] DQ-603: 效应量的区间算法取配对 bootstrap 还是解析近似，`experiment/stats.py` 现有哪一支可直接复用？ — 决策：owner 2026-10-15 裁决取配对 bootstrap（逐种子差值重采样，报中位数与 [5%, 95%] 分位区间）；`experiment/stats.py` 现只有比例差的 `bootstrap_proportion_diff`，不能直接用于连续指标，故在同一模块新增连续指标的配对 bootstrap 原语，沿用其种子与重采样约定，不另建第二个统计模块。
