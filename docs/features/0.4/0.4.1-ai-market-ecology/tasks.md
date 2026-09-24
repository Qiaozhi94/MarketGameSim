---
kind: milestone
id: 0.4.1
version: "0.4"
related_features:
  - 0.3.1
  - 0.3.2
topics:
  - market-ecology
  - trader-strategy-layer
  - stylized-facts
doc_kind: tasks
created: 2026-09-19
updated: 2026-09-24
---

# 0.4.1：AI 市场生态 - 任务

> Owner: TBD | Spec: `spec.md` | Design: `design.md`

## 0. 来源与执行规则

- 行为与验收真相源：[`spec.md`](spec.md)。
- 技术方案与边界：[`design.md`](design.md)。
- 每项任务只描述一个可验证动作，并引用合法的 US/需求/AC ID。
- 每个 Phase 的最后一项任务是成果门；成果门必须产出可打开页面或可消费的 artifact。
- **G1 研究问题前置检查**（features/README §阶段成果门，ADR-010）：本次交付服务
  [`owner-research-question`](../../../research/owner-research-question.md) 的研究问题 #2
  「AI 市场自身的均衡与突变」——它是研究问题 #1/#3 的对照基线，没有一个会自发成交、
  能内生崩盘的纯 AI 市场，人类介入前后的差异无从测量。**owner 2026-09-21 批准。**
- L1 合同不可改：任何任务都不得修改撮合、账本、保证金、强平与事件 schema 的既有语义。
- 质量门限值由 `spec.md` §6 唯一拥有；任务不得就地改门限，调门限须改 spec 并说明理由。

## 1. 前置条件

- [x] T960 (`FR-501`, `AC-501`): 复现并锁定冷启动死锁——为「零公开成交流 ⇒ EWMA 预热
      不结束 ⇒ 目标仓位恒 0 ⇒ 无委托」写可重复运行的复现测试，作为锚设计的红灯基线
      — verify: `tests/unit/agent/test_bootstrap_anchor.py`
- [x] T961 (`FR-505`, `DR-502`, `AC-504`, `AC-505`): 冻结市场质量六项与 stylized facts 五项的计算口径
      （Q-505 已裁决：特征 3 要求 lag 1 与 lag 50 都显著，p 取两者最大值；统计窗口按 Q-501
      从最后一个代理退出冷启动后开始），落地
      `MarketQualityReport` schema 与机器校验入口；本里程碑的组 A 家族**另建实例**，
      不得并入 `build_market_validation_matrix` 既有家族 — verify:
      `tests/unit/metrics/test_market_quality.py`
- [x] T962 (`DR-501`, `NFR-502`, `AC-503`): 冻结 `StrategyRoster` schema（族标识/数量/参数/
      时间尺度/冷启动锚/引擎指纹）与由 `roster_id` 重建装配的入口 — verify:
      `tests/unit/experiment/test_strategy_roster.py`

## 2. 实现任务

### Phase 1：冷启动与 L2 分层

- [x] T963 (`FR-501`, `NFR-502`, `AC-501`): 实现冷启动锚——零公开成交流条件下的确定性首笔
      意图（Q-501：±1 最小单位、方向按族内装配顺序奇偶交替且不用随机数、奇数族的余数轮流分配、按对手最优价且对手方为空时以初始价挂限价、退出复用预热条件），
      并写明 `ewma_half_life_trades` 在 live 生态下的语义（spec §3 范围内的澄清项），
      锚来源做成可插拔接口且只注册 `synthetic`，锚参数与来源标识进入运行头；正反两侧都有
      断言（有锚产生委托 / 无锚复现死锁 / 未注册来源 fail closed）— verify:
      `tests/unit/agent/test_bootstrap_anchor.py`
- [x] T964 (`FR-502`, `IR-501`, `AC-502`): 实现 `TraderStrategy` 协议、分级信息集（I0—I3）与
      策略族注册表；未注册族标识在装配阶段 fail closed 并返回稳定原因码 — verify:
      `tests/unit/agent/test_strategy_registry.py`
- [x] T965 (`TR-501`, `NFR-502`, `AC-510`): 把策略族标识与信息集分级写入既有 `AGENT_DECIDE`
      记录的 `internal_state`，不新增事件类型；覆盖多族、多记录并存的批量因果链场景
      — verify: `tests/integration/test_strategy_layer_causality.py`
