# 订单簿验收向量

**适用范围**：跨规格实现合同（当前交付规格 v0.1）  
**状态**：Stable（变更须同步[撮合合同](matching.md)）  
**创建日期**：2026-08-01　**更新日期**：2026-08-02  
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
| 2 | `ORDER_CANCELLED` | `order_id=`本单 `cancelled_qty_units=3000` `price_ticks=null` `side=BUY` `order_type=MARKET` `reason=IOC_REMAINDER` |
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
| 1 | `ORDER_CANCELLED` | `order_id=s1` `agent_id=A` `cancelled_qty_units=2000` `price_ticks=10000` `side=SELL` `order_type=LIMIT` `reason=SELF_TRADE_PREVENTION` |
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

### OB-8：整批成交后才做风险检查（0.1.2 验收）

**本向量覆盖 0.1.2 退出条件 E1**——含 6 种账户与 4 条补充向量。

**统一配置**：

```text
tick_size = 0.01, min_quantity = 0.001, cash_unit = 1e-8, MULT = 1000
maker_bps = -1, taker_bps = 5, fee_bps_cap = 5
initial_price_ticks = 10000, maint_bp = 500, target_bp = 1000
liquidation_latency_ns = 1000000  (1 毫秒)
```

#### OB-8 主向量：6 账户整批扫描

前置簿：`M 挂卖 10000×2000, 10100×2000, 10200×2000`（三档）。
6 个账户初始状态（按 `agent_id` 字典序升序）：

| agent_id | wallet_units | position | entry | leverage_tier | initial_bp | 状态 |
|---|---|---|---|---|---|---|
| `A_safe` | 10000000000000 | 0 | 0 | 10 | 1000 | ACTIVE（始终安全） |
| `B_first` | 500000000000 | 500000 | 5000000000000 | 10 | 1000 | 满杠杆，触发后首次进 PENDING |
| `C_stable` | 500000000000 | 500000 | 5000000000000 | 10 | 1000 | 已 PENDING，数量稳定 |
| `D_recount` | 500000000000 | 500000 | 5000000000000 | 10 | 1000 | 已 PENDING，价格变化数量重算 |
| `E_recover` | 500000000000 | 500000 | 5000000000000 | 10 | 1000 | 已 PENDING，本次恢复至 ACTIVE |
| `F_breach` | 500000000000 | 0 | 0 | 10 | 1000 | 已被前一笔强平归零且 wallet<0 |

`T 买 LIMIT 10200×5000`（taker）。跨三档成交于 10000/10100/10200（与 OB-4 同样的价格，但数量更大）。

**关键风控计算**（risk_mark = 10200，三档最后一笔）：

| 账户 | risk_equity | notional | margin_ratio_bp | 结论 |
|---|---|---|---|---|
| A_safe | wallet=10000 | 0 | null | 安全（无仓位） |
| B_first | 5000+500×102−50000 = 600 | 500×102 = 51000 | 117 | **触发** → PENDING |
| C_stable | 5000+500×102−50000 = 600 | 51000 | 117 | **触发**，但假定本事务前已 pending 且 required_quantity 恰为刚算出的同一值 |
| D_recount | 600 | 51000 | 117 | **触发**，required_quantity 与 C 不同（模拟已 pending 状态下的计算偏差） |
| E_recover | 假设本事务前 margin_ratio = 600（≥500） | — | ≥500 | **OK**（恢复转移） |
| F_breach | 0 + 0 − 0 = 0，但 wallet = -1（核销前瞬间） | 0 | null | **BREACHED**（阶段 1） |

**`m` 的判定**（事件 Schema §4.2.2 "可行动风险决定" 判据）：

