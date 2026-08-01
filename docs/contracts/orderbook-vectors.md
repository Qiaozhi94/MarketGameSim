# 订单簿验收向量

**适用范围**：跨规格实现合同（当前交付规格 v0.1）  
**状态**：Stable（变更须同步[撮合合同](matching.md)）  
**创建日期**：2026-08-01　**更新日期**：2026-08-01  
**支撑需求**：v0.1 / FR-001—FR-003、SC-001；PRD / PR-001  
**关联**：[撮合](matching.md)、[事件 Schema](event-schema.md)、
[账户验收向量](acceptance-vectors.md)

## 0. 用途

[撮合合同](matching.md) §8 的验收要点此前只有**场景描述**，没有期望值——
实现者会写出自己认为对的测试，然后测试通过。本文补齐每条的**完整期望状态**：
事件序列、每条记录的 `record_index`、成交价与量、`fill_index` / `fill_count`、
逐笔 `valuation_mark` 与 `risk_mark`、以及事务后的簿状态。

与[账户验收向量](acceptance-vectors.md)互补：那份管账本，这份管簿与撮合。
**两份都是实现的裁判**，实现与本表不符时以本表为准，除非能证明本表违反撮合合同。

## 1. 公共约定

```text
tick_size = 0.01           min_quantity = 0.001
initial_price_ticks = 10000（= 100.00）
log_key = (timestamp, transaction_seq, record_index)
  ├ 队列事件（ORDER_ARRIVAL）恒为 record_index = 0
  └ 事务记录从 1 递增
```

**整数是唯一裁判**。表中括号内的十进制值仅供人阅读，实现断言一律比较整数字段：
`price_ticks`、`quantity_units`、`*_half_ticks`。

**估值标记 `vm` 以半 tick 为单位**（事件 Schema §4.2）：

```text
两侧皆有报价：vm = best_bid_ticks + best_ask_ticks
任一侧为空　：vm = last_ticks × 2
首笔成交之前：vm = initial_price_ticks × 2 = 20000
```

`vm_after` 测量的是**该笔成交刚完成时**的盘口，**taker 剩余尚未挂入簿**。因此
OB-5/6/7 中成交后两侧皆空，`vm_after` 走 `last × 2` 分支——这不是遗漏。

事务内记录顺序遵循事件 Schema §1.4 的冻结合同：
`r0 ORDER_ARRIVAL` → 撮合记录（`TRADE_SETTLE` / `ORDER_CANCELLED`）→
`MARGIN_CALL × m` → `MARKET_DATA_PUBLISH`（盘口有变化时，恒为最后一条）。

下表中「簿」为事务结束后的状态，价格由高到低（BID）/由低到高（ASK）聚合。
所有向量均在**同一时间戳**内，故只列 `transaction_seq` 与 `record_index`。

**本文不含账户与手续费**——那些由账户验收向量覆盖。这里只验簿与成交生成。

**验收里程碑**：OB-1—OB-7、OB-9a 属 0.1.1；**OB-8 与 OB-9b 依赖杠杆账户与保证金
判定，属 0.1.2**，不列入 0.1.1 的退出条件 E3。

## 2. 验收向量

### OB-1：价格优先

| tx | r | 记录 | 整数字段（括号为展示值） |
|---|---|---|---|
| 1 | 0 | `ORDER_ARRIVAL` | A BUY `price_ticks=10000`(100.00) `quantity_units=5000`(5.000) LIMIT → 订单 o1 |
| 1 | 1 | `MARKET_DATA_PUBLISH` | `best_bid=10000` `best_ask=null` |
| 2 | 0 | `ORDER_ARRIVAL` | B BUY `price_ticks=10100` `quantity_units=5000` LIMIT → 订单 o2 |
| 2 | 1 | `MARKET_DATA_PUBLISH` | `best_bid=10100` `best_ask=null` |
| 3 | 0 | `ORDER_ARRIVAL` | C SELL `price_ticks=10000` `quantity_units=3000` LIMIT |
| 3 | 1 | `TRADE_SETTLE` | `price_ticks=10100` `quantity_units=3000` maker=**o2** `fill_index=0` `fill_count=1` `vm_before=20000` `vm_after=20200` `risk_mark=10100` |
| 3 | 2 | `MARKET_DATA_PUBLISH` | `best_bid=10100` `best_ask=null` |

