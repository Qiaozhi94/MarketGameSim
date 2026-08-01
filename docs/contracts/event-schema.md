# 事件 Schema 与优先级类别

**适用范围**：跨规格实现合同（当前交付规格 v0.1）  
**状态**：Stable（跨规格实现合同；变更须记 ADR 并提升 `schema_version`）  
**创建日期**：2026-07-29　**更新日期**：2026-08-01  
**支撑需求**：v0.1 / FR-004、FR-008、FR-015、KR-001—KR-006；PRD / KPI-002、KPI-006  
**关联**：
[ADR-001](../adr/001-numeric-and-serialization-contract.md)、
[ADR-002](../adr/002-same-timestamp-event-scheduling.md)、
[指标字典](../product/metrics-dictionary.md)

## 1. 队列顺序与日志顺序

队列调度和事务日志解决的是两个不同问题，使用两把键：

```text
queue_key = (timestamp, priority_class, enqueue_seq)       # 只决定队列事件何时弹出
log_key   = (timestamp, transaction_seq, record_index)     # 决定日志、哈希与重放顺序
```

- `timestamp`：整数纳秒逻辑时间（KR-002），禁止浮点；
- `priority_class`：§3 冻结的队列调度类别；
- `enqueue_seq`：事件入队时分配的全局单调计数器，是 queue key 的最终裁决；
- `transaction_seq`：队列事件弹出时分配的全局单调事务序号；
- `record_index`：事务内记录序号，从 0 开始；父队列事件恒为 0，其事务记录从 1 递增。

**日志、摘要哈希、因果键比较和重放只使用 `log_key`。** `priority_class` 不参与日志
排序；否则第一张订单事务内产生的 class 1/2 记录会排到同时间戳下一张 class 0 订单
之后，与在线执行顺序相反。

订单簿的时间优先使用订单到达事务的 `transaction_seq`。同一时间戳、同为 class 0 的
订单按 `enqueue_seq` 弹出，因此其 `transaction_seq` 顺序与真实到达裁决一致。

### 1.1 队列事件产生规则（KR-006）

事务处理期间新入队的队列事件 `e'` 必须满足：

```text
queue_key(e') > queue_key(current_queue_event)
```

违反时内核立即抛出异常并终止运行，**不得静默重排**（ADR-002 §1）。

推论：新入队事件若回到更小的 class，`timestamp` 必须前进。因此 `AGENT_DECIDE`
产生的普通订单和 `MARGIN_CALL` 产生的强平订单都必须带非零延迟。事务记录不入队，
不适用 queue-key 回退规则；它们通过递增的 `record_index` 保证 log key 严格递增。

为此**禁止零通信延迟**：所有代理的 `latency_ns ≥ 1`（FR-013）。零值配置在校验阶段
拒绝，不静默替换为 1。纳秒粒度下 1 ns 已足以表达「几乎无延迟」，且零延迟无现实
对应。

### 1.2 回退 class 的队列跳转清单（穷举）

**每一个回退 class 的跳转都必须跨越至少 1 ns，且必须列在下表中。** 表外出现回退即为
实现缺陷或 schema 遗漏，不得临时加 1 ns 绕过。

| 跳转 | class | 跨越时间由谁承担 | 下限 |
|---|---|---|---|
| `AGENT_DECIDE` → `ORDER_ARRIVAL` | 4 → 0 | 代理通信延迟 `latency_ns` | ≥ 1 |
| `MARGIN_CALL` 事务记录 → `ORDER_ARRIVAL`（强平单） | 当前订单事务 → 0 | 风控下单延迟 `liquidation_latency_ns` | ≥ 1 |

第二行是 2026-08-01 检视补入的：强平单同样是 `ORDER_ARRIVAL`(class 0)，由
`MARGIN_CALL`(class 1) 产生，因此**也是回退**。此前文档称「`AGENT_DECIDE` →
`ORDER_ARRIVAL` 是唯一回退」，与 §4.2.2 的强平流程自相矛盾。

`liquidation_latency_ns` 不是权宜之计——交易所风控从判定到下单本就有延迟，且该延迟
是一个**有研究意义的参数**：风控反应越慢，连锁强平的价格滑落越深。它与 `grace_ns`
语义不同：`grace_ns` 是给账户补保证金的宽限窗口，`liquidation_latency_ns` 是宽限
结束后风控自身的下单耗时。

`TRADE_SETTLE` → `MARGIN_CALL` / `MARKET_DATA_PUBLISH` 都是同一父事务内的记录链，
靠 `record_index` 推进，不受 queue-key 规则约束。`AGENT_OBSERVE` → `AGENT_DECIDE`
是 class 3 → 4 的队列跳转，允许同时间戳、间隔为 0。观察与决策分为两个 class 是为了
让信息集独立记录（§3.1），不意味着两者必须在时间上分开。

### 1.3 第一版不含的生命周期事件

加密式制度为 24/7 连续交易，**没有开盘、收盘、隔夜与熔断**，因此第一版不需要
`SESSION_OPEN` / `SESSION_CLOSE` / `HALT` / `RESUME` / `SETTLEMENT_DUE` 事件。

