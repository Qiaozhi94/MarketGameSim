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
updated: 2026-09-13
---

# 0.3.2：Web 交易终端与所有者 N-of-1 采集 - 设计

> Owner: TBD | Spec: `spec.md` | Tasks: `tasks.md`

## 0. 输入与约束

- **行为契约**：[`spec.md`](spec.md)。
- **PRD / Architecture**：[`../../../market-game-sim-prd.md`](../../../market-game-sim-prd.md) §15 H2-D、
  [`../../../market-game-sim-architecture.md`](../../../market-game-sim-architecture.md)。
- **上游 Contract**：[`0.3.1 design`](../0.3.1-human-in-the-loop-experiment/design.md)、
  [`interactive-session`](../../../contracts/interactive-session.md)、H2 frozen protocol。
- **实现约束**：复用既有 loopback HTTP 服务和 H2 session controller；不引入交易凭据、外部
  行情、数据库或新的撮合/账本实现；正式 owner 场景必须在 Web preview gate 通过后才可开始。

## 1. 技术概要与影响面

新增一个 H2 owner Web adapter，把既有 session view 和 canonical input 映射为浏览器可读 JSON，
再用原生 HTML/CSS/Canvas 或 SVG 渲染报价、K 线、账户和动作状态。页面只负责展示和提交意图，
服务端 session lock 负责窗口裁决，市场内核继续拥有撮合、账本、保证金和强平。

- 前端：单页 loopback terminal，报价卡、K 线图、账户卡、窗口倒计时、动作按钮和错误/空态。
- 后端 / API：H2 owner session 的 view/decision/abort/status 路由和稳定错误码。
- 存储 / Migration：owner session manifest、K 线派生 artifact、输入/事件哈希；不引入数据库。
- Runtime / Agent Adapter：复用 H2 owner target-slot adapter 和有限窗口 controller，不添加人类账户。
- Event / Evidence：写 canonical input receipt、`NO_ACTION`、窗口状态和 artifact refs；owner index 独立。
- 文档 / 配置：冻结 K 线聚合周期、观察信息集、页面启动手册和训练前 gate。

## 2. 架构与模块边界

```text
H2 protocol/assignment -> owner session controller -> H2 owner Web adapter -> browser terminal
                                      |                         |
                                      +-> market runtime/event log
                                      +-> session/artifact manifest
public tape -------------------------> Kline projector
```

- session controller 是窗口、状态和一次性动作槽的唯一真相源；浏览器不能自行推进逻辑时间。
- Web adapter 只将 `view()` 和 canonical decision contract 序列化为 HTTP；不复制交易业务逻辑。
- Kline projector 只读 public tape 和已冻结的窗口时间，不读取私有账户、参照策略或未来事件。
- 页面渲染层不缓存可提交动作的成功状态；每次提交以服务端回执为准，刷新后从 session view 重建。
- owner evidence index 只消费合格 owner manifest，不被 AI formal analyzer 自动扫描。

## 3. 数据模型与 Migration

- `OwnerWebSessionView`：阶段、窗口、可见报价、K 线、本人账户、动作能力和状态。
- `OwnerDecisionReceipt`：`session_id`、`window_id`、`input_seq`、`intent_id`、动作、数量、
  服务端裁决、错误码和事件引用。
- `KlineSeries`：`t_open/t_close/open/high/low/close/volume`（若 volume 属于 public tape），
  `bar_period_windows`、源 tape 版本、窗口范围和内容哈希。
- `owner-session.json`：协议/assignment/client/artifact 哈希、技术状态、reason code 和训练/formal 标志。

历史 H1 session 不迁移为 H2 owner evidence；H1 仍只能 replay。若 K 线成为新的正式观察字段，
通过新 H2 protocol version 和新 assignment 处理，不修改已冻结 `0.3.1` 协议。

## 4. 接口、Contract 与 Event

### API / CLI / Adapter Contract

- 复用 `python -m market_game_sim.interactive.client` 的 loopback 启动能力，新增 H2 owner 页面/路由，
  不新增公网监听或 console script。
- `GET /api/v1/h2/owner/session` 返回版本化 `view`：`stage`、`window`、`market`、`kline`、
  `account`、`actions`、`status`、`server_time` 和 `protocol_hash`（正式态可隐藏 hash）。
- `POST .../decision` 的线性化点是 session lock 内占用窗口动作槽；迟到、重复和非法请求分别
  返回 `WINDOW_CLOSED`、`DUPLICATE_INPUT`、`INVALID_ACTION`/`INVALID_QTY`。
- `POST .../abort` 只写 owner/technical abort reason，不读取结果字段；status 路由用于刷新恢复。

### Event / Trace Contract

- 页面点击先成为规范 input，再进入既有 `AGENT_DECIDE -> ORDER_* -> TRADE/ACCOUNT/LIQUIDATION` 链。
- 无动作窗口写 `NO_ACTION`；服务端接收时间只作依从性诊断，不改变逻辑事件排序。
- 每个 view 的 K 线带源 tape/version hash，避免 UI 自行从浏览器轮询数据重算出另一套历史。

## 5. Runtime、Workflow 与并发

