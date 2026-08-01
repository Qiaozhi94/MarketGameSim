# 事件 Schema 与优先级类别

**适用范围**：跨规格实现合同（当前交付规格 001）  
**状态**：Stable（跨规格实现合同；变更须记 ADR 并提升 `schema_version`）  
**创建日期**：2026-07-29  
**支撑需求**：001 / FR-004、FR-008、FR-015、KR-001—KR-006；PRD / KPI-002、KPI-006  
**关联**：
[ADR-001](../adr/001-numeric-and-serialization-contract.md)、
[ADR-002](../adr/002-same-timestamp-event-scheduling.md)、
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

违反时内核立即抛出异常并终止运行，**不得静默重排**（ADR-002 §1）。

推论：**同一 `timestamp` 内 `priority_class` 不得减小**。允许保持不变——同 class 的
后继事件靠 `seq` 严格递增即满足不变量（例如 `TRADE_SETTLE` 产生 `MARGIN_CALL`，
两者同为 class 1，见 §4.2.2）。要回到**更小**的 class，`timestamp` 必须先前进——因此
`AGENT_DECIDE`（class 4）产生的 `ORDER_ARRIVAL`（class 0）永远落在更晚的时间戳上。

为此**禁止零通信延迟**：所有代理的 `latency_ns ≥ 1`（FR-013）。零值配置在校验阶段
拒绝，不静默替换为 1。纳秒粒度下 1 ns 已足以表达「几乎无延迟」，且零延迟无现实
对应。

### 1.2 回退 class 的跳转清单（穷举）

**每一个回退 class 的跳转都必须跨越至少 1 ns，且必须列在下表中。** 表外出现回退即为
实现缺陷或 schema 遗漏，不得临时加 1 ns 绕过。

| 跳转 | class | 跨越时间由谁承担 | 下限 |
|---|---|---|---|
| `AGENT_DECIDE` → `ORDER_ARRIVAL` | 4 → 0 | 代理通信延迟 `latency_ns` | ≥ 1 |
| `MARGIN_CALL` → `ORDER_ARRIVAL`（强平单） | 1 → 0 | 风控下单延迟 `liquidation_latency_ns` | ≥ 1 |

第二行是 2026-08-01 检视补入的：强平单同样是 `ORDER_ARRIVAL`(class 0)，由
`MARGIN_CALL`(class 1) 产生，因此**也是回退**。此前文档称「`AGENT_DECIDE` →
`ORDER_ARRIVAL` 是唯一回退」，与 §4.2.2 的强平流程自相矛盾。

`liquidation_latency_ns` 不是权宜之计——交易所风控从判定到下单本就有延迟，且该延迟
是一个**有研究意义的参数**：风控反应越慢，连锁强平的价格滑落越深。它与 `grace_ns`
语义不同：`grace_ns` 是给账户补保证金的宽限窗口，`liquidation_latency_ns` 是宽限
结束后风控自身的下单耗时。

**非回退的跳转不需要任何时间间隔**，键本就严格递增：`TRADE_SETTLE`(1) →
`MARGIN_CALL`(1)（同 class，靠 `seq`）、`TRADE_SETTLE`(1) →
`MARKET_DATA_PUBLISH`(2)、`MARKET_DATA_PUBLISH`(2) → `AGENT_OBSERVE`(3)、
`AGENT_OBSERVE`(3) → `AGENT_DECIDE`(4) **均允许同时间戳，间隔可为 0**。观察与决策
分为两个 class 是为了让信息集独立记录（§3.1），不意味着两者必须在时间上分开。

### 1.3 第一版不含的生命周期事件

加密式制度为 24/7 连续交易，**没有开盘、收盘、隔夜与熔断**，因此第一版不需要
`SESSION_OPEN` / `SESSION_CLOSE` / `HALT` / `RESUME` / `SETTLEMENT_DUE` 事件。

股票式制度引入时，这些事件必须**先补入本文的 class 清单并逐一验证键单调性**，尤其是
「收盘时点触发保证金判定」这一跳（`SNAPSHOT`(5) → `MARGIN_CALL`(1) 为回退，须列入
§1.2 表并指定跨越时间的承担者）。在此之前不得实现任何依赖时段状态的逻辑。

若无此规则，`AGENT_DECIDE` 在同一时间戳插入 class 0 事件会破坏事件队列的单调性，
「数值越小越先处理」在实现层无法成立，KPI-002 的哈希输入顺序随之不确定。

