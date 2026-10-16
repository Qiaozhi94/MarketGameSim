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
updated: 2026-10-16
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
  `InteractiveRuntime`，不复用其代码，只沿用 `interactive/adapter.py` 为人类动作补发
  `AGENT_DECIDE` 的做法。

## 1. 技术概要与影响面

按依赖顺序落地：

1. **会话 artifact 冻结**——新增 `experiment/perturbation/session.py`：`PerturbationSession`
   的动作日志追加、封口、读取与校验入口，格式带版本号与内容哈希。**必须先于任何 owner 自由
   场次落地**。
2. **注入路径确定性修复**——改 `experiment/h2/live_market.py`（见 §5「并发」）：HTTP 线程
   只入队载荷；`advance()` 持锁取出时分配 `order_id`、逻辑时间戳与 `submitted_at`，补发
   `AGENT_DECIDE`，记录 `advance` 序号并追加动作日志；进程正常结束时封口。
3. **载体与预热**——载体 C 的 roster 按种子用 `experiment/roster.py::save_roster` 落盘到
   `docs/experiments/0.4.2-rosters/`（构造方式同 `metrics/anchor_scan.py::config_roster`）；
   live 市场新增预热：开放终端前连续调用 `advance()` 而不等待 `--tick-seconds`。
4. **同种子对照与回放**——新增 `experiment/perturbation/paired.py`：以同一装配参数与种子
   构建基线臂与有人类臂；有人类臂的动作按 `advance` 序号在推进循环中投递。同种子重放在
   Phase 1 交付，开环跨种子回放在 Phase 2 交付。
5. **效应量报告**——新增 `metrics/stability_effect.py`：四个稳定性指标的两臂分布、逐种子
   差值、效应量与区间。盘口可用率与大波动频次调用 0.4.1 既有实现（`quality_run.py` 的
   `two_sided_book_uptime`、`instability.py` 的分钟变动与强平连锁扫描，后者补窗口参数）；
   配对 bootstrap 原语加在 `experiment/stats.py`（见 DQ-603）。

影响面：`experiment/h2/live_market.py`（注入确定性、决策记录补发、动作日志、预热、回放
动作源）、`metrics/instability.py`（扫描函数增加可选窗口参数，缺省行为不变）、
`experiment/stats.py`（新增配对 bootstrap 原语）。**不影响** `experiment/h2/runner.py` 的
0.3.1 配对轨与 0.4.1、0.4.3 的质量门路径；纯 AI 运行不经过注入路径，事件流与入库摘要不变
（由既有回归门与专门断言证明）。

`live_market.py` 的 `_snapshot` / `export_metrics` 自带 `max_drawdown`（累计峰值口径，即
0.4.1 报告 §12 记录的缺陷口径）与 `big-move`（逐 advance、非分钟），它们是 0.4.1 终端的
**遗留诊断**，不是本里程碑的指标；artifact 导出与效应量报告只读 `metrics/stability_effect.py`
的计算结果，不复用这两个字段。

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
  experiment/h2/live_market.py     advance() 持锁取出 → 分配字段 → 补发 AGENT_DECIDE → 追加日志
        ▲
        │
人类扰动（本里程碑新增）
  experiment/perturbation/session.py   动作日志 + 封口 + 校验入口
  experiment/perturbation/paired.py    基线臂、同种子重放、开环回放与配对
  metrics/stability_effect.py          四指标效应量与区间（统计原语在 experiment/stats.py）