- `view` 是只读；`decision`、`abort` 与 deadline 事件竞争同一 session lock。
- 浏览器可轮询或重连，但不允许客户端恢复一个已消费的 `input_seq`；服务端以 assignment/session 状态为准。
- 页面断线不暂停市场；窗口结束照常 `NO_ACTION`，技术故障是否补跑由冻结 adjudication 决定。
- preview、training、formal 使用不同 stage guard；正式结果字段永不放入 owner view。
- 开发顺序是 `contract/Kline -> preview -> training -> formal`，E2 未通过时启动入口 fail closed。

## 6. UI 与可观测性

- **交互设计原型（可离线打开的 HTML）**：[`interaction-design.html`](interaction-design.html) ——
  v3 按所有者 2026-09-13 反馈改为**真实终端形态**：自由连续交易（市价/限价、点盘口填价、挂单与撤单）、
  1m—4h 多周期 K 线与时间轴、最新 K 线为普通实时蜡烛、带列名的最近成交表、委托回报状态流转、
  SIM 环境角标与「ⓘ 市场说明」。原实验协议元素（8 秒决策时点、阶段徽标、解盲清单、门禁/休息/结果盲页）
  拆入「采集模式」并在原型［实验模式］状态组与设计说明「真实终端对齐审查」表中保留检视；
  该拆分属需求变更（0.3.2 仍为 draft），待 owner 裁决 DQ-H 后同步修订 spec/design 相应条目。
- 桌面优先三栏：左侧报价/账户，中间 K 线与最近成交，右侧窗口状态和买卖按钮。
- K 线使用明确的 OHLC tooltip/空态；没有完整 bar 时显示数据不足，不绘制看似真实的占位蜡烛。
- 按钮状态至少有 enabled、submitting、submitted、disabled、rejected；中止按钮始终可见但需确认。
- 页面显示合成市场/无真实资金、阶段、窗口倒计时和服务状态；不显示 seed、参照策略或未来事件。
- 诊断只记录 session/window/client/error/latency/hash，不记录键盘、屏幕或无关行为遥测。

## 7. 失败、恢复、安全与兼容

- 校验与失败映射：协议/assignment/stage/session 不匹配在输入写入前失败；数量、窗口和重复
  输入使用稳定错误码，前端展示可读消息。
- 重启与恢复：浏览器刷新只重新读取 view；服务端故障写 `TECHNICAL_ABORT`，不得拼接半局日志。
- 权限 / escalation / 凭据边界：绑定 loopback；无登录凭据、无真实资金、无外部 API token。
- Windows / POSIX / 版本兼容：复用现有 Python 3.11/3.14 支持矩阵，路径和定时器不依赖 shell 特性。

## 8. 测试策略与验收映射

| 验收项 | 测试层级 | 计划文件 / 场景 | 关键断言 |
|---|---|---|---|
| `AC-401` | unit / integration / UI | `tests/unit/interactive/test_kline_projection.py`、`tests/integration/test_h2_owner_web.py` | 报价/K 线/空态真实来自 public tape |
| `AC-402` | unit / integration / UI | `tests/unit/experiment/test_owner_input_contract.py`、`tests/integration/test_h2_owner_web.py` | 一次性窗口动作、非法/迟到/重复拒绝 |
| `AC-403` | integration / UI | `tests/integration/test_h2_owner_web.py` | preview gate、stage guard、正式结果盲 |
| `AC-404` | unit / integration | `tests/unit/experiment/test_owner_privacy.py`、`tests/integration/test_h2_owner_web.py` | artifact 哈希、loopback、无凭据/外部行情 |
| `AC-405` | integration | `tests/integration/test_experiment_session.py`、`tests/integration/test_h2_owner_web.py` | session lock 与既有交易路径一致 |
| `AC-406` | UI / E2E | `tests/e2e/test_h2_owner_terminal.py` | loading/empty/error/timeout/abort/completed |
| `AC-407` | unit / integration | `tests/unit/experiment/test_owner_privacy.py` | PII 与人群结论边界 |
| `AC-408` | integration / manual | `tests/integration/test_h2_owner_delivery.py` | manifest 重建、训练/正式分离、备用补跑 |

批量测试覆盖至少 2 个协议版本、无报价首窗、K 线不足周期、重复点击、迟到输入、断线和技术中止。
浏览器 E2E 只在功能 contract 稳定后加入；真实 owner 场景不作为自动化 fixture。

## 9. 已确认决策与残余风险

| 决策 / 风险 | 结论或缓解 | 理由 | 替代方案 / 后续 |
|---|---|---|---|
| 技术栈 | 复用依赖清单外的原生 loopback HTTP/HTML/Canvas 或 SVG | 降低 Python 3.14、Windows 和离线启动风险 | 后续若需要公开产品再另立前端 Feature |
| K 线周期 | preview 默认 5 个逻辑窗口聚合一柱 | 现有 owner 场景通常少于 60 窗，60 秒一柱可能长期没有完整柱 | Q-401 决定正式协议是否升级 |
| 订单动作 | MVP 只暴露 H2 已冻结动作空间允许的买/卖/不行动/撤销 | 防止 Web UI 偷换交易语义 | 复杂限价单另立需求 |
| 个人数据 | 只用 owner research pseudonym，本仓库不保存身份映射 | 所有者是设计者与被试，结果只能个人描述 | 发布前 PII 扫描和人工复核 |

## 10. 待确认设计问题

- [ ] DQ-401: 若正式 K 线作为观察字段，参照策略是否同步接收同一派生序列并生成新 protocol version？
