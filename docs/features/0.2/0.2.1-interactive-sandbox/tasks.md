---
kind: milestone
id: 0.2.1
version: "0.2"
doc_kind: tasks
created: 2026-09-01
updated: 2026-09-04
---

# 0.2.1：H1 手动交易沙盒 - 任务

> Spec: `spec.md` | Design: `design.md`

## 0. 来源与执行规则

- 行为与验收真相源：[`spec.md`](spec.md)；技术方案与边界：[`design.md`](design.md)。
- 先写正反测试，再接生产入口；批量输入、活动订单和 artifact 必须包含多记录场景。
- 每项完成并验证后立即勾选；实现中若契约失效，先修订三件套。
- 三个 Phase 分别对应 PRD §15 的 H1-A、H1-B、H1-C 可见成果门。
- 所有产物标记 `interactive + engineering-demonstration`，不得进入研究证据。
- 推进到 `ready-for-development` 前，覆盖 AC-001—AC-008 的实现任务所列 `verify:` 测试文件
  必须已存在于 `tests/` 下；未实现行为可先用 `pytest.mark.xfail(strict=True)` 骨架占位并
  写明原因。门禁不接受目录或 `tools/verify.py` 代替具体测试文件。
- T816 保留 AC 范围声明用于检查验收上界；它的目录级 `verify:` 不满足逐条 AC 路径门禁，
  每条 AC 仍必须由 T803—T815 的具体测试文件独立覆盖。

## 1. 前置条件

- [x] T801 (`Q-201`—`Q-203`, `DQ-201`—`DQ-204`): 已确认浏览器 loopback 客户端、R2 派生演示配置、
      seed 7、默认暂停/单步、1×连续模式、输入记录策略和 ABORTED 恢复边界；Q 与 DQ 结论一致，
      重叠部分以 DQ 为准，Q 只保留产品口径并引用 DQ — verify: `spec.md`、`design.md`
- [x] T802 (`TR-201`—`TR-203`, `IR-201`—`IR-203`): 已冻结输入 artifact、会话接口、稳定错误码
      与 manifest 合同；冻结 H1 参数为 `max_transactions=80`、人类初始现金 `10,000.00`、空仓、
      `1×`、单笔最大数量 `1.000`、最多 `8` 个活动订单、最多 `64` 条待处理输入和默认端口 `8765`；
      若改事件 Schema，先完成版本提升和跨真源测试；冻结后创建 T803—T815 所列测试文件骨架，
      再推进 `ready-for-development` — verify:
      `docs/contracts/interactive-session.md`、`docs/contracts/event-schema.md`、
      `src/market_game_sim/schema/event_fields.json`；本合同冻结事件 Schema v4，不新增 H1 专用事件。

## 2. 实现任务

### Phase 1：H1-A 确定性交互会话

- [x] T803 (`FR-201`, `FR-204`, `IR-202`, `AC-001`, `AC-004`): 以正反测试实现会话状态机、
      单 writer inbox、暂停/继续/单步和逻辑时间分配 — verify:
      `tests/unit/interactive/test_session.py`、`tests/unit/interactive/test_pacing.py`
- [x] T804 (`FR-202`, `IR-201`, `AC-002`): 实现只读已提交状态的观察快照投影，按
      `AGENT_OBSERVE` 闭集覆盖未完成 K 线、超 k 深度、未来事件、代理私有状态和多活动订单
      不可泄漏场景 — verify:
      `tests/integration/test_interactive_observation.py`
- [x] T805 (`FR-205`, `TR-201`, `IR-203`, `NFR-201`, `AC-005`): 实现规范输入 journal、哈希
      和无墙钟等待的重放驱动 — verify: `tests/integration/test_interactive_replay.py`
- [x] T806 (`FR-206`, `NFR-203`, `AC-006`): 在正式运行、统计、报告与 evidence index 生产入口
      接入 manifest/header 双读、模式不一致、交互/缺失/未知拒绝矩阵；覆盖摘要不变的模式篡改、
      匹配非交互正例及多 bundle 整批零部分写入 — verify:
      `tests/integration/test_interactive_evidence_guard.py`