股票式制度引入时，这些**队列事件**必须先补入本文的 class 清单并逐一验证 queue key。
若收盘事件自身执行风险扫描，`MARGIN_CALL` 仍只是该收盘事务内的记录；若另设待执行的
风险检查，则必须新增显式队列事件类型，不能把 `MARGIN_CALL` 记录重新塞回队列。在此
之前不得实现任何依赖时段状态的逻辑。

### 1.4 队列事件与事务记录（事件生命周期）

**并非所有事件都从队列弹出。** 事件分两类，这是消除「撮合何时改变账户」歧义的
唯一方式：

| 类别 | 事件 | 语义 |
|---|---|---|
| **队列事件** | `ORDER_ARRIVAL`(0)、`AGENT_OBSERVE`(3)、`AGENT_DECIDE`(4)、`SNAPSHOT`(5) | 入队；弹出时**执行一个原子事务**，事务内可改变状态 |
| **事务记录** | `ORDER_CANCELLED`(0)、`TRADE_SETTLE`(1)、`MARGIN_CALL`(1)、`MARKET_DATA_PUBLISH`(2) | **不入队**；在某个队列事件的事务内生成 |

事务记录的 class 只是阶段标签，**不参与任何排序**（§3.1）——`ORDER_CANCELLED` 的
class 0 与父 `ORDER_ARRIVAL` 相同，不意味着它会排到成交之前。

**记录的写入时点：事务提交时一次性写出，不是逐条即时写。父记录 `r0` 也不例外。**

撮合循环逐档进行，第一笔成交发生时还不知道本次撮合总共会有几笔（取决于簿深度、
是否遇到自成交、taker 剩余量）。而 `TRADE_SETTLE.fill_count` 要求第一笔就携带总数
（撮合合同 §2.2），因此**记录必须在事务内缓冲、撮合结束后统一填入 `fill_count`
并按 `record_index` 顺序一次性写出**。

缓冲不影响任何其他语义：账户在撮合循环中**逐笔立即更新**（本节「为什么必须这样分」
要解决的问题依旧成立），只是**日志写出**延后到事务末尾。

由此得到一条日志不变式，验证器可以无条件依赖：

> **日志中的每个事务要么完整存在，要么完全不存在。** 不存在只写了 `r0`、
> 或成交写了一半的事务。

`r0` 一并缓冲正是为了这条不变式。若 `r0` 在事务开始时就写出，异常终止时日志里会留下
一个没有任何后续记录的孤儿父记录，重放器无法区分它是「被拒的订单」还是「崩在半路的
事务」——两者的 `record_index` 序列完全相同。

**缓冲不是 dry-run。** 撮合只执行一遍：每一档撮合完成即更新账户、扣费、处理自成交
撤单，同时把对应记录**追加进事务缓冲区**（此时 `fill_count` 字段留空）。撮合循环
结束后回填全部 `TRADE_SETTLE.fill_count`，再按 `record_index` 顺序一次性写出。
「先在不可变簿快照上 dry-run 一遍**以确定日志内容**，再正式执行一遍」的方案被
排除——两遍执行必须产生完全一致的结果，而这个一致性本身需要额外的验证手段，
成本高于缓冲。

这与**准入阶段**的预撮合无关：代理策略 §11.1 为计算 `reserved_units` 需要在不可变
簿快照上预撮合，那发生在撮合**之前**、不产生任何记录，且其与正式撮合的一致性另有
断言（0.1.2 T102）。两者不要混为一谈。

`fill_index` 在成交发生时即可确定（就是缓冲区内的成交计数），只有 `fill_count`
需要回填。`ORDER_CANCELLED` 与 `MARGIN_CALL` 不参与 `fill_index` 计数。

若实现选择即时写出，则必须改用可流式表达的 `is_last_fill` 而非 `fill_count`——
本文选择前者，因为 `fill_count` 让重放器能预先分配容量、并在读到第一笔时即校验完整性。

队列事件弹出时先**分配**（不是写出）`record_index=0` 的父记录；事务内记录共享该父
事件的 `transaction_seq`，按实际发生顺序分配 `record_index=1,2,...`。它们不会被再次
弹出执行，记录的是已经发生的状态变化，而非待执行的指令。

#### 事务内记录顺序（冻结）

一个 `ORDER_ARRIVAL` 事务的记录顺序恒为：

```text
r0            ORDER_ARRIVAL              父记录（含 accepted / reject_reason）
r1 .. rp      撮合过程记录                TRADE_SETTLE 与 ORDER_CANCELLED
                                          按撮合循环中的实际发生顺序交错
r(p+1) .. rq  MARGIN_CALL × m (m ≥ 0)     整批结算后一轮风险扫描，按 agent_id 升序
r(q+1)        MARKET_DATA_PUBLISH         仅当本事务改变了盘口
```

三条推论，都是验收断言：

1. **`MARKET_DATA_PUBLISH` 恒为事务的最后一条记录**——它发布的是本事务全部状态变化
   （含强平判定）之后的盘口。若排在 `MARGIN_CALL` 之前，代理会看到尚未反映强平后果的簿；
