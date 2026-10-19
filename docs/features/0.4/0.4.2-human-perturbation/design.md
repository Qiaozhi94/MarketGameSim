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
doc_kind: design
created: 2026-09-20
updated: 2026-10-17
---

# 0.4.2：人类扰动实验 - 技术设计

> Spec: [`spec.md`](spec.md) | Tasks: [`tasks.md`](tasks.md)

## 0. 输入与约束

- 行为真相源：[`spec.md`](spec.md)；本文不复制需求正文，只写实现方案与边界。
- 架构决策：[`ADR-010`](../../../decisions/010-market-ecology-research-pivot.md)（研究方向）、
  [`ADR-011`](../../../decisions/011-market-engine-trader-layering.md)（L1/L2 分层）、
  [`ADR-006`](../../../decisions/006-realtime-free-trading-owner-terminal.md)（自由连续交易）。
- 全局不变量（数值口径、事件因果链、确定性）由
  [`架构文档`](../../../market-game-sim-architecture.md) 与
  [`docs/contracts/`](../../../contracts/matching.md) 唯一拥有；本文只引用。
- 上游载体：`0.4.1` 的 `StrategyRoster` 装配、live 市场推进语义与 owner 终端页面；`0.4.3`
  的价值投资者族与扫描格装配。本里程碑不改两者的既有接口语义。
- 硬约束：不修改 L1 既有合同；不修改 0.4.1 已冻结的质量与 stylized facts 口径。
- 0.3.2 的 `experiment/h2/owner_web.py` 已归档，且跑在另一套引擎（`AiFlowGenerator` +
  `InteractiveRuntime`）上，**不是**本里程碑的影响面；0.2.1 的 `interactive/journal.py` 只服务
  `InteractiveRuntime`，不复用其代码，只沿用 `interactive/adapter.py` 为人类动作补发
  `AGENT_DECIDE` 的做法。

## 1. 技术概要与影响面

按依赖顺序落地：

1. **会话 artifact 冻结**——新增 `experiment/perturbation/session.py`：`PerturbationSession`
   的动作日志追加、封口、读取与校验入口，格式带版本号与内容哈希。**必须先于任何 owner 自由
   场次落地**。
2. **注入路径确定性修复**——改 `experiment/h2/live_market.py`（见 §5「并发」）：HTTP 线程
   只入队载荷；`advance()` 持锁取出时为每笔动作入队一条 owner 的 `AGENT_OBSERVE`（携带会话内
   动作序号），记录 `advance` 序号并追加动作日志；内核再经外部决策接缝派生决策与委托
   （见 §4、§5）；进程正常结束时封口。
3. **载体与预热**——载体 C 的 roster 按种子用 `experiment/roster.py::save_roster` 落盘到
   `docs/experiments/0.4.2-rosters/`（构造方式同 `metrics/anchor_scan.py::config_roster`）；
   live 市场新增预热：开放终端前连续调用 `advance()` 而不等待 `--tick-seconds`。
4. **同种子对照与回放**——新增 `experiment/perturbation/paired.py`：以同一装配参数与种子
   构建基线臂与有人类臂；有人类臂的动作按 `advance` 序号在推进循环中投递。同种子重放在
   Phase 1 交付，开环跨种子回放在 Phase 2 交付。
5. **效应量报告**——新增 `metrics/stability_effect.py`：四个稳定性指标的两臂分布、逐种子
   差值、效应量与区间。盘口可用率与大波动频次调用 0.4.1 既有实现（`quality_run.py` 的
   `two_sided_book_uptime`、`instability.py` 的分钟变动与强平连锁扫描，后者补窗口参数）；
   配对 bootstrap 原语加在 `experiment/stats.py`（见 DQ-603）。

影响面：`experiment/h2/live_market.py`（注入确定性、owner 观察事件入队、动作日志、预热、
回放动作源）、`experiment/runner.py`（`_dispatch_agents` 增加 owner 观察分支；
`_handle_external_decide` 增加撤单 `kind`）、`metrics/instability.py`（扫描函数增加可选窗口参数，缺省行为不变）、
`experiment/stats.py`（新增配对 bootstrap 原语）。**不影响** `experiment/h2/runner.py` 的
0.3.1 配对轨与 0.4.1、0.4.3 的质量门路径；纯 AI 运行不经过注入路径，事件流与入库摘要不变
（由既有回归门与专门断言证明）。