- [x] T807 `[成果门:H1-A]` (`AC-001`, `AC-002`, `AC-004`, `AC-005`, `AC-006`): 单命令生成
      可打开的 headless 会话说明、输入记录、事件日志和重放摘要，标记为
      `interactive + engineering-demonstration` — verify: `tests/integration/test_interactive_headless.py`

### Phase 2：H1-B 本地交易界面

- [ ] T808 (`FR-203`, `IR-201`, `TR-202`, `AC-003`): 将人类限价/市价下单与撤单接入现有
      决策、准入、撮合、账本和风险生产路径，覆盖接受/拒绝及批量订单 — verify:
      `tests/integration/test_human_order_path.py`
- [ ] T809 (`FR-207`, `UX-201`, `UX-202`, `UX-203`, `AC-007`): 实现选定本地客户端的市场、
      账户、订单、输入结果、会话控制和边界提示视图 — verify:
      `tests/integration/test_interactive_client.py`
- [ ] T810 (`FR-204`, `IR-202`, `NFR-202`, `AC-004`): 接通客户端控制、幂等键、断开与终态
      行为，验证没有半提交和终态复活 — verify: `tests/integration/test_interactive_control.py`
- [ ] T811 `[成果门:H1-B]` (`AC-003`, `AC-004`, `AC-007`): 用固定演示配置完成观察、合法下单、
      拒单、撤单与账户审查的本地闭环，标记为 `interactive + engineering-demonstration` —
      verify: `tests/integration/test_interactive_user_journey.py`

### Phase 3：H1-C 重放与交付包

- [ ] T812 (`FR-205`, `TR-201`, `TR-202`, `IR-203`, `AC-005`): 增加跨进程双次重放及输入
      篡改、截断、重复幂等键反例 — verify: `tests/integration/test_interactive_replay.py`
- [ ] T813 (`FR-208`, `TR-203`, `IR-203`, `AC-008`): 生成 RUN、manifest、输入日志、事件日志
      与离线 replay 的同源成果包，并校验全部内容哈希 — verify:
      `tests/integration/test_interactive_bundle.py`
- [ ] T814 (`NFR-202`, `NFR-204`, `AC-007`, `AC-008`): 验证 Windows 本机启动、客户端断开、
      日志写入失败、断网回放和 stable abort 行为 — verify:
      `tests/integration/test_interactive_failure_paths.py`
- [ ] T815 `[成果门:H1-C]` (`AC-005`, `AC-006`, `AC-007`, `AC-008`): 单命令交付代表性 H1 包，
      从 README 两次点击内可达并在新进程确定性重放，标记为
      `interactive + engineering-demonstration` — verify: `tests/integration/test_interactive_delivery.py`

## 3. 验证与验收任务

- [ ] T816 (`AC-001`—`AC-008`): 运行交互单元、集成、客户端与跨进程测试，逐项回填 AC 的
      真实测试路径 — verify: `tests/unit/interactive/`、`tests/integration/`
- [ ] T817 (`E5`): 运行唯一质量门并保存 H1-C 验证记录 — verify:
      `python tools/verify.py`
- [ ] T818 `[状态门]`: 核对 E1—E5、成果包、交互证据隔离与回归测试后，回写里程碑和版本
      状态；H1 不建立研究声明 — verify: `python tools/validate_spec_lifecycle.py`

## 4. 依赖与并行关系

- `T801 -> T802 -> T803`：先关闭产品/设计问题并冻结合同，再实现会话核心。
- `T803 -> T804/T805/T806 -> T807`：H1-A 先闭合确定性、观察边界和证据隔离。
- `T807 -> T808/T809/T810 -> T811`：客户端只消费已经稳定的交互协议。
- `T811 -> T812/T813/T814 -> T815 -> T816 -> T817 -> T818`：交付包与状态收口严格串行。

## 5. 明确后移

- H2 人在环正式实验 → 后续独立 Feature：须冻结随机分组、信息权限、操作窗口、学习/疲劳
  和排除规则，不与 H1 数据合并。
- 多人/远程/公网服务、身份与权限 → v0.3+：H1 仅单机单人 loopback。
- 真实交易连接、钱包和券商适配 → 永久非目标：违反产品安全边界。
- 股票式制度、多品种、订单流预知者与策略学习 → 各自新的可证伪问题规格，不进入 H1。
