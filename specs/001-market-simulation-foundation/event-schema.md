# 事件 Schema 与优先级类别

**规格**：001-market-simulation-foundation  
**状态**：Draft（清单冻结后转 Frozen）  
**创建日期**：2026-07-29  
**对应任务**：T000d、T004　**支撑需求**：FR-008、KR-001—KR-003、KPI-002、KPI-007  
**关联**：[ADR-001](../../docs/adr/001-discrete-event-time-kernel.md)、[指标字典](../../docs/product/metrics-dictionary.md)

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
| `side` | `BUY` \| `SELL` |
| `order_type` | `LIMIT` \| `MARKET` |
| `price_ticks` | 整数 tick 价；市价单为 null |
| `quantity` | 数量 |
| `submitted_at` | 代理提交时刻（与 `timestamp` 之差即通信延迟） |
| `accepted` | 是否通过准入校验 |
| `reject_reason` | 拒绝原因，未拒绝为 null |

`submitted_at` 与 `timestamp` 并存是速度优势可归因的前提（A-003）。

### 4.2 TRADE_SETTLE（class 1）

| 字段 | 说明 |
|---|---|
| `trade_id` | 成交标识 |
| `maker_order_id` / `taker_order_id` | 双方订单 |
| `maker_agent_id` / `taker_agent_id` | 双方代理 |
| `price_ticks` / `quantity` | 成交价与量 |
| `maker_fee` / `taker_fee` | 分别计费（FR-003） |
| `mid_before` | 成交前中间价，用于有效点差与滑点 |

### 4.3 MARKET_DATA_PUBLISH（class 2）

盘口摘要：`best_bid`、`best_ask`、各侧 k 档深度、`last`。未定义值记 NaN
（指标字典 §3.1）。

### 4.4 AGENT_OBSERVE（class 3）

| 字段 | 说明 |
|---|---|
| `agent_id` | 观察方 |
| `observed_at` | 所观察行情的产生时刻 |
| `information_set` | 该代理本次可见内容的快照或其摘要哈希 |

`timestamp - observed_at` 即观察延迟。`information_set` 是 KPI-007 追溯链的起点。
完整记录成本高时可只存摘要哈希，但须保证可由配置与种子重放还原。

### 4.5 AGENT_DECIDE（class 4）

| 字段 | 说明 |
|---|---|
| `agent_id` | 决策方 |
| `rule_id` | 触发的决策规则标识 |
| `intents` | 产生的订单意图列表，可为空 |
| `internal_state` | 决策相关的内部状态（如均值回复代理的当前锚值与半衰期） |

`rule_id` 与 `internal_state` 使「为什么下这一单」可解释，支撑 US-3 与 KPI-007。

### 4.6 SNAPSHOT（class 5）

| 字段 | 说明 |
|---|---|
| `snapshot_type` | `ACCOUNT` \| `BOOK` |
| `payload` | 账户或订单簿完整状态 |

账户快照频率可配置（FR-008），是回放中绘制持仓与 PnL 演化曲线的数据来源
（ADR-004）。

## 5. 运行元数据

每次运行的日志头部必须记录（PR-012）：`run_id`、代码版本、配置哈希、
`master_seed`、开始时间、完成状态、`schema_version`。

## 6. 事件摘要哈希（KPI-002）

对事件序列按全序逐个计算滚动哈希，输入为各事件的**语义字段**（排除
`event_id` 等实现细节标识）。参与哈希的字段集合须显式声明并随 schema 版本管理。

## 7. 待定项

- **E-001**：`information_set` 存完整内容还是摘要哈希，取决于日志体积实测；
- **E-002**：参与摘要哈希的字段白名单；
- **E-003**：`MARKET_DATA_PUBLISH` 的深度档位 k（与指标字典 D-003 一致）。
