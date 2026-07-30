# Code Review Report

**Reviewed**: MarketGameSim 当前产品、规格、实验、基准与 ADR 文档  
**Languages / formats**: Markdown, YAML, TOML, JSON  
**Review Date**: 2026-07-30  
**处置状态**: 8 项已全部关闭（2026-07-30），见下「处置结论」  

## 处置结论（2026-07-30）

复核后 8 项发现全部成立，无误报。优先级作两处调整：**M-001 升为 High**（属内核
单调性缺陷，威胁 KR-003 与 KPI-002，而非表述模糊）；**M-005 降为 Low**（与研究
正确性无关）。另补两项报告未覆盖的缺陷，一并处置。

| 编号 | 处置 |
|---|---|
| H-001 | EXP-000 冻结 X-001—X-004：τ 网格、σ 敏感性子实验（X-002）、运行终止条件与 burn-in、统计检验/lag 集合/置信水平/bootstrap 次数/BH family；`experiments/EXP-000.yaml` 列为 T014b 的前置产物 |
| H-002 | 新增 [ADR-005](../adr/005-numeric-and-serialization-contract.md)：最小单位整数、唯一舍入点、舍入方向、预冻结上界、PnL 不二次舍入；BENCH-001 增 `cash_unit`；新增 SC-007 |
| H-003 | 新增 [ADR-006](../adr/006-same-timestamp-event-scheduling.md) §3—§5：因果外键、引用完整性断言（SC-008）、研究运行强制 `full` 信息集 |
| M-001 | ADR-006 §1—§2 → KR-006：新事件全序键严格递增 + 禁止零延迟；event-schema §1.1 |
| M-002 | ADR-005 §6—§7：领域层无 NaN / 日志 `null` / 分析层 NaN 三层分离；FR-012、event-schema §4.3+§9、指标字典 §3.1、degenerate-states §0+§1.2 同步 |
| M-003 | Q-009 移出 spec.md 未决问题并注明关闭依据 |
| M-004 | KPI-008 前移至 M2 退出条件；M3 改由新增的 KPI-012（单维度配对对照归因）验收 |
| M-005 | `.gitignore` 增 `.claude/settings.local.json` |
| 补 A | EXP-000 的 `G-004` 与 PRD 项目目标编号冲突且无文档承载 → 改用 `X-` 前缀编号体系 |
| 补 B | 研究运行终止条件不得沿用 BENCH-001 的事件数口径（采样点数差一个数量级）→ 指标字典 §2、EXP-000 X-003 |

### 处置后复查（2026-07-31）

对照改动后的文档复查了一遍，发现处置本身留下的问题，已一并修正：

| 编号 | 问题 | 处置 |
|---|---|---|
| R-001 | ADR-006 §2 把「观察到决策的间隔 ≥ 1」也一并禁止，属**多余约束**——3→4 沿 class 递增，键本就严格递增 | 收紧为只约束 `latency_ns ≥ 1`（唯一回退 class 的跳转）；ADR-006 §2、FR-007、event-schema §1.1、T001b 同步 |
| R-002 | BENCH-001.yaml 用裸浮点字面量，`yaml.safe_load` 直接产出 `float`，ADR-005 §2「禁止 float 中转」在自己的基准配置上即失效 | 领域量改为带引号字符串并加书写约定；ADR-005 §2 补可执行规则与适用范围（墙钟阈值除外）；已验证解析后无 float |
| R-003 | 追溯链止于 `information_set`，无法机器验证「观察来自哪一次行情发布」 | `AGENT_OBSERVE` 增 `market_data_event_id`；§5.1 路径、ADR-006 §3、E-002 排除清单同步 |
| R-004 | KPI-012 追溯指向 `methodology.md` §9—§10，但方法论无对应条款 | 新增 methodology §10.1 单维度对照条款，追溯改指 §10.1 |
| R-006 | `target_order_id` 是否参与摘要哈希，ADR-006 §6（排除）与 event-schema E-002（纳入）相互矛盾 | 统一为**纳入**，ADR-006 §6 补明例外理由；排除清单改列 `market_data_event_id` |
| R-007 | ADR-006 §4 标题误写 SC-007（守恒），实际对应 SC-008（引用完整性） | 改正为 SC-008 |

R-006、R-007 由 2026-07-31 的下一轮检视报告发现，属本轮处置引入的疏漏，已在同一
提交中修正。该轮报告的其余发现另行处置。

