---
kind: version-spec
id: v0.3-human-in-the-loop-crash-experiment
version: "0.3"
status: draft
research_claim_status: not-established
research_claim_required: true
evidence_class: formal-research
created: 2026-09-04
updated: 2026-09-12
---

# Feature Specification: AI Mechanism Baseline & Web Trading Terminal

**规格编号**：v0.3-human-in-the-loop-crash-experiment（**历史标识**：主证据轨道已在
2026-09-06 重置为 AI 机制基线，编号与目录名保留只为不破坏既有 traceability 与链接，不代表
当前范围）<br>
**关联 PRD**：[`../../market-game-sim-prd.md`](../../market-game-sim-prd.md) §15 H2<br>
**架构**：[`design.md`](design.md)<br>
**里程碑**：[`0.3.1`](0.3.1-human-in-the-loop-experiment/spec.md)（AI 正式基线）→
[`0.3.2`](0.3.2-web-trading-terminal/spec.md)（Web 终端与所有者采集）

## 问题与目标

H2 分成两个可独立收口的里程碑：`0.3.1` 在无外生基本面冲击的合成永续市场中，用 **168 个**
配对 seed block 检验冻结纯代理策略的价格崩盘、流动性枯竭和强平机制；`0.3.2` 再提供可见价格、
K 线和交互按钮，让项目所有者完成个人 N-of-1 场景。两者不合并样本量，不招募外部真人，不建立
人群结论。

**研究声明只能挂在 AI 轨道上。** 所有者 N-of-1 轨的证据级别是 `experiment-preview`：它是
n=1 自我实验，[`SOP`](../../SOP.md) §2 把样本量 1、有学习效应的运行排除在统计之外，
[`features/README`](../README.md) 也规定只有 `formal-research` 能建立研究声明。本版本的
`research_claim_status` 因此只由 AI 轨证据决定。

本版本把 `0.3.1` 的主要机制推断限定为冻结 AI 策略在 paired-seed 分布上的差异；`0.3.2`
的所有者结果限定为本人、冻结任务与场景分布，且必须声明所有者同时是设计者与被试这一不可消除偏倚。
两个里程碑各自拥有完整的实验边界与验收正文。

## 非目标

- 不估计脱离参与者、任务和模型族的抽象“人类效应”，不外推到真实市场。
- 不连接真实市场、真实账户或资金，不提供交易信号或投资建议。
- 不把 H1 `interactive` 会话、试运行、培训局或预览运行升级为正式证据。
- 不引入外生价格/基本面冲击，不把三个结果家族合成单一得分。

## 用户场景

