---
kind: milestone
id: 0.2.1
version: "0.2"
doc_kind: design
created: 2026-09-01
updated: 2026-09-04
---

# 0.2.1：H1 手动交易沙盒 - 设计

> Spec: `spec.md` | Tasks: `tasks.md`

## 0. 输入与约束

- **行为契约**：[`spec.md`](spec.md)。
- **版本设计**：[`../design.md`](../design.md)。
- **PRD / Architecture**：PRD §15 H1；architecture §1、§3。
- **Contract**：事件 Schema、代理策略、撮合、账户与保证金、退化状态、
  [`interactive-session.md`](../../../contracts/interactive-session.md)。
- **实现约束**：逻辑时间仍是唯一市场时间；人类订单不得绕过现有生产入口；
  `interactive` 永不进入研究证据；核心领域层保持标准库边界。

## 1. 技术概要与影响面

新增一个内核外的 `interactive` 会话层：它负责状态机、墙钟节流、输入排序、快照投影和
artifact 写出；人类适配器把规范动作转换成现有代理/订单事件；客户端只消费快照和提交
命令。重放器以配置、种子和输入序列重新驱动同一会话层。

- 客户端：新增本地交易界面，采用 DQ-201 已确认的 loopback 浏览器方案。
- Runtime：新增 session controller、pacer、human adapter、input journal。
- 内核：只接收已分配逻辑时间的现有动作，不读取墙钟。
- Event / Evidence：沿用 `AGENT_DECIDE` 因果链；新增版本化输入 artifact 与交互证据守卫。
- Replay / Report：复用离线回放，增加人类输入索引和 manifest 绑定。
- 配置：新增交互配置段与固定演示配置。

## 2. 架构与模块边界

```text
client
  -> InteractiveSession API
       |- SnapshotProjector -> committed event/world state
       |- InputJournal      -> canonical input artifact
       |- Pacer             -> wall-clock to logical-time assignment
       `- HumanAdapter      -> existing AGENT_DECIDE / order entry
                                  -> kernel -> book/ledger -> event log

saved config + seed + input journal
  -> InteractiveReplay -> same InteractiveSession without wall-clock waits
