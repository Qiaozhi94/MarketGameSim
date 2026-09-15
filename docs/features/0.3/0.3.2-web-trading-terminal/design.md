---
kind: milestone
id: 0.3.2
version: "0.3"
related_features:
  - 0.3.1
topics:
  - web-terminal
  - owner-n-of-1
  - kline
  - human-in-the-loop
doc_kind: design
created: 2026-09-12
updated: 2026-09-14
---

# 0.3.2：Web 交易终端与所有者 N-of-1 采集 - 设计

> Owner: TBD | Spec: `spec.md` | Tasks: `tasks.md`

> **开发前置约束（2026-09-16）**：进入代码开发前，`tasks.md` 必须补齐 `[TEST]` 组——
> 从体验旅程派生的可执行验收（编写早、执行晚，每旅程步骤 ≥1 条断言）。
> 开工门禁（SDD Flow T3）会拒绝缺失该组的流转。

## 0. 输入与约束

- **行为契约**：[`spec.md`](spec.md)。
- **PRD / Architecture**：[`../../../market-game-sim-prd.md`](../../../market-game-sim-prd.md) §15 H2-D、
  [`../../../market-game-sim-architecture.md`](../../../market-game-sim-architecture.md)。
- **上游 Contract**：[`0.3.1 design`](../0.3.1-human-in-the-loop-experiment/design.md)、
  [`interactive-session`](../../../contracts/interactive-session.md)、H2 frozen protocol。
- **实现约束**：复用既有 loopback HTTP 服务和 H2 session controller；不引入交易凭据、外部
  行情、数据库或新的撮合/账本实现；正式 owner 场景必须在 Web preview gate 通过后才可开始。
- **架构决策**：[`ADR-006`](../../../decisions/006-realtime-free-trading-owner-terminal.md)——
  真实世界时间与自由连续交易；实验约束收敛到采集模式。

## 1. 技术概要与影响面

新增一个 H2 owner Web adapter，把既有 session view 和 canonical input 映射为浏览器可读 JSON，
再用原生 HTML/CSS/Canvas 或 SVG 渲染报价、K 线、账户和动作状态。页面只负责展示和提交意图，
服务端 session lock 负责委托幂等与时点采样裁决，市场内核继续拥有撮合、账本、保证金和强平。

- 前端：单页 loopback terminal，报价卡、多周期 K 线图、账户卡、下单面板（市价/限价）、
当前挂单、操作回报表和错误/空态。
- 后端 / API：H2 owner session 的 view/decision/abort/status 路由和稳定错误码。
- 存储 / Migration：owner session manifest、K 线派生 artifact、输入/事件哈希；不引入数据库。
- Runtime / Agent Adapter：复用 H2 owner target-slot adapter 和会话调度 controller，不添加人类账户。
- Event / Evidence：写 canonical input receipt、逻辑时点采样快照和 artifact refs；owner index 独立。
- 文档 / 配置：冻结 K 线聚合周期、观察信息集、页面启动手册和训练前 gate。

## 2. 架构与模块边界

```text
H2 protocol/assignment -> owner session controller -> H2 owner Web adapter -> browser terminal
                                      |                         |
                                      +-> market runtime/event log
                                      +-> session/artifact manifest
public tape -------------------------> Kline projector
```

- session controller 是会话状态、委托幂等和逻辑时点采样的唯一真相源；浏览器不能自行推进
逻辑时间。
- Web adapter 只将 `view()` 和 canonical decision contract 序列化为 HTTP；不复制交易业务逻辑。
- Kline projector 只读 public tape 和已冻结的时间参数（压缩比/周期），不读取私有账户、参照策略或未来事件。
- 页面渲染层不缓存可提交动作的成功状态；每次提交以服务端回执为准，刷新后从 session view 重建。
- owner evidence index 只消费合格 owner manifest，不被 AI formal analyzer 自动扫描。

## 3. 数据模型与 Migration

- `OwnerWebSessionView`：模式、阶段、可见报价、多周期 K 线、本人账户、委托能力和状态。
- `OwnerDecisionReceipt`：`session_id`、`sample_point_id`、`input_seq`、`intent_id`、动作、数量、
  服务端裁决、错误码和事件引用。
- `KlineSeries`：`t_open/t_close/open/high/low/close/volume`（若 volume 属于 public tape），
  `bar_period`（1m/5m/15m/1h/4h）、时间压缩比、源 tape 版本、时间范围和内容哈希。
- `owner-session.json`：协议/assignment/client/artifact 哈希、技术状态、中止类型
  （`abort_kind=owner|technical`，其中 `technical` 只能由服务端故障路径写入）、reason code
  和训练/formal 标志。
