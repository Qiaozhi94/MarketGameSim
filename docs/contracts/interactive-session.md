# 0.2.1 H1 交互会话合同

**适用范围**：0.2.1 H1 本地、单人、loopback 交互运行。
**合同版本**：1
**状态**：Frozen（2026-09-04；实现前冻结）
**事件 Schema**：沿用 v4；本合同不新增事件类型或字段。
**关联**：[`0.2.1 spec`](../features/0.2/0.2.1-interactive-sandbox/spec.md)、
[`0.2.1 design`](../features/0.2/0.2.1-interactive-sandbox/design.md)

## 1. H1 固定演示参数

| 参数 | 冻结值 |
|---|---|
| 客户端绑定 | `127.0.0.1`；默认端口 `8765`；允许 CLI 覆盖端口，但拒绝非 loopback 绑定 |
| 市场配置 | 派生 `market_game_sim.showcase.r2.build_r2_config()`；不采用 BENCH-001 压力配置 |
| 种子 | `7` |
| 初始价格 | `100.00`（`10_000` ticks） |
| 背景参与者 | 1 个库存型做市商、1 个目标驱动代理、1 个人类账户 |
| 人类账户 | 初始现金 `10,000.00`，空仓、无活动订单、`1×`、初始保证金率 `100%` |
| 人类交易限制 | 单笔最大数量 `1.000`，最多 `8` 个活动订单 |
| 会话上限 | `max_transactions=80`，沿用内核事务计数语义 |
| 输入队列 | 最多 `64` 条待处理输入；超限返回 `QUEUE_FULL` |
| 默认节奏 | `PAUSED + STEP` |
| 连续节奏 | 可选 `1×`，UI 节拍 `250 ms`；墙钟不得进入市场逻辑或输入哈希 |

金额在合同和 UI 中使用用户可见的十进制表示；内部 `wallet_units` 由现有单位转换规则
生成，不在客户端重复换算。

## 2. 规范输入 artifact

文件名固定为 `input-journal.jsonl`。每行是一个 JSON 对象；文件使用 UTF-8，记录按
`input_seq` 排列，不允许删除、重排或覆盖历史记录。

文件采用闭合的三类记录：首行 `INPUT_HEADER`、中间零到多行 `INPUT`、末行
`INPUT_TRAILER`。header 精确包含 `record_kind`、`input_schema_version=1`、`session_id`；
trailer 精确包含 `record_kind`、`input_schema_version=1`、`session_id`、`input_count`、
`input_hash`。未知字段、未知记录类型、重复 header/trailer 或 trailer 后追加内容均拒绝。

### 2.1 记录字段

| 字段 | 类型 / 闭集 | 规则 |
|---|---|---|
| `record_kind` | `INPUT` | 固定记录判别符 |
| `input_schema_version` | `1` | 单条输入协议版本 |
| `session_id` | string | 所属会话标识；用于绑定，不进入 `input_hash` |
| `input_seq` | non-negative integer | 从 `0` 开始，全局严格递增 |
| `client_request_id` | non-empty string | 客户端幂等键；同键同 payload 重复返回原结果 |
| `action` | `PLACE_ORDER \| CANCEL_ORDER \| PAUSE \| RESUME \| STEP \| END` | 未知动作拒绝 |
| `payload` | object 或 `null` | 合法动作是规范化后的对象；解析失败时为 `null` |
| `assigned_timestamp` | integer 或 `null` | 分配后的逻辑纳秒；预分配拒绝为 `null` |
| `accepted` | boolean | 每条输入恰有一个接受或拒绝结果 |
| `reason_code` | 稳定错误码 | 接受时为 `OK`；拒绝时必须是非 `OK` |
| `received_at_wall` | RFC 3339 string 或 `null` | 仅诊断用途，不进入 `input_hash` |

`PLACE_ORDER.payload` 必须包含 `order_id`、`side`、`order_type`、`quantity_units` 和
`price_ticks`；市价单的 `price_ticks` 为 `null`。`CANCEL_ORDER.payload` 必须包含
`order_id`。控制动作的 payload 是空对象 `{}`。领域数值使用整数最小单位，禁止浮点。

### 2.2 顺序、哈希与重放

- 规范 JSON 使用 UTF-8、`sort_keys=true`、无空白分隔符；每行以 LF 结束。
- `input_hash` 使用小写十六进制 SHA-256，按文件顺序覆盖每条 `INPUT` 除 `session_id`、
  `received_at_wall` 外的规范 JSON 字节；每条投影后包含一个 LF。header/trailer 不参与哈希，
  空输入 journal 的摘要为 SHA-256 空字节摘要。
- `assigned_timestamp` 单调不减；同一已提交事务边界上的多条输入可以共享时间戳，排序键
  固定为 `(assigned_timestamp, input_seq)`。
- 重放只接受 `input_schema_version=1` 和完整 journal；未知版本、截断行、缺失 trailer、
  哈希不符均 fail closed。
- 墙钟时间、刷新频率和客户端渲染不得影响输入哈希、事件摘要哈希或逐帧状态。

## 3. Session API

以下是与传输无关的逻辑接口；H1 HTTP adapter 通过 JSON 映射它们，不得另写一套业务规则。