**仍未关闭**（需决策，见下）：

- **H-001 余项**：EXP-000 的「固定条件」至今只有名字没有值（市场制度、费率、初始
  价格、代理总数、初始资金与持仓分布、观察频率与延迟），**四类代理的基线构成比例
  也未定**。已冻结的是扫描维度与分析口径，不是被扫的市场本身——`EXP-000.yaml` 目前
  仍生成不出来。BENCH-001 是性能基准（代理构成「只求有代表性」），不能直接充当研究
  基线。该项阻塞 EXP-000 冻结，进而阻塞 T000i。
- **R-005**：`lag*` 检查范围写窄。主要指标表规定 `ACF_r` 查 lag 1—20，`lag*` 超出即
  标「不适用」；而 `lag* = τ/λ`，τ 网格跨 32 倍（25→800），λ ≈ 1 笔/秒时 τ=800 对应
  `lag* = 800`。照此高 τ 半张表会自动判「不适用」，而「lag ≈ τ 处无峰」正是本实验
  自称的核心防线。需把 `lag*` 邻域检查独立于自相关检验并扩大范围（2500 点序列可算
  到 lag ≈ 250），并在冻结前用试运行标定 λ，确认 τ 网格与运行长度匹配——可能要回头
  调 X-001 或 X-003。

除以上两项与 T000i 本身（评审并冻结，M0 唯一剩余项）外，报告已全部闭环。

**Severity legend**:

- **Critical**：会直接导致数据破坏、安全事故或结论完全失真，必须立即修复。
- **High**：会阻断 M0 冻结、核心正确性或研究结论可信度，应在实现前修复。
- **Medium**：存在跨文档矛盾、边界语义或工程治理缺口，应在对应功能实现前修复。
- **Low**：不会阻断当前阶段，但会增加后续维护成本。

## Executive Summary

文档体系已经相当完整：PRD、方法论、指标字典、ADR、事件 Schema、退化状态、
任务拆解、性能基准和预注册实验协议均已建立，需求编号连续，本地 Markdown 链接检查
未发现失效链接。当前主要缺口不是继续增加文档种类，而是把现有合同收紧到“可冻结、
可执行、可验收”的程度。

本次发现 8 项：3 High、5 Medium。建议暂不执行 T000i；先关闭前三项 High，再统一
状态与路线图口径，001 规格即可进入正式评审。

## High Findings

### H-001：EXP-000 尚不能作为可执行的预注册协议

**位置**：

- `docs/experiments/EXP-000-baseline-validation.md:28`
- `docs/experiments/EXP-000-baseline-validation.md:29`
- `docs/experiments/EXP-000-baseline-validation.md:32`
- `docs/experiments/EXP-000-baseline-validation.md:52`
- `docs/experiments/EXP-000-baseline-validation.md:68`
- `docs/experiments/EXP-000-baseline-validation.md:83`
- `docs/product/metrics-dictionary.md:85`

**问题**：

协议把 `τ` 扫描点保留为 G-004 待定，同时把半衰期离散度 `σ` 列为固定条件，却又要求
实验输出 `σ` 初值建议。若 `σ` 不进入自变量或敏感性分析，仅靠 `τ × p_trend` 扫描无法
识别 `σ` 的合适范围。此外，协议没有冻结研究运行时长/终止条件，无法保证指标字典要求
的至少 2000 个采样点；“显著大于正态”“前若干 lag”“配对检验”“自助法置信区间”等
也没有指定具体检验、lag 集合、置信水平、重采样次数和多重检验 family。

**影响**：

协议现在无法生成唯一的机器可执行实验配置，运行后仍有较大的分析自由度，预注册防止
选择性报告的目标不能真正成立。

**建议**：

1. 新增研究配置 `experiments/EXP-000.yaml`，冻结所有固定条件、运行时长、种子集合和
   完整 `τ` 网格。
2. 将 `σ` 纳入第三维扫描，或增加一个预先声明的 `σ` 敏感性子实验；否则删除“回写
   σ 建议”的承诺。
3. 明确统计检验、零假设、显著性阈值、lag 集合、置信水平、bootstrap 次数及 BH
   校正所覆盖的假设族。
4. 在协议冻结前增加机器校验：每次有效研究运行必须达到 2000 个采样点。

