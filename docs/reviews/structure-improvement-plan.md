# MarketGameSim 目录结构改造方案

> 状态：**Approved v1.4（模板结构已定稿，尚未实施）**  
> 基线日期：2026-08-09  
> 实施时机：另行安排；实施前必须确认工作树状态并按本方案执行  
> 参考：PersonaHub `structure-improvement-plan.md`、`docs/features/README.md`，以及
> GitHub spec-kit / OpenSpec 的模板与变更收口思想  
> 原则：**两个项目采用相同的 docs 骨架与 Feature 生命周期；保留 MarketGameSim
> 为可复现实验所必需的 traceability、contracts、experiments 差异。**

## 0. 基线结论

MarketGameSim 的现有规格、合同、ADR、四层测试、实验出口和需求追踪已经有效，不需要
重新设计内容模型。本次改造解决的是文档入口与生命周期不统一，而不是重写已有规格。

正式采用以下结论：

1. SDD 文档迁入 `docs/features/`，采用与 PersonaHub 相同的
   `README + TEMPLATE + releases + <version>` 骨架。
2. 现有 `specs/v0.1-belief-testing-laboratory/` 整体迁为 `docs/features/0.1/`；
   内部 0.1.1—0.1.4 里程碑名称与相对层级保持不变。
3. 版本根 `plan.md` 改名为 `design.md`。已实现的历史里程碑不事后补写虚构的
   `design.md`；0.1.4 和以后新建的里程碑采用 `spec/design/tasks` 三件套。
4. 版本收口采用 PersonaHub 的逻辑收口：保留稳定路径，新增 `releases/0.1.md` 和版本
   README；不创建 `v0.1-stable` 副本，不把里程碑移动到 archive。
5. `traceability.json` 保留需求 owner、milestone 和 exit 的原始语义。目录迁移只更新
   path，不重写 owner，不给 requirement statuses 增加 `archived`。
6. 模板只放在 `docs/features/TEMPLATE/`；现有 `.specify/templates/` 在实施时迁入并删除，
   不保留镜像或第二份模板。
7. PersonaHub 不使用独立 constitution 文件，而是按职责由 PRD、architecture、decisions、
   SOP 和 CLAUDE 分别拥有。现有 constitution 内容按同一规则迁入对应文档，迁移完成后
   删除 `.specify/`，不新建 `docs/constitution.md`。

本方案当前仅作为实施基线。**本次定稿不执行目录移动、frontmatter 迁移、源码修改或
CI 修改。**

## 1. 目标目录结构

### 1.1 仓库目标结构

```text
market-game-sim/
├─ .github/
│  └─ workflows/
│     └─ ci.yml
├─ benchmarks/
├─ conversations/
├─ data/
├─ docs/
│  ├─ README.md                         # 文档地图与所有权索引，不复制正文
│  ├─ decisions/                       # 原 docs/adr
│  │  ├─ 000-template.md
│  │  ├─ 001-numeric-and-serialization-contract.md
│  │  └─ 002-same-timestamp-event-scheduling.md
│  ├─ features/
│  │  ├─ README.md                     # SDD、状态门、模板和版本收口规则
│  │  ├─ TEMPLATE/                     # Feature/里程碑模板唯一真源
│  │  │  ├─ spec.md
│  │  │  ├─ design.md
│  │  │  └─ tasks.md
│  │  ├─ releases/
│  │  │  └─ 0.1.md
│  │  └─ 0.1/
│  │     ├─ README.md                  # 版本状态；收口后标记只读维护
│  │     ├─ spec.md                    # v0.1 版本级研究规格
│  │     ├─ design.md                  # 原 plan.md，共享技术设计
│  │     ├─ traceability.json          # MarketGameSim 特有的追踪真源
│  │     ├─ 0.1.1-minimal-kernel/
│  │     │  ├─ spec.md
│  │     │  └─ tasks.md
│  │     ├─ 0.1.2-leverage-and-first-experiment/
│  │     │  ├─ spec.md
│  │     │  └─ tasks.md
│  │     ├─ 0.1.3-robustness/
│  │     │  ├─ spec.md
│  │     │  └─ tasks.md
│  │     └─ 0.1.4-replay-and-report/
│  │        ├─ spec.md
│  │        ├─ design.md               # 迁移时补齐；尚未进入实现
│  │        └─ tasks.md
│  ├─ research/
│  │  ├─ methodology.md                # 原 docs/product/methodology.md
│  │  └─ metrics-dictionary.md         # 原 docs/product/metrics-dictionary.md
│  ├─ reviews/
│  │  ├─ RETROSPECTIVE.md
│  │  └─ structure-improvement-plan.md
│  ├─ contracts/                       # 项目特有，保持不变
│  ├─ experiments/                     # 项目特有，保持不变
│  ├─ market-game-sim-prd.md            # 原 docs/product/prd.md
│  ├─ market-game-sim-architecture.md   # 后续从稳定设计提炼；本批不强求
│  └─ SOP.md                           # 项目原则、开发纪律与状态转换入口
├─ src/
│  └─ market_game_sim/
├─ tests/
├─ tools/
│  ├─ README.md
│  ├─ spec_validation.py               # 共享规格校验实现
│  ├─ validate_contract_sources.py
│  ├─ validate_spec_lifecycle.py       # 薄 CLI，不重复 owner 判据
│  └─ verify.py                        # 本地统一验证入口
├─ CLAUDE.md
├─ README.md
└─ pyproject.toml
```

