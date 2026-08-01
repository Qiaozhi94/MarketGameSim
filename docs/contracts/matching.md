# 撮合合同：订单簿与成交生成

**适用范围**：跨规格实现合同（当前交付规格 001）  
**状态**：Stable（变更须记 ADR 并提升 `schema_version`）  
**创建日期**：2026-08-01  
**支撑需求**：001 / FR-001—FR-003；PRD / PR-001  
**关联**：[事件 Schema](event-schema.md)、[账户与保证金](margin-and-account.md)、
[代理策略](agent-strategy.md)、[退化状态](degenerate-states.md)

## 0. 本文为什么必须存在

此前文档只说「价格时间优先的限价订单簿」，但**没有定义**：taker 吃 maker 时按谁的
价成交、一张订单跨多档时产生几个 `TRADE_SETTLE`、限价单未成交部分的去向。

这些是 0.1.1 第一天就会撞上的问题，且每一个都有多种合法实现。不定死，实现者的选择会
直接改变成交价序列、`last` 的取值、乃至强平触发时点。

## 1. 订单簿结构与定序

### 1.1 价格时间优先

- **价格优先**：买方按 `price_ticks` **降序**、卖方按**升序**排队；
- **时间优先**：同价位内按订单到达事务的 **`transaction_seq` 升序**（KR-003）——不是
  `timestamp`，同一纳秒到达的两笔订单必须有确定先后。

**定序不得依赖字典/集合遍历顺序、对象标识或哈希值。**

### 1.2 撮合事务：ORDER_ARRIVAL 是唯一的事务边界

`ORDER_ARRIVAL` 是**队列事件**，弹出时执行一个**原子事务**（事件 Schema §1.4）：

```text
ORDER_ARRIVAL 弹出
├─ 准入检查（§5）
├─ 撮合循环：逐档成交，每档【立即更新双方账户】并生成 TRADE_SETTLE 记录
├─ 剩余处理：挂入簿 或 IOC 撤销
├─ 两阶段风险检查（一次，§2.3）→ 生成 MARGIN_CALL 记录
├─ 生成 MARKET_DATA_PUBLISH 记录
└─ 若有待强平账户：入队新的 ORDER_ARRIVAL（跨 liquidation_latency_ns）
事务结束
```

**事务内的账户变化立即生效**。因此同一时间戳内后续弹出的 `ORDER_ARRIVAL` 看到的
是已更新的账户——这正是事件 Schema §1.4 要解决的问题。

`TRADE_SETTLE`、`MARGIN_CALL`、`MARKET_DATA_PUBLISH` 以及自成交阻止产生的 `CANCEL`
都是**事务记录**，不入队、不会被再次执行。唯一入队的产物是强平单（它必须跨越
`liquidation_latency_ns`，且是 class 1→0 的回退跳转，见事件 Schema §1.2）。

## 2. 成交生成

### 2.1 成交价 = maker 的挂单价

**taker 吃 maker 时，成交价恒为 maker 的挂单价 `price_ticks`，不是 taker 的限价。**

这意味着 taker 可能获得**优于自身限价**的成交（price improvement）：买单限价 101、
簿上最优卖价 100 → 成交于 **100**，taker 少付。

理由：maker 先到达，其报价构成对市场的承诺；按 taker 限价成交等于让后到者单方面
改写价格。这也是真实交易所的通行规则。

**当前代理策略下 price improvement 不会发生**：`aggressiveness ∈ [0,1]` 使买单价
`= bid + a×(ask−bid) ≤ ask`，限价永不超过对侧最优价。`a = 1` 时限价恰为 `ask`，
成交价也是 `ask`，两者相同。

该代理的 `Spread`（指标字典 §5.2）仍为**负**——`Spread = q × (mid − ask) < 0`，
即付出半个价差。例：`bid=100, ask=100.10, mid=100.05`，买 10 手成交于 100.10 →
`Spread = 10 × (100.05 − 100.10) = −0.50`。

规则仍须定义，因为**强平单是市价单**（§3），会跨档吃掉多个价位，此时各档均按
maker 挂单价成交。将来引入其他订单类型时同理。

### 2.2 跨多档：逐档拆分为多个 TRADE_SETTLE

一张订单吃掉多个价位时，**每一档产生一个独立的 `TRADE_SETTLE`**——因为该事件的
`price_ticks` 是单一值（事件 Schema §4.2）。

拆分规则：

```text
按对手方队列顺序（价格优先 → 到达事务 `transaction_seq` 优先）逐档撮合：
  对每一档：
    fill_qty = min(taker 剩余数量, 该 maker 订单剩余数量)
    生成一个 TRADE_SETTLE，price_ticks = 该 maker 的挂单价
    taker 剩余 -= fill_qty
  直到 taker 剩余为 0，或无可成交对手方
```

**多个 `TRADE_SETTLE` 的属性**：

| 项 | 规则 |
|---|---|
| `caused_by_event_id` | 全部指向**同一个** `ORDER_ARRIVAL` |
| `record_index` | 在父 `ORDER_ARRIVAL` 事务内按撮合顺序**严格递增** |
| `transaction_seq` | 全批共享父 `ORDER_ARRIVAL` 的事务序号 |
| `trade_id` | 各自唯一 |
| `taker_order_id` | 相同（同一张 taker 订单） |
| `maker_order_id` | 各不相同 |
| `batch_index` / `batch_size` | 本笔在该批中的序号（从 0）与该批总笔数 |

`batch_index` / `batch_size` 使重放器**无需推断**批的边界：`batch_index == batch_size − 1`
即本批最后一笔，其后紧跟该批的 `MARGIN_CALL`（若有）。仅凭 `caused_by_event_id`
相同也能分组，但那要求重放器先读完整批才知道边界，无法流式处理。

