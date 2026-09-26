---
kind: milestone
id: 0.4.3
parent: v0.4-market-ecology
version: "0.4"
doc_kind: tasks
gate_version: 1
created: 2026-09-25
updated: 2026-09-26
---

# 0.4.3：外生价格锚 - 任务

> Owner: TBD | Spec: `spec.md` | Design: `design.md`

## 0. 来源与执行规则

- 行为与验收真相源：[`spec.md`](spec.md)。技术方案与边界：[`design.md`](design.md)。
- 每项任务只描述一个可验证动作，并引用合法的 US/需求/AC ID。
- 每个 Phase 的最后一项任务是成果门；成果门必须产出可打开页面或可消费的 artifact。
- **G1 研究问题前置检查**：本交付服务
  [`owner-research-question`](../../../research/owner-research-question.md) 的研究问题 #2
  「AI 市场自身的均衡与突变」——0.4.1 已证明当前市场会单调发散并停止成交，
  没有一个价格有界的市场，均衡与突变都无从谈起。**待 owner 批准。**
- 判据、门限与口径全部引自 0.4.1 spec §6，**任务不得就地改门限**。
- L1 合同不可改。

## 1. 前置条件

- [ ] T1100: **修 `families/_common.py::max_position_units` 的量纲缺陷**（原 T1002 的
      0.4.1 那一份）—— `max_position = max_notional // mark` 少除一个 `MULT`，导致策略层
      给出的目标相当于约 2000 倍杠杆，而 `risk_appetite_x1000` 的校验范围 `[500, 20000]`
      说明该字段的设计语义是 0.5—20 倍（实验报告 §19.3）。**这是策略层违反自身契约，
      不是整洁性问题。**
      **代价接近零**（§20.2）：0.4.1 产物不进任何 evidence index（NFR-503），且 MULT 补丁与
      2 倍封顶两次实验都显示市场结果逐项相同（`max_order_qty` 与保证金闸口截断在更前面）。
      与 `T1104` 同轮落地，共用一次盖章。
      **本条不是锚的强度挂载点**（§18.5：强度不挂在任何容量约束上），而是让价值族的容量
      参数不被静默改写的前提。
      **验收必须包含**：全窗口（5700 逻辑秒）行为不变的断言——§20.4 的「行为不变」只验证到
      约 1800 秒，不得假定它在全窗口成立
      — verify: `tests/unit/agent/test_position_ceiling_units.py`（正反两侧：修正后隐含杠杆
      落在契约范围内、修正前的口径被哨兵抓出）+ 全窗口行为不变的集成断言
- [ ] T1101 `[已知缺陷·本里程碑不修]`: **`agent/goal.py::RiskBudgetLinearV1` 的同一处量纲
      缺陷**（原 T1002 的 v0.1 那一份，第 512 行）。`_common.py` 当初复制了该算法，
      **连缺陷一起复制**（§20.1）。**本里程碑不修**：改它会让 v0.1/v0.2 签收证据失效，
      且经济等价证明会失败（`goal_belief` 代理的仓位会真的缩小），只能全量重跑 T215 的
      128 块 × 16 次运行；且 v0.1 目标层还乘了 `signal_bp` 缩放，影响需单独评估。
      **它不阻塞本里程碑**——0.4.3 用的是 families 那份。等有独立理由（如 v0.5 重建证据链）
      再一并处理
      — verify: 实验报告 [`§20.3`](../../../experiments/0.4.1-market-quality-baseline.md)
- [ ] T1102 `[阻塞·待 owner 裁决]`: 采纳
      [`ADR-017`](../../../decisions/017-allow-constant-exogenous-price-reference.md)
      （有限修订 ADR-011 §决策 2，2026-09-26 起草，状态 Proposed）——**允许恒定或确定性
      外生参照，仍禁止随机价值过程**。窄修订的理由是保全研究问题 #2：恒定参照不会移动、
      不能制造任何价格动态，故崩盘仍是市场自己的行为；随机 `v_t` 则会让任何崩盘都可归因
      于它的路径。不得绕开：用 I3 注入路径实现等价机制等于规避一条明写的决策
      （[锚选型材料 §5](../../../research/exogenous-price-anchor-options.md)）
      — verify: `python tools/validate_spec_lifecycle.py`
- [ ] T1103 (`Q-701`, `Q-702`): 冻结 `v_t` 的形态、参数与信息层归属；纯恒定形态已被
      0.4.1 §14 实测排除（价格钉死、异质性塌陷），随机过程被 ADR-017 排除，故候选只剩
      「确定性非随机路径」— verify: `tests/unit/metrics/`