```

- `InteractiveSession` 是会话生命周期和输入排序的唯一拥有者。
- `SnapshotProjector` 只读取已提交状态，不得暴露未来队列或代理内部状态。
- `HumanAdapter` 只做输入到现有动作合同的转换，不复制准入、撮合或风险逻辑。
- `InputJournal` 拥有外生输入；event log 继续拥有市场事实，二者由 manifest 内容哈希绑定。
- evidence guard 在任何正式消费者读取事件正文前双读 bundle manifest 与首条
  `RUN_HEADER.run_mode`，并要求两处模式一致；事件 header 是模式真源，manifest 只作交叉校验。

## 3. 数据模型与 Migration

H1 不引入数据库 migration，新增两个版本化 JSON/JSONL artifact：

`input-journal.jsonl` 使用 `INPUT_HEADER + INPUT* + INPUT_TRAILER` 闭合结构；每条 `INPUT`
字段：

- `record_kind`：恒为 `INPUT`；`input_schema_version`：恒为 1。
- `session_id`：诊断标识，不参与确定性比较。
- `input_seq`：从 0 开始严格递增。
- `action`：`PLACE_ORDER | CANCEL_ORDER | PAUSE | RESUME | STEP | END`。
- `payload`：按 action 的闭合对象；领域数值使用整数最小单位。
- `assigned_timestamp`：分配后的逻辑纳秒；预分配拒绝时为 `null`。同一已提交事务边界可重复；
  重放比较与排序一律使用 `(assigned_timestamp, input_seq)` 复合键。
- `accepted` 与 `reason_code`：每条输入恰有一个结果。
- `received_at_wall`：可空 RFC 3339 诊断字段，不进入输入哈希。

manifest 在现有成果包字段上增加 `input_schema_version`、`input_hash`、`run_mode` 与客户端
版本。`input_hash` 是小写 SHA-256，按行覆盖 `INPUT` 中除 `session_id`、
`received_at_wall` 外的规范投影及 LF；header/trailer 不参与哈希。

兼容策略：v1 重放器只接受精确支持的输入 schema；未知版本 fail closed，不做猜测性迁移。

## 4. 接口、Contract 与 Event

### API / CLI / Adapter Contract

逻辑接口与客户端传输解耦：

- `start(config, seed) -> SessionView`
- `observe(after_revision) -> SessionView`
- `place_order(command) -> InputResult`
- `cancel_order(command) -> InputResult`
- `control(PAUSE | RESUME | STEP | END) -> InputResult`
- `replay(config, seed, input_path) -> ReplayResult`

每个 mutation 命令携带客户端生成的幂等键；同键同 payload 返回原结果，同键不同 payload
稳定拒绝。错误码至少区分非法状态、非法输入、风险拒绝、未知订单、重复冲突与内部中止。

### Evidence guard 输入面

guard 同时读取 (a) bundle manifest 的 `run_mode`（JSON artifact，字段可缺失或为未知字符串）
与 (b) 事件日志首条 `RUN_HEADER.run_mode`（闭集 enum；合法日志中不可缺失或未知）。判定顺序：

1. 任一处为 `interactive`：拒绝。
2. manifest 缺失模式或模式不在闭集：拒绝。
3. manifest 与 header 不一致：按未知来源拒绝。
4. 两处为同一非 `interactive` 值：放行。

header 字段在事件 Schema 中为 `HASH_EXCLUDE`，因此模式一致性由独立 guard 断言负责，事件
摘要哈希不能替代该断言。批量扫描先完成全批校验，再原子写 evidence index；任一候选失败时
整批拒绝且零部分写入。

### Event / Trace Contract

接受的 `PLACE_ORDER`/`CANCEL_ORDER` 先形成 `AGENT_DECIDE(rule_id="human")`，再沿既有因果
外键进入订单事件。被拒绝的人类输入始终存在于 input journal；是否也写业务事件遵循 DQ-203
已冻结的记录策略。

若实现需要新增事件类型或字段，必须先修订 `event_fields.json`、事件 Schema 文档、哈希
清单与 schema version，并补跨真源负向测试。

## 5. Runtime、Workflow 与并发

会话由单 writer 驱动；客户端线程/进程不得直接调用 kernel mutation。输入先进入有序 inbox，
会话控制器只在已提交事务边界取出下一条输入，完成规范化、逻辑时间分配和原子提交，再更新
input result 与快照 revision。

暂停语义：完成当前事务后停止调度；`STEP` 从 PAUSED 状态推进一个调度单位并重新进入
PAUSED。暂停期收到的多条输入按 `input_seq` 全部分配到同一个下一事务边界的逻辑时间，逐条
依序提交，中途不推进逻辑时间。重放模式禁用墙钟等待，严格按记录的
`(assigned_timestamp, input_seq)` 复合键注入。

客户端断开与崩溃恢复策略遵循 DQ-202/DQ-204 已冻结的边界；无论策略为何，已提交事务不得回滚，未提交输入不得
标记 accepted。

## 6. UI 与可观测性

首屏至少包含：

- 价格/K 线、买卖盘摘要、逻辑时间、会话状态与节奏控制。
- 钱包/权益、仓位、保证金状态、活动订单。
- 限价/市价下单、撤单和最近输入结果。
- 合成市场、无真实资金、非交易建议的常驻提示。
- loading、empty、paused、rejected、completed、aborted 的独立呈现。

会话状态与 UI 状态分属不同层，映射唯一规定如下：

| 会话状态 | 对应 UI 状态 | 说明 |
|---|---|---|
| `CREATED` | `loading` | 尚未 start，控制区只有“开始”可用 |
| `RUNNING` | 无独立 UI 态，正常呈现 | 空簿时叠加 `empty` |
| `PAUSED` | `paused` | 可提交输入，逻辑时间不推进 |
| `COMPLETED` / `ABORTED` | `completed` / `aborted` | 终态，输入区禁用 |
| —（输入级） | `rejected` | 单条输入结果，不是会话状态 |

诊断信息包含 `session_id`、最新 `input_seq`、快照 revision、逻辑时间、终止状态和稳定错误码；
墙钟延迟只作 UX 诊断，不进入市场指标。

## 7. 失败、恢复、安全与兼容

- 输入解析失败：记录拒绝结果，不进入内核，不分配逻辑时间。
- 内核事务失败：沿现有事务回滚；input result 标记拒绝或会话中止，不留下半提交状态。
- journal/event log 写入失败：会话 ABORTED，写得出时生成稳定 abort code；不声称成果完整。
- 重放哈希不符：报告首个不一致 `input_seq`/event，不生成“复现成功”manifest。
- evidence guard：任一侧为 `interactive`、manifest 缺失/未知、manifest/header 不一致均拒绝；
  只有两处匹配的非 `interactive` 模式放行。批量 guard 先全量校验再写出，拒绝先于任何下游
  文件写入。
- 安全：默认 loopback、无外部凭据、无真实市场 adapter；任何公网绑定均不在 H1 范围。
- 兼容：Windows 为必验环境；路径使用 `pathlib`，客户端不得成为核心协议真源。

## 8. 测试策略与验收映射

| 验收项 | 测试层级 | 计划文件 / 场景 | 关键断言 |
|---|---|---|---|
| `AC-001` | unit + integration | `tests/unit/interactive/test_session.py` | 合法启动、重复/非法启动无副作用 |
| `AC-002` | integration | `tests/integration/test_interactive_observation.py` | 字段是 `AGENT_OBSERVE` 子集；无未完成 K 线、超 k 深度、未来/私有状态 |
| `AC-003` | integration | `tests/integration/test_human_order_path.py` | 正反下单与撤单共用生产路径 |
| `AC-004` | unit + integration | `tests/unit/interactive/test_pacing.py`、`tests/integration/test_interactive_control.py` | 同边界多输入共享时间戳，复合键严格递增；状态机、暂停、单步正确 |
| `AC-005` | cross-process | `tests/integration/test_interactive_replay.py` | 输入、事件摘要与逐帧一致 |
| `AC-006` | integration | `tests/integration/test_interactive_evidence_guard.py` | header/manifest 正反矩阵；摘要不变的模式篡改仍拒绝；批量零部分写入 |
| `AC-007` | client / E2E | `tests/integration/test_interactive_client.py` | 主视图与 §6 映射的全部 UI 状态 |
| `AC-008` | integration + manual | `tests/integration/test_interactive_bundle.py` | 单命令、同源、断网可打开 |

所有行为分支须有接受/拒绝两面测试；会话、inbox、订单批处理和 artifact 写出至少各有一个
多记录场景。失败测试必须同时检查失败前后状态及 fresh retry。

## 9. 已确认决策与残余风险

| 决策 / 风险 | 结论或缓解 | 理由 | 替代方案 / 后续 |
|---|---|---|---|
| 第二套实时内核 | 拒绝；使用外层 pacer 节流现有内核 | 避免逻辑时间与撮合语义分叉 | 性能不足时先测量 |
| UI 专用订单服务 | 拒绝；统一 HumanAdapter | 防止准入/撮合/风控漂移 | 无 |
| 墙钟重放 | 不重放墙钟，只重放分配后的逻辑时间 | 墙钟不可复现且不属市场语义 | 墙钟只作诊断 |
| 研究污染 | 正式消费者入口逐个 fail closed | 只标 header 但不接入口守卫会失效 | H2 另立协议 |
| 输入与事件双日志漂移 | manifest 双哈希 + 因果链接 + 重放比较 | 两者拥有不同事实，不能合并 | H1-C 验证 |

## 10. 待确认设计问题

- [x] DQ-201: 采用仅绑定 `127.0.0.1` 的 Python HTTP adapter + 原生 HTML/JS 客户端；默认端口 `8765`，允许显式覆盖但拒绝非 loopback 绑定。客户端通过短轮询读取版本化快照，并通过 JSON mutation 接口提交动作；核心会话协议保持传输无关。
- [x] DQ-202: 默认 `PAUSED + STEP`，可选 `1×` 连续模式，UI 节拍 `250 ms`。输入只在已提交事务边界按 `input_seq` 取样；`assigned_timestamp` 单调不减，复合键 `(assigned_timestamp, input_seq)` 严格递增。客户端断开后完成当前事务并自动暂停，不允许后台无界继续运行。
- [x] DQ-203: 解析或 Schema 校验失败只写 input journal；已进入生产订单路径后被制度、风控或业务规则拒绝的输入同时写 journal 和既有拒绝事件。不新增 H1 专用事件类型，首版不提升 event schema version。
- [x] DQ-204: 首版不做进程内断点续跑；崩溃会话标记为 `ABORTED`。恢复时从头重放完整且哈希有效的输入日志；输入截断、缺 trailer 或哈希不符均 fail closed。
