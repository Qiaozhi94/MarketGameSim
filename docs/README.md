# docs —— 文档地图与所有权索引

本文只记录**什么信息由谁拥有**和入口链接，不复制状态、需求、合同或设计正文。从本文
出发最多两次点击可到达任一权威文档。

## 信息 → 唯一拥有者

| 信息 | 唯一拥有者 |
|---|---|
| 产品目标、范围、安全边界 | [`docs/market-game-sim-prd.md`](market-game-sim-prd.md) |
| 全局模块边界与技术不变量 | [`docs/market-game-sim-architecture.md`](market-game-sim-architecture.md) |
| 指标、研究方法与解释边界 | [`docs/research/`](research/methodology.md)（methodology、metrics-dictionary） |
| 跨 Feature 实现合同 | [`docs/contracts/`](contracts/matching.md) |
| 长期架构决策（ADR） | [`docs/decisions/`](decisions/000-template.md) |
| Feature/里程碑行为与状态 | 对应 `spec.md`（见 [`docs/features/README.md`](features/README.md)） |
| Feature/里程碑实现方案 | 对应 `design.md`（见 [`docs/features/README.md`](features/README.md)） |
| requirement owner 与 exit | [`docs/features/0.1/traceability.json`](features/0.1/traceability.json) |
| 开发纪律与质量门 | [`docs/SOP.md`](SOP.md) |
| 当前项目入口和强提醒 | [`CLAUDE.md`](../CLAUDE.md) |
| 实验协议与结果索引 | [`docs/experiments/`](experiments/experiment-template.md) |
| 性能基准与判定协议 | [`benchmarks/`](../benchmarks/README.md) |
| 检视与复盘报告 | [`docs/reviews/`](reviews/RETROSPECTIVE.md) |

## 文档职责边界

- README、CLAUDE、版本 README 只是**派生入口**，不得成为状态/需求/合同的第二份
  机器可读声明。
- `spec.md` frontmatter 是状态唯一真源；design/tasks 不得声明独立状态。
- architecture 不复制字段级合同；Feature design 不重新定义全局不变量。
- release / RETROSPECTIVE 不是当前产品或实现真相源。

## 验证入口

唯一公开验证入口：`python tools/verify.py`（真源、生命周期、链接、所有权、pytest、
ruff）。
