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
updated: 2026-09-06
---

# 0.3.1：H2 人在环崩盘反馈实验 - 设计

> Owner: TBD | Spec: `spec.md` | Tasks: `tasks.md`

## 0. 输入与约束

2026-09-06 方向重置后的规范输入是
[`H2-dual-track-contract`](../../../experiments/H2-dual-track-contract.md)：AI 正式轨使用
**168 个** paired-seed blocks（三个家族的 0.25 SD SESOI 各需 168，见
[`H2-block-power-baseline`](../../../experiments/H2-block-power-baseline.md)、
[`H2-endpoint-calibration`](../../../experiments/H2-endpoint-calibration.md)、
[`H2-cascade-calibration`](../../../experiments/H2-cascade-calibration.md)），所有者 N-of-1 轨
使用 6 个训练和 24 个正式 paired blocks，两条 evidence index 严格隔离。AI 轨是
`formal-research`，所有者轨是 `experiment-preview`，研究声明只能由 AI 轨建立。本文已按双轨
合同完成重基线；任何冲突均以合同为准。

- **行为契约**：[`spec.md`](spec.md)。
- **PRD / Architecture / Research**：[`PRD §15`](../../../market-game-sim-prd.md#15-交付路线图)、
  [`architecture`](../../../market-game-sim-architecture.md)、
  [`methodology`](../../../research/methodology.md)、
  [`metrics dictionary`](../../../research/metrics-dictionary.md)。
- **上游 Contract**：[`event-schema`](../../../contracts/event-schema.md)、
  [`agent-strategy`](../../../contracts/agent-strategy.md)、
  [`interactive-session`](../../../contracts/interactive-session.md)。
- **实现约束**：复用唯一市场内核；H1 `interactive` 保持隔离；正式采样在剩余 Q/DQ 关闭、
  preview 通过和协议冻结前不可开始。项目不招募外部真人，唯一真人是项目所有者本人。

## 1. 技术概要与影响面

在 H1 会话适配器外新增实验编排层。编排器加载内容寻址协议和签发的 assignment，按 `run_mode`
分流两条轨道：`ai-mechanism-experiment` 成对执行两个冻结策略；`owner-n-of-1` 锁定所有者
客户端的观察/动作窗口，并把规范输入送入既有生产路径。独立 evidence guard 对轨道、模式、
阶段、协议、pair、排除状态和哈希执行 fail-closed 校验；分析器分别以 seed block 与所有者
场景为单位生成三个结果家族和机制表。

- 前端：所有者会话的训练/正式阶段、倒计时、中止状态与解盲控制；移除正式态 pause/step。
- 后端 / API：协议冻结、assignment、双轨窗口控制和样本裁决；无 enrollment/同意流程。
- 存储 / Migration：文件型 protocol/assignment/session/evidence artifact；不引入数据库。
- Runtime / Agent Adapter：新增 H2 专用目标插槽替换适配器，以及占用同一插槽的**窗口匹配
  参照代理**（主对照决策生产者，须受同一窗口调度器约束）；目标代理仍保留在冻结
  `agent_specs` 与账户集合中，但正式处理运行禁用其策略决策入口，由规范人类输入接管同一
  `agent_id`、账户、初始资金、杠杆与风险参数。`owner-n-of-1` 禁止沿用 H1
  `extra_accounts["human"]` 的新增账户路径；撮合、账本、保证金和强平生产路径保持不变。
- Event / Evidence：新 `ai-mechanism-experiment` 与 `owner-n-of-1` mode、sample stage、
  协议/pair 元数据与两条互相隔离的 evidence index。
- 文档 / 配置：预注册、数据字典、运行手册、解盲与保留政策和两份正式报告。

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
- `pair validator` 要求比较矩阵中标为“相同”的字段逐字段一致（含账户、初始资金、信息集、
  动作空间与**窗口调度参数**）；决策生产者、参与者任务/激励和策略 ID/version/参数/显式目标
  按矩阵标为不同并分别披露。`OWNER_N_OF_1` 轨的所有者运行标记为描述性，不参与 AI 轨 pair
  完整性判定。
- `analysis` 只读取冻结 evidence index，不扫描 artifact 目录自动挑样本。
- 三类机制指标的规范定义只写入 `docs/research/metrics-dictionary.md`；protocol 保存字典版本与
  指标 ID，分析器不得复制公式或按本地实现重新解释口径。
- 身份/联系信息由研究流程外部保管，本仓库仅处理不可直接识别的研究假名。

## 3. 数据模型与 Migration

计划新增版本化 JSON schema：

- `protocol.json`：研究问题、假设、estimand、结果/机制字典、样本/停止、任务、窗口、顺序、
  排除、分析、结论语法、双轨证据级别、解盲规则及 `protocol_hash`。
- `owner.jsonl`：所有者研究假名与训练完成状态；不采集外部参与者，不含姓名或联系方式。
- `assignments.jsonl`：`assignment_id`、`run_mode`、`pair_id`、seed/config、session order、
  target slot、签发协议哈希。
- session manifest：运行与阶段元数据、输入/事件/artifact 哈希、完整性、技术状态。
- `adjudication.jsonl`：按冻结 reason code 记录 included/excluded/withdrawn，保留裁决时间和依据。
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
- 每个 assignment 预生成两条策略运行：`risk_budget_linear_v1` 与 `risk_budget_threshold_v1`。
  在 `AI_FORMAL` 轨它们构成配对 block；在 `OWNER_N_OF_1` 轨它们是所有者场景的
  `WINDOW_MATCHED_POLICY_CONTROL` 形态参照。两条策略运行都必须通过与所有者相同的有限窗口
  调度器产生决策——同窗口长度、每窗至多一个动作、超时写 `NO_ACTION`；禁止任一条按内核默认
  的逐次调度决策。窗口调度参数进入全部条件的冻结字段白名单与 `protocol_hash`。
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

- 训练页面：边界说明、标准任务、练习结果和正式态提示；无外部参与者，故无同意/资格流程。
- 正式页面：只显示冻结观察子集、本人状态、逻辑进度、窗口倒计时和输入回执；隐藏 pause、
  step、配置、种子和其他代理私有信息。
- 状态映射：waiting、active-window、submitted、no-action、completed、technical-abort、aborted。
- 研究控制台只显示 session 健康、协议/assignment 哈希和故障；在 24 个正式场景完成前不显示任何结果，
  以执行解盲规则并降低结果驱动干预风险。
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
| `AC-302` | integration / UI | `tests/integration/test_experiment_session.py` | 有限窗口、超时、无特权控制 |
| `AC-303` | integration | `tests/integration/test_h2_evidence_guard.py` | 模式/阶段/协议/pair 拒绝且零部分输出 |
| `AC-304` | integration | `tests/integration/test_h2_paired_runs.py` | 比较矩阵中标为“相同”的字段逐字段一致、目标差异分别披露、主对照复现、处理重放、次要对照标为描述性 |
| `AC-305` | unit / research | `tests/unit/experiment/test_h2_outcomes.py` | 三家族、双侧区间、多重性、无综合分数 |
| `AC-306` | unit / integration | `tests/unit/experiment/test_h2_mechanisms.py`、`tests/integration/test_h2_mechanisms.py` | 三机制及完整因果追溯 |
| `AC-307` | E2E / research | `tests/integration/test_h2_delivery.py` | index-only 重建、哈希与结论语法 |
| `AC-308` | contract / manual | `tests/unit/experiment/test_h2_privacy.py`、`tests/integration/test_experiment_session.py` | PII 拒绝、阶段提示、撤回政策 |

preview 使用固定假参与者输入覆盖放大、稳定、无检出、缺失 pair、断线和撤回路径；正式研究
结果不作为单元测试 fixture 提交。真实参与者 pilot 的验收记录仅标为 `experiment-preview`。

## 9. 已确认决策与残余风险

| 决策 / 风险 | 结论或缓解 | 理由 | 替代方案 / 后续 |
|---|---|---|---|
| 控制设计 | AI 正式 block 配对 threshold/linear；每个所有者 block 另配同 seed 的两条 AI 反事实 | 分离模型机制与个人体验 | 预生成后以哈希锁定；策略不为 H2 调参 |
| 窗口匹配 | 两条纯代理对照必须跑同一有限窗口调度器，调度参数进入三条件冻结字段白名单 | 否则描述性对比会混入决策机会变化 | 由 `pair validator` 与 AC-304 断言执行 |
| 估计单位 | AI 轨为 paired-seed block；个人轨为 owner × paired scenario | 同模型调用不是独立人类，个人多局也不独立 | 两轨分别建模且禁止合并 |
| 分配 | AI seed 计划和所有者场景顺序预先签发 | 控制路径选择、学习和疲劳 | T902 冻结顺序与备用池 |
| 正式交互 | 所有者固定窗口，无暂停/单步 | H1 自由操作不适合作正式个人比较 | 训练阶段仍可暂停讲解 |
| 证据准入 | 新 mode + stage + protocol + pair 多重闭锁 | mode 单字段不足以防误纳 | guard 矩阵覆盖缺失/伪装 |
| 隐私风险 | 不收集外部身份或支付数据；个人报告默认本地保存 | 唯一真人是项目所有者 | 发布前仍运行 PII 扫描 |
| 非代码关键路径 | T902 冻结 AI 校准和所有者场景顺序；T917 使用结果盲场景台账 | 场景选择不能由 `verify.py` 单独保证 | no-go 时仅继续 `experiment-preview`；样本不足不得建立声明或关闭 v0.3 |

### 研究协议裁决与剩余证据门

> 方向重置：下列 Q-301—Q-308 旧裁决仅保留为审计上下文。参与者类型、样本单位、预算和
> 推断边界已经由 `H2-dual-track-contract-v1` 取代，不得直接实现旧真人招募设计。

以下内容已经回写为 0.3.1 的研究设计基线。Q-301—Q-308 均已关闭；Q-306 按个人独立项目、
不寻求外部审查的所有者决定关闭，但不得把该决定表述为伦理批准、豁免或辖区合规结论。

> **Q-304 的样本量部分已被 `H2-dual-track-contract-v1` 取代**：下面 N=130 的一整套计算是
> **真人参与者口径**（130 名参与者 × 每人 8 局 ≈ 936 个配对局），与当前 `AI_FORMAL` 轨道的
> 「配对 seed block」单位不可通约。当前基线是**不少于 158 个 block**，见
> [`H2-block-power-baseline`](../../../experiments/H2-block-power-baseline.md)；旧计算只作
> 变更审计，不得用于任何 go/no-go 或实现。

#### Q-301：目标插槽与两条对照的策略实例

- 两条策略之一固定为 `risk_budget_threshold_v1`，参数冻结为
  `theta_in=3000`、`theta_out=1200`、`k_x1000=600`；它的显式无动作带与滞回比线性策略更适合
  有限窗口下的主要参照，但不声称与参与者目标对齐。
- 另一条固定为 v0.1 原主方向策略 `risk_budget_linear_v1`。两者在 `AI_FORMAL` 轨地位平等。
  两者沿用 v0.1 的 `risk_appetite_x1000=int(Uniform[500,20000))` 及其语义抽样键，并冻结
  `aggressiveness=10000bp`、`max_order_qty=500000000`、`ewma_half_life_trades=0`，不得为 H2 调参。
- 两条参照策略（`risk_budget_threshold_v1` 与 `risk_budget_linear_v1`）的策略 ID 或参数组合必须不同；协议
  必须记录主对照选择依据及其事前证据，禁止根据 H2 结果交换主、次标签。
- 全部正式场景固定同一非做市目标插槽、角色、初始账户、杠杆上限与风险参数；参与者不得
  自选插槽，两条纯代理对照只在策略 ID/参数组合上不同。禁止替换做市商。

#### Q-302：参与者任务与激励

- 标准任务固定为“在遵守市场和风险规则的前提下，最大化全部正式局的平均终局权益，并
  尽量避免破产”，不得引导追求单局最高收益或制造崩盘。
- 报酬采用每名完成者固定 `$22.00 USD` 基础报酬，加 `$0–4.40` 综合绩效奖金；奖金上限为
  基础报酬的 20%，按多局平均终局权益计算，不扣款、不与单局杠杆收益线性挂钩，也不奖励
  触发强平或崩盘。单人最高报酬为 `$26.40`；绝对金额、币种、奖金公式与支付条件必须写入
  协议和参与前说明。预算依据见
  [`H2-compensation-budget`](../../../experiments/H2-compensation-budget.md)。
- 训练和正式界面持续声明合成市场、模拟资金、非投资建议、非真实交易能力认证；参与者
  无需且不得提供真实账户、资产或交易凭据。

#### Q-303：窗口、局数与休息

- 每个决策窗口固定推进 `1_000_000_000ns` 逻辑时间，对应 8 秒墙钟；每局 60 窗，每人
  8 个正式场景，按 `4 + 4` 两个 block 执行，block 间强制休息至少 5 分钟。
- 正式操作约 64 分钟；连同同意、训练、理解检查和休息，总会话目标 90 分钟、硬上限
  105 分钟。正式局不能暂停或单步；窗口超时稳定提交 `NO_ACTION`。训练局可暂停讲解，
  但必须保持 `sample_stage=training`。
- pilot 只允许调整一次：若超时窗口超过 10%，把墙钟窗口从 8 秒增至 10 秒；不得缩短
  逻辑窗口或依据结果指标调整。调整后重新生成协议哈希，再开始正式采样。

#### Q-304：样本量、停止与多重性

- pilot 固定 8 人且永不进入正式样本。正式资源规划为固定 130 名已分配参与者、每人 8 局；
  最多额外招募 26 人，只能替代分配前未通过资格或理解检查者，因此总招募上限为 156 人；
  分配后的退出者不得补招替代。
- 三个家族各以发生概率的配对风险差为唯一主要 estimand，最小实质效应冻结为绝对
  `0.125`。严重程度和其他结果均为次要指标。
- 功效模拟必须以 participant 为聚类/重复测量单位，覆盖参与者内相关 `0.2/0.5/0.8`、
  10% pair 缺失、双侧检验和三个主要 estimand 的 Holm 校正，且在正式 N=130 时达到
  至少 80% 功效；不得把“人数 × 每人局数”直接当作独立样本量。
- 正式研究采用固定样本量/固定停止规则，不按显著性提前停止。若上述功效要求在 N=130 时
  仍不成立，T902 必须判定 no-go，不得冻结正式协议；只能在不查看正式数据的前提下重新设计，
  或继续仅标记为 `experiment-preview`。
- [`H2-power-feasibility`](../../../experiments/H2-power-feasibility.md) v3 的保守规划证据显示，
  N=130 在相关 `0.2/0.5/0.8` 下的功效分别为 99.8%/93.4%/80.0%，当前资源合同因此为
  `CONSERVATIVE_GO_AT_CAP`。目标会话 90 分钟对应 195 个已分配参与者小时，105 分钟硬上限
  对应 227.5 小时。正式样本、pilot、最多 26 名分配前筛出者及 10% 预备金合计冻结
  `$4,100.00 USD` 参与者报酬预算。招募平台固定为 Prolific，按独立研究者 `42.8%`费率计算
  `$1,754.80`平台费，VAT/汇兑前项目资金需求为 `$5,854.80`并向上冻结 `$5,900.00`；VAT、
  税费和汇兑成本另计，不得挤占参与者报酬预算。

#### Q-305：资格、排除、补跑与撤回

- 资格条件仅包括适用法定同意年龄、实验语言理解以及订单、仓位、保证金与模拟资金风险的
  理解检查；真实交易经验只作描述性变量，不作为门槛。
- 理解检查共 6 题，至少答对 5 题，且保证金/强平题与模拟资金风险题必须正确；培训后可用
  等价题重测一次，仍未通过者在 assignment 前排除。
- 客户端断线但服务端正常时窗口照常推进并写 `NO_ACTION`，不补跑；只有服务端、日志或完整性
  故障允许整局补跑。补跑必须使用预签发备用池中的新 `session_id`、seed 和 `pair_id`，原中止
  记录保留，配套纯代理控制在结果盲条件下生成。
- 亏损、破产、少交易、极端结果或主观“不认真”不得作为排除理由。身份映射在数据冻结后
  30 天内删除；去标识研究数据默认保留 5 年。撤回和保留规则必须写入同意书，若 Q-306 的
  适用伦理决定要求更严格期限，以该决定为准。

#### Q-306：伦理适用性

- 所有者确认本项目为个人独立实验，不指定或评估国家/地区规则、无依托机构、不准备外部
  伦理申请材料且不寻求 IRB/伦理委员会授权；因此外部批准/豁免不是本项目的软件开发门。
- 该选择不得被表述为伦理批准、豁免或辖区合规结论。参与者仍须在实验前主动同意模拟市场、
  数据用途、报酬、退出与保留边界；不采集敏感财务信息，参与者不承担真实损失。
- 决策记录见 [`H2-ethics-applicability`](../../../experiments/H2-ethics-applicability.md)。若未来
  引入机构、资助方、受监管场景或扩大参与者/数据范围，必须重新打开 Q-306。

#### Q-307：三个结果家族

- 正式分析窗口是完整的 60 窗正式局。价格崩盘发生指标沿用 v0.1：`EV-1`、下行 `EV-2`
  （`ln(P_t/P_0) < -ln(10)`）或清空 bid 的 `EV-4`；严重度沿用
  `max_t(max(ln(P_0/P_t),0))`。峰值至谷值回撤与下行面积只能作为次要新增指标，不得称为
  v0.1 继承阈值。
- 流动性枯竭发生指标沿用 `EV-3`（最长连续无成交时长 `>5%*run_total_ns`）或清空任一侧的
  `EV-4`；严重度沿用 `max_continuous_no_trade_ns/run_total_ns`。最低 k=10 深度、相对初始
  深度和价差扩张为次要指标，不新增未经校准的“双边深度比例”主要阈值。
- 强平连锁是 H2 新家族：同一 `chain_id` 至少出现两个不同账户且 `max(chain_depth)>=1` 时记为
  发生；主要严重度为 `max(chain_depth)+1`，未发生时记 0。不同强平账户数、最大 chain size
  与强平成交量占比为次要指标。
- 家族重叠按各自规则同时计入；三个家族分别报告，不生成综合崩盘得分。指标 ID、版本、公式、
  单位、缺失与零值语义必须在首个正式样本前写入指标字典并由协议引用。

#### Q-308：处理定义与 estimand 命名（已裁决，正文见 spec §1/§7）

裁决结果：主要估计量是**匹配可观测接口与决策窗口后的人类决策相对参照策略差异**，主对照
`WINDOW_MATCHED_POLICY_CONTROL` 形态的两条策略参照运行；
所有者臂只跑一次，两条参照都是纯代理运行，
可随 assignment 预生成，因此第二条对照不增加招募范围，也不进入主要终点的多重性校正。

实现侧由此产生三条硬约束（不满足则 B 只是纸面对齐，比联合处理更危险）：

1. **窗口调度匹配**：`WINDOW_MATCHED_POLICY_CONTROL` 形态的两条参照必须运行在与所有者相同的有限窗口调度器下
   ——同窗口长度、每窗至多一个动作、超时同样写 `NO_ACTION`。对照代理不得按内核默认的
   每次调度都决策；`pair validator` 必须把窗口调度参数纳入冻结字段白名单。
2. **对照策略来源受限**：主对照策略取自 v0.1 已验证的代理家族，参数随协议预注册并进入
   `protocol_hash`，不得为 H2 重新调参——否则“人类比策略强/弱”的结论只反映对照被调弱。
3. **匹配边界如实声明**：匹配账户/风险边界、信息集、动作空间与决策机会；参与者任务/激励
   与参照策略目标分别冻结，不声称目标函数对齐。结论语法强制三限定词（参与者池、任务与
   激励、模型族）及参照策略名称，禁用简称“人类效应”。

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
  `enroll`、`train`、`assign`、`run`、`withdraw`、`adjudicate`、`analyze` 和 `deliver`。
- 采用 protocol、participant、assignment、session-manifest、adjudication、evidence-index
  六类版本化 JSON schema。正式写入必须绑定协议哈希、原子落盘；分析只能读取显式冻结的
  evidence index，不能扫描目录自动挑选样本。

#### DQ-303：窗口竞争与迟到输入

- 服务端单调钟是唯一墙钟裁判，窗口采用 `[open_monotonic_ns, deadline_monotonic_ns)`；输入
  只有在会话锁内满足 `received_monotonic_ns < deadline_monotonic_ns` 并成功占用唯一最终动作槽
  才有效。截止事件与输入竞争同一把锁，不设置隐藏宽限。
- 每个窗口最多接受一次最终动作，迟到返回 `WINDOW_CLOSED`，无有效动作写 `NO_ACTION`。
  客户端倒计时仅作展示；开窗、截止、接收、裁决时间和 reason code 进入诊断，不回拨逻辑时间。

#### DQ-304：主要统计模型

- 以 participant × seed pair 为底层观察；先计算每位参与者各有效 pair 的
  `risk_budget_threshold_v1 - risk_budget_linear_v1` 严重程度配对差，按 block 等权平均。
- 主要 95% CI 与双侧检验使用按参与者整簇重抽样的 10000 次 bootstrap，并冻结随机种子；
  三个主要发生率差使用 Holm 校正，同时报告原始效应、CI、原始 p 与校正 p。
- 人类/代理身份没有被随机互换，因此 sign-flip/标签置换不得称作主要随机化推断；可作为明确
  披露对称性/交换性假设的敏感性分析。包含 participant 与 scenario/order 效应的分层模型作为
  第二项敏感性分析。

#### DQ-305：技术中止与恢复

- H2 首版正式运行不支持中途恢复。技术故障写 `TECHNICAL_ABORT`，原运行不纳入正式
  分析；仅按预注册顺序从已签发备用池取得新 `session_id`、新 seed 和新 `pair_id` 整局补跑，
  并绑定结果盲生成的纯代理控制；原中止记录保留在样本流图中。
- adjudication 使用 `rerun_of_session_id` 与 `supersedes_pair_id` 连接原运行和补跑；preview 可以
  测试 checkpoint，但不得将正式中止运行拼接为完整样本。

## 10. 待确认设计问题

- [x] DQ-301: 已关闭 — 决策：事件 schema 升至 v5，v4 只读回放，H2 guard 只接受完整 v5，未知版本 fail closed。
- [x] DQ-302: 已关闭 — 决策：统一 `python -m market_game_sim.experiment` 命令族与六类版本化 schema，分析只读冻结 evidence index。
- [x] DQ-303: 已关闭 — 决策：服务端单调钟、半开窗口和会话锁内动作槽为唯一裁决点，无隐藏宽限。
- [x] DQ-304: 已关闭 — 决策：参与者等权配对差与 participant-cluster bootstrap 为主要分析，Holm 控制三项主要检验。
- [x] DQ-305: 已关闭 — 决策：正式运行不恢复或拼接，技术中止仅允许用预签发新 seed/pair 整局补跑并保留审计链。
