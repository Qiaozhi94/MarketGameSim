---
kind: milestone
id: 0.4.2
version: "0.4"
related_features:
  - 0.4.1
  - 0.4.3
  - 0.3.2
topics:
  - human-perturbation
  - paired-seed-control
  - stability-effect-size
doc_kind: tasks
created: 2026-09-20
updated: 2026-10-17
---

# 0.4.2：人类扰动实验 - 任务

> Owner: qiaozhi li | Spec: `spec.md` | Design: `design.md`

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
- 预注册（`T1127`）提交后，不得改动其中任何字段，不得在配对结果之后增减种子或处理会话；
  预注册提交之前不得运行任何正式配对。

## 1. 前置条件

- [x] T1120 (`FR-601`, `AC-601`): 在任何 owner 自由场次之前冻结 `PerturbationSession` 格式
      （会话单位为一次市场进程；头记录含版本号、会话标识、`roster_id`、种子、引擎配置指纹；
      动作行含 `advance_index`、`action_seq` 与载荷；封口行含结束 `advance` 序号与该序号处的
      事件摘要；内容哈希对「头记录 + 动作行」定义），并写成可被校验入口消费的冻结记录（已落地：
      [`0.4.2-perturbation-session-format.json`](../../../experiments/0.4.2-perturbation-session-format.json)
      v1，`session.py::FROZEN_FORMATS` 钉 sha256） — verify:
      `tests/unit/experiment/test_perturbation_session.py`
- [x] T1121 (`FR-603`, `DR-602`, `AC-605`): 冻结四个稳定性指标的计算口径与退化判定规则（spec
      SC-603）：盘口可用率与大波动频次取自 0.4.1 已冻结定义、只加窗口；最大回撤与最大涨幅
      （窗口起点重置的峰谷/谷峰，含 `P_t` 取样方式与跨窗口起点分钟变动对的处理）写入
      [`指标字典`](../../../research/metrics-dictionary.md) 后冻结，不另立第二份（已落地：指标字典 0.3.0 §9，owner 2026-10-19 裁决 `P_t` 取 1 秒网格最新成交价、分钟变动对只计两端都在窗口内；实现 `metrics/stability_effect.py`） — verify:
      `tests/unit/metrics/test_stability_effect.py`

## 2. 实现任务

### Phase 1：会话格式冻结、注入确定性、载体、同种子重放与功效分析

- [x] T1122 (`FR-601`, `DR-601`, `AC-601`, `AC-602`): 实现 `PerturbationSession` 的头记录、动作行
      追加、封口、读取与校验入口；缺字段、错版本号、含画像字段三类非法输入给稳定原因码；在任意
      一条动作之后终止进程时已取出动作不丢、会话标 `UNSEALED`，且未封口会话可通过校验、内容
      哈希稳定、种子与 `roster_id` 可读（正反用例都要有） — verify:
      `tests/unit/experiment/test_perturbation_session.py`
- [x] T1123 (`FR-604`, `NFR-602`, `AC-606`): 在校验入口拒绝对错判定/行为画像字段与直接身份
      信息，并断言合法 artifact 不被误拒 — verify:
      `tests/unit/experiment/test_perturbation_session.py`
- [x] T1124 (`FR-601`, `NFR-601`, `IR-601`, `TR-601`, `AC-602`, `AC-603`): 修复 live 市场注入路径
      （design §4、§5）——HTTP 线程只入队载荷；`advance()` 持锁取出时分配 `action_seq`、入队
      owner 的 `AGENT_OBSERVE` 并追加动作行；`experiment/runner.py` 增加 owner 观察分支（不参与
      周期性重排），决策走 `_handle_external_decide` 并扩展撤单 `kind`；owner 规格只注入
      `world["agent_specs"]`、`latency_ns ≥ 1`；撤单由 HTTP 线程原样入队，`advance()` 持锁取出时
      把终端给的 `order_id` 反查成 `target_action_seq` 写入动作行，反查不到的按「入队后才判定的
      无效撤单」丢弃（不进内核、不入动作日志，断言二者都不发生）；进程正常结束时封口。
      回归测试用确定性交错钩子构造「同一 advance 内多笔提交」「提交恰在推进中途」两类交错
      （`order_id`、时间戳、`submitted_at` 只由序号与载荷决定且不重复），并断言注册 owner 规格后
      纯 AI 运行的 0.4.1/0.4.3 入库摘要不变 — verify:
      `tests/integration/test_perturbation_injection.py`
