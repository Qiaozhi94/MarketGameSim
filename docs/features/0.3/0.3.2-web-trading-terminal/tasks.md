---
kind: milestone
id: 0.3.2
version: "0.3"
related_features:
  - 0.3.1
topics:
  - web-terminal
  - owner-n-of-1
  - kline
doc_kind: tasks
created: 2026-09-12
updated: 2026-09-13
---

# 0.3.2：Web 交易终端与所有者 N-of-1 采集 - 任务

> Owner: TBD | Spec: `spec.md` | Design: `design.md`

## 0. 来源与执行规则

- 行为与验收真相源：[`spec.md`](spec.md)。
- 技术方案与边界：[`design.md`](design.md)。
- 每项任务只描述一个可验证动作，并引用合法的 US/需求/AC ID。
- 每个 Phase 的最后一项任务是成果门；成果门必须产出可打开页面或可消费的 owner artifact。
- 所有者时间不在工程任务完成前占用；E2 Web preview 未通过不得开始训练或正式场景。
- owner 结果始终是个人描述性数据，不进入 AI formal evidence index 或研究声明。

## 1. 前置条件

- [ ] T927 (`FR-302`, `IR-301`, `AC-405`): 在任务级接入已完成的 `0.3.1/T915` preview contract，
      验证 session controller、assignment、委托幂等、
      时点采样和 canonical input contract 可供 Web adapter 复用 — verify: `docs/features/0.3/0.3.1-human-in-the-loop-experiment/design.md`；
      既有契约门：`tests/unit/experiment/test_h2_protocol.py`
- [ ] T928 (`FR-401`, `NFR-403`, `AC-401`): 在仓库 CI 矩阵 Python 3.11/3.13 的目标环境确认
      loopback 服务、时间单调钟和静态资源加载约束，并把 OS/Python/启动命令记入环境记录；
      其它本地解释器版本只作额外冒烟，不作为验收目标 — verify: `tests/integration/test_h2_owner_web.py`
- [ ] T929 (`FR-401`, `DR-402`, `AC-401`, `AC-404`): 冻结 owner 轨四项参数——时间压缩比（采集
      1:1）、可选 K 线周期集合、逻辑时点采样粒度、场景市场时间跨度——并升级 owner 协议版本
      与 E1 冻结清单；同时冻结 owner 证据包布局与 schema（`docs/experiments/owner-n-of-1/`
      下 `environment.json`/manifest/index 字段、完成状态 `complete`/`incomplete-study`、
      哈希与 sample flow 结构），并实现机器校验入口 `tools/validate_owner_evidence.py`（覆盖
      完整样本、`incomplete-study`、零样本与哈希/唯一 ID 正反样例）；证据合同必须先于任何
      真实采集冻结，作为 K 线投影、owner 会话与真实采集的前置 — verify:
      `tests/unit/experiment/test_h2_protocol.py`、`tests/unit/experiment/test_owner_evidence_validator.py`

## 2. 实现任务

### Phase 1：H2-D1 Web 终端与交易预览

- [ ] T930 (`FR-401`, `DR-402`, `UX-401`, `AC-401`): 实现 public tape → 多周期 OHLC K 线投影器
      （1m/5m/15m/1h/4h 与时间压缩比）、无报价/数据不足空态和源哈希 — verify: `tests/unit/interactive/test_kline_projection.py`
- [ ] T931 (`IR-301`, `IR-401`, `UX-401`, `UX-403`, `AC-403`): 实现 H2 owner view/start/status/
      abort 路由和 loopback 页面骨架，页面显示报价、账户、市场时钟、K 线与 SIM/阶段标识，
      不返回参照策略/未来信息；同一提交内落地 preview gate fail closed（E2 证据未通过时拒绝
      training/formal 入口），使门控在 H2-D1 成果门前可用 — verify: `tests/integration/test_h2_owner_web.py`
- [ ] T932 (`SC-401`, `AC-401`, `AC-403`, `AC-404`): 生成可打开的本地 Web preview
      页面，作为内部 preview contract 验收；入口和验收命令写入 `RUN.md`；固定假参与者可看到价格/
      K 线/账户，且采集模式只显示冻结观察白名单字段（自由模拟演示字段在采集态隐藏）；
      证据标签为 `experiment-preview` — verify: `tests/e2e/test_h2_owner_terminal.py`；
      既有原型门：`tests/unit/test_owner_observation_whitelist.py`

- [ ] T933 (`FR-402`, `IR-402`, `TR-401`, `AC-402`): 将市价/限价买卖委托与撤单映射到 canonical
      input，并实现数量、价格、幂等和稳定错误码校验 — verify:
      `tests/unit/experiment/test_owner_input_contract.py`；
      既有原型交互门：`tests/unit/test_terminal_prototype_behavior.py`