**`valuation_mark_before/after` 逐笔取值**：第 `k` 笔的 `before` 是第 `k−1` 笔成交
**之后**的盘口中间价，`after` 是本笔之后的。**不是整批共用一个 before/after**——
否则跨档成交的 `Impact` 会被错误地全部归给第一笔。

**这些是撮合循环内部的临时簿状态**，不是事务结束后的最终簿状态。批内最后一笔的
`valuation_mark_after` 才等于事务结束时的盘口中间价。重放器计算 PnL 桥接时逐笔使用
记录值即可；若要重建「事务后的簿」，应取批末值或随后的 `MARKET_DATA_PUBLISH`。

`risk_mark` 同理逐笔更新为该笔成交价；因此一次跨档成交会**依次**推进 `last`。

### 2.3 保证金判定在整批撮合之后

**所有 `TRADE_SETTLE` 全部生成并结算完毕后**，才执行账户合同 §4.1 的两阶段风险
检查，**不是每笔成交后各查一次**。

理由：跨档成交是一个原子的市场事件，中间态（吃到一半时的账户状态）不应触发强平。
若逐笔检查，同一张大单可能在自己造成的中间价位上触发他人强平，而那个价位从未作为
`last` 稳定存在过。

## 3. 订单类型与剩余处理

| 类型 | 可成交部分 | 剩余部分 |
|---|---|---|
| **限价单** | 按 §2 撮合 | **挂入订单簿**（GTC，挂到成交或被撤销为止） |
| **市价单** | 按 §2 撮合 | **立即撤销**（IOC，退化状态 §1.1） |
| **强平单** | 按 §2 撮合 | 立即撤销（IOC）；账户保持 `PENDING_LIQUIDATION`，由后续成交触发重评 |

限价单挂入簿时，其时间优先键为该 `ORDER_ARRIVAL` 的 `transaction_seq`——**不是**挂入时刻重新
分配的序号。这保证时间优先与到达顺序一致。

**限价单的价格必须已对齐 tick**（代理策略 §7），未对齐者在准入阶段即被拒绝，
不进入撮合。

## 4. 自成交阻止

撮合时若对手方 `maker_agent_id == taker_agent_id`，执行 **cancel-resting**：

```text
1. 撤销簿上那张 maker 订单（写入 ORDER_ARRIVAL，action=CANCEL，
   reject_reason=SELF_TRADE_PREVENTION）
2. taker 继续撮合下一档，不消耗数量
3. 若下一档仍是自己，重复
```

被撤销的挂单**释放其占用的保证金**（代理策略 §11.1 整体重算）。

选 cancel-resting 的理由见代理策略 §11.2：全撤重报机制下，簿上旧单已是过时意图。

## 5. 撮合与准入的顺序

```text
ORDER_ARRIVAL 事件内，顺序固定：
  1. 制度钩子校验（001 / D-1）——拒绝则记 accepted=false，结束
  2. tick / min_quantity 对齐检查（代理策略 §7）——不对齐则拒绝
  3. 初始保证金检查（账户合同 §3.3）——不足则拒绝
  4. 撮合（§2），逐档生成 TRADE_SETTLE
  5. 剩余部分按 §3 处理（挂单或撤销）
  6. 整批结算后执行两阶段风险检查（§2.3）
```

**保证金检查在撮合之前**，按订单**全部成交**的最坏情形计算（账户合同 §3.3）。
部分成交不会使已通过的检查失效——实际占用只会更少。

## 6. 空簿与单边簿

| 情形 | 行为 |
|---|---|
| 对手侧完全为空 | 限价单直接挂入；市价单全额撤销（IOC） |
| 对手侧不足以吃满 | 成交可成交部分，剩余按 §3 处理 |
| 两侧皆空 | `mid` 未定义，`valuation_mark` 退化为 `last`（指标字典 §3.1）；首笔成交前退化为 `initial_price` |

单边簿下 `book` 因子取满偏 ±1（代理策略 §3.1），这是**真实信息**而非缺失。

## 7. 确定性要求

给定相同的订单到达序列（含 `transaction_seq`），撮合结果必须逐笔一致：成交笔数、每笔的
`price_ticks` / `quantity_units` / `maker_order_id`、以及 `TRADE_SETTLE` 的 `record_index`
分配顺序。

**不得依赖**：浮点价格比较（价格是整数 tick，ADR-001）、集合遍历顺序、对象哈希。

## 8. 验收要点

以下须作为 0.1.1 的订单簿测试用例（与[验收向量](acceptance-vectors.md)的账户用例
互补）：

1. **价格优先**：买 101 与买 100 同时在簿，卖单到达先成交 101；
2. **时间优先**：同价两笔买单，先到（`transaction_seq` 小）者先成交；
3. **price improvement**：买单限价 101 吃到卖价 100，成交价为 **100**；
4. **跨三档**：一张买单吃掉卖 100 / 101 / 102 三档，产生 **3 个** `TRADE_SETTLE`，
   `caused_by_event_id` 相同、`record_index` 递增、`valuation_mark` 逐笔推进；
5. **限价剩余挂单**：吃完可成交部分后，剩余数量以原 `transaction_seq` 挂入簿；
6. **市价剩余撤销**：同上场景改为市价单，剩余全额撤销；
7. **自成交**：taker 遇到自己的挂单 → 该挂单被撤、taker 继续吃下一档；
8. **整批后判定**：跨档成交期间不触发强平，整批结算后才执行两阶段检查。
9. **同时间戳双订单黄金日志**：A 成交后耗尽保证金，B 随后到达并被拒；日志顺序为
   `A(record 0) → A 的事务记录(record 1..n) → B(record 0)`，所有 `log_key` 严格递增，
   在线状态与仅凭日志重放状态一致。