事务后簿：`BID [(10100, 2000), (10000, 5000)]`　`ASK []`

**三条断言**：

1. C 的卖单虽限价 10000，却成交于 **10100**——买方队列按价格降序，出价更高的 o2 排
   在 o1 前，且成交价取 maker 价（撮合合同 §2.1）；
2. 前两个事务**只挂入不成交，也不产生任何撤单/挂入记录**，但**都写
   `MARKET_DATA_PUBLISH`**——`best_bid` 从 null 变为 10000、再变为 10100；
3. `vm_before=20000` 是首笔成交前的 `initial_price × 2`，`vm_after=20200` 是
   `last × 2`（ASK 侧为空）。

### OB-2：时间优先（同价按 `transaction_seq`）

| tx | r | 记录 | 整数字段 |
|---|---|---|---|
| 1 | 0 | `ORDER_ARRIVAL` | A BUY `price_ticks=10000` `quantity_units=5000` → o1，`transaction_seq=1` |
| 1 | 1 | `MARKET_DATA_PUBLISH` | `best_bid=10000` `best_ask=null` |
| 2 | 0 | `ORDER_ARRIVAL` | B BUY `price_ticks=10000` `quantity_units=5000` → o2，`transaction_seq=2` |
| 2 | 1 | `MARKET_DATA_PUBLISH` | `best_bid=10000` `best_ask=null`（**深度变化**） |
| 3 | 0 | `ORDER_ARRIVAL` | C SELL `price_ticks=10000` `quantity_units=3000` |
| 3 | 1 | `TRADE_SETTLE` | `price_ticks=10000` `quantity_units=3000` maker=**o1** `fill_index=0` `fill_count=1` `vm_before=20000` `vm_after=20000` `risk_mark=10000` |
| 3 | 2 | `MARKET_DATA_PUBLISH` | `best_bid=10000` `best_ask=null` |

事务后簿：`BID [(10000, 7000)]`——A 剩 2000、B 仍 5000。

**两条断言**：

1. 同价位下先到（`transaction_seq` 小）者先成交，成交对手是 **o1**；
2. 事务 2 的 `best_bid` 未变，但 **k 档深度变了**，因此仍须发布行情——判定依据是
   事件 Schema §4.3 的**全部字段**，不是仅看最优价（事件 Schema §1.4 推论 3）。

### OB-3：price improvement

| tx | r | 记录 | 整数字段 |
|---|---|---|---|
| 1 | 0 | `ORDER_ARRIVAL` | A SELL `price_ticks=10000` `quantity_units=5000` LIMIT |
| 1 | 1 | `MARKET_DATA_PUBLISH` | `best_bid=null` `best_ask=10000` |
| 2 | 0 | `ORDER_ARRIVAL` | B BUY `price_ticks=10100`(**限价 101**) `quantity_units=3000` LIMIT |
| 2 | 1 | `TRADE_SETTLE` | `price_ticks=10000` `quantity_units=3000` `fill_index=0` `fill_count=1` `vm_before=20000` `vm_after=20000` `risk_mark=10000` |
| 2 | 2 | `MARKET_DATA_PUBLISH` | `best_bid=null` `best_ask=10000`（深度 5000 → 2000） |

事务后簿：`BID []`　`ASK [(10000, 2000)]`

**断言**：成交价取 maker 挂单价 **10000**，**不是** taker 限价 10100
（撮合合同 §2.1）。B 全额成交，无剩余挂入。

### OB-4：跨三档（`valuation_mark` 逐笔推进）

前置：M 挂卖 100×2、101×2、102×2；N 挂买 99×10（使 `mid` 有定义）。
T 买 **限价 102 × 5**：

| r | 记录 | 整数字段（括号为展示值） |
|---|---|---|
| 0 | `ORDER_ARRIVAL` | `price_ticks=10200`(102.00) `quantity_units=5000`(5.000) LIMIT |
| 1 | `TRADE_SETTLE` | `price_ticks=10000` `quantity_units=2000` maker=a1 `fill_index=0` `fill_count=3` `vm_before=19900`(99.50) `vm_after=20000`(100.00) `risk_mark=10000` |
| 2 | `TRADE_SETTLE` | `price_ticks=10100` `quantity_units=2000` maker=a2 `fill_index=1` `fill_count=3` `vm_before=20000` `vm_after=20100`(100.50) `risk_mark=10100` |
| 3 | `TRADE_SETTLE` | `price_ticks=10200` `quantity_units=1000` maker=a3 `fill_index=2` `fill_count=3` `vm_before=20100` `vm_after=20100` `risk_mark=10200` |
| 4 | `MARKET_DATA_PUBLISH` | `best_bid=9900` `best_ask=10200` |

