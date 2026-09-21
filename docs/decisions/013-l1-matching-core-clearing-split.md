# ADR-013：L1 拆分为 L1a 通用撮合核心与 L1b 清算风控层，开源引擎只作参考

日期：2026-09-21  
状态：Accepted（owner 裁决，2026-09-21「底层交易引擎能否替换为开源项目」对话）  
关联规格：[`../features/0.4/spec.md`](../features/0.4/spec.md)（L1 合同不变的前提）  
关联决策：[`ADR-011`](011-market-engine-trader-layering.md)（L1/L2 分层）、
[`ADR-012`](012-evidence-rebinding-attestation.md)（本次重绑的盖章依据）  
关联文档：[`../market-game-sim-architecture.md`](../market-game-sim-architecture.md) §1、
[`../contracts/matching.md`](../contracts/matching.md)、
[`../../src/market_game_sim/book/engine.py`](../../src/market_game_sim/book/engine.py)、
[`../../src/market_game_sim/book/matching.py`](../../src/market_game_sim/book/matching.py)

## 背景

owner 提出的目标是「上层输出订单流（AI、人类或回放），底层是通用撮合引擎，将来可以
独立出去复用」，并问能否直接换成成熟的开源撮合引擎。

**开源候选的调研结论（2026-09-21，GitHub API 核对许可证与活跃度）**：

| 项目 | 语言 / 许可证 | 结论 |
|---|---|---|
| nautilus_trader | Rust+Python / LGPL-3.0 | 撮合是回测用的交易所模拟，依赖很重 |
| OrderBook-rs | Rust / MIT | 活跃，但需要原生绑定 |
| exchange-core | Java / Apache-2.0 | 2023-10 后停更，没有强平连锁 |
| liquibook | C++ / 非标准许可证 | 跨语言，许可证需单独审查 |
| LightMatchingEngine | Python / MIT | 2022-01 后停更，功能少于现有 `orderbook.py` |
| dYdX v4-chain、Drift protocol-v2 | Go / Rust | 有永续清算和强平，但与链深度耦合；Drift 已归档 |

它们都不能直接引入：KR-005 要求核心领域层只用标准库；外部引擎不保证本项目的确定性
口径（代码 + 配置 + 种子 + 输入）和整数守恒断言；而且都不输出因果外键。强平、保证金
和破产没有通用的开源实现，因为这部分规则本身就与品种强相关。

**真正妨碍「通用」的是代码结构，不是实现质量。** 拆分前，`book/orderbook.py` 已经
零依赖，但 `book/matching.py` 在同一个循环里既撮合又结算：每成交一笔就立刻调用
`ledger` 的记账、手续费和保证金计算，并且导入了 `ledger/`、`hook/`、`kernel/`。
撮合无法脱离账本单独使用。

## 决策

1. **L1 拆成两层，写进依赖规则**：
   - **L1a 撮合核心**：`book/orderbook.py` + `book/engine.py`。输入是 `IncomingOrder`
     （订单流端口），输出是 `MatchResult`：按实际发生顺序排列的 `Fill` /
     `SelfTradeCancel` 步骤，加上挂单剩余或 IOC 剩余。**只准导入标准库和自身**，
     不认识账户、保证金、手续费、强平、事件 id 和制度钩子；
   - **L1b 清算风控**：`book/matching.py`（事务处理器适配层）+ `ledger/` + `hook/`。
     负责准入（会话、初始保证金、强平过期）、逐笔结算与分录、占用保证金、因果事件
     id、批后两阶段风控与强平连锁。
2. **L1b 严格按顺序消费 L1a 的步骤**。每个步骤自带结算所需的全部数据（身份、价格、
   数量、当时的估值标记，自成交撤单还带当时的 `last_ticks`），因此 L1b 不需要在撮合
   中途读取订单簿，结算看到的状态序列与拆分前单循环实现完全一致。
3. **开源项目只作参考，不作依赖**：接口形状参考 OrderBook-rs 和 exchange-core
   （下单 / 撤单 / 成交回报），强平阶梯与穿仓分摊的概念参考 dYdX v4 的设计文档。
   不拷贝代码。
4. **撮合合同、账户合同、事件 Schema 全部不变**。本决策是纯结构重构，不需要重新签收
   v0.1/v0.2。

## 备选方案

- **方案 A：直接引入开源撮合引擎**。会违反 KR-005 与确定性口径，且因果链和强平连锁
  仍然要自己重写。不采纳。
- **方案 B：只抽出撮合，把强平也做成「通用」模块**。强平规则与永续合约制度绑定，
  强行通用化只会增加抽象而没有复用方。不采纳；L1b 保持品种专用。
- **方案 C：维持单循环实现，只在文档里声明分层**。门禁无法执行，下一次改动就会重新
  耦合。不采纳；隔离由测试锁定（见后果）。

## 后果

- **正面**：L1a 可以脱离账本单独使用和单独测试（`tests/unit/book/test_engine.py`
  不构造 kernel、world 或账户）；它的依赖边界由
  `tests/unit/book/test_engine_isolation.py` 用 AST 锁定，并有反向用例证明守卫能拦截
  违规导入。
- **行为等价的证据**（2026-09-21）：
  - BENCH-001 标定 / 未标定 × 种子 1–3 共 6 次运行（每次约 15.7 万事件，含 79–100 次
    `MARGIN_CALL`），拆分前后完整事件流 sha256 逐位一致，`book.operation_count` 一致；
  - T215 全部 128 个种子块 × 8 个单元 × 主跑与审计 = **2048 次运行**，
    `event_summary_sha256` 与 `artifacts/formal/T215/checkpoints` 冻结值全部一致。
- **负面**：`matching.py` 的名字仍叫 matching，实际职责已是 L1b 适配层。为了不破坏
  40 多处 import，暂不改名。
- **后续行动**：
  - 本次源码树变更按 ADR-012 在同一提交内重盖章（`rerun: false`），理由引用上面的
    2048/2048 证据；
  - 若 L1a 将来要独立发布，在 L1a 之上补一个与 `world` dict 无关的公开包入口，
    另立 ADR；
  - 若要用外部引擎做交叉验证 oracle，放在 `tests/` 下作为可选依赖，不进核心层。
