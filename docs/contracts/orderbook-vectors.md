# 订单簿验收向量

**适用范围**：跨规格实现合同（当前交付规格 001）  
**状态**：Stable（变更须同步[撮合合同](matching.md)）  
**创建日期**：2026-08-01  
**支撑需求**：001 / FR-001—FR-003、SC-001；PRD / PR-001  
**关联**：[撮合](matching.md)、[事件 Schema](event-schema.md)、
[账户验收向量](acceptance-vectors.md)

## 0. 用途

[撮合合同](matching.md) §8 的九条验收要点此前只有**场景描述**，没有期望值——
实现者会写出自己认为对的测试，然后测试通过。本文补齐每条的**完整期望状态**：
事件序列、每条记录的 `record_index`、成交价与量、`fill_index` / `fill_count`、
逐笔 `valuation_mark` 与 `risk_mark`、以及事务后的簿状态。

与[账户验收向量](acceptance-vectors.md)互补：那份管账本，这份管簿与撮合。
**两份都是实现的裁判**，实现与本表不符时以本表为准，除非能证明本表违反撮合合同。

## 1. 公共约定

```text
tick_size = 0.01    min_quantity = 0.001
log_key = (timestamp, transaction_seq, record_index)
  ├ 队列事件（ORDER_ARRIVAL）恒为 record_index = 0
  └ 事务记录从 1 递增
```

下表中「簿」为事务结束后的状态，价格由高到低（BID）/由低到高（ASK）聚合。
所有向量均在**同一时间戳**内，故只列 `transaction_seq` 与 `record_index`。

**本文不含账户与手续费**——那些由账户验收向量覆盖。这里只验簿与成交生成。

## 2. 验收向量

### OB-1：价格优先

| # | 事务 | record | 记录 | 内容 |
|---|---|---|---|---|
| 1 | A 买 100 × 5 | 0 | `ORDER_ARRIVAL` | BUY 100.00 × 5.000 LIMIT |
| | | 1 | `RESTED` | o1 剩 5.000，`transaction_seq=1` |
| 2 | B 买 101 × 5 | 0 | `ORDER_ARRIVAL` | BUY 101.00 × 5.000 |
| | | 1 | `RESTED` | o2 剩 5.000，`transaction_seq=2` |
| 3 | C 卖 100 × 3 | 0 | `ORDER_ARRIVAL` | SELL 100.00 × 3.000 |
| | | 1 | `TRADE_SETTLE` | **价 101.00** × 3.000，maker=**o2** |

**断言**：C 的卖单虽限价 100，却成交于 **101**——买方队列按价格降序，出价更高的 o2
排在 o1 前。事务后 `BID [(101.00, 2.000), (100.00, 5.000)]`。

### OB-2：时间优先（同价按 `transaction_seq`）

| # | 事务 | record | 记录 | 内容 |
|---|---|---|---|---|
| 1 | A 买 100 × 5 | 0/1 | `ORDER_ARRIVAL`/`RESTED` | `transaction_seq=1` |
| 2 | B 买 100 × 5 | 0/1 | `ORDER_ARRIVAL`/`RESTED` | `transaction_seq=2` |
| 3 | C 卖 100 × 3 | 1 | `TRADE_SETTLE` | 价 100.00 × 3.000，maker=**o1** |

**断言**：同价位下先到（`transaction_seq` 小）者先成交。事务后
`BID [(100.00, 7.000)]`——A 剩 2、B 仍 5。

### OB-3：price improvement

| # | 事务 | record | 记录 | 内容 |
|---|---|---|---|---|
| 1 | A 卖 100 × 5 | 0/1 | `ORDER_ARRIVAL`/`RESTED` | ASK 100.00 |
| 2 | B 买 **限价 101** × 3 | 1 | `TRADE_SETTLE` | **价 100.00** × 3.000 |

**断言**：成交价取 maker 挂单价 100，**不是** taker 限价 101（撮合合同 §2.1）。
事务后 `ASK [(100.00, 2.000)]`。

### OB-4：跨三档（`valuation_mark` 逐笔推进）

前置：M 挂卖 100×2、101×2、102×2；N 挂买 99×10（使 `mid` 有定义）。
T 买 **限价 102 × 5**：

| record | 记录 | 价 × 量 | maker | `fill_index`/`fill_count` | `vm_before` | `vm_after` | `risk_mark` |
|---|---|---|---|---|---|---|---|
| 0 | `ORDER_ARRIVAL` | — | — | — | — | — | — |
| 1 | `TRADE_SETTLE` | 100.00 × 2.000 | a1 | **0 / 3** | **99.50** | **100.00** | 100.00 |
| 2 | `TRADE_SETTLE` | 101.00 × 2.000 | a2 | **1 / 3** | **100.00** | **100.50** | 101.00 |
| 3 | `TRADE_SETTLE` | 102.00 × 1.000 | a3 | **2 / 3** | **100.50** | **100.50** | 102.00 |

事务后 `BID [(99.00, 10.000)]`　`ASK [(102.00, 1.000)]`。

**三条关键断言**：

1. **三笔独立的 `TRADE_SETTLE`**，`caused_by_event_id` 全部指向同一 `ORDER_ARRIVAL`，
   `record_index` 与 `fill_index` 各自递增；
2. **`valuation_mark` 逐笔推进**：99.50 → 100.00 → 100.50 → 100.50。若整批共用一个
   `before/after`，跨档成交的 `Impact` 会被错误地全归给第一笔（撮合合同 §2.2）；
3. **第三笔 `vm_before == vm_after == 100.50`**：吃掉 102 档 1 手后该档仍剩 1 手，
   `best_ask` 未变，故 `mid` 未变。**这不是 bug**——`Impact` 为 0 是正确结果。

