---
kind: milestone
id: 0.4.3
parent: v0.4-market-ecology
version: "0.4"
doc_kind: tasks
gate_version: 1
created: 2026-09-25
updated: 2026-10-04
---

# 0.4.3：外生价格锚 - 任务

> Owner: qiaozhi li | Spec: `spec.md` | Design: `design.md`

## 0. 来源与执行规则

- 行为与验收真相源：[`spec.md`](spec.md)。技术方案与边界：[`design.md`](design.md)。
- 每项任务只描述一个可验证动作，并引用合法的 US/需求/AC ID。
- 每个 Phase 的最后一项任务是成果门；成果门必须产出可打开页面或可消费的 artifact。
- **G1 研究问题前置检查**（owner 2026-10-04 批准）：本交付为
  [`owner-research-question`](../../../research/owner-research-question.md) 的研究问题
  **#1（人类扰动）与 #3（人机相互作用）提供候选载体**——二者都需要一个能活过测量窗口的
  市场；[`0.4.2`](../0.4.2-human-perturbation/spec.md) 是否以本里程碑的锚定市场为载体，
  由 0.4.2 自己的规格裁决。本交付**不服务研究问题 #2**：#2 已在无锚条件下得到回答
  （0.4.1 报告 §8：单调发散到 7.1 倍后停止成交，零追保零强平），且按
  [`ADR-017`](../../../decisions/017-allow-constant-exogenous-price-reference.md)
  防污染条款，装锚后的任何运行不得被引用为 #2 的证据。
- 判据、门限与口径全部引自 0.4.1 spec §6，**任务不得就地改门限**。
- L1 合同不可改；`TraderStrategy` 协议与 `PROTOCOL_VERSION` 不改（`IR-701`）。

## 1. 前置条件

- [x] T1100 (`NFR-701`, `AC-702`): **修 `families/_common.py::max_position_units` 的量纲
      缺陷**（原 T1002 的 0.4.1 那一份）—— `max_position = max_notional // mark` 少除一个
      `MULT`，导致策略层给出的目标相当于约 2000 倍杠杆，而 `risk_appetite_x1000` 的校验
      范围 `[500, 20000]` 说明该字段的设计语义是 0.5—20 倍（实验报告 §19.3）。**这是策略层
      违反自身契约，不是整洁性问题。**
      **`MULT` 的来源**：族层沿用 `DEFAULT_MULT`，装配时断言 `engine.mult == DEFAULT_MULT`，
      不等即 fail closed——不允许族层与引擎的合约乘数静默不一致。
      0.4.1 产物不进任何 evidence index（NFR-503），无冻结证据影响。与 `T1104` 同轮落地，
      共用一次盖章。
      **本条不是锚的强度挂载点**（§18.5：强度不挂在任何容量约束上），而是让价值族的容量
      参数不被静默改写的前提。
      **全窗口实测**（§20.4 要求补测）：「行为不变」**被证伪**——修正后无锚基线约 2000 秒
      停摆（原约 2700 秒），机制是均值回归族失去虚高容量（0.4.1 报告 §21）。owner 2026-10-04
      裁决照修、如实记录、不调族参数；原「全窗口行为不变」断言随之取消，代之以报告 §21 的
      实测记录与下列集成级回归锁
      — verify: `tests/unit/agent/test_position_ceiling_units.py`（正反两侧：修正后隐含杠杆
      落在契约范围内、修正前的口径被哨兵抓出；`engine.mult` 不一致时装配拒绝）+
      `tests/integration/test_binding_diagnosis.py::test_margin_gate_no_longer_binds_once_the_ceiling_has_units`
      （退回旧公式即变红）
- [x] T1101 `[已知缺陷·本里程碑不修]` (`NFR-701`): **`agent/goal.py` 里 v0.1 冻结契约的
      同一处量纲缺陷，共两份**：`RiskBudgetLinearV1`（约第 512 行）与
      `RiskBudgetThresholdV1`（约第 591 行，H2 处理组在用）。`_common.py` 当初复制了该算法，
      **连缺陷一起复制**（§20.1）。**本里程碑不修**：改它们会让 v0.1/v0.2 签收证据失效，
      且经济等价证明会失败（`goal_belief` 与 H2 处理组代理的仓位会真的缩小），只能全量重跑
      T215 的 128 块 × 16 次运行；且 v0.1 目标层还乘了 `signal_bp` 缩放，影响需单独评估。
      **它不阻塞本里程碑**——0.4.3 用的是 families 那份。本条只交付显式标记：两份各一条
      `xfail(strict=True)` 测试，断言隐含杠杆落在 `risk_appetite_x1000` 的契约范围内并写明
      不修原因——缺陷一旦被意外修复，测试转红要求人工确认
      — verify: `tests/unit/agent/test_goal_position_ceiling_known_defect.py`