### H-002：金额、数量与手续费的精度及舍入合同缺失

**位置**：

- `specs/001-market-simulation-foundation/spec.md:45`
- `specs/001-market-simulation-foundation/spec.md:47`
- `docs/product/metrics-dictionary.md:74`
- `docs/product/metrics-dictionary.md:160`
- `benchmarks/BENCH-001.yaml:27`
- `benchmarks/BENCH-001.yaml:28`
- `benchmarks/BENCH-001.yaml:30`

**问题**：

价格已规定内部使用整数 tick，但数量、现金、名义金额、maker/taker 手续费、返佣以及
已实现 PnL 没有规定数值表示和舍入方向。基准配置使用 `0.01`、`0.001` 和 bps 小数；
如果实现直接使用二进制浮点，每事件后的严格现金/库存守恒可能因累计舍入误差失败。
负 maker 费率还需要明确返佣精度和最小结算单位。

**影响**：

这是订单准入、手续费预冻结、账户不为负和 KPI-001 守恒验收的共同基础。若留到编码时
临时决定，不同模块很容易采用不同舍入口径。

**建议**：

新增“数值与结算口径”合同或 ADR：

- 价格、数量、现金均采用最小单位整数，或统一使用 `Decimal`；
- 明确配置字符串到内部值的解析规则；
- 明确名义金额、maker/taker 费用、返佣和 PnL 的舍入模式及舍入时点；
- 定义不可整除数量/费用余数的处理方式；
- 将这些规则加入订单准入、部分成交和守恒属性测试。

### H-003：KPI-007 的因果追溯链没有被事件 Schema 强制表达

**位置**：

- `specs/001-market-simulation-foundation/spec.md:38`
- `specs/001-market-simulation-foundation/event-schema.md:62`
- `specs/001-market-simulation-foundation/event-schema.md:69`
- `specs/001-market-simulation-foundation/event-schema.md:86`
- `specs/001-market-simulation-foundation/event-schema.md:102`
- `specs/001-market-simulation-foundation/event-schema.md:113`
- `specs/001-market-simulation-foundation/event-schema.md:144`
- `specs/001-market-simulation-foundation/event-schema.md:149`

**问题**：

Schema 有观察、决策、订单和成交事件，但没有显式的因果外键。`ORDER_ARRIVAL` 没有
`decision_event_id` / `intent_id`，`AGENT_DECIDE` 没有 `observation_event_id`，
撤单也没有明确关联其触发决策。默认只记录 `information_set` 摘要，因此“完整链路”
还依赖用当前代码重新运行一次，而不是仅靠原始证据包完成审计。

**影响**：

同一代理一次决策产生多条意图、连续决策或重放代码版本变化时，无法可靠证明某笔订单
来自哪次观察与哪条规则。KPI-007 可能在展示层看似可用，但没有可机器验证的完整性。

**建议**：

- 为事件增加稳定的 `observation_event_id`、`decision_event_id`、`intent_id` 和必要的
  `caused_by_event_id`；
- 定义从 `trade_id → order_id → intent_id → decision → observation → account events`
  的可验证路径和引用完整性断言；
- 正式研究运行保存完整信息集，或保存可独立还原它的版本化证据包；摘要模式仅用于性能
  基准；
- 增加一项验收：随机抽取/遍历全部成交，因果链必须完整且引用对象唯一存在。

## Medium Findings

### M-001：同时间戳内新增高优先级事件的语义未定义

**位置**：

- `specs/001-market-simulation-foundation/spec.md:52`
- `specs/001-market-simulation-foundation/spec.md:72`
- `specs/001-market-simulation-foundation/event-schema.md:36`
- `specs/001-market-simulation-foundation/event-schema.md:40`
- `specs/001-market-simulation-foundation/event-schema.md:44`

**问题**：

`AGENT_DECIDE` 可能产生订单；若通信延迟配置为 0，它会在当前时间戳新增 class 0 的
`ORDER_ARRIVAL`。该事件的优先级小于当前 class 4，却是在 class 4 处理后才入队，因而
“数值越小越先处理”的同时间戳语义无法成立。类似问题也可能由结算后发布、观察后立即
决策形成。

**建议**：

冻结以下规则之一：

