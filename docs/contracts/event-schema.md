# 事件 Schema 与优先级类别

**适用范围**：跨规格实现合同（当前交付规格 002）  
**状态**：Stable（跨规格实现合同；变更须记 ADR 并提升 `schema_version`）  
**创建日期**：2026-07-29  
**对应任务**：T000d、T000j、T004　**支撑需求**：FR-008、KR-001—KR-003、KR-006、
KPI-002、KPI-007  
**关联**：
[ADR-005](../adr/005-numeric-and-serialization-contract.md)、
[ADR-006](../adr/006-same-timestamp-event-scheduling.md)、
[指标字典](../product/metrics-dictionary.md)

## 1. 全序键

每个事件持有唯一键：

```text
(timestamp, priority_class, seq)
```

- `timestamp`：整数纳秒逻辑时间（KR-002）。禁止浮点。
- `priority_class`：本文 §3 冻结的整数类别。同一时间戳下决定处理顺序。
- `seq`：全局单调递增计数器，事件入队时分配。同类别同时间戳的最终裁决。

**任何定序不得依赖字典/集合遍历顺序、对象标识或哈希值。** 订单簿的「时间优先」以
订单到达事件的 `seq` 判定，而非 `timestamp`——同一纳秒到达的两笔订单必须有确定
先后。

### 1.1 事件产生规则（KR-006）

处理事件 `e` 期间产生的任何新事件 `e'` 必须满足：

```text
key(e') > key(e)
```

违反时内核立即抛出异常并终止运行，**不得静默重排**（ADR-006 §1）。

推论：**同一 `timestamp` 内只允许沿 `priority_class` 递增方向推进**。要回到更小的
class，`timestamp` 必须先前进——因此 `AGENT_DECIDE`（class 4）产生的
`ORDER_ARRIVAL`（class 0）永远落在更晚的时间戳上。

为此**禁止零通信延迟**：所有代理的 `latency_ns ≥ 1`（FR-007）。零值配置在校验阶段
拒绝，不静默替换为 1。纳秒粒度下 1 ns 已足以表达「几乎无延迟」，且零延迟无现实
对应。

该约束**只针对通信延迟**——`AGENT_DECIDE`(4) → `ORDER_ARRIVAL`(0) 是唯一回退 class
的跳转。其余跳转沿 class 递增，键本就严格递增：`TRADE_SETTLE`(1) →
`MARKET_DATA_PUBLISH`(2)、`MARKET_DATA_PUBLISH`(2) → `AGENT_OBSERVE`(3)、
`AGENT_OBSERVE`(3) → `AGENT_DECIDE`(4) **均允许同时间戳，间隔可为 0**
（ADR-006 §2）。观察与决策分为两个 class 是为了让信息集独立记录（§3.1），不意味着
两者必须在时间上分开。

若无此规则，`AGENT_DECIDE` 在同一时间戳插入 class 0 事件会破坏事件队列的单调性，
「数值越小越先处理」在实现层无法成立，KPI-002 的哈希输入顺序随之不确定。

## 2. 冻结约束

**`priority_class` 的取值与语义一经冻结不得静默变更。**

变更将使历史实验的事件摘要哈希（KPI-002）不可比。如需变更，按宪章治理条款记录
ADR、提升 schema 版本号，并显式声明受影响的既有实验。

事件日志顶层必须携带 `schema_version` 字段。

## 3. 优先级类别（冻结清单）

数值越小越先处理。

| class | 名称 | 含义 |
|---|---|---|
| 0 | `ORDER_ARRIVAL` | 订单或撤单到达交易所，触发准入校验与撮合 |
| 1 | `TRADE_SETTLE` | 成交结算，账户现金/持仓/费用更新 |
| 2 | `MARKET_DATA_PUBLISH` | 行情发布（成交与盘口变化对外可见） |
| 3 | `AGENT_OBSERVE` | 代理接收行情，其信息集在此刻确定 |
| 4 | `AGENT_DECIDE` | 代理决策，产生新的订单意图 |
| 5 | `SNAPSHOT` | 周期性账户与订单簿快照，纯记录，不改变状态 |

### 3.1 排序理由

**交易所侧状态转移（0—2）先于代理侧（3—4）。** 这保证代理观察到的永远是一个撮合
已完成的一致簿状态，不会看到撮合中间态。若顺序颠倒，代理可能基于半更新的簿做决策，
使 A-002（代理只能使用信息集内数据）在实现层被悄然破坏。

