---
kind: milestone
id: 0.4.1
version: "0.4"
related_features:
  - 0.3.1
  - 0.3.2
topics:
  - market-ecology
  - trader-strategy-layer
  - stylized-facts
doc_kind: design
created: 2026-09-19
updated: 2026-09-21
---

# 0.4.1：AI 市场生态 - 技术设计

> Spec: [`spec.md`](spec.md) | Tasks: [`tasks.md`](tasks.md)

## 0. 输入与约束

- 行为真相源：[`spec.md`](spec.md)；本文不复制需求正文，只写实现方案与边界。
- 架构决策：[`ADR-011`](../../../decisions/011-market-engine-trader-layering.md)（L1/L2 分层、
  不引入基本面、Alpha101 子集、alphamill 单向边界）、
  [`ADR-010`](../../../decisions/010-market-ecology-research-pivot.md)（研究方向）、
  [`ADR-003`](../../../decisions/003-goal-driven-agents-and-flagship-identification.md)（目标驱动代理与运行族矩阵）。
- 全局不变量（数值口径 C1/C2、事件因果链、确定性）由
  [`代理策略合同`](../../../contracts/agent-strategy.md) 与
  [`架构文档`](../../../market-game-sim-architecture.md) 唯一拥有；本文只引用，不重定义。
- 硬约束：不修改 L1 既有合同（撮合、账本、保证金、强平、事件 schema）。
- 实测基线（ADR-011 背景表）：双代理 3.0 笔/分钟、盘口可用 52.3%、
  40 交易者装配 4–5 秒墙钟/逻辑秒。

## 1. 技术概要与影响面

三件事按依赖顺序落地：

1. **冷启动锚**——改 `agent/goal.py` 的 degenerate 分支语义（新增锚定分支，不动既有
   `EWMA_WARMUP` 语义的对外行为），使零成交市场可产生首笔委托。锚来源是可插拔接口，
   本里程碑只注册 `synthetic`（spec Q-501）；`historical_snapshot` 由 ADR-014 承接。
2. **L2 策略层**——新增 `agent/strategy_layer/` 包：`TraderStrategy` 协议、注册表、
   分级信息集与原生策略族实现；通过既有 `GoalModel` 注册表与
   `world["behavior_mapping"]` 接缝接入，`_dispatch_agents` 的分发逻辑不变。
3. **质量判据**——新增 `metrics/market_quality.py`（市场质量六项，本里程碑首次定义）；
   stylized facts **扩展既有的 `metrics/validation.py`**，不新建并列模块：厚尾（超额峰度
   z 检验）、收益自相关、`|r|` ACF 三项的口径与实现由已冻结的
   [`0.1.2 基准市场验证协议`](../../../experiments/0.1.2-market-validation-protocol.md)
   拥有，本里程碑只追加 lag 50 延伸与协议未覆盖的两项（成交量—波动相关、订单流长记忆），
   并复用 `experiment/stats.py::holm_bonferroni` 做家族校正。另交付 `StrategyRoster` /
   `MarketQualityReport` 两类 artifact 与校验入口。

影响面：`experiment/h2/live_market.py`（换装配来源、补运行入口）、
`bench/population.py`（复用群体构建，不改其对 BENCH-001 的既有语义）、
`RUN.md`（新增 live 市场入口）。**不影响** `experiment/h2/runner.py` 的配对轨路径与
0.3.1 已签收结果——回归由既有测试全绿保证。

## 2. 架构与模块边界

```text
L1 交易引擎（不改；分层见架构文档 §1 与 ADR-013）
  L1b kernel/ book/matching.py ledger/ eventlog/ hook/   准入、结算、保证金、强平、事件因果链
  L1a book/orderbook.py book/engine.py                    纯撮合核心
        ▲ ORDER_ARRIVAL / TRADE_SETTLE / 事件记录
        │
L2 交易者策略层（本里程碑新增；即架构文档的 L2b）
  agent/strategy_layer/
    protocol.py     TraderStrategy 协议 + 分级信息集定义
    registry.py     策略族注册表（fail closed）
    families/       trend_following / mean_reversion / sentiment_noise / market_maker_v2
    external.py     外部信号注入接口（Alpha101 子集；alphamill 适配器移出，见 spec §3）
        ▲ StrategyRoster 装配
        │
装配与度量
  experiment/h2/live_market.py        持续市场载体（换装配来源 + 运行入口）
  metrics/market_quality.py           市场质量六项（新增）
  metrics/validation.py               stylized facts：既有三项复用 + 新增两项与 lag 50 延伸
                                      （口径拥有者仍是 0.1.2 冻结协议）
```

