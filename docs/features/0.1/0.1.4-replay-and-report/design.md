---
kind: milestone
id: 0.1.4
parent: v0.1-belief-testing-laboratory
version: "0.1"
related_features: []
topics: [replay, report]
doc_kind: design
gate_version: 1
created: 2026-08-09
updated: 2026-08-09
prerequisites:
  - 0.1.3
---

# 0.1.4：回放与报告 - 设计

> Spec: `spec.md` | Tasks: `tasks.md`

## 0. 输入与约束

- **行为契约**：`spec.md`（FR-019/FR-020/SC-008，退出条件 E1—E5）。
- **架构来源**：`docs/features/0.1/design.md`（L4 呈现与报告层，只读事件日志，D-7）。
- **上游 Contract**：`docs/contracts/event-schema.md`（日志结构、帧、快照）、
  `docs/research/metrics-dictionary.md`（K 线周期、PnL 桥接）、
  `docs/contracts/degenerate-states.md`（经济终点与技术无效）。
- **实现约束**：产物为单文件 HTML，无服务端、无外部请求、不导入内核。

## 1. 技术概要与影响面

把事件日志变成可读的逐帧回放与总结报告，证明日志自包含，且不引入第二个真源。

- 后端 / 数据：`replay/`、`report/` 两个新模块（L4），只消费事件日志与 artifact。
- Event / Evidence：`report_artifacts.json` registry 已冻结 10 类报告输入。
- 测试：新增逐帧一致性 observer（测试专用）、导入检查测试。

## 2. 架构与模块边界

```text
report/   消费 artifact manifest，生成总结报告（条件性结论、效应量、置信区间、失效边界）
replay/   消费事件日志，生成单文件 HTML 逐帧回放
```

依赖规则（与 D-7 / NFR-004 一致）：

- `replay/`、`report/` **不导入** `kernel/`、`book/`、`ledger/`、`eventlog/`；
- 与内核之间只有**日志文件**这一条通路（§3.2）；
- 报告**不自行重算**统计或聚合，只消费 §4.1 的冻结 artifact 并核对哈希。

## 3. 数据模型与 Migration

- 回放器输入：事件日志 JSONL（规范序列化，ADR-001 §7），唯一输入。
- 报告输入：artifact manifest（`manifest_version` + `artifact_root` + 逐 artifact 七项
  封闭清单），每类 artifact 的字段 Schema 唯一真源是
  `src/market_game_sim/schema/report_artifacts.json`。
- 不适用：无持久化 schema 迁移；`replay_artifacts` 的字段变更走 registry
  `schema_version` 提升。

## 4. 接口、Contract 与 Event

### API / CLI / Adapter Contract

- **回放器入口**：`market_game_sim.replay.generate.build_replay(log_path: Path,
  out_path: Path, *, downsample: DownsampleRule | None = None) -> None`；CLI
  `python -m market_game_sim.replay.generate --log <path> --out <path.html>
  [--downsample <rule>]`。失败即非 0 退出码并向 stderr 打印失败原因；先写临时
  文件成功后原子替换，不产出半成品 `.html`。

- **报告入口**：`market_game_sim.report.generate.build_report(manifest_path: Path,
  out_dir: Path) -> ReportResult`；CLI
  `python -m market_game_sim.report.generate --manifest <path> --out <dir>`。
  **`artifact_root` 只有一个来源**——manifest 文件自身的顶层字段（§4.1），不作为
  CLI flag 或函数参数重复出现，避免两个真源互相冲突；`artifact_root` 为相对路径
  时相对 `manifest_path` 所在目录解析，为绝对路径时直接使用。产出两个文件到
  `out_dir`：`report.json`（机器可读，**唯一真源**）与 `report.md`（人类可读，
  由 `report.json` 渲染而来，不得反向派生）。

  `report.json` 顶层封闭字段：`schema_version`（整数）、`run_id`（字符串）、
  `manifest_hash`（字符串，manifest 文件自身摘要）、`generated_at`（ISO 8601
  字符串）、`metrics`（对象，PnL 桥接/经济终点/技术无效率汇总）、
  `conditional_conclusion`（对象，原样消费 §4.1 的 `conditional_conclusion`
  artifact）、`robustness_conclusion`（对象或 `null`，同上消费 0.1.3 产物）、
  `negative_results`（数组，原样消费 `negative_results` artifact）、
  `failure`（对象或 `null`）。

  **成功/失败二态，不存在「部分成功」中间态**：成功时 `failure` 为 `null`，
  `metrics`/`conditional_conclusion`/`negative_results` 均已填充，CLI 退出码
  `0`；失败时上述业务字段全为 `null`，`failure` 非空，CLI 退出码 `1`。

  `failure.code` 取值封闭为五类，与 §4.1 manifest 五类失败一一对应：
  `MISSING_ARTIFACT` / `HASH_MISMATCH` / `SCHEMA_VERSION_MISMATCH` /
  `FIELD_SCHEMA_INVALID` / `UNDECLARED_EXTRA_FILE`。`failure.artifact_id` 定位到
  触发失败的 artifact（`UNDECLARED_EXTRA_FILE` 时改填触发失败的文件相对路径），
  `failure.message` 是人类可读原因。

