# MarketGameSim 架构

本文是**全局模块边界、运行时约束与技术不变量**的唯一真源，也是原则 2（撮合正确性
不可妥协）与原则 7（小步、确定性、可观察）的规范正文拥有者。字段级合同、算法层与
撮合规则不在这里重复，见 `docs/contracts/` 与各里程碑 `design.md`。

> 各版本共享设计：v0.1 见 `docs/features/0.1/design.md`；v0.2 交互层见
> `docs/features/0.2/design.md`；v0.3（H2 AI 基线与 owner Web 终端）见
> `docs/features/0.3/design.md`；v0.4（L1/L2 分层与人类扰动）见
> `docs/features/0.4/design.md`。

## 1. 分层与依赖方向

```text
L4  呈现与报告        replay/ · report/ · showcase/ · interactive/
                      单文件 HTML 回放器、条件性结论、成果包与证据索引、H1 交互沙盒会话
L3  实验编排与度量    experiment/ · bench/ · metrics/ · robustness/ · evidence/
                      批量运行、配对对照、参数扫描、排除与统计、指标口径、证据级别守卫
L2b 交易者策略层      agent/strategy_layer/（v0.4 新增）
                      TraderStrategy 协议、分级信息集、策略族注册表与原生/外部策略族
L2a 代理运行时        agent/（既有）
                      因子、信念权重、目标仓位、订单意图、做市商、决策事件写入
L1b 清算与风控        kernel/ · book/matching.py · ledger/ · eventlog/ · hook/
                      准入、逐笔结算与分录、保证金、强平连锁、事件因果链、制度钩子接口
L1a 撮合核心          book/orderbook.py · book/engine.py
                      订单簿、价格时间优先、成交与自成交撤单；订单进、撮合结果出
L0  跨层基础          config/ · rng/ · schema/
                      配置解析与校验、确定性随机流、机器真源（事件字段/合同 JSON）
```

**L2 拆成 L2a/L2b 是有原因的，不要合并回去**：
[`ADR-011`](decisions/011-market-engine-trader-layering.md) 把「L1 交易引擎 / L2 交易者
策略层」写成了正式分层，而本文此前的 L2 指的是整个 `agent/` 包（代理运行时）。同一个
仓库里出现两个互不相同的「L2」会让「L2 不得写事件」这类规则失去判定对象——`agent/` 确实
写决策事件，`agent/strategy_layer/` 不写。因此：**ADR-011 所说的「L2 交易者策略层」=
本文的 L2b；「L1 交易引擎」= 本文的 L1。** 两处措辞的对应关系由本节唯一拥有。

**L1 拆成 L1a/L1b 同样有原因**（[`ADR-013`](decisions/013-l1-matching-core-clearing-split.md)）：
L1a 是通用撮合核心，不认识账户、保证金、手续费、强平与事件 id，可以脱离账本单独使用；
L1b 按顺序消费 L1a 输出的撮合步骤，完成结算、风控与因果链。凡是规则只写「L1」的地方，
同时约束 L1a 与 L1b。

依赖规则（单向，不得逆转）：

- L1 不导入 L2a/L2b/L3/L4 中的任何模块；L0 不导入任何上层模块；
- **L1a 只导入标准库与自身**，不导入 L1b 与 L0（ADR-013 §决策 1；由
  `tests/unit/book/test_engine_isolation.py` 锁定）；L1b 通过 `engine.match` 使用 L1a，
  不自行遍历订单簿撮合；
- L4 只消费事件日志，不被 L1—L3 引用（NFR-004、v0.1 / D-7）；
- L2a 通过接口与 L1 交互，不直接触碰订单簿内部结构；
- **L2b 只读分级信息集、只输出目标仓位或委托意图**：不持有账本引用、不调用撮合、
  不写事件（ADR-011 §决策 1）；它通过 L2a 既有的 `GoalModel` / `behavior_mapping`
  接缝接入，不绕过 L2a 直达 L1；
- 制度钩子（v0.1 / D-1）由 L1 定义接口、由配置注入实现，撮合核心不含制度判断。

## 2. 技术不变量（原则 2 的规范正文）

撮合正确性不可妥协——**影响账本或价格形成的缺陷属于阻断性问题**：

- 订单生命周期、价格时间优先、现金与持仓守恒、费用和交易约束必须通过确定性测试。
- 全局守恒以整数精确断言（C1/C2），不得写成浮点容差。
- 唯一舍入点是手续费；价格、数量、金额以最小单位整数承载（ADR-001）。
- 新事件全序键严格递增；因果外键与账户分录写入事件 Schema（ADR-002）。
- 制度钩子只能拒绝或延迟订单，不得改写（v0.1 / D-1）。

## 3. 运行时不变量（原则 7 的规范正文）

小步、确定性、可观察：

- 优先单品种、规则代理、最小订单类型；RL、LLM、多市场等能力必须在基础模型验证后
  通过独立规格引入。
- 所有状态变化必须可记录、可回放、可解释。
- 确定性定义为「相同代码 + 配置 + 种子 + 输入序列」；核心领域层仅用标准库
  （KR-005）。
- 账户状态机不出现非法转移（如 `LIQUIDATED → ACTIVE`）。

## 4. 相关入口

- `docs/features/0.1/design.md`：跨里程碑共享技术设计。
- `docs/features/0.2/design.md`：交互会话、输入重放与研究隔离的共享设计。
- `docs/contracts/`：跨规格实现合同。
- `docs/decisions/`：已拍板且跨 Feature 生效的长期决策（ADR）。
- `docs/SOP.md`：原则入口与阻断规则。
