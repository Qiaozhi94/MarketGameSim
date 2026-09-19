---
kind: version-design
id: v0.4-market-ecology
version: "0.4"
doc_kind: design
created: 2026-09-20
updated: 2026-09-20
---

# v0.4 跨里程碑技术设计：L1/L2 分层约束

> 状态唯一真源是 [`spec.md`](spec.md) frontmatter；本文只写跨里程碑共享的技术约束。

## 分层契约

```text
L1 交易引擎（v0.1/v0.2 已签收，本版本不改）
  kernel/ book/ ledger/ eventlog/     撮合、账本、保证金、强平、事件因果链、确定性重放
        ▲ 仅通过既有 ORDER_ARRIVAL / AGENT_DECIDE 路径交互
L2 交易者策略层（v0.4 新增）
  agent/strategy_layer/               TraderStrategy 协议、注册表、分级信息集、策略族
```

- L2 **只能**读分级信息集、**只能**输出目标仓位或委托意图。
- L2 **不得**持有账本引用、不得调用撮合、不得写事件记录。
- 新增策略族不得触发任何 L1 合同变更；一旦需要改 L1，必须先升级对应 contract 并
  单独立项，不在 L2 里绕过。

## 全局不变量的归属

数值与序列化口径、事件因果链、确定性重放的定义由
[`docs/contracts/`](../../contracts/agent-strategy.md) 与
[`架构文档`](../../market-game-sim-architecture.md) 唯一拥有。本版本任何文档都只引用，
不重新定义。

## 证据边界

- 本版本全部产出为 `engineering-demonstration`，不进入任何 evidence index。
- 沙盘结果不得出现在 alphamill 证据链中，也不得作为策略有效性的证据
  （[`ADR-011`](../../decisions/011-market-engine-trader-layering.md) §决策 5）。
- 质量门限值与 stylized facts 计算口径由各里程碑 spec §6 唯一拥有；跨里程碑复用时
  链接而不复制。
