---
kind: version-design
id: v0.3-human-in-the-loop-crash-experiment
version: "0.3"
doc_kind: design
created: 2026-09-04
updated: 2026-09-04
---

# v0.3：Human-in-the-loop Crash Experiment - 设计

## 设计边界

v0.3 复用同一离散事件内核、撮合、账本、保证金、强平与指标合同；新增受协议约束的
`human-experiment` 运行编排、配对纯代理反事实、参与者匿名元数据和独立正式证据入口。
H1 `interactive` 客户端只能作为交互基础，不能直接成为正式实验入口。

## 跨里程碑不变量

- 正式人类会话和纯代理反事实共享代码、制度配置、初始状态、背景代理、种子与逻辑时长；
  唯一预定差异是目标代理的决策来源。
- `run_mode=human-experiment` 不等于自动合格；协议哈希、样本阶段、完整性和排除状态全部
  合法时才可进入 H2 evidence index。
- 人类只见冻结信息集，并在冻结操作窗口内行动；正式运行不允许暂停、单步或临时改配置。
- 参与者标识使用研究假名；身份映射、联系方式、支付信息不得进入运行日志或成果包。
- 三个结果家族分别计算、分别呈现；机制指标不替代主要结果。

## 里程碑映射

- [`0.3.1-human-in-the-loop-experiment/design.md`](0.3.1-human-in-the-loop-experiment/design.md)：
  协议状态机、运行 contract、配对分析、证据门与参与者边界。

