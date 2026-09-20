---
kind: version-spec
id: v0.4-market-ecology
version: "0.4"
status: draft
research_claim_status: not-applicable
research_claim_required: false
evidence_class: engineering-demonstration
created: 2026-09-20
updated: 2026-09-20
---

# Feature Specification: AI 市场生态与 L2 交易者策略层

**规格编号**：v0.4-market-ecology<br>
**关联 PRD**：[`../../market-game-sim-prd.md`](../../market-game-sim-prd.md) §15<br>
**架构**：[`design.md`](design.md)<br>
**架构决策**：[`ADR-011`](../../decisions/011-market-engine-trader-layering.md)（L1/L2 分层与
alphamill 单向边界）、[`ADR-010`](../../decisions/010-market-ecology-research-pivot.md)（研究方向）<br>
**研究北极星**：[`../../research/owner-research-question.md`](../../research/owner-research-question.md)<br>
**里程碑**：[`0.4.1`](0.4.1-ai-market-ecology/spec.md)（L2 交易者策略层与市场真实性判据）、
[`0.4.2`](0.4.2-human-perturbation/spec.md)（人类扰动实验 H2-F：同种子对照下的稳定性效应量）

## 问题与目标

v0.1 已证明合成市场在 `SPONTANEOUS` 族下可以自发交易并支撑正式研究声明，但两件事
没有做到，而 owner 的研究问题恰好都压在它们上面：

1. **持续运行路径上的市场是死的**。`live_market`（1:1 实时、owner 随时进出的载体）
   实测 3.0 笔成交/分钟、52.3% 的秒无双边盘口、中位盘口档位 (1, 1)，
   根因是冷启动死锁与单一策略模板（口径见 [`ADR-011`](../../decisions/011-market-engine-trader-layering.md) 背景表）。
2. **离散的崩盘与流动性枯竭事件从未出现过**。`0.1.5-evidence-index.json` 的
   `experimental_validity` 显示：两个目标模型 × 三个处理对比 × 两个结果家族，
   全部 `occurrence` 假设的 `nonzero_block_counts` 均为 **0 / 128 blocks**；
   v0.1 的研究声明是由连续的 `severity` 指标建立的。

本版本交付 L1 交易引擎与 L2 交易者策略层的正式分层，使市场在持续运行路径上会自发
成交、由异质策略族形成价格，并用可复现的数字判定它像不像一个市场。