| 账户 | 扫描前 | 扫描后 | 决定 | 记入？ | verdict |
|---|---|---|---|---|---|
| A_safe | ACTIVE | ACTIVE | 无 | **否** | — |
| B_first | ACTIVE | PENDING | 首次进 pending，新调度强平单 | **是** | PENDING_LIQUIDATION |
| C_stable | PENDING | PENDING | 仍不足，但 required_quantity 不变 | **否** | — |
| D_recount | PENDING | PENDING | 仍不足，required_quantity **变化** | **是** | PENDING_LIQUIDATION |
| E_recover | PENDING | ACTIVE | 恢复至维持线以上 | **是** | OK |
| F_breach | ACTIVE | LIQUIDATED | position=0 且 wallet<0 | **是** | BREACHED |

故 `m = 4`（B_first、D_recount、E_recover、F_breach）。`MARKET_DATA_PUBLISH` 的
`record_index = 4 + 4 = 8`。

**记录顺序**（按 `agent_id` 升序，r0 父 `ORDER_ARRIVAL`，r1..r3 三笔 `TRADE_SETTLE`，
r4..r7 四条 `MARGIN_CALL`，r8 `MARKET_DATA_PUBLISH`）：

```text
r0   ORDER_ARRIVAL          T BUY LIMIT 10200×5000 (caused_by self = e_tx_0)
r1   TRADE_SETTLE           10000×2000  maker=M1  fill_index=0  fill_count=3
r2   TRADE_SETTLE           10100×2000  maker=M2  fill_index=1  fill_count=3
r3   TRADE_SETTLE           10200×1000  maker=M3  fill_index=2  fill_count=3
r4   MARGIN_CALL            B_first  verdict=PENDING_LIQUIDATION
                             required_quantity_units=288678  (案例 7 一致)
                             margin_ratio_bp=117  liquidation_generation_after=1
                             chain_id=<B_first的event_id>  chain_depth=0
r5   MARGIN_CALL            D_recount verdict=PENDING_LIQUIDATION
                             required_quantity_units=193271  (案例 7 一致)
                             margin_ratio_bp=117  liquidation_generation_after=2
                             chain_id=<D_recount上一代event_id>  chain_depth=<继承>
r6   MARGIN_CALL            E_recover verdict=OK
                             required_quantity_units=0  liquidation_generation_after=<+1>
                             chain_id=null  chain_depth=null
r7   MARGIN_CALL            F_breach  verdict=BREACHED
                             required_quantity_units=0  liquidation_generation_after=1
                             chain_id=null  chain_depth=null
                             postings=[ACCOUNT, EXCHANGE_RISK]
r8   MARKET_DATA_PUBLISH    best_bid=10000  best_ask=null  last=10200
```

**三条断言**：

1. **`m = 4` 不是 6**：`A_safe`（无仓位安全）和 `C_stable`（PENDING→PENDING 数量不变）
   不产生 `MARGIN_CALL`；其余 4 账户每个都"产生可行动风险决定"；
2. **r4..r7 的 `caused_by_event_id` 全部相同** = `e_tx_0`（本事务的父 `ORDER_ARRIVAL`）；
3. **r4..r7 的 `risk_mark_event_id` 全部相同** = `e_tx_3`（本批最后一笔 `TRADE_SETTLE`）。
   `risk_mark_ticks = 10200`（该笔的成交价）。

**核销分录**（F_breach 的 r7.postings）：

```text
postings[0]  WRITE_OFF_POSTING  role=ACCOUNT       agent_id=F_breach
             wallet_delta=+1  wallet_after=0  position_after=0
             entry_notional_after=0  risk_pnl_delta=0
postings[1]  WRITE_OFF_POSTING  role=EXCHANGE_RISK agent_id=null
             wallet_delta=0    wallet_after=null  position_after=null
             entry_notional_after=null  risk_pnl_delta=-1
```

注意交易所侧三 `*_after` 字段为 `null`（不是 0），与 §4.2.3 一致。

#### OB-8 补充向量 1：部分强平后 required_quantity 重算（PENDING→PENDING）

前置：单代理 `X`，`wallet=5000×10⁸`，`tier=10`，建仓 500×100，`risk_mark=94`（同案例 7）。