- [ ] T934 (`FR-302`, `NFR-402`, `AC-405`): 接入幂等去重、逻辑时点采样和既有撮合/账本/风控路径，
      验证刷新、断线不重复委托或推进逻辑时间 — verify: `tests/integration/test_h2_owner_web.py`
- [ ] T935 (`UX-402`, `UX-404`, `AC-406`): 完成按钮 enabled/submitting/disabled/rejected、无报价
      禁用、断线、退出、完成和错误空态；采集模式下退出需选择原因并写 `OWNER_ABORT` 终态
      — verify: `tests/e2e/test_h2_owner_terminal.py`；
      既有原型交互门：`tests/unit/test_terminal_prototype_behavior.py`
- [ ] T936 `[成果门:H2-D1]` (`SC-402`, `AC-402`, `AC-403`, `AC-405`, `AC-406`): 生成可交互的本地交易终端
      preview，固定输入完成合法市价/限价委托、成交、撤单、拒单、断线与退出，并验收 E2 的
      preview fail-closed 门控；证据标签为 `experiment-preview` — verify: `tests/e2e/test_h2_owner_terminal.py`

### Phase 2：H2-D2 所有者训练、正式采集与个人交付

- [ ] T937 (`FR-403`, `DR-401`, `NFR-302`, `AC-403`, `AC-407`): 实现 training/formal
      assignment、阶段解盲、假名化和 owner artifact PII guard（preview gate fail closed 已在
      T931 落地，此处只消费其结果） — verify:
      `tests/unit/experiment/test_owner_privacy.py`；
      既有原型门：`tests/unit/test_owner_observation_whitelist.py`
- [ ] T938 (`TR-302`, `AC-408`): 按冻结粒度写 owner 逻辑时点采样快照，连接委托、成交、账本、
      盘口和强平事件因果链；区分技术中止（按冻结顺序从备用池整局补跑）与所有者主动中止
      （写 `OWNER_ABORT` reason code 后进入终态、不补跑、不进入 evidence index），并把
      `abort_kind`/reason code 写入 owner-session.json — verify: `tests/integration/test_h2_owner_web.py`；
      既有证据合同门：`tests/unit/test_owner_incomplete_study.py`
- [ ] T939 (`SC-403`, `AC-408`): 在 E2 gate 通过后按冻结台账完成 6 个训练场景；训练结果不写入
      formal evidence index。完成证据必须包含目标环境记录与真实 training manifest（6 条唯一
      `session_id`、哈希、排除/补跑流、非退化事件内容）；集成测试只验机制，不能替代真实场景
      已经发生的完成声明 — verify: `tests/integration/test_h2_owner_delivery.py`
- [ ] T940 (`SC-403`, `AC-403`, `AC-408`): 交付训练后可启动 formal 的 owner session bundle，
      包含阶段/assignment/解盲 guard 矩阵；证据标签为 `experiment-preview`
      — verify: `tests/integration/test_h2_owner_delivery.py`

- [ ] T941 (`FR-302`, `TR-302`, `NFR-302`, `AC-405`, `AC-407`): 按冻结 assignment 完成 24 个正式
      owner 场景，或在冻结停止规则命中时按规则结束并生成 `incomplete-study`（不得伪造完成）；
      结果字段对中止、补跑和解盲裁决保持不可见。完成证据必须包含真实 owner evidence index
      （唯一 `session_id`、哈希、排除/补跑流；非退化断言按完成状态条件化）与目标环境记录，
      不得仅以集成测试代替 — verify:
      `tests/integration/test_h2_owner_delivery.py`
- [ ] T942 (`DR-401`, `DR-402`, `AC-408`): 正式采集完成后，用 T929 已冻结的 schema 与 validator
      冻结 owner evidence index、session manifest、输入/事件/K 线 artifact 哈希和 sample flow，
      产出 `docs/experiments/owner-n-of-1/` 固定布局；本任务只做采集后 index freeze，不再定义
      或改动证据格式 — verify:
      `tests/integration/test_h2_owner_delivery.py`
- [ ] T943 (`SC-404`, `AC-407`, `AC-408`): 从 owner evidence index 生成个人描述性报告、代表性
      回放和限制声明，明确不外推到人群 — verify: `tests/integration/test_h2_owner_delivery.py`
- [ ] T944 `[成果门:H2-D2]` (`SC-403`, `SC-404`, `AC-407`, `AC-408`): 生成可打开的 owner
      `experiment-preview` 交付包；若场景不足则生成 `incomplete-study` 而不伪造完成。完成
      证据须断言 evidence index 计数、唯一 ID、哈希，并由目标环境记录佐证；非退化断言按完成
      状态条件化——完整样本（24 场）断言非退化，`incomplete-study` 按实际样本数断言非退化，
      零样本以文档化停止原因通过 — verify:
      `tests/integration/test_h2_owner_delivery.py`

## 3. 验证与验收任务

