# MarketGameSim

可复现的合成市场反事实与压力测试环境：把交易信念转化为可在明确声明的模型族内被
实验否定的条件性命题。

模型中不存在外生基本面信息通道，价格路径完全由订单流互动内生产生——这是一项**实验
隔离选择**，用于研究订单流与价格反馈是否足以产生目标现象，不代表对真实市场信息效率
的判断。

**第一版围绕一个旗舰问题**：在加密式永续市场中，杠杆上限分布与维持保证金率是否足以
产生自我强化的价格崩盘？

系统能否定的是「信念在该模型族中无条件成立」，不是「信念在真实市场中成立」。

项目采用规格驱动开发（Specification-Driven Development，SDD），版本与里程碑三件套
（spec/design/tasks）生命周期见 [`docs/features/README.md`](docs/features/README.md)。

## v0.1 研究交付

- [正式总结报告](docs/experiments/0.1.5-flagship-report.md)
- [代表性离线回放](docs/experiments/0.1.5-representative-replay.html)
- [限制与失效边界](docs/experiments/0.1.5-flagship-report.md#限制与失效边界)
- [正式 evidence index](docs/experiments/0.1.5-evidence-index.json)

四项交付均来自 `SPONTANEOUS + formal-research` 正式证据；单命令重建入口与边界见
[`PRD §15 交付路线图`](docs/market-game-sim-prd.md#15-交付路线图)。

## 当前规格

- [`docs/features/0.2/`](docs/features/0.2/README.md)：已签收的 H1 手动交易沙盒。
  - `spec.md` 版本需求　`design.md` 跨里程碑约束　`traceability.json` 需求归属
  - `0.2.1-interactive-sandbox/`：观察、下单、撤单、输入重放与研究证据隔离
- [`docs/features/0.1/`](docs/features/0.1/README.md)：已签收的含杠杆与强制平仓市场实验环境，
  用于把交易信念改写成可证伪的条件性命题。
  - `spec.md` 需求与验收　`design.md` 架构与测试策略
  - `0.1.1-minimal-kernel/` 最小确定性内核
  - `0.1.2-leverage-and-first-experiment/` 杠杆实验闭环
  - `0.1.3-robustness/` 模型稳健性
  - `0.1.4-replay-and-report/` 回放与报告
  - `0.1.5-goal-driven-flagship/` 目标驱动代理与正式旗舰实验

**v0.1 已签收**：0.1.1—0.1.5 全部退出条件通过，0.1.5 研究声明已建立；不可变记录见
[`docs/features/releases/0.1.md`](docs/features/releases/0.1.md)，需求归属见版本根 `spec.md`
与 `docs/features/0.1/traceability.json`。

## 产品与研究文档

- `docs/market-game-sim-prd.md`：产品目标、MVP 范围、成功指标、风险和交付路线图。
- `docs/research/methodology.md`：代理经济学、博弈分析、价格涌现和模型验证方法。
- `docs/research/metrics-dictionary.md`：术语与指标的口径合同，含守恒不变量。

## 实现契约

- `docs/contracts/matching.md`：订单簿定序、成交价规则、跨档拆分与自成交阻止。
- `docs/contracts/event-schema.md`：事件全序键、冻结的优先级类别、各类事件字段。
- `docs/contracts/degenerate-states.md`：退化状态、技术无效与经济终点的判定。
- `docs/contracts/agent-strategy.md`：从信息集到订单意图的确定管线。
- `docs/contracts/margin-and-account.md`：线性永续账户、保证金、强平与穿仓核销。
- `docs/contracts/acceptance-vectors.md`：账户引擎的十个验收向量（整数期望值表）。
- `docs/contracts/orderbook-vectors.md`：订单簿验收向量（OB-1—OB-7、OB-9a 属 0.1.1；
  OB-8、OB-9b 属 0.1.2）。
- `benchmarks/`：性能基准配置、三层判定协议与参考机计时口径。

## 编号命名空间

每个前缀只属于一份文档，跨文档引用时前缀已足以定位来源：

| 前缀 | 含义 | 所属文档 |
|---|---|---|
| `PR-` `KPI-` `G-` `Q-` | 产品需求 / 指标 / 目标 / 决策 | `docs/market-game-sim-prd.md` |
| `FR-` `KR-` `NFR-` `SC-` `A-` | 功能 / 内核 / 非功能需求、成功指标、假设 | `docs/features/0.1/spec.md` |
| `D-1`—`D-7` `P-1`—`P-3` | 设计决策 / 参数取值 | 同上 |
| `MD-` | 指标参数（Δt、W、k、分桶） | `docs/research/metrics-dictionary.md` |
| `DS-` `EV-` `TI-` | 退化参数 / 经济终点 / 技术无效 | `docs/contracts/degenerate-states.md` |
| `E-` | 事件 Schema 参数 | `docs/contracts/event-schema.md` |
| `OB-` | 订单簿验收向量 | `docs/contracts/orderbook-vectors.md` |
| `T0xx`—`T7xx` | 实现任务，**每个里程碑文件内局部唯一**（0.1.1—0.1.4） | `docs/features/0.1/0.1.x-*/tasks.md` |

**任务编号只在单个里程碑内唯一。** 0.1.1 与 0.1.2 都有 `T104`、`T604`，含义完全不同。
跨里程碑引用任务时必须带前缀：写 `0.1.1 T604`，不写 `T604`。

**文件编号沿革**：方向重置（2026-07-31）移除了旧方向的 `001` 规格与
ADR-001—004、007—009，其决策要点并入 v0.1 规格的「设计决策与理由」章。现有编号已
重排为连续序列；旧编号的完整内容见 `git show 41240a2`。

## 版本标识：四套互不相干的编号

同一个「0.1」在四个地方出现，含义**各不相同**，混用会导致引用失真：

| 编号 | 例子 | 含义 | 谁来推进 |
|---|---|---|---|
| **规格 ID** | `v0.1-belief-testing-laboratory` | 一份规格的目录名与稳定标识 | 提出新研究问题时新开 `v0.2-…` |
| **里程碑 ID** | `0.1.1`—`0.1.4` | 规格 v0.1 **内部的实现阶段**，是章节号 | 规格拆分时确定，不随代码变 |
| **包版本** | `pyproject.toml` 的 `0.1.0` | 发布物的 SemVer | 首次可运行发布时才推进 |
| **Schema 版本** | `schema_version = 2` | 事件日志格式版本 | 首次正式运行后，任何字段变更都须提升 |

**里程碑 ID 不是 SemVer**，尽管形状相似。`0.1.1` 完成不意味着发布 `0.1.1` 包——
里程碑全部完成后才形成「完整的 v0.1」，届时包版本如何编号另行决定。
判据：看到 `0.1.x` 想问「这是版本还是阶段」时，答案恒为**阶段**。

## 已生效架构决策

ADR 只记录**跨规格生效、且已被多轮检视验证**的工程合同。尚未被实现检验的设计意图
写在规格的「设计决策与理由」章（v0.1 / D-1—D-7），不占用 ADR 编号。

- `docs/decisions/001-numeric-and-serialization-contract.md`：金额与数量以最小单位整数
  承载，手续费为唯一舍入点，日志缺失值用 `null`。
- `docs/decisions/002-same-timestamp-event-scheduling.md`：新事件全序键严格递增
  （禁止零延迟），因果外键与账户分录写入事件 Schema。

## 建议工作流

```text
提出假设
  → 编写/评审 spec
  → 编写 design 与 ADR
  → 拆分 tasks
  → 测试驱动实现
  → 运行批量实验
  → 保存证据并回写结论
```

## 目录

```text
docs/                 文档：decisions、features、contracts、experiments、research
src/market_game_sim/  Python 源码
tests/                单元、集成和仿真测试
tools/                校验与统一验证入口
benchmarks/           性能基准配置与判定协议
conversations/        AI 对话存档与复盘
```

## 开始开发

环境与依赖见 `pyproject.toml`。开发纪律与质量门见 [`docs/SOP.md`](docs/SOP.md)；
唯一公开验证入口为：

```bash
python tools/verify.py
```

## 本地手动交易沙盒（H1-B）

Phase 2 客户端只绑定 loopback，使用合成市场和模拟资金：

```bash
python -m market_game_sim.interactive.client
```

然后打开 `http://127.0.0.1:8765`。界面支持限价/市价下单、撤单、暂停、继续、单步、
账户与保证金审查；结果不构成交易建议，也不会进入正式研究证据。

代表性交互成果包可用单命令生成：

```bash
python -m market_game_sim.interactive.delivery
```

生成与查看说明见 [`docs/experiments/interactive-H1.md`](docs/experiments/interactive-H1.md)；
成果生成后可离线打开其中的 `replay.html`。
