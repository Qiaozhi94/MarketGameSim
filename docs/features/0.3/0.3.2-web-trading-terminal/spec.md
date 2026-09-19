---
kind: milestone
id: 0.3.2
parent: v0.3-human-in-the-loop-crash-experiment
version: "0.3"
status: done
status_evidence: Web 终端（E1/E2）已交付并由 tests/e2e/test_h2_owner_terminal.py 与
  tests/integration/test_h2_owner_web.py 验收；N-of-1 采集轨随 ADR-010 归档，已移出本里程碑范围
research_claim_status: not-applicable
research_claim_required: false
evidence_class: experiment-preview
gate_version: 1
created: 2026-09-12
updated: 2026-09-20
prerequisites:
  - 0.2.1
---

# 0.3.2：Web 交易终端

> Owner: TBD | Target: v0.3

> **范围收窄（2026-09-20，[ADR-010](../../../decisions/010-market-ecology-research-pivot.md)）**：
> 原「所有者 N-of-1 采集」轨（6 训练 + 24 正式场景、配对观察白名单、采集态 evidence index）
> 已整体归档，移出本里程碑范围——它不是未完成，是经 owner 裁决不再做。协议、assignment、
> session guard 等机械与其测试保留在仓库，受控对照类研究问题出现时可复活。本里程碑
> 收口的是已交付的 Web 交易终端。

## 0. 来源与意图

- **版本规格**：[`../spec.md`](../spec.md)（所有者运行相关需求由本里程碑承接）。
- **PRD 来源**：[`../../../market-game-sim-prd.md`](../../../market-game-sim-prd.md) §15 H2-D。
- **架构来源**：[`../../../market-game-sim-architecture.md`](../../../market-game-sim-architecture.md)。
- **上游设计**：[`0.3.1 design`](../0.3.1-human-in-the-loop-experiment/design.md)。
- **上游合同**：[`H2-formal-freeze protocol`](../../../experiments/H2-formal-freeze/protocol.json)、
  [`interactive-session`](../../../contracts/interactive-session.md)。
- **架构决策**：[`ADR-006`](../../../decisions/006-realtime-free-trading-owner-terminal.md)
  （真实世界时间与自由连续交易，实验约束收敛到采集模式）。
- **交互设计原型**：[`interaction-design.html`](interaction-design.html)（真实终端形态，owner 2026-09-18 定稿）。
- **功能类型**：user-facing / runtime / workflow / validation / docs。
- **规格模式**：full。
- **变更类型**：ADDED。
- **一句话意图**：交付一个本地可打开的真实终端形态 Web 交易终端——自由连续交易
  （市价/限价）、真实世界时间呈现、可审计操作回报，并保留 preview fail-closed 门控与
  会话采样审计链。
- **窗口合同修订（Q-403，2026-09-13）**：owner 轨不再使用用户可见的决策窗口与"每窗一次
  动作"约束（修订 Q-303 中 owner 墙钟窗部分，见 ADR-006）；市场仍按冻结逻辑步进推进，
  服务端按冻结粒度对逻辑时点静默采样。AI 正式轨（0.3.1）不受影响。

## 1. 问题、目标与非目标

### 问题

当前 H2 所有者入口是 CLI，展示字段不构成可用的行情终端：无法稳定看到价格历史和 K 线，
也没有贴近真实交易习惯的下单交互。若直接开始四天训练，交互缺陷会在训练过程中持续阻塞，
并让所有者场景数据与页面问题纠缠在一起。

### 目标

1. 提供真实终端形态的 loopback Web 页面：实时显示冻结信息集中的报价、盘口、最近成交、
   多周期 K 线和本人账户，时间呈现采用合成交易所墙钟。
2. 提供自由连续交易：市价与限价委托、挂单管理与撤单，全部映射到 canonical input 并
   生成操作回报；服务端幂等与既有撮合、账本、风控路径裁决。
3. 先以固定假参与者完成 Web preview 和故障验收，preview 未通过时采集入口 fail closed。
4. 生成可审计的 owner session artifact：服务端按冻结粒度采样逻辑时点，并区分
   owner 主动中止与技术中止。

### 非目标