- **owner 成果包固定布局**：`docs/experiments/owner-n-of-1/` 下 `environment.json`
  （`schema_version`/`os`/`platform`/`python`/`start_command`/`recorded_at`）、
  `owner-session-manifest.json`、`owner-evidence-index.json`、`kline/`。manifest 与 index
  带 `schema_version`、完成状态（`complete`/`incomplete-study`）、条数、唯一 `session_id`、
  每条哈希与 `exclusion`/`rerun_of` 流；机器校验入口为
  `python tools/validate_owner_evidence.py --dir <path>`，schema 与 validator 在 T929 先于任何
  真实采集冻结/实现，T942 只在采集后冻结 index，不再改动证据格式。

历史 H1 session 不迁移为 H2 owner evidence；H1 仍只能 replay。若 K 线成为新的正式观察字段，
通过新 H2 protocol version 和新 assignment 处理。owner 轨的决策窗字段已按
ADR-006/Q-403 从 H2 冻结协议移除并重新冻结（`protocol_hash` 变更，frozen 归档同步重建）；
AI_FORMAL 的窗口调度与 168 block 合同不受影响。

## 4. 接口、Contract 与 Event

### API / CLI / Adapter Contract

- 复用 `python -m market_game_sim.interactive.client` 的 loopback 启动能力，新增 H2 owner 页面/路由，
  不新增公网监听或 console script。
- `GET /api/v1/h2/owner/session` 返回版本化 `view`：`mode`、`stage`、`market`、`kline`、
  `account`、`resting_orders`、`status`、`server_time` 和 `protocol_hash`（正式态可隐藏 hash）。
- `POST .../orders` 的线性化点是 session lock 内的委托幂等登记；非法请求返回
  `INVALID_ACTION`/`INVALID_QTY`/`INVALID_PRICE`/`RISK_REJECTED`；重复请求按
  `client_request_id` 幂等重放原结果。
- `DELETE .../orders/{order_id}` 撤单；`POST .../abort` 幂等，**只表达 owner 主动中止**：
  写稳定 `OWNER_ABORT` reason code 后进入终态，不消耗备用池、不补跑、不进入 evidence index。
  `TECHNICAL_ABORT` 只能由服务端完整性/故障检测路径在内部生成，Web 请求不得提交该分类，
  客户端也不能选择是否消耗备用池；abort 不读取结果字段；status 路由用于刷新恢复。

### Event / Trace Contract

- 页面委托先成为规范 input，再进入既有 `AGENT_DECIDE -> ORDER_* -> TRADE/ACCOUNT/LIQUIDATION` 链。
- 服务端按冻结粒度对逻辑时点写采样快照（仓位/权益/净成交/动作数），无委托的时点不产生
  用户级输入记录；服务端接收时间只作依从性诊断，不改变逻辑事件排序。
- 每个 view 的 K 线带源 tape/version hash，避免 UI 自行从浏览器轮询数据重算出另一套历史。

## 5. Runtime、Workflow 与并发

- `view` 是只读；`orders`、`abort` 竞争同一 session lock；市场推进由服务端调度驱动。
- 浏览器可轮询或重连；同一逻辑委托在断线/重连后的重试必须复用原 `client_request_id` 以命中
  幂等重放，只有新委托或不同 payload 才使用新键；服务端以 assignment/session 状态为准。
- 页面断线不暂停市场；挂单在服务端继续生效，技术故障是否补跑由冻结 adjudication 决定。
- preview、training、formal 使用不同 stage guard；正式结果字段永不放入 owner view。
- 开发顺序是 `contract/Kline -> preview -> training -> formal`，E2 未通过时启动入口 fail closed。

## 6. UI 与可观测性

- **交互设计原型（最终交付版，可离线打开）**：[`interaction-design.html`](interaction-design.html) ——
  以币安现货页为布局基准的真实终端形态：买入/卖出页签 + 单一下单按钮、限价/市价、点盘口填价、
  PERP/USDT 双单位下单、杠杆 1–10× 与可配初始资金（资产页）、挂单/回报全宽底栏、多周期 K 线、
  SIM 环境角标与「ⓘ 市场说明」。本版承接 v4 按所有者 2026-09-13 反馈确立的真实终端形态，
  需求变更已由 Q-403/ADR-006 裁决；设计依据、逐项对齐审查与评审模式（`#review`）说明迁入
  [`interaction-design-notes.md`](interaction-design-notes.md)。
- 桌面优先三栏：左侧报价/账户，中间 K 线与最近成交，右侧下单面板和操作回报。
- K 线使用明确的 OHLC tooltip/空态；没有完整 bar 时显示数据不足，不绘制看似真实的占位蜡烛。
- **采集模式观察字段白名单**（与 spec §5 一致）：`best_bid`/`best_ask`/`last`、市场时钟、
  盘口档位（≤10）、最近成交、多周期 OHLC（周期集合随 E1）、权益/可用/未实现/仓位/占用
  保证金/保证金比率/账户状态、当前挂单与动作状态。原型 v4 的 24h 涨跌/高低/成交量、标记
  价格、资金费率与倒计时、买卖深度比条、MA(7/25/99)、1D 周期和预估强平价属**自由模拟
  专用工程演示**，采集模式隐藏，除非 E1 冻结为观察字段并让参照策略获得同一信息集（Q-401）。
