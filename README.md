# MarketGameSim

多代理金融市场博弈仿真实验平台。

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