2. **`accepted = false` 的事务只有 `r0`**。准入被拒不改变簿，因此既无成交记录也无
   行情发布；
3. **不改变盘口的成功事务不写 `MARKET_DATA_PUBLISH`**（例如撤销一张不在最优档、
   且不影响 k 档深度的挂单）。判定依据是 §4.3 声明的全部字段是否发生变化，
   不是「是否有成交」。

#### 为什么必须这样分

若 `TRADE_SETTLE` 入队、且账户在它弹出时才更新，则同一时间戳内会出现：

```text
ORDER_ARRIVAL A（class 0）→ 撮合成功，TRADE_SETTLE A 入队（class 1，未处理）
ORDER_ARRIVAL B（class 0）→ ★ 用【尚未结算 A】的旧钱包做保证金准入
TRADE_SETTLE A（class 1）→ 此时才更新账户
```

因为同时间戳内 class 0 全部排在 class 1 之前，★ 处会放行一张本该被拒的订单——
同一笔保证金被用了两次。

反过来，若在 `ORDER_ARRIVAL` 内直接改账户、`TRADE_SETTLE` 仍作为队列事件，那它弹出
时无事可做，「事件是原子状态转移」的定义即被架空。

**本文选择前者的修正版**：账户在 `ORDER_ARRIVAL` 事务内更新，`TRADE_SETTLE` 明确
降级为事务记录。这既保证了同时间戳的后续订单看到最新账户，又不让记录承担它无法承担
的执行语义。

#### 「原子事务」指哪一种原子性

数据库语境下「原子事务」通常同时含两层意思，本合同**只要求第一层**：

| 层 | 含义 | 本合同 |
|---|---|---|
| **可见性原子性** | 任何其他事务都观察不到本事务的中间态 | **要求**。单线程顺序执行天然成立——事务执行期间没有任何其他事务在跑 |
| **失败原子性** | 事务失败时全部状态变更回滚 | **不要求**。见 §1.5 |

此前文档只写「原子事务」，读者会默认包含第二层。**不包含。** 撮合循环中的账户与簿
变更是**原地生效、不可回滚**的。

### 1.5 失败语义：fail-stop，不回滚

**内核在事务执行中抛出的任何异常都是实现缺陷或配置错误，不存在可恢复的异常类。**
KR-006 单调性违反、C1/C2 失衡、状态机非法转移、回退跳转白名单外的跳转——每一条都
意味着代码是错的，而不是市场出现了某种需要处理的情况。

因此语义固定为 **fail-stop**：

1. **整个运行立即终止**。不回滚、不重试、不跳过该事务、不继续处理队列；
2. **该事务的缓冲区整体丢弃**，日志中不出现它的任何记录（含 `r0`）；
3. 尽力写出 `RUN_TRAILER`（`terminated = ABORTED` + 稳定 `abort_code`，§6.2）；
4. 该运行判 **TI-4**（退化状态 §技术无效），**不得**进入摘要哈希比较、重放、
   统计分析或任何实验结论；
5. **禁止从中断点恢复或续跑。** 修复缺陷后必须以同一配置与种子完整重跑。

**TI-4 与 TI-5 互斥，按尾部记录判别**：

| 情形 | 尾部 | 判据 |
|---|---|---|
| 正常结束 | `terminated = COMPLETED` | 有效运行 |
| 内核 fail-stop | `terminated = ABORTED` | **TI-4**——内核**知道**自己出了问题并留下了 `abort_code` |
| 尾部缺失或被截断 | 无 `RUN_TRAILER`，或 `record_count` 与实际行数不符 | **TI-5**——内核**没来得及知道**（进程被杀、磁盘写满、断电） |

两者都**整份拒绝**，但诊断码不同：TI-4 指向内核缺陷，可由 `abort_code` 直接定位；
TI-5 指向环境问题，须查系统日志而非代码。混为一谈会让排查方向从一开始就错。

**验证器的对应义务**：`verify` 遇到上述任一情形都必须**拒绝整份日志**，不得
「尽力而为地校验前半段」。半截运行的部分校验通过没有任何证据价值。

#### 为什么不做回滚

回滚需要为账户、订单簿、`reserved` 与待入队事件维护 undo log 或每事务写时复制。
代价是**每个事件都要付的分配开销**，而 KPI-004 的 10 秒门槛正是按事件吞吐量定的。

买到的是什么？是「内核已经证明自己有 bug，但运行继续，并产出结果」。这比中止更糟：
带缺陷的运行会生成看似正常的日志与统计，而缺陷发生在哪个事务已被回滚抹掉。

**研究工具的正确失败方式是大声地停下，不是安静地续跑。**

### 1.6 对日志自包含性的影响：无

事务记录携带完整的 `postings`（`*_delta` 与 `*_after`，§4.2.1），重放器按 log key 逐条
应用即可重建账户终态，**不需要知道它们是否曾经入队**。SC-006 的要求不受影响。

缓冲写出同样不影响自包含性——它改变的只是记录**何时**落盘，不改变记录内容。

## 2. 冻结约束

