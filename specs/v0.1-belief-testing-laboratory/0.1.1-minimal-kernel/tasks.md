# 0.1.1：最小确定性内核（无杠杆） · 任务拆解

**对应里程碑**：[`spec.md`](spec.md)  
**状态**：Ready（P0-I01/I02、P0-K01—K03 均已于 2026-08-01 关闭）

## 约定

- 每个任务标注 `[合同引用]`——实现前先读该节，实现后对照验收；
- **测试先行**：带 `[TDD]` 的任务，先写失败的测试再写实现；
- 任务顺序即依赖顺序，同一 Phase 内可并行的标 `[P]`；
- **任务编号只在本文件内唯一**。引用其他里程碑的任务时必须带里程碑前缀
  （写 `0.1.2 T104`，不写 `T104`）——各里程碑都有 `T1xx`—`T6xx`，裸编号会指向错误任务。

---

## Phase 1：数值与配置基础

- [ ] **T101** `[ADR-001 §1]` 定义整数值对象：`Price`、`Quantity`、`Cash`、`Bp`、
      `Nanos`。全部不可变，禁止浮点构造。
- [ ] **T102** `[ADR-001 §2]` `[TDD]` 配置解析：YAML 领域量必须为**字符串**，
      经 `Decimal` 转最小单位整数。**收到 float 即报错**，不接受先转 str 的补救。
- [ ] **T103** `[ADR-001 §2]` `[TDD]` 配置校验：
      `tick_size × min_quantity` 是 `cash_unit` 的整数倍；
      `latency_ns ≥ 1`（KR-006）；`leverage_tier_distribution` 各档之和 = 10000。
- [ ] **T104** `[ADR-001 §7]` `[TDD]` 规范序列化：整数字面量、缺失值 `null`、
      UTF-8/NFC、`ensure_ascii=false`、`separators=(",",":")`、键按码位升序、
      每事件一个 LF。**断言两次序列化逐字节相同**。

## Phase 2：事件内核

- [ ] **T201** `[事件 Schema §1]` 实现双键：队列事件使用
      `(timestamp, priority_class, enqueue_seq)`，日志记录使用
      `(timestamp, transaction_seq, record_index)`；三个计数器的作用域与分配时点不得混用。
- [ ] **T202** `[事件 Schema §1.1]` `[TDD]` **KR-006 单调性断言**：入队时校验
      `queue_key(新事件) > queue_key(当前队列事件)`，违反则抛异常终止，**不得静默重排**。
- [ ] **T203** `[事件 Schema §1.2]` `[TDD]` 回退跳转白名单：只有
      `AGENT_DECIDE→ORDER_ARRIVAL` 与 `MARGIN_CALL→ORDER_ARRIVAL` 可回退 class，
      且必须跨越 ≥ 1 ns。表外回退即缺陷。
- [ ] **T204** `[事件 Schema §3]` 优先级类别枚举（含 `MARGIN_CALL` 同为 class 1、
      `ORDER_CANCELLED` 同为 class 0）。
- [ ] **T204b** `[事件 Schema §1.4]` `[订单簿向量 OB-9a]` `[TDD]` **队列事件 vs
      事务记录**：只有 `ORDER_ARRIVAL`/`AGENT_OBSERVE`/`AGENT_DECIDE`/`SNAPSHOT` 入队；
      `ORDER_CANCELLED`/`TRADE_SETTLE`/`MARGIN_CALL`/`MARKET_DATA_PUBLISH` 直接写日志。
      **验收用例 = OB-9a**：同时间戳两张买单，第一张吃光 10000 档 → **第二张必须
      成交于 10100**。若事务记录入队，第二张会看到未被消耗的 10000 档并错误成交。
      **不用保证金构造该用例**——0.1.1 的准入是恒通过的桩，保证金版本是 0.1.2 的 OB-9b。
- [ ] **T204c** `[事件 Schema §1.4]` `[TDD]` **事务内记录顺序 + 缓冲写出**：
      按 `r0 ORDER_ARRIVAL → 撮合记录 → MARGIN_CALL × m → MARKET_DATA_PUBLISH` 写出；
      记录在事务内缓冲、撮合结束后回填 `fill_count` 再一次性写出。
      **三条断言**：`MARKET_DATA_PUBLISH` 恒为事务最后一条；`accepted=false` 的事务
      只有 `r0`；盘口无变化的事务不写行情。已写出的记录**不得回写修改**。
- [ ] **T205** `[事件 Schema §6—§9]` `[P]` 事件日志写入器 + 运行元数据头部
      （含 `tick_size`/`min_quantity`/`cash_unit` 单位定义）。
- [ ] **T206** `[事件 Schema §7、E-002]` `[TDD]` 事件摘要哈希：按 E-002 的**按事件
      类型封闭清单**取字段（含 `fill_index`/`fill_count`、两个 mark、全部 `postings`），
      **排除**因果外键与 `event_id`；在规范编码之上计算。
