# v0.2：Interactive Market Sandbox

本目录是 v0.2 的稳定入口。状态唯一真源是 [`spec.md`](spec.md) 的 frontmatter；本文只
提供导航，不复制状态或需求正文。

## 里程碑

| 里程碑 | 状态（见 spec frontmatter） | 目标 |
|---|---|---|
| [`0.2.1-interactive-sandbox/`](0.2.1-interactive-sandbox/spec.md) | done | H1 手动交易沙盒 |

## 边界

- v0.2.1 只交付本地、隔离的 `interactive` 运行，不连接交易所、券商、钱包或真实资金。
- 交互数据只用于教学、可用性与机制探索，不进入任何研究统计或证据索引。
- H2 人在环正式实验须在 H1 完成后另立规格并冻结独立协议。

## 相关入口

- [`spec.md`](spec.md)：v0.2 产品行为与需求真源。
- [`design.md`](design.md)：v0.2 跨里程碑技术约束。
- [`traceability.json`](traceability.json)：需求到里程碑退出条件的机器追踪真源。
- [`docs/features/README.md`](../README.md)：三件套与生命周期规则。

## 收口提示

**v0.2 已签收**：H1 本地手动交易、确定性重放、研究证据隔离与离线成果包均已完成。
不可变签收信息见 [`docs/features/releases/0.2.md`](../releases/0.2.md)。