**本版本不建立研究声明**：`evidence_class` 为 `engineering-demonstration`，
`research_claim_required: false`。`0.4.1` 交付 owner 研究问题 #1/#3 所需的**对照基线**
与市场载体；`0.4.2`（`experiment-preview`）承接北极星的**第一**研究问题「人类扰动」，
交付会话 artifact 冻结格式、同种子对照与效应量报告，但同样不建立研究声明——是否升级为
`formal-research` 由 [`0.4.2 Q-601`](0.4.2-human-perturbation/spec.md#8-待确认问题) 裁决。

## 非目标

- 不引入外生基本面、价值过程、财报或市值数据；价值投资者族不做
  （[`ADR-011`](../../decisions/011-market-engine-trader-layering.md) §决策 2）。
- 不做多标的合约池；Alpha101 的横截面算子（`rank`）因此不在可用子集内。
- 不修改 L1 既有合同（撮合、账本、保证金、强平、事件 schema、确定性口径）。
- 不把沙盘盈亏写成任何策略的有效性证据，也不回流 alphamill 证据链。
- `0.4.1` 不执行人类扰动实验本身；本版本整体不产生任何研究声明。
- 不做 owner 个人画像、不判定 owner 操作对错、不复活固定场次/跨度的受控框架。

## 用户场景

- **US-501**：看到一个会自己活动的市场；正文见 [`0.4.1 spec §2`](0.4.1-ai-market-ecology/spec.md#2-用户场景)。
- **US-502**：用异质策略族装配市场；正文见 [`0.4.1 spec §2`](0.4.1-ai-market-ecology/spec.md#2-用户场景)。
- **US-503**：把外部量化策略接进沙盘；正文见 [`0.4.1 spec §2`](0.4.1-ai-market-ecology/spec.md#2-用户场景)。
- **US-601**：自由进出市场并留下可分析的记录；正文见 [`0.4.2 spec §2`](0.4.2-human-perturbation/spec.md#2-用户场景)。
- **US-602**：比较有没有人类时的市场稳定性；正文见 [`0.4.2 spec §2`](0.4.2-human-perturbation/spec.md#2-用户场景)。

## 功能需求

- **FR-501**：消除冷启动死锁；正文见 [`0.4.1 spec §4`](0.4.1-ai-market-ecology/spec.md#4-需求)。
- **FR-502**：提供可插拔的 L2 交易者策略层；正文见 [`0.4.1 spec §4`](0.4.1-ai-market-ecology/spec.md#4-需求)。
- **FR-503**：按清单装配并运行异质策略族市场；正文见 [`0.4.1 spec §4`](0.4.1-ai-market-ecology/spec.md#4-需求)。
- **FR-504**：量化交易者族与 alphamill 单向边界；正文见 [`0.4.1 spec §4`](0.4.1-ai-market-ecology/spec.md#4-需求)。
- **FR-505**：市场真实性判据与门；正文见 [`0.4.1 spec §4`](0.4.1-ai-market-ecology/spec.md#4-需求)。
- **FR-601**：冻结 owner 自由会话 artifact 格式；正文见 [`0.4.2 spec §4`](0.4.2-human-perturbation/spec.md#4-需求)。
- **FR-602**：同种子对照运行（无人类基线 vs 有人类）；正文见 [`0.4.2 spec §4`](0.4.2-human-perturbation/spec.md#4-需求)。
- **FR-603**：稳定性效应量报告；正文见 [`0.4.2 spec §4`](0.4.2-human-perturbation/spec.md#4-需求)。
- **FR-604**：扰动即数据，不判对错、不做画像；正文见 [`0.4.2 spec §4`](0.4.2-human-perturbation/spec.md#4-需求)。

## 数据、事件与接口需求

- **DR-501**：记录可重建装配的策略族清单；正文见 [`0.4.1 spec §4`](0.4.1-ai-market-ecology/spec.md#4-需求)。
- **DR-502**：记录带门限与逐项判定的市场质量报告；正文见 [`0.4.1 spec §4`](0.4.1-ai-market-ecology/spec.md#4-需求)。
- **TR-501**：策略族决策连入既有因果链并可回溯族标识；正文见 [`0.4.1 spec §4`](0.4.1-ai-market-ecology/spec.md#4-需求)。
- **IR-501**：提供 TraderStrategy 协议与策略族注册入口；正文见 [`0.4.1 spec §4`](0.4.1-ai-market-ecology/spec.md#4-需求)。
- **IR-502**：提供非阻塞的外部策略信号注入接口；正文见 [`0.4.1 spec §4`](0.4.1-ai-market-ecology/spec.md#4-需求)。
- **DR-601**：记录可重放的人类扰动会话；正文见 [`0.4.2 spec §4`](0.4.2-human-perturbation/spec.md#4-需求)。
- **DR-602**：记录带区间与失效边界的效应量报告；正文见 [`0.4.2 spec §4`](0.4.2-human-perturbation/spec.md#4-需求)。
- **TR-601**：owner 委托同路径进入因果链并可区分参与者类别；正文见 [`0.4.2 spec §4`](0.4.2-human-perturbation/spec.md#4-需求)。
- **IR-601**：沿用既有终端与非阻塞注入路径的人类参与与回放入口；正文见 [`0.4.2 spec §4`](0.4.2-human-perturbation/spec.md#4-需求)。

## 非功能需求

- **NFR-501**：纯 AI 市场以 1:1 实时运行；正文见 [`0.4.1 spec §4`](0.4.1-ai-market-ecology/spec.md#4-需求)。
- **NFR-502**：同装配同种子的价格序列逐点可复现；正文见 [`0.4.1 spec §4`](0.4.1-ai-market-ecology/spec.md#4-需求)。
- **NFR-503**：沙盘产出不进入证据索引也不回流 alphamill；正文见 [`0.4.1 spec §4`](0.4.1-ai-market-ecology/spec.md#4-需求)。
- **NFR-601**：人类在场不改变 L1 语义与 AI 侧确定性；正文见 [`0.4.2 spec §4`](0.4.2-human-perturbation/spec.md#4-需求)。
- **NFR-602**：owner 会话产物不含身份信息且不进入既有证据索引；正文见 [`0.4.2 spec §4`](0.4.2-human-perturbation/spec.md#4-需求)。

## 成功与退出

- **SC-501**：纯 AI 市场自发成交且市场质量六项达标；正文见 [`0.4.1 spec §6`](0.4.1-ai-market-ecology/spec.md#6-成功与验收)。
- **SC-502**：stylized facts 达到冻结条数；正文见 [`0.4.1 spec §6`](0.4.1-ai-market-ecology/spec.md#6-成功与验收)。
- **SC-503**：内生不稳定事件的存在性判定（达标或如实判定为不存在）；正文见 [`0.4.1 spec §6`](0.4.1-ai-market-ecology/spec.md#6-成功与验收)。
- **SC-504**：量化交易者族可装配且可审计；正文见 [`0.4.1 spec §6`](0.4.1-ai-market-ecology/spec.md#6-成功与验收)。
- **SC-601**：会话 artifact 格式在第一场之前冻结且可重放；正文见 [`0.4.2 spec §6`](0.4.2-human-perturbation/spec.md#6-成功与验收)。
- **SC-602**：同种子两臂可配对且基线逐点可复现；正文见 [`0.4.2 spec §6`](0.4.2-human-perturbation/spec.md#6-成功与验收)。
- **SC-603**：结论以效应量形态给出（分布移动 + 区间 + 失效边界）；正文见 [`0.4.2 spec §6`](0.4.2-human-perturbation/spec.md#6-成功与验收)。
- **SC-604**：不产出对错判定、行为画像与身份信息；正文见 [`0.4.2 spec §6`](0.4.2-human-perturbation/spec.md#6-成功与验收)。

版本级需求归属与退出条件由 [`traceability.json`](traceability.json) 唯一拥有。

## 已确认决策

1. L1 交易引擎与 L2 交易者策略层正式分层，L2 只能读分级信息集、只能输出目标仓位或
   委托意图，不持有账本引用、不调用撮合、不写事件（ADR-011）。
2. 不引入外生基本面与价值投资者族；市场价格只由订单流与策略互动决定。
3. 「真实有效」的判据是市场质量六项 + stylized facts 五项，不是「用了多少真实策略」；
   门限值由 `0.4.1 spec §6` 唯一拥有，修改须留 git 痕迹与理由。
4. Alpha101 只取纯时序子集；含 `rank`/`IndNeutralize`/`cap` 的公式在装配时 fail closed。
5. alphamill 单向消费：沙盘结果永不进入其证据链，也不构成任何策略有效性的证据。
6. 人类扰动的研究命题形态是**效应量命题**（同种子对照下稳定性指标的分布移动 + 区间 +
   失效边界），不是「人类能否造成崩盘」——后者在允许高杠杆大单量时自我实现，不可证伪；
   条款正文由 [`PRD §15`](../../market-game-sim-prd.md#15-交付路线图) 唯一拥有。

## 待确认事项

**内生崩盘的存在性是开放问题，不是工程指标。** v0.1 的 128 个 paired block 中
`occurrence` 事件一次都没有出现过，因此「异质策略族 + 杠杆反馈能否产生离散的崩盘或
流动性枯竭」在本版本开工时是未知的。若 0.4.1 跑完仍未出现，结论是「该市场结构在
冻结参数下不产生离散崩盘事件」——这是一个如实的发现，**不是未达标**，也不允许通过
调低门限来制造通过。owner 研究问题 #2 的答案由此产生，无论它是哪一个方向。