- 不连接交易所、真实账户、真实资金或外部行情源。
- 不实现多人协作、登录系统、公开部署、移动端适配或投资建议。
- 不在本里程碑修改 AI 正式轨的研究 estimand，也不把 owner n=1 结果写成人群结论。
- **不执行 N-of-1 采集**：6 训练 + 24 正式场景、owner evidence index 与个人描述性报告
  随 [ADR-010](../../../decisions/010-market-ecology-research-pivot.md) 归档，不属于本里程碑。
- 不把 K 线展示自动视为新的可用信息；正式采集前必须冻结其观察集语义与参照策略的同
  信息集方案（Q-401）。
- 不在自由模拟终端引入实验性节奏约束（决策窗口、阶段徽标、解盲清单）；这些只属于
  采集模式（ADR-006）。

**描述性对比边界（Q-403）**：owner 的动作空间是市价/限价委托与撤单，而两条参照策略
（v0.1 目标插槽家族）只发市价单——Q-308 比较矩阵中「信息集与动作空间 | 相同」对 owner
不再成立。owner 的个人结果只作场景级描述性对比，并必须同时声明机会集（无用户可见决策窗）
与动作空间两处差异。

## 2. 用户场景

### US-401：先确认行情再交易（Priority: P1）

作为项目所有者，我希望在开始交易前看到可读的报价、盘口、最近成交和多周期 K 线，以便
确认当前市场确实提供了交易所需的价格信息。

**为什么是这个优先级**：没有行情可见性，训练和正式交易都无法有效进行。

**独立测试**：启动本地 preview session，验证页面在无外部网络时仍能显示合成报价和至少一
根完整 K 线，并在空数据/断线时显示明确状态。

**验收场景**：

1. Given 会话进行中市场推进，then 页面更新 bid、ask、last、市场时钟和账户状态。
2. Given 已有足够的冻结 public tape，when 页面渲染，then K 线按所选周期显示 OHLC，
   提供时间轴与多周期切换，不显示未来数据。

### US-402：自由提交买卖委托（Priority: P1）

作为项目所有者，我希望用真实交易终端的方式随时提交市价或限价委托并管理挂单，以便完成
真实、可审计的交易决策。

**为什么是这个优先级**：交易动作必须能在页面上完成，并且必须落入已有撮合、账本和风控路径。

**独立测试**：用固定输入覆盖合法市价/限价委托、数量与价格校验、拒单、撤单、断线恢复和
重复提交，检查操作回报与事件链一致。

**验收场景**：

1. Given 会话进行中且数量合法，when 提交市价委托，then 按盘口即时成交并显示成交回报。
2. Given 限价委托未触及盘口，when 提交，then 进入当前挂单，价格触及后自动成交，撤单
   则生成已撤单回报且零成交。
3. Given 数量或价格非法，when 提交，then 页面在本地预检拒绝或服务端返回稳定错误，不产生订单。

### US-403：页面通过后再开始所有者训练（Priority: P1）

作为项目维护者，我希望 Web preview、断线、中止和阶段隔离先通过，再允许进入采集模式开始
训练和正式场景，以便页面缺陷不会消耗正式场景。

**为什么是这个优先级**：所有者时间是稀缺资源，必须由工程验收保护。

**独立测试**：preview 未通过时阻止 `training`/`formal`；通过后只发放冻结 assignment，并验证结果盲。

**验收场景**：

1. Given preview gate 未通过，when 请求 owner training，then 系统拒绝并说明缺少的 gate 证据。
2. Given training 完成且正式 assignment 已签发，when 开始 formal，then 页面不显示已完成场景结果或参照策略产出。

## 3. 范围与边界

### 范围内

- loopback-only H2 Web 页面（真实终端形态）：市场报价、盘口、最近成交、多周期 K 线、
  账户、市价/限价下单、挂单管理、操作回报和状态提示。
- 复用 H2 既有 protocol、assignment、session controller、撮合、账本、保证金和强平路径。
- K 线由冻结 public tape 派生，提供 1m/5m/15m/1h/4h 派生视图；时间压缩比与周期集合在
  E1 前冻结（Q-401）。