```

边界规则：人类动作只能通过既有的外部注入路径进入内核，与 AI 委托共用撮合与风控；
本里程碑不新增事件类型，只为人类动作补发既有类型 `AGENT_DECIDE` 的实例。

## 3. 数据模型与 Migration

- `PerturbationSession`（新增）：动作日志为 JSONL，每受理一笔动作追加一行并 `flush`；封口
  记录为同目录下的 JSON。字段：`format_version`、`session_id`、`arm`（`baseline` / `human`）、
  `replay_mode`（`original` / `same_seed_replay` / `open_loop_replay`）、`seal_status`
  （`SEALED` / `UNSEALED`）、`roster_id`、`seed`、`engine_config_digest`、`actions[]`
  （`advance_index`、`timestamp_ns`、`submitted_at_ns`、`order_id`、`decision_event_id`、
  动作类型与载荷、`wall_clock`、受理原因码）、`end_advance_index`、`observation_digest[]`、
  `event_digest`（结束序号处的事件摘要）、`content_hash`、`evidence_class: experiment-preview`、
  `run_mode: interactive`。缺封口记录即 `UNSEALED`。
- `PerturbationPreregistration`（新增，JSON，单一文件）：功效分析报告引用、`σ_b` 与功效公式、
  处理会话内容哈希清单、逐指标 MDE、N、有效配对下限、开环回放种子清单；sha256 由测试钉住，
  配对入口只读该文件。
- `PerturbationEffectReport`（新增，JSON）：`preregistration_sha256`、`treatment_session_hash`、
  `pair_set_id`、`pairs[]`（种子、两臂运行标识、回放模式）、`metrics{}`（每指标两臂分布、
  逐种子差值、效应量、区间、实测 `σ_d`、功效判定）、`failure_boundary`（退化配对、中止配对、
  载体 SC-501 失效的种子，各带原因码）、`original_cases[]`、`out_of_window_actions`、
  `evidence_class: experiment-preview`、`run_mode: interactive`、`content_hash`。
  **有效配对数低于下限时效应量字段缺省**（不是 0），避免零功效被读成零效应。
- 无既有数据迁移：各类 artifact 均为新增文件，不改写 0.3.2 owner 会话或 0.4.1/0.4.3 质量报告。
- 兼容规则：`format_version` 变更必须是显式改动；旧版本 artifact 按其声明的版本解析，
  不就地改写语义。

## 4. 接口、Contract 与 Event

- 会话写入/读取（IR-601）：`append_action(journal, action)` / `seal_session(path, seal)` /
  `load_session(path)` / `validate_session(payload)`；校验失败返回稳定原因码，不抛裸异常。
- 动作回放：`replay_actions(actions, market, end_advance_index)` 在推进循环中，于每次 `advance()`
  取出阶段投递 `advance_index` 等于当前序号的动作，按日志顺序入队；同种子重放推进到
  `end_advance_index` 后比较事件摘要，不一致返回 `REPLAY_DIVERGED`；动作序号早于当前序号
  （无法投递）返回稳定原因码并判失败，不得跳过动作或改写时点。开环回放推进到 5700 s。
- 事件（TR-601）：**不新增事件类型**。每笔 owner 动作补发一条 `AGENT_DECIDE`（沿用 0.2.1
  `interactive/adapter.py` 的形状：`internal_state` 带参与者类别 `human` 与动作序号），委托的
  `intent_id` / `decision_event_id` 指向它，满足 `event-schema.md` §4.1 对 `origin = AGENT`
  的因果外键要求；补发的决策记录与委托同批入队（见 §5），计入事件摘要。
- 证据索引隔离（AC-607）：既有拦截点是 `showcase/evidence_index.py::_validate_common_scope`
  （只接受 `run_family = SPONTANEOUS` 且 `evidence_class = formal-research`）与
  `evidence/evidence_guard.py` 的 `RunMode.INTERACTIVE`；本里程碑的 artifact 与报告显式携带
  `experiment-preview` 与 `run_mode: interactive`，并有测试断言交给索引构建入口时被拒绝。
- 报告入口：`build_stability_effect_report(pairs, preregistration)`；统计原语来自 `experiment/stats.py`。

## 5. Runtime、Workflow 与并发

- 基线臂：用 `StrategyRoster` + seed 构建纯 AI 市场，无任何外部注入，逐点记录指标序列。
- 有人类臂：同一装配参数 + seed，动作源为 owner 实时终端（采集）或冻结动作日志（回放）。
- 预热：live 市场启动后先不等待墙钟连续推进到 `W0 = max(冷启动退出, 3660 s)`，期间终端只读、
  拒绝下单；推进到 5700 s 仍未退出冷启动时拒绝开放并给原因码。载体 C 种子 7 实测：到 3660 s
  需 2545 次 advance、墙钟约 164 s。之后按 `--tick-seconds` 节拍推进；**每次 advance 推进的
  逻辑时间不是固定 1 秒**，窗口 3660→5700 s 实测 1459 次 advance，`--tick-seconds 1.0` 下约
  28 分钟墙钟。`--tick-seconds` 帮助文字里「1:1 实时」的说法随 T1125 改正。
- 并发（注入确定性）：
  - HTTP 线程只做载荷校验并把载荷放入队列；不读 `logical_ns`、不扫描内核队列、不分配
    `order_id` 序号；
  - `advance()` 持 `LiveMarket.lock` 依次取出载荷，在同一临界区内为每笔动作分配 `order_id`、
    逻辑时间戳（同现有 `max(…, _safe_ts())` 口径）、`submitted_at`（取出时的逻辑时间）、补发的
    `AGENT_DECIDE` 及其时间戳，按「决策记录先于委托」的次序入队，记录当前 `advance` 序号并
    追加动作日志——决策记录与委托在同一次取出中分配，不在 HTTP 线程里生成任何字段；
  - 人类思考时间不阻塞内核推进（ADR-006 的连续市场前提）；
  - 回归测试用确定性交错钩子（在入队与 `advance()` 之间注入可控的调度点）构造「同一 advance
    内多笔提交」「提交恰在推进中途」两类交错，不用真线程碰运气。
- 采集与回放的关系：实时采集产出带 `advance_index` 的动作日志；由于全部字段只由序号与载荷
  决定，同种子重放应与原场逐位一致，不一致即视为实现缺陷（`REPLAY_DIVERGED`），不作为
  可报告的「差异」（spec Q-604）。

## 6. UI 与可观测性

- 沿用 0.4.1 live 市场自带的 owner 终端页面，不做界面重做；预热期间页面显示预热进度并禁用
  下单。
- 可观测产物：会话 artifact、功效分析报告、预注册文件与效应量报告；退化判定、功效判定与
  载体未达标声明在报告顶层可见。
- CLI：`python -m market_game_sim.experiment.perturbation.paired`（基线/重放/开环三种运行），
  命令与端口在 `RUN.md` 记录。

## 7. 失败、恢复、安全与兼容

- 市场进程被异常终止：动作日志已逐条落盘，会话为 `UNSEALED`，可作开环处理，不作原场个案。
- 同种子重放与原场不一致：`REPLAY_DIVERGED`，fail closed，该会话不进入配对。
- 动作回放无法投递（序号已过）：判失败并给稳定原因码；不得跳过动作或改写时点。
- 预注册文件缺失、哈希不一致或处理会话不在其中：配对入口 fail closed。
- 退化与中止按配对判定：退化配对（窗口内零成交、单边空簿、基线臂中止）与人类臂中止配对
  列入失效边界；有效配对数低于预注册下限时整份报告不出效应量。
- 安全与边界：artifact 不含直接身份信息与凭据；不连接真实账户或外部网络；
  产物一律标注 `experiment-preview` 与 `run_mode: interactive`，被 evidence index 入口拒绝（§4）。

## 8. 测试策略与验收映射

| AC | 主要测试 | 层次 |
|---|---|---|
| AC-601 | artifact 冻结格式的正反校验（合法落盘 / 缺字段与错版本号被拒） | 单元 |
| AC-602 | 逐条追加：任意动作后终止进程不丢动作、标 `UNSEALED`；空会话与多动作封口会话 | 单元 + 集成 |
| AC-603 | 同种子基线逐点复现；同种子重放逐位一致与篡改判失败；确定性交错下的注入 | 集成 |
| AC-604 | owner 与 AI 委托的因果外键都解析到 `AGENT_DECIDE`；并存批量场景 | 集成 |
| AC-605 | 效应量报告：有效 / 退化 / 人类臂中止三类输入；回撤/涨幅窗口起点重置；功效不足标注 | 单元 + 集成 |
| AC-606 | 画像/对错判定字段与身份信息的拒绝用例 | 单元 |
| AC-607 | artifact 与报告交给 evidence index 构建入口被拒；合规输入不受影响 | 集成 |
| AC-608 | 载体清单哈希与参数；预热前拒单、预热后开放、5700 s 仍未退出冷启动时拒绝开放 | 集成 |
| AC-609 | 预注册文件缺失 / 哈希不一致 / 处理会话不在其中时配对入口 fail closed | 单元 |
| AC-610 | 开环回放按序号投递并推进到 5700 s；配对集合可重建；撤单目标不存在时记原因码 | 集成 |

既有回归：0.4.1 质量门、0.4.3 锚定市场门、0.3.1 配对轨与 0.3.2 终端测试必须全绿；
纯 AI 运行的 0.4.1/0.4.3 入库摘要不变。

## 9. 已确认决策与残余风险

- 已确认：命题形态为效应量命题；artifact 格式先于第一场冻结；不判对错、不做画像；
  不新增事件类型；分析单元为种子、主效应量取开环回放（spec Q-601—Q-604）；功效分析取保守
  近似；owner 委托补发 `AGENT_DECIDE`（spec §7 决策表）。
- 残余风险 1：开环回放把动作与市场状态的对应关系打断——限价单的绝对价格在其他种子上
  可能远离盘口。缓解是报告标签强制写「固定订单流扰动」，并逐场列出原场个案作对照。
- 残余风险 2：`ρ ≥ 0` 假设不成立导致功效被高估——缓解是报告给出实测 `σ_d`，超出上界即标注
  功效不足，而不是把区间压在 0 上宣称「无影响」。
- 残余风险 3：载体 C 在 20 个功效种子之外的种子上可能停摆或钉死——这类种子作为退化或
  失效边界如实报告，不替换种子。
- 残余风险 4：证据级别升级冲动——任何结论只能以 `experiment-preview` 形态呈现，升级须另立预注册。

## 10. 待确认设计问题

- [x] DQ-601: 动作序列的时点基准取逻辑秒还是墙钟毫秒，两者在回放对齐上的取舍？ — 决策：owner 2026-10-15 裁决以 `advance` 序号 + 分配的逻辑纳秒时间戳为对齐基准，墙钟只作辅助字段；仅记录屏幕上的逻辑秒不足以逐位重放（委托实际落在取出时刻之后的安全时点）。
- [x] DQ-602: 基线臂与有人类臂是否共享同一进程内的 RNG 流，还是各自独立构建？ — 决策：owner 2026-10-15 裁决两臂各自独立构建；市场对装配参数 + 种子完全确定，独立构建与共享等价且更易隔离。
- [x] DQ-603: 效应量的区间算法取配对 bootstrap 还是解析近似，`experiment/stats.py` 现有哪一支可直接复用？ — 决策：owner 2026-10-15 裁决取配对 bootstrap（逐种子差值重采样，报中位数与 90% 分位区间）；`experiment/stats.py` 现只有比例差的 `bootstrap_proportion_diff`，不能直接用于连续指标，故在同一模块新增连续指标的配对 bootstrap 原语，显式传 `ci_level = 0.90`，重采样次数与种子取 10000 / 0（与 `bootstrap_proportion_diff` 的缺省一致），不另建第二个统计模块。
