# M0 冻结记录（T000i）

**冻结日期**：2026-07-31  
**依据任务**：T000i　**规格**：001-market-simulation-foundation  
**基线**：本记录所在提交；事件 `schema_version = 1`  
**确认**：co-creator 于 2026-07-31 确认冻结，含 EXP-000 的 X-006 固定条件提案值

## 1. 本次冻结的对象

| 文档 | 冻结后状态 | 冻结内容 |
|---|---|---|
| [`spec.md`](spec.md) | Approved | FR-001—FR-013、KR-001—KR-006、A-001—A-004、NFR-001—NFR-004、SC-001—SC-008 |
| [`plan.md`](plan.md) | Approved | 技术上下文、组件边界、宪章检查 |
| [`tasks.md`](tasks.md) | Approved | Phase 0 完成；Phase 1 起可执行 |
| [`event-schema.md`](event-schema.md) | **Frozen** | 全序键与 KR-006 事件产生规则、`priority_class` 清单、各事件必备字段与因果外键、账户分录、E-001—E-003、序列化合同 |
| [`degenerate-states.md`](degenerate-states.md) | **Frozen** | 退化行为、DV-1—DV-3 判定、G-001—G-003 |
| [`../../docs/product/metrics-dictionary.md`](../../docs/product/metrics-dictionary.md) | **Frozen** | 术语、采样约定、指标定义、守恒不变量、D-001—D-004 |
| [`../../docs/experiments/EXP-000-baseline-validation.md`](../../docs/experiments/EXP-000-baseline-validation.md) | **Registered** | 假设、扫描网格、固定条件、统计合同、X-001—X-007 |
| [`../../benchmarks/`](../../benchmarks/) | Frozen（除校准值） | BENCH-001 配置与三层判定协议 |

已生效决策：[ADR-001](../../docs/adr/001-discrete-event-time-kernel.md)—
[ADR-006](../../docs/adr/006-same-timestamp-event-scheduling.md)，均为 Accepted。

**不在本次冻结范围**：`prd.md` 与 `methodology.md` 保持 Draft。它们随阶段演进
（M2/M3 会继续写入结果与结论纪律），冻结会带来虚假的稳定感；两者的**约束力来自
本记录所列的下游文档**，而非其自身状态标签。

## 2. 冻结后的变更规则

任何变更都不是禁止的，但必须留下可追溯的代价：

| 变更对象 | 要求 |
|---|---|
| `priority_class` 取值/语义、事件必备字段、因果外键、序列化合同 | 记录 ADR + **提升 `schema_version`** + 显式声明受影响的既有实验（event-schema §2） |
| 指标口径（D-001—D-004、守恒等式、采样约定） | 记录 ADR + 评估对既有实验可比性的影响；**D-001 一经用于正式实验即不可改** |
| 退化状态判据（DV-1—DV-3、G-001—G-003） | 记录 ADR；已用于正式实验的判据变更须重新预注册 |
| EXP-000 的 X-001—X-007、判据、统计方法 | **须作为新实验重新预注册**（新编号），不得原地修改。运行后调整等同选择性报告（methodology §9.3） |
| 数值与结算口径（ADR-005） | 记录 ADR + 提升 `schema_version`（影响日志字节） |
| FR/KR/SC 编号语义 | 记录 ADR；编号只增不改写，废弃项标注而非删除 |

## 3. 冻结时明示的未决项

这些**不阻塞冻结**，各自有明确归属与解冻条件：

| 项 | 归属 | 解冻条件 |
|---|---|---|
| Q-008 订单流预知者可见范围 | M3 | M3 立项前形成决策 |
| Q-010 半衰期离散度 σ 初值 | M2 | EXP-000 的 X-002 子实验产出后回写 |
| G-001 的 K 阈值校准 | M2 | EXP-000 输出各参数点 `max\|ln(P_t/P_0)\|` 分布后确认 |
| `book_operations_golden`、CALIB-001 参考耗时 | T021/T022 | 首次实现后实测写入 |
| X-006 代理构成对成交率 λ 的影响 | T014b | 首次试运行核对实测 λ；若 `lag*` 越界，调整 X-006 或 X-001 并**重新评审** |

## 4. 冻结的意义与限度

M0 的全部产出是**文档**，没有任何代码检验过它们是否可实现。冻结不表示这些合同已被
证明正确，只表示：**从此刻起，改动它们需要显式代价，而不是随手编辑。**

因此 Phase 1 的第一批实现任务（T001—T004c）同时承担**证伪职责**：若整数单位换算、
因果外键写入、账户分录或规范序列化在实现中被发现不可行或代价过高，应当**记录 ADR
并提升 schema_version**，而不是悄悄偏离合同——后者会使冻结形同虚设，也会让此前
三轮文档检视的投入失去意义。

已知的最大风险：EXP-000 的固定条件（X-006）是提案值，其 λ 估算未经任何实测支撑。
这是冻结时就明示的薄弱点，而非事后发现的缺陷。
