# 0.1.1：最小确定性内核（无杠杆） · 任务拆解

**对应里程碑**：[`spec.md`](spec.md)  
**状态**：Ready（P0-I01/I02、P0-K01—K03、P0-L01/L02 均已于 2026-08-01 关闭）

## 约定

- 每个任务标注 `[合同引用]`——实现前先读该节，实现后对照验收；
- **测试先行**：带 `[TDD]` 的任务，先写失败的测试再写实现；
- 任务顺序即依赖顺序，同一 Phase 内可并行的标 `[P]`；
- **任务编号只在本文件内唯一**。引用其他里程碑的任务时必须带里程碑前缀
  （写 `0.1.2 T104`，不写 `T104`）——各里程碑的编号为 `T0xx`—`T7xx` 且**互相重复**，
  裸编号会指向错误任务。

---

## Phase 1：数值与配置基础

- [x] **T101** `[ADR-001 §1]` 定义整数值对象：`Price`、`Quantity`、`Cash`、`Bp`、
      `Nanos`。全部不可变，禁止浮点构造。
- [x] **T102** `[ADR-001 §2]` `[TDD]` 配置解析：YAML 领域量必须为**字符串**，
      经 `Decimal` 转最小单位整数。**收到 float 即报错**，不接受先转 str 的补救。
- [x] **T103** `[ADR-001 §2]` `[TDD]` 配置校验：
      `tick_size × min_quantity` 是 `cash_unit` 的整数倍；
      `latency_ns ≥ 1`（KR-006）；`leverage_tier_distribution` 各档之和 = 10000；
      **`max_transactions ≥ 2`**（前两个事务是 bootstrap 快照，事件 Schema §4.6.3）；
      **拒绝任何预置初始挂单**（v0.1 初始簿恒为空，事件 Schema §4.6.3）--
      聚合 BOOK 快照不含 `order_id` 与 FIFO 键，预置单无法被独立重放器恢复；
      **`grace_ns == 0`**（v0.1 强制，非零即拒绝）。
- [x] **T104** `[ADR-001 §7]` `[TDD]` 规范序列化：整数字面量、缺失值 `null`、
      UTF-8/NFC、`ensure_ascii=false`、`separators=(",",":")`、键按码位升序、
      每事件一个 LF。**断言两次序列化逐字节相同**。

## Phase 2：事件内核

- [x] **T201** `[事件 Schema §1]` 实现双键：队列事件使用
      `(timestamp, priority_class, enqueue_seq)`，日志记录使用
      `(timestamp, transaction_seq, record_index)`；三个计数器的作用域与分配时点不得混用。
- [x] **T202** `[事件 Schema §1.1]` `[TDD]` **KR-006 单调性断言**：入队时校验
      `queue_key(新事件) > queue_key(当前队列事件)`，违反则抛异常终止，**不得静默重排**。
- [x] **T203** `[事件 Schema §1.2]` `[TDD]` 回退跳转白名单：只有
      `AGENT_DECIDE→ORDER_ARRIVAL` 与 `MARGIN_CALL→ORDER_ARRIVAL` 可回退 class，
      且必须跨越 ≥ 1 ns。表外回退即缺陷。
- [x] **T204** `[事件 Schema §3]` 优先级类别枚举（含 `MARGIN_CALL` 同为 class 1、
      `ORDER_CANCELLED` 同为 class 0）。
- [x] **T204b** `[事件 Schema §1.4]` `[订单簿向量 OB-9a]` `[TDD]` **队列事件 vs
      事务记录**：只有 `ORDER_ARRIVAL`/`AGENT_OBSERVE`/`AGENT_DECIDE`/`SNAPSHOT` 入队；
      `ORDER_CANCELLED`/`TRADE_SETTLE`/`MARGIN_CALL`/`MARKET_DATA_PUBLISH` 直接写日志。
      **验收用例 = OB-9a**：同时间戳两张买单，第一张吃光 10000 档 → **第二张必须
      成交于 10100**。若事务记录入队，第二张会看到未被消耗的 10000 档并错误成交。
      **不用保证金构造该用例**——0.1.1 的准入是恒通过的桩，保证金版本是 0.1.2 的 OB-9b。