- [x] T1102: 采纳
      [`ADR-017`](../../../decisions/017-allow-constant-exogenous-price-reference.md)
      （有限修订 ADR-011 §决策 2）——**owner 2026-10-04 收窄采纳：只允许恒定外生参照**；
      随机价值过程、确定性时变路径、逐代理价值分散仍禁止。收窄理由：ADR 自身的论证
      「恒定参照不会移动，因此不能制造价格动态」只覆盖恒定形态。不得绕开：用 I3 注入
      路径实现等价机制等于规避一条明写的决策
      （[锚选型材料 §5](../../../research/exogenous-price-anchor-options.md)）
      — verify: `python tools/validate_spec_lifecycle.py`
- [x] T1103 (`Q-701`, `Q-702`): 冻结 `v_t` 的形态与可见性——**owner 2026-10-04 裁决**：
      形态为恒定值 `v_t ≡ engine.initial_price_ticks`，强度改由价值族响应函数承载（§14 的
      钉死对应强度无穷大，不是形态的后果）；只对价值族可见、人类终端不显示，落地路径为
      逐代理私有参数通道（`IR-701`，文档检视后修订）。结论唯一拥有者：spec §8 Q-701/Q-702
      — verify: `python tools/validate_spec_lifecycle.py`
- [x] T1104 `[量级哨兵]` (`NFR-701`, `AC-702`): 在族层仓位上限处加一条**量级哨兵**——计算出的上限
      若隐含杠杆超出现实可能范围（**100 倍**，取自现实交易所的最大杠杆量级，非拍定值）
      即 fail closed，因为那说明**单位错了而不是参数大**。
      **零行为代价已实测**（0.4.1 §19.6：封顶 100/10/2 倍时市场结果逐项相同，
      连降 1000 倍都不改变成交与价格，因为 `max_order_qty` 截断在更前面）；
      **它本来就能抓住 T1002**——在第一次计算时抓住，而不是靠账本静默吸收。
      随 `T1100` 的动力学改动一并落地（同一轮盖章）
      — verify: `tests/unit/agent/test_leverage_tripwire.py`（正反两侧：超限 fail closed、
      现实范围内照常放行；变异验证：去掉哨兵后 T1002 的 2000 倍口径必须不再被抓出）

## 2. 实现任务

### Phase 1：锚定市场

- [x] T1105 (`FR-701`, `IR-701`, `AC-701`, `AC-706`): 价值族装配时派生
      `v_t = engine.initial_price_ticks` 并写入该族代理的 `strategy_private`；断言 `v_t`
      收益在整个窗口恒为 0（正反两侧：恒定通过、任一时刻取值变化即失败）；断言其他族代理
      的私有参数与所有分级信息集不含 `v_t`、`PROTOCOL_VERSION` 仍为 1、人类终端载荷不含
      `v_t`（正反两侧）
      — verify: `tests/unit/agent/test_value_reference.py`
- [x] T1106 (`FR-702`, `AC-702`): 实现 `value_investor` 族与其 roster 参数校验
      （`sensitivity_x1000 ∈ [1, 1000000]`）；目标仓位方向与偏离相反、幅度随偏离单调不减、
      以族层仓位上限封顶；走既有撮合/账本/风控路径
      — verify: `tests/unit/agent/test_value_family.py`
- [x] T1107 (`NFR-701`, `SC-704`, `AC-702`): 强度参数的 **binding**（复用 0.4.1 的
      `metrics/binding_diagnosis.py`）与**单调性**（新建：多档强度 × 全窗口 × 价格倍数，
      实测方式参照 0.4.1 §17.2 表）实测断言：`sensitivity_x1000` 做 binding 与单调性，
      `count` 只做单调性（其 binding 构造上恒真）；任一不满足即 fail closed，换响应函数
      形式重做，最多两种（第二种实测前预注册），两种都失败按 spec §5 以 `UNQUALIFIED` 收口。
      **须在 `T1100` 落地后执行**——修正前的仓位上限口径会改变哪个约束 binding。
      **结果（2026-10-04）**：两个旋钮均 MONOTONE、`sensitivity` 12 秒内 BINDING，首种响应函数
      形式通过；但 `sensitivity` 100 与 1000 之间是悬崖（≤100 只延缓发散，≥1000 钉在 ±0.6%），
      T1109 网格须在该段加密（[实验报告 §2](../../../experiments/0.4.3-anchored-market.md)）
      — verify: `tests/integration/test_anchor_strength.py`（读入库产物
      `docs/experiments/0.4.3-anchor-strength.json`，由 `python -m market_game_sim.metrics.anchor_strength` 生成）