`live_market.py` 的 `_snapshot` / `export_metrics` 自带 `max_drawdown`（累计峰值口径，即
0.4.1 报告 §12 记录的缺陷口径）与 `big-move`（逐 advance、非分钟），它们是 0.4.1 终端的
**遗留诊断**，不是本里程碑的指标；artifact 导出与效应量报告只读 `metrics/stability_effect.py`
的计算结果，不复用这两个字段。

## 2. 架构与模块边界

```text
L1 交易引擎（不改）
  kernel/ book/ ledger/ eventlog/
        ▲ 与 AI 委托完全相同的撮合/账本/风控路径
        │
L2 交易者策略层（0.4.1 / 0.4.3，不改）
  agent/strategy_layer/            StrategyRoster 装配（含价值族）
        ▲
        │
live 市场（0.4.1，本里程碑改注入路径）
  experiment/h2/live_market.py     advance() 持锁取出 → 入队 owner AGENT_OBSERVE → 追加日志
  experiment/runner.py             owner 观察 → AGENT_DECIDE → _handle_external_decide → ORDER_ARRIVAL
        ▲
        │
人类扰动（本里程碑新增）
  experiment/perturbation/session.py   动作日志 + 封口 + 校验入口
  experiment/perturbation/paired.py    基线臂、同种子重放、开环回放与配对
  metrics/stability_effect.py          四指标效应量与区间（统计原语在 experiment/stats.py）
```

边界规则：人类动作只能通过既有的外部注入路径进入内核，与 AI 委托共用撮合与风控；
本里程碑不新增事件类型，人类动作只产生既有类型（`AGENT_OBSERVE` / `AGENT_DECIDE` /
`ORDER_ARRIVAL`）的新实例。

## 3. 数据模型与 Migration

- `PerturbationSession`（新增）：一个 JSONL 文件，每行 `flush`。字段、取值范围、记录顺序、
  内容哈希定义与稳定原因码的**唯一冻结记录**是
  [`0.4.2-perturbation-session-format.json`](../../../experiments/0.4.2-perturbation-session-format.json)
  （T1120，v1）；`experiment/perturbation/session.py::FROZEN_FORMATS` 把版本钉到该文件的
  sha256，文件改动而未新建版本即 `FORMAT_DRIFT`。下面只列结构，细则以冻结记录为准。每条
  记录带 `record_type`（`header` / `action` / `seal`）。
  - **头记录**（第一行，会话开始时写入）：`format_version`、`session_id`、`arm`
    （`baseline` / `human`）、`replay_mode`（`original` / `same_seed_replay` / `open_loop_replay`）、
    `roster_id`、`seed`、`engine_config_digest`、`evidence_class: experiment-preview`、
    `run_mode: interactive`；
  - **动作行**（每笔动作被 `advance()` 取出时追加）：`advance_index`、`action_seq`（会话内单调）、
    动作类型与载荷（撤单以 `target_action_seq` 指向被撤的下单动作，不记 `order_id`）、`wall_clock_ms`；
  - **封口行**（进程正常结束时追加）：`end_advance_index`、`event_digest`（结束序号处的事件
    摘要，E-002 滚动摘要）、`observation_digests[]`（每条已提交的 owner 观察一项：
    `action_seq` + 其 `information_set` 的摘要）、`content_hash`（须等于重算值）。
  `content_hash` = 头记录与全部动作行的规范行字节的 sha256，封口与否都可计算；缺封口行即
  `UNSEALED`；文件末尾未以换行结束的残片（写入中途被终止）不是记录，排除并报告。`order_id`、时间戳、`submitted_at`、`decision_event_id` 是内核派生结果，不写入
  动作行，由重放复现。
- `PerturbationPreregistration`（新增，JSON，单一文件）：功效分析报告引用、`σ_b` 与功效公式、
  处理会话内容哈希清单、逐指标 MDE、N、有效配对下限、开环回放种子清单；sha256 由测试钉住，
  配对入口只读该文件。
- `PerturbationEffectReport`（新增，JSON）：`preregistration_sha256`、`treatment_session_hash`、
  `pair_set_id`、`pairs[]`（种子、两臂运行标识、回放模式）、`metrics{}`（每指标两臂分布、
  逐种子差值、效应量、区间、实测 `σ_d`、功效判定）、`failure_boundary`（退化配对、中止配对、
  载体 SC-501 失效的种子，各带原因码）、`original_cases[]`、`out_of_window_actions`、
  `evidence_class: experiment-preview`、`run_mode: interactive`、`content_hash`。
  **有效配对数低于下限时效应量字段缺省**（不是 0），避免零功效被读成零效应。
