---
kind: milestone
id: 0.4.3
parent: v0.4-market-ecology
version: "0.4"
doc_kind: tasks
gate_version: 1
created: 2026-09-25
updated: 2026-09-25
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

- [ ] T1100 `[阻塞·须先裁决]`: **T1002（策略层与账本的名义口径不一致）的处置裁决**
      — 0.4.1 §17.6 已证明两个「装配可调、不必动冻结契约」的强度挂载点均不可用，
      只剩账本保证金闸口，而它属冻结契约。裁决前本里程碑无法确定强度参数挂在哪里
      — verify: [`0.4.1 实验报告 §17.6`](../../../experiments/0.4.1-market-quality-baseline.md)
- [ ] T1101 `[阻塞·须先修订]`: **修订 [`ADR-011`](../../../decisions/011-market-engine-trader-layering.md)
      §决策 2**（明文禁止外生价值过程）。不得绕开：用注入路径实现等价机制等于规避
      一条明写的决策（[锚选型材料 §5](../../../research/exogenous-price-anchor-options.md)）
      — verify: `python tools/validate_spec_lifecycle.py`
- [ ] T1102 (`Q-701`, `Q-702`): 冻结 `v_t` 的形态、参数与信息层归属；常数形态已被
      0.4.1 §14 实测排除（价格钉死、异质性塌陷）— verify: `tests/unit/metrics/`

## 2. 实现任务

### Phase 1：价值过程与价值族

- [ ] T1103 (`FR-701`, `AC-701`): 实现 `v_t` 求值与运行头记录；同参数同种子逐点复现；
      对 `v_t` 自身做 stylized facts 检验并断言**波动聚集与厚尾不通过**（正反两侧）
      — verify: `tests/unit/metrics/test_value_process.py`
- [ ] T1104 (`FR-702`, `AC-702`): 实现价值投资者族，目标仓位随 `(price − v_t)/v_t` 的
      绝对值单调增大；走既有撮合/账本/风控路径 — verify:
      `tests/unit/agent/test_value_family.py`
- [ ] T1105 (`NFR-701`, `AC-702`): 强度参数的 **binding 与单调性**各一条实测断言，
      复用 0.4.1 的 `metrics/binding_diagnosis.py`；任一不满足即 fail closed
      — verify: `tests/integration/test_anchor_strength.py`
- [ ] T1106 `[成果门:H2-E4]` (`FR-701`, `FR-702`, `E3`): 产出装配含价值族的可运行市场与
      其运行头，价格不再单调发散、窗口末仍有成交；证据标签 `engineering-demonstration`
      — verify: `tests/integration/test_anchored_market.py`

### Phase 2：归因与达标

- [ ] T1107 (`FR-703`, `AC-703`): 关闭价值族的同种子对照运行随报告落盘，两轮判定可比
      — verify: `tests/integration/test_attribution_control.py`
- [ ] T1108 (`AC-705`): 锚过强的检出——价格倍数过低 + 异质性塌陷（0.4.1 §14 的实测
      形态）须被判出并如实记录，**不得判达标** — verify:
      `tests/integration/test_anchor_too_strong.py`
- [ ] T1109 `[成果门:H2-E5]` (`SC-701`, `SC-702`, `AC-704`, `E1`, `E2`): 跨种子质量报告
      集合——E3/E4 在**原口径下**的达标判定；未达标时如实产出未通过报告，
      **不得调门限**；证据标签 `engineering-demonstration`
      — verify: `tests/integration/test_market_quality_gate.py`

## 3. 验证与验收任务

- [ ] T1110 (`AC-701`, `AC-702`): 运行 `v_t` 复现、价值族单调性与强度前置的正反测试
      — verify: `tests/unit/metrics/test_value_process.py`
- [ ] T1111 (`AC-703`, `AC-705`): 运行归因对照与锚过强检出的测试
      — verify: `tests/integration/test_attribution_control.py`
- [ ] T1112 (`AC-704`): 运行达标与未达标两条路径的门禁测试
      — verify: `tests/integration/test_market_quality_gate.py`
- [ ] T1113 (`AC-701`—`AC-705`): 运行项目统一质量门，确认 0.4.1 与 0.3.1 路径无回归
      — verify: `python tools/verify.py`
- [ ] T1114 `[状态门]`: 回写 spec 验收证据、版本索引与状态；必须是本文件最后一项
      — verify: `python tools/validate_spec_lifecycle.py`

## 4. 依赖与并行关系

- `T1100, T1101 -> T1102`：强度挂载点与 ADR 修订都未定时，参数冻结没有依据。
- `T1102 -> T1103 -> T1104 -> T1105 -> T1106`：价值过程、族、强度前置、成果门依次串行。
- `T1106 -> T1107 [P]` 与 `T1106 -> T1108 [P]`：归因对照与锚过强检出互不共享状态。
- `T1107, T1108 -> T1109 -> T1110, T1111, T1112 -> T1113 -> T1114`。

## 5. 明确后移

- **实盘行情数据与快照分叉** → [`ADR-014`](../../../decisions/014-historical-snapshot-fork-anchor.md)
  与其独立里程碑；本里程碑的 `v_t` 是合成过程，不依赖任何行情源。
- **多标的与横截面因子** → 独立 Feature。
- **人类扰动实验** → [`0.4.2`](../0.4.2-human-perturbation/spec.md)。
- **形态 3（外部信号携带价值观点）** → 不采纳为锚的实现路径：锚性质会由一个允许静默
  降级的组件提供（[锚选型材料 §5](../../../research/exogenous-price-anchor-options.md)）；
  外部信号接口本身在 0.4.1 已交付，保持其原定位。