| 接口 | 输入 | 输出 |
|---|---|---|
| `start(config, seed)` | 固定 H1 配置或 replay 参数 | `SessionView`；初始状态 `PAUSED` |
| `observe(after_revision)` | 可选快照 revision | 版本化 `SessionView` |
| `place_order(command)` | 幂等键 + 规范订单 | `InputResult` |
| `cancel_order(command)` | 幂等键 + `order_id` | `InputResult` |
| `input_result(input_seq)` | 输入序号 | 对应 `InputResult` |
| `control(PAUSE \| RESUME \| STEP \| END)` | 幂等键 + 控制动作 | `InputResult` |
| `replay(config, seed, input_path)` | 完整规范输入 journal | `ReplayResult` |

所有 mutation 都必须携带 `client_request_id`。同键同 payload 返回第一次结果；同键不同
payload 返回 `IDEMPOTENCY_CONFLICT`，不得执行第二次动作。

`InputResult` 至少包含：`input_seq`、`accepted`、`reason_code`、`assigned_timestamp`、
`event_ids` 和 `snapshot_revision`。控制动作没有业务事件时，`event_ids` 为空数组。

## 4. 会话状态与稳定错误码

### 4.1 状态转换

```text
CREATED -> PAUSED    start / 完成校验与初始化后按默认节奏等待首个 STEP 或 RESUME
RUNNING -> PAUSED    pause / 当前事务提交完成后停止推进
PAUSED  -> RUNNING   resume
PAUSED  -> PAUSED    step / 只提交一个调度单位后回到 PAUSED
RUNNING -> COMPLETED end 或经济终点
PAUSED  -> COMPLETED end
*       -> ABORTED   不可恢复故障
```

`COMPLETED` 和 `ABORTED` 是终态；终态输入只能拒绝，不能复活会话。暂停期间收到的多条
输入按 `input_seq` 处理，并共享下一事务边界的逻辑时间；中途不推进逻辑时间。

### 4.2 错误码

| 错误码 | 含义 | 是否写入内核业务事件 |
|---|---|---|
| `OK` | 输入已接受 | 按动作执行 |
| `INVALID_STATE` | 当前状态不允许该动作 | 否 |
| `INVALID_INPUT` | Schema、类型、范围或规范化失败 | 否 |
| `RISK_REJECTED` | 账户、保证金或业务风险规则拒绝 | 是，沿既有拒绝事件语义 |
| `UNKNOWN_ORDER` | 撤销目标不存在或不属于当前账户 | 是，沿既有拒绝事件语义 |
| `DUPLICATE_REQUEST` | 已处理的同一幂等请求再次到达 | 否；返回原结果 |
| `IDEMPOTENCY_CONFLICT` | 同一幂等键对应不同 payload | 否 |
| `QUEUE_FULL` | 待处理输入达到 64 条上限 | 否 |
| `SESSION_NOT_FOUND` | session id 不存在 | 否 |
| `ABORTED` | 会话已因不可恢复故障中止 | 否 |
| `INTERNAL_ABORT` | 内核、日志或 artifact 写入故障 | 否 |

解析或 Schema 校验失败只写 input journal；已经进入生产订单路径后被制度、风控或业务规则
拒绝的输入同时写 input journal 和既有拒绝事件。不新增 H1 专用事件类型。

## 5. 观察快照

`observe` 只读取已提交状态，返回字段必须是 `AGENT_OBSERVE` 信息集的子集，并且只包含：

- 价格、上一根完整 K 线、最多 `k=10` tick 的买卖盘摘要、逻辑时间和会话状态；
- 人类账户自己的钱包/权益、仓位、保证金状态和活动订单；
- 最近输入结果、稳定错误码和快照 revision。

未完成 K 线、超出十档深度、未来事件、代理私有状态和未公开通信队列不得出现在快照中。

## 6. H1 manifest

每个 H1 成果包必须包含 `RUN.md`、`manifest.json`、`input-journal.jsonl`、`run.jsonl` 和
离线 `replay.html`。manifest 使用以下闭合字段：

| 字段 | 规则 |
|---|---|
| `manifest_version` | `1` |
| `run_mode` | 必须为 `interactive` |
| `evidence_class` | 必须为 `engineering-demonstration` |
| `schema_version` | `4` |
| `input_schema_version` | `1` |
| `session_id` | 与所有 artifact 绑定 |
| `client_version` | 客户端版本 |
| `code_version` | 代码版本 |
| `config_hash` | 固定配置内容哈希 |
| `seed` | `7` |
| `input_hash` | 见 §2.2 |
| `event_summary_hash` | `run.jsonl` 事件摘要哈希 |
| `frame_hash` | 逐帧状态哈希 |
| `termination_state` | `COMPLETED \| ABORTED` |
| `abort_code` | `termination_state=ABORTED` 时为稳定 abort code，否则为 `null` |
| `artifacts` | 每项含 `artifact_id`、相对 `path`、`sha256`；路径必须在成果包内 |

`run.jsonl` 首条 `RUN_HEADER.run_mode` 必须存在且为 `interactive`，并与 manifest 完全一致。
该字段在事件 Schema 中为 `HASH_EXCLUDE`，所以一致性必须由独立 guard 校验，不能依赖事件
摘要哈希。任一 artifact 校验失败时不得生成部分成果包。

`interactive` 产物只属于工程演示，正式研究、批量统计、报告和 evidence index 入口必须
拒绝它们；交互运行不产生研究声明。