## 2. 冻结约束

**`priority_class` 的取值与语义一经冻结不得静默变更。**

变更将使历史实验的事件摘要哈希（KPI-002）不可比。如需变更，按宪章治理条款记录
ADR、提升 schema 版本号，并显式声明受影响的既有实验。

事件日志顶层必须携带 `schema_version` 字段。

**当前 `schema_version = 1`。** 2026-07-31 的方向重置新增了 `MARGIN_CALL`（§4.2.2）
与杠杆相关字段，但**未提升版本号**——此前没有任何实验运行过，不存在可比性问题。
首次正式运行之后，任何字段或 class 变更都必须提升版本号。

## 3. 优先级类别（冻结清单）

数值越小越先处理。

| class | 名称 | 含义 |
|---|---|---|
| 0 | `ORDER_ARRIVAL` | 订单或撤单到达交易所，触发准入校验与撮合 |
| 1 | `TRADE_SETTLE` | 成交结算，账户钱包/仓位/开仓成本/费用更新 |
| 1 | `MARGIN_CALL` | 保证金判定与强平触发；同 class 内排在结算之后（§4.2.2） |
| 2 | `MARKET_DATA_PUBLISH` | 行情发布（成交与盘口变化对外可见） |
| 3 | `AGENT_OBSERVE` | 代理接收行情，其信息集在此刻确定 |
| 4 | `AGENT_DECIDE` | 代理决策，产生新的订单意图 |
| 5 | `SNAPSHOT` | 周期性账户与订单簿快照，纯记录，不改变状态 |

### 3.1 排序理由

**交易所侧状态转移（0—2）先于代理侧（3—4）。** 这保证代理观察到的永远是一个撮合
已完成的一致簿状态，不会看到撮合中间态。若顺序颠倒，代理可能基于半更新的簿做决策，
使 A-002（代理只能使用信息集内数据）在实现层被悄然破坏。

**观察（3）与决策（4）分离为两个类别**，而非合并。理由是 KPI-006 要求任一成交可
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
| `quantity_units` | 整数最小数量单位（ADR-001 §1） |
| `intent_id` | 产生该订单/撤单的意图标识（因果外键） |
| `decision_event_id` | 该意图所属的 `AGENT_DECIDE` 事件（因果外键） |
| `submitted_at` | 代理提交时刻（与 `timestamp` 之差即通信延迟） |
| `accepted` | 是否通过准入校验 |
| `reject_reason` | 拒绝原因，未拒绝为 null |
| `reserved_delta_units` | 保证金占用变动：下单预冻结为正，撤单/拒绝释放为负（§4.2.1） |
| `origin` | `AGENT` \| `LIQUIDATION`——强平单由风控产生，不来自代理决策 |
| `trigger_ratio_bp` | `origin=LIQUIDATION` 时的触发保证金率（整数万分数），否则 null |

`submitted_at` 与 `timestamp` 并存是速度优势可归因的前提（A-003）。
`intent_id` 与 `decision_event_id` 是 KPI-006 追溯链的中间环节（§5）。

**强平单的因果外键指向风控判定而非代理决策**：`origin = LIQUIDATION` 时，
`decision_event_id` 指向触发它的 `MARGIN_CALL` 事件（§4.2.2），`intent_id` 为 null。
这使「哪些成交由强平造成」可被机器识别，是测量连锁规模与深度的前提。

### 4.2 TRADE_SETTLE（class 1）

| 字段 | 说明 |
|---|---|
| `trade_id` | 成交标识 |
| `caused_by_event_id` | 触发本次撮合的 `ORDER_ARRIVAL`（因果外键） |
| `maker_order_id` / `taker_order_id` | 双方订单 |
| `maker_agent_id` / `taker_agent_id` | 双方代理 |
| `price_ticks` / `quantity_units` | 成交价与量（整数，ADR-001 §1） |
| `notional_cash_units` | 成交名义金额，整数且无舍入（ADR-001 §2） |
| `maker_fee_cash_units` / `taker_fee_cash_units` | 分别计费（FR-003），整数，舍入方向见 ADR-001 §3 |
| `valuation_mark_before_half_ticks` | 成交**前**的估值标记价（`mid`，以半 tick 为单位的整数 `best_bid + best_ask`）；任一侧空时退化为 `last × 2` |
| `valuation_mark_after_half_ticks` | 成交**后**的估值标记价，同上口径 |
| `risk_mark_ticks` | 成交后的风险标记价 = 本笔成交价（`last`），用于保证金判定 |
| `postings` | **账户分录**，长度恒为 2（maker 与 taker 各一条），见 §4.2.1 |