- [x] T966 (`FR-503`, `DR-501`, `AC-503`): 让 `live_market` 按 `StrategyRoster` 装配市场，
      并验证同清单同种子价格序列逐点一致 — verify: `tests/integration/test_h2_live_market.py`
- [x] T967 `[成果门:H2-E1]` (`FR-501`, `FR-505`, `AC-501`, `AC-504`, `E6`): 生成可运行的纯 AI 市场与
      第一份 `MarketQualityReport`——冷启动后自发成交、双边盘口可用、六项指标**逐项如实判定**、
      未通过项顶层可见。**本门不要求六项全部达标**（退出条件 E6）：异质策略族在 Phase 2 才实现，
      而价格发现来自策略族异质（ADR-011 §决策 3），Phase 1 达标在机制上不成立；`SC-501` 的
      「全部达标」由 `H2-E2`/`H2-E3` 承接。证据标签为 `engineering-demonstration`
      — verify: `tests/integration/test_market_quality_gate.py`；实测记录：
      [`0.4.1-market-quality-baseline.md`](../../../experiments/0.4.1-market-quality-baseline.md)

### Phase 2：异质策略族与市场真实性

- [x] T968 (`FR-503`, `AC-503`): 实现趋势跟随族（多时间尺度）与均值回归族 — verify:
      `tests/unit/agent/test_native_strategy_families.py`
- [x] T969 (`FR-503`, `AC-503`): 实现情绪噪声族与改良做市商族（报价参数分散，消除全员同价位
      导致的单档盘口）— verify: `tests/unit/agent/test_native_strategy_families.py`
- [x] T970 (`NFR-501`, `AC-509`): 把目标装配压到墙钟 ≤0.5 秒/逻辑秒；先测量事务构成再优化
      （实测撤挂事务占绝大多数），断言失败即红而非警告 — verify:
      `tests/performance/test_live_market_realtime.py`（32 项全绿）。
      达标数字与三条限定见实验报告
      [`§9`](../../../experiments/0.4.1-market-quality-baseline.md)：末段中位 0.1152
      （门限 0.5，余量约 4.3 倍），分母为**真实逻辑秒**而非 `advance()` 次数
- [x] T971 (`FR-505`, `SC-502`, `AC-505`): 按 spec §6 SC-502 表实现 stylized facts 五项度量——
      前三项**复用** `metrics/validation.py` 的既有检验（厚尾用超额峰度 z 检验、收益自相关、
      `|r|` ACF），只新增 lag 50 延伸与协议未覆盖的两项，不新建第二套口径或第二份校正算法；
      在合成对照序列上做正反判定（已知厚尾序列判通过、独立正态序列判未通过）— verify:
      `tests/unit/metrics/test_stylized_facts.py`
- [x] T972 (`FR-503`, `SC-503`, `AC-506`): 跨种子运行纯 AI 市场，对内生不稳定事件做**存在性判定**
      （出现→记录触发条件与频次；未出现→产出如实的「不存在」结论）。两条路径都要有断言，
      阈值取自冻结常量；**不得为制造「出现」而调阈值或注入冲击** — verify:
      `tests/integration/test_endogenous_instability.py`
- [ ] T973 `[成果门:H2-E2]` `[判定 UNQUALIFIED·非未执行]` (`SC-501`, `SC-502`, `SC-503`, `AC-505`, `AC-506`, `AC-509`): 生成异质策略族
      市场的跨种子质量报告集合——市场质量六项达标、stylized facts 达到 SC-502 条数、实时性能达标，
      并产出 SC-503 的**内生不稳定事件存在性判定报告**（出现→记录触发条件与频次；未出现→产出
      「该市场结构在冻结参数下不产生离散崩盘事件」的结论）。**「出现」不是本门的通过条件**：
      把「必须出现崩盘」写进收口前提，压力会精确落在调阈值上，而这正是 SC-503、§5 不变量与
      ADR-005 共同禁止的动作。证据标签为 `engineering-demonstration` — verify:
      `tests/integration/test_endogenous_instability.py`
      **状态（2026-09-24）**：已执行，判定 **UNQUALIFIED**，故保持未勾——未勾在此表示
      「跑过但没达标」，不表示「没做」。三种子交错未通过（见实验报告
      [`§7`](../../../experiments/0.4.1-market-quality-baseline.md)）；其后查明更根本的
      原因是市场在统计窗口打开前就停止成交（[`§8`](../../../experiments/0.4.1-market-quality-baseline.md)），
      一次根因修复（T1001）未足以翻面。**不得为勾选本条而调门限或口径。**

