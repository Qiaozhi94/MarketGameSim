# v0.3：AI Mechanism Baseline & Personal Decision Lab

本目录是 v0.3 的稳定入口。状态唯一真源是 [`spec.md`](spec.md) 的 frontmatter；本文只
提供导航，不复制状态或需求正文。

## 里程碑

| 里程碑 | 状态（见 spec frontmatter） | 目标 |
|---|---|---|
| [`0.3.1-human-in-the-loop-experiment/`](0.3.1-human-in-the-loop-experiment/spec.md) | draft | H2 AI 正式机制基线与研究交付 |
| [`0.3.2-web-trading-terminal/`](0.3.2-web-trading-terminal/spec.md) | draft | 本地 Web 交易终端、价格/K 线与所有者 N-of-1 数据采集 |

## 边界

- `0.3.1` 只收口 H2 AI 正式机制轨的 168 个 paired-seed blocks；所有者训练和正式 N-of-1
  采集由 `0.3.2` 承担，不阻塞 AI 研究包交付。
- `0.3.2` 只服务项目所有者本人，包含可见价格、K 线、交互下单按钮和 24 个正式 N-of-1
  paired blocks；不招募外部真人。
- 市场不接受外生基本面或价格冲击；价格崩盘、流动性枯竭和强平连锁始终分开报告。
- `AI_FORMAL` 与未来的 `OWNER_N_OF_1` 使用独立 evidence index；H1 自由交互不得进入任一正式样本。

## 相关入口

- [`spec.md`](spec.md)：v0.3 产品行为与需求真源。
- [`design.md`](design.md)：v0.3 跨里程碑技术约束。
- [`traceability.json`](traceability.json)：需求到里程碑退出条件的机器追踪真源。
- [`docs/features/README.md`](../README.md)：三件套与生命周期规则。
