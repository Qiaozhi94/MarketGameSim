# v0.4：AI 市场生态与 L2 交易者策略层

本目录是 v0.4 的稳定入口。状态唯一真源是 [`spec.md`](spec.md) 的 frontmatter；本文只
提供导航，不复制状态或需求正文。

## 里程碑

| 里程碑 | 状态（见 spec frontmatter） | 目标 |
|---|---|---|
| [`0.4.1-ai-market-ecology/`](0.4.1-ai-market-ecology/spec.md) | draft | L2 交易者策略层、冷启动锚与市场真实性判据 |

## 边界

- 本版本交付市场载体与对照基线，**不建立研究声明**（`engineering-demonstration`）。
- 不引入外生基本面与价值投资者族；不做多标的合约池。
- L1 交易引擎的既有合同不可改；L2 只能通过分级信息集与意图输出影响市场。
- 沙盘结果单向：永不进入 alphamill 证据链，也不构成任何策略有效性的证据。
- owner 的人类扰动实验（研究问题 #1/#3）由后续版本承接，本版本只交付其对照基线。

## 相关入口

- [`spec.md`](spec.md)：v0.4 行为与需求真源。
- [`design.md`](design.md)：L1/L2 分层的跨里程碑技术约束。
- [`traceability.json`](traceability.json)：需求到里程碑退出条件的机器追踪真源。
- [`ADR-011`](../../decisions/011-market-engine-trader-layering.md)：分层与 alphamill 单向边界决策。
- [`docs/features/README.md`](../README.md)：三件套与生命周期规则。
