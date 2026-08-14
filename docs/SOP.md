# SOP —— 项目不可违反原则、开发纪律与状态门

本文是 MarketGameSim 的**原则入口与质量门**唯一真源：它汇总「项目不可违反原则」的
短摘要与各自唯一拥有者链接，规定开发纪律、验证流程、状态转换与复核协议。

> 分工原则：**每条原则的规范正文只放一个唯一拥有者**，本文只写短摘要与链接，不重复
> PRD、methodology、contracts、architecture 的完整定义（本仓库此前有独立
> `constitution.md`，已按职责分解，详见「原则拥有者」表）。

## 0. 项目不可违反原则（入口）

以下原则是**阻断性**的：违反其中任何一条的规格/实现不得进入实现或收口阶段。规范
正文在各自的唯一拥有者中，本文只给摘要与入口。

| # | 原则 | 短摘要 | 规范正文唯一拥有者 |
|---|---|---|---|
| 1 | 可追溯规格优先 | 功能必须先有已评审规格；实现/测试/实验/结论必须引用需求编号；未写入规格的行为不视为承诺 | `docs/SOP.md` 本节 + `docs/features/README.md` |
| 2 | 撮合正确性不可妥协 | 订单生命周期、价格时间优先、守恒、费用与交易约束必须通过确定性测试；影响账本或价格形成的缺陷是阻断问题 | `docs/contracts/` + `docs/market-game-sim-architecture.md`（本文只保留阻断规则） |
| 3 | 实验必须可复现 | 每次实验保存配置、种子、代码版本、运行时间与指标定义；配对种子比较；单次运行不作一般性结论 | `docs/research/methodology.md` + 本节 §2 |
| 4 | 区分角色、能力与行为 | 做市商/大资金/知情/操纵必须建模为不同角色；资金、信息、延迟、市场影响是显式能力，不得用隐藏假设代替机制 | `docs/research/methodology.md` |
| 5 | 先验证市场，再解释策略 | 解释代理盈亏前，基准市场须通过预先声明的统计与微观结构检查；结论写成「在这些假设与参数下」 | `docs/research/methodology.md` + `docs/market-game-sim-prd.md` |
| 6 | 安全与合规边界 | 操纵只用于封闭仿真/检测/监管压力测试；不连接真实账户，不把实验输出包装成操纵操作指南 | `docs/market-game-sim-prd.md`（本文只保留实施禁止项 §4） |
| 7 | 小步、确定性、可观察 | 优先单品种、规则代理、最小订单类型；所有状态变化可记录、可回放、可解释；RL/LLM/多市场经独立规格引入 | `docs/market-game-sim-architecture.md` + 本节 §2 |

本表是「项目不可违反原则」的**唯一入口**，其他文档只写对应条目摘要并链接回本表或
各拥有者，不得全文复制。

## 1. 开发纪律

- **提交前本地全绿**：`python tools/verify.py`（唯一公开入口）运行真源校验、生命周期/
  链接/所有权校验、pytest、ruff check、ruff format check，失败即返回非零。
- **推送后确认 CI**：`git push` 后用 `gh run watch <run-id> --exit-status` 确认当前
  HEAD 的全部必需 CI job 全绿（真源自校验、ruff、pytest 3.11、pytest 3.13）。
- **每次修复补回归测试**：同一提交内为修复的行为补正反两面的仓库内测试；已知但暂不
  修复的缺口用 `pytest.mark.xfail(strict=True)` 标记并写明原因。
- **安全校验降级必须声明**：若「失败即拒绝」改为「仅警告/仅记录」，必须在提交信息或
  代码注释中显式说明原因。
- **开发工具锁定版本上界**：`dev` 分组内每个工具必须有上界（如 `ruff>=0.16,<0.17`），
  工具升级必须是一次显式、本地验证过的改动。

## 2. 实验可复现与确定性（原则 3、7 的阻断规则）

- 实验保存配置、随机种子、代码版本、运行时间与指标定义；比较策略使用相同外生路径
  与配对随机种子。
- 单次运行不得作为一般性结论；样本量 1、不可复现、有学习效应的运行（`interactive`
  模式）不进任何统计。
- 所有状态变化必须可记录、可回放、可解释；确定性定义含「相同代码 + 配置 + 种子 +
  输入序列」。

## 3. 状态门

- **状态唯一真源**是各版本/里程碑 `spec.md` 的 frontmatter `status`；`design.md`、
  `tasks.md`、README、CLAUDE 不得声明第二份独立状态。
- `research_claim_status` 与工程 `status` 正交，只表示研究声明是否建立，不得被解释为
  第二份工程状态；合法值与证据门槛见 `docs/features/README.md`。
- 状态机：`draft → ready-for-development → in-progress → review → done`。
- 前置条件用结构化 `prerequisites` ID，前置未达成时实施入口由门禁判定 blocked。
- 进入 `ready-for-development` 前：spec 覆盖负责的 requirement；前置为存在且无循环的
  ID；spec/design 待确认问题全部关闭；tasks 可追踪到合法引用；traceability owner/
  scope/exit 与 spec 一致。
- `done` 时：tasks、AC 与退出条件非空且全部完成，每条 AC 引用存在的仓库内测试路径；
  不因 checkbox 反向推断状态。
- legacy gate v0 的历史未完成任务只允许通过显式、逐项且机器可验的迁移映射保留，不能
  事后伪勾；gate v1 不设例外。

## 4. 实施禁止项（原则 6 的阻断规则）

- 不连接券商、交易所、钱包或真实资金。
- 不预测真实证券/加密资产未来价格，不生成交易信号，不提供投资建议。
- 不把仿真结论外推至真实市场；输出是条件性命题与机制理解。
- 操纵行为只用于封闭仿真、检测与监管压力测试。

## 5. 验证与复核流程

- 唯一公开验证入口：`python tools/verify.py`，按固定顺序运行真源校验、生命周期/
  链接/所有权校验、pytest、ruff check、ruff format check。
- 目录结构改造等路径迁移提交额外运行 Markdown 链接检查，迁移前后全仓扫描。
- 复核（review）检查：规格完整性、测试证据、复现信息、研究边界；机器门只证明引用与
  结构自洽，语义覆盖由人工复核判断。

## 6. 相关入口

- `docs/README.md`：全仓文档所有权地图。
- `docs/features/README.md`：Feature/里程碑生命周期与模板规则。
- `docs/market-game-sim-prd.md`、`docs/market-game-sim-architecture.md`、
  `docs/research/methodology.md`、`docs/contracts/`、`docs/decisions/`：各原则规范正文。
- `CLAUDE.md`：当前有效状态与必须自动加载的提醒。