**观察（3）与决策（4）分离为两个类别**，而非合并。理由是 KPI-007 要求任一成交可
追溯至「当时的信息集」——分离后信息集在 `AGENT_OBSERVE` 事件中被独立记录，与决策
逻辑解耦，追溯链无需从决策结果反推输入。

**快照（5）最后。** 快照必须记录该时间戳上所有实质状态转移完成后的状态，否则
快照序列与事件序列会不一致。

## 4. 事件类型与必备字段

所有事件共有：`schema_version`、`event_id`、`timestamp`、`priority_class`、`seq`、
`event_type`、`run_id`。

### 4.1 ORDER_ARRIVAL（class 0）

| 字段 | 说明 |
|---|---|
| `agent_id` | 提交方 |
| `order_id` | 订单标识 |
| `action` | `SUBMIT` \| `CANCEL` |
| `target_order_id` | `CANCEL` 时指向被撤销的订单；`SUBMIT` 时为 null |
| `side` | `BUY` \| `SELL` |
| `order_type` | `LIMIT` \| `MARKET` |
| `price_ticks` | 整数 tick 价；市价单为 null |
| `quantity_units` | 整数最小数量单位（ADR-005 §1） |
| `intent_id` | 产生该订单/撤单的意图标识（因果外键） |
| `decision_event_id` | 该意图所属的 `AGENT_DECIDE` 事件（因果外键） |
| `submitted_at` | 代理提交时刻（与 `timestamp` 之差即通信延迟） |
| `accepted` | 是否通过准入校验 |
| `reject_reason` | 拒绝原因，未拒绝为 null |
| `reserved_cash_delta_units` | 冻结现金变动：下单预冻结为正，撤单/拒绝释放为负（§4.2.1） |

`submitted_at` 与 `timestamp` 并存是速度优势可归因的前提（A-003）。
`intent_id` 与 `decision_event_id` 是 KPI-007 追溯链的中间环节（§5）。

### 4.2 TRADE_SETTLE（class 1）

| 字段 | 说明 |
|---|---|
| `trade_id` | 成交标识 |
| `caused_by_event_id` | 触发本次撮合的 `ORDER_ARRIVAL`（因果外键） |
| `maker_order_id` / `taker_order_id` | 双方订单 |
| `maker_agent_id` / `taker_agent_id` | 双方代理 |
| `price_ticks` / `quantity_units` | 成交价与量（整数，ADR-005 §1） |
| `notional_cash_units` | 成交名义金额，整数且无舍入（ADR-005 §2） |
| `maker_fee_cash_units` / `taker_fee_cash_units` | 分别计费（FR-003），整数，舍入方向见 ADR-005 §3 |
| `mid_before_half_ticks` | 成交前中间价，以 **半 tick** 为单位的整数（`best_bid + best_ask`），任一侧空时为 null |
| `postings` | **账户分录**，长度恒为 2（maker 与 taker 各一条），见 §4.2.1 |

#### 4.2.1 账户分录 `postings`

每条分录记录该成交对**一个代理**账户的完整影响，全部为最小单位整数：

| 字段 | 说明 |
|---|---|
| `agent_id` | 该分录所属代理 |
| `role` | `MAKER` \| `TAKER` |
| `cash_delta_units` | 现金变动（含手续费；返佣为正） |
| `position_delta_units` | 持仓变动（买入为正） |
| `fee_delta_units` | 该方手续费（正为付出，负为返佣） |
| `reserved_cash_delta_units` | 冻结现金的变动（预冻结释放为负） |
| `cash_after_units` / `position_after_units` | 结算后余额，用于逐事件守恒断言 |
| `cost_after_cash_units` | 结算后持仓累计成本（ADR-005 §5） |

**账户变化必须内嵌于引发它的事件，不能靠「时间上位于成交之后的周期快照」推断。**
周期快照可能聚合多笔成交，无法从单笔成交唯一确定其账户影响——那不是因果关联，
SC-008 的「每一跳唯一存在」在快照上无法成立。

同理，非成交引起的账户变化也记录在引发它的事件上：`ORDER_ARRIVAL` 携带
`reserved_cash_delta_units`（下单预冻结、撤单或拒绝时释放），字段语义与上表一致。
由此**每一次账户变动都由某个事件承载，且该事件自带因果外键**，无需新增事件类别，
`priority_class` 冻结清单（§3）不受影响。

