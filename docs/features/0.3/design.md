---
kind: version-design
id: v0.3-human-in-the-loop-crash-experiment
version: "0.3"
doc_kind: design
created: 2026-09-04
updated: 2026-09-06
---

# v0.3：AI Mechanism Baseline & Personal Decision Lab - 设计

## 设计边界

v0.3 复用同一离散事件内核、撮合、账本、保证金、强平与指标合同；新增 130 个
paired-seed blocks 的 `ai-mechanism-experiment` 正式轨，以及仅项目所有者使用的
`owner-n-of-1` 个人轨。两轨共享市场内核和配对字段，但使用独立 evidence index；H1
`interactive` 只能作为交互基础，不能直接成为正式实验入口。

## 跨里程碑不变量

- AI 正式 paired block 共享代码、制度配置、初始状态、背景代理、seed 与逻辑时长；唯一
  预定差异是目标插槽的冻结 AI 策略。
- `ai-mechanism-experiment` 与 `owner-n-of-1` 使用独立 manifest 和 evidence index，任何跨轨
  样本合并均 fail closed。
- 所有者只见冻结信息集并在冻结窗口内行动；正式运行不允许暂停、单步或临时改配置。
- 不招募外部真人，不建立身份映射、联系方式或支付数据。
- 三个结果家族分别计算、分别呈现；机制指标不替代主要结果。

## 里程碑映射

- [`0.3.1-human-in-the-loop-experiment/design.md`](0.3.1-human-in-the-loop-experiment/design.md)：
  协议状态机、运行 contract、配对分析、证据门与参与者边界。