**事件序列**（含两事务，第二事务是强平单的自身事务）：

```text
# === 第一事务：本批成交触发 X 首次进入 PENDING ===
t=0   tx=K    r0  ORDER_ARRIVAL     Y BUY 94×1000 (推动 risk_mark=94)
t=0   tx=K    r1  TRADE_SETTLE      94×500  fill_index=0  fill_count=1
                                       caused_by_event_id = eK_0
t=0   tx=K    r2  MARGIN_CALL       X  verdict=PENDING_LIQUIDATION
                                       required_quantity_units=288678
                                       margin_ratio_bp=425
                                       liquidation_generation_after=1
                                       chain_id=<event_id of r2>  chain_depth=0
                                       caused_by_event_id=eK_0
                                       risk_mark_event_id=eK_1
t=0   tx=K    r3  MARKET_DATA_PUBLISH

# === 跨越 liquidation_latency_ns 1ms，调度强平单 ===
# === 第二事务：强平单（origin=LIQUIDATION）到达交易所 ===
# 此处假设：X 仍在 PENDING，部分强平 200 手后价格跌至 92（跨档）
# 强平单市价 IOC，触发重算 required_quantity=193271
# 由于是"重算"，liquidation_generation 必须 +1，调度替代单

t=1ms  tx=K+1  r0  ORDER_ARRIVAL     强平单  SELL MARKET 288678
                                        origin=LIQUIDATION
                                        decision_event_id=eK_2  (指向触发它的 MARGIN_CALL)
                                        trigger_ratio_bp=425
                                        liquidation_generation=1
                                        accepted=true  reject_reason=null
t=1ms  tx=K+1  r1  TRADE_SETTLE      94×200  fill_index=0  fill_count=1
t=1ms  tx=K+1  r2  MARGIN_CALL       X  verdict=PENDING_LIQUIDATION
                                        required_quantity_units=193271  # 重算
                                        margin_ratio_bp=359
                                        liquidation_generation_after=2  # +1
                                        chain_id=<继承自 r2 of tx K>
                                        chain_depth=<继承，不 +1>
                                        caused_by_event_id=e(K+1)_0
                                        risk_mark_event_id=e(K+1)_1
t=1ms  tx=K+1  r3  MARKET_DATA_PUBLISH
```

**关键断言**：
1. 第二事务的 r2 与第一事务的 r2 **都是 PENDING_LIQUIDATION**（状态没变），但
   `liquidation_generation_after` 从 1 → 2（换代），**必须**记一条 `MARGIN_CALL`；
2. 第二事务的 r2 不计入 OB-8 的 `m`（它有自己的 `transaction_seq`）；
3. **替代单尚未到达**——它由这次重算在后续事务中调度，本向量到此结束。

#### OB-8 补充向量 2：延迟窗口内恢复（LIQUIDATION_STALE 拒单）

前置：单代理 `X` 已 PENDING，`liquidation_generation=1`（强平单已入队但未到达）。

```text
# === 第一事务：进入 PENDING，调度强平单（generation=1）===
# ... (同补充向量 1 第一事务) ...

# === 第二事务：他人成交使 X 恢复至 ACTIVE ===
# 此时强平单还在队列里携带 generation=1
t=ε   tx=K+1  r0  ORDER_ARRIVAL     Z BUY 105×100  (反向拉升 X 的 risk_mark)
t=ε   tx=K+1  r1  TRADE_SETTLE      105×100
t=ε   tx=K+1  r2  MARGIN_CALL       X  verdict=OK
                                        required_quantity_units=0
                                        liquidation_generation_after=2  # +1（恢复也换代）
                                        chain_id=null  chain_depth=null
t=ε   tx=K+1  r3  MARKET_DATA_PUBLISH

# === 第三事务：原强平单到达交易所，账户已为 ACTIVE、generation=2 ===
t=1ms  tx=K+2  r0  ORDER_ARRIVAL     强平单  SELL MARKET
                                        origin=LIQUIDATION
                                        liquidation_generation=1   # 旧代次
                                        accepted=false
                                        reject_reason=LIQUIDATION_STALE
                                        reserved_delta_units=0
t=1ms  tx=K+2  (无后续记录 — 只有 r0)
```