### 1.2 与 PersonaHub 一致及保留差异

| 层级 | 统一规则 | MarketGameSim 保留差异 |
|---|---|---|
| `docs/decisions/` | ADR 使用统一目录名和编号 | 决策内容围绕数值、事件与实验内核 |
| `docs/features/` | `README/TEMPLATE/releases/<version>` 骨架一致 | 版本根额外保留 `traceability.json` |
| Feature artifacts | 新 Feature 使用 `spec/design/tasks` | 0.1.1—0.1.3 作为 legacy 可暂缺 design |
| `docs/research/` | 研究资料集中 | 方法论和指标字典是实验判据 |
| 项目专属证据 | 允许在统一骨架外扩展 | `contracts/`、`experiments/`、`benchmarks/` 保留 |

目录结构一致的目标是降低跨项目切换成本，不是强迫两个领域拥有完全相同的 artifact。

## 2. Artifact 与真相源规则

### 2.1 版本根

`docs/features/0.1/` 表示一个可签收的大版本研究目标：

- `spec.md`：行为、研究边界、需求与成功指标的唯一真源；
- `design.md`：跨里程碑共享的技术设计，承接原 `plan.md`；
- `traceability.json`：requirement → milestone → exit 的机器追踪真源；
- `README.md`：只做入口和版本收口提示，不复制状态或需求正文。

版本根不再额外生成 `v0.1-stable/spec.md`。0.1 完成时直接把版本根规格状态改为
`done`，再由 release 文档记录不可变签收信息。

### 2.2 里程碑三件套

新里程碑采用：

```text
<milestone>/
├─ spec.md       # 做什么、怎样算完成
├─ design.md     # 怎么实现、边界与取舍
└─ tasks.md      # 按什么顺序实施
```

历史兼容规则：

- 0.1.1—0.1.3 已经进入或完成实现，不事后编造独立 design；它们继续引用版本根
  `design.md`，并使用 `gate_version: 0`；
- 0.1.4 尚未实现，迁移时根据已有 spec/tasks 和版本共享设计补一份正式 `design.md`，
  使用 `gate_version: 1`；
- 以后所有新里程碑必须三件套齐全，不得新建 `gate_version: 0`；
- legacy 以后可以在有真实证据时单向升级到 gate v1，但不得为追求目录整齐而补写
  无法证实的历史设计过程。

### 2.3 模板唯一真源

`docs/features/TEMPLATE/` 是供人和 agent 阅读、复制的模板唯一真源，与 PersonaHub
保持一致。2026-08-09 已从 PersonaHub 的已验证模板原样复制三份文件，并用 SHA-256
确认字节一致；M002-M004 已完成。

现有 `.specify/templates/` 现在是待退役旧模板，不再保留为兼容镜像，也不得用
`git mv` 或复制覆盖已经落地的通用 TEMPLATE。实施阶段只更新旧路径引用；确认没有
消费者后删除三份旧模板。随后按 §2.5 完成 constitution 原则分解并删除整个
`.specify/`。

本项目明确不依赖 spec-kit CLI 自动读取 `.specify/templates/`；如果未来重新引入该能力，
必须先修订本基线，不能在两个位置各维护一份模板。

#### 2.3.1 通用 `spec.md` 模板结构

本节与 PersonaHub 共用同一套模板契约。它不是某个 Feature 的历史快照，而是两个项目
后续新 Feature/里程碑的稳定写作与门禁输入。`spec.md` 固定使用以下 9 个顶层章节；
顶层标题不得省略或改号，只有章节内部子标题按领域选用：

```text
0. 来源与意图         # PRD/architecture/research/contracts/ADR 指针 + 一句话意图
1. 问题、目标与非目标 # 为什么做、成功改变什么、产品层明确不做什么
2. 用户场景           # US-xxx（Priority）+ 独立测试 + Given/When/Then 验收场景
3. 范围与边界         # 范围内 / 范围外 / 边界场景
4. 需求               # 项目定义的 requirement 类型子标题按需出现
5. 生命周期与不变量   # 状态机、实验流程、不变量；不适用时写明理由
6. 成功与验收         # SC/KPI/exit + AC；可追踪性内联，不再单列追踪表
7. 测试、依赖与决策   # 三个固定子标题；风险和已关闭权衡放“决策”
8. 待确认问题         # 固定保留；无开放项时明确写“无”
```