- [x] T1125 (`FR-605`, `AC-608`): 把载体 C（count 6 / sensitivity 150，其余同 0.4.3 T1109
      固定项）按种子落盘到 `docs/experiments/0.4.2-rosters/`；live 市场新增预热：开放终端前
      不等待墙钟推进到 `W0`，期间拒绝下单，推进到 5700 s 仍未退出冷启动时拒绝开放（正反
      两侧）；改正 `--tick-seconds` 帮助文字里「1:1 实时」的说法 — verify:
      `tests/integration/test_perturbation_carrier.py`
- [x] T1126 (`FR-602`, `NFR-601`, `TR-601`, `AC-603`, `AC-604`): 实现同种子两臂——无人类基线臂
      同装配同种子逐点可复现；同种子重放臂按 `advance` 序号与 `action_seq` 投递动作行、推进到
      结束序号后比对封口事件摘要（owner 的观察、决策与委托都计入摘要），不一致返回
      `REPLAY_DIVERGED`；`chain_verifier` 对含 owner 委托的事件流通过 — verify:
      `tests/integration/test_perturbation_paired.py`
- [ ] T1127 (`SC-605`, `AC-609`): 在 20 个种子上跑载体 C 的无人类基线，产出四指标跨种子
      标准差 `σ_b` 与功效分析报告（`σ_d ≤ √2 · σ_b`、`ρ ≥ 0` 假设与 N 公式见 spec SC-605）；
      处理会话（预注册提交时已存在的全部会话）的内容哈希、逐指标 MDE（owner 在功效报告产出后
      登记）、N、有效配对下限与开环回放种子清单写入单一预注册文件并**先于任何正式配对运行
      提交**；配对入口只读该文件，缺失、哈希不一致或处理会话不在其中时 fail closed — verify:
      `tests/unit/experiment/test_perturbation_preregistration.py`
- [ ] T1128 `[成果门:H2-F1]` (`US-601`, `FR-601`, `SC-601`, `SC-605`, `AC-601`, `AC-602`, `E1`, `E2`, `E3`):
      交付一场可重放的自由会话 artifact、无人类基线运行记录、功效分析报告与预注册文件——
      仅凭 artifact 即可在同种子上重放出与原场事件摘要逐位相同的运行；证据标签为
      `experiment-preview` — verify: `tests/integration/test_perturbation_paired.py`、
      `tests/unit/experiment/test_perturbation_session.py`

### Phase 2：开环跨种子回放与效应量报告

- [x] T1129 (`FR-602`, `IR-601`, `DR-601`, `AC-610`): 实现开环跨种子回放——按 `advance` 序号把
      处理会话的动作日志投到预注册种子上并推进到 5700 s；无法投递时判失败并给稳定原因码；
      撤单按 `target_action_seq` 经本次运行的 `action_seq → order_id` 映射解析——原场撤掉的挂单
      在开环种子上仍挂着时照常撤掉，已成交或被拒时记录原因码，不静默丢弃动作；配对集合可由
      预注册文件与会话哈希重建 — verify: `tests/integration/test_perturbation_open_loop.py`
- [x] T1130 (`TR-501`, `TR-601`, `AC-604`): 人类与 AI 委托并存时的批量因果链用例——多条记录
      同时存在，`chain_verifier` 对含 owner 下单与撤单的事件流通过，owner 与 AI 委托的
      `decision_event_id` 都解析到 `AGENT_DECIDE`，参与者类别可区分且撮合路径一致 — verify:
      `tests/integration/test_perturbation_paired.py`
- [x] T1131 (`FR-603`, `DR-602`, `NFR-602`, `AC-605`, `AC-607`): 实现效应量报告——四指标两臂
      分布、逐种子差值、差值中位数与配对 bootstrap 90% 区间（原语加在 `experiment/stats.py`，
      `ci_level = 0.90`、10000 次、种子 0）、实测 `σ_d` 与功效判定、失效边界（退化配对、人类臂
      中止配对、载体 SC-501 失效的种子）与原场个案；有效配对数低于下限时效应量字段缺省而不是
      填 0；artifact 与报告携带 `experiment-preview` 与 `run_mode: interactive`，交给 evidence
      index 构建入口时被拒 — verify: `tests/unit/metrics/test_stability_effect.py`、
      `tests/integration/test_perturbation_evidence_guard.py`