### 4.3 MARKET_DATA_PUBLISH（class 2）

盘口摘要：`best_bid`、`best_ask`、各侧 k 档深度、`last`。**未定义值写 `null`**
（ADR-005 §6）——不得写 `NaN`：JSON 标准无 NaN 字面量。分析层读取后再映射为 NaN
（指标字典 §3.1）。

### 4.4 AGENT_OBSERVE（class 3）

| 字段 | 说明 |
|---|---|
| `agent_id` | 观察方 |
| `market_data_event_id` | 所观察的 `MARKET_DATA_PUBLISH` 事件（因果外键） |
| `observed_at` | 所观察行情的产生时刻 |
| `information_set` | 该代理本次可见内容的快照或其摘要哈希 |

`timestamp - observed_at` 即观察延迟。`information_set` 是 KPI-007 追溯链的起点。
完整记录成本高时可只存摘要哈希（E-001），但须保证可由配置与种子重放还原。

`market_data_event_id` 使追溯链一路闭合到行情发布本身：仅有 `observed_at` 时刻时，
只能回答「代理看到了什么」，不能机器验证「看到的是哪一次发布」——同一纳秒可能有
多条发布，digest 模式下更无从比对。

### 4.5 AGENT_DECIDE（class 4）

| 字段 | 说明 |
|---|---|
| `agent_id` | 决策方 |
| `observation_event_id` | 本次决策所依据的 `AGENT_OBSERVE`（因果外键） |
| `rule_id` | 触发的决策规则标识 |
| `intents` | 产生的订单意图列表，可为空 |
| `internal_state` | 决策相关的内部状态（如均值回复代理的当前锚值与半衰期） |

`intents` 的每个元素必须携带 **`intent_id`**（本次运行内唯一的稳定标识），以及
`action`、`side`、`order_type`、`price_ticks`、`quantity_units`。一次决策产生多笔
意图时（做市商双边报价即产生 2 笔），`intent_id` 是与后续 `ORDER_ARRIVAL` 一一对应
的唯一依据——仅靠「同代理、时间相近」无法区分，且这种不可靠无法被检出。

`rule_id` 与 `internal_state` 使「为什么下这一单」可解释，支撑 US-3 与 KPI-007。

### 4.6 SNAPSHOT（class 5）

| 字段 | 说明 |
|---|---|
| `snapshot_type` | `ACCOUNT` \| `BOOK` |
| `payload` | 账户或订单簿完整状态 |

账户快照频率可配置（FR-008），是回放中绘制持仓与 PnL 演化曲线的数据来源
（002 / D-7）。快照是状态观测而非状态转移，**不携带因果外键，也不承担账户追溯**
——账户追溯由 §4.2.1 的分录承担。快照的作用是回放与图表，以及与分录累加值的
交叉核对（两者不一致即为实现缺陷）。

## 5. 因果链与引用完整性（KPI-007）

### 5.1 追溯路径

因果外键（ADR-006 §3）使下列路径完全在日志内可解析，无需重放：

```text
trade_id
  → caused_by_event_id        （ORDER_ARRIVAL：哪笔订单触发了撮合）
  → maker_order_id / taker_order_id
  → intent_id                 （哪个意图产生了该订单）
  → decision_event_id         （哪次决策产生了该意图）
  → observation_event_id      （该决策基于哪次观察）
  → information_set           （当时的信息集）
  → market_data_event_id      （该观察来自哪一次行情发布）
```

账户侧由同一 `TRADE_SETTLE` 内的 `postings` 承担（§4.2.1）：两条分录直接给出双方的
现金、持仓、费用与冻结变动及结算后余额。加上 `ORDER_ARRIVAL` 的
`reserved_cash_delta_units`，US-3 要求的「成交 → 观察 → 决策 → 订单 → 账户」在日志内
闭合，且每一环都是事件自带字段，不依赖时间上的邻近关系。

### 5.2 引用完整性断言（SC-008）

对每次运行的事件日志：