通用职责边界：

- 「1. 非目标」只记录产品/研究意图层的明确排除；「3. 范围外」记录本次交付切片的
  具体边界，两者不得复制同一段文字。
- 「5. 生命周期与不变量」和「8. 待确认问题」始终存在。前者不适用时写
  `不适用：<理由>`；后者无开放项时只写 `无`。固定标题让人和门禁使用同一解析边界。
- spec 待确认问题使用 `Q-xxx`，design 待确认设计问题使用 `DQ-xxx`：
  `- [ ] Q-001: <问题>` 表示开放，关闭后改为
  `- [x] Q-001: <问题> — 决策：<结论>`。禁止普通 bullet 或自由文本绕过门禁。
- 「7. 测试、依赖与决策」固定包含 `### 测试策略`、`### 依赖`、`### 决策与风险`。
  schema、module、class、function 等实现拆分仍属于 `design.md`。

第 4 节的 requirement ID 类型由项目领域决定，不强迫两个项目使用相同前缀。
MarketGameSim 继续使用现有 FR/KPI/SC、合同和 exit 语义，并由 `traceability.json` 保存
requirement → milestone → exit 的机器追踪；模板结构统一不改变该真相源。

`design.md` 同样是通用模板契约，固定以下 11 个顶层章节：

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

不适用的技术关注面保留标题并写 `不适用：<理由>`；第 10 节只接受规范的
`DQ-xxx` checkbox 或单独一行 `无`。design 描述结构、契约、状态、失败和技术取舍，
不写逐步编码任务。

`tasks.md` 固定以下 6 个顶层章节，Phase 只作为第 2 节的动态三级标题：

```text
0. 来源与执行规则
1. 前置条件
2. 实现任务
   ### Phase 1：<按 Feature/里程碑定义>
   ### Phase 2：<按 Feature/里程碑定义>
3. 验证与验收任务
4. 依赖与并行关系
5. 明确后移
```

任务统一为：

```markdown
- [ ] T001 [P] (`FR-001`, `AC-001`): <一个可验证动作> — verify: `tests/test_example.py`
```

`[P]` 只用于修改不同文件且没有顺序依赖的任务；机器门可以验证 `[P]` 任务没有显式
前置边，文件是否真的互不冲突仍由 review 判断。第 3 节覆盖自动化测试、真实实验验证
和最终质量门；第 5 节必须写明后移到哪个里程碑/版本，不能隐藏当前范围内未完成任务。

第 6 节每条 AC 必须有唯一 `AC-xxx`，并引用至少一个在第 4 节或
`traceability.json` 中真实定义、由当前里程碑负责的 requirement/contract/exit ID。
进入 `review` 前必须回填真实存在的仓库内测试路径，标记 `done` 前必须勾选：

```markdown
- [ ] **AC-001** (`FR-001`, `KPI-002`): 可观察行为 — tests: `tests/integration/test_example.py`
```

`draft`、`ready-for-development`、`in-progress` 阶段允许 `tests:` 暂缺，但 AC 的 ID、
需求引用和可观察行为必须已经存在。静态门禁只证明引用和证据文件一致，不宣称能证明
测试语义真实覆盖 AC；语义覆盖仍由 review 判断。

旧 0.1.1—0.1.3 使用 `gate_version: 0`，不做无收益的历史章节重排；0.1.4 及以后使用
`gate_version: 1`，在进入 `ready-for-development` 前必须同时对齐 spec/design/tasks
三份结构。

### 2.4 需求追踪真源

`traceability.json` 中的字段必须保持语义分离：

- requirement `statuses` 继续只表示 `owned/deferred/removed`；
- milestone 生命周期由各 milestone `spec.md` frontmatter 表示；
- release 生命周期由版本根 `spec.md` 和 `releases/<version>.md` 表示；
- 目录迁移只更新 `milestones` path；owner 的 milestone ID、scope 和 exit 不变。

退出条件编号只在单个里程碑内唯一。任何校验继续使用
`<milestone-id>/<exit-id>` 这一组合，不得把多个里程碑退出条件合并到一张只有 E1/E2 的
表中。

### 2.5 项目原则的拥有者

PersonaHub 没有独立 constitution 文件。它使用以下分工避免一份“最高原则”文档逐渐
混入产品、架构、流程和当前状态四种不同生命周期的内容：