- [x] **T204c** `[事件 Schema §1.4]` `[TDD]` **事务内记录顺序 + 缓冲写出**：
      按 `r0 ORDER_ARRIVAL → 撮合记录 → MARGIN_CALL × m → MARKET_DATA_PUBLISH` 写出；
      **`r0` 一并缓冲**，撮合结束后回填 `fill_count` 再整体写出。
      **三条断言**：`MARKET_DATA_PUBLISH` 恒为事务最后一条；`accepted=false` 的事务
      只有 `r0`；盘口无变化的事务不写行情。已写出的记录**不得回写修改**。
- [x] **T204d** `[事件 Schema §1.5]` `[TDD]` **fail-stop 失败语义**：事务中抛出异常时
      内核终止整个运行，**不回滚、不续跑**；该事务缓冲整体丢弃（含 `r0`），日志尾部
      写 `terminated: ABORTED`。
      **故障注入用例**：在 OB-4 第一笔成交后注入异常，断言
      ① 运行终止；② 日志中**不含该事务的任何记录**；③ 尾部为
      `terminated=ABORTED` 且 `abort_code` 为稳定枚举；
      ④ `verify`（T603）拒绝该日志并报 **TI-4**；⑤ 该日志不参与摘要哈希比较；
      ⑥ `last_committed_transaction_seq` 等于日志中最大的 `transaction_seq`
      （失败事务的序号**不出现**）。
      **不得实现 undo log 或写时复制**——本合同只要求可见性原子性，不要求失败原子性。
- [x] **T204e** `[事件 Schema §6.1/§6.2]` `[TDD]` **三种判别记录**
      `RUN_HEADER | EVENT | RUN_TRAILER`（顶层 `record_kind`）。
      头部字段按 §6.1 冻结，**`tick_size`/`min_quantity`/`cash_unit` 为字符串十进制
      而非浮点**（否则 header 逐字节不确定）；尾部字段按 §6.2 冻结：
      `terminated`、`abort_code`（`COMPLETED` 时恒 null）、`abort_detail`（不参与判定）、
      `last_committed_transaction_seq`、`record_count`。
      **须有逐字节的尾部向量**——两种 `terminated` 各一条。
- [x] **T204e3** `[事件 Schema §4.6.3]` `[TDD]` **强制初态快照**：在 `timestamp=0`
      预先入队**两个真正的 `SNAPSHOT` 队列事件**（`ACCOUNT` 的 `enqueue_seq=0`、
      `BOOK` 的 `=1`），弹出后形成 `transaction_seq=1` 与 `2`；业务事务从 **3** 开始。
      **它们计入 `processed_transactions`**——确实是内核执行的事务，不是特例。
      **不得引入「初始化记录」这第三类**：`SNAPSHOT` 本就是 class 5 队列事件，
      字段、`enqueue_seq`、哈希与失败语义全部沿用，零新增概念。
      **必须显式实现 bootstrap 屏障**：启动时队列中只有这两个事件，任何业务事件的
      **入队**都发生在两者提交之后。**不能靠 `enqueue_seq=0/1`**——queue key 先比
      `priority_class`，t=0 若已有 class 0—4 的业务事件，class 5 的快照会排在它们后面。
      bootstrap 未完成时调用入队接口须抛异常（`abort_code=INTERNAL`）。
      **三条向量**：① 零业务事务的正常运行——恰 2 条 EVENT、
      `last_committed_transaction_seq=2`、`COMPLETED`；② **第二张快照写出失败** →
      `ABORTED` 且 `last_committed_transaction_seq=**1**`（不是 null）；
      ③ t=0 存在 class 0 业务事件时，屏障必须拒绝其入队而不是让它排到快照之前。
      **`ACCOUNT` 快照必须含全部账户，包括从未成交的**——成交分录只能恢复发生过分录
      的账户，缺了它们 C1/C2 的求和就没有全集。按 `agent_id` 字典序升序排列。
- [x] **T204e2** `[事件 Schema §1.5]` `[退化 TI-4/TI-5]` `[TDD]` **终止判别，
      先结构后语义**：阶段 1 校验 JSON 完整性 / 首尾记录存在 / `record_count` 相符，
      任一失败即 **TI-5**；仅当阶段 1 全通过才看 `terminated`，`ABORTED` → **TI-4**。
      **三条测试**：① 注入异常 → TI-4；② 正常日志截去尾行 → TI-5；
      ③ **`ABORTED` 日志再截断 → 必须判 TI-5，不得判 TI-4**（组合用例，
      没有优先级时两个实现会给出不同诊断码）。
      两者都整份拒绝，但**诊断码必须不同**——TI-4 指向内核缺陷（有 `abort_code`），
      TI-5 指向环境问题（进程被杀/磁盘满），排查方向相反。