- **遍历全部** `TRADE_SETTLE`（非抽样），沿 §5.1 逐跳解析；
- 每一跳的目标事件必须在日志中**唯一存在**，且其全序键**严格小于**引用方；
- 断链、悬空引用或多重匹配即判定该运行不合格；
- **账户侧**：每笔成交的 `postings` 恰为 2 条且 `agent_id` 与 `maker/taker_agent_id`
  一致；分录的 `*_after_units` 等于该代理上一条分录的 `*_after_units` 加本次
  `*_delta_units`（首次以初始值为基），且与同代理最近一次 `ACCOUNT` 快照一致。

该断言不依赖重放，因而不随代码版本失效——这是 KPI-007 从「展示层可读」升级为
「可机器验证」的关键。

## 6. 运行元数据

每次运行的日志头部必须记录（PR-012）：`run_id`、代码版本、配置哈希、
`master_seed`、开始时间、完成状态、`schema_version`，以及数值单位定义
`tick_size`、`min_quantity`、`cash_unit`（ADR-005 §7）。

## 7. 事件摘要哈希（KPI-002）

对事件序列按全序逐个计算滚动哈希，输入为各事件的**语义字段**（排除
`event_id` 等实现细节标识）。参与哈希的字段集合须显式声明并随 schema 版本管理。

哈希在 §9 的规范序列化之上计算，因而与语言、平台的浮点实现无关（ADR-005 §7）。

## 8. 参数取值

### E-001：information_set 的记录方式

**默认记录摘要哈希**，并提供 `information_set_mode: full` 配置开关用于追溯特定运行。

理由：每个 `AGENT_OBSERVE` 事件都完整存储可见盘口，将使日志体积被观察事件主导
（代理数 × 观察频率），而观察事件是所有事件类型中数量最多的一类。

**digest 模式仅用于性能基准。** 任何用于研究结论的运行必须使用
`information_set_mode: full`，或产出可独立还原信息集的版本化证据包（ADR-006 §5）。

理由：digest 模式下完整追溯依赖「用同一份代码重跑」，而代码版本会随时间变化——
KPI-007 的证据能力因此逐年衰减。§5 的引用完整性断言在两种模式下都成立，但信息集
内容本身只有 full 模式才在日志内自包含。性能门槛由 BENCH-001 单独承载，研究运行的
日志体积是可接受的代价（须在 M2 首次运行前实测确认）。

### E-002：参与摘要哈希的字段

**纳入**：`timestamp`、`priority_class`、`seq`、`event_type`，以及各事件类型的
外部可观察语义字段——`agent_id`、`order_id`、`side`、`order_type`、`price_ticks`、
`quantity_units`、`accepted`、`reject_reason`、成交双方标识、成交价量、
`notional_cash_units`、`maker_fee_cash_units`、`taker_fee_cash_units`，以及撤单的
`target_order_id`——**撤销哪一笔订单是外部可观察的市场行为**，与 `order_id` 同属
一类，不可排除。

**排除**：`event_id`、`run_id`、墙钟时间、`information_set`、`internal_state`，
以及指向事件的因果外键——`observation_event_id`、`decision_event_id`、`intent_id`、
`caused_by_event_id`、`market_data_event_id`（ADR-006 §6）。它们与 `event_id` 同属实现标识，其生成方式属
实现细节；引用完整性由 §5.2 的独立断言保证，不需要哈希参与。

排除 `internal_state` 与 `information_set` 是关键选择：哈希应捕捉**市场结果的
确定性**，而非代理实现的内部细节。若纳入，一次不改变任何行为的内部状态表示重构
就会使哈希变化，KPI-002 将频繁误报，最终导致该断言被忽视。

### E-003：深度档位

`k = ±10 tick`，与指标字典 D-003 一致。

## 9. 序列化合同

规范序列化规则随 `schema_version` 管理，变更须提升版本号（ADR-005 §7）：

- 数值字段一律为 **JSON 整数字面量**，不得出现浮点字面量、指数记法或引号包裹的
  数字。所有金额与数量以最小单位整数表达（ADR-005 §1），单位定义写在运行元数据
  头部（§6），事件体内不重复携带；
- **缺失值一律为 `null`**，不得使用 `NaN`、`Infinity`、空字符串或省略字段；
- 对象键按 UTF-8 码位升序排列；
- Parquet 输出的缺失值写 null，与 JSONL 一致。

统计层的 NaN 语义只在分析代码读取日志之后成立，不进入日志本身——这正是 FR-012
（领域层不得产出未定义状态）与指标字典 §3.1（未定义报价的统计表示）之间的分层。