| PersonaHub 文档 | 负责内容 | MarketGameSim 对应文档 |
|---|---|---|
| `personahub-prd.md` | 产品目标、范围、安全边界的唯一真相 | `market-game-sim-prd.md` |
| `personahub-architecture.md` | 全局模块边界、运行时约束和技术不变量 | `market-game-sim-architecture.md` |
| `docs/decisions/` | 已拍板且跨 Feature 生效的长期决策 | `docs/decisions/` |
| `docs/SOP.md` | 开发纪律、状态门、验证和复核流程 | `docs/SOP.md` |
| `CLAUDE.md` | 当前有效状态、短入口和必须自动加载的提醒 | `CLAUDE.md` |

现有 `.specify/memory/constitution.md` 的七条原则按内容迁移：

| 现有原则 | 正式拥有者 |
|---|---|
| 可追溯规格优先 | `docs/SOP.md` + `docs/features/README.md` |
| 撮合正确性不可妥协 | `docs/contracts/` + `market-game-sim-architecture.md`，SOP 只保留阻断规则 |
| 实验必须可复现 | `docs/research/methodology.md` + `docs/SOP.md` |
| 区分角色、能力与行为 | `docs/research/methodology.md` |
| 先验证市场，再解释策略 | `docs/research/methodology.md` + PRD |
| 安全与合规边界 | PRD；SOP 只保留实施禁止项 |
| 小步、确定性、可观察 | architecture + SOP |

迁移不是把 constitution 全文复制到五个位置，而是把每条原则的规范正文放入唯一拥有者，
其他文档只写短摘要和链接。`docs/SOP.md` 提供“项目不可违反原则”入口，但不重复 PRD、
methodology、contracts 或 architecture 的完整定义。迁移并通过链接检查后，删除
`.specify/memory/constitution.md` 和空的 `.specify/` 目录。

### 2.6 文档地图与所有权

新增 `docs/README.md` 作为两次点击内可到达全部权威文档的地图。它只记录“什么信息由谁
拥有”和入口链接，不复制状态、需求、合同或设计正文：

| 信息 | 唯一拥有者 |
|---|---|
| 产品目标、范围、安全边界 | `docs/market-game-sim-prd.md` |
| 全局模块边界与技术不变量 | `docs/market-game-sim-architecture.md` |
| 指标、研究方法与解释边界 | `docs/research/` |
| 跨 Feature 实现合同 | `docs/contracts/` |
| 长期架构决策 | `docs/decisions/` |
| Feature/里程碑行为与状态 | 对应 `spec.md` |
| Feature/里程碑实现方案 | 对应 `design.md` |
| requirement owner 与 exit | `traceability.json` |
| 开发纪律与质量门 | `docs/SOP.md` |
| 当前项目入口和强提醒 | `CLAUDE.md` |

README、CLAUDE 和版本 README 都只能作为派生入口。校验器需要阻止以下所有权漂移：

- design/tasks 自行声明另一份 status；
- README 或 CLAUDE 出现与 spec frontmatter 不同的当前状态；
- architecture 复制字段级合同，或 Feature design 重新定义全局不变量；
- release/RETROSPECTIVE 被当成当前产品或实现真相源。

MarketGameSim 当前 CLAUDE.md 规模尚可，不做为了缩短而缩短的机械迁移；实施后控制在
约 200 行以内，只保留当前有效规则、验证命令和权威文档指针。

## 3. 状态模型与 frontmatter

### 3.1 唯一状态真源

每个版本或里程碑的 `spec.md` frontmatter 是状态唯一机器真源。`design.md`、`tasks.md`、
README 和 CLAUDE.md 不再声明另一份独立 Status；它们只链接或展示由 spec 派生的索引。

里程碑示例：

```yaml
---
kind: milestone
id: 0.1.3
parent: v0.1-belief-testing-laboratory
version: "0.1"
status: in-progress
gate_version: 0
created: 2026-08-01
updated: 2026-08-09
prerequisites:
  - 0.1.2
---
```

版本根示例：

```yaml
---
kind: version-spec
id: v0.1-belief-testing-laboratory
version: "0.1"
status: in-progress
created: 2026-07-31
updated: 2026-08-09
---
```

### 3.2 状态机

统一采用与 PersonaHub 相同的状态：

```text
draft
  -> ready-for-development
  -> in-progress
  -> review
  -> done
```

状态与前置条件分开：

- `status` 表示 artifact/实现所处生命周期；
- `prerequisites` 表示调度依赖；
- 不再使用 `Ready after 0.1.3` 这类混合自由文本状态；
- 前置未达成时，文档仍可为 `ready-for-development`，但实施入口必须由门禁判定 blocked；
- 版本根只有在全部里程碑 `done` 且收口检查通过后才能变为 `done`。

### 3.3 迁移时的初始状态

根据当前仓库证据，迁移基线暂定：

| Artifact | 初始状态 | gate |
|---|---|---:|
| v0.1 版本根 | `in-progress` | 不适用 |
| 0.1.1 | `done` | 0 |
| 0.1.2 | `done` | 0 |
| 0.1.3 | `in-progress` | 0 |
| 0.1.4 | `ready-for-development` | 1 |