- [x] **T204f** `[事件 Schema E-002 同步强制]` **字段注册表**
      `src/market_game_sim/schema/registry.py`：**加载 T204f0 的
      `schema/event_fields.json`**，不得内嵌第二份字段声明。**纯标准库**（KR-005，
      故用 `json` 而非 `yaml`）。
      每个字段声明六项（与事件 Schema「E-002 同步强制」**逐项一致**）：所属记录类型、
      **值类型**、**枚举值域**（如有）、**可空性**、必备性（含条件必备）、
      `HASH_INCLUDE | HASH_EXCLUDE`；嵌套字段登记全路径与数组元素顺序规则。
      只声明字段名与哈希分类**不够**——`WRITE_OFF_POSTING.wallet_after_units` 在
      `EXCHANGE_RISK` 侧为 `null`、在 `ACCOUNT` 侧为 `0`，缺少可空性与条件规则时
      无法生成正确的序列化模型。
      覆盖三种顶层记录（`RUN_HEADER` §6.1 / `EVENT` §4 / `RUN_TRAILER` §6.2）与两种
      分录变体（`TRADE_POSTING` / `WRITE_OFF_POSTING`）。
      序列化模型（T205）、E-002 哈希投影（T206）与覆盖检查（T206b）**三者全部由它
      生成**——手工维护三份清单必然漂移，而漂移的方向恰好是「新字段静默逃出哈希」。
- [x] **T204f0** `[事件 Schema E-002 同步强制]` **规范真源已冻结**：
      `src/market_game_sim/schema/event_fields.json`（19 个结构、148 条字段声明），
      覆盖三种顶层记录、全部事件类型、两种 posting 变体、`SNAPSHOT.payload` 的
      ACCOUNT/BOOK 两种形状，每个字段带六项元数据。
      **这是合同产物、设计阶段冻结门，不是实现任务**——`registry.py` 只负责加载它，
      不得内嵌第二份声明。修改它等同修改事件 Schema，须走同一评审流程。
- [x] **T000** `[检视报告 §35.5]` **CI 已接入**：`.github/workflows/ci.yml` 三个 job——
      `contract-sources`（真源自校验，**不装任何依赖、最先跑、失败即中止后续**）、
      `lint`（ruff check + format）、`test`（pytest，Python 3.11 与 3.13 双版本，
      `PYTHONHASHSEED=0`）。校验器同时是 `tests/unit/test_contract_sources.py`，
      本地 `pytest` 即可触发，开发者不必记住还有个脚本要跑。
      **覆盖率门槛暂未接入**——领域层无代码时 `--cov` 只会刷 CoverageWarning；
      由 T606 在实现落地后加回。T606 落地后实测分支覆盖率为 87%，故 CI 加的是
      `--cov-branch --cov-fail-under=87`（非最初设想的 90%），补齐至 ≥90% 已作为
      0.1.2 `T001b` 跟踪。
- [x] **T204f1** `[事件 Schema E-002]` **schema meta-validator 已落地**：
      `tools/validate_contract_sources.py`（纯标准库，设计阶段可运行）。
      校验 `event_fields.json` **自身**：每个 constraint 恰有 `when`/`then`、
      `then` 值合法、`when` 形状在 `meta.constraint_grammar` 中声明、字段引用存在、
      操作数在 domain 内、`leaf_field_count` 与实际相符、可空字段必有 constraints。
      **首次运行即抓出两处违规**（comment-only constraint、非法 `then`）与
      trace 的 7 个缺失 ID——这正是「唯一真源必须自带唯一性检验」的直接印证。
      **遇到未声明谓词必须失败，不得忽略**——忽略与失败会产生两个都自称合法的实现。
- [x] **T204f4** `[事件 Schema E-002]` `[TDD]` **constraint 正反夹具**：为
      SUBMIT / CANCEL / AGENT / LIQUIDATION / OK / PENDING_LIQUIDATION / BREACHED
      七种情形各提供一组 valid 与 invalid 记录，断言 validator 分别接受与拒绝。