事务后簿：`BID [(9900, 10000)]`　`ASK [(10200, 1000)]`

**四条关键断言**：

1. 三笔独立 `TRADE_SETTLE`，`caused_by_event_id` 同指一个 `ORDER_ARRIVAL`，
   `record_index` 与 `fill_index` 各自递增；
2. **`vm` 逐笔推进**：19900 → 20000 → 20100 → 20100（半 tick 单位）。整批共用一个
   `before/after` 会把跨档的 `Impact` 全归给第一笔；
3. **第三笔 `vm_before == vm_after == 20100`**：吃掉 102 档 1 手后该档仍剩 1 手，
   `best_ask` 未变。**这不是 bug**，`Impact = 0` 是正确结果；
4. `fill_count=3` 出现在**第一笔**——第一笔成交发生时总笔数尚不可知，因此记录必须
   在事务内缓冲、撮合结束后回填 `fill_count` 并一次性写出（事件 Schema §1.4）。
   **这条断言是 `fill_count` 生成时点的唯一机器裁判**：若实现逐条即时写出，
   第一笔只能写出错误的 `fill_count=1`。

### OB-5：限价剩余挂入（保留原 `transaction_seq`）

前置：M 挂卖 100 × 2。T 买 100 × 5：

| r | 记录 | 整数字段 |
|---|---|---|
| 0 | `ORDER_ARRIVAL` | `price_ticks=10000` `quantity_units=5000` LIMIT |
| 1 | `TRADE_SETTLE` | `price_ticks=10000` `quantity_units=2000` `fill_index=0` `fill_count=1` `vm_before=20000` `vm_after=20000` `risk_mark=10000` |
| 2 | `MARKET_DATA_PUBLISH` | `best_bid=10000` `best_ask=null` |

事务后簿：`BID [(10000, 3000)]`　`ASK []`

**三条断言**：

1. **挂入不产生记录**。剩余 3000 units 挂入簿由父 `ORDER_ARRIVAL`（5000）减去成交
   （2000）推出，并由 `MARKET_DATA_PUBLISH` 的新盘口确认。时间优先键为该
   `ORDER_ARRIVAL` 的 `transaction_seq=2`，**不是**挂入时刻重新分配的序号；
2. `vm_before=20000` 走 `initial_price × 2`（首笔成交前，且 BID 侧为空）；
   `vm_after=20000` 走 `last × 2`——成交刚完成时 taker 剩余**尚未挂入**，两侧皆空；
3. 因此 `vm_before == vm_after`，`Impact = 0`。**这不是 bug**：吃掉唯一的 ASK 档
   并不改变 `last` 之外的任何估值输入。

### OB-6：市价剩余撤销（IOC）

同 OB-5 前置，改为市价单：

| r | 记录 | 整数字段 |
|---|---|---|
| 0 | `ORDER_ARRIVAL` | `price_ticks=null` `quantity_units=5000` **MARKET** |
| 1 | `TRADE_SETTLE` | `price_ticks=10000` `quantity_units=2000` `fill_index=0` `fill_count=1` `vm_before=20000` `vm_after=20000` `risk_mark=10000` |
| 2 | `ORDER_CANCELLED` | `order_id=`本单 `cancelled_qty_units=3000` `price_ticks=null` `side=BUY` `reason=IOC_REMAINDER` |
| 3 | `MARKET_DATA_PUBLISH` | `best_bid=null` `best_ask=null` |

事务后簿：两侧皆空。

**两条断言**：

1. 市价单剩余**撤销并写记录**（与 OB-5 的挂入不写记录形成对照）——撤销是一次主动
   的状态变化，挂入只是订单未被消耗的默认归宿；
2. `ORDER_CANCELLED.price_ticks = null`——被撤的是市价单，它没有挂单价。这与 OB-7
   中撤销一张**簿上限价单**（`price_ticks` 非空）是两种情形。