### Phase 3：量化交易者族（不依赖 alphamill）与运行入口

- [x] T974 (`FR-504`, `AC-508`): 实现 Alpha101 公式筛查器——含 `rank`/`IndNeutralize`/`cap` 的
      公式在装配时拒绝并给出稳定原因码，纯时序子集通过；正反用例都要有 — verify:
      `tests/unit/agent/test_alpha_formula_screen.py`
- [x] T975 (`FR-504`, `IR-502`, `AC-507`): 扩展外部信号注入接口——支持 LIMIT 意图、非阻塞推进与
      `signal_version`；信号缺失/超时/非法时降级为 `NO_ACTION` 并写稳定原因码，既有 owner 轨
      阻塞式用法保持可用 — verify: `tests/integration/test_external_signal_family.py`
- [x] T976 (`FR-504`, `TR-501`, `SC-504`, `AC-507`): 量化交易者族的委托走既有撮合/账本/风控路径，
      因果链可回溯到族标识与信号版本 — verify: `tests/integration/test_external_signal_family.py`
- [x] T977 (`NFR-503`, `AC-508`): 为量化族 artifact 写入单向边界声明（不得用作策略有效性证据、
      不回流 alphamill 证据链），并断言其不进入任何 evidence index；本 Phase 用固定信号序列
      验收，**不依赖 alphamill 运行时**（其 M3 未开工，当前无可消费产出）— verify:
      `tests/integration/test_external_signal_family.py`
- [x] T978 `[成果门:H2-E3]` (`SC-504`, `AC-507`, `AC-508`): 生成量化交易者族的可消费运行 artifact，
      并把纯 AI 市场的启动入口与质量报告命令写入 `RUN.md`；证据标签为
      `engineering-demonstration` — verify: `tests/integration/test_external_signal_family.py`

## 3. 验证与验收任务

- [x] T979 (`AC-501`, `AC-502`, `AC-503`): 运行冷启动锚、注册表 fail closed 与装配复现的正反测试
      — verify: `tests/unit/agent/test_bootstrap_anchor.py`、
      `tests/unit/agent/test_strategy_registry.py`
- [x] T980 (`AC-504`, `AC-505`, `AC-506`): 运行市场质量六项、stylized facts 五项与内生不稳定事件的
      门禁测试，覆盖达标与未达标两种装配 — verify:
      `tests/integration/test_market_quality_gate.py`
- [x] T981 (`AC-507`, `AC-508`, `AC-510`): 运行外部信号族的因果链、降级、边界声明与多族批量场景
      测试 — verify: `tests/integration/test_strategy_layer_causality.py`
- [x] T982 (`AC-509`): 运行实时性能断言，并记录目标环境（OS/Python/装配清单）— verify:
      `tests/performance/test_live_market_realtime.py`
- [x] T983 (`AC-501`—`AC-510`): 运行项目统一质量门，并确认 0.3.1 配对轨与 H2 双代理路径无回归
      — verify: `python tools/verify.py`；既有回归门：`tests/integration/test_h2_live_market.py`
- [x] T1001 (`E3`/`E4` 阻塞项，2026-09-24): 定位并修复「市场在 burn-in 边界前停止成交」
      — 根因是均值回归族的参照窗口比趋势族短一个数量级（增量成交带 vs 最长 60 根 K 线），
      平滑上涨下唯一的稳定力自动退场；参照改为 12 根 K 线收盘均值（I1 → I2）。
      修复后市场首次越过 burn-in 边界（3600 秒本段成交 0 → 2447，总成交 8761 → 15141），
      **但价格仍单调涨 6.7 倍、卖侧最终清空，E3/E4 仍未达成**（机制见实验报告 §8.4）
      — verify: `tests/unit/agent/test_native_strategy_families.py`（含平滑上涨必须被对抗、
      无成交带也能决策、窗口长度不变量三项；变异验证：窗口缩到 3 根红 2 项、参照改回
      成交带红 6 项）；实验报告 [`§8`](../../../experiments/0.4.1-market-quality-baseline.md)
