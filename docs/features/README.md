# docs/features —— 版本与里程碑（Feature / Milestone）生命周期

本文是 `docs/features/` 的入口与规则唯一真源，规定 Feature/里程碑三件套的职责、状态
门、问题语法（Q/DQ）与版本收口方式。本目录**不是**某份正文的复制，状态与需求正文只
属于各 `spec.md`。

> 参考：与 PersonaHub 共用同一套 docs 骨架与生命周期；MarketGameSim 额外保留
> `traceability.json` 与 `contracts/`、`experiments/` 差异。

## 目录骨架

```text
docs/features/
├─ README.md           # 本文：规则与入口
├─ TEMPLATE/           # 三件套模板唯一真源
│  ├─ spec.md
│  ├─ design.md
│  └─ tasks.md
├─ releases/           # 版本收口记录（<version>.md）
└─ <version>/          # 版本根 + 里程碑
   ├─ README.md        # 版本入口与收口提示（派生，不声明独立状态）
   ├─ spec.md          # 版本级研究规格（状态唯一真源）
   ├─ design.md        # 跨里程碑共享技术设计（承接原 plan.md）
   ├─ traceability.json# requirement → milestone → exit 机器追踪
   └─ <milestone>/
      ├─ spec.md
      ├─ design.md     # gate v1 起必选
      └─ tasks.md
```

## 状态唯一真源

- **唯一状态真源**是每个版本/里程碑 `spec.md` 的 frontmatter `status`。
- `research_claim_status` 是与工程生命周期正交的研究声明状态，只允许
  `not-applicable`、`not-established`、`established`；它不替代或复制 `status`。
- `design.md`、`tasks.md`、`README.md`、`CLAUDE.md` **不得**声明第二份独立 Status；
  它们只链接或展示由 spec 派生的索引。
- 状态机：`draft → ready-for-development → in-progress → review → done`。
- `status` 表示生命周期；`prerequisites` 表示调度依赖；两者分离，不再使用
  「Ready after 0.1.3」这类混合自由文本。
- 版本根只有在全部里程碑 `done` 且收口检查通过后才能变为 `done`。
- `research_claim_status: established` 只允许与 `status: done`、
  `evidence_class: formal-research` 和存在的 `research_evidence` 路径同时出现；版本根
  `done` 时不得仍为 `not-established`。
- 需要以研究声明作为退出条件的 spec 必须声明 `research_claim_required: true`（合法值
  只有 `true`/`false`，其它写法一律拒绝）；此时 `status: done` 与
  `research_claim_status: established` 必须同时成立，且 `not-applicable` 与
  `required: true` 并存在任何状态下都是矛盾配置。