实施迁移前必须再次对照当时的任务与退出证据；如果项目进度已变化，以实施时证据为准，
不得机械套用本表。

## 4. 状态门与校验设计

### 4.1 Ready 审查门

进入 `ready-for-development` 前检查：

- [ ] spec 是否覆盖本里程碑负责的 FR/KPI/SC 等 requirement；
- [ ] prerequisite 是否为结构化 ID，且引用存在的里程碑；
- [ ] spec 的「8. 待确认问题」是否全部关闭并采用 `Q-xxx` 格式，或明确写 `无`；
- [ ] design 的待确认问题是否全部关闭，或已转为 tasks 中的验证任务；
- [ ] tasks 是否能追踪到合法 requirement、合同、ADR 或明确的 `N/A: <reason>`；
- [ ] traceability 中的 owner、scope、exit 是否与 spec 的退出条件一致。

机器门只验证可证明的结构和引用。TDD 是否真实经历“先红后绿”、设计判断是否合理等过程
事实由评审确认，不伪装成静态脚本能够证明。

### 4.2 共享校验实现

不再复制 `validate_contract_sources.py` 已有的 owner/path/exit 判据：

```text
tools/spec_validation.py
  纯函数：frontmatter、目录发现、状态、前置、owner、exit、链接边界

tools/validate_contract_sources.py
  现有真源与合同校验入口，复用 spec_validation

tools/validate_spec_lifecycle.py
  生命周期薄 CLI，复用 spec_validation

tools/verify.py
  本地公开入口：按顺序运行真源、生命周期、文档链接/所有权、pytest、ruff check/format
```

现有 `tests/unit/test_contract_sources.py` 已包含 23 个测试和多项负向变异，并非“没有
单测”。重构时保留这些测试，同时新增 `tests/unit/tools/test_spec_validation.py`。

### 4.3 生命周期校验范围

基础校验适用于所有版本和里程碑：

1. 路径、frontmatter ID、version 和 kind 一致；状态值合法；同类 ID 全仓唯一。
2. `spec.md` 是唯一状态真源；design/tasks 不允许声明独立 status。
3. prerequisite 引用存在且无循环；不能出现“按需”“视情况”等自由文本替代结构化 ID。
4. `traceability.json` 的 owner milestone 和 exit 存在；继续验证多 owner scope 不重叠。
5. Markdown 相对链接存在、留在仓库边界内且不是目录冒充文件。
6. `docs/README.md` 所有权索引引用存在；状态、字段级合同和全局不变量没有在错误层级
   形成第二份机器可读声明。

`gate_version: 1` 额外校验：

- 三件套齐全；
- spec/design/tasks 顶层结构与 §2.3.1 完全一致，固定章节不得缺失、改号或合并；
- design 不适用章节必须写理由；tasks Phase 只能位于第 2 节，任务格式必须合法，
  `[P]` 任务不得同时声明显式前置依赖；
- 每条 AC 引用的 requirement/contract/exit ID 必须存在且归当前里程碑负责；
- `ready-for-development` 及以上不允许 spec/design 留有未关闭问题；待确认章节只接受
  规范 Q/DQ checkbox 或单独一行 `无`，自由文本、空章节和缺章节均失败；
- `review` / `done` 时每条 AC 至少引用一个存在的仓库内测试文件；
- `done` 时 tasks、AC 与退出条件非空且全部完成；`review` 可以合法地全部勾选，
  校验器不得从 checkbox 反向推断状态；
- 已完成任务不得仍包含 `TODO/TBD/待补/未补/pending`；
- requirement/合同/测试引用必须是可解析的仓库内路径或 ID。

`gate_version: 0` 只用于已确认的 legacy 里程碑，只执行元数据、状态唯一性、路径、链接和
现有 traceability 校验。新建或回退到 v0 必须失败。

### 4.4 测试要求

每条新增校验规则必须有正向和负向变异测试，至少覆盖：

- 合法的 version root、gate v0 与 gate v1 milestone；
- 缺 artifact、非法状态、重复 ID、无效 prerequisite 和依赖环；
- spec/design/tasks 固定章节缺失/改号/合并，Q/DQ 开放、自由文本、空章节与合法 `无`；
- design 不适用章节缺理由，tasks Phase 层级/任务格式错误，`[P]` 仍有显式前置依赖；
- draft/ready 暂无测试路径合法，review/done 缺失或越界测试路径失败，review 全勾合法；
- owner/exit 不存在、多 owner scope 冲突、局部 E 编号组合校验；
- 绝对路径、`..` 逃逸、目录、glob、坏链接和 CRLF 文档；
- 文档所有权索引缺失、坏入口、重复 status 和跨层级真相源；
- 多版本、多里程碑同时存在的批量场景。