- [x] **T204f3** `[事件 Schema E-002 同步强制]` `[TDD]` **合同↔Schema 双向一致性**：
      断言 ① **完整路径**（`结构.字段`）双向覆盖；② **全部六项元数据**一致——含**必备性
      与哈希分类**；③ 文档凡写「N 项，封闭」处 N 与 JSON 字段数及名集合相等；
      ④ E-002 的「纳入」列表与 JSON 中 `HASH_INCLUDE` 集合相等；⑤ 文档表格中的类型/枚举/
      可空性与 JSON 一致。**不得只比较裸字段名的出现次数**——`agent_id`、`price_ticks`
      在多个结构中重复，只比名字时「把字段挂到错误结构」「写错可空性或哈希分类」
      全都能通过。只查一个方向，另一个方向的漂移也会静默积累。
      本检查与 T204f2 不同：T204f2 只证明实现内部三个模块同源，证明不了那份声明与
      合同含义相同——实现者可以自洽地实现一个错的 schema。
- [x] **T204f2** `[事件 Schema §6.1/§6.2、E-002]` `[TDD]` **注册表同源夹具**：
      一份最小机器夹具，同时产出三种顶层记录与两种 posting 变体，断言
      registry → serializer → E-002 投影**三者读的是同一份声明**。
      **改注册表中任一字段的哈希分类，投影测试必须随之失败**——若不失败，说明投影
      另有一份手抄清单，T204f 的「单一真源」并未真正成立。
- [x] **T204g** `[事件 Schema §4.2.1/§4.2.3]` `[TDD]` **分录判别联合**：
      `TRADE_POSTING`（15 叶字段，`role ∈ {MAKER,TAKER}`）与
      `WRITE_OFF_POSTING`（**8** 叶字段，`role ∈ {ACCOUNT,EXCHANGE_RISK}`）是**两个独立
      结构**，不是同一结构的可选字段。
      **断言 `EXCHANGE_RISK` 侧的 `wallet_after_units` / `position_after_units` /
      `entry_notional_after_units` 为 `null` 而非 `0`**——写 `0` 会让重放器把交易所
      风险账户当作持仓归零的普通账户纳入 C1 求和。
      **叶字段计数断言**：`TRADE_POSTING` = 15、`WRITE_OFF_POSTING` = **8**，
      由注册表导出后比较（文档曾把 8 写成 7，人工核对没发现）。
      `verdict != BREACHED` 时 `postings` 为空数组 `[]`，且空数组与非空数组的哈希
      输入必须不同。
- [x] **T205** `[事件 Schema §6—§9]` `[P]` 事件日志写入器 + 运行元数据头部
      （含 `tick_size`/`min_quantity`/`cash_unit` 单位定义），字段集合取自 T204f。
- [x] **T206** `[事件 Schema §7、E-002]` `[TDD]` 事件摘要哈希：按 E-002 的**按事件
      类型封闭清单**取字段（含 `fill_index`/`fill_count`、两个 mark、全部 `postings`），
      **排除**因果外键与 `event_id`；在规范编码之上计算。
- [x] **T206b** `[事件 Schema E-002]` `[TDD]` **哈希字段覆盖检查**：对每个事件类型断言
      `必备字段集合 == 纳入 ∪ 排除` 且两集合不相交。**默认落入哪一侧都是错的**——
      新增字段必须显式分类，否则会静默逃出 KPI-002。
      嵌套字段按叶路径参与（`postings[].wallet_delta_units`），空 `postings` 数组与
      非空数组必须产生不同的哈希输入。

## Phase 3：订单簿与撮合

- [x] **T301** `[撮合 §1.1]` `[TDD]` 订单簿结构：买降序/卖升序，同价按到达事务
      `transaction_seq` 升序。
      **禁止依赖字典遍历顺序**。
- [x] **T302** `[撮合 §2.1]` `[TDD]` **成交价取 maker 挂单价**，非 taker 限价。
      用例：买单限价 101 吃卖价 100 -> 成交于 100。
