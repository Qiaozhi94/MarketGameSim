---
kind: milestone
id: 0.3.1
version: "0.3"
related_features:
  - 0.2.1
topics:
  - human-in-the-loop
  - paired-counterfactual
  - formal-research
doc_kind: design
created: 2026-09-04
updated: 2026-09-12
---

# 0.3.1：H2 AI 机制正式基线 - 设计

> Owner: TBD | Spec: `spec.md` | Tasks: `tasks.md`

## 0. 输入与约束

2026-09-12 范围修订后的规范输入是
[`H2-dual-track-contract`](../../../experiments/H2-dual-track-contract.md)：当前里程碑的 AI 正式轨使用
**168 个** paired-seed blocks（三个家族的 0.25 SD SESOI 各需 168，见
[`H2-block-power-baseline`](../../../experiments/H2-block-power-baseline.md)、
[`H2-endpoint-calibration`](../../../experiments/H2-endpoint-calibration.md)、
[`H2-cascade-calibration`](../../../experiments/H2-cascade-calibration.md)）。所有者 N-of-1 的
窗口、输入链、K 线和隐私边界只作为 0.3.2 的下游合同；本里程碑只交付 AI `formal-research`，
研究声明只能由 AI 轨建立。本文按新的范围完成重基线；任何冲突均以合同为准。

