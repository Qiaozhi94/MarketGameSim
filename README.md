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

- `specs/002-belief-testing-laboratory/`：含杠杆与强制平仓的市场实验环境，用于把
  交易信念改写成可证伪的条件性命题。**状态 Draft**。

## 产品文档

- `docs/product/prd.md`：产品目标、MVP 范围、成功指标、风险和交付路线图。
- `docs/product/methodology.md`：代理经济学、博弈分析、价格涌现和模型验证方法。
- `docs/product/metrics-dictionary.md`：术语与指标的口径合同，含守恒不变量。

## 实现契约

- `docs/contracts/event-schema.md`：事件全序键、冻结的优先级类别、各类事件字段。
- `docs/contracts/degenerate-states.md`：退化状态行为与发散样本判定标准。
- `benchmarks/`：性能基准配置、三层判定协议与参考机计时口径。

## 已生效架构决策

ADR 只记录**跨规格生效、且已被多轮检视验证**的工程合同。尚未被实现检验的设计意图
写在规格的「设计决策与理由」章（002 / D-1—D-7），不占用 ADR 编号。

- `docs/adr/005-numeric-and-serialization-contract.md`：金额与数量以最小单位整数
  承载，手续费为唯一舍入点，日志缺失值用 `null`。
- `docs/adr/006-same-timestamp-event-scheduling.md`：新事件全序键严格递增
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
`specs/002-belief-testing-laboratory/spec.md` 中的研究边界和验收指标。