- [ ] T1132 `[成果门:H2-F2]` (`US-602`, `FR-602`, `FR-603`, `SC-602`, `SC-603`, `AC-605`, `AC-610`, `E4`, `E5`):
      在预注册种子集合上交付一组配对运行与可打开的效应量报告——分布移动 + 区间 + 失效边界
      + 原场个案 + 功效判定，开环结果标注「固定订单流扰动」，退化路径如实输出退化判定；
      证据标签为 `experiment-preview`，不进入任何 evidence index — verify:
      `tests/integration/test_perturbation_open_loop.py`、`tests/unit/metrics/test_stability_effect.py`

## 3. 验证与验收任务

- [ ] T1133 (`AC-601`, `AC-602`, `AC-606`): 运行 artifact 冻结格式、逐条追加与拒绝规则的正反
      测试 — verify: `tests/unit/experiment/test_perturbation_session.py`
- [ ] T1134 (`AC-603`, `AC-604`, `AC-608`): 运行注入确定性、载体与预热、同种子基线复现、
      同种子重放逐位一致与人类/AI 并存批量因果链测试 — verify:
      `tests/integration/test_perturbation_injection.py`、
      `tests/integration/test_perturbation_carrier.py`、
      `tests/integration/test_perturbation_paired.py`
- [ ] T1135 (`AC-605`, `AC-607`, `AC-609`, `AC-610`): 运行效应量报告的有效/退化/中止三类输入、
      预注册守卫、开环回放与证据索引隔离测试 — verify:
      `tests/unit/metrics/test_stability_effect.py`、
      `tests/unit/experiment/test_perturbation_preregistration.py`、
      `tests/integration/test_perturbation_open_loop.py`、
      `tests/integration/test_perturbation_evidence_guard.py`
- [ ] T1136 (`AC-601`—`AC-610`): 运行项目统一质量门，并确认 0.4.1 质量门、0.4.3 锚定市场门、
      0.3.1 配对轨与 0.3.2 终端路径无回归 — verify: `python tools/verify.py`；既有回归门：
      `tests/integration/test_h2_owner_web.py`、`tests/integration/test_anchored_market.py`
- [ ] T1137 `[状态门]`: 回写 spec 验收证据、版本索引与状态；必须是本文件最后一项 — verify:
      `python tools/validate_spec_lifecycle.py`

## 4. 依赖与并行关系

- `T1120 -> T1122 -> T1123`：格式先冻结，再实现日志/封口/校验，再加拒绝规则。
- `T1120, T1122 -> T1124`：注入修复按冻结格式追加动作日志。
- `T1121 -> T1127`、`T1121 -> T1131`：指标口径先冻结，才谈得上功效分析与效应量。
- `T1124, T1125 -> T1126 -> T1127`：同种子两臂跑在载体 C 上、依赖确定的注入路径；功效分析
  依赖跨种子基线。
- `T1123, T1126, T1127 -> T1128`：T1128 是 Phase 1 成果门，须在预注册提交之后。
- `T1128 -> T1129 -> T1130 [P]` 与 `T1128 -> T1131 [P]`：开环回放与效应量实现改不同文件，可并行。
- `T1129, T1130, T1131 -> T1132`：配对与报告齐备后才产出 Phase 2 成果门。
- `T1133 [P]`、`T1134 [P]`、`T1135 [P]` 可并行；`T1133, T1134, T1135 -> T1136 -> T1137`。

## 5. 明确后移

- 研究声明与 `formal-research` 升级 → 另立预注册（spec Q-601 已裁决分析单元为种子；
  本里程碑维持 `experiment-preview`）。
- 以锚定 roster `2425a8…`（载体 B）为对照载体的开环回放 → **可选**：计算便宜、可在 T1132 后
  追加，单独成节报告，不作为本里程碑任何退出条件。
- 研究问题 #3（人机流动相互作用）的专门分析 → 独立里程碑；本里程碑只保证其所需的会话
  数据格式与配对能力。
- 固定场次/跨度/每窗一次动作的受控框架 → 保持归档（ADR-010、releases/0.3.md）；
  受控对照类问题复活时须先修订研究北极星。
- 多人（owner 之外的参与者）扰动 → 独立 Feature：涉及伦理适用性与身份信息边界的重新评估。