- owner session manifest、委托/成交/事件哈希、时点采样快照，以及 owner 主动中止与
  技术中止的区分。

### 范围外

- **N-of-1 采集执行**（6 训练 + 24 正式场景、owner evidence index、个人描述性报告）：
  随 ADR-010 归档；协议与 guard 机械保留在仓库但不在本里程碑交付。
- 真实行情/交易所、账户认证、凭据托管、远程访问、多人交易和公开排行榜。
- AI formal evidence index、AI 主要结果、多重性校正和研究声明。
- 任何跨轨合并、结果驱动的补跑、未来信息显示或替所有者提交动作的自动化。
- 止损/止盈等条件单与高级图表指标（后续交易产品 Feature）。

### 边界场景

- 会话开头没有成交或报价时，页面显示等待行情空态，不伪造价格；有报价前下单按钮禁用。
- K 线数据不足一个周期时显示未完成/数据不足状态，不把部分数据误标为完整历史。
- 断线、重复委托（幂等重放）、技术中止和所有者主动中止均写稳定 reason code，并按冻结
  规则处理。
- 若 K 线或盘口档位被认定为新增观察信息，必须先升级 owner observation/protocol 版本，
  并使参照策略获得同一信息集。

## 4. 需求

### 功能需求

### Requirement: 运行自由连续交易的所有者会话（`FR-302`）

- **FR-302**：系统应让项目所有者在与参照策略相同的撮合、账本、保证金和强平路径中自由
  连续交易；采集会话按冻结的市场时间跨度推进，正式会话不得暂停、单步或临时改参；
  服务端按冻结粒度对逻辑时点静默采样（仓位/权益/净成交/动作数），采样不约束用户操作
  节奏（ADR-006）。

### Requirement: 展示冻结行情与多周期 K 线（`FR-401`）

- **FR-401**：系统应在会话进行中显示 `best_bid`、`best_ask`、`last`、市场时钟、盘口与
  最近成交、由冻结 public tape 派生的多周期 OHLC K 线，以及本人权益/可用/未实现/仓位/
  占用保证金/保证金比率/账户状态；采集模式只显示 §5 定义的冻结观察白名单字段，白名单外
  的展示字段不得进入采集视图或 artifact；数据不足、无报价和断线必须有明确空态，禁止用
  占位价格冒充市场数据。

### Requirement: 生成可审计的规范委托（`FR-402`）

- **FR-402**：系统应把市价与限价买卖委托和撤单映射到既有 canonical input，并在服务端
  校验数量、价格、重复提交和账户约束；页面按钮不得绕过撮合、账本或风控路径。

### Requirement: 训练与正式阶段门控（`FR-403`）

- **FR-403**：系统应在 Web preview 通过前拒绝 owner `training`/`formal`；采集模式隐藏
  结果、参照策略、种子和未来事件，并只接受已签发 assignment；自由模拟不进入任何实验
  证据索引（ADR-006）。

### 数据 / 实体需求

- **DR-401**：`OwnerWebSession` 应保存 `session_id`、`assignment_id`、模式、时点采样
  快照、客户端版本、委托与事件哈希、技术状态、中止类型（owner/technical）和 reason code，
  不保存真实身份、联系方式或屏幕录制。
- **DR-402**：K 线 artifact 应绑定 public tape 版本、聚合周期、时间压缩比、时间范围和
  内容哈希，不能脱离 session/协议元数据单独成为正式证据。

### 事件 / Trace 需求

- **TR-302**：服务端按冻结粒度对 owner 会话的逻辑时点写采样快照，并通过 `input_seq`、
  `intent_id`、`decision_event_id` 把委托、撤单、成交、账本、盘口变化与强平事件连入
  因果链；墙钟只作依从性诊断。
- **TR-401**：页面每次委托应写入可审计输入回执，包含 `session_id`、动作类型、数量、
  价格、客户端接收时间、服务端裁决和稳定错误码，不写键盘内容或无关遥测。

### API / 接口需求

- **IR-301**：所有者 Web 会话入口应提供版本化的 start、view、orders、abort 和
  resume-status 接口；`abort` 幂等且只表达 owner 主动中止（写稳定 `OWNER_ABORT` reason
  code 后为终态、不补跑）；`TECHNICAL_ABORT` 由服务端故障路径内部生成，客户端不得提交该
  分类；正式态不暴露 pause、step、改参、种子或未来信息。