边界规则：L2 只能读分级信息集、只能输出目标仓位或委托意图；它不持有账本引用，
不调用撮合，也不写事件——这些仍由 L1 的既有 handler 路径完成。

## 3. 数据模型与 Migration

- `StrategyRoster`（新增，JSON）：`roster_id`、`seed`、`families[]`（族标识、数量、
  参数、时间尺度）、`bootstrap_anchor`（冷启动锚冻结参数，含来源标识 `source`）、`engine_config_digest`。
  由 `roster_id` 可重建装配（DR-501）。
- `MarketQualityReport`（新增，JSON）：`run_id`、`roster_id`、`logical_seconds`、
  `quality{}`（六项实测）、`stylized_facts{}`（五项实测）、`thresholds{}`、
  `verdicts{}`（逐项通过判定）、`failed[]`（顶层可见的未通过项）、`content_hash`。
- 无既有数据迁移：两类 artifact 都是新增文件，不改写任何既有 artifact 布局。
- 运行头新增字段：`strategy_roster_id` 与 `bootstrap_anchor`，供重放判定（NFR-502）。
  字段增补遵循既有运行头合同的向后兼容规则，不改既有字段语义。

## 4. 接口、Contract 与 Event

- `TraderStrategy` 协议（IR-501）：`decide(info: TieredInformationSet, state, prefs)
  -> StrategyDecision`；`StrategyDecision` 携带目标仓位或委托意图 + 族标识。
  协议版本号随协议变更递增。
- 分级信息集：按策略族声明的**信息层级**裁剪——`I0` 盘口顶档 + 自己账户；
  `I1` 增加最近成交流；`I2` 增加多周期 K 线；`I3` 增加外部信号通道。层级用 `I`
  前缀，避免与架构分层 L0—L4 撞名（同一仓库两个「L2」的教训见架构文档 §1）。
  裁剪在 L2 内完成，L1 的信息集构建逻辑不变。
- 注册表：`register_strategy(family)` / `get_strategy(family_id)`；未注册标识抛出
  稳定错误码，装配阶段即失败（fail closed）。
- 外部信号接口（IR-502）：扩展既有 `world["external_decision_sources"]` 的决策契约，
  从「`NO_ACTION` / `MARKET`」扩展到同时支持 `LIMIT`，并增加 `signal_version` 字段；
  非阻塞——源未就绪时返回 `NO_ACTION` 而不是等待。既有 owner 轨的阻塞式用法保持可用。
- 事件：**不新增事件类型**。策略族标识与信号版本写入既有 `AGENT_DECIDE` 记录的
  `internal_state`，因果链仍由 `intent_id` / `decision_event_id` 承载（TR-501）。

## 5. Runtime、Workflow 与并发

- 装配：读 `StrategyRoster` → 构建 `AgentSpec` 列表（复用 `bench/population.py` 的
  抽样原语，保持 KR-004 的 keyed draw 口径）→ 构建 world → bootstrap 首批 observe。
- 推进：`LiveMarket.advance()` 维持既有「注入外部委托 → 内核批量处理 → 采样」结构；
  本里程碑只换装配来源与补度量，不改推进语义。
- 并发：HTTP 服务线程与推进线程仍由 `LiveMarket.lock` 串行化；外部信号适配器必须
  非阻塞，避免把网络/文件延迟带进内核事务（IR-502）。
- 性能路径（NFR-501）：**退路顺序与各自代价已在 spec §7 决策表冻结，设计阶段不再重开**。
  已知实测（ADR-011 背景表 + live_market 实测）：40 交易者装配 4–5 秒墙钟/逻辑秒，
  事务以做市商撤挂为主——50 万笔委托对 0 笔成交，成交/委托 = 0.00019，说明绝大多数
  事务是「挂上去又撤掉」。`T970` 的第一步是把这个构成量化落盘（按事件类型统计
  `ORDER_ARRIVAL` / `ORDER_CANCELLED` / `TRADE_SETTLE` 的占比与耗时），再按 spec §7
  的固定顺序取用退路：① 做市商重报价频率/撤单策略 → ② 拉长观察/采样间隔 →
  ③ 降低代理数。取用 ③ 时不得同时下调 SC-502 的任何判据。

## 6. UI 与可观测性

