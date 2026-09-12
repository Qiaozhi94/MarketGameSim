---
kind: milestone
id: 0.3.2
parent: v0.3-human-in-the-loop-crash-experiment
version: "0.3"
status: draft
research_claim_status: not-applicable
research_claim_required: false
evidence_class: experiment-preview
gate_version: 1
created: 2026-09-12
updated: 2026-09-12
prerequisites:
  - 0.3.1
---

# 0.3.2：Web 交易终端与所有者 N-of-1 采集

> Owner: TBD | Target: v0.3

## 0. 来源与意图

- **版本规格**：[`../spec.md`](../spec.md)（所有者运行相关需求由本里程碑承接）。
- **PRD 来源**：[`../../../market-game-sim-prd.md`](../../../market-game-sim-prd.md) §15 H2-D。
- **架构来源**：[`../../../market-game-sim-architecture.md`](../../../market-game-sim-architecture.md)。
- **上游设计**：[`0.3.1 design`](../0.3.1-human-in-the-loop-experiment/design.md)。
- **上游合同**：[`H2-formal-freeze protocol`](../../../experiments/H2-formal-freeze/protocol.json)、
  [`interactive-session`](../../../contracts/interactive-session.md)。
- **功能类型**：user-facing / runtime / workflow / validation / docs。
- **规格模式**：full。
- **变更类型**：ADDED。
- **一句话意图**：在所有者训练开始前交付一个本地可打开的 H2 Web 终端，让所有者能看到
  best bid/ask、last、K 线、账户状态并用按钮提交受限交易动作；页面验收通过后再进行 6 个训练
  和 24 个正式 N-of-1 场景。

## 1. 问题、目标与非目标

### 问题

当前 H2 所有者入口是 CLI，展示字段不构成可用的行情终端：无法稳定看到价格历史和 K 线，
也没有适合鼠标操作的交易按钮。若直接开始四天训练，交互缺陷会在训练过程中持续阻塞，
并让所有者场景数据与页面问题纠缠在一起。

### 目标

1. 提供 loopback-only Web 页面，实时显示冻结信息集中的报价、最近成交、K 线和本人账户。
2. 提供买入、卖出、撤销/不行动等受限交互按钮，并将每次点击绑定到规范窗口和输入回执。
3. 先以固定假参与者完成 Web preview 和故障验收，再允许所有者开始训练。
4. 在训练/正式阶段严格隔离结果、参照策略和未来信息，生成可审计的 owner session artifact。

### 非目标

- 不连接交易所、真实账户、真实资金或外部行情源。
- 不实现多人协作、登录系统、公开部署、移动端适配或投资建议。
- 不在本里程碑修改 AI 正式轨的研究 estimand，也不把 owner n=1 结果写成人群结论。
- 不把 K 线展示自动视为新的可用信息；正式采集前必须冻结其观察集语义与控制运行匹配规则。

## 2. 用户场景

### US-401：先确认行情再交易（Priority: P1）

作为项目所有者，我希望在开始训练前看到可读的报价、最近成交和 K 线，以便确认当前市场
确实提供了交易所需的价格信息。

**为什么是这个优先级**：没有行情可见性，训练和正式交易都无法有效进行。

**独立测试**：启动本地 preview session，验证页面在无外部网络时仍能显示合成报价和至少一
根完整 K 线，并在空数据/断线时显示明确状态。

**验收场景**：

1. Given session 已进入 active-window，when 市场推进，then 页面更新 bid、ask、last、时间和账户状态。
2. Given 已有足够的冻结 public tape，when 页面渲染，then K 线按固定周期显示 OHLC，不显示未来窗口。

### US-402：用按钮提交规范动作（Priority: P1）

作为项目所有者，我希望用按钮提交买入、卖出或不行动，以便在每个有限窗口内完成一次真实
可审计的交易决策。

**为什么是这个优先级**：交易动作必须能在页面上完成，并且必须落入已有撮合、账本和风控路径。

**独立测试**：用固定输入覆盖合法动作、数量校验、窗口超时、重复点击和拒单，检查页面回执与事件链一致。

**验收场景**：