### OB-7：自成交 cancel-resting

前置：A 挂卖 100×2（s1）、B 挂卖 101×2（s2）。A 买 **101 × 3**：

| r | 记录 | 整数字段 |
|---|---|---|
| 0 | `ORDER_ARRIVAL` | A BUY `price_ticks=10100` `quantity_units=3000` |
| 1 | `ORDER_CANCELLED` | `order_id=s1` `agent_id=A` `cancelled_qty_units=2000` `price_ticks=10000` `side=SELL` `reason=SELF_TRADE_PREVENTION` |
| 2 | `TRADE_SETTLE` | `price_ticks=10100` `quantity_units=2000` maker=**s2** `fill_index=0` `fill_count=1` `vm_before=20000` `vm_after=20200` `risk_mark=10100` |
| 3 | `MARKET_DATA_PUBLISH` | `best_bid=10100` `best_ask=null` |

事务后簿：`BID [(10100, 1000)]`　`ASK []`

**五条断言**：

1. 撤销的是**簿上旧单**（cancel-resting），不是新到的 taker；
2. **撤销不消耗 taker 数量**——A 的 3000 units 全部可用于继续撮合；
3. taker 继续吃下一档 s2，成交价 10100（maker 价）；
4. `ORDER_CANCELLED` 带 `reason`，使自成交阻止的发生频率可统计；
5. **`record_index` 与 `fill_index` 在此错位**：撤单占用 `r1`，唯一一笔成交的
   `record_index=2` 而 `fill_index=0`。这是两个序号必须分开记录的直接证据
   （撮合合同 §2.2）。

### OB-8：整批成交后才做风险检查

**本向量属 0.1.2**（需要杠杆账户与保证金判定），0.1.1 不验收。

前置：簿上卖 100×2、101×2、102×2；若干杠杆账户持有多头。T 买 102 × 5 跨三档。

期望的记录顺序：

```text
r0        ORDER_ARRIVAL
r1..r3    TRADE_SETTLE × 3         ← 逐笔更新账户，但不做风险判定
r4..r(3+m) MARGIN_CALL × m (m ≥ 0)  ← 整批结算后一轮扫描，按 agent_id 升序
r(4+m)    MARKET_DATA_PUBLISH
```

**断言**：风险扫描**只执行一轮**，但该轮可能产生 **m 条** `MARGIN_CALL`——
事件 Schema §4.2.2 要求对所有非零仓位账户 O(N) 扫描，多个账户同时跌破维持线时
各产生一条，按 `agent_id` 升序。**「一轮」不等于「至多一条」。**

若实现逐笔检查，会在跨档的中间价位上触发他人强平，而那个价位从未作为 `last` 稳定
存在过（撮合合同 §2.3）。

### OB-9a：同时间戳双订单看到已提交状态（0.1.1 验收）

前置：M 挂卖 `10000 × 2000`（订单 s1）与 `10100 × 2000`（订单 s2）。
**同一时间戳 t** 内，A 与 B 两张买单先后到达（`enqueue_seq` 决定先后）：
A 买 `10100 × 2000`，B 买 `10100 × 2000`。

| `log_key` | 记录 | 整数字段 |
|---|---|---|
| (t, 1, 0) | `ORDER_ARRIVAL` | A BUY `price_ticks=10100` `quantity_units=2000` |
| (t, 1, 1) | `TRADE_SETTLE` | `price_ticks=10000` `quantity_units=2000` maker=**s1** `fill_index=0` `fill_count=1` `vm_before=20000` `vm_after=20000` `risk_mark=10000` |
| (t, 1, 2) | `MARKET_DATA_PUBLISH` | `best_bid=null` `best_ask=10100` |
| (t, 2, 0) | `ORDER_ARRIVAL` | B BUY `price_ticks=10100` `quantity_units=2000` |
| (t, 2, 1) | `TRADE_SETTLE` | **`price_ticks=10100`** `quantity_units=2000` maker=**s2** `fill_index=0` `fill_count=1` `vm_before=20000` `vm_after=20200` `risk_mark=10100` |
| (t, 2, 2) | `MARKET_DATA_PUBLISH` | `best_bid=null` `best_ask=null` |