## 5. 版本收口规则

某版本全部里程碑 `done` 后执行逻辑收口：

1. 新建 `docs/features/releases/<version>.md`，记录里程碑列表、需求摘要、实验配置、
   证据索引、已知限制、commit 和校验结果。
2. 保留 `docs/features/<version>/` 原路径；新增或更新版本 README，标记已收口且仅允许
   修复历史错误、证据缺失或死链。
3. 版本根 `spec.md` 原地转为 `done`，不复制 stable spec，不改 requirement owner。
4. release 写入 `closed_at` 前必须验证全部里程碑状态、traceability、合同真源、链接和
   测试门禁。
5. Git tag 固定实际交付快照；release 文档提供人类入口，Git 保存不可变历史。

T607 或后续校验器通过只表示 ID、路径和声明关系自洽，不代表机器理解并证明了规格语义。
收口仍需人工核对需求措辞、实验结论与已知限制。

## 6. 路径迁移清单

正式实施时，仍需保留历史的路径迁移使用 `git mv`；已经复制完成的通用 TEMPLATE
按“退役旧来源”处理，不再覆盖目标文件：

| 当前路径 | 目标路径 |
|---|---|
| `specs/v0.1-belief-testing-laboratory/` | `docs/features/0.1/` |
| `specs/v0.1-belief-testing-laboratory/plan.md` | `docs/features/0.1/design.md` |
| `.specify/templates/spec-template.md` | 删除：已由 `docs/features/TEMPLATE/spec.md` 取代 |
| `.specify/templates/plan-template.md` | 删除：已由 `docs/features/TEMPLATE/design.md` 取代 |
| `.specify/templates/tasks-template.md` | 删除：已由 `docs/features/TEMPLATE/tasks.md` 取代 |
| `.specify/memory/constitution.md` | 按 §2.5 分解到 PRD/architecture/SOP/features README |
| `docs/adr/` | `docs/decisions/` |
| `docs/product/prd.md` | `docs/market-game-sim-prd.md` |
| `docs/product/methodology.md` | `docs/research/methodology.md` |
| `docs/product/metrics-dictionary.md` | `docs/research/metrics-dictionary.md` |
| `structure-improvement-plan.md` | `docs/reviews/structure-improvement-plan.md` |
| `code-review-report.md` | 若仍开放则转 `docs/reviews/CURRENT-code.md`；已闭环则按 review 协议删除 |

迁移必须同步更新：

- README、CLAUDE、规格、合同、ADR、实验索引和检视报告中的路径；
- `traceability.json.milestones` 的 path；
- `validate_contract_sources.py` 的 TRACE/SPEC 常量及相关测试 fixture；
- 子 spec 的 `../plan.md` 引用，以及所有会变成 `docs/docs/...` 的相对链接；
- README、工具说明或 agent 指令中对 `.specify/`、constitution 和旧模板路径的引用。

上表完成且所有目标文档通过复核后，删除已经为空的 `.specify/`。constitution 采用内容
分解迁移，不把同一份原文机械复制到多个目标文件。

迁移完成前后都要运行全仓路径搜索。不能只以 T607 通过作为链接正确性的证明。

## 7. 分阶段实施计划

### 阶段 A：文档骨架、模板与项目原则（约 2—3 小时）

1. 建立 `docs/features/README.md`、`releases/`、`docs/research/`；`TEMPLATE/` 三份文件
   已由 M002-M004 提前落地，不重复生成。
2. 对照通用 TEMPLATE 更新规则与链接，确认 `.specify/templates/` 没有仍需保留的
   项目专属内容；不得覆盖通用模板。
3. 按 §2.5 把 constitution 原则迁入各自拥有者，建立 `docs/SOP.md` 原则与流程入口。
4. 按 §2.3.1 已定稿结构验证 frontmatter grammar，确认全仓不再引用旧模板；不得在
   实施阶段重新发明另一套三件套顶层章节。

### 阶段 B：原子路径迁移（约 2—3 小时）

1. 按第 6 节执行 `git mv`。
2. 一次性更新路径、相对链接、traceability 和校验器常量。
3. 跑 Markdown 链接检查与现有 T607，确认没有悬空引用。

### 阶段 C：生命周期门禁（约 3—4 小时）

1. 迁移结构化 frontmatter，移除 design/tasks 的重复状态。
2. 抽取 `spec_validation.py`，增加生命周期薄 CLI。
3. 增加链接、文档所有权校验与统一 `verify.py` 入口。
4. 保留现有 23 个真源校验测试并补齐生命周期变异测试。

### 阶段 D：项目入口收口（约 1—2 小时）

1. 新增 `docs/README.md` 所有权地图，更新根 README、CLAUDE 并新增 SOP。
2. 补 `tools/README.md`。
3. 为 0.1.4 补正式 design；不补写 0.1.1—0.1.3 的虚构历史 design。
4. 处置根 `code-review-report.md`，确保根目录只保留入口和构建配置。