1. Given 窗口开放且数量合法，when 点击买入或卖出，then 页面只接受一次动作并显示 submitted。
2. Given 窗口关闭或数量非法，when 点击动作，then 页面拒绝请求并显示稳定错误，不产生订单。

### US-403：页面通过后再开始所有者训练（Priority: P1）

作为项目维护者，我希望 Web preview、断线、中止和阶段隔离先通过，再允许训练和正式场景，
以便页面缺陷不会消耗正式场景。

**为什么是这个优先级**：所有者时间是稀缺资源，必须由工程验收保护。

**独立测试**：preview 未通过时阻止 `training`/`formal`；通过后只发放冻结 assignment，并验证结果盲。

**验收场景**：

1. Given preview gate 未通过，when 请求 owner training，then 系统拒绝并说明缺少的 gate 证据。
2. Given training 完成且正式 assignment 已签发，when 开始 formal，then 页面不显示已完成场景结果或参照策略产出。

## 3. 范围与边界

### 范围内

- loopback-only H2 Web 页面：市场报价、最近成交、K 线、账户、窗口倒计时、动作按钮和状态回执。
- 复用 H2 既有 protocol、assignment、session controller、撮合、账本、保证金和强平路径。
- K 线由冻结 public tape 派生；默认使用 5 个逻辑窗口聚合一根预览 K 线，正式语义在 E1 前冻结。
- 训练阶段 6 个场景、正式阶段 24 个场景；所有者只作为项目唯一真人，不招募外部参与者。
- owner session manifest、输入/事件哈希、技术中止和按备用池补跑的审计链。

### 范围外

- 真实行情/交易所、账户认证、凭据托管、远程访问、多人交易和公开排行榜。
- AI formal evidence index、AI 主要结果、多重性校正和研究声明。
- 任何跨轨合并、结果驱动的补跑、未来信息显示或替所有者提交动作的自动化。

### 边界场景

- 首个窗口没有成交或报价时，页面显示 `market warming`/空态，不伪造价格；有报价前交易按钮禁用。
- K 线不足一个周期时显示未完成/数据不足状态，不把部分柱误标为完整历史。
- 断线、重复点击、迟到输入、技术中止和所有者主动中止均写稳定 reason code，并按冻结规则处理。
- 若 K 线被认定为新增观察信息，必须先升级 owner observation/protocol 版本，并使参照策略获得同一信息集。

## 4. 需求

### 功能需求

### Requirement: 运行受控的所有者替换会话（`FR-302`）

- **FR-302**：系统应让项目所有者在与参照策略相同的订单、撮合、保证金和强平路径中决策；背景市场按逻辑
时间推进，正式会话不得暂停、单步或临时改参，所有窗口必须接受至多一次规范动作。

### Requirement: 展示冻结行情与 K 线（`FR-401`）

- **FR-401**：系统应在 active-window 显示 `best_bid`、`best_ask`、`last`、报价时间、本人仓位/权益和由
冻结 public tape 聚合的 OHLC K 线；数据不足、无报价和断线必须有明确空态，禁止用占位价格冒充市场数据。

### Requirement: 生成可审计的规范动作（`FR-402`）

- **FR-402**：系统应把买入、卖出、不行动和撤销（若当前窗口/动作空间允许）映射到既有 canonical input，
并在服务端校验数量、窗口、重复提交和账户约束；页面按钮不得绕过撮合、账本或风控路径。

### Requirement: 训练与正式阶段门控（`FR-403`）

- **FR-403**：系统应在 Web preview 通过前拒绝 owner `training`/`formal`，在正式阶段隐藏结果、参照策略、
种子和未来事件，并只接受已签发 assignment。

### 数据 / 实体需求

- **DR-401**：`OwnerWebSession` 应保存 `session_id`、`assignment_id`、阶段、窗口状态、客户端
  版本、输入哈希、事件哈希、技术状态和 reason code，不保存真实身份、联系方式或屏幕录制。
- **DR-402**：K 线 artifact 应绑定 public tape 版本、聚合周期、窗口范围和内容哈希，不能脱离
  session/协议元数据单独成为正式证据。