- **行为契约**：[`spec.md`](spec.md)。
- **PRD / Architecture / Research**：[`PRD §15`](../../../market-game-sim-prd.md#15-交付路线图)、
  [`architecture`](../../../market-game-sim-architecture.md)、
  [`methodology`](../../../research/methodology.md)、
  [`metrics dictionary`](../../../research/metrics-dictionary.md)。
- **上游 Contract**：[`event-schema`](../../../contracts/event-schema.md)、
  [`agent-strategy`](../../../contracts/agent-strategy.md)、
  [`interactive-session`](../../../contracts/interactive-session.md)。
- **实现约束**：复用唯一市场内核；H1 `interactive` 保持隔离；AI 正式采样在剩余 Q/DQ
  关闭、preview 通过和协议冻结前不可开始。项目不招募外部真人；所有者采集由 0.3.2 负责。

## 1. 技术概要与影响面

在 H1 会话适配器外新增实验编排层。编排器加载内容寻址协议和签发的 assignment，当前按
`ai-mechanism-experiment` 成对执行两个冻结策略；owner 的 `run_mode`、窗口和输入合同只
保留兼容边界，由 0.3.2 Web 终端接入。独立 evidence guard 对模式、阶段、协议、pair、排除
状态和哈希执行 fail-closed 校验；分析器以 AI seed block 为单位生成三个结果家族和机制表。

- 前端：固定假参与者 preview 状态、倒计时、中止状态与解盲合同；生产 owner Web 终端移至 0.3.2。
- 后端 / API：协议冻结、AI assignment、窗口控制和样本裁决；无 enrollment/同意流程。
- 存储 / Migration：文件型 protocol/assignment/session/evidence artifact；不引入数据库。
- Runtime / Agent Adapter：新增 H2 专用目标插槽替换适配器，以及占用同一插槽的**窗口匹配
  参照代理**（主对照决策生产者，须受同一窗口调度器约束）；目标代理仍保留在冻结
  `agent_specs` 与账户集合中，但正式处理运行禁用其策略决策入口，由规范人类输入接管同一
  `agent_id`、账户、初始资金、杠杆与风险参数。`owner-n-of-1` 禁止沿用 H1
  `extra_accounts["human"]` 的新增账户路径；撮合、账本、保证金和强平生产路径保持不变。
- Event / Evidence：新 `ai-mechanism-experiment` mode、sample stage、协议/pair 元数据与 AI
  evidence index；owner evidence index 由 0.3.2 独立生成。
- 文档 / 配置：预注册、数据字典、运行手册、AI 报告和下游 Web 接口边界。

## 2. 架构与模块边界

```text
Frozen Protocol -> Assignment Ledger -> Experiment Session Controller
                                             |
Preview Client -> canonical input ------------+-> existing market runtime/event log
                                             |
Paired pure-agent runner --------------------+-> pair validator
                                                   |
                                      formal evidence guard
                                                   |
                          outcomes + mechanisms + report/replay
```

- H2 冻结协议计划放在 `src/market_game_sim/experiment/h2/protocol.py`；它拥有参与者、分配、
  窗口、停止和分析预注册，不替代既有 `experiment/protocol.py` 的三区运行约束，也不替代
  `experiment/stress_protocol.py` 的外生压力合同。共享内容寻址工具可以抽取复用，但三类
  protocol 的 schema、错误码和 evidence guard 不得互相冒充。
- H2 `protocol` 是本研究设计唯一真相源，冻结后内容寻址且不可原地修改。
- `assignment` 在采样前决定参与者、seed block、顺序和目标代理，不读取运行结果。
- `experiment session controller` 只负责窗口、状态和输入规范化，不复制撮合/风控业务逻辑。
- `target-slot adapter` 只替换冻结目标插槽的决策生产者，不新增或删除账户；处理与控制运行的
  账户集合、初始资金总量、背景 `agent_specs` 和制度配置必须逐字段相同。
- `pair validator` 要求比较矩阵中标为“相同”的字段逐字段一致（含账户、初始资金、信息集、
  动作空间与**窗口调度参数**）；AI 决策生产者与策略 ID/version/参数/显式目标按矩阵披露。
  `OWNER_N_OF_1` 的 owner 运行不在本里程碑进入 AI pair 完整性判定。
- `analysis` 只读取冻结 evidence index，不扫描 artifact 目录自动挑样本。
- 三类机制指标的规范定义只写入 `docs/research/metrics-dictionary.md`；protocol 保存字典版本与
  指标 ID，分析器不得复制公式或按本地实现重新解释口径。
- 身份/联系信息由研究流程外部保管，本仓库仅处理不可直接识别的研究假名。

## 3. 数据模型与 Migration

计划新增版本化 JSON schema：

- `protocol.json`：研究问题、假设、estimand、结果/机制字典、样本/停止、任务、窗口、顺序、
  排除、分析、结论语法、`AI_FORMAL`/`OWNER_N_OF_1` 证据级别、解盲规则及 `protocol_hash`。
- `owner.jsonl`：所有者研究假名与训练完成状态；不采集外部参与者，不含姓名或联系方式。
- `assignments.jsonl`：`assignment_id`、`run_mode`、`pair_id`、seed/config、session order、
  target slot、签发协议哈希。
- session manifest：运行与阶段元数据、输入/事件/artifact 哈希、完整性、技术状态。
- `adjudication.jsonl`：按冻结 reason code 记录 included/excluded/aborted，保留裁决时间和依据。
- evidence index：只列纳入 pair 及协议哈希，不复制身份资料。

H2 预注册采用双层机器门：`docs/experiments/H2-preregistration.md` 进入现有
`validate_preregistrations`，校验研究问题、参数归属和冻结字段不缺项；H2 `protocol.json`
schema 校验参与者、assignment、窗口、停止、排除和分析的可执行字段。freeze manifest 分别
保存两份文件的 SHA-256，`protocol.json` 另引用预注册 ID 与摘要；任一缺失、摘要不匹配或漂移
均不得 freeze。T904/T916 必须为两层门禁各提供失败与通过用例。

事件 header 的兼容修改将事件 schema 从 v4 提升为 v5。读取入口按版本分派：v4 日志保持
只读回放兼容但不补填 H2 字段且不能通过 H2 guard；v5 承载 H2 正式字段；未知版本继续
fail closed。该变更必须记录 ADR，且不得把 v4 日志迁移或重写为 H2 正式证据。

## 4. 接口、Contract 与 Event

### API / CLI / Adapter Contract

统一沿用仓库的 `python -m` 入口；本里程碑不增加 `[project.scripts]`，不得在文档或交付说明
中使用不存在的 `market-game-sim` console script：

- `python -m market_game_sim.experiment protocol validate|freeze <path>`：验证完整性并生成内容哈希，
  只允许从 draft 产生新冻结版。
- `python -m market_game_sim.experiment assign|train|run|abort`：每步要求上一状态的不可伪造
  引用；`run <assignment> --arm linear|threshold` 运行策略条件，`run <assignment> --arm owner`
  运行所有者条件。`control_arm` 闭集为 `linear | threshold | owner`，CLI 直接复用该枚举，
  不维护第二套名称映射；AI 轨 assignment 要求两条策略齐备，所有者轨额外要求 owner 条件。
- `python -m market_game_sim.experiment protocol preview <path>`：只生成 `experiment-preview`
  协议与 guard 验收产物，不产生正式证据。
- `python -m market_game_sim.experiment adjudicate|analyze|deliver`：阶段严格分离，正式命令只读
  显式冻结的 evidence index。

错误码至少区分协议未冻结/漂移、assignment 不匹配、窗口关闭、阶段非法、pair 漂移、技术
中止、撤回和证据不合格。protocol、participant、assignment、session-manifest、adjudication、
evidence-index 六类对象各自使用版本化 schema；正式写入绑定 `protocol_hash` 并原子落盘。

### Event / Trace Contract

`RUN_HEADER` 计划增加 spec TR-301 字段；人类窗口写 `HUMAN_WINDOW_OPEN/CLOSE` 或等价可审计
边界，合法输入沿用 `AGENT_DECIDE -> ORDER_* -> TRADE/ACCOUNT/LIQUIDATION` 因果链，超时写
`NO_ACTION`。事件全序继续由逻辑时间与既有优先级合同拥有；墙钟开闭时间只用于依从性诊断，
进入 artifact 哈希但不进入市场结果摘要。

## 5. Runtime、Workflow 与并发

- 每个正式 assignment 只允许一个活动 session；通过文件锁/CAS 防止重复启动与重复纳入。
- 客户端输入带 `window_id + input_seq`；控制器只在窗口开放、未提交时接受一次规范决定。
  窗口使用半开区间 `[open_monotonic_ns, deadline_monotonic_ns)`；唯一线性化点是服务端会话锁内
  成功占用该窗口的最终动作槽，且必须满足 `received_monotonic_ns < deadline_monotonic_ns`。
- 截止事件与输入竞争同一把会话锁，以谁先占用最终动作槽裁决；不设置隐藏宽限。迟到输入
  稳定返回 `WINDOW_CLOSED`，无有效输入写 `NO_ACTION`，均不回拨逻辑时间。
- 控制运行可预生成，但必须使用与处理运行相同的冻结代码/config/seed；代码变化使 pair 失效。
- 每个 AI assignment 预生成两条策略运行：`risk_budget_linear_v1` 与
  `risk_budget_threshold_v1`，构成配对 block。窗口调度参数进入冻结字段白名单与
  `protocol_hash`；owner 场景所需的 `WINDOW_MATCHED_POLICY_CONTROL` 由 0.3.2 复用，不在此处
  生成 owner 运行。
- 背景代理随机数继续使用既有语义键
  `(master_seed, agent_id, mechanism, decision_index, draw_index)`；禁止改成跨代理共享的可变
  计数器。pair manifest 绑定 RNG contract 版本，确保替换目标插槽不会仅因抽样游标错位改变
  其他代理的随机流；由处理引起的观察和调度路径分叉仍属于合法处理效应。
- 首个正式样本前随 assignment 一并签发有序备用 seed/pair 池。技术补跑只能按冻结顺序消耗
  下一个备用项；对应纯代理控制须在处理结果对 assignment/adjudication 不可见时生成并锁定。
  原 seed/pair 不得复用，备用项的启用和未启用状态都进入样本流图。
- session 完成不等于纳入；adjudication 只读取技术/协议字段，结果字段对裁决器不可见。
- 正式停止检查只基于冻结样本计数/统计规则；任何中期查看权限在协议内明确。

## 6. UI 与可观测性

- Preview 页面：边界说明、标准任务、固定输入结果和正式态提示；无外部参与者，故无同意/资格流程。
- 下游 Web 页面：只显示冻结观察子集、本人状态、逻辑进度、窗口倒计时和输入回执；隐藏 pause、
  step、配置、种子和其他代理私有信息，由 0.3.2 具体实现。
- 状态映射：waiting、active-window、submitted、no-action、completed、technical-abort、aborted。
- 研究控制台只显示 AI session 健康、协议/assignment 哈希和故障；owner 解盲规则由 0.3.2 执行。
- 诊断记录窗口延迟、断线和客户端版本，但不得收集键盘内容、屏幕录制或无关行为遥测。

## 7. 失败、恢复、安全与兼容

- 校验与失败映射：协议/阶段/pair 任一不合法即在证据写入前失败；市场事务沿用原子提交。
- 重启与恢复：H2 首版正式 session 不允许从提交边界恢复或拼接日志。服务端、日志或完整性
  故障写 `TECHNICAL_ABORT`；原运行保留但排除，只能从预签发备用池取得新 session/seed/pair
  整局补跑，并在 adjudication 中用 `rerun_of_session_id`、`supersedes_pair_id` 保留审计链。
- 权限 / escalation / 凭据边界：loopback 优先，无交易凭据；研究 ID 不承担身份认证用途。
- 隐私：本仓库不保存真实身份映射；日志白名单化，发布前运行 PII 扫描和人工复核。
- Windows / POSIX / 版本兼容：复用 H1 支持矩阵；窗口计时使用单调钟，市场仍只读逻辑时间。

## 8. 测试策略与验收映射

| 验收项 | 测试层级 | 计划文件 / 场景 | 关键断言 |
|---|---|---|---|
| `AC-301` | unit / contract | `tests/unit/experiment/test_h2_protocol.py` | 完整冻结、漂移新哈希、旧 assignment 拒绝 |
| `AC-302` | integration / preview | `tests/integration/test_experiment_session.py` | 有限窗口、超时、preview 无特权控制 |
| `AC-303` | integration | `tests/integration/test_h2_evidence_guard.py` | 模式/阶段/协议/pair 拒绝且零部分输出 |
| `AC-304` | integration | `tests/integration/test_h2_paired_runs.py` | 比较矩阵中标为“相同”的字段逐字段一致、目标差异分别披露、主对照复现、处理重放、次要对照标为描述性 |
| `AC-305` | unit / research | `tests/unit/experiment/test_h2_outcomes.py` | 三家族、双侧区间、多重性、无综合分数 |
| `AC-306` | unit / integration | `tests/unit/experiment/test_h2_mechanisms.py`、`tests/integration/test_h2_mechanisms.py` | 三机制及 AI 决策因果追溯 |
| `AC-307` | E2E / research | `tests/integration/test_h2_delivery.py` | index-only 重建、哈希与结论语法 |
| `AC-308` | contract / manual | `tests/unit/experiment/test_h2_privacy.py`、`tests/integration/test_experiment_session.py` | PII 拒绝、preview 阶段提示、下游隐私边界 |

preview 使用固定假参与者输入覆盖放大、稳定、无检出、缺失 pair、断线和中止路径；正式研究
结果不作为单元测试 fixture 提交。真实 owner 的 Web 训练/正式验收属于 0.3.2，仍不得回流为
本里程碑的 preview fixture。

## 9. 已确认决策与残余风险

| 决策 / 风险 | 结论或缓解 | 理由 | 替代方案 / 后续 |
|---|---|---|---|
| 控制设计 | 当前只收口 AI 正式 block 配对 threshold/linear；owner 的同 seed 反事实由 0.3.2 复用 | 先闭合可独立交付的研究包 | 0.3.2 以同一协议接口接入 |
| 窗口匹配 | 两条纯代理对照必须跑同一有限窗口调度器，调度参数进入三条件冻结字段白名单 | 否则描述性对比会混入决策机会变化 | 由 `pair validator` 与 AC-304 断言执行 |
| 估计单位 | 当前为 AI paired-seed block；owner × paired scenario 属于 0.3.2 | 同模型调用不是独立人类，个人多局也不独立 | 两里程碑分别建模且禁止合并 |
| 分配 | 当前预先签发 AI seed 计划；owner 场景顺序作为 0.3.2 输入 | 先避免 owner 时间成为 AI 研究阻塞 | 0.3.2 冻结 owner 顺序与备用池 |
| 正式交互 | owner 固定窗口、无暂停/单步是 0.3.2 合同 | H1 自由操作不适合作正式个人比较 | 由 0.3.2 Web 终端实现 |
| 证据准入 | 新 mode + stage + protocol + pair 多重闭锁 | mode 单字段不足以防误纳 | guard 矩阵覆盖缺失/伪装 |
| 隐私风险 | 当前不收集 owner 会话；0.3.2 不收集外部身份或支付数据，个人报告默认本地保存 | 先收口 AI 研究包 | 发布前仍运行 PII 扫描 |
| 非代码关键路径 | T902 冻结 AI 校准；T917 使用结果盲 AI 台账 | 场景选择不能由 `verify.py` 单独保证 | AI 样本不足时保留 `incomplete-study`，不阻塞 0.3.2 规划 |

### 研究协议裁决与剩余证据门

> 方向重置：本节只保留 AI_FORMAL 的当前有效合同；所有者训练、Web 终端和个人采集由
> 0.3.2 单独拥有，不得成为本里程碑的执行依赖。

以下 Q-301—Q-308 已回写为 0.3.1 的 AI 研究设计基线；所有者相关字段只作为 0.3.2 的
下游接口引用。

> 样本单位是 `AI_FORMAL` 的 paired-seed block，不使用真人参与者功效、预算或会话时长作为
> 当前 go/no-go。当前基线为 **168 个合格 block**，见
> [`H2-block-power-baseline`](../../../experiments/H2-block-power-baseline.md)。

#### Q-301：目标插槽与两条对照的策略实例

- 两条策略之一固定为 `risk_budget_threshold_v1`，参数冻结为
  `theta_in=3000`、`theta_out=1200`、`k_x1000=600`；其显式无动作带与滞回作为事前记录的
  策略特征，不构成结果驱动的选择。
- 另一条固定为 v0.1 原主方向策略 `risk_budget_linear_v1`。两者在 `AI_FORMAL` 轨地位平等，
  沿用 v0.1 的 `risk_appetite_x1000=int(Uniform[500,20000))` 及语义抽样键，并冻结
  `aggressiveness=10000bp`、`max_order_qty=500000000`、`ewma_half_life_trades=0`，不得为 H2 调参。
- 两条参照策略（`risk_budget_threshold_v1` 与 `risk_budget_linear_v1`）的策略 ID 或参数组合必须不同；
  协议必须记录主对照选择依据及其事前证据，禁止根据 H2 结果交换主、次标签。
- 全部 AI 正式场景固定同一非做市目标插槽、角色、初始账户、杠杆上限与风险参数；两条纯代理
  对照只在策略 ID/参数组合上不同。所有者 Web 采集不属于本里程碑，由 0.3.2 承接。

#### Q-302：AI 策略目标与参照

- AI 正式轨只比较两条冻结策略的显式目标、参数和决策结果，不引入真人任务或激励变量。
- `risk_budget_threshold_v1` 与 `risk_budget_linear_v1` 的身份、参数和主对照选择依据在协议
  中事前冻结，不按结果交换主、次标签。
- 所有者任务和 Web 交互由 0.3.2 单独冻结，不进入本里程碑的研究估计量。

#### Q-303：AI 窗口与运行调度

- 每个 AI 决策窗口固定推进 `1_000_000_000ns` 逻辑时间；两条策略运行都必须通过与所有者相同的有限窗口调度器，
  每窗至多一个动作，超时写 `NO_ACTION`。
- `AI_FORMAL` 轨按 168 个 paired-seed block 批处理执行，无墙钟、休息或参与者内重复测量。
- 所有者墙钟、训练和正式场景安排由 0.3.2 单独实现，并复用本节冻结的窗口接口。

#### Q-304：样本量、停止与多重性（已按 AI 基线冻结）

- `AI_FORMAL` 轨固定收满 **168** 个合格 paired-seed block，不按显著性提前停止；三个结果
  家族的主要 estimand 均为严重程度配对差，发生指标只作描述性报告。
- SESOI、bootstrap、Holm 校正、缺失和补跑规则均按预注册协议冻结；任何不足只能生成
  `incomplete-study` 样本流。
- 所有者的 6 个训练和 24 个正式场景属于 0.3.2，不进入本里程碑的样本量和研究声明。

#### Q-305：排除、补跑与中止

- AI 纳入、排除和技术补跑只读取冻结协议字段与结果盲台账，不读取结果方向。
- 服务端、日志或完整性故障保留原运行，并按预注册顺序使用新 seed/pair 整局补跑；亏损、
  极端结果或策略方向不得触发补跑。
- 所有者断线、中止和个人数据边界由 0.3.2 的 Web contract 单独定义。

#### Q-306：范围边界

- 本里程碑不招募或采集真人，不产生真人研究声明、人群推断或外部伦理结论。
- 所有者 Web 终端、训练、正式采集和个人报告属于 0.3.2；若未来扩大参与范围，必须另立
  需求和协议，不得回写为本 AI 研究轨的样本。

#### Q-307：三个结果家族（已按校准结论重写）

- 正式分析窗口是完整的 60 窗正式场景。**三个家族的主要 estimand 一律是严重程度配对差；
  发生指标一律只作描述性**，因为它们的配对差实测为零方差（见
  [`H2-endpoint-calibration`](../../../experiments/H2-endpoint-calibration.md) 与
  [`H2-cascade-calibration`](../../../experiments/H2-cascade-calibration.md)）。
- 价格崩盘：描述性发生指标沿用 v0.1 的 `EV-1`、下行 `EV-2`（`ln(P_t/P_0) < -ln(10)`）或清空
  bid 的 `EV-4`；**主要严重度**沿用 `max_t(max(ln(P_0/P_t),0))`。峰谷回撤与下行面积为次要
  新增指标，不得称为 v0.1 继承阈值。
- 流动性枯竭：描述性发生指标沿用 `EV-3`（最长连续无成交时长 `>5%*run_total_ns`）或清空
  任一侧的 `EV-4`；**主要严重度**沿用 `max_continuous_no_trade_ns/run_total_ns`。最低 k=10
  深度、相对初始深度和价差扩张为次要指标。
- 强平连锁：**主要严重度是单个 `chain_id` 下被强平的最大账户数**（未发生记 0）——这正是
  冻结 SESOI `0.25049` 所依据的量。**不得**改用 `max(chain_depth)+1`：实测所有 `chain_depth`
  都是 0，该量恒为常数，会把这个家族变回零方差终点。描述性发生指标记为“同一 `chain_id`
  出现两个及以上不同账户”；原先附加的 `max(chain_depth)>=1` 条件在本模型族恒为假，只作为
  “未观察到真正连锁传导”的事实报告，不作为发生判据。强平账户总数与强平成交量占比为次要指标。
- 强平连锁只在高杠杆 + `maint_bp=1200` 制度格发生；正式场景分布必须包含该格，否则该家族
  按“无数据”报告。严重度指标必须如实读作“一次强平判定牵连的账户数”，不得表述为连锁深度。
- 家族重叠按各自规则同时计入；三个家族分别报告，不生成综合崩盘得分。指标 ID、版本、公式、
  单位、缺失与零值语义必须在首个正式样本前写入指标字典并由协议引用。

#### Q-308：处理定义与 estimand 命名（已裁决，正文见 spec §1/§7）

裁决结果：主要估计量是**两个冻结 AI 策略在匹配账户、信息集、动作空间与决策窗口后的严重
程度配对差**，主对照为 `WINDOW_MATCHED_POLICY_CONTROL` 形态的两条策略参照运行；两条
参照都是纯代理运行，可随 assignment 预生成，不涉及真人招募或所有者样本。

实现侧由此产生三条硬约束（不满足则 B 只是纸面对齐，比联合处理更危险）：

1. **窗口调度匹配**：`WINDOW_MATCHED_POLICY_CONTROL` 形态的两条参照必须运行在与所有者相同的有限窗口调度器下
   ——同窗口长度、每窗至多一个动作、超时同样写 `NO_ACTION`。对照代理不得按内核默认的
   每次调度都决策；`pair validator` 必须把窗口调度参数纳入冻结字段白名单。
2. **对照策略来源受限**：主对照策略取自 v0.1 已验证的代理家族，参数随协议预注册并进入
   `protocol_hash`，不得为 H2 重新调参。
3. **匹配边界如实声明**：匹配账户/风险边界、信息集、动作空间与决策机会；两条策略的目标、
   参数与模型族分别冻结，不声称目标函数对齐。结论语法必须写出策略名称和模型边界。

协议必须冻结以下可审计比较矩阵；任何标为“相同”的字段都由 `pair validator` 逐字段断言：

| 维度 | `OWNER_DECISION` | `WINDOW_MATCHED_POLICY_CONTROL`（两条策略参照） | 合同 |
|---|---|---|---|
| 账户与风险边界 | 冻结目标插槽 | 同一目标插槽 | 相同 |
| 信息集与动作空间 | 冻结公开观察与订单接口 | 同一 schema 与权限 | 相同 |
| 决策机会 | 有限窗口、每窗一次、超时 `NO_ACTION` | 同一调度器与参数 | 相同 |
| 决策目标 | 所有者文字任务；实际目标不可观测 | 两条 v0.1 策略各自的 ID/version/参数与显式目标 | **不同且必须分别披露；两条策略之间也必须不同** |

所有者轨的定位是描述性：它回答“该所有者相对两条参照策略发生了什么”，用于外部
可读性与稳健性观察；它共享有限窗口调度，只保留策略差异，其结果段落必须标注 descriptive，
不得替代主要结论。

### 已确认技术设计

以下 DQ-301—DQ-305 已裁决为实现合同；后续变更须更新 spec/design、协议 schema 与回归测试，
不得只修改运行代码。

#### DQ-301：事件 schema 与旧日志兼容

- 事件 schema 从 v4 升至 v5，增加 `run_mode`、`sample_stage`、
  `protocol_id/hash`、匿名 `participant_id`、`assignment_id`、`pair_id`、condition、
  `session_order`、`target_agent_id` 和 `window_contract_version`。
- 读取入口按版本分派：v4 旧日志只读回放，缺少 H2 字段时不能补写或升级为 H2 正式证据；
  v5 才能进入 H2 guard；未知版本 fail closed。

#### DQ-302：CLI、API 与对象 schema

- 统一为 `python -m market_game_sim.experiment` 命令族，下设 `protocol validate/freeze/preview`、
  `assign`、`train`、`run`、`abort`、`adjudicate`、`analyze` 和 `deliver`。`run` 用
  `--arm linear|threshold|owner` 选择条件，枚举与协议 schema 的 `control_arm` 共用真源。
  不设 `enroll`/`withdraw`：项目不招募外部真人，没有报名与撤回同意流程。
- 采用 protocol、owner、assignment、session-manifest、adjudication、evidence-index 六类
  版本化 JSON schema（`owner` 取代旧的 `participant`，只存研究假名与训练完成状态）。
  正式写入必须绑定协议哈希、原子落盘；`AI_FORMAL` 与 `OWNER_N_OF_1` 各自维护 evidence index，
  分析只能读取显式冻结的那一份，不能扫描目录自动挑选样本，也不能跨轨读取。

#### DQ-303：窗口竞争与迟到输入

- 服务端单调钟是唯一墙钟裁判，窗口采用 `[open_monotonic_ns, deadline_monotonic_ns)`；输入
  只有在会话锁内满足 `received_monotonic_ns < deadline_monotonic_ns` 并成功占用唯一最终动作槽
  才有效。截止事件与输入竞争同一把锁，不设置隐藏宽限。
- 每个窗口最多接受一次最终动作，迟到返回 `WINDOW_CLOSED`，无有效动作写 `NO_ACTION`。
  客户端倒计时仅作展示；开窗、截止、接收、裁决时间和 reason code 进入诊断，不回拨逻辑时间。

#### DQ-304：AI_FORMAL 主要统计模型（已按 severity 终点重基线）

- **观察单位是配对 seed block，不是参与者。** `AI_FORMAL` 轨每个 block 产生一个
  `risk_budget_threshold_v1 - risk_budget_linear_v1` 的**严重程度**配对差；block 之间独立，
  没有参与者内聚类，因此不使用 participant-cluster 结构。
- 主要 95% CI 与双侧检验使用 block 级重抽样的 10000 次 bootstrap，并冻结随机种子；三个
  家族的**严重程度**主要检验用 Holm 校正，同时报告原始效应、CI、原始 p 与校正 p。
- **发生指标不是主要检验**：三个家族的发生率配对差实测为零方差（见
  [`H2-endpoint-calibration`](../../../experiments/H2-endpoint-calibration.md) 与
  [`H2-cascade-calibration`](../../../experiments/H2-cascade-calibration.md)），只作描述性报告，
  且必须如实呈现其零方差事实。
- 两个策略不是随机分配到 seed 的（每个 seed 都跑两条），配对差的随机性只来自 seed 抽样，
  因此 sign-flip/标签置换不得称作主要随机化推断；它只能作为明确披露交换性假设的敏感性
  分析。包含 scenario/regime 效应的分层模型作为第二项敏感性分析。
- `OWNER_N_OF_1` 轨（n=1）只报告 24 个场景的配对差分布、行为时间线与个案描述，**不做**
  显著性检验、不给人群区间，也不与 AI 轨合并。

#### DQ-305：技术中止与恢复

- H2 首版正式运行不支持中途恢复。技术故障写 `TECHNICAL_ABORT`，原运行不纳入正式
  分析；仅按预注册顺序从已签发备用池取得新 `session_id`、新 seed 和新 `pair_id` 整局补跑，
  并绑定结果盲生成的纯代理控制；原中止记录保留在样本流图中。
- adjudication 使用 `rerun_of_session_id` 与 `supersedes_pair_id` 连接原运行和补跑；preview 可以
  测试 checkpoint，但不得将正式中止运行拼接为完整样本。

## 10. 待确认设计问题

- [x] DQ-301: 已关闭 — 决策：事件 schema 升至 v5，v4 只读回放，H2 guard 只接受完整 v5，未知版本 fail closed。
- [x] DQ-302: 已关闭 — 决策：统一 `python -m market_game_sim.experiment` 命令族（无 enroll/withdraw）与六类版本化 schema（owner 取代 participant），分析只读本轨冻结 evidence index。
- [x] DQ-303: 已关闭 — 决策：服务端单调钟、半开窗口和会话锁内动作槽为唯一裁决点，无隐藏宽限。
- [x] DQ-304: 已关闭 — 决策：观察单位为配对 seed block，严重程度配对差 + block 级 bootstrap 为主要分析，Holm 控制三项主要检验；发生指标只作描述性，所有者轨不做显著性检验。
- [x] DQ-305: 已关闭 — 决策：正式运行不恢复或拼接，技术中止仅允许用预签发新 seed/pair 整局补跑并保留审计链。
