# ADR-004：RUN_HEADER 增加回放关键配置字段，事件日志 schema 升级到 v3

日期：2026-08-12  
状态：Accepted  
关联规格：[`../features/0.1/spec.md`](../features/0.1/spec.md)（FR-019）、
[0.1.4 里程碑规格](../features/0.1/0.1.4-replay-and-report/spec.md)  
解决问题：0.1.4 检视 round-1 Critical「公开 build_replay 用硬编码配置默认值」与
round-2 High「RUN_HEADER 新增必填字段但 event schema_version 未升级」  
关联文档：[事件 Schema](../contracts/event-schema.md)、
[0.1.4 设计](../features/0.1/0.1.4-replay-and-report/design.md)

## 背景

0.1.4 回放器要证明「日志自包含」：仅凭日志逐帧重建价格、订单簿、账户状态，且与原始
运行逐帧一致（E1 / SC-008）。但回放重建 `reserved_units` 与 `margin_ratio_bp` 需要
四个运行期配置值——`mult`（现金单位缩放）、`fee_bps_cap`（手续费上限）、
`initial_price_ticks`（初始价格，无成交时的风险标记价）、`agent_initial_bp`
（每个代理的初始保证金率）。这些值无法从事件流本身推导（ADR-001 禁止浮点推导），
若回放器用硬编码默认值重建，任何非默认配置的运行都会得到与原始运行不一致的回放。

round-1 修复把这些字段加入 RUN_HEADER，但存在两个契约缺口：

1. **生产写入路径未证明携带真实配置**：`build_run_header` 为四个字段提供默认值，
   调用方可能写出与真实运行不符的 header，回放出的帧与原始运行不一致，而 E1 只测了
   手写 header 的路径；
2. **版本契约未跟进**：事件 Schema §2 规定「字段变更须记 ADR 并提升
   `schema_version`」，新增必填字段仍保持 v2 属于跨版本契约破坏。

## 决策

### 1. 事件日志 `schema_version` 从 2 升级到 3

RUN_HEADER 新增四个必填回放字段是版本化契约变更，`schema_version` 提升到 3：

- v2：同时间戳事件调度（ADR-002），`(timestamp, priority_class, seq)` 全序键；
- v3：RUN_HEADER 新增 `mult` / `fee_bps_cap` / `initial_price_ticks` /
  `agent_initial_bp` 四个回放关键字段（全部必填、`HASH_EXCLUDE`——RUN_HEADER
  整条本就不参与事件摘要哈希）。

### 2. 四个回放字段在 `build_run_header` 中必填，不提供默认值

`build_run_header` 的 `mult` / `fee_bps_cap` / `initial_price_ticks` /
`agent_initial_bp` 改为**必填参数**（删除默认值），从构造侧杜绝「写入错误默认配置」
的可能。任何写日志的路径都必须显式传入真实运行配置；测试调用方同步补齐显式取值。

### 3. v2 日志兼容策略：显式拒绝，不静默降级

v2 日志（或任何缺少四个回放字段的 header）**不可通过公开回放路径回放**：回放读取器
`ReplayConfig.from_header` 对缺失字段抛 `LogError`（TI-5），快速失败并给出明确错误。
这是显式的前向兼容决策——回放一致性的前提是配置在日志内自包含，缺失配置时拒绝比
用错误默认值产出不一致回放更安全。

### 4. 生产配置闭环必须可验证

E1 验收增加真实闭环测试：`ExperimentConfig`（非默认 mult/initial_price/fee）→
`build_run_header`（显式真实值）→ 日志文件 → 公开 `build_replay` → 与独立 oracle
逐帧比对。该测试证明 header 携带的是真实配置而非硬编码默认值。

## 理由

- 日志是回放唯一输入（v0.1 / D-7）：配置若不随日志走，回放要么依赖第二个真源
  （外部配置），要么用错误默认值产出不一致结果——两者都破坏「日志自包含」的
  E1 命题。
- schema_version 是事件日志格式的唯一版本标识（事件 Schema §2），任何必填字段变更
  都须提升，否则无法区分「旧格式缺字段」与「新格式漏字段」，跨版本比较会失真。
- 必填参数而非默认值：把「写错配置」从运行期故障前移到构造期错误，成本最低。

## 影响

- `schema_version` 常量与全部相关测试夹具从 2 更新到 3（writer / kernel runner /
  event_fields.json / digest / parser / bench / 回放测试）。
- `build_run_header` 的调用方需显式传入四个回放字段。
- 事件摘要哈希口径不变（RUN_HEADER 整条排除，v3 的哈希输入与 v2 相同）。

## 备选方案

- **保持 v2，把回放字段设为可选**：可行但弱化了契约——旧日志缺字段时回放器仍要
  决定用哪个默认值，等于把「第二个真源」以默认值形式请回来。
- **在 EVENT 记录里冗余存储配置**：每条事件都携带配置会膨胀日志，且配置本就不是
  市场语义事件，放 header 更符合「头部=运行元数据」的既有分层。