事务后簿：两侧皆空。

**三条断言**：

1. **B 成交于 10100，不是 10000**——A 的事务已提交，s1 已被吃光。若 `TRADE_SETTLE`
   作为队列事件入队，同时间戳内 class 0 全排在 class 1 前，B 撮合时会看到**尚未被
   消耗**的 s1 并错误地成交于 10000。**这个价差就是该向量的全部意义**；
2. `vm_before` 的连续性：B 的 `vm_before=20000` 恰等于 A 的 `vm_after`——两个事务
   之间没有任何未记录的状态变化。两笔 `vm` 都走 `last × 2` 分支（BID 侧全程为空）；
3. 六条 `log_key` 严格递增，日志顺序与在线执行顺序一致。

**这是队列事件/事务记录分野的核心验收**（事件 Schema §1.4），且**不依赖任何账户
或保证金逻辑**——0.1.1 无杠杆也能完整执行。

### OB-9b：同时间戳双订单的保证金拒单（**0.1.2 验收**）

同 OB-9a 的时序结构，但第一张成交后耗尽保证金，第二张因
`reserved_after > risk_equity` 被拒：事务只有 `record_index=0`，
`accepted=false`、`reject_reason=INSUFFICIENT_MARGIN`。

**0.1.1 不验收本向量**：其前置需要杠杆账户、维持保证金率与费率，而 0.1.1 的准入
检查是恒通过的桩（撮合合同 §5）。完整的账户初态、费率与 `reserved` 整数期望值随
0.1.2 的账户验收向量一并给出，届时须与本表的 `log_key` 结构对齐。

## 3. 实现须复现的断言

每个向量执行后断言：

1. 事件序列的**种类、顺序、`record_index`** 与本表完全一致——**包括
   `MARKET_DATA_PUBLISH` 的存在与位置**。多写、少写或错位都判失败；
2. 每笔成交的 `price_ticks` / `quantity_units` / `maker_order_id` /
   `fill_index` / `fill_count` 与本表相等（整数比较）；
3. `valuation_mark_before/after` 与 `risk_mark` 逐笔相等（半 tick / tick 整数）；
4. `ORDER_CANCELLED` 的 `cancelled_qty_units` / `price_ticks` / `side` / `reason`
   与本表相等；
5. 事务后的簿状态（各价位聚合数量）与本表相等；
6. 所有 `log_key` 严格递增。

**一律整数比较，不得使用容差断言**。表中括号内的十进制值只用于阅读，测试夹具
不得从它们换算——换算是 half-tick 字段最常见的错误来源（误乘或误除 2）。

## 4. 覆盖矩阵

| 向量 | 里程碑 | 覆盖的合同条款 |
|---|---|---|
| OB-1 | 0.1.1 | 价格优先、maker 价成交、纯挂入事务也发布行情 |
| OB-2 | 0.1.1 | 时间优先按 `transaction_seq`、深度变化即发布行情 |
| OB-3 | 0.1.1 | price improvement |
| OB-4 | 0.1.1 | 跨档拆分、逐笔 `vm` 推进、`fill_count` 回填时点 |
| OB-5 | 0.1.1 | 限价剩余挂入**不产生记录**、保留原 `transaction_seq` |
| OB-6 | 0.1.1 | 市价 IOC 撤销产生 `ORDER_CANCELLED` |
| OB-7 | 0.1.1 | 自成交 cancel-resting、`record_index` 与 `fill_index` 错位 |
| OB-9a | 0.1.1 | 队列事件/事务记录分野（不依赖账户） |
| **OB-8** | **0.1.2** | 整批后一轮风险扫描、`MARGIN_CALL × m` |
| **OB-9b** | **0.1.2** | 保证金拒单 |

0.1.1 的退出条件 E3 = **OB-1—OB-7 与 OB-9a 全部通过**。

## 5. 已知界限

- 本表**不含账户、手续费与保证金**——OB-8/OB-9b 只断言记录的**位置与数量**，
  账户数值由[账户验收向量](acceptance-vectors.md)覆盖；
- 除 OB-9a 外全部在**单一时间戳**内；跨时间戳的定序由事件 Schema §1.1 的
  KR-006 断言覆盖；
- 强平单的撮合行为与市价单相同（OB-6），其触发与数量计算见账户合同 §4。