- 无既有数据迁移：各类 artifact 均为新增文件，不改写 0.3.2 owner 会话或 0.4.1/0.4.3 质量报告。
- 兼容规则：`format_version` 变更必须是显式改动；旧版本 artifact 按其声明的版本解析，
  不就地改写语义。

## 4. 接口、Contract 与 Event

- 会话写入/读取（IR-601）：`append_action(journal, action)` / `seal_session(path, seal)` /
  `load_session(path)` / `validate_session(payload)`；校验失败返回稳定原因码，不抛裸异常。
- 动作回放（T1126 落地为 `LiveMarket.schedule_actions` + `perturbation/paired.py::run_arm` /
  `replay_same_seed`；序号已过给 `REPLAY_ACTION_LATE`，投递时重新分配的序号与动作行不符给
  `REPLAY_SEQUENCE_MISMATCH`，两者都归入 `REPLAY_DIVERGED`；封口与重放共用
  `LiveMarket.seal_digests()`，事件摘要与 owner 观察摘要分别比对）：在推进循环中，于每次 `advance()`
  取出阶段投递 `advance_index` 等于当前序号的动作，按日志顺序入队；同种子重放推进到
  `end_advance_index` 后比较事件摘要，不一致返回 `REPLAY_DIVERGED`；动作序号早于当前序号
  （无法投递）返回稳定原因码并判失败，不得跳过动作或改写时点。开环回放推进到 5700 s。
- 事件（TR-601）：**不新增事件类型**。不能在注入时直接入队决策与委托：队列键是
  `(timestamp, priority_class, enqueue_seq)`，同一时间戳下委托类（0）先于决策类（4）处理
  （`kernel/keys.py:36-40`、`:80-85`）；决策的 `event_id` 是事务提交时的 `e{txn}_0`
  （`kernel/runner.py:482`），入队时拿不到；`chain_verifier` 要求 观察 → 决策 → 委托 严格先后
  （`evidence/chain_verifier.py:85-110`）。因此走既有链：
  1. `advance()` 入队一条 owner 的 `AGENT_OBSERVE`（时间戳取现有 `_safe_ts()` 口径，携带
     `_owner_action_seq`）；
  2. `_dispatch_agents` 对带 `_owner_action_seq` 的观察走 owner 分支（参照
     `_handle_stress_observe` 的「记录为真实 观察 → 决策 链」做法）：记录观察（`information_set`
     为 `{owner_action_seq, market_data_event_id}`，封口的 `observation_digests` 即对它取摘要），
     在**同一时间戳**入队 `AGENT_DECIDE`（类 3 → 4 是前进类，与 stress 路径同口径；owner 的
     思考时间已发生在终端侧，内核里不再加一段决策延迟），**不**参与周期性观察重排；
  3. 该决策走 `_handle_external_decide`（`experiment/runner.py:433-480`），外部源按
     `_owner_action_seq` 从会话动作源取载荷，返回 `MARKET` / `LIMIT` / `CANCEL`（撤单为本里程碑
     新增 `kind`）；接缝生成 `ORDER_ARRIVAL`，`decision_event_id = e{txn}_0`，`order_id`
     （`o-owner-e{txn}_0-{seq}`，`experiment/runner.py:456`、`:479`）、到达时间（决策时间 + owner
     延迟）与 `submitted_at` 均由内核确定；参与者类别 `human` 由 owner 源追加进决策记录的
     `internal_state`（接缝现只写 `decision_source` / `window_index`，`:504-506`）——T1124 落地为
     外部源可附 `internal_state`（owner 源写 `decision_source: live_owner_terminal`、
     `participant_class: human`、`owner_action_seq`），并以可选的 `orders_submitted` 回调把
     新下委托的 `order_id` 交回源。
  4. **撤单目标的解析**：owner 决策源在每次运行内维护 `action_seq → order_id` 映射，下单委托
     生成时登记；撤单载荷带 `target_action_seq`，源据映射解析出本次运行的 `order_id`，映射中
     没有（该下单在本种子上未生成委托）时决策为 `NO_ACTION` 并留原因码
     `CANCEL_TARGET_UNRESOLVED`，目标已不在簿时撤单照常入内核、按既有撤单语义不产生
     `ORDER_CANCELLED`；撤单委托与 AI 撤单同形（`order_id` 即被撤目标）。终端按委托
     视图里的 `order_id` 撤单（`owner_terminal.html:143-145`）：HTTP 线程只把它原样入队（§5，
     HTTP 线程不读内核状态），由 `advance()` 持锁取出时用同一映射反查成 `target_action_seq`
     再写入动作行——换种子后 `order_id` 必然不同，动作行里不能出现它；反查不到（非 owner 委托
     或不存在的编号）时按 spec 边界场景「入队后才判定的无效撤单」处理：丢弃该载荷、不进内核、
     不入动作日志，终端没有同步回执（它已收到「已入队」）——与 HTTP 线程当场拒绝的格式校验失败
     不是同一类。
  **owner 规格的注册位置与约束**：
  - 只注入运行时 `world["agent_specs"]`（`live_market.py:244` 处），**不**进 `config.agent_specs`——
    后者会让 `live_market.py:263-273` 在 t=0 给 owner 排一条观察并周期重排，改变纯 AI 摘要；
  - 两臂都注入、计入引擎配置指纹（会话头记录的 `engine_config_digest` =
    `live_market.session_engine_config_digest`：roster 引擎块 + `OWNER_SPEC` 的 blake2b-128）；`_handle_external_decide` 依赖 `agent_specs[owner]`（`:455`，
    缺则 `KeyError`）与 `accounts[owner]`（`:458`，`live_market.py:219` 已建）；
  - owner 的 `latency_ns ≥ 1`（`OWNER_SPEC` 取 1 ms，与 `_safe_ts()` 的间隔一致）：`AGENT_DECIDE → ORDER_ARRIVAL` 是优先级类回退，调度白名单要求
    时间戳至少前进 1 ns（`kernel/scheduling.py:31`），否则 `KernelAbort`；
  - T1124 断言注入后纯 AI 运行的事件流与 0.4.1/0.4.3 入库摘要逐位不变，不成立即回到本节重新设计。
  - **会话落盘**：`LiveMarket(session_path=...)`（CLI `--session-out`，须同时给
    `--roster-file`）在构造时写头记录；动作行在取出时先落盘再入队观察；进程正常退出时
    `seal_session()` 封口，`end_advance_index` 取已开始的 `advance()` 次数（即下一次 advance
    的序号，回放推进到序号等于它为止），`event_digest` 为封口时全部已提交事件的 E-002 滚动摘要。