**queue key、log key 与 `priority_class` 的取值和语义一经冻结不得静默变更。**

变更将使历史实验的事件摘要哈希（KPI-002）不可比。如需变更，按宪章治理条款记录
ADR、提升 schema 版本号，并显式声明受影响的既有实验。

事件日志顶层必须携带 `schema_version` 字段。

**当前 `schema_version = 2`。** 版本 2 将原单一 `(timestamp, priority_class, seq)`
替换为 queue/log 双键，并把 class 1—2 明确为事务记录。2026-07-31 的方向重置新增了
`MARGIN_CALL`（§4.2.2）与杠杆相关字段；2026-08-01 关闭 P0-K01/K03 时新增
`ORDER_CANCELLED`（§4.7）、冻结了事务内记录顺序（§1.4）并改写 E-002 为按事件类型的
封闭清单。这些变更**均未提升版本号**——至今没有任何实验运行过，不存在可比性问题。

**首次正式运行之后，任何字段、class 或哈希字段集合的变更都必须提升版本号。**
「首次正式运行」指第一次产出被 `docs/experiments/` 引用的事件日志。

## 3. 优先级类别（冻结清单）

数值越小越先处理。

| class | 名称 | 含义 |
|---|---|---|
| 0 | `ORDER_ARRIVAL` | 订单或撤单**指令**到达交易所，触发准入校验与撮合 |
| 0 | `ORDER_CANCELLED` | 撤单**结果**：簿上订单被移除（§4.7）；事务记录，不入队 |
| 1 | `TRADE_SETTLE` | 成交结算，账户钱包/仓位/开仓成本/费用更新 |
| 1 | `MARGIN_CALL` | 保证金判定与强平触发；同 class 内排在结算之后（§4.2.2） |
| 2 | `MARKET_DATA_PUBLISH` | 行情发布（成交与盘口变化对外可见） |
| 3 | `AGENT_OBSERVE` | 代理接收行情，其信息集在此刻确定 |
| 4 | `AGENT_DECIDE` | 代理决策，产生新的订单意图 |
| 5 | `SNAPSHOT` | 周期性账户与订单簿快照，纯记录，不改变状态 |

### 3.1 调度与事务记录顺序

class 0/3/4/5 决定**队列事件**在同一时间戳的弹出顺序。class 1—2 对事务记录仅保留
阶段标签语义，不参与跨事务日志排序；事务记录由父事务的 `record_index` 排序。
`AGENT_OBSERVE` 弹出时读取的必然是此前全部已提交事务后的状态，不会看到撮合中间态。

**观察（3）与决策（4）分离为两个类别**，而非合并。理由是 KPI-006 要求任一成交可
追溯至「当时的信息集」——分离后信息集在 `AGENT_OBSERVE` 事件中被独立记录，与决策
逻辑解耦，追溯链无需从决策结果反推输入。

**快照（5）最后。** 快照必须记录该时间戳上所有实质状态转移完成后的状态，否则
快照序列与事件序列会不一致。

## 4. 事件类型与必备字段

所有日志记录共有：`schema_version`、`event_id`、`timestamp`、`transaction_seq`、
`record_index`、`priority_class`、`event_type`、`run_id`。队列事件另有 `enqueue_seq`；
事务记录通过父事件或因果外键定位其事务，不单独入队。

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
| `fill_index` / `fill_count` | 本笔在该次撮合中的序号（从 0）与该次撮合的总成交笔数（撮合合同 §2.2） |
| `postings` | **账户分录**，长度恒为 2（maker 与 taker 各一条），见 §4.2.1 |

**两个 mark 都必须记录**：`risk_mark` 决定强平判定，`valuation_mark` 决定权益与
会计桥接（指标字典 §3.1、§5.2）。缺任一个，PnL 桥接都无法仅凭日志重放。

#### 4.2.1 成交分录 `postings`（`TRADE_POSTING`）

每条分录记录该成交对**一个代理**账户的完整影响，全部为最小单位整数。
`MARGIN_CALL` 携带的是另一种分录（`WRITE_OFF_POSTING`，§4.2.3），两者由
`posting_type` 判别，字段集合不同——**不要把本表当作通用分录表**。

| 字段 | 说明 |
|---|---|
| `posting_type` | 恒为 `"TRADE_POSTING"`（判别标签） |
| `agent_id` | 该分录所属代理，**恒非 null** |
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
| `caused_by_event_id` | **本事务的父 `ORDER_ARRIVAL`**（因果外键） |
| `risk_mark_event_id` | 确立本次判定所用 `risk_mark` 的那笔成交 = **本批最后一笔 `TRADE_SETTLE`**（因果外键） |
| `margin_ratio_bp` | 判定时的保证金率（整数万分数，账户合同 §3.2） |
| `maintenance_bp` | 当时生效的维持保证金率 |
| `verdict` | `OK` \| `PENDING_LIQUIDATION` \| `LIQUIDATING` \| `BREACHED`（穿仓） |
| `required_quantity_units` | 恢复至 `target_bp` 所需的最小平仓数量（账户合同 §4.2）；`OK` 时为 0 |
| `chain_depth` | 该判定所处的连锁层数，0 表示非连锁触发（指标字典 §4.1） |
| `postings` | `WRITE_OFF_POSTING[]`：**仅 `verdict = BREACHED` 时**长度为 2（`[ACCOUNT, EXCHANGE_RISK]`），否则为空数组 `[]`。字段表见 §4.2.3 |