**关键断言**：
1. 强平单到达时被拒（`accepted=false, reject_reason=LIQUIDATION_STALE`），**事务只有 r0**；
2. 拒绝原因是：账户当前 `liquidation_generation=2`，订单携带 `=1`，不等即拒；
3. **恢复也换代**（v0.1 spec `liquidation_generation_after=2`），让旧强平单失效。

#### OB-8 补充向量 3：乱序到达，仅最新代次通过

前置：X 已 PENDING 且发生两次数量重算，`liquidation_generation=1`。
**重算 #1**（假设）→ 调度强平单 A（gen=2）；
**重算 #2** → 调度强平单 B（gen=3）；A 仍在队列里。

**乱序到达**：B 先于 A 到达交易所。

```text
# === 事务 1：强平单 B (gen=3) 先到 ===
t   tx=M    r0  ORDER_ARRIVAL  强平单 B
                                  origin=LIQUIDATION
                                  liquidation_generation=3
                                  accepted=true  (账户仍 PENDING 且 gen=3)
                                  reject_reason=null
t   tx=M    r1  TRADE_SETTLE  ...

# === 事务 2：强平单 A (gen=2) 随后到 ===
t'  tx=M+1  r0  ORDER_ARRIVAL  强平单 A
                                  origin=LIQUIDATION
                                  liquidation_generation=2
                                  accepted=false
                                  reject_reason=LIQUIDATION_STALE  (gen 不等)
                                  reserved_delta_units=0
t'  tx=M+1  (无后续)
```

**关键断言**：
1. 代次只增不减，乱序到达时只有最新代次通过；
2. 旧强平单 A 一定被拒，账户不被过量强平。

#### OB-8 补充向量 4：三账户同批，三种 chain 归属

前置：单时间戳上 Y 强平成交 100 手推动价格。
三个账户同时被扫描：

| 账户 | 扫描前 | 扫描后 | 角色 | chain_id | chain_depth |
|---|---|---|---|---|---|
| `Y` | PENDING (gen=k) | PENDING 续单重算 | **续单重算** | 继承父判定 | 继承，不+1 |
| `Z_new` | ACTIVE | PENDING | **新拖入** | 继承父判定 | 父 +1 |
| `W_other` | PENDING (其他链) | PENDING 数量重算 | **他链重算** | **保留自身** | **保留自身** |

其中 `W_other` 已属于另一条链（不是由 Y 的强平触发的），本次仅因价格变化而数量重算。

**事件序列**：

```text
t   tx=L    r0  ORDER_ARRIVAL  (Y 的强平单)  ...
t   tx=L    r1  TRADE_SETTLE   (跨档成交 Y 的强平)
t   tx=L    r2  MARGIN_CALL    Y     chain_id=<gen of eL_0's decision_event_id>
                                          chain_depth=<父判定深度>
t   tx=L    r3  MARGIN_CALL    Z_new chain_id=<同上>  chain_depth=<父+1>
t   tx=L    r4  MARGIN_CALL    W_other chain_id=<W_other已有>
                                           chain_depth=<W_other已有>
t   tx=L    r5  MARKET_DATA_PUBLISH
```

**关键断言**：
1. **W_other 的 chain_id 和 chain_depth 完全保留**（既不继承 Y 的链，也不是父+1）；
2. 仅 `chain_id` 分组时，W_other 不与 Y/Z_new 划为同一组——每条链的规模按 `chain_id`
   分组，不能只用 `chain_depth`（深度可能相同）；
