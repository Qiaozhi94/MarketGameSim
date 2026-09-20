---
kind: milestone
id: 0.4.2
version: "0.4"
related_features:
  - 0.4.1
  - 0.3.2
topics:
  - human-perturbation
  - paired-seed-control
  - stability-effect-size
doc_kind: tasks
created: 2026-09-20
updated: 2026-09-20
---

# 0.4.2：人类扰动实验 - 任务

> Owner: TBD | Spec: `spec.md` | Design: `design.md`

## 0. 来源与执行规则

- 行为与验收真相源：[`spec.md`](spec.md)。
- 技术方案与边界：[`design.md`](design.md)。
- 每项任务只描述一个可验证动作，并引用合法的 US/需求/AC ID。
- 每个 Phase 的最后一项任务是成果门；成果门必须产出可打开页面或可消费的 artifact。
- **G1 研究问题前置检查**（features/README §阶段成果门，ADR-010）：本次交付直接服务
  [`owner-research-question`](../../../research/owner-research-question.md) 的研究问题 #1
  「人类扰动」——owner 亲身参与是项目核心动机，本里程碑把这份参与变成可配对、可分析的数据。
- 命题形态由 PRD §15 的可证伪化桥接条款唯一拥有：结论是效应量命题，不是「人类能否
  造成崩盘」；任务不得就地改写这一形态。
- L1 合同与 0.4.1 已冻结口径不可改。

## 1. 前置条件

- [ ] T985 (`FR-601`, `AC-601`): 在任何 owner 自由场次之前冻结 `PerturbationSession` 格式
      （字段、版本号、内容哈希口径），并写成可被校验入口消费的冻结记录 — verify:
      `tests/unit/experiment/test_perturbation_session.py`
- [ ] T986 (`FR-603`, `DR-602`, `AC-605`): 冻结三个稳定性指标（最大回撤、大波动频次、
      盘口可用率）的计算口径与退化判定规则，口径取自 0.4.1 已冻结定义，不另立第二份
      — verify: `tests/unit/metrics/test_stability_effect.py`

## 2. 实现任务

### Phase 1：会话格式冻结与无人类基线

- [ ] T987 (`FR-601`, `DR-601`, `AC-601`, `AC-602`): 实现 `PerturbationSession` 的写入/读取/
      校验入口；缺字段、错版本号、含画像字段三类非法输入给稳定原因码（正反用例都要有）
      — verify: `tests/unit/experiment/test_perturbation_session.py`
- [ ] T988 (`FR-604`, `NFR-602`, `AC-606`): 在校验入口拒绝对错判定/行为画像字段与直接身份
      信息，并断言合法 artifact 不被误拒 — verify:
      `tests/unit/experiment/test_perturbation_session.py`
- [ ] T989 (`FR-602`, `NFR-601`, `TR-601`, `AC-603`, `AC-604`): 实现无人类基线臂——同 roster
      同种子逐点可复现；owner 委托的参与者类别标识写入既有决策记录，不新增事件类型
      — verify: `tests/integration/test_perturbation_paired.py`
- [ ] T990 `[成果门:H2-F1]` (`US-601`, `FR-601`, `SC-601`, `AC-601`, `AC-602`, `E1`): 交付一场可重放的
      自由会话 artifact 与无人类基线运行记录——仅凭 artifact 即可重建动作序列与市场时点；
      证据标签为 `experiment-preview` — verify:
      `tests/integration/test_perturbation_paired.py`

### Phase 2：同种子对照与效应量报告

- [ ] T991 (`FR-602`, `IR-601`, `AC-603`): 实现动作序列回放臂——按逻辑时点投递到既有非阻塞
      注入路径；时点对不齐时判失败并给稳定原因码，不静默丢弃动作 — verify:
      `tests/integration/test_perturbation_paired.py`
- [ ] T992 (`TR-501`, `TR-601`, `AC-604`): 人类与 AI 委托并存时的批量因果链用例——多条记录
      同时存在，参与者类别可区分且撮合路径一致 — verify:
      `tests/integration/test_perturbation_paired.py`
- [ ] T993 (`FR-603`, `DR-602`, `AC-605`): 实现效应量报告——三指标两臂分布、效应量、不确定性
      区间与失效边界；统计原语复用 `experiment/stats.py`，退化输入时效应量字段缺省而不是填 0
      — verify: `tests/unit/metrics/test_stability_effect.py`
- [ ] T994 `[成果门:H2-F2]` (`US-602`, `FR-602`, `FR-603`, `SC-602`, `SC-603`, `AC-603`, `AC-605`, `E3`, `E4`):
      交付一组同种子配对运行与可打开的效应量报告——分布移动 + 区间 + 失效边界，退化路径
      如实输出退化判定；证据标签为 `experiment-preview`，不进入任何 evidence index — verify:
      `tests/integration/test_perturbation_paired.py`

## 3. 验证与验收任务

- [ ] T995 (`AC-601`, `AC-602`, `AC-606`): 运行 artifact 冻结格式与拒绝规则的正反测试 — verify:
      `tests/unit/experiment/test_perturbation_session.py`
- [ ] T996 (`AC-603`, `AC-604`): 运行同种子基线复现、回放对齐与人类/AI 并存批量因果链测试
      — verify: `tests/integration/test_perturbation_paired.py`
- [ ] T997 (`AC-605`, `AC-607`): 运行效应量报告的有效/退化两种输入，并断言产物不进入任何既有
      evidence index — verify: `tests/unit/metrics/test_stability_effect.py`
- [ ] T998 (`AC-601`—`AC-607`): 运行项目统一质量门，并确认 0.4.1 质量门、0.3.1 配对轨与 0.3.2
      终端路径无回归 — verify: `python tools/verify.py`；既有回归门：
      `tests/integration/test_h2_owner_web.py`
- [ ] T999 `[状态门]`: 回写 spec 验收证据、版本索引与状态；必须是本文件最后一项 — verify:
      `python tools/validate_spec_lifecycle.py`

## 4. 依赖与并行关系

- `T985 -> T987 -> T988`：格式先冻结，再实现写入/校验，再加拒绝规则。
- `T986 -> T993`：指标口径先冻结，才谈得上算效应量。
- `T987, T988 -> T989 -> T990`：基线臂依赖可落盘的会话格式；T990 是 Phase 1 成果门。
- `T990 -> T991 -> T992 [P]` 与 `T990 -> T993 [P]`：回放臂与效应量实现改不同文件，可并行。
- `T991, T992, T993 -> T994`：配对与报告齐备后才产出 Phase 2 成果门。
- `T995 [P]`、`T996 [P]`、`T997 [P]` 可并行；`T995, T996, T997 -> T998 -> T999`。

## 5. 明确后移

- 研究声明与 `formal-research` 升级 → 先闭合 Q-601（SOP §2「交互运行不进统计」的适用边界）。
- 研究问题 #3（人机流动相互作用）的专门分析 → 独立里程碑；本里程碑只保证其所需的会话
  数据格式与配对能力。
- 固定场次/跨度/每窗一次动作的受控框架 → 保持归档（ADR-010、releases/0.3.md）；
  受控对照类问题复活时须先修订研究北极星。
- 多人（owner 之外的参与者）扰动 → 独立 Feature：涉及伦理适用性与身份信息边界的重新评估。