### 事件 / Trace 需求

- **TR-302**：每个 owner 决策窗口必须写规范决定或 `NO_ACTION`，并通过 `input_seq`、`intent_id`、
  `decision_event_id` 连接订单、撤单、成交、账本、盘口变化与强平事件；墙钟只作依从性诊断。
- **TR-401**：页面每次动作应写入可审计输入回执，包含 `session_id`、`window_id`、动作类型、
  数量、客户端接收时间、服务端裁决和稳定错误码，不写键盘内容或无关遥测。

### API / 接口需求

- **IR-301**：所有者 Web 会话入口应提供版本化的 start、view、submit、abort 和 resume-status
  接口；正式态不暴露 pause、step、改参、种子或未来信息。
- **IR-401**：`GET /api/v1/h2/owner/session` 应返回当前阶段、窗口、报价、K 线、本人账户、
  可用动作、状态和错误，不返回参照策略或结果字段。
- **IR-402**：`POST /api/v1/h2/owner/session/{session_id}/decision` 应要求 `window_id`、
  `input_seq`、规范动作和数量，重复/迟到/非法请求返回稳定错误且不产生副作用。

### UX 需求

- **UX-401**：页面必须让用户在一个视图中看见价格、K 线、账户和当前窗口剩余时间。
- **UX-402**：买入、卖出、不行动和中止按钮必须有可见的 disabled/loading/submitted/error 状态，
  并在无报价或窗口关闭时阻止误操作。
- **UX-403**：页面必须持续显示 `training`/`formal`/`preview` 阶段，不显示未来信息、参照策略
  状态或未解盲结果。
- **UX-404**：页面必须提供可读的断线、空行情、拒单、超时、中止和完成状态，不依赖浏览器控制台排错。

### 非功能需求

- **NFR-302**：owner 数据最小化、假名化、退出和本地保留边界必须明确；成果包不得包含直接身份
  信息，也不得把 owner 结果写成人群结论。
- **NFR-401**：loopback 页面在无外部网络时可用；前端不引入交易凭据和第三方行情依赖。
- **NFR-402**：页面状态以服务端 session 为准，刷新或短暂断线不得重复提交窗口动作。
- **NFR-403**：支持项目既有 Windows/POSIX 运行方式；不得要求新增不可审计的全局服务或数据库。

## 5. 生命周期与不变量

```text
PREVIEW_BLOCKED -> PREVIEW_READY   Web 页面、行情、K 线、按钮和故障路径验收通过
PREVIEW_READY -> TRAINING          发放训练 assignment，结果仍隔离
TRAINING -> FORMAL_ARMED           6 个训练完成且正式 assignment/协议版本匹配
FORMAL_ARMED -> FORMAL_RUNNING     进入有限窗口并隐藏结果/参照策略
FORMAL_RUNNING -> COMPLETED        24 个场景完成或按冻结规则结束
FORMAL_RUNNING -> TECHNICAL_ABORT  断线/完整性/服务故障命中冻结无效条件
TECHNICAL_ABORT -> RERUN_PENDING   仅技术原因且备用池仍有可用项
```

不变量：

- 所有动作必须经服务端窗口锁和既有交易路径；前端状态不能单独证明提交成功。
- 每个窗口至多一个决定；迟到、重复和非法输入不推进逻辑时间、不写订单副作用。
- K 线只来自冻结 public tape；若其构成新增观察信息，必须新协议版本并匹配参照策略信息集。
- training、preview、formal 和 AI evidence index 始终隔离；owner session 不进入 AI 研究声明。
- 结果字段对中止、补跑和解盲裁决不可见；所有者只能看到当前允许的行情和本人账户。

## 6. 成功与验收

### 成功标准

- **SC-401**：本地新进程可打开 Web 页面并在无外部网络时显示合成报价、账户和至少一根完整 K 线。
- **SC-402**：固定输入可完成合法买入/卖出、拒单、超时、重复点击、断线和中止，输入与事件哈希一致。
- **SC-403**：6 个训练场景与 24 个正式场景均受阶段/assignment/解盲门控，且 owner evidence index
  与 AI evidence index 分离。