- `evidence_class` 合法值为 `engineering-demonstration`、`experiment-preview`、
  `formal-research` 三类；其中只有 `formal-research` 能建立研究声明，`experiment-preview`
  声明 `established` 会被门禁拒绝。标签语义由 [`PRD §15`](../market-game-sim-prd.md#15-交付路线图)
  唯一拥有，本文只规定它在 frontmatter 里的取值与组合约束。

## 三件套职责

| 文件 | 职责 |
|---|---|
| `spec.md` | 做什么、怎样算完成。**状态唯一真源**，固定 9 个顶层章节（§2.3.1）。 |
| `design.md` | 怎么实现、边界与取舍。固定 11 个顶层章节；不写逐步编码任务。 |
| `tasks.md` | 按什么顺序实施。固定 6 个顶层章节；Phase 只作为第 2 节动态三级标题。 |

### 阶段成果门

本节是阶段成果门规则的唯一拥有者；PRD 只拥有项目级成果顺序与投入估算，模板只给
书写形态，两者都不再复述规则本身。

- 预计超过 **8 个工程小时**的 Feature/里程碑，`tasks.md` 第 2 节必须按可独立演示的
  Phase 切分。
- **每个 Phase 的最后一项任务必须是成果门**，标记为 `` `[成果门:<ID>]` ``（ID 与 PRD
  §15 的成果门编号一致，如 `R1`），并写明用户可打开的产物、生成入口、验收动作与证据
  标签。裸 `` `[成果门]` ``（无 ID）不接受。
- Phase 的完成标准不能只是“若干 task/测试通过”；没有 `replay.html`、报告、可调用接口、
  可观察行为或同等可消费产物，就不算阶段成果。
- 研究项目的中间产物必须标记 `engineering-demonstration`、`experiment-preview` 或
  `formal-research`，不得把 smoke run 或预览升级成正式结论。
- 以上前三条对 `gate_version: 1` 且 `created >= 2026-08-14`（规则引入日）的里程碑由
  `tools/validate_spec_lifecycle.py` 强制执行；规则引入前已完成的里程碑不追溯执法。
- 任务 ID 在 `tasks.md` 内唯一且按文档顺序递增（允许跳号），同样由门禁执行——编号顺序
  与执行顺序背离时，依赖关系只能靠人读出来。
- 跨里程碑检索也必须无歧义：0.2.x 从当前全仓未使用的 T8xx 号段开始；2026-09-01 起创建的
  里程碑任务 ID 必须与全仓其他里程碑唯一，由门禁校验，不能只靠约定号段。
- 回写生命周期状态的那一项任务标记 `` `[状态门]` ``：**必须存在、全文件唯一、且是最后
  一项**。`done` 要求全部任务勾完，状态门排在任何任务之前都会形成"`done` 要求该任务
  完成、该任务又要求先 `done`"的不可满足顺序。门禁按标记判定，不猜任务描述的措辞——
  "推进/更新为/设为 done" 是同一件事，而"核对 `done` 的前置证据"不是。
  **没有豁免**：所有 gate v1 里程碑一律要求，0.1.4 的 T405 已回填标记。曾经尝试过按
  `created`（或 `status == done 且 created < 规则日`）豁免历史里程碑，两版都错——
  frontmatter 里没有"何时关闭"这个事实，`created` 不是它的代理，第二版还会在里程碑
  将来转 `done` 的那一刻自动打开缺口。
- 项目级成果顺序、投入估算与交易者介入边界由
  [`PRD §15`](../market-game-sim-prd.md#15-交付路线图) 唯一拥有；Feature 文档只说明
  本 Feature 如何满足对应成果门。

### gate 规则

- `gate_version: 0`：仅用于已确认的 legacy 里程碑（0.1.1—0.1.3），只执行元数据、
  状态唯一性、路径、链接与现有 traceability 校验。**新建或回退到 v0 必须失败。**
- legacy `done` 若仍有未勾任务，spec 必须声明 `legacy_open_tasks_migrated_to`，且每项任务
  用 `[migrated-to: <milestone>/<task>]` 唯一映射到真实后继任务；不得伪造勾选。
- `gate_version: 1`：新里程碑（0.1.4 起）必选。额外校验三件套齐全、顶层结构与模板
  完全一致、Q/DQ 全部关闭；标记 `done` 时 tasks 与 AC 必须全部完成。
- 对 2026-09-01 起创建的里程碑，版本根 spec 只保留 requirement ID、一句话意图与里程碑
  正文链接；里程碑 spec 唯一拥有完整需求正文。同一 US 在两处出现时标题必须一致。
- AC 校验（gate v1）的具体口径：
  - 每条 AC 括号内引用的 ID 必须真实存在——`FR/NFR/SC/DR/TR/IR/US/UX` 在本 spec 或版本根
    spec 声明过，`PR/KPI` 在 PRD 声明过，`E<n>` 在本 spec 的退出条件表里；
  - 每条 AC 必须被至少一个任务引用（`` `AC-001`—`AC-012` `` 这类范围声明会展开计入）；
  - `ready-for-development` 及以上，覆盖该 AC 的任务里至少有一条 `verify:` 指向仓库内
    `tests/` 下真实存在的测试文件；目录和 `tools/verify.py` 等非测试路径不计入。`draft`
    阶段允许测试尚未创建，只要求引用关系成立。

### 固定顶层章节

`spec.md`（9 章）：

```text
0. 来源与意图
1. 问题、目标与非目标
2. 用户场景
3. 范围与边界
4. 需求
5. 生命周期与不变量
6. 成功与验收
7. 测试、依赖与决策
8. 待确认问题
```

`design.md`（11 章）：

```text
0. 输入与约束
1. 技术概要与影响面
2. 架构与模块边界
3. 数据模型与 Migration
4. 接口、Contract 与 Event
5. Runtime、Workflow 与并发
6. UI 与可观测性
7. 失败、恢复、安全与兼容
8. 测试策略与验收映射
9. 已确认决策与残余风险
10. 待确认设计问题
```

`tasks.md`（6 章）：

```text
0. 来源与执行规则
1. 前置条件
2. 实现任务
3. 验证与验收任务
4. 依赖与并行关系
5. 明确后移
```

## 问题语法（Q / DQ）

- spec 待确认问题用 `Q-xxx`，design 用 `DQ-xxx`。
- 开放：`- [ ] Q-001: <问题>`；关闭：`- [x] Q-001: <问题> — 决策：<结论>`。
- 「8. 待确认问题」/「10. 待确认设计问题」只接受规范 checkbox 或单独一行 `无`；
  禁止自由文本、空章节、缺章节。
- `ready-for-development` 及以上不允许 spec/design 留有未关闭问题。

## 版本收口

- 某版本全部里程碑 `done` 后：新建 `docs/features/releases/<version>.md`，版本根
  `spec.md` 原地转为 `done`（不复制 stable spec），新增或更新版本 README 标记收口。
- `closed_at` 写入前必须验证全部里程碑状态、traceability、合同真源、链接和测试门禁。
- 不创建 `v0.x-stable` 副本，不把里程碑移动到 archive，不重写 requirement owner。

## 需求追踪

- `traceability.json` 是 requirement → milestone → exit 的机器追踪真源。
- `UX` 是里程碑本地家族，只在里程碑 spec 声明并由 AC 认领，不进入版本级
  `traceability.json`；版本级矩阵只追踪跨里程碑归属的家族。
- requirement `statuses` 只表示 `owned/deferred/removed`；milestone 生命周期由各
  milestone `spec.md` frontmatter 表示；release 生命周期由版本根 `spec.md` 与
  `releases/<version>.md` 表示。
- 退出条件编号只在单个里程碑内唯一，跨里程碑引用用 `<milestone-id>/<exit-id>`。

## 相关入口

- `docs/README.md`：全仓文档所有权地图。
- `docs/SOP.md`：开发纪律与质量门。
- 唯一公开验证入口：`python tools/verify.py`。