- [ ] **T206b** `[事件 Schema E-002]` `[TDD]` **哈希字段覆盖检查**：遍历 §4 声明的
      每个事件类型的必备字段，凡不在 E-002 的「纳入」或「排除」清单中即测试失败。
      **默认落入哪一侧都是错的**——新增字段必须显式分类，否则会静默逃出 KPI-002。

## Phase 3：订单簿与撮合

- [ ] **T301** `[撮合 §1.1]` `[TDD]` 订单簿结构：买降序/卖升序，同价按到达事务
      `transaction_seq` 升序。
      **禁止依赖字典遍历顺序**。
- [ ] **T302** `[撮合 §2.1]` `[TDD]` **成交价取 maker 挂单价**，非 taker 限价。
      用例：买单限价 101 吃卖价 100 → 成交于 100。
- [ ] **T303** `[撮合 §2.2]` `[TDD]` **跨档拆分**：一张单吃多档 → 多个
      `TRADE_SETTLE`，`caused_by_event_id` 相同、共享 `transaction_seq`、`record_index` 递增、
      `valuation_mark` **逐笔推进**（不是整批共用）。
- [ ] **T304** `[撮合 §3]` `[事件 Schema §4.7]` `[TDD]` 剩余处理：限价单挂入簿
      （**保留到达事务的 `transaction_seq`**，且**不产生任何记录**）；市价单按 IOC
      全额撤销并写 `ORDER_CANCELLED`（`reason=IOC_REMAINDER`、`price_ticks=null`）。
      **挂入与撤销的不对称是有意的**（OB-5 对 OB-6）：撤销是主动状态变化，挂入只是
      订单未被消耗的默认归宿，可由 `ORDER_ARRIVAL − Σ 成交 − Σ 撤销` 推出。
- [ ] **T305** `[撮合 §4]` `[事件 Schema §4.7]` `[TDD]` 自成交阻止：cancel-resting，
      撤销簿上旧单并写 **`ORDER_CANCELLED`**（`reason=SELF_TRADE_PREVENTION`），
      taker 继续吃下一档、不消耗数量。**不是** `ORDER_ARRIVAL(action=CANCEL)`——
      那是代理主动提交的撤单指令，属队列事件。
- [ ] **T306** `[撮合 §5]` 准入与撮合的固定顺序：制度钩子 → 对齐检查 →
      （保证金检查桩，0.1.1 恒通过）→ 撮合 → 剩余处理 → 风险检查桩 → 行情发布。
      **桩的调用点必须全部就位**，且 `reserved_units` 须按公式算出并写入分录
      （T407b）——0.1.2 只接上拒绝逻辑，不改公式。
- [ ] **T306b** `[撮合 §1.2]` `[TDD]` **撮合事务原子性**：`ORDER_ARRIVAL` 弹出时
      在单个事务内完成撮合、逐笔结算、剩余处理、风险检查；事务内账户变化立即生效。
      **验收用例**：一张大单跨三档 → 三笔 `TRADE_SETTLE`（`fill_index` 0/1/2、
      `fill_count` 3）+ **仅一次**整批风险检查。期望值见
      [订单簿向量](../../../docs/contracts/orderbook-vectors.md) OB-4。
- [ ] **T307** `[撮合 §6]`、`[退化 §1]` `[TDD]` 空簿与单边簿：市价单 IOC 撤销、
      `mid` 未定义时 `valuation_mark` 退化为 `last`、首笔成交前退化为
      `initial_price`。
- [ ] **T308** `[订单簿向量 OB-1—OB-7、OB-9a]` `[TDD]` **八条订单簿向量全部通过**
      （退出条件 E3）。断言事件序列（**含 `MARKET_DATA_PUBLISH` 的存在与位置**）、
      `record_index`、`fill_index`/`fill_count`、逐笔 `valuation_mark`/`risk_mark`、
      `ORDER_CANCELLED` 字段与事务后簿状态，**全部为整数比较，禁止容差断言**。
      **OB-8 与 OB-9b 不在 0.1.1 范围内**——它们依赖杠杆账户与保证金判定，
      属 0.1.2（`0.1.2 T201` / `0.1.2 T104`）。

## Phase 4：账户与记账（无杠杆）

- [ ] **T401** `[账户 §1]` 账户实体：`wallet_units`、`position_units`、
      `entry_notional_units`、`reserved_units`、`realized_pnl_units`、`state`。
      **字段全部就位**，保证金逻辑留空（0.1.2 填）。
- [ ] **T402** `[账户 §2.1]` `[TDD]` `entry_notional` 更新：同向加仓 / 反向平仓 /
      **反向翻仓**三条路径；`avg_entry` 向零取整，余数留在 `entry_notional`。
- [ ] **T403** `[账户 §2.2]` `[TDD]` 未实现盈亏与**双口径权益**：
      `equity(mark) = wallet + position × mark − entry_notional`，据此导出
      `risk_equity = equity(risk_mark)` 与 `valuation_equity = equity(valuation_mark)`。
      **两者不得互相替代**：风险公式一律用 `risk_equity`，报告与 PnL 桥接一律用
      `valuation_equity`。0.1.1 虽不做保证金判定，但双口径须在此就位——否则 0.1.2 会在
      单一口径的基础上叠加。