- [ ] T1104 `[量级哨兵]` (`NFR-701`): 在族层仓位上限处加一条**量级哨兵**——计算出的上限
      若隐含杠杆超出现实可能范围（**100 倍**，取自现实交易所的最大杠杆量级，非拍定值）
      即 fail closed，因为那说明**单位错了而不是参数大**。
      **零行为代价已实测**（0.4.1 §19.6：封顶 100/10/2 倍时市场结果逐项相同，
      连降 1000 倍都不改变成交与价格，因为 `max_order_qty` 截断在更前面）；
      **它本来就能抓住 T1002**——在第一次计算时抓住，而不是靠账本静默吸收。
      随 `T1100` 的动力学改动一并落地（同一轮盖章）
      — verify: `tests/unit/agent/test_leverage_tripwire.py`（正反两侧：超限 fail closed、
      现实范围内照常放行；变异验证：去掉哨兵后 T1002 的 2000 倍口径必须不再被抓出）

## 2. 实现任务

### Phase 1：价值过程与价值族

- [ ] T1105 (`FR-701`, `AC-701`): 实现 `v_t` 求值与运行头记录；同参数同种子逐点复现；
      对 `v_t` 自身做 stylized facts 检验并断言**波动聚集与厚尾不通过**（正反两侧）
      — verify: `tests/unit/metrics/test_value_process.py`
- [ ] T1106 (`FR-702`, `AC-702`): 实现价值投资者族，目标仓位随 `(price − v_t)/v_t` 的
      绝对值单调增大；走既有撮合/账本/风控路径 — verify:
      `tests/unit/agent/test_value_family.py`
- [ ] T1107 (`NFR-701`, `AC-702`): 强度参数的 **binding 与单调性**各一条实测断言，
      复用 0.4.1 的 `metrics/binding_diagnosis.py`；任一不满足即 fail closed
      — verify: `tests/integration/test_anchor_strength.py`
- [ ] T1108 `[成果门:H2-E4]` (`FR-701`, `FR-702`, `E3`): 产出装配含价值族的可运行市场与
      其运行头，价格不再单调发散、窗口末仍有成交；证据标签 `engineering-demonstration`
      — verify: `tests/integration/test_anchored_market.py`

### Phase 2：归因与达标

- [ ] T1109 (`FR-703`, `AC-703`): 关闭价值族的同种子对照运行随报告落盘，两轮判定可比
      — verify: `tests/integration/test_attribution_control.py`
- [ ] T1110 (`AC-705`): 锚过强的检出——价格倍数过低 + 异质性塌陷（0.4.1 §14 的实测
      形态）须被判出并如实记录，**不得判达标** — verify:
      `tests/integration/test_anchor_too_strong.py`
- [ ] T1111 `[成果门:H2-E5]` (`SC-701`, `SC-702`, `AC-704`, `E1`, `E2`): 跨种子质量报告
      集合——E3/E4 在**原口径下**的达标判定；未达标时如实产出未通过报告，
      **不得调门限**；证据标签 `engineering-demonstration`
      — verify: `tests/integration/test_market_quality_gate.py`

## 3. 验证与验收任务

- [ ] T1112 (`AC-701`, `AC-702`): 运行 `v_t` 复现、价值族单调性与强度前置的正反测试
      — verify: `tests/unit/metrics/test_value_process.py`
- [ ] T1113 (`AC-703`, `AC-705`): 运行归因对照与锚过强检出的测试
      — verify: `tests/integration/test_attribution_control.py`
- [ ] T1114 (`AC-704`): 运行达标与未达标两条路径的门禁测试
      — verify: `tests/integration/test_market_quality_gate.py`
- [ ] T1115 (`AC-701`—`AC-705`): 运行项目统一质量门，确认 0.4.1 与 0.3.1 路径无回归
      — verify: `python tools/verify.py`
- [ ] T1116 `[状态门]`: 回写 spec 验收证据、版本索引与状态；必须是本文件最后一项
      — verify: `python tools/validate_spec_lifecycle.py`

## 4. 依赖与并行关系

- `T1100, T1102 -> T1103`：量纲修正与 ADR-017 裁决都未落地时，`v_t` 参数冻结没有依据。
  `T1101` 无前置（冻结契约缺陷登记，本里程碑不修）。
- `T1100` 与 `T1104` **同一轮落地**：两者都改 src，攒在一起走一次盖章（省一轮经济等价证明）。
- `T1103 -> T1105 -> T1106 -> T1107 -> T1108`：价值过程、族、强度前置、成果门依次串行。
- `T1108 -> T1109 [P]` 与 `T1108 -> T1110 [P]`：归因对照与锚过强检出互不共享状态。
- `T1109, T1110 -> T1111 -> T1112, T1113, T1114 -> T1115 -> T1116`。

## 5. 明确后移

- **实盘行情数据与快照分叉** → [`ADR-014`](../../../decisions/014-historical-snapshot-fork-anchor.md)
  与其独立里程碑；本里程碑的 `v_t` 是合成过程，不依赖任何行情源。
- **多标的与横截面因子** → 独立 Feature。
- **人类扰动实验** → [`0.4.2`](../0.4.2-human-perturbation/spec.md)。
- **形态 3（外部信号携带价值观点）** → 不采纳为锚的实现路径：锚性质会由一个允许静默
  降级的组件提供（[锚选型材料 §5](../../../research/exogenous-price-anchor-options.md)）；
  外部信号接口本身在 0.4.1 已交付，保持其原定位。