`risk_mark` 逐笔等于该笔成交价，因此一次跨档成交会**依次**推进 `last`。

### OB-5：限价剩余挂入（保留原 `transaction_seq`）

前置：M 挂卖 100 × 2。T 买 100 × 5：

| record | 记录 | 内容 |
|---|---|---|
| 0 | `ORDER_ARRIVAL` | BUY 100.00 × 5.000 LIMIT |
| 1 | `TRADE_SETTLE` | 100.00 × 2.000，maker=a1 |
| 2 | `RESTED` | 剩 **3.000** 挂入，`transaction_seq=2`（**该订单到达时的值**） |

**断言**：挂入簿的时间优先键是该 `ORDER_ARRIVAL` 的 `transaction_seq`，**不是**挂入
时刻重新分配的序号。事务后 `BID [(100.00, 3.000)]`。

### OB-6：市价剩余撤销（IOC）

同 OB-5 的前置，改为市价单：

| record | 记录 | 内容 |
|---|---|---|
| 0 | `ORDER_ARRIVAL` | BUY **price=null** × 5.000 **MARKET** |
| 1 | `TRADE_SETTLE` | 100.00 × 2.000 |
| 2 | `CANCEL` | 剩 3.000，`reason=IOC_REMAINDER` |

**断言**：市价单剩余**立即撤销**、不挂入簿。事务后 `BID []　ASK []`——簿被清空。

### OB-7：自成交 cancel-resting

前置：A 挂卖 100 × 2（o=s1）、B 挂卖 101 × 2（o=s2）。A 买 **101 × 3**：

| record | 记录 | 内容 |
|---|---|---|
| 0 | `ORDER_ARRIVAL` | A BUY 101.00 × 3.000 |
| 1 | `CANCEL` | **s1**（A 自己的卖单），`reason=SELF_TRADE_PREVENTION` |
| 2 | `TRADE_SETTLE` | 101.00 × 2.000，maker=**s2**（B 的） |
| 3 | `RESTED` | A 的买单剩 1.000 挂入 |

**四条断言**：

1. 撤销的是**簿上的旧单**（cancel-resting），不是新到的 taker；
2. **撤销不消耗 taker 数量**——A 的 3 手全部可用于继续撮合；
3. taker 继续吃**下一档** s2，成交价 101（maker 价）；
4. 撤销写入独立记录并带 `reason`，使自成交阻止的发生频率可被统计。

事务后 `BID [(101.00, 1.000)]　ASK []`。

### OB-8：整批成交后才做风险检查

前置：簿上卖 100×2、101×2、102×2；某杠杆账户持有多头。T 买 102 × 5 跨三档。

**期望的记录顺序**：

```text
record 0     ORDER_ARRIVAL
record 1..3  TRADE_SETTLE × 3        ← 逐笔更新账户，但不做风险判定
record 4     MARGIN_CALL（若有）      ← 整批结算完毕后，仅一次
record 5     MARKET_DATA_PUBLISH
```

**断言**：`MARGIN_CALL` 的数量与 `TRADE_SETTLE` 的笔数**无关**——三笔成交至多产生
一轮两阶段检查。若实现逐笔检查，会在跨档的中间价位上触发他人强平，而那个价位从未
作为 `last` 稳定存在过（撮合合同 §2.3）。

`fill_index == fill_count − 1` 的那笔之后即是风险检查的位置，重放器据此定位，
无需先读完整个事务。

### OB-9：同时间戳双订单的黄金日志

同一时间戳内，同一代理的两张订单先后到达。第一张成交后耗尽保证金，第二张必须被拒。

**期望的 `log_key` 序列**：

```text
(t, transaction_seq=1, record_index=0)   ORDER_ARRIVAL  A   ← 第一张
(t, transaction_seq=1, record_index=1)   TRADE_SETTLE       ← A 的事务记录
(t, transaction_seq=1, record_index=2)   MARKET_DATA_PUBLISH
(t, transaction_seq=2, record_index=0)   ORDER_ARRIVAL  B   ← 第二张
(t, transaction_seq=2, record_index=1)   （无成交，accepted=false）
```

**这是队列事件/事务记录分野的核心验收**（事件 Schema §1.3）：

- B 的准入检查看到的是 **A 的事务已完成后**的账户状态，因此被正确拒绝；
- 若 `TRADE_SETTLE` 作为队列事件入队，则同时间戳内 class 0 全部排在 class 1 之前，
  B 会用**尚未结算**的旧账户通过检查——同一笔保证金被用两次；
- 所有 `log_key` 严格递增，且日志顺序与在线执行顺序一致。

## 3. 实现须复现的断言

每个向量执行后断言：

1. 事件序列的**种类、顺序、`record_index`** 与本表完全一致；
2. 每笔成交的 `price_ticks` / `quantity_units` / `maker_order_id` /
   `fill_index` / `fill_count` 与本表相等（整数比较）；
3. `valuation_mark_before/after` 与 `risk_mark` 逐笔相等；
4. 事务后的簿状态（各价位聚合数量）与本表相等；
5. 所有 `log_key` 严格递增。

## 4. 已知界限

- 本表**不含账户、手续费与保证金**——OB-8/OB-9 只断言记录的**位置与数量**，
  账户数值由[账户验收向量](acceptance-vectors.md)覆盖；
- 本表全部在**单一时间戳**内，跨时间戳的定序由事件 Schema §1.1 的 KR-006 断言覆盖；
- 强平单的撮合行为与市价单相同（OB-6），其触发与数量计算见账户合同 §4。