- [ ] **T404** `[ADR-001 §3]` `[TDD]` 手续费：**向上取整**，方向恒不利于代理；
      负 maker 费率（返佣）同样向上取整。费用账户为**有符号**累计量。
- [ ] **T405** `[事件 Schema §4.2.1]` `[TDD]` 账户分录 `postings`：长度恒为 2，
      含 `*_delta` 与 `*_after`。**每次账户变动都由引发它的事件承载**。
- [ ] **T406** `[账户 §2.3]` `[TDD]` **C1/C2 逐事件断言**——整数精确相等，
      不得写成容差断言。违反即测试失败并打印失衡账户。
      逐事件价值断言**必须含 `entry_notional_delta`**（plan §5.2）：
      `Σ(wallet_delta − entry_notional_delta) + 费用 + 风险 = 0`。
      漏掉 `entry_notional` 会把合法的跨价换手判为失败。
- [ ] **T407** `[验收向量]` `[TDD]` **案例 1—5、10 全部通过**（退出条件 E2）。
      案例 2（三代理跨价换手）为必测项，只做案例 1 会误证已推翻的旧等式。
- [ ] **T407b** `[验收向量 7b]` `[TDD]` `reserved_units` 四组场景。**0.1.1 只需算出
      并记录该值**（准入判定桩恒通过），0.1.2 才接入拒绝逻辑——但公式与分录须在 0.1.1 就
      正确，否则 0.1.2 会在错误基础上叠加。
- [ ] **T408** `[指标字典 §5.2]` `[TDD]` PnL 桥接逐事件残差为 0，
      用 `valuation_mark`（**不是** `risk_mark`）。

## Phase 5：制度钩子（接口就位）

- [ ] **T501** `[v0.1 / D-1]` 钩子接口：`validate_order`、`session_state`、
      `settlement_rule`、`margin_rule`、`price_bound`。**调用点必须全部就位**，
      遗漏一个时点会导致整类制度将来无法表达。
- [ ] **T502** `[v0.1 / D-1]` 加密式配置的空实现：24/7、即时结算、无涨跌停、
      无熔断。**钩子只能拒绝或延迟，不能改写订单**。

## Phase 6：确定性与验收

- [ ] **T601** `[代理策略 §10.1—§10.2]` `[P]` RNG：`blake2b` 长度前缀语义键 →
      开区间均匀数。**不用 `SeedSequence`**（NumPy 非标准库）。
      0.1.1 只需均匀分布，其余分布 0.1.2 补。
- [ ] **T602** `[SC-002]` `[TDD]` 确定性：同配置同种子两次运行的事件摘要哈希
      相同（退出条件 E4）。
- [ ] **T603** `[SC-006]` `[TDD]` **独立验证器** `verify`：只读事件日志，
      **不导入 `kernel/` 或 `ledger/`**——复用内核代码就无法证明日志自包含。
      重建账户终态、校验因果链引用完整性、校验 C1/C2。
- [ ] **T604** `[KR-005]` `[TDD]` 导入检查：核心领域层无 NumPy 等第三方导入
      （退出条件 E8）。
- [ ] **T605** `[plan §5.2]` 属性测试：随机订单流（含极端价格、边界数量、自成交、
      跨档）下 C1/C2 恒成立、`queue_key` / `log_key` 各自严格递增、状态机无非法转移。
- [ ] **T606** `[NFR-002]` 覆盖率：订单簿与账本分支覆盖 ≥ 90%（退出条件 E9）。

---

## 退出检查清单

全部勾选后 0.1.1 完成，方可进入 0.1.2：

- [ ] E1 C1/C2 逐事件精确成立（T406）
- [ ] E2 验收向量 1—5、10 通过（T407）
- [ ] E3 订单簿向量 **OB-1—OB-7 与 OB-9a** 全部通过（T308；OB-8/OB-9b 属 0.1.2）
- [ ] E4 事件摘要哈希稳定（T602）
- [ ] E5 KR-006 单调性断言生效（T202、T203）
- [ ] E6 日志自包含、因果链完整（T603）
- [ ] E7 规范序列化逐字节确定（T104）
- [ ] E8 核心层无第三方导入（T604）
- [ ] E9 分支覆盖 ≥ 90%（T606）

## 遇到合同缺陷时

实现中发现合同不可行或自相矛盾时：

1. **停下，不要绕过**——绕过会使合同失去裁判地位；
2. 记录问题与最小复现；
3. 按 PRD §10 修合同（必要时记 ADR、提升 `schema_version`）；
4. 重算受影响的验收向量期望值；
5. 再继续实现。

四轮复审都是在文档层发现错误的，实现层大概率还会再发现——这是预期之内的，
不是意外。