- **US-301**：执行配对的 AI 正式实验；正文见 [`0.3.1 spec §2`](0.3.1-human-in-the-loop-experiment/spec.md#2-用户场景)。
- **US-302**：审计 AI 决策来源的行为机制；正文见 [`0.3.1 spec §2`](0.3.1-human-in-the-loop-experiment/spec.md#2-用户场景)。
- **US-303**：生成边界清晰的 AI 正式结论；正文见 [`0.3.1 spec §2`](0.3.1-human-in-the-loop-experiment/spec.md#2-用户场景)。

## 功能需求

- **FR-301**：冻结 H2 协议与配对反事实；正文见 [`0.3.1 spec §4`](0.3.1-human-in-the-loop-experiment/spec.md#4-需求)。
- **FR-302**：运行受控的所有者替换会话；正文见 [`0.3.2 spec §4`](0.3.2-web-trading-terminal/spec.md#4-需求)。
- **FR-303**：隔离培训、预览与正式样本；正文见 [`0.3.1 spec §4`](0.3.1-human-in-the-loop-experiment/spec.md#4-需求)。
- **FR-304**：分别计算三个结果家族；正文见 [`0.3.1 spec §4`](0.3.1-human-in-the-loop-experiment/spec.md#4-需求)。
- **FR-305**：记录并分析预注册机制指标；正文见 [`0.3.1 spec §4`](0.3.1-human-in-the-loop-experiment/spec.md#4-需求)。
- **FR-306**：生成 H2 正式证据包；正文见 [`0.3.1 spec §4`](0.3.1-human-in-the-loop-experiment/spec.md#4-需求)。

## 数据、事件与接口需求

- **DR-301**：协议、参与者、分配与会话数据最小化；正文见 [`0.3.1 spec §4`](0.3.1-human-in-the-loop-experiment/spec.md#4-需求)。
- **TR-301**：正式运行头绑定协议与配对标识；正文见 [`0.3.1 spec §4`](0.3.1-human-in-the-loop-experiment/spec.md#4-需求)。
- **TR-302**：所有者行动保留完整因果链；正文见 [`0.3.2 spec §4`](0.3.2-web-trading-terminal/spec.md#4-需求)。
- **IR-301**：提供锁定的所有者 Web 会话入口；正文见 [`0.3.2 spec §4`](0.3.2-web-trading-terminal/spec.md#4-需求)。
- **IR-302**：正式证据入口 fail closed；正文见 [`0.3.1 spec §4`](0.3.1-human-in-the-loop-experiment/spec.md#4-需求)。

## 非功能需求

- **NFR-301**：结果可复现且配对反事实不可变；正文见 [`0.3.1 spec §4`](0.3.1-human-in-the-loop-experiment/spec.md#4-需求)。
- **NFR-302**：所有者隐私、退出与本地数据边界明确；正文见 [`0.3.2 spec §4`](0.3.2-web-trading-terminal/spec.md#4-需求)。
- **NFR-303**：故障与排除规则不得由结果反向决定；正文见 [`0.3.1 spec §4`](0.3.1-human-in-the-loop-experiment/spec.md#4-需求)。

## 成功与退出

- **SC-301**：冻结且机器可验证的 H2 协议；正文见 [`0.3.1 spec §6`](0.3.1-human-in-the-loop-experiment/spec.md#6-成功与验收)。
- **SC-302**：正式样本与配对纯代理反事实完整；正文见 [`0.3.1 spec §6`](0.3.1-human-in-the-loop-experiment/spec.md#6-成功与验收)。
- **SC-303**：三类结果与机制指标按预注册方法独立报告；正文见 [`0.3.1 spec §6`](0.3.1-human-in-the-loop-experiment/spec.md#6-成功与验收)。
- **SC-304**：证据包可复建、可审计且不越过模型边界；正文见 [`0.3.1 spec §6`](0.3.1-human-in-the-loop-experiment/spec.md#6-成功与验收)。

版本级需求归属与退出条件由 [`traceability.json`](traceability.json) 唯一拥有。

## 已确认决策

1. AI 正式比较是 threshold 与 linear 冻结策略在同一目标插槽、同 seed 下的差异，由 0.3.1 收口。
2. 所有者 Web 终端与采集是 0.3.2 的后续范围，完成后再进行所有者训练和正式场景。
3. 价格崩盘、流动性枯竭与强平连锁是三个独立结果家族，不使用综合分数。
4. 激进订单、流动性撤回和风险减仓首先作为预注册机制分析；未经额外识别设计不声称
   因果中介效应。
5. H1 自由交互与 H2 培训/预览数据永不进入正式样本。

## 待确认事项

参与者类型已由 [`H2-dual-track-contract`](../../experiments/H2-dual-track-contract.md) 重置：
外部真人、报酬和招募平台均为零；0.3.1 的样本单位是 168 个 AI paired-seed block，0.3.2
才执行项目所有者的 6 个训练和 24 个正式 N-of-1 paired blocks。旧真人功效与预算证据保留但已
废止，其中的 130 是参与者数而非 block 数，不得沿用。0.3.1 与 0.3.2 各自按本里程碑的 preview
与 Web 验收推进，不互相阻塞。