- 证据索引隔离（AC-607）：既有拦截点是 `showcase/evidence_index.py::_validate_common_scope`
  （只接受 `run_family = SPONTANEOUS` 且 `evidence_class = formal-research`）与
  `evidence/evidence_guard.py` 的 `RunMode.INTERACTIVE`；本里程碑的 artifact 与报告显式携带
  `experiment-preview` 与 `run_mode: interactive`，并有测试断言交给索引构建入口时被拒绝。
- 报告入口：`build_stability_effect_report(pairs, preregistration)`；统计原语来自 `experiment/stats.py`。

## 5. Runtime、Workflow 与并发

- 基线臂：用 `StrategyRoster` + seed 构建纯 AI 市场，无任何外部注入，逐点记录指标序列。
- 有人类臂：同一装配参数 + seed，动作源为 owner 实时终端（采集）或冻结动作日志（回放）。
- 预热：live 市场启动后先不等待墙钟连续推进到 `W0 = max(冷启动退出, 3660 s)`，期间终端只读、
  拒绝下单；推进到 5700 s 仍未退出冷启动时拒绝开放并给原因码。载体 C 种子 7 实测：到 3660 s
  需 2545 次 advance、墙钟约 164 s。之后按 `--tick-seconds` 节拍推进；**每次 advance 推进的
  逻辑时间不是固定 1 秒**，窗口 3660→5700 s 实测 1459 次 advance，`--tick-seconds 1.0` 下约
  28 分钟墙钟。`--tick-seconds` 帮助文字里「1:1 实时」的说法随 T1125 改正。
