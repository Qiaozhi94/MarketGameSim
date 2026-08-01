# MarketGameSim

可复现的合成市场反事实与压力测试环境：把交易信念转化为可在明确声明的模型族内被
实验否定的条件性命题。

模型中不存在外生基本面信息通道，价格路径完全由订单流互动内生产生——这是一项**实验
隔离选择**，用于研究订单流与价格反馈是否足以产生目标现象，不代表对真实市场信息效率
的判断。

**第一版围绕一个旗舰问题**：在加密式永续市场中，杠杆上限分布与维持保证金率是否足以
产生自我强化的价格崩盘？

系统能否定的是「信念在该模型族中无条件成立」，不是「信念在真实市场中成立」。

项目采用规格驱动开发（Specification-Driven Development，SDD）：

1. 在 `.specify/memory/constitution.md` 明确不可违背的工程与研究原则。
2. 在 `specs/<编号>-<主题>/spec.md` 描述用户场景、需求和验收标准。
3. 在同一规格目录的 `plan.md` 记录技术方案和边界。
4. 在 `tasks.md` 将方案拆成可验证的实现任务。
5. 实现、测试和实验输出必须能够追溯到对应需求。

## 当前规格

- `specs/v0.1-belief-testing-laboratory/`：含杠杆与强制平仓的市场实验环境，用于把
  交易信念改写成可证伪的条件性命题。
  - `spec.md` 需求与验收　`plan.md` 架构与测试策略
  - `milestones/0.1.1-*` 最小确定性内核（**当前阶段，可开工**）
  - `milestones/0.1.2-*`、`0.1.3-*` 杠杆实验闭环、模型稳健性（范围已定，任务待拆）

## 产品文档

- `docs/product/prd.md`：产品目标、MVP 范围、成功指标、风险和交付路线图。
- `docs/product/methodology.md`：代理经济学、博弈分析、价格涌现和模型验证方法。
- `docs/product/metrics-dictionary.md`：术语与指标的口径合同，含守恒不变量。

## 实现契约

- `docs/contracts/matching.md`：订单簿定序、成交价规则、跨档拆分与自成交阻止。
- `docs/contracts/event-schema.md`：事件全序键、冻结的优先级类别、各类事件字段。
- `docs/contracts/degenerate-states.md`：退化状态、技术无效与经济终点的判定。
- `docs/contracts/agent-strategy.md`：从信息集到订单意图的确定管线。
- `docs/contracts/margin-and-account.md`：线性永续账户、保证金、强平与穿仓核销。
- `docs/contracts/acceptance-vectors.md`：账户引擎的十个验收向量（整数期望值表）。
- `docs/contracts/orderbook-vectors.md`：订单簿的九个验收向量（OB-1—OB-9）。
- `benchmarks/`：性能基准配置、三层判定协议与参考机计时口径。

## 编号命名空间

每个前缀只属于一份文档，跨文档引用时前缀已足以定位来源：

| 前缀 | 含义 | 所属文档 |
|---|---|---|
| `PR-` `KPI-` `G-` `Q-` | 产品需求 / 指标 / 目标 / 决策 | `docs/product/prd.md` |
| `FR-` `KR-` `NFR-` `SC-` `A-` | 功能 / 内核 / 非功能需求、成功指标、假设 | `specs/001-.../spec.md` |
| `D-1`—`D-7` `P-1`—`P-3` | 设计决策 / 参数取值 | 同上 |
| `MD-` | 指标参数（Δt、W、k、分桶） | `docs/product/metrics-dictionary.md` |
| `DS-` `EV-` `TI-` | 退化参数 / 经济终点 / 技术无效 | `docs/contracts/degenerate-states.md` |
| `E-` | 事件 Schema 参数 | `docs/contracts/event-schema.md` |
| `T1xx`—`T6xx` | 0.1.1 实现任务 | `specs/001-.../milestones/0.1.1-tasks.md` |

**文件编号沿革**：方向重置（2026-07-31）移除了旧方向的 `001` 规格与
ADR-001—004、007—009，其决策要点并入 001 规格的「设计决策与理由」章。现有编号已
重排为连续序列；旧编号的完整内容见 `git show 41240a2`。

## 已生效架构决策

ADR 只记录**跨规格生效、且已被多轮检视验证**的工程合同。尚未被实现检验的设计意图
写在规格的「设计决策与理由」章（001 / D-1—D-7），不占用 ADR 编号。

- `docs/adr/001-numeric-and-serialization-contract.md`：金额与数量以最小单位整数
  承载，手续费为唯一舍入点，日志缺失值用 `null`。
- `docs/adr/002-same-timestamp-event-scheduling.md`：新事件全序键严格递增
  （禁止零延迟），因果外键与账户分录写入事件 Schema。

## 建议工作流

```text
提出假设
  → 编写/评审 spec
  → 编写 plan 与 ADR
  → 拆分 tasks
  → 测试驱动实现
  → 运行批量实验
  → 保存证据并回写结论
```

## 目录

```text
.specify/             SDD 宪章与通用模板
specs/                按功能编号保存的规格、计划和任务
docs/product/         PRD 与产品级路线图
docs/adr/             架构决策记录
docs/contracts/       跨规格实现合同（事件 Schema、退化状态）
docs/experiments/     实验协议与结果索引
src/market_game_sim/  Python 源码
tests/                单元、集成和仿真测试
```

## 开始开发

环境与依赖会在技术选型确认后加入。当前阶段先评审
`specs/v0.1-belief-testing-laboratory/spec.md` 中的研究边界和验收指标。