**为什么因果父是 `ORDER_ARRIVAL` 而不是某笔 `TRADE_SETTLE`**：跨档成交产生多笔
`TRADE_SETTLE`，而风险扫描在**整批之后只做一次**（§4.2.2 扫描范围）。此时「导致该
判定的成交」没有唯一答案，且扫描覆盖**全部非零仓位账户**——绝大多数被判定的账户
根本没参与本次成交，对它们而言不存在任何「自己的那笔成交」。指向 `ORDER_ARRIVAL`
则恒唯一：**是这一张订单的到达触发了这一轮扫描**。

`risk_mark_event_id` 单独承载「判定用的价格从哪来」：批末扫描使用的 `risk_mark` 是
本批**最后一笔** `TRADE_SETTLE` 的成交价，因此该外键恒指向那一笔。两个外键分工明确：
一个回答「谁触发了扫描」，一个回答「按哪个价格判的」。

**v0.1 中 `risk_mark_event_id` 恒非 null**——只有成交能改变 `risk_mark`
（代理策略 §3.3），因此不含成交的事务不触发扫描，也就不产生 `MARGIN_CALL`。
字段声明为可空是为将来的非成交触发场景（如按时间的资金费结算）预留，
**在 v0.1 中出现 null 即为实现缺陷**。

#### 4.2.3 穿仓核销分录（`WRITE_OFF_POSTING`）

`verdict = BREACHED` 的 `MARGIN_CALL` 是**穿仓核销的唯一事件载体**。它携带两条分录，
使核销可仅凭日志重放，不依赖对「最后一笔强平成交」的推断。

**核销分录是独立的记录类型，不是成交分录（§4.2.1 的 `TRADE_POSTING`）的特例。**
两者构成一个**判别联合**，由 `posting_type` 区分：

| 载体 | `posting_type` | `role` 值域 | 长度 |
|---|---|---|---|
| `TRADE_SETTLE.postings` | `TRADE_POSTING` | `MAKER` \| `TAKER` | 恒为 2，顺序 `[MAKER, TAKER]` |
| `MARGIN_CALL.postings` | `WRITE_OFF_POSTING` | `ACCOUNT` \| `EXCHANGE_RISK` | `BREACHED` 时为 2，顺序 `[ACCOUNT, EXCHANGE_RISK]`；否则为空数组 `[]` |

**为什么不复用同一张宽表**：核销分录的两侧都不是 maker/taker，`role` 没有合法取值；
交易所风险账户没有钱包、仓位与保证金率，用 `0` 填充会与 §4.2.1「无仓位时
`margin_ratio_after_bp` 为 null」直接冲突，而 `role`、`agent_id` 这类非数值字段
根本无法用 `0` 填充。「其余写 0」不是一份可实现的合同——字段注册表（E-002 同步强制）
无法据此确定类型与空值规则。

`WRITE_OFF_POSTING` 的**完整字段表**（共 7 项，无其他字段）：

| 字段 | `role = ACCOUNT` | `role = EXCHANGE_RISK` |
|---|---|---|
| `posting_type` | `"WRITE_OFF_POSTING"` | `"WRITE_OFF_POSTING"` |
| `role` | `"ACCOUNT"` | `"EXCHANGE_RISK"` |
| `agent_id` | 该穿仓账户 | **`null`**（交易所账户无 `agent_id`） |
| `wallet_delta_units` | `−wallet_before`（**正值**，把负钱包补到 0） | `0` |
| `wallet_after_units` | `0` | **`null`**（交易所风险账户不持有钱包） |
| `position_after_units` | `0` | **`null`** |
| `entry_notional_after_units` | `0` | **`null`** |
| `risk_pnl_delta_units` | `0` | `wallet_before`（**负值**） |

`null` 与 `0` 的区别在这里是实质性的：`0` 表示「该量存在且为零」，`null` 表示
「该量对本载体不存在」。交易所风险账户没有仓位这一概念，写 `0` 会让重放器把它当作
一个持仓归零的普通账户纳入 C1 求和。

两条分录的 `wallet_delta_units` 与 `risk_pnl_delta_units` 大小相等、符号相反，
C2 守恒（账户合同 §5）。

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

同一轮扫描产生多个 `MARGIN_CALL` 时，按 **`agent_id` 升序**产生事件——这是确定性
要求，不是效率考虑：顺序影响 **`record_index` 分配**，进而影响 KPI-002 的哈希。
（`transaction_seq` 在同一父事务内恒定不变，不受此影响。）

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
（v0.1 / D-7）。快照是状态观测而非状态转移，**不携带因果外键，也不承担账户追溯**
——账户追溯由 §4.2.1 的分录承担。快照的作用是回放与图表，以及与分录累加值的
交叉核对（两者不一致即为实现缺陷）。

