---
kind: milestone-tasks
id: 0.1.5
version: "0.1"
doc_kind: tasks
created: 2026-08-14
updated: 2026-08-15
---

# 0.1.5：目标驱动代理与旗舰实验识别 - 任务

> Spec: `spec.md` | Design: `design.md`

## 0. 来源与执行规则

- 行为与验收真相源：[`spec.md`](spec.md)；技术边界：[`design.md`](design.md)。
- 每项实现先补正反回归测试；批量代理、成交与四 cell 必须有多记录场景。
- 完成并验证后立即勾选；若合同失效，先修订三件套再继续。
- T203—T206 分别承接 0.1.2 T404—T407，不能在原任务中伪造完成。
- 本里程碑按 [`PRD §15`](../../../market-game-sim-prd.md#15-交付路线图) 的 R1—R5
  逐门交付；每个成果门都必须生成可打开产物，不能等 T216 时一次性展示。

## 1. 前置条件

- [ ] **T201** (`FR-021`—`FR-027`): 更新代理、事件、实验与证据 Contract，并冻结 Schema 版本 — verify: `python tools/verify.py`
- [ ] **T202** (`FR-024`, `SC-010`): 冻结 `2 × 2`、三终点家族、seed plan 与排除规则预注册 — verify: `docs/experiments/`

## 2. 实现任务

### Phase 0：R1 可打开的工程基线

- [ ] **T200** `[成果门:R1]` (`FR-027`, `AC-011`): 为现有已验证管线增加单命令成果入口，
      在 `artifacts/showcase/latest/` 生成 `RUN.md`、`manifest.json`、原始日志、
      `replay.html` 与 `summary.md`；证据级别固定为 `engineering-demonstration`，不得写入
      正式 evidence index — verify: `tests/integration/test_showcase_bundle.py`

### Phase 1：目标、信息与遗留代理链

- [ ] **T203** (`FR-021`, `AC-001`): 实现目标模型接口、linear/threshold 模型与独立制度约束层，承接 0.1.2 T404 — verify: `tests/unit/agent/`
- [ ] **T204** (`FR-021`, `AC-001`): 迁移库存型做市商目标与报价风险政策，承接 0.1.2 T405 — verify: `tests/unit/agent/`
- [ ] **T205** (`FR-022`, `FR-025`, `AC-002`, `AC-005`): 实现公开 tape、逐代理游标、观察/决策证据链，承接 0.1.2 T406 — verify: `tests/integration/`
- [ ] **T206** (`FR-022`, `NFR-005`, `AC-002`): 固化多代理构建、零仓位、K 线、EWMA 与确定性测试，承接 0.1.2 T407 — verify: `tests/unit/agent/`
- [ ] **T207** `[成果门:R2]` (`FR-027`, `AC-001`, `AC-002`, `AC-005`): 用固定种子生成目标驱动代理
      单次运行成果包，回放至少一条“观察—目标—约束—订单—成交”链；证据级别固定为
      `engineering-demonstration` — verify: `tests/integration/test_goal_driven_showcase.py`

### Phase 2：运行族与证据权限

- [ ] **T208** (`FR-023`, `IR-501`, `AC-003`): 实现三运行族配置闭集与 fail-closed 允许/拒绝矩阵 — verify: `tests/unit/experiment/`
- [ ] **T209** (`FR-023`, `DR-501`, `AC-004`): 实现 `StressProtocolV1`、四 cell 同路径校验和 `EXOGENOUS_STRESS` provenance — verify: `tests/unit/experiment/`
- [ ] **T210** (`FR-025`, `TR-501`, `TR-502`, `AC-005`): 扩展决策事件与全链独立验证器 — verify: `tests/integration/`
- [ ] **T211** (`FR-026`, `IR-502`, `AC-008`): 实现 evidence class 与跨族报告/聚合权限守卫 — verify: `tests/unit/experiment/`

### Phase 3：正式旗舰实验

- [ ] **T212** (`FR-024`, `AC-006`): 实现四 cell 配对 seed plan 与三终点独立统计计划 — verify: `tests/integration/`
- [ ] **T213** `[成果门:R3]` (`FR-024`, `FR-027`, `AC-006`, `AC-007`): 用小种子计划生成四 cell ×
      三终点比较表与代表性回放；manifest 标记 `experiment-preview`，报告显式拒绝正式结论
      措辞 — verify: `tests/integration/test_flagship_preview.py`
- [ ] **T214** (`FR-024`, `SC-010`, `AC-007`): 运行校准/验证后冻结的正式 `SPONTANEOUS` 实验 — verify: `docs/experiments/`
- [ ] **T215** (`FR-026`, `DR-502`, `SC-011`, `AC-009`): 生成正式 evidence index 与条件性结论 — verify: `docs/experiments/`
- [ ] **T216** `[成果门:R4]` (`FR-024`, `FR-026`, `FR-027`, `AC-007`, `AC-009`): 交付三终点正式
      结果、效应量/不确定性、代表性回放与可复现 manifest；仅允许
      `SPONTANEOUS + formal-research` — verify: `docs/experiments/`

## 3. 验证与验收任务

- [ ] **T217** (`AC-001`—`AC-012`): 逐项核对退出条件、批量回归与正式证据路径 — verify: `python tools/verify.py`
- [ ] **T218** (`AC-001`—`AC-012`): 运行项目统一质量门和确定性复现 — verify: `python tools/verify.py`
- [ ] **T219** (`FR-026`, `AC-009`, `AC-010`): 回写验收证据并仅在正式证据成立后推进 `done / established` — verify: `tools/validate_spec_lifecycle.py`
- [ ] **T220** `[成果门:R5]` (`FR-027`, `AC-009`, `AC-012`): 生成 v0.1 研究交付入口，确保非开发者从
      README 两次点击内到达总结报告、代表性回放、限制说明与 evidence index — verify:
      `python tools/verify.py`

## 4. 依赖与并行关系

- `T200`：立即执行，不依赖 0.1.5 新模型；完成后再投入长周期重构。
- `T201 -> T203—T210`：Contract 与 Schema 先冻结。
- `T202 -> T212—T216`：正式运行不得早于预注册冻结。
- `T203—T206 -> T207 -> T208—T211`：R2 先证明新代理路径可见、可回放。
- `T203—T211 -> T212 -> T213`：四 cell 预览只使用已验证的新路径。
- `T213 -> T214 -> T215 -> T216 -> T217 -> T218 -> T219 -> T220`：预览、正式运行、
  证据与状态顺序不可逆。

## 5. 明确后移

- 完整效用最大化目标模型 → v0.2+：不是本轮识别成立的必要条件。
- 无价格冲击外部承接池中介实验 → 后续独立规格：不进入 v0.1 签收。
- 手动交易沙盒 → R2 后的 H1 独立 Feature：可与 R3/R4 并行开发，但交互数据不得进入
  v0.1 旗舰证据；人在环正式实验须等 R5 后另行预注册。