总工作量预计 **8—12 小时**，建议拆成 3—4 个可独立验证的提交；不与 0.1.3/0.1.4
业务实现混在同一提交。

## 8. 验证与提交要求

本地与自动化文档中的公开验证入口统一为：

```text
python tools/verify.py
```

`verify.py` 按固定顺序运行真源校验、生命周期/链接/所有权校验、pytest、ruff check 和
ruff format check；失败即返回非零。各底层命令仍可单独用于定位，但 README、SOP 和
CLAUDE 不再各自维护不同的完整命令清单。

路径迁移提交额外运行 Markdown 链接检查；阶段 B 完成时确认旧模板路径引用已经消失；
constitution 完成职责分解后再确认整个 `.specify/` 已删除。

推送后按 CLAUDE.md 的既有约定确认所有 CI job 全绿。生命周期校验优先接入现有
`contract-sources` 前置 job，避免仅为了展示拆出重复 job；如果最终决定新增 job，必须
同步更新 CLAUDE.md 中的 job 数量与名称。

## 9. 明确不做

- 不引入 OpenSpec/spec-kit 的额外 CLI 运行时依赖；
- 不创建 `v0.1-stable` 或复制完整规格真源；
- 不把已交付里程碑移动到 archive；
- 不重写 requirement owner，不把 `archived` 混入 requirement statuses；
- 不把 `contracts/`、`experiments/` 或 `benchmarks/` 强塞进 PersonaHub 不存在的目录；
- 不为已实现里程碑事后虚构 design；
- 不新建 `docs/constitution.md`，不把旧 constitution 全文复制到多个文档；
- 不在本次方案定稿中执行任何正式迁移。

## 10. 已关闭的方案风险

| 风险 | 基线处置 |
|---|---|
| 自由文本状态无法稳定解析 | 使用结构化 frontmatter，说明文字留在正文 |
| Ready 与前置条件混在一个字符串 | status 与 prerequisites 分离 |
| TEMPLATE 与 `.specify/templates` 漂移 | 将旧模板迁入 docs 后删除旧目录，只保留一个真源 |
| constitution 混合多种生命周期内容 | 按 PRD/architecture/decisions/SOP/CLAUDE 职责分解后删除 `.specify/` |
| 新旧文档被同一门禁立即拉红 | 明确 gate v0/v1，禁止新建 v0 |
| owner/path 校验重复实现 | 抽取共享 `spec_validation.py` |
| 物理归档破坏链接和追踪 | 保留版本稳定路径，使用 releases 逻辑收口 |
| stable 副本制造第二真源 | 版本根 spec 原地转 done，Git tag 固定快照 |
| T607 只比 ID、不理解语义 | 明确机器门边界，收口保留人工语义复核 |
| 归档规则可能被遗忘 | 版本 done 与 release/closed_at 建立机器门禁 |
| 校验只看 milestone、忽略跨文件漂移 | 校验 version/spec/design/tasks/index 的一致性 |
| 路径迁移产生普通 Markdown 死链 | 增加仓库边界内的链接检查与迁移前后扫描 |
| 方案误称 T607 无单测 | 正文改为保留现有 23 个测试并在其上扩展 |
| 文档职责存在但入口分散 | 新增 docs/README 所有权地图并机器检查越权声明 |
| 本地、SOP 与 CI 门禁可能漂移 | `python tools/verify.py` 作为唯一公开入口 |

## 11. 基线变更规则

本文件是后续实施的范围基线。实施中若要改变以下任一项，必须先修订方案并说明理由：

- `docs/features/` 目标骨架；
- 保留历史里程碑路径、不做物理 archive；
- `traceability.json` owner 语义；
- `docs/features/TEMPLATE` 的唯一真源地位；
- §2.3.1 的 spec/design/tasks 固定顶层结构、Q/DQ 语法和分阶段测试证据规则；
- 项目原则按 §2.5 分工拥有、最终删除 `.specify/` 的决定；
- legacy gate v0 与新里程碑 gate v1 的边界；
- 0.1.1—0.1.3 不补写历史 design 的决定。

其他实现细节可以在不改变这些边界的前提下小步调整。

## 12. “10 分结构”验收标准

| 维度 | 通过条件 |
|---|---|
| 可发现性 | 从 `docs/README.md` 最多两次点击到达任一权威文档 |
| 单一真源 | 状态、需求、owner、合同、架构、指标各有且只有一个机器可读拥有者 |
| 可执行性 | 每条结构性规则有自动校验，过程性规则有明确人工审查门 |
| 生命周期 | milestone 从 draft 到 done、版本从 active 到 release 均有机器检查的进入与退出 |
| 仓库卫生 | 根目录无过期 review、运行日志、数据库、缓存或重复模板 |