- **IR-401**：`GET /api/v1/h2/owner/session` 应返回当前模式、市场、K 线、本人账户、
  可用动作、状态和错误，不返回参照策略或结果字段。
- **IR-402**：`POST /api/v1/h2/owner/session/{session_id}/orders` 应要求
  `client_request_id` 幂等键与规范动作（side/type/quantity/price），非法请求返回稳定
  错误且不产生副作用；重复请求幂等重放原结果。

### UX 需求

- **UX-401**：页面必须让用户在一个视图中看见价格、K 线、账户和市场时钟。
- **UX-402**：下单按钮必须有可见的 enabled/submitting/disabled/rejected 状态，并在无
  报价或断线时阻止误操作。
- **UX-403**：自由模拟以 `SIM` 环境角标标识；采集模式必须持续显示 `training`/`formal`
  阶段，不显示未来信息、参照策略状态或未解盲结果。
- **UX-404**：页面必须提供可读的断线、空行情、拒单、中止和完成状态，不依赖浏览器控制台排错。

### 非功能需求

- **NFR-302**：owner 数据最小化、假名化、退出和本地保留边界必须明确；session artifact
  不得包含直接身份信息。（原条款中「不得把 owner 结果写成人群结论」随 N-of-1 采集轨
  一并归档——本里程碑不产出 owner 结果。）
- **NFR-401**：loopback 页面在无外部网络时可用；前端不引入交易凭据和第三方行情依赖。
- **NFR-402**：页面状态以服务端 session 为准，刷新或短暂断线不得重复提交委托。
- **NFR-403**：服务端部署与运行环境为 Linux（POSIX）；终端是浏览器页面，客户端操作系统不是部署面、不在验收范围；不得要求新增不可审计的全局服务或数据库。

## 5. 生命周期与不变量

```text
PREVIEW_BLOCKED -> PREVIEW_READY   Web 页面、行情、K 线、按钮和故障路径验收通过
PREVIEW_READY -> TRAINING          发放训练 assignment，结果仍隔离
TRAINING -> FORMAL_ARMED           6 个训练完成且正式 assignment/协议版本匹配
FORMAL_ARMED -> FORMAL_RUNNING     进入冻结的市场时间跨度并隐藏结果/参照策略
FORMAL_RUNNING -> COMPLETED        24 个场景按冻结规则完成
FORMAL_RUNNING -> INCOMPLETE_STUDY 冻结停止规则命中且未满 24 场：生成 incomplete-study，非 completed
TRAINING -> OWNER_ABORT            所有者主动中止训练：写稳定 reason code 后进入终态
FORMAL_RUNNING -> OWNER_ABORT      所有者主动中止正式场景：同上，且不补跑
FORMAL_RUNNING -> TECHNICAL_ABORT  断线/完整性/服务故障命中冻结无效条件
TECHNICAL_ABORT -> RERUN_PENDING   仅技术原因且备用池仍有可用项
```

**采集态转换已归档（2026-09-20，ADR-010）**：上表中 `TRAINING` / `FORMAL_ARMED` /
`FORMAL_RUNNING` / `COMPLETED` / `INCOMPLETE_STUDY` / `RERUN_PENDING` 属已归档的 N-of-1
采集轨，其 guard 机械与测试保留在仓库但本里程碑不执行；本里程碑交付并收口的是
`PREVIEW_BLOCKED -> PREVIEW_READY` 以及自由模拟态下的 `OWNER_ABORT` / `TECHNICAL_ABORT`
区分。下列语义描述保留为归档轨的契约记录。

`OWNER_ABORT` 是终态，区别于可补跑的 `TECHNICAL_ABORT`：owner 主动中止不消耗备用池、
不生成补跑样本，也不进入 owner evidence index；只有技术中止才按冻结顺序从备用池整局
补跑（Q-305/DQ-305）。`INCOMPLETE_STUDY` 也是独立终态：只描述未满 24 场的冻结停止结果，
不得写成 `COMPLETED`，也不产生研究声明。

