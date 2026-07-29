# MarketGameSim

多代理加密现货市场博弈仿真实验平台。

模型中不存在外生基本面信息通道：价格路径完全由订单流互动内生产生。这使项目可以
集中研究市场行为本身，以及价格走势如何反过来影响交易者决策。

项目采用规格驱动开发（Specification-Driven Development，SDD）：

1. 在 `.specify/memory/constitution.md` 明确不可违背的工程与研究原则。
2. 在 `specs/<编号>-<主题>/spec.md` 描述用户场景、需求和验收标准。
3. 在同一规格目录的 `plan.md` 记录技术方案和边界。
4. 在 `tasks.md` 将方案拆成可验证的实现任务。
5. 实现、测试和实验输出必须能够追溯到对应需求。

## 当前规格

- `specs/001-market-simulation-foundation/`：单品种连续竞价市场、异质交易代理、可复现实验和行为归因的基础版本。

## 产品文档

- `docs/product/prd.md`：产品目标、MVP 范围、成功指标、风险和交付路线图。
- `docs/product/methodology.md`：代理经济学、博弈分析、价格涌现和模型验证方法。
- `docs/product/metrics-dictionary.md`：术语与指标的口径合同，含守恒不变量。

## 实现契约

- `specs/001-.../event-schema.md`：事件全序键、冻结的优先级类别、各类事件字段。
- `specs/001-.../degenerate-states.md`：退化状态行为与发散样本判定标准。

## 已生效架构决策

- `docs/adr/001-discrete-event-time-kernel.md`：离散事件内核，整数时间戳，分流 RNG。
- `docs/adr/002-build-minimal-kernel.md`：自建最小内核，外部框架仅作设计参考。
- `docs/adr/003-crypto-spot-market-without-fundamentals.md`：加密现货标的，
  以内生锚替代外生基本价值，允许极端行情。
- `docs/adr/004-replay-based-visualization.md`：可视化采用事件日志回放。

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
docs/experiments/     实验协议与结果索引
src/market_game_sim/  Python 源码
tests/                单元、集成和仿真测试
```

## 开始开发

环境与依赖会在技术选型确认后加入。当前阶段先评审
`specs/001-market-simulation-foundation/spec.md` 中的研究边界和验收指标。