五项全部满足、本地 `python tools/verify.py` 全绿且推送后 CI 四个 job 全绿，才视为本次
目录结构改造完成。目录“看起来一致”但缺少所有权或自动门禁，不算完成。

## 13. 实施任务清单

本节是目录结构改造的执行进度真相源。开始一项时保留 `[ ]` 并在末尾标记
`（进行中）`；完成且验证后立即改为 `[x]`，不得最后统一补勾。任一时刻只允许一个
非 `[P]` 任务处于进行中。进度直接按已勾选数量计算，不另维护百分比。

### Phase A：文档骨架、模板与项目原则

- [x] M001：建立 `docs/features/`、`TEMPLATE/`、`releases/`、`docs/research/` 和
  `docs/reviews/` 目标骨架。
- [x] M002 [P]：按 §2.3.1 定稿结构落地 `docs/features/TEMPLATE/spec.md`。
- [x] M003 [P]：按 §2.3.1 定稿结构落地 `docs/features/TEMPLATE/design.md`。
- [x] M004 [P]：按 §2.3.1 定稿结构落地 `docs/features/TEMPLATE/tasks.md`。
- [x] M005：编写 `docs/features/README.md`，固化三件套职责、状态门、Q/DQ 和版本收口。
- [x] M006：按 §2.5 把 constitution 原则分别迁入 PRD、architecture、decisions、SOP
  和 CLAUDE 的唯一拥有者。
- [x] M007：验证原则没有被全文复制到多个目标，所有短摘要都链接到唯一拥有者。

### Phase B：原子路径迁移

- [x] M008：迁移前记录工作树状态并全仓扫描旧 specs、`.specify/`、ADR、product 路径。
- [x] M009：用 `git mv` 把 `specs/v0.1-belief-testing-laboratory/` 迁到
  `docs/features/0.1/`。
- [x] M010：把版本根 `plan.md` 改名为 `design.md`，保持 0.1.1—0.1.3 legacy 层级不变。
- [x] M011 [P]：迁移 `docs/adr/`、PRD、methodology 和 metrics dictionary 到目标路径。
- [x] M012：更新 `traceability.json.milestones` path，保持 owner、scope、exit 语义不变。
- [x] M013：更新 README、CLAUDE、spec、contract、ADR、实验索引、工具常量和测试 fixture
  中的全部旧路径及相对链接。
- [x] M014：运行迁移后全仓搜索与 Markdown 链接检查，确认无旧模板/constitution 引用
  后删除空的 `.specify/`。

### Phase C：状态元数据、共享校验与测试

- [x] M015：迁移 version/milestone spec frontmatter，写入 canonical status、prerequisites
  与 gate_version，移除 design/tasks 的重复 Status。
- [x] M016：为 0.1.4 补正式 design 并对齐三份新模板；不补写 0.1.1—0.1.3 的历史 design。
- [x] M017：抽取 `tools/spec_validation.py`，复用现有 owner/path/exit 判据。
- [x] M018 [P]：实现 `validate_spec_lifecycle.py` 薄 CLI 和链接/文档所有权校验。
- [x] M019：保留现有 23 个真源测试，并补 gate v0/v1、三件套结构、Q/DQ、AC/tests、
  prerequisite、owner/exit 和批量场景测试。
- [x] M020：实现 `tools/verify.py`，统一运行真源、生命周期、链接、所有权、pytest 和 ruff。
- [x] M021：更新 SOP、CLAUDE、README 与工具说明，公开验证入口统一为
  `python tools/verify.py`。

### Phase D：入口与版本逻辑收口

- [x] M022：新增 `docs/README.md` 所有权地图，验证两次点击内可到达全部权威文档。
- [x] M023：更新根 README、CLAUDE 和 `tools/README.md`，删除重复状态与完整命令清单。
- [x] M024：新增 `docs/features/0.1/README.md`，保留稳定路径并说明 legacy design 规则。
- [ ] M025：仅在全部里程碑 done 后生成 `docs/features/releases/0.1.md`、写入
  `closed_at`；条件未满足时保持未勾。
- [x] M026：把本方案迁入 `docs/reviews/`，按 review 协议处置根 `code-review-report.md`。

### Phase E：工具版本、CI 与最终验收

- [x] M027：为 pytest、ruff 等开发工具锁定有上界的版本范围，并用该版本本地验证。
- [x] M028：更新 CI 使用 `python tools/verify.py`，保持真源、ruff、pytest 3.11/3.13
  四个必需 job 的职责清楚且无重复执行。
- [ ] M029：运行 `python tools/verify.py`，逐项核对第 12 节五项验收标准并记录结果。
- [ ] M030：提交并推送，使用 `gh run watch <run-id> --exit-status` 确认当前 HEAD 的全部
  必需 CI job 全绿。