- [ ] T1108 `[成果门:H2-E4]` (`US-701`, `NFR-702`, `AC-707`): 产出装配含价值族的可运行
      市场与其 roster 清单：运行满 5700 逻辑秒价格不单调发散、窗口末仍有成交，同 roster
      同种子重跑价格序列逐点一致；证据标签 `engineering-demonstration`
      — verify: `tests/integration/test_anchored_market.py`

### Phase 2：扫描与判定

- [ ] T1109 (`SC-704`, `AC-708`): **预注册**强度网格（`count` × `sensitivity_x1000` 的取值
      清单）、种子集合与 spec `SC-704` 的两条扫描筛选判据（含分段口径），写入
      单一文件并**先于任何扫描运行提交**；扫描入口只读该文件，文件缺失或内容哈希与扫描记录不一致时 fail closed
      — verify: `tests/unit/metrics/test_anchor_scan_preregistration.py`
- [ ] T1110 (`SC-701`, `SC-702`, `AC-705`): 质量报告顶部新增锚过强诊断字段（各族主动成交
      占比、`trend_following` 主动成交笔数——即 0.4.1 §15 的第三条判据、窗口价格区间、
      下跌分段数），**不改变** SC-701/SC-702 的判定（ADR-016 裁决 B）
      — verify: `tests/integration/test_anchor_heterogeneity_diagnostics.py`
- [ ] T1111 `[成果门:H2-E5]` (`SC-701`, `SC-702`, `AC-704`): 按预注册文件扫完整个网格；
      通过两条扫描筛选判据的配置做 SC-701/SC-702 的跨种子完整测量；产出跨种子质量报告集合与
      终点判定——`QUALIFIED`（存在达标配置）或 `UNQUALIFIED`（逐格未通过报告）。
      **不得调门限、不得在扫描后改网格**；证据标签 `engineering-demonstration`
      — verify: `tests/integration/test_anchored_quality_gate.py`

## 3. 验证与验收任务

- [ ] T1112 (`AC-701`, `AC-702`, `AC-706`): 运行 `v_t` 恒定与可见性、价值族单调性、
      强度前置与量级哨兵的正反测试
      — verify: `tests/unit/agent/test_value_reference.py`、
      `tests/unit/agent/test_value_family.py`、`tests/integration/test_anchor_strength.py`、
      `tests/unit/agent/test_leverage_tripwire.py`
- [ ] T1113 (`AC-705`, `AC-708`): 运行锚过强诊断与预注册守卫的测试
      — verify: `tests/integration/test_anchor_heterogeneity_diagnostics.py`、
      `tests/unit/metrics/test_anchor_scan_preregistration.py`
- [ ] T1114 (`AC-704`, `AC-707`): 运行锚定市场与达标/未达标两条终点的门禁测试
      — verify: `tests/integration/test_anchored_market.py`、
      `tests/integration/test_anchored_quality_gate.py`
- [ ] T1115 (`AC-701`—`AC-708`): 运行项目统一质量门，确认 0.4.1 与 0.3.1 路径无回归
      — verify: `python tools/verify.py`
- [ ] T1116 `[状态门]`: 回写 spec 验收证据、版本索引与状态；必须是本文件最后一项
      — verify: `python tools/validate_spec_lifecycle.py`

## 4. 依赖与并行关系

- `T1100` 与 `T1104` **同一轮落地**：两者都改 src，攒在一起走一次盖章（省一轮经济等价证明）。
  `T1101` 无前置（冻结契约缺陷的显式标记，本里程碑不修）。`T1102`、`T1103` 已完成。
- `T1105 -> T1106`：价值族依赖 `v_t` 的下发通道。
- `T1100, T1104, T1106 -> T1107 -> T1108`：强度诊断须在仓位上限口径修正后执行。
- `T1108 -> T1109 -> T1111`：预注册必须先于扫描提交。
- `T1108 -> T1110 [P]`：诊断字段与预注册互不共享状态。
- `T1110, T1111 -> T1112, T1113, T1114 -> T1115 -> T1116`。

## 5. 明确后移

- **实盘行情数据与快照分叉** → [`ADR-014`](../../../decisions/014-historical-snapshot-fork-anchor.md)
  与其独立里程碑；本里程碑的 `v_t` 是恒定参照，不依赖任何行情源。
- **多标的与横截面因子** → 独立 Feature。
- **人类扰动实验** → [`0.4.2`](../0.4.2-human-perturbation/spec.md)。
- **形态 3（外部信号携带价值观点）** → 不采纳为锚的实现路径：锚性质会由一个允许静默
  降级的组件提供（[锚选型材料 §5](../../../research/exogenous-price-anchor-options.md)）；
  外部信号接口本身在 0.4.1 已交付，保持其原定位。
- **`agent/goal.py` 两份冻结契约缺陷的修复**（`T1101`）→ 等有独立理由（如 v0.5 重建证据链）
  再一并处理。