- [ ] T945 (`AC-401`, `AC-402`, `AC-403`, `AC-405`, `AC-406`, `AC-408`): 运行 Web API、K 线、委托、
      空态、断线、撤单、阶段 guard 与 owner abort（写 `OWNER_ABORT` 终态、不消耗备用池、不补跑）
      的正反测试 — verify: `tests/integration/test_h2_owner_web.py`
- [ ] T946 (`AC-404`, `AC-407`, `AC-408`): 运行 artifact 哈希、PII、owner index 隔离和新进程重建
      验证 — verify: `tests/integration/test_h2_owner_delivery.py`
- [ ] T947 (`AC-401`, `AC-402`, `AC-403`, `AC-404`, `AC-405`, `AC-406`, `AC-407`, `AC-408`): 运行
      项目统一质量门 — verify: `python tools/verify.py`

### [TEST] 组：层 2 旅程验收轨（必填）

从体验旅程派生（每旅程步骤 ≥1 条可执行断言）；**编写早、执行晚**——夹具随 T932 立红灯，
收尾全量执行作为 E2 验收。交互语义已由原型行为门锁定（`tests/unit/test_terminal_prototype_behavior.py`），
本组将其提升为真实现终端上的旅程验收。

- [ ] T949 [TEST] (`AC-401`): 旅程一「先确认行情再交易」：新进程打开 loopback 页面（无外部
      网络）→ 报价/盘口/最近成交/多周期 K 线可见 → 切换品种与周期刷新 → 空态不造假
      — verify: `tests/e2e/test_h2_owner_terminal.py::test_journey_market_visibility`；RED/GREEN: 待回填
- [ ] T950 [TEST] (`AC-402`, `AC-405`, `AC-406`): 旅程二「自由提交买卖委托」：市价成交回报 →
      限价挂单 → 价格触及自动成交 → 撤单零成交 → 非法输入稳定拒绝 → 断线/刷新不重复委托
      — verify: `tests/e2e/test_h2_owner_terminal.py::test_journey_free_trading`；RED/GREEN: 待回填
- [ ] T951 [TEST] (`AC-403`, `AC-406`): 旅程三「页面通过后才开始训练」：preview 未过拒绝
      training/formal → 通过后进入采集态（白名单外字段隐藏、无参照策略/结果泄漏）→ 退出
      采集写 `OWNER_ABORT` 终态且不补跑 — verify:
      `tests/e2e/test_h2_owner_terminal.py::test_journey_gating_and_collection`；RED/GREEN: 待回填
- [ ] T952 [TEST] (`AC-407`, `AC-408`): 旅程四「个人结果可重建」：从 owner session artifact
      重建个人描述性报告 → 无直接身份信息、不产生人群结论 → owner evidence index 与 AI
      index 隔离可从 manifest 重建 — verify:
      `tests/e2e/test_h2_owner_terminal.py::test_journey_rebuild_evidence`；RED/GREEN: 待回填

- [ ] T953 `[状态门]`: 回写 spec 验收证据、owner evidence index、版本索引和状态；必须是本文件最后
      一项 — verify: `python tools/validate_spec_lifecycle.py`

## 4. 依赖与并行关系

- `T927 -> T928 -> T929`：先复用 session contract，核验目标平台（T928，Python 3.11/3.13），
  再冻结 owner 参数（压缩比/周期集合/采样粒度/市场跨度）。T929 同时冻结证据布局/schema 并
  实现 validator，保证任何真实采集发生前证据格式已固定且可机器校验。
- `T929 -> T930 [P]` 与 `T929 -> T931 [P]`：K 线纯派生模块与 HTTP view/门控页面修改不同
  文件，可并行；preview gate fail closed 与 abort 路由在 T931 落地。
- `T930, T931 -> T932`：K 线投影与页面汇合为可打开的 preview，验收包含门控。
- `T932 -> T933 -> T934 -> T935 -> T936`：页面先能看，再允许自由委托，最后验收错误/恢复状态。
- `T936 -> T937 -> T938 -> T939 -> T940`：preview gate 通过、且 T938 的逻辑时点采样因果链与
  中止裁决完成后，才允许占用所有者训练时间；T938 是 T939 的显式前置。
- `T940 -> T941 -> T942 -> T943 -> T944`：正式场景按冻结规则完成或结束后才冻结 owner index
  和个人报告。
- `T945 [P]` 与 `T946 [P]` 可并行：运行时正反测试与交付包审计不共享 session 状态。

## 5. 明确后移

- 公开部署、登录/权限、多用户协作和真实行情 → 后续独立 Feature：当前目标是本地所有者终端。
- 条件单（止损/止盈）与高级图表指标 → 后续交易产品 Feature：MVP 动作空间只含市价/限价委托与撤单。
- owner 结果的人群统计推断或因果中介识别 → 后续研究：本里程碑只交付个人描述性结果。
