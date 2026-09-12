---
kind: milestone
id: 0.3.1
version: "0.3"
related_features:
  - 0.2.1
topics:
  - human-in-the-loop
  - paired-counterfactual
  - formal-research
doc_kind: tasks
created: 2026-09-04
updated: 2026-09-12
---

# 0.3.1：H2 人在环崩盘反馈实验 - 任务

> Owner: TBD | Spec: `spec.md` | Design: `design.md`

## 0. 来源与执行规则

- 行为与验收真相源：[`spec.md`](spec.md)。
- 技术方案与边界：[`design.md`](design.md)。
- 每项任务只描述一个可验证动作，并引用合法的 US/需求/AC ID。
- 阶段成果门规则见 [`docs/features/README.md`](../../README.md#阶段成果门)；状态推进与 AC
  测试路径规则见同文档的 [`gate 规则`](../../README.md#gate-规则)（唯一拥有者）。推进
  `ready-for-development` 前须建立本文件所列的具体测试文件；未实现行为使用
  `pytest.mark.xfail(strict=True)` 骨架并写明原因。
- 完成且验证后立即勾选；实现中契约失效时先修订三件套。
- 首个 AI 正式 block 前必须关闭全部 Q/DQ、完成 AI 范围重基线并冻结协议；所有者 Web 采集
  不属于本里程碑关键路径，外部真人招募为零。
- T925 只运行统一质量门并检查验收上界，不承担任何 AC 的测试路径锚点；AC-301—AC-308
  必须由 T904—T924 所列具体测试文件覆盖。

## 1. 前置条件

- [x] T901 (`Q-301`, `Q-302`, `Q-303`, `Q-304`, `Q-305`, `Q-306`, `Q-307`, `DQ-301`,
      `DQ-302`, `DQ-303`, `DQ-304`, `DQ-305`): 按 `H2-dual-track-contract-v1` 将 spec/design
      中遗留的多人招募、报酬、伦理与人群推断合同重基线为 AI 正式轨，并把 owner 窗口、输入链
      和隐私字段降为 0.3.2 下游合同；旧内容只保留在 superseded 证据中。两条 AI 参照策略
      (`risk_budget_threshold_v1` 与 `risk_budget_linear_v1`) 的策略 ID 或参数组合必须不同，
      并记录主对照选择依据 — verify: `tests/unit/test_h2_dual_track_contract.py`、`spec.md`、`design.md`
- [x] T902 (`FR-301`, `SC-301`): 三个家族的严重程度 SESOI 已按 0.25 SD 全部冻结
      （`price_crash`/`liquidity_dry_up` = `4.5969e-3`，`liquidation_cascade` = `0.25049`），
      block 数冻结为 168；正式场景分布必须包含高杠杆 + `maint_bp=1200` 制度格，否则强平连锁
      家族无数据（发生指标三家族均实测为零方差，不得作主要 estimand；block 数不得下调）；
      owner 的 24 场景顺序只登记为 0.3.2 输入，不作为当前 go/no-go；确认 AI 研究声明只挂 AI 轨。已作废的旧真人功效、Prolific
      与 `$5,900` 预算不得进入当前 go/no-go — verify:
      `docs/experiments/H2-dual-track-contract.json`、`tests/unit/test_h2_block_power.py`、
      `tests/unit/test_h2_dual_track_contract.py`、`docs/experiments/H2-preregistration.md`
- [x] T903 (`FR-301`, `NFR-301`, `AC-301`): 验证 v0.2.1、事件/指标合同与目标代理配置可支持
      比较矩阵中标为“相同”的字段逐字段一致，并能冻结、输出其余差异项 — verify:
      `tests/unit/experiment/test_h2_protocol.py`

## 2. 实现任务

### Phase 1：H2-A 冻结协议与配对运行骨架

- [x] T904 (`FR-301`, `DR-301`, `AC-301`): 实现 protocol schema、完整性校验、内容哈希与不可变
      冻结，并与仓库预注册门交叉绑定；`control_arm` 闭集为 `linear | threshold | owner`，CLI 复用
      同一枚举真源 — verify: `tests/unit/experiment/test_h2_protocol.py`
- [x] T905 [P] (`DR-301`, `AC-308`): 固化 owner 下游可复用的研究假名、训练/正式阶段标识、
      解盲规则和成果包 PII 扫描边界；本里程碑不采集 owner 会话（无外部参与者，故无报名/同意/
      资格/撤回流程）
      — verify: `tests/unit/experiment/test_h2_privacy.py`
- [x] T906 (`FR-301`, `NFR-303`, `AC-304`): 实现预签发 assignment、seed/scenario
      顺序、有序备用 seed/pair 池与结果盲纳入元数据；H2 使用独占的 50000 seed 段 — verify:
      `tests/unit/experiment/test_h2_assignment.py`、`tests/integration/test_h2_paired_runs.py`
- [x] T907 (`FR-301`, `TR-301`, `NFR-301`, `AC-304`): 实现目标代理插槽、AI 双臂生成与
      两条纯代理运行均受同一有限窗口调度器约束（`WINDOW_MATCHED_POLICY_CONTROL` 形态），
      以及两轨的双臂生成与冻结字段比较（窗口调度参数必须在白名单内，
      主对照策略取自预注册的 v0.1 家族；协议须冻结账户/风险、信息、动作、窗口与目标差异的
      比较矩阵，且不声称目标函数对齐） — verify: `tests/integration/test_h2_paired_runs.py`
- [x] T908 (`FR-303`, `IR-302`, `AC-303`): 实现 mode/stage/protocol/pair/inclusion 多重 evidence
      guard 和原子拒绝 — verify: `tests/integration/test_h2_evidence_guard.py`
- [x] T909 `[成果门:H2-A]` (`AC-301`, `AC-303`, `AC-304`): 生成可打开的冻结协议、配对
      manifest diff 与 guard 矩阵，入口 `python -m market_game_sim.experiment protocol preview`，
      验收协议漂移及 H1 数据均被拒绝，标记为 `experiment-preview` — verify:
      `tests/integration/test_h2_delivery.py`

### Phase 2：H2-B 锁定客户端与实验预览

- [x] T910 (`FR-301`, `AC-302`): 实现 preview 使用的有限决策窗口、单次提交、超时 `NO_ACTION`
      与迟到输入拒绝 — verify: `tests/integration/test_experiment_session.py`
- [x] T911 (`UX-301`, `UX-302`, `UX-303`, `AC-302`, `AC-308`): 实现固定假参与者 preview UI、
      倒计时、阶段提示与中止入口，并固化未来 owner Web 终端不得暴露 pause/step/改参的状态合同 — verify:
      `tests/integration/test_experiment_session.py`
- [x] T912 [P] (`FR-304`, `SC-303`, `AC-305`): 实现三个独立结果家族、配对估计、不确定性、
      多重性和缺失处理；Holm 只作用于 AI 轨 `risk_budget_threshold_v1 - risk_budget_linear_v1`
      的三个主要终点，所有者轨对比输出为描述性且不得替代主要结论 — verify:
      `tests/unit/experiment/test_h2_outcomes.py`
- [x] T913 [P] (`FR-305`, `TR-301`, `SC-303`, `AC-306`): 实现激进订单、流动性撤回和风险减仓
      指标及因果追溯，将 ID/公式/单位/窗口/缺失语义写入指标字典唯一真源 — verify:
      `docs/research/metrics-dictionary.md`、`tests/unit/experiment/test_h2_mechanisms.py`、
      `tests/integration/test_h2_mechanisms.py`
- [x] T914 (`FR-303`, `NFR-303`, `AC-303`, `AC-308`): 实现技术中止、preview 中止、补跑与结果盲
      adjudication 流程；补跑只能按冻结顺序消耗备用 seed/pair 并绑定配套控制 — verify:
      `tests/integration/test_h2_evidence_guard.py`
- [x] T915 `[成果门:H2-B]` (`AC-302`, `AC-303`, `AC-305`, `AC-306`, `AC-308`): 用固定假参与者
      输入生成训练、正式会话、三结果与机制预览，入口
      `python -m market_game_sim.experiment preview`，验收有限窗口、阶段隔离、重放和报告结构，
      标记为 `experiment-preview` — verify: `tests/integration/test_h2_delivery.py`

### Phase 3：H2-C AI 正式采样与研究交付

- [x] T916 (`FR-301`, `SC-301`, `AC-301`): 冻结最终预注册、分析代码、协议哈希与分配表，并在
      首个正式样本前归档时间证据；预注册文档门和 protocol schema 门须同时通过 — verify:
      `tests/unit/experiment/test_h2_protocol.py`、`python tools/validate_spec_lifecycle.py`
- [ ] T917 (`US-301`, `NFR-303`, `AC-304`, `AC-308`): 按冻结协议完成 T902 冻结的 AI paired
      block 数（168；若资源窗口结束仍不足，按预注册停止规则写出 `incomplete-study` 样本流）。
      纯代理正式运行按冻结 seed/配置台账与结果盲裁决推进；owner 训练和 24 个正式场景不属于
      本任务，转由 0.3.2 — verify:
      `tests/integration/test_h2_paired_runs.py`
- [ ] T918 (`FR-303`, `IR-302`, `SC-302`, `AC-303`, `AC-304`): 冻结只含完整合格 pair 的 H2
      evidence index 和样本流图 — verify: `tests/integration/test_h2_evidence_guard.py`
- [ ] T919 (`FR-304`, `FR-305`, `SC-303`, `AC-305`, `AC-306`): 运行预注册主要、机制与敏感性
      分析，输出机器结果并执行结论边界检查 — verify: `tests/unit/experiment/test_h2_outcomes.py`
- [ ] T920 (`FR-306`, `NFR-301`, `SC-304`, `AC-307`, `AC-308`): 生成 AI 正式报告、
      代表性回放、限制、manifest 与隐私审查记录 — verify: `tests/integration/test_h2_delivery.py`
- [ ] T921 `[成果门:H2-C]` (`AC-304`, `AC-305`, `AC-306`, `AC-307`, `AC-308`): 从冻结 AI evidence
      index 单命令生成可打开的 H2 AI 正式交付包，入口
      `python -m market_game_sim.experiment deliver --formal`，验收配对重建、三结果分呈、机制边界、
      PII 扫描与限制声明，标记为 `formal-research` — verify:
      `tests/integration/test_h2_delivery.py`

## 3. 验证与验收任务

- [ ] T922 (`AC-301`, `AC-303`, `AC-304`): 运行协议、证据门、配对和重放正反测试 — verify:
      `tests/unit/experiment/test_h2_protocol.py`、`tests/integration/test_h2_evidence_guard.py`、
      `tests/integration/test_h2_paired_runs.py`
- [ ] T923 (`AC-302`, `AC-308`): 在目标 Windows 环境运行 AI/preview 窗口、断线、中止与阶段提示
      验收；所有者 Web 终端由 0.3.2 单独验收 — verify: `tests/integration/test_experiment_session.py`
- [ ] T924 (`AC-305`, `AC-306`): 用冻结模拟数据验证效应恢复、缺失、多重性、三机制和无综合分数
      — verify: `tests/unit/experiment/test_h2_outcomes.py`、
      `tests/unit/experiment/test_h2_mechanisms.py`、`tests/integration/test_h2_mechanisms.py`
- [ ] T925 (`AC-301`, `AC-302`, `AC-303`, `AC-304`, `AC-305`, `AC-306`, `AC-307`, `AC-308`):
      运行项目统一质量门 — verify: `python tools/verify.py`
- [ ] T926 `[状态门]`: 回写 AI spec 验收/研究证据、版本索引和状态；研究声明仅在 H2-C AI 正式
      证据复核通过后设为 established — verify: `tools/validate_spec_lifecycle.py`

## 4. 依赖与并行关系

- `T901 -> T902 -> T904`：先完成 AI 合同重基线和 paired-seed 校准，再冻结可执行协议。
- `T902` 的 AI 方差校准是当前研究关键路径；owner 场景顺序只作为 0.3.2 的输入登记，不阻塞
  当前 go/no-go；`python tools/verify.py` 通过不能代替这些证据。
- `T904 -> T906 -> T907 -> T909`：assignment 与 pair 必须绑定已冻结协议。
- `T907 -> T910 -> T911 -> T915`：preview UI 依赖窗口和目标代理插槽；生产 Web 终端不在本里程碑。
- `T908 -> T914 -> T915`：预览必须先验证阶段隔离和裁决。
- `T912 [P]` 与 `T913 [P]` 可并行：结果与机制属于不同分析模块且定义已由协议冻结。
- `T915 -> T916 -> T917 -> T918 -> T919 -> T920 -> T921`：AI 正式协议冻结后才采样，index
  冻结后才分析，分析完成后才生成正式报告；T917 未达到冻结停止规则时不得进入 T918。
- `T905 [P]` 可与运行骨架开发并行：只修改会话阶段/隐私模块，不共享市场运行状态。

## 5. 明确后移

- 因果中介识别 → 后续独立研究：需要对行为通道追加操纵或更强识别假设。
- 多人同时交易与社会互动 → v0.4+：会改变处理定义、信息结构和推断单位。
- 参与者专业度/人口统计异质性 → 后续预注册研究：H2 首先识别受控替换的平均效应。
- 真实市场校准与外部效度 → 后续研究：H2 只在当前合成模型族内建立条件性结论。
- Web 交易终端、价格/K 线展示、按钮交互、所有者训练和 24 个 N-of-1 场景 →
  [`0.3.2 Web trading terminal`](../0.3.2-web-trading-terminal/spec.md)：当前先交付 AI 正式基线，
  避免项目所有者四天训练阻塞研究包收口。