不变量：

- 所有委托必须经服务端幂等校验与既有撮合、账本、风控路径；前端状态不能单独证明提交成功。
- 逻辑时点采样由服务端完成，采样不产生用户可见的节奏约束；委托因果链完整可追溯。
- 主动中止与技术中止必须区分并写稳定 reason code：客户端只能触发 owner 主动中止，进入
  `OWNER_ABORT` 终态，不消耗备用池、不补跑、不进入 evidence index；`TECHNICAL_ABORT` 分类
  只由服务端完整性/故障检测产生，技术中止才允许按冻结顺序从备用池整局补跑。
- K 线只来自冻结 public tape 的派生视图；时间压缩比为冻结参数；若 K 线/盘口构成新增
  观察信息，必须新协议版本并匹配参照策略信息集。
- owner 采集模式的可见字段冻结为白名单：`best_bid`/`best_ask`/`last`、市场时钟、盘口
  档位（≤10）、最近成交、多周期 OHLC（周期集合随 E1）、本人权益/可用/未实现/仓位/
  占用保证金/保证金比率/账户状态、当前挂单与动作状态；白名单外字段（24h 涨跌/高低/
  成交量、标记价格、资金费率与倒计时、买卖深度比条、MA 等图表指标、白名单外周期、
  预估强平价）只允许作为自由模拟的工程演示，采集模式与 artifact 中一律不出现。任何
  白名单外字段若要进入采集观察，必须先升级 owner observation/protocol 版本，并让参照
  策略获得同一信息集（Q-401/E1）。
- training、preview、formal 和 AI evidence index 始终隔离；自由模拟会话永不进入任何
  实验证据索引；owner session 不进入 AI 研究声明。
- 结果字段对中止、补跑和解盲裁决不可见；所有者只能看到当前允许的行情和本人账户。

## 6. 成功与验收

### 成功标准

- **SC-401**：本地新进程可打开 Web 页面并在无外部网络时显示合成报价、账户和至少一根
  完整 K 线。
- **SC-402**：固定输入可完成合法市价/限价委托、撤单、拒单、断线、刷新恢复和退出，委托
  与事件哈希一致。

> **SC-403 / SC-404 已移除（2026-09-20，ADR-010）**：两者都以「6 训练 + 24 正式场景
> 真实发生」为前提，该采集轨已归档。移除是范围裁决，不是未达标；版本根
> [`traceability.json`](../traceability.json) 中两者的 `status` 为 `removed`。

### 退出条件

| 退出 | 条件 | 证据 |
|---|---|---|
| E1 | owner observation/K 线周期与时间压缩比、协议版本、动作空间（市价/限价）、时点采样粒度、隐私边界，以及 owner 证据包布局/schema 与机器校验入口冻结 | contract review + protocol diff + validator 通过记录 |
| E2 | Web preview 可打开，价格/K 线/账户/下单/错误状态和门控通过 | browser preview bundle |

E3（训练场景）与 E4（正式采集）随 N-of-1 轨归档移除；本里程碑以 E1、E2 收口。

### 验收清单

- [x] **AC-401** (`FR-401`, `IR-401`, `UX-401`, `SC-401`): 页面显示真实生成的 bid/ask/last、账户和
      多周期 K 线，无报价时不显示伪价格。
- [x] **AC-402** (`FR-402`, `IR-402`, `TR-401`): 市价/限价委托进入既有撮合路径；非法输入稳定拒绝
      且零副作用；限价成交/撤单状态流转与操作回报一致。
- [x] **AC-403** (`FR-403`, `IR-301`, `UX-403`): preview 未通过时 training/formal 入口 fail closed；
      采集态视图的白名单与结果隔离由归档轨的 guard 测试锁定。
- [x] **AC-404** (`DR-401`, `DR-402`, `NFR-302`, `NFR-401`, `NFR-403`): artifact 绑定协议/时间/哈希，loopback
      无外部行情和凭据依赖；session artifact 不含直接身份信息。
- [x] **AC-405** (`FR-302`, `TR-302`, `NFR-402`): owner 委托沿既有撮合、账本和风控路径，时点采样
      完整；刷新/断线不重复委托。