- **SC-404**：owner 个人描述性结果可从 session artifact 重建，不产生人群研究声明。

### 退出条件

| 退出 | 条件 | 证据 |
|---|---|---|
| E1 | owner observation/K 线语义、协议版本、动作空间与隐私边界冻结 | contract review + protocol diff |
| E2 | Web preview 可打开，价格/K 线/账户/按钮/错误状态和窗口门控通过 | browser preview bundle |
| E3 | 6 个训练场景完成且未污染 formal；输入链和中止/补跑路径通过 | training manifest + guard matrix |
| E4 | 24 个正式 owner 场景按冻结规则完成或形成 incomplete-study，个人报告明确不外推 | owner evidence index + descriptive report |

### 验收清单

- [ ] **AC-401** (`FR-401`, `IR-401`, `UX-401`, `SC-401`): 页面显示真实生成的 bid/ask/last、账户和 K 线，
      无报价时不显示伪价格。
- [ ] **AC-402** (`FR-402`, `IR-402`, `TR-401`): 合法动作只提交一次；非法、迟到和重复输入有稳定拒绝且零订单副作用。
- [ ] **AC-403** (`FR-403`, `IR-301`, `UX-403`): preview 未通过时 training/formal 被拒绝，正式态隐藏未来信息和结果。
- [ ] **AC-404** (`DR-401`, `DR-402`, `NFR-401`, `NFR-403`): artifact 绑定协议/窗口/哈希，loopback 无外部行情和凭据依赖。
- [ ] **AC-405** (`FR-302`, `TR-302`, `NFR-402`): owner 决策沿既有窗口、撮合、账本和风控路径，刷新/断线不重复提交。
- [ ] **AC-406** (`UX-402`, `UX-404`): loading、empty、error、timeout、abort、completed 状态可见且可操作。
- [ ] **AC-407** (`NFR-302`, `SC-404`): owner artifact 不含直接身份信息，报告只作个人描述，不产生人群结论。
- [ ] **AC-408** (`SC-402`, `SC-403`): 训练/正式阶段、备用补跑和 owner evidence index 可从 manifest 重建。

## 7. 测试、依赖与决策

### 测试策略

- 单元测试：K 线聚合、报价空态、动作规范化、窗口/数量/重复提交校验。
- 集成测试：Web session API、既有市场路径、断线/中止/补跑、artifact 哈希和阶段 guard。
- UI / E2E：浏览器打开、K 线刷新、按钮反馈、拒单、超时、无报价和结果盲。
- 真实环境 / 手动验证：Windows 与 POSIX 本地 loopback 各完成一次 preview；正式 owner 场景
  只在 E2/E3 通过后启动。

### 依赖

- 上游 Feature / Contract：0.3.1 H2 protocol/session/guard、0.2.1 interactive runtime、event schema。
- 下游消费者：owner training/formal runner、owner evidence index 和个人描述性报告。
- 外部 / 环境依赖：项目所有者分四天完成场景；不依赖外部网络、交易所或外部参与者。

### 决策与风险

| 决策 / 风险 | 结论或缓解 | 理由 | 后续 |
|---|---|---|---|
| 行情来源 | 只读冻结合成 public tape，不接外部行情 | 可复现、无凭据、无真实交易风险 | E1 冻结 tape/协议版本 |
| K 线信息集 | MVP 先作为 public tape 派生视图；若成为新增观察信息则升级协议并匹配控制 | 防止页面改善改变正式估计对象 | E1 前拍板 |
| 页面部署 | loopback-only、依赖现有 Python 服务 | 先解决所有者本地可用性 | 后续另立公开部署 Feature |
| 所有者时间 | Web preview 先闭环，训练和正式场景后置 | 避免四天时间被页面缺陷消耗 | E2 未通过不得开始 E3 |

## 8. 待确认问题

- [ ] Q-401: 正式 owner 观察集中是否把 5 窗一根 K 线作为新增字段；若是，确认新 protocol version 与参照策略的同信息集方案。
- [x] Q-402: 是否连接真实行情或真实账户？— 决策：否，仅 loopback 合成市场和本地 artifact。