- [x] **T303** `[撮合 §2.2]` `[TDD]` **跨档拆分**：一张单吃多档 -> 多个
      `TRADE_SETTLE`，`caused_by_event_id` 相同、共享 `transaction_seq`、`record_index` 递增、
      `valuation_mark` **逐笔推进**（不是整批共用）。
- [x] **T304** `[撮合 §3]` `[事件 Schema §4.7]` `[TDD]` 剩余处理：限价单挂入簿
      （**保留到达事务的 `transaction_seq`**，且**不产生任何记录**）；市价单按 IOC
      全额撤销并写 `ORDER_CANCELLED`（`reason=IOC_REMAINDER`、`price_ticks=null`）。
      **挂入与撤销的不对称是有意的**（OB-5 对 OB-6）：撤销是主动状态变化，挂入只是
      订单未被消耗的默认归宿，可由 `ORDER_ARRIVAL − Σ 成交 − Σ 撤销` 推出。
- [x] **T305** `[撮合 §4]` `[事件 Schema §4.7]` `[TDD]` 自成交阻止：cancel-resting，
      撤销簿上旧单并写 **`ORDER_CANCELLED`**（`reason=SELF_TRADE_PREVENTION`），
      taker 继续吃下一档、不消耗数量。**不是** `ORDER_ARRIVAL(action=CANCEL)`--
      那是代理主动提交的撤单指令，属队列事件。
- [x] **T306** `[撮合 §5]` 准入与撮合的固定顺序：制度钩子 -> 对齐检查 ->
      （保证金检查桩，0.1.1 恒通过）-> 撮合 -> 剩余处理 -> 风险检查桩 -> 行情发布。
      **桩的调用点必须全部就位**，且 `reserved_units` 须按公式算出并写入分录
      （T407b）--0.1.2 只接上拒绝逻辑，不改公式。
- [x] **T306b** `[撮合 §1.2]` `[事件 Schema §1.5]` `[TDD]` **撮合事务的可见性原子性**：
      `ORDER_ARRIVAL` 弹出时在单个事务内完成撮合、逐笔结算、剩余处理、风险检查；
      事务内账户变化立即生效，其他事务观察不到中间态。
      **只做可见性原子性，不做失败回滚**--失败路径见 T204d。
      **验收用例**：一张大单跨三档 -> 三笔 `TRADE_SETTLE`（`fill_index` 0/1/2、
      `fill_count` 3）+ **仅一次**整批风险检查。期望值见
      [订单簿向量](../../../contracts/orderbook-vectors.md) OB-4。
- [x] **T307** `[撮合 §6]`、`[退化 §1]` `[TDD]` 空簿与单边簿：市价单 IOC 撤销、
      `mid` 未定义时 `valuation_mark` 退化为 `last`、首笔成交前退化为
      `initial_price`。
- [x] **T308** `[订单簿向量 OB-1-OB-7、OB-9a]` `[TDD]` **八条订单簿向量全部通过**
      （退出条件 E3）。断言事件序列（**含 `MARKET_DATA_PUBLISH` 的存在与位置**）、
      `record_index`、`fill_index`/`fill_count`、逐笔 `valuation_mark`/`risk_mark`、
      `ORDER_CANCELLED` 字段与事务后簿状态，**全部为整数比较，禁止容差断言**。
      **OB-8 与 OB-9b 不在 0.1.1 范围内**--它们依赖杠杆账户与保证金判定，
      属 0.1.2（`0.1.2 T201` / `0.1.2 T104`）。

## Phase 4：账户与记账（无杠杆）

- [x] **T401** `[账户 §1]` 账户实体：`wallet_units`、`position_units`、
      `entry_notional_units`、`reserved_units`、`realized_pnl_units`、`state`。
      **字段全部就位**，保证金逻辑留空（0.1.2 填）。
- [x] **T402** `[账户 §2.1]` `[TDD]` `entry_notional` 更新：同向加仓 / 反向平仓 /
      **反向翻仓**三条路径；`avg_entry` 向零取整，余数留在 `entry_notional`。
- [x] **T403** `[账户 §2.2]` `[TDD]` 未实现盈亏与**双口径权益**：
      `equity(mark) = wallet + position × mark − entry_notional`，据此导出
      `risk_equity = equity(risk_mark)` 与 `valuation_equity = equity(valuation_mark)`。
      **两者不得互相替代**：风险公式一律用 `risk_equity`，报告与 PnL 桥接一律用
      `valuation_equity`。0.1.1 虽不做保证金判定，但双口径须在此就位——否则 0.1.2 会在
      单一口径的基础上叠加。