**两个 mark 都必须记录**：`risk_mark` 决定强平判定，`valuation_mark` 决定权益与
会计桥接（指标字典 §3.1、§5.2）。缺任一个，PnL 桥接都无法仅凭日志重放。

#### 4.2.1 账户分录 `postings`

每条分录记录该成交对**一个代理**账户的完整影响，全部为最小单位整数：

| 字段 | 说明 |
|---|---|
| `agent_id` | 该分录所属代理 |
| `role` | `MAKER` \| `TAKER` |
| `wallet_delta_units` | 钱包变动（已实现盈亏 − 手续费；**开仓不扣名义金额**） |
| `position_delta_units` | 仓位变动（买入为正，卖出为负） |
| `entry_notional_delta_units` | 开仓成本变动（账户合同 §2.1） |
| `realized_pnl_delta_units` | 本次成交实现的盈亏（仅反向平仓时非 0） |
| `fee_delta_units` | 该方手续费（正为付出，负为返佣） |
| `reserved_delta_units` | 保证金占用变动（挂单占用释放为负） |
| `wallet_after_units` / `position_after_units` | 结算后余额，用于逐事件守恒断言 |
| `entry_notional_after_units` | 结算后开仓成本 |
| `equity_after_units` | 结算后权益 = 钱包 + 未实现盈亏（可为负，见穿仓） |
| `margin_ratio_after_bp` | 结算后保证金率（按 `risk_mark` 计算），整数万分数；**无仓位时为 null**（账户合同 §3.2） |
| `risk_pnl_delta_units` | 恒为 0——`TRADE_SETTLE` 不承载核销，核销只发生在 `MARGIN_CALL`（§4.2.3） |

**账户变化必须内嵌于引发它的事件，不能靠「时间上位于成交之后的周期快照」推断。**
周期快照可能聚合多笔成交，无法从单笔成交唯一确定其账户影响——那不是因果关联，
SC-006 的「每一跳唯一存在」在快照上无法成立。

同理，非成交引起的账户变化也记录在引发它的事件上：`ORDER_ARRIVAL` 携带
`reserved_delta_units`（下单预冻结、撤单或拒绝时释放），字段语义与上表一致。
由此**每一次账户变动都由某个事件承载，且该事件自带因果外键**，无需新增事件类别，
`priority_class` 冻结清单（§3）不受影响。

#### 4.2.2 MARGIN_CALL（class 1）

保证金判定结果。**与 `TRADE_SETTLE` 同属 class 1**——判定必须在结算之后、行情发布
之前完成，否则代理会看到一个尚未反映强平后果的簿状态（§3.1 同一理由）。

| 字段 | 说明 |
|---|---|
| `agent_id` | 被判定的账户 |
| `caused_by_event_id` | 导致该判定的 `TRADE_SETTLE`（只有成交能改变风险 mark，代理策略 §3.3） |
| `margin_ratio_bp` | 判定时的保证金率（整数万分数，账户合同 §3.2） |
| `maintenance_bp` | 当时生效的维持保证金率 |
| `verdict` | `OK` \| `PENDING_LIQUIDATION` \| `LIQUIDATING` \| `BREACHED`（穿仓） |
| `required_quantity_units` | 恢复至 `target_bp` 所需的最小平仓数量（账户合同 §4.2）；`OK` 时为 0 |
| `chain_depth` | 该判定所处的连锁层数，0 表示非连锁触发（指标字典 §4.1） |
| `postings` | **仅 `verdict = BREACHED` 时非空**，长度为 2：代理核销分录 + 交易所风险账户分录（见 §4.2.3） |

#### 4.2.3 穿仓核销分录

`verdict = BREACHED` 的 `MARGIN_CALL` 是**穿仓核销的唯一事件载体**。它携带两条分录，
使核销可仅凭日志重放，不依赖对「最后一笔强平成交」的推断：