- 按钮状态至少有 enabled、submitting、disabled、rejected；退出按钮始终可见但需确认。
- 自由模拟显示 SIM 环境角标与合成市场/无真实资金声明；采集模式持续显示阶段、场景进度和
  服务状态；两者都不显示 seed、参照策略或未来事件。
- 诊断只记录 session/window/client/error/latency/hash，不记录键盘、屏幕或无关行为遥测。

## 7. 失败、恢复、安全与兼容

- 校验与失败映射：协议/assignment/stage/session 不匹配在输入写入前失败；数量、价格和重复
  委托使用稳定错误码，前端展示可读消息。
- 重启与恢复：浏览器刷新只重新读取 view；服务端故障写 `TECHNICAL_ABORT`，不得拼接半局日志。
- 权限 / escalation / 凭据边界：绑定 loopback；无登录凭据、无真实资金、无外部 API token。
- 部署环境 / 版本兼容：服务端部署目标为 Linux（POSIX），复用仓库 CI 现有 Python 3.11/3.13
  支持矩阵，路径和定时器不依赖 shell 特性；其它本地解释器版本只作额外冒烟，不作为验收目标。

## 8. 测试策略与验收映射

| 验收项 | 测试层级 | 计划文件 / 场景 | 关键断言 |
|---|---|---|---|
| `AC-401` | unit / integration / UI | `tests/unit/interactive/test_kline_projection.py`、`tests/integration/test_h2_owner_web.py` | 报价/K 线/空态真实来自 public tape |
| `AC-402` | unit / integration / UI | `tests/unit/experiment/test_owner_input_contract.py`、`tests/integration/test_h2_owner_web.py` | 市价/限价委托入既有路径、非法拒绝零副作用、撤单状态流转 |
| `AC-403` | integration / UI | `tests/integration/test_h2_owner_web.py` | preview gate、stage guard、正式结果盲 |
| `AC-404` | unit / integration | `tests/unit/experiment/test_owner_privacy.py`、`tests/integration/test_h2_owner_web.py` | artifact 哈希、loopback、无凭据/外部行情 |
| `AC-405` | integration | `tests/integration/test_experiment_session.py`、`tests/integration/test_h2_owner_web.py` | 幂等去重、时点采样与既有交易路径一致 |
| `AC-406` | UI / E2E | `tests/e2e/test_h2_owner_terminal.py` | loading/empty/error/disconnect/abort/completed |
| `AC-407` | unit / integration | `tests/unit/experiment/test_owner_privacy.py` | PII 与人群结论边界 |
| `AC-408` | integration / manual | `tests/integration/test_h2_owner_delivery.py` | manifest 重建、训练/正式分离、备用补跑 |

批量测试覆盖至少 2 个协议版本、无报价首窗、K 线不足周期、重复点击、迟到输入、断线和技术中止。
浏览器 E2E 只在功能 contract 稳定后加入；真实 owner 场景不作为自动化 fixture。
6/24 个真实 owner 场景的完成证据必须来自目标环境记录（OS/Python/启动命令）与真实 owner
manifest/evidence index（`docs/experiments/owner-n-of-1/`、唯一 `session_id`、哈希、排除/
补跑流），由 `tools/validate_owner_evidence.py` 校验；非退化断言按完成状态条件化（完整样本
断言非退化，`incomplete-study` 按实际样本数断言，零样本以文档化停止原因通过）。集成与 E2E
测试只验机制，不能替代真实场景已经发生的完成声明。

## 9. 已确认决策与残余风险

| 决策 / 风险 | 结论或缓解 | 理由 | 替代方案 / 后续 |
|---|---|---|---|
| 技术栈 | 复用依赖清单外的原生 loopback HTTP/HTML/Canvas 或 SVG | 降低 Python 版本和离线启动风险 | 后续若需要公开产品再另立前端 Feature |
| K 线周期 | 多周期（1m/5m/15m/1h/4h）为同一冻结 tape 的派生视图；时间压缩比采集 1:1、自由模拟可选加速 | 贴近真实交易体验且保持确定性 | 周期集合与压缩比随 E1 冻结 |
| 订单动作 | MVP 动作空间为市价/限价买卖委托与撤单（内核与 H1 合同已支持 order_type/price_ticks） | 真实终端形态的基础能力；采样替代用户侧节奏约束 | 止损/止盈等条件单另立需求 |
| 个人数据 | 只用 owner research pseudonym，本仓库不保存身份映射 | 所有者是设计者与被试，结果只能个人描述 | 发布前 PII 扫描和人工复核 |

## 10. 待确认设计问题

- [x] DQ-401: 已裁决（2026-09-13，ADR-006/Q-401）——K 线为同一冻结 tape 的多周期派生视图，周期集合与压缩比随 E1 冻结，参照策略对比为场景级描述性。
