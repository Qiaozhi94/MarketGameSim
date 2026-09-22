# v0.4：AI 市场生态与 L2 交易者策略层

本目录是 v0.4 的稳定入口。状态唯一真源是 [`spec.md`](spec.md) 的 frontmatter；本文只
提供导航，不复制状态或需求正文。

## 里程碑

| 里程碑 | 状态（见 spec frontmatter） | 目标 |
|---|---|---|
| [`0.4.1-ai-market-ecology/`](0.4.1-ai-market-ecology/spec.md) | in-progress | L2 交易者策略层、冷启动锚与市场真实性判据 |
| [`0.4.2-human-perturbation/`](0.4.2-human-perturbation/spec.md) | draft | 人类扰动实验 H2-F：会话 artifact 冻结、同种子对照与稳定性效应量 |

## 边界

- 本版本交付市场载体与对照基线，**不建立研究声明**（`engineering-demonstration`）。
- 不引入外生基本面与价值投资者族；不做多标的合约池。
- L1 交易引擎的既有合同不可改；L2 只能通过分级信息集与意图输出影响市场。
- 沙盘结果单向：永不进入 alphamill 证据链，也不构成任何策略有效性的证据。
- owner 的人类扰动实验（研究问题 #1）由 `0.4.2` 承接：`0.4.1` 交付对照基线与市场载体，
  `0.4.2` 交付会话 artifact 冻结格式、同种子对照与效应量报告；研究问题 #3 复用同一套数据，
  由后续里程碑分析。
- 人类扰动的结论形态是效应量命题，不是「人类能否造成崩盘」（条款见 PRD §15）。

## 相关入口

- [`spec.md`](spec.md)：v0.4 行为与需求真源。
- [`design.md`](design.md)：L1/L2 分层的跨里程碑技术约束。
- [`traceability.json`](traceability.json)：需求到里程碑退出条件的机器追踪真源。
- [`ADR-011`](../../decisions/011-market-engine-trader-layering.md)：分层与 alphamill 单向边界决策。
- [`docs/features/README.md`](../README.md)：三件套与生命周期规则。