- 禁止零延迟，并要求新事件的全序键严格大于当前事件；或
- 定义同时间戳 microstep/phase 轮次，把轮次纳入全序键；或
- 明确允许回到较小 class，并重写“同时间戳优先级”的语义与相关测试。

### M-002：FR-012 与事件 Schema 对 NaN 的要求直接冲突，JSONL 也无标准 NaN

**位置**：

- `specs/001-market-simulation-foundation/spec.md:61`
- `specs/001-market-simulation-foundation/spec.md:63`
- `specs/001-market-simulation-foundation/event-schema.md:95`
- `specs/001-market-simulation-foundation/plan.md:11`

**问题**：

FR-012 要求退化状态不得产出 NaN，而事件 Schema 和指标字典要求未定义报价记为 NaN；
同时 JSON 标准不支持 NaN，直接写入 JSONL 会产生非标准数据或序列化失败。

**建议**：
  
区分“领域状态不可出现非法 NaN”与“输出层缺失值”：事件 JSONL 统一使用 `null`，
Parquet 使用 null，分析层读取后再映射为 NaN；同步修改 FR-012、事件 Schema 和指标
字典的表述，并把 canonical serialization 纳入 schema 版本合同。

### M-003：Q-009 在 PRD 中已关闭，但基础规格仍列为未决

**位置**：

- `docs/product/prd.md:424`
- `specs/001-market-simulation-foundation/spec.md:122`
- `specs/001-market-simulation-foundation/spec.md:126`
- `specs/001-market-simulation-foundation/tasks.md:15`

**问题**：

PRD 和任务表都声明 Q-009 已由基准协议关闭，`spec.md` 仍将它列为未决问题。001 规格
无法在这种状态下无歧义地转为 Approved。

**建议**：

将 Q-009 移到 `spec.md` 的已决策列表并链接 `benchmarks/README.md` 与
`reference-machine.md`。保留 CALIB-001 实测值和 golden 值为实现/校准任务，而不是
产品决策未决项。

### M-004：基准验证的里程碑验收口径错位

**位置**：

- `docs/product/prd.md:353`
- `docs/product/prd.md:355`
- `docs/product/prd.md:374`

**问题**：

M2 明确要输出首份基准市场验证报告，但 M2 退出条件没有 KPI-008；KPI-008 反而放在
M3 退出条件中。这样 M2 可以在验证报告不满足“通过/失败/不适用 + 排除率”时形式上
退出，与“先验证市场，再解释策略”的治理原则不一致。

**建议**：

把 KPI-008 移入 M2 退出条件。M3 保留 KPI-005、KPI-006、KPI-009、KPI-010，并增加
能力异质性阶段自己的因果归因验收指标。

### M-005：本机权限文件未被忽略

**位置**：

- `.claude/settings.local.json:4`
- `.claude/settings.local.json:5`
- `.gitignore:1`

**问题**：

未跟踪的 `.claude/settings.local.json` 包含本机用户名路径和宽泛的用户目录读取权限，
而 `.gitignore` 未忽略该文件。它不是项目可移植配置，也不应进入公开仓库。

**建议**：

在 `.gitignore` 增加 `.claude/settings.local.json`（或整个 `.claude/`，若没有共享配置
需求）。如需共享 Claude 配置，另建不含本机路径和本地授权的最小模板。

## Positive Observations

- PRD 的 PR-001—PR-019、KPI-001—KPI-011 编号连续，追溯表覆盖完整。
- ADR-001 至 ADR-004 与 PRD、规格和任务之间已有较清晰的双向链接。
- 退化状态不是简单终止，而是完整保存并报告排除率，研究设计意识很好。
- 每代理 RNG 分流、整数逻辑时间和事件全序为配对实验与确定性打下了可靠基础。
- 区分性能基准 `BENCH-001` 与研究基准 `EXP-000` 是正确方向。
- 本地 Markdown 链接检查未发现失效目标。

## Summary

| Severity | Count |
|---|---:|
| Critical | 0 |
| High | 3 |
| Medium | 5 |
| Low | 0 |
| **Total** | **8** |

## Bottom Line

项目现在已经不缺“框架型文档”，缺的是四份更硬的实现合同：可执行的 EXP-000 配置、
数值/舍入 ADR、带因果外键的事件 Schema、以及同时间戳调度规则。完成前三项 High 并
消除状态矛盾后，再执行 T000i 冻结，会比直接进入编码阶段稳妥得多。