- [ ] T1002 `[已知缺陷·不在本里程碑修]`: 策略层与账本的名义口径不一致——账本用
      `notional = |仓位| × mark × MULT`，而 v0.1 冻结的 `risk_budget_linear_v1` 用
      `max_position = max_notional // mark`（少一个 MULT）。后果是每个族永远顶在保证金
      闸口上、`k_x1000` 与 `risk_appetite_x1000` 实际不影响行为。属冻结契约口径，
      需 owner 裁决后单独修（先例：ADR-012 / ADR-015）；修它会改变行为，T215/H2 冻结
      证据须重绑重盖。**同时是外生价格锚的前置条件**——更一般的前置是「锚的强度参数必须
      被证明 binding」，本条只是达成它的一种方式（见
      [`exogenous-price-anchor-options.md §6`](../../../research/exogenous-price-anchor-options.md)）
      — verify: 实验报告 [`§8.5`](../../../experiments/0.4.1-market-quality-baseline.md)
- [ ] T1003 `[状态门]`: 回写 spec 验收证据、版本索引与状态；必须是本文件最后一项 — verify:
      `python tools/validate_spec_lifecycle.py`

## 4. 依赖与并行关系

- `T960 -> T961 [P]` 与 `T960 -> T962 [P]`：先把死锁复现成红灯，再并行冻结两类 schema
  （质量报告与装配清单改不同文件）。
- `T962 -> T963 [P]` 与 `T962 -> T964 [P]`：锚改 `agent/goal.py`，协议与注册表新建
  `agent/strategy_layer/`，互不共享文件；T963 只消费 T962 的 `bootstrap_anchor` 字段，
  不依赖 T961 的质量报告 schema。
- `T974 [P]` 无前置：公式筛查器是纯函数、独立文件，随时可并行；它列在 Phase 3 只表示
  验收归属，不表示执行顺序。
- `T964 -> T965`，`T964 -> T968 [P]` 与 `T964 -> T969 [P]`：因果链写入与四个原生族都只
  依赖协议与注册表；族实现的单元测试不需要活市场，两批族互不共享文件。
- `T961 -> T971 [P]`：stylized facts 度量的验收只用合成对照序列，口径由 T961 冻结，
  不需要等活市场。
- `T963, T964 -> T966`，`T961, T966 -> T967`：先有锚与注册表才谈得上装配，先有装配
  才谈得上度量；T967 是 Phase 1 成果门。
- `T968, T969 -> T970`，`T967, T970, T971 -> T972 -> T973`：策略族齐备后才有意义做性能
  压测；性能不达标时跨种子运行代价过高，故 T970 在 T972 之前。
- `T965, T973 -> T975 -> T976 -> T977 -> T978`：T975 与 T965 都改 `AGENT_DECIDE` 的
  `internal_state` 写入路径，须串行；市场先真，再接外部策略，否则量化族的行为无法与
  内生行为区分。
- `T979 [P]`、`T980 [P]`、`T981 [P]`、`T982 [P]` 可并行：四组验收不共享运行状态。
- `T979, T980, T981, T982 -> T983 -> T1001, T1002 -> T1003`。

## 5. 明确后移

- 外生基本面/价值过程与价值投资者族 → 需先修订 ADR-011 与研究北极星，不在本里程碑。
- 多标的合约池与 Alpha101 横截面算子 → 独立 Feature：本里程碑只做单标的纯时序子集。
- 人类扰动实验的设计与执行（同种子对照：无人类基线 vs 有人类 × N 次重复）→
  [`0.4.2`](../0.4.2-human-perturbation/spec.md)（PRD §15 的 `H2-F`，2026-09-20 立项）；
  本里程碑只交付它的对照基线与市场载体。
- Web 终端界面改动与观察面调整 → 0.3.2 轨：本里程碑只保证终端背后的市场是活的。
- **alphamill 适配器** → 独立 Feature，触发条件是 alphamill M3「策略到 paper 闭环 +
  版本化信号」产出（2026-09-20 核实其活跃 Feature 为 F003/F007/F008，均在 0.2 版本 M2 阶段）。
  本里程碑只交付不依赖上游的注入接口与公式筛查器。
- alphamill 侧的任何改动与双向证据互认 → 永久后移（ADR-011 §决策 5 禁止回流）。
- **实盘盘面分叉锚（`historical_snapshot`）** → [`ADR-014`](../../../decisions/014-historical-snapshot-fork-anchor.md)
  与独立里程碑（owner 2026-09-21 批准方向）：需要行情数据与许可、快照格式与哈希入运行头、
  「只继承价格与成交带、不继承挂单」的设计以及「分叉后走势不是预测」的产物声明。本里程碑
  只交付可插拔的锚来源接口，保证它以后接入时不用改 L2。