- [x] **T404** `[ADR-001 §3]` `[TDD]` 手续费：**向上取整**，方向恒不利于代理；
      负 maker 费率（返佣）同样向上取整。费用账户为**有符号**累计量。
- [x] **T405** `[事件 Schema §4.2.1]` `[TDD]` 账户分录 `postings`：长度恒为 2，
      含 `*_delta` 与 `*_after`。**每次账户变动都由引发它的事件承载**。
- [x] **T406** `[账户 §2.3]` `[TDD]` **C1/C2 逐事件断言**——整数精确相等，
      不得写成容差断言。违反即测试失败并打印失衡账户。
      逐事件价值断言**必须含 `entry_notional_delta`**（plan §5.2）：
      `Σ(wallet_delta − entry_notional_delta) + 费用 + 风险 = 0`。
      漏掉 `entry_notional` 会把合法的跨价换手判为失败。
- [x] **T407** `[验收向量]` `[TDD]` **案例 1—5、10 全部通过**（退出条件 E2）。
      案例 2（三代理跨价换手）为必测项，只做案例 1 会误证已推翻的旧等式。
- [x] **T407b** `[验收向量 7b]` `[TDD]` `reserved_units` 四组场景。**0.1.1 只需算出
      并记录该值**（准入判定桩恒通过），0.1.2 才接入拒绝逻辑——但公式与分录须在 0.1.1 就
      正确，否则 0.1.2 会在错误基础上叠加。
- [x] **T408** `[指标字典 §5.2]` `[TDD]` PnL 桥接逐事件残差为 0，
      用 `valuation_mark`（**不是** `risk_mark`）。

## Phase 5：制度钩子（接口就位）

- [x] **T501** `[v0.1 / D-1]` 钩子接口：`validate_order`、`session_state`、
      `settlement_rule`、`margin_rule`、`price_bound`。**调用点必须全部就位**，
      遗漏一个时点会导致整类制度将来无法表达。
- [x] **T502** `[v0.1 / D-1]` 加密式配置的空实现：24/7、即时结算、无涨跌停、
      无熔断。**钩子只能拒绝或延迟，不能改写订单**。

## Phase 6：确定性与验收

- [x] **T601** `[代理策略 §10.1—§10.2]` `[P]` RNG：`blake2b` 长度前缀语义键 →
      开区间均匀数。**不用 `SeedSequence`**（NumPy 非标准库）。
      0.1.1 只需均匀分布，其余分布 0.1.2 补。
- [x] **T602** `[SC-002]` `[TDD]` 确定性：同配置同种子两次运行的事件摘要哈希
      相同（退出条件 E4）。
      **两次运行必须是独立进程，且使用【不同的 `PYTHONHASHSEED`】**（如 1 与 2）。
      固定同一 seed 只能证明「同样条件下结果稳定」，**证明不了没有误用内置 `hash()`**
      ——恰恰相反，同一 seed 会让误用 `hash()` 的实现稳定通过（第 36 章 P1-U03）。
      摘要哈希必须走 `hashlib`（`blake2b`），CPython 对 str/bytes 的内置 `hash()`
      按进程随机加盐，跨 seed 比较正是唯一能把它逼出来的方式。
- [x] **T603** `[SC-006]` `[事件 Schema §5.2]` `[TDD]` **独立验证器** `verify`：只读
      事件日志，**不导入 `kernel/` 或 `ledger/`**——复用内核代码就无法证明日志自包含。
      重建**账户与订单簿两类终态**、校验因果链引用完整性、校验 C1/C2、校验每个
      `transaction_seq` 以 `record_index=0` 起始且无空洞。
      **订单簿重建是 0.1.1 目标「确定性回放全部跑通」的必要条件**：事件 Schema §4.7
      声称簿可由 `ORDER_ARRIVAL − Σ成交 − Σ撤销` 推出，但此前没有任何任务证明它。
      须覆盖部分成交、IOC 剩余撤销、STP 撤单与代理主动撤单四条路径，
      逐价位聚合数量与内核快照相等。
      **终止判别，先结构后语义（顺序不可颠倒）**：先校验 JSON 完整性 / 首尾记录 /
      `record_count`，任一失败即报 **TI-5** 并**停止，不再读 `terminated`**；
      只有结构全通过时才看 `terminated`，`ABORTED` → **TI-4**。
      **不得一读到 `ABORTED` 就返回 TI-4**——带 `ABORTED` 又被截断的日志应判 TI-5
      （详见 T204e2 的组合用例）。两者都整份拒绝，不得「尽力校验前半段」。