- [x] **AC-406** (`UX-402`, `UX-404`): enabled/submitting/disabled/rejected 按钮状态与断线、空行情、
      拒单、中止、完成状态可见且可操作。

> **AC-407 / AC-408 已移除（2026-09-20，ADR-010）**：两者分别验收个人描述性报告与
> 训练/正式阶段的 evidence index 重建，均属已归档的采集轨。AC-407 中仍然有效的
> 「artifact 不含直接身份信息」已并入 AC-404。

## 7. 测试、依赖与决策

### 测试策略

- 单元测试：多周期 K 线聚合、时间压缩比换算、报价空态、委托规范化、数量/价格/幂等校验、
  时点采样快照。
- 集成测试：Web session API、既有市场路径、限价成交与撤单、断线/中止/补跑、artifact 哈希
  和阶段 guard。
- UI / E2E：浏览器打开、K 线多周期刷新、委托反馈、拒单、无报价和结果盲。
- 真实环境 / 手动验证：Linux（POSIX）本地 loopback 用真实浏览器完成一次 preview（客户端 OS 不限、
  不在验收范围）；正式 owner 场景
  只在 E2/E3 通过后启动。6/24 个真实场景的完成证据固定落在 `docs/experiments/owner-n-of-1/`
  （`environment.json` + `owner-session-manifest.json` + `owner-evidence-index.json`），机器校验
  入口为 `python tools/validate_owner_evidence.py --dir <path>`；证据须包含目标环境记录
  （OS/Python/启动命令）、唯一 `session_id`、哈希、排除/补跑流。非退化断言按完成状态条件化：
  完整样本（24 场）断言非退化；`incomplete-study` 按实际样本数断言非退化；零样本以文档化的
  冻结停止原因通过，不被非退化门拒绝。集成测试只验机制，不能单独证明真人场景已经发生。
  平台目标以仓库 CI 矩阵 Python 3.11/3.13 为准，本地其它解释器版本只作额外冒烟。

### 依赖

- 上游 Feature / Contract：0.3.1 H2 protocol/session/guard、0.2.1 interactive runtime、event schema。
- 下游消费者：owner training/formal runner、owner evidence index 和个人描述性报告。
- 外部 / 环境依赖：项目所有者分四天完成场景；不依赖外部网络、交易所或外部参与者。

### 决策与风险

| 决策 / 风险 | 结论或缓解 | 理由 | 后续 |
|---|---|---|---|
| 行情来源 | 只读冻结合成 public tape，不接外部行情 | 可复现、无凭据、无真实交易风险 | E1 冻结 tape/协议版本 |
| 时间模型 | 内核逻辑步进与合成交易所墙钟分离，由冻结压缩比连接；采集 1:1 实时 | 贴近真实交易体验且保持确定性 | ADR-006；压缩比随 E1 冻结 |
| K 线信息集 | 多周期为同一冻结 tape 的派生视图；若成为新增观察信息则升级协议并匹配控制 | 防止页面改善改变正式估计对象 | Q-401/E1 拍板 |
| 页面部署 | loopback-only、依赖现有 Python 服务 | 先解决所有者本地可用性 | 后续另立公开部署 Feature |
| 所有者时间 | Web preview 先闭环，训练和正式场景后置 | 避免四天时间被页面缺陷消耗 | E2 未通过不得开始 E3 |

## 8. 待确认问题

- [x] Q-401: K 线信息集 — 决策（2026-09-13）：多周期 K 线是同一冻结 public tape 的派生视图，不新增信息源；参照策略对比为场景级描述性。周期集合与时间压缩比的冻结值属待冻结部分，由 T929 在 E1 前拍板（见退出条件 E1），不再计入已闭合范围。
- [x] Q-402: 是否连接真实行情或真实账户？— 决策：否，仅 loopback 合成市场和本地 artifact。
- [x] Q-403: owner 轨放弃 8s 决策窗口合同（2026-09-13，ADR-006）——自由连续交易 + 服务端逻辑时点静默采样，场景为冻结的市场时间跨度，修订 Q-303 的 owner 部分；AI 正式轨不变。