### Event / Trace Contract

- 逐帧一致性：bootstrap 两个事务合并为第 0 帧；此后第 k 帧对应
  `transaction_seq = k + 2`。帧键两边必须相等。
- 投影字段：各账户 11 字段 + 交易所 2 字段（事件 Schema §4.6.1）、最近成交价
  `last_ticks` 与盘口聚合 `price_ticks`/`quantity_units`/`order_count`（事件
  Schema §4.6.2）。
- 降采样：允许，但规则写入产物并页面可见；E1 一致性验收在未降采样日志上执行。

## 5. Runtime、Workflow 与并发

- 单次进程内生成，无并发与事务状态。
- 降采样流程：读日志 → 按声明规则抽样 → 内联嵌入 HTML → 页面标注。
- 缺件行为（五类失败，见 §4 `failure.code`）：必备件缺失 / 哈希不符 /
  `schema_version` 错版 / 必备字段缺失或类型错误 / 出现未声明额外数据件
  → 报告生成失败（`report.json.failure` 非空），不降级为部分报告。

## 6. UI 与可观测性

- 单文件 HTML：价格、订单簿、账户与强平事件逐帧呈现，支持拖拽、变速与暂停。
- K 线视图：周期与指标字典 §1.9 一致，只用已完成 K 线。
- 数据内联嵌入，不 fetch 任何资源，不依赖 CDN 或本地服务。

## 7. 失败、恢复、安全与兼容

- 失败映射：artifact 校验失败即报告生成失败，`report.json.failure.code`（五类
  封闭清单，见 §4）与 `failure.artifact_id` 定位到具体 artifact 与失败类别。
- 安全边界：纯离线单文件，无网络、无执行外部代码（除自身内联 JS）。
- 兼容：回放与报告同源，保证「看到的」与「统计的」是同一份数据。

## 8. 测试策略与验收映射

| 验收项 | 测试层级 | 计划文件 / 场景 | 关键断言 |
|---|---|---|---|
| `AC-001` (E1/SC-008) | integration | 逐帧一致性 | 回放重建状态 == 独立 observer 快照，逐帧逐字段相等 |
| `AC-002` (E2/PR-018) | integration | 离线打开 | 断网环境下单文件可用，无外部请求 |
| `AC-003` (E3/FR-020) | unit | K 线视图 | 周期与指标字典 §1.9 一致，只用已完成 K 线 |
| `AC-004` (E4/PR-019) | integration | 总结报告 | 数值消费上游 artifact，不自行重算，哈希核对通过 |
| `AC-005` (E5) | unit | 导入检查 | `replay/`、`report/` 不导入 `kernel/`、`ledger/`、`book/`、`eventlog/` |
| `AC-006` (E6/FR-019) | unit | 逐帧呈现与交互控制 | 拖拽定位、变速、暂停均可用；强平帧带可见标注 |

- E1 的 oracle 由测试专用独立 observer 提供，只作期望值输入，绝不喂给回放器。

## 9. 已确认决策与残余风险

| 决策 / 风险 | 结论或缓解 | 理由 | 后续 |
|---|---|---|---|
| 回放器重新实现撮合，形成第二真源 | E1 逐帧一致性是真正防线 | 导入检查挡不住重新实现 | 不一致即失败 |
| 单文件内联大日志导致产物过大 | 允许降采样 | 产物可归档 | 一致性验收在完整日志做 |
| 报告数值与上游产物不一致 | 消费冻结 artifact 并核对哈希 | E4 不自行重算 | 三方一致（manifest/registry/实际） |

## 10. 待确认设计问题

无