### 4.7 ORDER_CANCELLED（class 0，事务记录）

**撤单结果**，与作为队列事件的撤单指令严格区分。两者是不同的事件类型，不是同一
类型的两种用法：

| 概念 | `event_type` | 类型 | 来源 |
|---|---|---|---|
| 撤单**指令** | `ORDER_ARRIVAL`（`action=CANCEL`） | **队列事件** | 代理主动提交，可能被拒（订单已成交/不存在） |
| 撤单**结果** | `ORDER_CANCELLED` | **事务记录** | IOC 剩余撤销、自成交阻止、强平前的清理 |

代理主动撤单时**两条记录都产生**：`ORDER_ARRIVAL(action=CANCEL)` 作为 `r0`，
撤单成功则事务内再写一条 `ORDER_CANCELLED`（`reason = AGENT_REQUEST`）。指令被拒时
只有 `r0`（`accepted=false`）。这样「簿上少了一张单」永远由 `ORDER_CANCELLED`
唯一表达，重放器不必区分撤销的来源。

字段：

| 字段 | 说明 |
|---|---|
| `order_id` | 被撤销的订单 |
| `agent_id` | 该订单所属代理 |
| `cancelled_qty_units` | 被撤销的剩余数量（整数） |
| `price_ticks` | 被撤销订单的挂单价；市价单剩余撤销时为 null |
| `side` | 被撤销订单的方向 |
| `reason` | `AGENT_REQUEST` \| `IOC_REMAINDER` \| `SELF_TRADE_PREVENTION` \| `LIQUIDATED_ACCOUNT` |
| `caused_by_event_id` | 触发本次撤销的队列事件（因果外键） |
| `reserved_delta_units` | 释放的保证金占用，恒 ≤ 0（代理策略 §11.1 整体重算之差） |

**不新增 `RESTED` 记录**：限价单剩余挂入簿**不产生记录**——它由父 `ORDER_ARRIVAL`
（含原始数量与限价）、本次事务的全部 `TRADE_SETTLE`（含成交数量）与事务末尾的
`MARKET_DATA_PUBLISH`（含新盘口）共同表达：

```text
挂入量 = ORDER_ARRIVAL.quantity_units − Σ TRADE_SETTLE.quantity_units
        − Σ ORDER_CANCELLED.cancelled_qty_units（同一 order_id）
挂入价 = ORDER_ARRIVAL.price_ticks
```

重放器据此可完整重建簿。为一个可推导的状态新增记录类型，只会增加 schema 面积与
哈希字段集合，且**挂入不是状态变化的原因，而是订单未被消耗的默认归宿**——撤销
则相反，它是一次主动的状态变化，因此必须留痕。

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
- 每一跳的目标事件必须在日志中**唯一存在**，且其 `log_key` **严格小于**引用方；
- 断链、悬空引用或多重匹配即判定该运行不合格；
- **账户侧**：每笔成交的 `postings` 恰为 2 条且 `agent_id` 与 `maker/taker_agent_id`
  一致；分录的 `*_after_units` 等于该代理上一条分录的 `*_after_units` 加本次
  `*_delta_units`（首次以初始值为基），且与同代理最近一次 `ACCOUNT` 快照一致；
- **`MARGIN_CALL` 侧**（0.1.2 起）：`caused_by_event_id` 指向的 `ORDER_ARRIVAL`
  与本判定同属一个 `transaction_seq`；`risk_mark_event_id` 指向的 `TRADE_SETTLE`
  是该事务内 `record_index` **最大**的一笔成交；判定使用的价格与该笔的
  `risk_mark_ticks` 相等；
- **事务完整性**（§1.5）：每个 `transaction_seq` 必须以 `record_index=0` 起始且
  中间无空洞；`RUN_TRAILER.last_committed_transaction_seq` 必须等于日志中出现过的
  最大 `transaction_seq`；
- **终止判别**（§1.5）：`terminated = ABORTED` → 判 **TI-4** 并整份拒绝；
  缺少 `RUN_TRAILER` 或 `record_count` 与实际行数不符 → 判 **TI-5** 并整份拒绝。
  两种情形都不做部分校验。

该断言不依赖重放，因而不随代码版本失效——这是 KPI-006 从「展示层可读」升级为
「可机器验证」的关键。

## 6. 运行元数据

日志文件由**三种判别记录**构成，由顶层字段 `record_kind` 区分：

```text
RUN_HEADER          恰好一条，文件第一行
EVENT*              零条或多条，§4 的事件记录
RUN_TRAILER         至多一条，文件最后一行
```

`record_kind` 是所有记录的必备字段，取值 `RUN_HEADER | EVENT | RUN_TRAILER`。
三者都受 §9 规范序列化约束，都进入 T204f 的字段注册表；**只有 `EVENT` 记录参与
§7 的摘要哈希**——头尾携带 `run_id`、墙钟时间等按 E-002 恒排除的内容。

### 6.1 RUN_HEADER

`run_id`、代码版本、配置哈希、`master_seed`、开始时间（墙钟）、`schema_version`，
以及数值单位定义 `tick_size`、`min_quantity`、`cash_unit`（ADR-001 §7、PR-012）。