- 本里程碑不改 Web 终端界面。
- 可观测产物是两类 artifact 与一个 CLI 报告：运行结束（或按间隔）导出
  `MarketQualityReport`，未通过项在报告顶层与 CLI 输出的第一屏可见。
- live 市场的 CLI 已存在（`experiment/h2/live_market.py::main`），缺的只是 `RUN.md` 登记，
  由 T978 承接。

## 7. 失败、恢复、安全与兼容

- 冷启动锚缺失或参数非法：装配阶段失败，不进入运行——避免再次出现「跑起来了但
  一单不发」的静默死锁。
- 某策略族全员退出（强平/风控）：市场继续，质量报告记录该族的退出时点与存活数。
- 外部信号源异常（缺失、超时、非法、版本不匹配）：该族降级为 `NO_ACTION`，写稳定
  原因码，内核照常推进。
- 兼容性：0.3.1 配对轨与 H2 双代理配置走原路径，行为不变；L2 分层是新增路径，
  既有 `GoalModel` 调用点保持可用。
- 安全与边界：沙盘 artifact 一律标注 `engineering-demonstration` 与单向边界声明；
  不含外部凭据，不访问外部网络。

## 8. 测试策略与验收映射

| AC | 主要测试 | 层次 |
|---|---|---|
| AC-501 | 冷启动锚正反测试（有锚产生首笔委托 / 无锚复现死锁） | 单元 + 集成 |
| AC-502 | 注册表注册与 fail closed 正反用例 | 单元 |
| AC-503 | 同清单同种子逐点复现、`roster_id` 重建装配 | 集成 |
| AC-504 | 市场质量六项口径；达标与未达标两种装配 | 单元 + 集成 |
| AC-505 | stylized facts 在合成对照序列上的正反判定 | 单元 |
| AC-506 | 跨种子内生不稳定事件存在性判定；出现→记录触发条件与频次，未出现→如实产出「不存在」结论（两者都算达标，SC-503） | 集成 |
| AC-507 | 外部信号族的委托因果链、降级路径 | 集成 |
| AC-508 | 公式筛查器拒绝 `rank`/`IndNeutralize`/`cap`；边界声明落盘 | 单元 |
| AC-509 | 墙钟/逻辑秒断言（失败即红） | 性能 |
| AC-510 | 多族多记录并存的批量因果链用例 | 集成 |

既有回归：0.3.1 与 H2 双代理路径的既有测试必须全绿，作为「L2 分层无回归」的证据。

## 9. 已确认决策与残余风险

- 已确认：不引入基本面/价值过程；不做多标的；Alpha101 只取纯时序子集；
  alphamill 单向消费；质量门限值由 spec §6 唯一拥有（均见 ADR-011）。
- 残余风险 1：冷启动锚可能改变既有 `GoalModel` 的边界行为——缓解是锚只在
  「无公开成交流」条件下生效，且既有测试全绿作为回归门。
- 残余风险 2：stylized facts 可能在门限内仍「看起来不像」——缓解是门限与口径
  冻结在 spec §6，调整须留 git 痕迹与理由，禁止为通过而调门限。
- 残余风险 3：性能可能需要降低代理数，而代理数下降又会削弱 stylized facts。
  **取舍方式本身不再留到实测后拍板**：退路顺序、各自代价与「取用降代理数时禁止同时
  下调 SC-502 判据」已写进 spec §7 决策表；Q-503 只剩一个待实测填入的参数（临界代理数）。

## 10. 待确认设计问题

- [x] DQ-501: 冷启动锚放在 `goal.py` 的 degenerate 分支，还是放在 L2 策略层内各族自行实现？— 决策（owner 2026-09-21）：放在 `goal.py` 的共享锚定分支，锚来源经可插拔接口注入；各族自行实现会让 ADR-014 的 `historical_snapshot` 接入时逐族改动。
- [x] DQ-502: 分级信息集的四个层级（I0—I3）是否够用，外部信号通道是否需要独立层级？— 决策（owner 2026-09-21）：够用；外部信号保持为最高层级 I3，不另立层级，其可审计性由 TR-501 的信号来源标识与版本承担。
- [x] DQ-503: `external_decision_sources` 扩展为非阻塞后，owner 轨既有阻塞式用法如何保持二者共存？— 决策（owner 2026-09-21）：每个外部决策源声明 `blocking` 标志，缺省 `true`（owner 轨行为不变），量化族显式声明 `false`；不改既有调用点。
