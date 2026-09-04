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
updated: 2026-09-04
---

# 0.3.1：H2 人在环崩盘反馈实验 - 设计

> Owner: TBD | Spec: `spec.md` | Tasks: `tasks.md`

## 0. 输入与约束

- **行为契约**：[`spec.md`](spec.md)。
- **PRD / Architecture / Research**：[`PRD §15`](../../../market-game-sim-prd.md#15-交付路线图)、
  [`architecture`](../../../market-game-sim-architecture.md)、
  [`methodology`](../../../research/methodology.md)、
  [`metrics dictionary`](../../../research/metrics-dictionary.md)。
- **上游 Contract**：[`event-schema`](../../../contracts/event-schema.md)、
  [`agent-strategy`](../../../contracts/agent-strategy.md)、
  [`interactive-session`](../../../contracts/interactive-session.md)。
- **实现约束**：复用唯一市场内核；H1 `interactive` 保持隔离；正式实验在 Q-301—Q-307、
  DQ-301—DQ-305 全部关闭、preview 通过和协议冻结前不可采样。

## 1. 技术概要与影响面

在 H1 会话适配器外新增实验编排层。编排器加载内容寻址协议和签发的 assignment，生成
配对纯代理控制，锁定正式客户端的观察/动作窗口，并将规范人类输入送入既有生产路径。
独立 evidence guard 对模式、阶段、协议、pair、排除状态和哈希执行 fail-closed 校验；
分析器以 participant-seed pair 为单位生成三个结果家族和机制表。

- 前端：实验专用阶段、同意/训练、倒计时、退出和技术中止状态；移除正式态 pause/step。
- 后端 / API：协议冻结、匿名 enrollment、assignment、窗口控制和样本裁决。
- 存储 / Migration：文件型 protocol/assignment/session/evidence artifact；不引入数据库。
- Runtime / Agent Adapter：新增 H2 专用目标插槽替换适配器；目标代理仍保留在冻结
  `agent_specs` 与账户集合中，但正式处理运行禁用其策略决策入口，由规范人类输入接管同一
  `agent_id`、账户、初始资金、杠杆与风险参数。`human-experiment` 禁止沿用 H1
  `extra_accounts["human"]` 的新增账户路径；撮合、账本、保证金和强平生产路径保持不变。
- Event / Evidence：新 `human-experiment` mode、sample stage、协议/pair 元数据与独立 guard。
- 文档 / 配置：预注册、数据字典、运行手册、同意/保留政策和正式报告。

## 2. 架构与模块边界

```text
Frozen Protocol -> Assignment Ledger -> Experiment Session Controller
                                             |
Participant Client -> canonical input -------+-> existing market runtime/event log
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
- `pair validator` 比较冻结字段白名单，处理字段只允许 `decision_source` 及其派生输入不同。
- `analysis` 只读取冻结 evidence index，不扫描 artifact 目录自动挑样本。
- 三类机制指标的规范定义只写入 `docs/research/metrics-dictionary.md`；protocol 保存字典版本与
  指标 ID，分析器不得复制公式或按本地实现重新解释口径。
- 身份/联系信息由研究流程外部保管，本仓库仅处理不可直接识别的研究假名。

## 3. 数据模型与 Migration

计划新增版本化 JSON schema：

- `protocol.json`：研究问题、假设、estimand、结果/机制字典、样本/停止、任务、窗口、顺序、
  排除、分析、结论语法、伦理确认及 `protocol_hash`。
- `participants.jsonl`：随机研究 ID、同意/资格/理解检查状态；不含姓名或联系方式。
- `assignments.jsonl`：`assignment_id`、`participant_id`、`pair_id`、seed/config、session order、
  target slot、签发协议哈希。
- session manifest：运行与阶段元数据、输入/事件/artifact 哈希、完整性、技术状态。
- `adjudication.jsonl`：按冻结 reason code 记录 included/excluded/withdrawn，保留裁决时间和依据。
- evidence index：只列纳入 pair 及协议哈希，不复制身份资料。

H2 预注册采用双层机器门：`docs/experiments/H2-preregistration.md` 进入现有
`validate_preregistrations`，校验研究问题、参数归属和冻结字段不缺项；H2 `protocol.json`
schema 校验参与者、assignment、窗口、停止、排除和分析的可执行字段。两者通过同一内容哈希
交叉绑定，任一缺失或漂移均不得 freeze。T904/T916 必须为两层门禁各提供失败与通过用例。

事件 header 的兼容修改必须提升 schema 版本；旧 `interactive` 和 v0.1 事件保持可读，但默认
不补填 H2 字段且不能通过 H2 guard。具体 schema 版本在 DQ-301 关闭后冻结。

## 4. 接口、Contract 与 Event

### API / CLI / Adapter Contract

计划统一沿用仓库的 `python -m` 入口；除非 DQ-302 显式增加 `[project.scripts]`，不得在文档
或交付说明中使用不存在的 `market-game-sim` console script：

- `python -m market_game_sim.experiment protocol validate|freeze <path>`：验证完整性并生成内容哈希，
  只允许从 draft 产生新冻结版。
- `python -m market_game_sim.experiment enroll|train|assign|run|withdraw`：每步要求上一状态的
  不可伪造引用。
- `python -m market_game_sim.experiment control-pair <assignment>`：从 assignment 生成冻结纯代理运行。
- `python -m market_game_sim.experiment preview|adjudicate|analyze|deliver`：阶段严格分离，正式命令
  只读冻结 index。

错误码至少区分协议未冻结/漂移、assignment 不匹配、窗口关闭、阶段非法、pair 漂移、技术
中止、撤回和证据不合格。接口名与 payload 待 DQ-302 冻结。

### Event / Trace Contract

`RUN_HEADER` 计划增加 spec TR-301 字段；人类窗口写 `HUMAN_WINDOW_OPEN/CLOSE` 或等价可审计
边界，合法输入沿用 `AGENT_DECIDE -> ORDER_* -> TRADE/ACCOUNT/LIQUIDATION` 因果链，超时写
`NO_ACTION`。事件全序继续由逻辑时间与既有优先级合同拥有；墙钟开闭时间只用于依从性诊断，
进入 artifact 哈希但不进入市场结果摘要。

## 5. Runtime、Workflow 与并发

- 每个正式 assignment 只允许一个活动 session；通过文件锁/CAS 防止重复启动与重复纳入。
- 客户端输入带 `window_id + input_seq`；控制器只在窗口开放、未提交时接受一次规范决定。
- 窗口关闭与输入到达竞争由服务器提交顺序裁决并记录；迟到输入稳定拒绝，不回拨逻辑时间。
- 控制运行可预生成，但必须使用与处理运行相同的冻结代码/config/seed；代码变化使 pair 失效。
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

- enrollment/training 页面：边界说明、同意状态、标准任务、理解检查、练习结果和正式态提示。
- 正式页面：只显示冻结观察子集、本人状态、逻辑进度、窗口倒计时和输入回执；隐藏 pause、
  step、配置、种子和其他代理私有信息。
- 状态映射：waiting、active-window、submitted、no-action、completed、technical-abort、withdrawn。
- 研究控制台只显示 session 健康、协议/assignment 哈希和故障，不显示实时盈亏或主要终点，
  降低实验员结果驱动干预风险。
- 诊断记录窗口延迟、断线和客户端版本，但不得收集键盘内容、屏幕录制或无关行为遥测。

## 7. 失败、恢复、安全与兼容

- 校验与失败映射：协议/阶段/pair 任一不合法即在证据写入前失败；市场事务沿用原子提交。
- 重启与恢复：正式 session 不静默续跑；按冻结规则标记 abort 或从已提交边界恢复，并保留
  两次启动审计。是否允许恢复由 DQ-305 决定；Q-305 只拥有补跑、排除和撤回的产品政策。
- 权限 / escalation / 凭据边界：loopback 优先，无交易凭据；研究 ID 不承担身份认证用途。
- 隐私：本仓库不保存真实身份映射；日志白名单化，发布前运行 PII 扫描和人工复核。
- Windows / POSIX / 版本兼容：复用 H1 支持矩阵；窗口计时使用单调钟，市场仍只读逻辑时间。

## 8. 测试策略与验收映射

| 验收项 | 测试层级 | 计划文件 / 场景 | 关键断言 |
|---|---|---|---|
| `AC-301` | unit / contract | `tests/unit/experiment/test_h2_protocol.py` | 完整冻结、漂移新哈希、旧 assignment 拒绝 |
| `AC-302` | integration / UI | `tests/integration/test_experiment_session.py` | 有限窗口、超时、无特权控制 |
| `AC-303` | integration | `tests/integration/test_h2_evidence_guard.py` | 模式/阶段/协议/pair 拒绝且零部分输出 |
| `AC-304` | integration | `tests/integration/test_h2_paired_runs.py` | 账户/资金/代理集合相同、唯一差异、控制复现、处理重放 |
| `AC-305` | unit / research | `tests/unit/experiment/test_h2_outcomes.py` | 三家族、双侧区间、多重性、无综合分数 |
| `AC-306` | unit / integration | `tests/unit/experiment/test_h2_mechanisms.py`、`tests/integration/test_h2_mechanisms.py` | 三机制及完整因果追溯 |
| `AC-307` | E2E / research | `tests/integration/test_h2_delivery.py` | index-only 重建、哈希与结论语法 |
| `AC-308` | contract / manual | `tests/unit/experiment/test_h2_privacy.py`、`tests/integration/test_experiment_session.py` | PII 拒绝、阶段提示、撤回政策 |

preview 使用固定假参与者输入覆盖放大、稳定、无检出、缺失 pair、断线和撤回路径；正式研究
结果不作为单元测试 fixture 提交。真实参与者 pilot 的验收记录仅标为 `experiment-preview`。

## 9. 已确认决策与残余风险

| 决策 / 风险 | 结论或缓解 | 理由 | 替代方案 / 后续 |
|---|---|---|---|
| 控制设计 | 同 seed/config 纯代理配对，不把 v0.1 样本直接复用 | H2 代码和协议必须同代可比 | 预生成后以哈希锁定 |
| 估计单位 | participant-seed pair，分析处理参与者内重复 | 同一人多局不独立 | 具体模型由功效模拟冻结 |
| 分配 | seed/scenario 顺序随机或平衡，分配表预先签发 | 控制学习、疲劳和场景顺序 | 算法与审计种子待冻结 |
| 正式交互 | 固定窗口，无暂停/单步 | H1 无限思考不适合作正式比较 | 训练阶段仍可暂停讲解 |
| 证据准入 | 新 mode + stage + protocol + pair 多重闭锁 | mode 单字段不足以防误纳 | guard 矩阵覆盖缺失/伪装 |
| 隐私风险 | 最小化、假名化、身份分离、发布扫描 | 人类研究增加识别风险 | 保留期与撤回政策待伦理确认 |

### 待确认研究协议的建议基线

以下内容是对 spec Q-301—Q-307 的**建议**，用于检视和功效模拟，不代表问题已经关闭；
只有评审通过并回写 spec 后才成为冻结合同。

#### Q-301：目标代理

- 建议固定替换一个具有方向性仓位目标的 `goal-driven` 代理，并在全部正式场景保持相同
  角色、策略参数、初始账户、杠杆上限和风险参数。
- 建议不替换做市商：撤掉做市角色会机械性改变盘口深度，难以区分人类决策效应与角色
  缺失效应。
- 参与者不得自选被替换角色；纯代理 pair 中保留同一 target slot 的原策略。

#### Q-302：参与者任务与激励

- 建议标准任务为“在遵守市场和风险规则的前提下，最大化全部正式局的平均终局权益，并
  避免破产”，而不是追求单局最高收益或制造崩盘。
- 建议采用固定参与报酬加封顶的小额绩效奖金；奖金按多局综合表现计算，不与单局杠杆收益
  线性挂钩，也不奖励触发强平或崩盘。
- 风险提示应持续声明合成市场、模拟资金、非交易建议、非真实交易能力认证；参与者无需
  提供真实账户、资产或交易凭据。

#### Q-303：窗口、局数与休息

- preview 建议起始值：每个决策窗口墙钟 8 秒，每局 8—10 分钟，每人 8 个正式场景，按
  `4 + 4` 两个 block 执行，block 间至少休息 5 分钟。
- 正式局不能暂停或单步；窗口超时稳定提交 `NO_ACTION`。训练局可暂停讲解，但必须保持
  `sample_stage=training`。
- pilot 只允许按预先写明的超时率、误操作率和完成时长判据调整一次参数；调整后重新生成
  协议哈希，再开始正式采样。

#### Q-304：样本量、停止与多重性

- 建议先以 H1 输入和模拟人类策略估计 participant-seed 配对差值的方差，再做功效模拟；
  不凭经验人数直接冻结正式样本量。
- pilot 建议 6—10 人且永不进入正式样本；正式实验先按 30—40 人、每人 8 局做资源预算，
  最终人数由双侧、至少 80% 功效和预注册最小实质效应的模拟结果决定。
- 正式研究采用固定样本量/固定停止规则，不按显著性提前停止。三个主要结果家族使用 Holm
  校正；每个家族须预先指定一个主要 estimand，其余结果标为次要或描述性。

#### Q-305：资格、排除、补跑与撤回

- 建议资格条件仅包括适用法定同意年龄、实验语言理解和订单/仓位/保证金理解检查；真实
  交易经验只作描述性变量，不作为默认门槛。
- 可排除条件限于：未同意、未通过预注册理解检查、关键事件缺失的系统故障、未达到最低
  完成局数或撤回同意。亏损、破产、少交易、极端结果或主观“不认真”不得作为排除理由。
- 只有预定义技术故障允许补跑；补跑必须使用新 `session_id`、新 seed 和新 `pair_id`，原
  中止记录保留在样本流图中。新 seed/pair 只能来自首个正式样本前签发的有序备用池，配套
  纯代理控制在结果盲条件下生成；不得因表现或结果极端补跑或跳选备用项。
- 建议分析冻结前撤回的数据从正式分析移除；匿名聚合发布后的处置与数据保留期限必须在
  同意书中事先说明，身份映射始终与运行数据分离。

#### Q-306：伦理适用性

- 首个真人 pilot 前应完成书面伦理适用性判断。依托机构开展时，取得其伦理委员会/IRB
  批准或豁免；独立研究也应保留签字的自查、同意书、风险、保留和撤回政策。
- 未取得上述确认时，只能运行自动化假参与者 preview，不得招募或采集真人数据。
- 不采集敏感财务信息；参与者不承担任何损失，绩效报酬设上限。

#### Q-307：三个结果家族

- 建议最大限度沿用 v0.1 指标字典的窗口和阈值；如需改变，必须在查看 H2 正式数据前给出
  理论理由、版本化并重新冻结协议。
- 价格崩盘：发生指标为固定窗口最大回撤越过阈值，主要严重程度为最大回撤；下行面积为
  次要指标。
- 流动性枯竭：发生指标为双边有效深度低于基准比例并持续规定时间，主要严重程度为枯竭
  持续时间；最低深度和价差扩张为次要指标。
- 强平连锁：发生指标为规定窗口内多个不同账户形成因果相邻强平，主要严重程度为最长连锁
  长度；强平账户数和名义量为次要指标。
- 三个家族分别报告，不生成综合崩盘得分。

### 待确认技术设计的建议基线

以下内容对应 DQ-301—DQ-305，同样只作为评审建议，不表示设计问题已经关闭。

#### DQ-301：事件 schema 与旧日志兼容

- 建议在当前事件 schema 上顺延一个版本，增加 `run_mode`、`sample_stage`、
  `protocol_id/hash`、匿名 `participant_id`、`assignment_id`、`pair_id`、condition、
  `session_order`、`target_agent_id` 和 `window_contract_version`。
- 旧日志保持只读兼容，但缺少 H2 字段时只能回放，不能补写或升级为 H2 正式证据。

#### DQ-302：CLI、API 与对象 schema

- 建议统一为 `python -m market_game_sim.experiment` 命令族，下设 `protocol validate/freeze`、
  `enroll`、`train`、`assign`、`run`、`withdraw`、`adjudicate`、`analyze` 和 `deliver`。
- 采用 protocol、participant、assignment、session-manifest、adjudication、evidence-index
  六类版本化 JSON schema。正式写入必须绑定协议哈希、原子落盘；分析只能读取显式冻结的
  evidence index，不能扫描目录自动挑选样本。

#### DQ-303：窗口竞争与迟到输入

- 建议服务端单调钟作为唯一墙钟裁判；输入在 deadline 前被服务端接收并取得提交序号才
  有效。每个窗口最多接受一次最终动作，迟到返回 `WINDOW_CLOSED`，无有效动作写
  `NO_ACTION`。
- 客户端倒计时仅作展示；接收时间、裁决时间和 reason code 进入诊断，不回拨逻辑时间。

#### DQ-304：主要统计模型

- 建议以 participant × seed pair 为观察单位，participant 内同 seed 的配对随机化/置换
  推断作为主要分析，包含参与者及必要场景效应的分层模型作为敏感性分析。
- 偏态严重程度采用随机化或 bootstrap 区间，同时报告原始尺度效应和不确定区间；三个结果
  家族使用 Holm 校正，不只报告 p 值。

#### DQ-305：技术中止与恢复

- 建议 H2 首版正式运行不支持中途恢复。技术故障写 `TECHNICAL_ABORT`，原运行不纳入正式
  分析；仅按预注册顺序从已签发备用池取得新 `session_id`、新 seed 和新 `pair_id` 整局补跑，
  并绑定结果盲生成的纯代理控制；原中止记录保留在样本流图中。
- preview 可以测试 checkpoint，但不得将正式中止运行拼接为完整样本。

## 10. 待确认设计问题

- [ ] DQ-301: `RUN_HEADER` 新字段应采用哪个 schema 版本，如何保持旧事件读取兼容？
- [ ] DQ-302: protocol、assignment、session 和 evidence guard 的最终 CLI/API 名称与 schema？
- [ ] DQ-303: 决策窗口关闭与迟到输入竞争的精确提交点、容错和墙钟诊断口径？
- [ ] DQ-304: 配对分析采用何种层级/置换模型，多重性与小样本区间如何实现和锁定？
- [ ] DQ-305: 技术中止是否允许从提交边界恢复；若允许，恢复 run 如何保持 pair 与审计身份？