| 分录 | `agent_id` | 字段 |
|---|---|---|
| 代理侧 | 该穿仓账户 | `wallet_delta_units = −wallet_before`（把负钱包补到 0）；`wallet_after_units = 0`；`position_after_units = 0`；`entry_notional_after_units = 0`；`risk_pnl_delta_units = 0` |
| 交易所侧 | `null`（交易所账户） | `risk_pnl_delta_units = wallet_before`（**负值**）；其余 `*_delta` 为 0 |

两条分录的 `wallet_delta` 与 `risk_pnl_delta` 大小相等、符号相反，C2 守恒
（账户合同 §5）。

**验收要求**：仅凭事件日志，从穿仓前状态重放至
`wallet = 0`、`position = 0`、`entry_notional = 0`、账户状态 `LIQUIDATED`，
且全局恒等式在每一步后精确成立。

**为什么不新增 `DEFAULT_WRITE_OFF` 事件类别**：核销与判定是同一逻辑时刻的同一件事，
拆成两个事件会引入「判定与核销之间的中间态」，而该中间态下 `wallet < 0` 且账户既非
活跃也非已核销——那是需要额外定义的第三种状态。复用 `MARGIN_CALL` 使
`priority_class` 冻结清单不变（§3）。

**判定事件独立记录、不与成交合并**，理由有二：判定可能得出 `OK`（不产生任何订单），
而「检查过且安全」本身是研究连锁传导所需的证据；`chain_depth` 只有在判定层面才能
逐层累计。

**扫描范围与顺序**：**一次 `ORDER_ARRIVAL` 的全部 `TRADE_SETTLE` 结算完毕后**
（跨档成交可能产生多笔，撮合合同 §2.2），执行**两阶段检查**（账户合同 §4.1）——
**不是每笔成交后各查一次**。跨档成交的中间态不应触发强平（撮合合同 §2.3）。

顺序固定：

1. **阶段 1（穿仓捕获）**：对本次 `TRADE_SETTLE.postings` 涉及的账户，若
   `position == 0 且 wallet < 0` → `verdict = BREACHED`，携带核销分录（§4.2.3）；
2. **阶段 2（保证金扫描）**：对**所有非零仓位账户**（不只是成交双方）执行
   **O(N) 全账户扫描**（性能成为瓶颈后再引入按强平价排序的风险索引）。

**只做阶段 2 会漏掉仓位归零的穿仓账户**——它们因 `position == 0` 被排除在扫描外，
核销分录永远不会产生。两阶段的账户集合天然不相交，无需去重。

同一次成交触发多个 `MARGIN_CALL` 时，按 **`agent_id` 升序**产生事件——这是确定性
要求，不是效率考虑：顺序影响 `seq` 分配，进而影响 KPI-002 的哈希。

`chain_depth` 传播规则：由成交直接触发的判定为该成交的 `chain_depth`；由**强平单
成交**触发的判定为 `触发它的强平判定的 chain_depth + 1`。普通代理成交触发的判定
恒为 0。

### 4.3 MARKET_DATA_PUBLISH（class 2）

盘口摘要：`best_bid`、`best_ask`、各侧 k 档深度、`last`。**未定义值写 `null`**
（ADR-001 §6）——不得写 `NaN`：JSON 标准无 NaN 字面量。分析层读取后再映射为 NaN
（指标字典 §3.1）。

### 4.4 AGENT_OBSERVE（class 3）

| 字段 | 说明 |
|---|---|
| `agent_id` | 观察方 |
| `market_data_event_id` | 所观察的 `MARKET_DATA_PUBLISH` 事件（因果外键） |
| `observed_at` | 所观察行情的产生时刻 |
| `information_set` | 该代理本次可见内容的快照或其摘要哈希 |

`timestamp - observed_at` 即观察延迟。`information_set` 是 KPI-006 追溯链的起点。
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

`rule_id` 与 `internal_state` 使「为什么下这一单」可解释，支撑 US-3 与 KPI-006。

### 4.6 SNAPSHOT（class 5）

| 字段 | 说明 |
|---|---|
| `snapshot_type` | `ACCOUNT` \| `BOOK` |
| `payload` | 账户或订单簿完整状态 |

账户快照频率可配置（FR-015），是回放中绘制持仓与 PnL 演化曲线的数据来源
（001 / D-7）。快照是状态观测而非状态转移，**不携带因果外键，也不承担账户追溯**
——账户追溯由 §4.2.1 的分录承担。快照的作用是回放与图表，以及与分录累加值的
交叉核对（两者不一致即为实现缺陷）。