3. 三条 `MARGIN_CALL` 的 `agent_id` 升序产生：`W_other < Y < Z_new`（按字符串排序）。

### OB-9b：同时间戳双订单的保证金拒单（0.1.2 验收）

同 OB-9a 的时序结构，但第一张成交后耗尽保证金，第二张因
`reserved_after > risk_equity` 被拒：事务只有 `record_index=0`，
`accepted=false`、`reject_reason=INSUFFICIENT_MARGIN`。

**统一配置**：

```text
tick_size = 0.01, min_quantity = 0.001, cash_unit = 1e-8, MULT = 1000
maker_bps = -1, taker_bps = 5
initial_price_ticks = 10000, maint_bp = 500, target_bp = 1000
leverage_tier = 1  (initial_bp = 10000)
A 和 B 的 wallet_units = 1000000000000  (10000 human)
```

**OB-9b 完整记录**：

```text
(t, 1, 0)  ORDER_ARRIVAL  A BUY 10100×2000  (从 B 接手)
            accepted=true  reserved_delta_units=<正向>
(t, 1, 1)  TRADE_SETTLE   10000×2000  maker=M_s1
                              fill_index=0  fill_count=1
                              vm_before=20000  vm_after=20000  risk_mark=10000
                              A.reserved_after = IM(买 2000 @ 100) = 200×100×1 = 20000
                              A.risk_equity   = wallet − taker_fee
                                              = 10000×10⁸ − 2000×10000×1000×5/10⁴
                                              = 1000000000000 − 1000000000
                                              = 999000000000
                              10000 ≤ 999000000000  ✓ 通过
(t, 1, 2)  MARKET_DATA_PUBLISH  best_bid=null  best_ask=10100

(t, 2, 0)  ORDER_ARRIVAL  B BUY 10100×2000
            accepted=false
            reject_reason=INSUFFICIENT_MARGIN
            reserved_delta_units=0
            (B 的 reserved_after > B 的 risk_equity)
(t, 2, *)  (无后续记录 — 只有 r0)
```

**关键断言**：
1. **B 的事务只有 `record_index=0`**，与 §1.4 一致；
2. `M_s1`（挂在卖 100 的 maker）已被 A 的成交吃光，B 撮合时簿上无对应挂单，但
   **B 在准入阶段就被拒**，因此根本没有进入撮合循环；
3. 与 OB-9a 对比：OB-9a 中 B 成交于 10100（因为 s1 已被 A 吃光），本向量 B 根本
   没成交——**保证金耗尽是准入阶段的事，不是撮合阶段**。

**「没钱了」≠「吃光了」**：OB-9a 检验撮合的时序可见性；OB-9b 检验准入的时序可见性。
两者并列才能把"两张同时间戳订单"的所有退化场景锁死。

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

### OB-9b：同时间戳双订单的保证金拒单（0.1.2 验收）

**完整期望值见上文 OB-9b 章节（含 0.1.2 账户初态、reserve 与保证金判定的完整整数）**。
本节只保留向后兼容的骨架描述：

同 OB-9a 的时序结构，但第一张成交后耗尽保证金，第二张因
`reserved_after > risk_equity` 被拒：事务只有 `record_index=0`，
`accepted=false`、`reject_reason=INSUFFICIENT_MARGIN`。

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

- OB-1—OB-7、OB-9a 不含账户、手续费与保证金，只验簿与成交生成，账户数值由
  [账户验收向量](acceptance-vectors.md)覆盖；
- **OB-8、OB-9b 含完整账户初态与保证金期望**（0.1.2 T007 冻结）；
- 全部向量都在**单一时间戳**内；只有 OB-9a/OB-9b 在该时间戳内含**多个订单事务**，
  其余各向量的每个事务独占一个时间戳。跨时间戳的定序由事件 Schema §1.1 的
  KR-006 断言覆盖，不由本表覆盖；
- 强平单的撮合行为与市价单相同（OB-6），其触发与数量计算见账户合同 §4。
