---
kind: milestone-tasks
id: 0.1.5
version: "0.1"
doc_kind: tasks
created: 2026-08-14
updated: 2026-08-14
---

# 0.1.5：目标驱动代理与旗舰实验识别 - 任务

> Spec: `spec.md` | Design: `design.md`

## 0. 来源与执行规则

- 行为与验收真相源：[`spec.md`](spec.md)；技术边界：[`design.md`](design.md)。
- 每项实现先补正反回归测试；批量代理、成交与四 cell 必须有多记录场景。
- 完成并验证后立即勾选；若合同失效，先修订三件套再继续。
- T203—T206 分别承接 0.1.2 T404—T407，不能在原任务中伪造完成。

## 1. 前置条件

- [ ] **T201** (`FR-021`—`FR-026`): 更新代理、事件、实验与证据 Contract，并冻结 Schema 版本 — verify: `python tools/verify.py`
- [ ] **T202** (`FR-024`, `SC-010`): 冻结 `2 × 2`、三终点家族、seed plan 与排除规则预注册 — verify: `docs/experiments/`

## 2. 实现任务

### Phase 1：目标、信息与遗留代理链

- [ ] **T203** (`FR-021`, `AC-001`): 实现目标模型接口、linear/threshold 模型与独立制度约束层，承接 0.1.2 T404 — verify: `tests/unit/agent/`
- [ ] **T204** (`FR-021`, `AC-001`): 迁移库存型做市商目标与报价风险政策，承接 0.1.2 T405 — verify: `tests/unit/agent/`
- [ ] **T205** (`FR-022`, `FR-025`, `AC-002`, `AC-005`): 实现公开 tape、逐代理游标、观察/决策证据链，承接 0.1.2 T406 — verify: `tests/integration/`
- [ ] **T206** (`FR-022`, `NFR-005`, `AC-002`): 固化多代理构建、零仓位、K 线、EWMA 与确定性测试，承接 0.1.2 T407 — verify: `tests/unit/agent/`

### Phase 2：运行族与证据权限

- [ ] **T207** (`FR-023`, `IR-501`, `AC-003`): 实现三运行族配置闭集与 fail-closed 允许/拒绝矩阵 — verify: `tests/unit/experiment/`
- [ ] **T208** (`FR-023`, `DR-501`, `AC-004`): 实现 `StressProtocolV1`、四 cell 同路径校验和 `EXOGENOUS_STRESS` provenance — verify: `tests/unit/experiment/`
- [ ] **T209** (`FR-025`, `TR-501`, `TR-502`, `AC-005`): 扩展决策事件与全链独立验证器 — verify: `tests/integration/`
- [ ] **T210** (`FR-026`, `IR-502`, `AC-008`): 实现 evidence class 与跨族报告/聚合权限守卫 — verify: `tests/unit/experiment/`

### Phase 3：正式旗舰实验

- [ ] **T211** (`FR-024`, `AC-006`): 实现四 cell 配对 seed plan 与三终点独立统计计划 — verify: `tests/integration/`
- [ ] **T212** (`FR-024`, `SC-010`, `AC-007`): 运行校准/验证后冻结的正式 `SPONTANEOUS` 实验 — verify: `docs/experiments/`
- [ ] **T213** (`FR-026`, `DR-502`, `SC-011`, `AC-009`): 生成正式 evidence index 与条件性结论 — verify: `docs/experiments/`

## 3. 验证与验收任务

- [ ] **T214** (`AC-001`—`AC-010`): 逐项核对退出条件、批量回归与正式证据路径 — verify: `python tools/verify.py`
- [ ] **T215** (`AC-001`—`AC-010`): 运行项目统一质量门和确定性复现 — verify: `python tools/verify.py`
- [ ] **T216** (`FR-026`, `AC-009`, `AC-010`): 回写验收证据并仅在正式证据成立后推进 `done / established` — verify: `tools/validate_spec_lifecycle.py`

## 4. 依赖与并行关系

- `T201 -> T203—T210`：Contract 与 Schema 先冻结。
- `T202 -> T211—T213`：正式运行不得早于预注册冻结。
- `T203—T210 -> T211`：四 cell 运行只使用已验证的新路径。
- `T211 -> T212 -> T213 -> T214 -> T215 -> T216`：运行、证据与状态顺序不可逆。

## 5. 明确后移

- 完整效用最大化目标模型 → v0.2+：不是本轮识别成立的必要条件。
- 无价格冲击外部承接池中介实验 → 后续独立规格：不进入 v0.1 签收。