## 5. 因果链与引用完整性（KPI-006）

### 5.1 追溯路径

因果外键（ADR-002 §3）使下列路径完全在日志内可解析，无需重放：

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
`reserved_delta_units`，US-3 要求的「成交 → 观察 → 决策 → 订单 → 账户」在日志内
闭合，且每一环都是事件自带字段，不依赖时间上的邻近关系。

### 5.2 引用完整性断言（SC-006）

对每次运行的事件日志：

- **遍历全部** `TRADE_SETTLE`（非抽样），沿 §5.1 逐跳解析；
- 每一跳的目标事件必须在日志中**唯一存在**，且其全序键**严格小于**引用方；
- 断链、悬空引用或多重匹配即判定该运行不合格；
- **账户侧**：每笔成交的 `postings` 恰为 2 条且 `agent_id` 与 `maker/taker_agent_id`
  一致；分录的 `*_after_units` 等于该代理上一条分录的 `*_after_units` 加本次
  `*_delta_units`（首次以初始值为基），且与同代理最近一次 `ACCOUNT` 快照一致。

该断言不依赖重放，因而不随代码版本失效——这是 KPI-006 从「展示层可读」升级为
「可机器验证」的关键。

## 6. 运行元数据

每次运行的日志头部必须记录（PR-012）：`run_id`、代码版本、配置哈希、
`master_seed`、开始时间、完成状态、`schema_version`，以及数值单位定义
`tick_size`、`min_quantity`、`cash_unit`（ADR-001 §7）。

## 7. 事件摘要哈希（KPI-002）

对事件序列按全序逐个计算滚动哈希，输入为各事件的**语义字段**（排除
`event_id` 等实现细节标识）。参与哈希的字段集合须显式声明并随 schema 版本管理。

哈希在 §9 的规范序列化之上计算，因而与语言、平台的浮点实现无关（ADR-001 §7）。

## 8. 参数取值

### E-001：information_set 的记录方式

**默认记录摘要哈希**，并提供 `information_set_mode: full` 配置开关用于追溯特定运行。

理由：每个 `AGENT_OBSERVE` 事件都完整存储可见盘口，将使日志体积被观察事件主导
（代理数 × 观察频率），而观察事件是所有事件类型中数量最多的一类。

**digest 模式仅用于性能基准。** 任何用于研究结论的运行必须使用
`information_set_mode: full`，或产出可独立还原信息集的版本化证据包（ADR-002 §5）。

理由：digest 模式下完整追溯依赖「用同一份代码重跑」，而代码版本会随时间变化——
KPI-006 的证据能力因此逐年衰减。§5 的引用完整性断言在两种模式下都成立，但信息集
内容本身只有 full 模式才在日志内自包含。性能门槛由性能基准配置单独承载，研究运行的
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
`caused_by_event_id`、`market_data_event_id`（ADR-002 §6）。它们与 `event_id` 同属实现标识，其生成方式属
实现细节；引用完整性由 §5.2 的独立断言保证，不需要哈希参与。

排除 `internal_state` 与 `information_set` 是关键选择：哈希应捕捉**市场结果的
确定性**，而非代理实现的内部细节。若纳入，一次不改变任何行为的内部状态表示重构
就会使哈希变化，KPI-002 将频繁误报，最终导致该断言被忽视。

### E-003：深度档位

`k = ±10 tick`，与指标字典 MD-003 一致。

## 9. 序列化合同

规范序列化规则随 `schema_version` 管理，变更须提升版本号（ADR-001 §7）：

- 数值字段一律为 **JSON 整数字面量**，不得出现浮点字面量、指数记法或引号包裹的
  数字。所有金额与数量以最小单位整数表达（ADR-001 §1），单位定义写在运行元数据
  头部（§6），事件体内不重复携带；
- **缺失值一律为 `null`**，不得使用 `NaN`、`Infinity`、空字符串或省略字段；
- 对象键按 UTF-8 码位升序排列；
- Parquet 输出的缺失值写 null，与 JSONL 一致。

统计层的 NaN 语义只在分析代码读取日志之后成立，不进入日志本身——这正是 FR-018
（领域层不得产出未定义状态）与指标字典 §3.1（未定义报价的统计表示）之间的分层。