- 预热的落地（T1125）：`LiveMarket(warmup=True)`（`--roster-file` 启动时一律开启）的终端阶段为
  `WARMING_UP → OPEN`，或 `WARMING_UP → NOT_APPLICABLE`（原因码 `COLD_START_NOT_EXITED` /
  `KERNEL_ABORT`）。预热期间逐次 advance 增量跟踪各代理最后一条决策是否带锚，判据与
  `quality_run.window_start_ns` 相同；逻辑时间第一次越过 `W0` 的那次 advance 之后开放，
  HTTP 入口在非 `OPEN` 阶段直接以阶段名拒绝、不入队、不入日志；会话文件随开放建立（头记录
  先于任何动作），文件已存在则在预热开始前就失败。载体 C 的清单由
  `experiment/perturbation/carrier.py` 用 0.4.3 预注册的固定项生成，种子 7 已落盘为
  `docs/experiments/0.4.2-rosters/roster-e7c9bdeeb558c5b7ed849d73e0e33704.json`；功效与开环
  种子随 T1127 预注册用同一函数生成。实测（真实常量）：种子 7 的 30 个锚定代理在第一次
  决策后即退出冷启动，`W0 = 3660 s`，2545 次 advance、墙钟约 170 s 后开放。
- 并发（注入确定性）：
  - HTTP 线程只做格式校验并把载荷放入队列；不读 `logical_ns`、不扫描内核队列、不分配任何
    序号或标识，返回的是「已入队」而不是 `order_id`（`order_id` 由内核在决策事务里生成，
    终端从盘口与委托视图读取）；
  - `advance()` 持 `LiveMarket.lock` 依次取出载荷，在同一临界区内分配 `action_seq`、按
    `_safe_ts()` 口径入队 owner 的 `AGENT_OBSERVE`、记录当前 `advance` 序号并追加动作行——
    HTTP 线程不生成任何进入事件流的字段；决策记录与委托由内核在随后的事务里派生（§4）；
  - 人类思考时间不阻塞内核推进（ADR-006 的连续市场前提）；
  - 回归测试用确定性交错钩子（在入队与 `advance()` 之间注入可控的调度点）构造「同一 advance
    内多笔提交」「提交恰在推进中途」两类交错，不用真线程碰运气。
- 采集与回放的关系：实时采集产出带 `advance_index` 与 `action_seq` 的动作日志；由于事件流里
  的全部 owner 字段只由这两个序号与载荷决定，同种子重放应与原场逐位一致，不一致即视为实现缺陷（`REPLAY_DIVERGED`），不作为
  可报告的「差异」（spec Q-604）。

## 6. UI 与可观测性

- 沿用 0.4.1 live 市场自带的 owner 终端页面，不做界面重做；预热期间页面显示预热进度并禁用
  下单。
- 可观测产物：会话 artifact、功效分析报告、预注册文件与效应量报告；退化判定、功效判定与
  载体未达标声明在报告顶层可见。
- CLI：`python -m market_game_sim.experiment.perturbation.paired`（`baseline` / `replay` /
  `pair`：基线、同种子重放、只读预注册的正式配对，开环回放在 `pair` 内按预注册种子运行）与
  `python -m market_game_sim.experiment.perturbation.preregistration`（`power` / `preregister`），
  命令在 `RUN.md` 记录。
- 实现落地（T1127/T1129/T1131）：配对入口唯一的预注册读取点是 `preregistration.begin_pairing`
  （缺失 / 未钉住 `PREREGISTRATION_SHA256` / 哈希不一致 / 功效报告被改 / 处理会话不在其中即
  fail closed），报告写出前 `verify_preregistration` 再核一次；开环撤单的结局（`CANCELLED` /
  `TARGET_NOT_ACTIVE` / `TARGET_UNRESOLVED` / `NOT_PROCESSED`）从事件流归类并逐对列入报告，不改
  内核撤单语义；失效边界的「载体 SC-501 失效的种子」按 SC-501 的五个市场项判定，墙钟性能项与
  种子无关、不计；全窗口运行单进程峰值内存 11 GB 以上（2026-10-19 实测：三进程并行与单进程
  各一次都因内存压力被中止），功效基线逐种子落盘续跑缓存，只宜单进程跑。

## 7. 失败、恢复、安全与兼容

- 市场进程被异常终止：头记录与动作行已逐条落盘，会话为 `UNSEALED`，身份、种子与内容哈希
  可读可校验，可作开环处理并被预注册收录，不作原场个案。
- 同种子重放与原场不一致：`REPLAY_DIVERGED`，fail closed，该会话不进入配对。
- 动作回放无法投递（序号已过）：判失败并给稳定原因码；不得跳过动作或改写时点。
- 预注册文件缺失、哈希不一致或处理会话不在其中：配对入口 fail closed。
- 退化与中止按配对判定：退化配对（窗口内零成交、单边空簿、基线臂中止）与人类臂中止配对
  列入失效边界；有效配对数低于预注册下限时整份报告不出效应量。
