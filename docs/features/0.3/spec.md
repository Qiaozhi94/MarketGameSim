---
kind: version-spec
id: v0.3-human-in-the-loop-crash-experiment
version: "0.3"
status: draft
research_claim_status: not-established
research_claim_required: true
evidence_class: formal-research
created: 2026-09-04
updated: 2026-09-05
---

# Feature Specification: Human-in-the-loop Crash Experiment

**规格编号**：v0.3-human-in-the-loop-crash-experiment<br>
**关联 PRD**：[`../../market-game-sim-prd.md`](../../market-game-sim-prd.md) §15 H2<br>
**架构**：[`design.md`](design.md)<br>
**首个里程碑**：[`0.3.1`](0.3.1-human-in-the-loop-experiment/spec.md)

## 问题与目标

H2 回答：在无外生基本面冲击的合成永续市场中，当账户、初始状态、信息集、动作空间与
决策窗口一致时，真实人类决策相对于预注册纯代理参照策略，是否会改变价格崩盘、流动性
枯竭与强平连锁的发生和严重程度；若发生改变，该差异是否与人类的激进订单、流动性撤回
或风险减仓行为相一致？相对于原方向性目标代理的差异只作次要描述。

本版本把主要推断对象限定为“协议化人类决策相对于预注册纯代理参照策略”的差异，并要求
可观测接口与决策机会对齐。完整研究问题、估计量、实验边界与验收正文由
[`0.3.1 spec`](0.3.1-human-in-the-loop-experiment/spec.md) 唯一拥有。

## 非目标

- 不估计脱离参与者、任务和模型族的抽象“人类效应”，不外推到真实市场。
- 不连接真实市场、真实账户或资金，不提供交易信号或投资建议。
- 不把 H1 `interactive` 会话、试运行、培训局或预览运行升级为正式证据。
- 不引入外生价格/基本面冲击，不把三个结果家族合成单一得分。

## 用户场景

- **US-301**：执行配对的人在环实验；正文见 [`0.3.1 spec §2`](0.3.1-human-in-the-loop-experiment/spec.md#2-用户场景)。
- **US-302**：审计人类行为机制；正文见 [`0.3.1 spec §2`](0.3.1-human-in-the-loop-experiment/spec.md#2-用户场景)。
- **US-303**：生成边界清晰的正式结论；正文见 [`0.3.1 spec §2`](0.3.1-human-in-the-loop-experiment/spec.md#2-用户场景)。

## 功能需求

- **FR-301**：冻结 H2 协议与配对反事实；正文见 [`0.3.1 spec §4`](0.3.1-human-in-the-loop-experiment/spec.md#4-需求)。
- **FR-302**：运行受控的人类替换会话；正文见 [`0.3.1 spec §4`](0.3.1-human-in-the-loop-experiment/spec.md#4-需求)。
- **FR-303**：隔离培训、预览与正式样本；正文见 [`0.3.1 spec §4`](0.3.1-human-in-the-loop-experiment/spec.md#4-需求)。
- **FR-304**：分别计算三个结果家族；正文见 [`0.3.1 spec §4`](0.3.1-human-in-the-loop-experiment/spec.md#4-需求)。
- **FR-305**：记录并分析预注册机制指标；正文见 [`0.3.1 spec §4`](0.3.1-human-in-the-loop-experiment/spec.md#4-需求)。
- **FR-306**：生成 H2 正式证据包；正文见 [`0.3.1 spec §4`](0.3.1-human-in-the-loop-experiment/spec.md#4-需求)。

## 数据、事件与接口需求

- **DR-301**：协议、参与者、分配与会话数据最小化；正文见 [`0.3.1 spec §4`](0.3.1-human-in-the-loop-experiment/spec.md#4-需求)。
- **TR-301**：正式运行头绑定协议与配对标识；正文见 [`0.3.1 spec §4`](0.3.1-human-in-the-loop-experiment/spec.md#4-需求)。
- **TR-302**：人类行动保留完整因果链；正文见 [`0.3.1 spec §4`](0.3.1-human-in-the-loop-experiment/spec.md#4-需求)。
- **IR-301**：提供锁定的实验会话入口；正文见 [`0.3.1 spec §4`](0.3.1-human-in-the-loop-experiment/spec.md#4-需求)。
- **IR-302**：正式证据入口 fail closed；正文见 [`0.3.1 spec §4`](0.3.1-human-in-the-loop-experiment/spec.md#4-需求)。

## 非功能需求

- **NFR-301**：结果可复现且配对反事实不可变；正文见 [`0.3.1 spec §4`](0.3.1-human-in-the-loop-experiment/spec.md#4-需求)。
- **NFR-302**：参与者隐私、同意与退出边界明确；正文见 [`0.3.1 spec §4`](0.3.1-human-in-the-loop-experiment/spec.md#4-需求)。
- **NFR-303**：故障与排除规则不得由结果反向决定；正文见 [`0.3.1 spec §4`](0.3.1-human-in-the-loop-experiment/spec.md#4-需求)。

## 成功与退出

- **SC-301**：冻结且机器可验证的 H2 协议；正文见 [`0.3.1 spec §6`](0.3.1-human-in-the-loop-experiment/spec.md#6-成功与验收)。
- **SC-302**：正式样本与配对纯代理反事实完整；正文见 [`0.3.1 spec §6`](0.3.1-human-in-the-loop-experiment/spec.md#6-成功与验收)。
- **SC-303**：三类结果与机制指标按预注册方法独立报告；正文见 [`0.3.1 spec §6`](0.3.1-human-in-the-loop-experiment/spec.md#6-成功与验收)。
- **SC-304**：证据包可复建、可审计且不越过模型边界；正文见 [`0.3.1 spec §6`](0.3.1-human-in-the-loop-experiment/spec.md#6-成功与验收)。

版本级需求归属与退出条件由 [`traceability.json`](traceability.json) 唯一拥有。

## 已确认决策

1. 主要比较是单个人类决策与预注册纯代理参照策略在同一冻结目标插槽中的差异；原方向性
   目标代理另作次要描述性对照。
2. 主假设为双侧：人类既可能放大，也可能抑制内生崩盘反馈。
3. 价格崩盘、流动性枯竭与强平连锁是三个独立结果家族，不使用综合分数。
4. 激进订单、流动性撤回和风险减仓首先作为预注册机制分析；未经额外识别设计不声称
   因果中介效应。
5. H1 自由交互与 H2 培训/预览数据永不进入正式样本。

## 待确认事项

样本量、参与者激励、目标代理身份、操作窗口和伦理审查边界由 0.3.1 的开放问题决定；
问题关闭、协议冻结并通过预览验收前，本版本保持 `draft`。