### 6.2 RUN_TRAILER

**完成状态写在尾部，不在头部**——头部在运行开始时写出，那时还不知道结局；更关键的
是进程被杀或磁盘写满时头部**已经写好**，日志看起来完全正常。

| 字段 | 类型 | 说明 |
|---|---|---|
| `record_kind` | 枚举 | 恒为 `"RUN_TRAILER"` |
| `terminated` | 枚举 | `COMPLETED` \| `ABORTED` |
| `abort_code` | 枚举 \| null | `terminated = COMPLETED` 时**恒为 `null`**；`ABORTED` 时取下表**稳定错误码** |
| `abort_detail` | 字符串 \| null | 诊断文本，**不参与任何判定、不入哈希、不得被程序解析**；`COMPLETED` 时为 `null` |
| `last_committed_transaction_seq` | 整数 \| null | 最后一个**已提交**事务的序号。失败事务的序号已被丢弃，**不出现在此**；无任何已提交事务时为 `null` |
| `record_count` | 整数 | 已写出记录总数，**含头尾两条**。用于检出「尾部之前被截断」 |

**稳定错误码**（枚举，新增须提升 `schema_version`）：

| `abort_code` | 触发条件 |
|---|---|
| `QUEUE_KEY_MONOTONICITY` | KR-006 违反（§1.1） |
| `CLASS_REGRESSION_NOT_WHITELISTED` | 回退跳转不在 §1.2 白名单内 |
| `CONSERVATION_BREACH` | C1 / C2 在某事件后不成立 |
| `ILLEGAL_STATE_TRANSITION` | 账户状态机非法转移 |
| `CONFIG_INVARIANT` | 配置校验在运行期被违反 |
| `INTERNAL` | 上述之外的内核异常 |

错误码与诊断文本分离是刻意的：`abort_detail` 含异常消息与栈，**内容随 Python 版本
与平台变化**，若参与判定会使排除规则不可复现。判定一律只看 `abort_code`。

**`last_committed_transaction_seq` 指已提交事务**：fail-stop 丢弃失败事务的全部记录
（§1.5），因此该序号必然等于日志中出现过的最大 `transaction_seq`。若两者不等，
说明写出逻辑有缺陷，验证器须报错。

## 7. 事件摘要哈希（KPI-002）

对事件序列按 `log_key` 逐个计算滚动哈希，输入为各事件的**语义字段**——
字段集合由 **E-002 的封闭清单**逐条声明，并随 schema 版本管理。

**只对正常结束的运行计算哈希。** `terminated: ABORTED` 或缺少尾部记录的日志不参与
KPI-002 比较（§1.5）——半截运行之间哈希相同不构成确定性证据。

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
日志体积是可接受的代价（须在 0.1.2 首次运行前实测确认）。

### E-002：参与摘要哈希的字段

**这是一份封闭清单**：下表未列出的字段一律不参与哈希。表按事件类型逐条给出，
不使用「以及各类型的语义字段」这类开放表述——开放表述会让新增字段默默落在清单外，
而 KPI-002 恰恰无法检出「本该被覆盖却没被覆盖」的字段。

**全部记录共有**：`schema_version`、`timestamp`、`transaction_seq`、`record_index`、
`priority_class`、`event_type`。**队列事件另有 `enqueue_seq`，同样纳入。**

`schema_version` 纳入是刻意的：schema 变更本就使历史哈希不可比（§2），让哈希自己
反映这一点，比依赖人工核对元数据头部可靠。`enqueue_seq` 纳入是因为它是同时间戳同
class 的**最终定序裁决**——两张订单谁先到是外部可观察的市场事实，不是实现细节。

| 事件类型 | 纳入哈希的字段 |
|---|---|
| `ORDER_ARRIVAL` | `agent_id`、`order_id`、`action`、`target_order_id`、`side`、`order_type`、`price_ticks`、`quantity_units`、`accepted`、`reject_reason`、`reserved_delta_units`、`origin`、`trigger_ratio_bp` |
| `ORDER_CANCELLED` | `order_id`、`agent_id`、`cancelled_qty_units`、`price_ticks`、`side`、`reason`、`reserved_delta_units` |
| `TRADE_SETTLE` | `maker_order_id`、`taker_order_id`、`maker_agent_id`、`taker_agent_id`、`price_ticks`、`quantity_units`、`notional_cash_units`、`maker_fee_cash_units`、`taker_fee_cash_units`、`valuation_mark_before_half_ticks`、`valuation_mark_after_half_ticks`、`risk_mark_ticks`、`fill_index`、`fill_count`、`postings[]`（叶字段见下表 A） |
| `MARGIN_CALL` | `agent_id`、`margin_ratio_bp`、`maintenance_bp`、`verdict`、`required_quantity_units`、`chain_depth`、`postings[]`（叶字段见下表 B） |
| `MARKET_DATA_PUBLISH` | `best_bid`、`best_ask`、`bid_depth_k`、`ask_depth_k`、`last` |
| `AGENT_OBSERVE` | `agent_id`、`observed_at` |
| `AGENT_DECIDE` | `agent_id`、`rule_id`、`intents[]` 的 `action`/`side`/`order_type`/`price_ticks`/`quantity_units`（**不含 `intent_id`**） |
| `SNAPSHOT` | `snapshot_type`、`payload` |