- 安全与边界：artifact 不含直接身份信息与凭据；不连接真实账户或外部网络；
  产物一律标注 `experiment-preview` 与 `run_mode: interactive`，被 evidence index 入口拒绝（§4）。

## 8. 测试策略与验收映射

| AC | 主要测试 | 层次 |
|---|---|---|
| AC-601 | artifact 冻结格式的正反校验（合法落盘 / 缺字段与错版本号被拒） | 单元 |
| AC-602 | 头记录先写、逐条追加：任意动作后终止进程不丢动作、标 `UNSEALED` 且可校验；空会话与多动作封口会话 | 单元 + 集成 |
| AC-603 | 同种子基线逐点复现；同种子重放逐位一致与篡改判失败；确定性交错下的注入 | 集成 |
| AC-604 | `chain_verifier` 对含 owner 下单与撤单的事件流通过；并存批量场景 | 集成 |
| AC-605 | 效应量报告：有效 / 退化 / 人类臂中止三类输入；回撤/涨幅窗口起点重置；功效不足标注 | 单元 + 集成 |
| AC-606 | 画像/对错判定字段与身份信息的拒绝用例 | 单元 |
| AC-607 | artifact 与报告交给 evidence index 构建入口被拒；合规输入不受影响 | 集成 |
| AC-608 | 载体清单哈希与参数；预热前拒单、预热后开放、5700 s 仍未退出冷启动时拒绝开放 | 集成 |
| AC-609 | 预注册文件缺失 / 哈希不一致 / 处理会话不在其中时配对入口 fail closed | 单元 |
| AC-610 | 开环回放按序号投递并推进到 5700 s；配对集合可重建；撤单按 `target_action_seq` 解析，仍挂着的被撤、已成交/被拒的记原因码 | 集成 |

既有回归：0.4.1 质量门、0.4.3 锚定市场门、0.3.1 配对轨与 0.3.2 终端测试必须全绿；
纯 AI 运行的 0.4.1/0.4.3 入库摘要不变。

## 9. 已确认决策与残余风险

- 已确认：命题形态为效应量命题；artifact 格式先于第一场冻结；不判对错、不做画像；
  不新增事件类型；分析单元为种子、主效应量取开环回放（spec Q-601—Q-604）；功效分析取保守
  近似；owner 委托经 观察 → 决策 → 委托 链由内核派生（spec §7 决策表）。
- 残余风险 1：开环回放把动作与市场状态的对应关系打断——限价单的绝对价格在其他种子上
  可能远离盘口。缓解是报告标签强制写「固定订单流扰动」，并逐场列出原场个案作对照。
- 残余风险 2：`ρ ≥ 0` 假设不成立导致功效被高估——缓解是报告给出实测 `σ_d`，超出上界即标注
  功效不足，而不是把区间压在 0 上宣称「无影响」。
- 残余风险 3：载体 C 在 20 个功效种子之外的种子上可能停摆或钉死——这类种子作为退化或
  失效边界如实报告，不替换种子。
- 残余风险 4：证据级别升级冲动——任何结论只能以 `experiment-preview` 形态呈现，升级须另立预注册。

## 10. 待确认设计问题

- [x] DQ-601: 动作序列的时点基准取逻辑秒还是墙钟毫秒，两者在回放对齐上的取舍？ — 决策：owner 2026-10-15 裁决以 `advance` 序号 + 分配的逻辑纳秒时间戳为对齐基准，墙钟只作辅助字段；仅记录屏幕上的逻辑秒不足以逐位重放（委托实际落在取出时刻之后的安全时点）。
- [x] DQ-602: 基线臂与有人类臂是否共享同一进程内的 RNG 流，还是各自独立构建？ — 决策：owner 2026-10-15 裁决两臂各自独立构建；市场对装配参数 + 种子完全确定，独立构建与共享等价且更易隔离。
- [x] DQ-603: 效应量的区间算法取配对 bootstrap 还是解析近似，`experiment/stats.py` 现有哪一支可直接复用？ — 决策：owner 2026-10-15 裁决取配对 bootstrap（逐种子差值重采样，报中位数与 90% 分位区间）；`experiment/stats.py` 现只有比例差的 `bootstrap_proportion_diff`，不能直接用于连续指标，故在同一模块新增连续指标的配对 bootstrap 原语，显式传 `ci_level = 0.90`，重采样次数与种子取 10000 / 0（与 `bootstrap_proportion_diff` 的缺省一致），不另建第二个统计模块。
