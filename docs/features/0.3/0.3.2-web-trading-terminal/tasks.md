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
      时点采样和 canonical input contract 可供 Web adapter 复用 — verify: `docs/features/0.3/0.3.1-human-in-the-loop-experiment/design.md`
- [ ] T928 (`FR-401`, `NFR-403`, `AC-401`): 在 Python 3.11/3.14 的目标环境确认 loopback 服务、
      时间单调钟和静态资源加载约束 — verify: `tests/integration/test_h2_owner_web.py`

## 2. 实现任务

### Phase 1：H2-D1 Web 终端与交易预览

- [ ] T929 (`FR-401`, `DR-402`, `UX-401`, `AC-401`): 实现 public tape → 多周期 OHLC K 线投影器
      （1m/5m/15m/1h/4h 与时间压缩比）、无报价/数据不足空态和源哈希 — verify: `tests/unit/interactive/test_kline_projection.py`
- [ ] T930 (`IR-301`, `IR-401`, `UX-401`, `UX-403`, `AC-403`): 实现 H2 owner view/start/status
      路由和 loopback 页面骨架，页面显示报价、账户、市场时钟、K 线与 SIM/阶段标识，不返回
      参照策略/未来信息 — verify: `tests/integration/test_h2_owner_web.py`
- [ ] T931 (`SC-401`, `AC-401`, `AC-403`, `AC-404`): 生成可打开的本地 Web preview
      页面，作为内部 preview contract 验收；入口和验收命令写入 `RUN.md`；固定假参与者可看到价格/
      K 线/账户，证据标签为 `experiment-preview` — verify: `tests/e2e/test_h2_owner_terminal.py`

- [ ] T932 (`FR-402`, `IR-402`, `TR-401`, `AC-402`): 将市价/限价买卖委托与撤单映射到 canonical
      input，并实现数量、价格、幂等和稳定错误码校验 — verify:
      `tests/unit/experiment/test_owner_input_contract.py`
- [ ] T933 (`FR-302`, `NFR-402`, `AC-405`): 接入幂等去重、逻辑时点采样和既有撮合/账本/风控路径，
      验证刷新、断线不重复委托或推进逻辑时间 — verify: `tests/integration/test_h2_owner_web.py`
- [ ] T934 (`UX-402`, `UX-404`, `AC-406`): 完成按钮 enabled/submitting/disabled/rejected、无报价
      禁用、断线、退出、完成和错误空态 — verify: `tests/e2e/test_h2_owner_terminal.py`
- [ ] T935 `[成果门:H2-D1]` (`SC-402`, `AC-402`, `AC-405`, `AC-406`): 生成可交互的本地交易终端
      preview，固定输入完成合法市价/限价委托、成交、撤单、拒单、断线与退出；证据标签为
      `experiment-preview` — verify: `tests/e2e/test_h2_owner_terminal.py`

### Phase 2：H2-D2 所有者训练、正式采集与个人交付

- [ ] T936 (`FR-403`, `DR-401`, `NFR-302`, `AC-403`, `AC-407`): 实现 preview gate、training/formal
      assignment、阶段解盲、假名化和 owner artifact PII guard — verify:
      `tests/unit/experiment/test_owner_privacy.py`
- [ ] T937 (`TR-302`, `AC-408`): 按冻结粒度写 owner 逻辑时点采样快照，连接委托、成交、账本、
      盘口和强平事件因果链，并支持技术中止的备用池补跑 — verify: `tests/integration/test_h2_owner_web.py`
- [ ] T938 (`SC-403`, `AC-408`): 在 E2 gate 通过后按冻结台账完成 6 个训练场景；训练结果不写入
      formal evidence index — verify: `tests/integration/test_h2_owner_delivery.py`
- [ ] T939 (`SC-403`, `AC-403`, `AC-408`): 交付训练后可启动 formal 的 owner session bundle，
      包含阶段/assignment/解盲 guard 矩阵；证据标签为 `experiment-preview`
      — verify: `tests/integration/test_h2_owner_delivery.py`

- [ ] T940 (`FR-302`, `TR-302`, `NFR-302`, `AC-405`, `AC-407`): 按冻结 assignment 完成 24 个正式
      owner 场景；结果字段对中止、补跑和解盲裁决保持不可见 — verify:
      `tests/integration/test_h2_owner_delivery.py`
- [ ] T941 (`DR-401`, `DR-402`, `AC-408`): 冻结 owner evidence index、session manifest、输入/事件/
      K 线 artifact 哈希和 sample flow — verify: `tests/integration/test_h2_owner_delivery.py`
- [ ] T942 (`SC-404`, `AC-407`, `AC-408`): 从 owner evidence index 生成个人描述性报告、代表性
      回放和限制声明，明确不外推到人群 — verify: `tests/integration/test_h2_owner_delivery.py`
- [ ] T943 `[成果门:H2-D2]` (`SC-403`, `SC-404`, `AC-407`, `AC-408`): 生成可打开的 owner
      `experiment-preview` 交付包；若场景不足则生成 `incomplete-study` 而不伪造完成 — verify:
      `tests/integration/test_h2_owner_delivery.py`

## 3. 验证与验收任务

- [ ] T944 (`AC-401`, `AC-402`, `AC-403`, `AC-405`, `AC-406`): 运行 Web API、K 线、委托、空态、
      断线、撤单和阶段 guard 正反测试 — verify: `tests/integration/test_h2_owner_web.py`
- [ ] T945 (`AC-404`, `AC-407`, `AC-408`): 运行 artifact 哈希、PII、owner index 隔离和新进程重建
      验证 — verify: `tests/integration/test_h2_owner_delivery.py`
- [ ] T946 (`AC-401`, `AC-402`, `AC-403`, `AC-404`, `AC-405`, `AC-406`, `AC-407`, `AC-408`): 运行
      项目统一质量门 — verify: `python tools/verify.py`
- [ ] T947 `[状态门]`: 回写 spec 验收证据、owner evidence index、版本索引和状态；必须是本文件最后
      一项 — verify: `python tools/validate_spec_lifecycle.py`

## 4. 依赖与并行关系

- `T927 -> T929 -> T930 -> T931`：先复用 session contract，再实现行情投影和 Web preview。
- `T929 [P]` 与 `T930 [P]` 可并行：K 线纯派生模块与 HTTP view 页面修改不同文件；`T931` 汇合。
- `T931 -> T932 -> T933 -> T934 -> T935`：页面先能看，再允许自由委托，最后验收错误/恢复状态。
- `T935 -> T936 -> T938 -> T939`：preview gate 通过后才占用所有者训练时间。
- `T939 -> T940 -> T941 -> T942 -> T943`：24 个正式场景完成后才冻结 owner index 和个人报告。
- `T944 [P]` 与 `T945 [P]` 可并行：运行时正反测试与交付包审计不共享 session 状态。

## 5. 明确后移

- 公开部署、登录/权限、多用户协作和真实行情 → 后续独立 Feature：当前目标是本地所有者终端。
- 限价单、复杂订单类型和高级图表指标 → 后续交易产品 Feature：先闭合 H2 已冻结动作空间。
- owner 结果的人群统计推断或因果中介识别 → 后续研究：本里程碑只交付个人描述性结果。