#### postings 叶字段（封闭）

`postings` 是嵌套数组，「全部字段」不是封闭表述——**必须逐叶列出**。两种载体是
**判别联合的两个变体**（§4.2.3），字段集合不同，不可互相套用。

**表 A：`TRADE_SETTLE.postings[]` = `TRADE_POSTING`**（长度恒为 2）

数组顺序**固定为 `[MAKER, TAKER]`**，不按 `agent_id` 排。自成交已被阻止（撮合 §4），
不存在两条分录同属一个代理的情形。

叶字段（15 项）：`posting_type`、`agent_id`、`role`、`wallet_delta_units`、
`position_delta_units`、`entry_notional_delta_units`、`realized_pnl_delta_units`、
`fee_delta_units`、`reserved_delta_units`、`wallet_after_units`、
`position_after_units`、`entry_notional_after_units`、`equity_after_units`、
`margin_ratio_after_bp`、`risk_pnl_delta_units`。**全部纳入。**

**表 B：`MARGIN_CALL.postings[]` = `WRITE_OFF_POSTING`**（`BREACHED` 时长度为 2，
否则为空数组 `[]`）

数组顺序**固定为 `[ACCOUNT, EXCHANGE_RISK]`**。交易所侧的 `agent_id` 为 `null`，
无法参与按 `agent_id` 的排序，因此顺序必须由角色而非标识决定。

叶字段（7 项）：`posting_type`、`role`、`agent_id`、`wallet_delta_units`、
`wallet_after_units`、`position_after_units`、`entry_notional_after_units`、
`risk_pnl_delta_units`。**全部纳入。** 各字段在两种 `role` 下的取值与可空性见
§4.2.3——`EXCHANGE_RISK` 侧的 `wallet_after_units` 等为 `null` 而非 `0`。

**表 B 不是表 A 的子集**：它少了 `position_delta_units`、`fee_delta_units`、
`equity_after_units`、`margin_ratio_after_bp` 等成交特有字段，多了不同的 `role` 值域。
注册表必须把它们声明为两个独立的结构，而不是同一结构的可选字段。

空数组与非空数组必须产生不同的哈希输入，不得把空 `postings` 视为字段缺失。

`postings` 全字段入哈希是关键修正：此前只有成交价量入哈希，若分组、
`entry_notional` 归属或 mark 口径写错而成交价量恰好相同，KPI-002 仍会报「确定性
通过」——账本错误因此对确定性断言完全不可见。同理，`fill_index`/`fill_count` 与
两个 mark 都是验收裁判（订单簿向量 §3），必须入哈希。

**排除**：`event_id`、`run_id`、`trade_id`、墙钟时间、`information_set`、
`internal_state`、`submitted_at`，以及全部指向事件的因果外键——
`observation_event_id`、`decision_event_id`、`intent_id`、`caused_by_event_id`、
`market_data_event_id`、`risk_mark_event_id`（ADR-002 §6）。它们与 `event_id` 同属
实现标识，其生成方式属实现细节；引用完整性由 §5.2 的独立断言保证，不需要哈希参与。

排除 `internal_state` 与 `information_set` 是关键选择：哈希应捕捉**市场结果的
确定性**，而非代理实现的内部细节。若纳入，一次不改变任何行为的内部状态表示重构
就会使哈希变化，KPI-002 将频繁误报，最终导致该断言被忽视。`AGENT_OBSERVE` 因此
只剩 `agent_id` 与 `observed_at` 入哈希——它观察到了什么由行情发布记录承载，
无需重复。

#### 同步强制：单一字段注册表

本表、序列化模型与覆盖检查是**三份清单描述同一件事**，手工维护必然漂移。因此实现
必须建立**唯一的机器可读字段注册表**，三者全部由它生成：

```text
src/market_game_sim/schema/registry.py     ← 唯一真源（纯标准库，KR-005）
  ├→ 序列化模型：每个事件类型的必备字段与顺序
  ├→ E-002 投影：哈希输入的字段选择
  └→ T206b 覆盖检查：纳入 ∪ 排除 是否恰好覆盖必备字段集合
```

注册表为每个字段声明四项：所属事件类型、是否必备、`HASH_INCLUDE | HASH_EXCLUDE`、
嵌套路径（`postings[].wallet_delta_units` 这类叶字段写全路径）。

**覆盖检查的判据**：对每个事件类型，`必备字段集合 == 纳入集合 ∪ 排除集合` 且两集合
不相交。任一字段既不在纳入也不在排除侧即测试失败。**默认落入哪一侧都是错的**——
新增字段时遗漏分类必须显式暴露，而不是安静地逃出 KPI-002 或安静地使哈希频繁误报。

本节文字与注册表冲突时，**以本节为准**，并按 §2 判断是否需要提升 `schema_version`。

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