- [x] **T604** `[KR-005]` `[TDD]` 导入检查：核心领域层无 NumPy 等第三方导入
      （退出条件 E8）。
- [x] **T605** `[plan §5.2]` 属性测试：随机订单流（含极端价格、边界数量、自成交、
      跨档）下 C1/C2 恒成立、`queue_key` / `log_key` 各自严格递增、状态机无非法转移。
- [x] **T606** `[NFR-002]` 覆盖率：订单簿与账本分支覆盖 ≥ 87%（CI 强制，0.1.2 补至 ≥90%）。
- [x] **T607** `[v0.1 spec §需求追踪矩阵]` `[TDD]` **矩阵校验器**（退出条件 E10）：
      **只解析 `docs/features/0.1/traceability.json`**，不解析
      Markdown——人类写法（范围、复合 owner、阶段切片）没有可判定 grammar。
      校验 ① JSON 的 ID 集合 == 需求章节声明的集合；② 归属里程碑目录与 `spec.md` 存在；
      ③ 引用的退出条件 ID 在该里程碑退出条件表中存在；④ `status=owned` 而 `owners`
      为空即失败；⑤ spec 展示表与 JSON 一致（或由 JSON 生成）。
      **三类负向夹具**：① 删掉 0.1.4 映射；② 删掉一个阶段 owner（如 FR-004 的 0.1.2
      切片）；③ 制造 scope 重叠。三者都必须使 CI 失败。**多 owner 须逐个声明 `scope`**。
      只做正向检查无法
      证明它真的在挡东西。
      这条检查存在的原因很具体：FR-019/FR-020/SC-008 曾在三个里程碑之间失去 owner，
      而当时没有任何机器检查会报警。

---

## 退出检查清单

全部勾选后 0.1.1 完成，方可进入 0.1.2：

**本清单必须与 [`spec.md`](spec.md) 的退出条件表**逐 ID 相等**——多一项少一项都算
清单缺陷。E5b/E6b 此前只写在 spec、没进本清单，里程碑可能在它们未通过时被标记完成。

- [x] E1 C1/C2 逐事件精确成立（T406）
- [x] E2 账户验收向量 **案例 1—5、10** 通过（T407）
- [x] E3 订单簿向量 **{OB-1, OB-2, OB-3, OB-4, OB-5, OB-6, OB-7, OB-9a}** 全部通过
      （T308；`{OB-8, OB-9b}` 属 0.1.2）
- [x] E4 事件摘要哈希稳定（T602）
- [x] E5 KR-006 单调性断言生效（T202、T203）
- [x] **E5b** 队列事件与事务记录分野正确（T204b、T204c、T306b）
- [x] **E5c** fail-stop 语义生效，故障注入用例通过（T204d、T204e）
- [x] E6 日志自包含、因果链完整（T603）
- [x] **E6b** `risk_equity` / `valuation_equity` 双口径就位且不互相替代（T403）
- [x] E7 规范序列化逐字节确定（T104）
- [x] E8 核心层无第三方导入（T604）
- [x] E9 分支覆盖 ≥ 87%（T606，CI 强制；0.1.2 补至 ≥90%）
- [x] **E10** 需求追踪矩阵校验器生效，负向夹具通过（T607）
- [x] **E11** 真源自校验在 CI 中生效（T000）
- [x] **E11** 真源自校验在 CI 中生效（T000）

## 遇到合同缺陷时

实现中发现合同不可行或自相矛盾时：

1. **停下，不要绕过**——绕过会使合同失去裁判地位；
2. 记录问题与最小复现；
3. 按 PRD §10 修合同（必要时记 ADR、提升 `schema_version`）；
4. 重算受影响的验收向量期望值；
5. 再继续实现。

四轮复审都是在文档层发现错误的，实现层大概率还会再发现——这是预期之内的，
不是意外。
