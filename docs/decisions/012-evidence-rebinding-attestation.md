# ADR-012：证据索引重绑必须显式盖章（attestation），不再静默改哈希

日期：2026-09-20  
状态：Accepted（owner 裁决，2026-09-20 方向变更后全量文档检视）  
关联规格：[`../features/0.1/0.1.5-goal-driven-flagship/spec.md`](../features/0.1/0.1.5-goal-driven-flagship/spec.md)  
关联决策：[`ADR-005`](005-evidence-binding-stays-full-tree.md)（绑定维持全树哈希）  
关联文档：[`../experiments/0.1.5-evidence-index.json`](../experiments/0.1.5-evidence-index.json)、
[`../../src/market_game_sim/showcase/evidence_index.py`](../../src/market_game_sim/showcase/evidence_index.py)

## 背景

[ADR-005](005-evidence-binding-stays-full-tree.md) 决定证据索引继续绑定**全树**源码哈希，
理由是「零判断」：全树哈希从不断言少于现实。守卫的报错原文是
`rerun T215 after source changes`——代码变了就重跑，没有例外条款。

实践没有按这条走。自 v0.1 于 2026-08-30 签收以来，`0.1.5-evidence-index.json` 的
`code.source_tree_sha256` 被改过 29 次，其中 **19 次的提交只改了这一行**
（`git log --numstat -- docs/experiments/0.1.5-evidence-index.json` 可逐条核验，
`1 1` 即为纯重绑），其余几次是整体重建；**没有任何一次提交声明重跑过 T215**
（128 block × 16 次运行）。改动内容多为 Web 终端、K 线、live 市场等与 T215 运行路径
无关的呈现层代码。

也就是说：机制上是 ADR-005 想要的「代码变了就重跑」，实践上是 ADR-005 在备选方案里
**明确拒绝**的方案 B——「不重跑就重盖章」，而且盖章这件事在仓库里没有任何痕迹：
索引看起来仍然像是由当前源码树产出的证据。这是本项目历史上最典型的门禁旁路面：
规则写着，机器不执行，实践悄悄走另一条路。

方向变更会让情况更糟：v0.4 将新增大量 `agent/strategy_layer/`、`experiment/perturbation/`
下与 0.1.5 证据路径无关的文件，重绑只会更频繁。

## 决策

**采用「最低成本 + 留痕」方案：索引新增 `attestation` 块，并由门禁强制它与哈希同步。**

1. `0.1.5-evidence-index.json` 新增顶层 `attestation`，记录这次绑定是**实跑**还是
   **重盖章**，以及证据真正产出时的源码树：

   | 字段 | 含义 |
   |---|---|
   | `rerun` | `true` = 本次绑定伴随真实 T215 重跑；`false` = 仅重盖章 |
   | `attested_source_tree_sha256` | 本次盖章针对的源码树，**必须等于** `code.source_tree_sha256` |
   | `t215_source_tree_sha256` | T215 实跑时的源码树（证据真正的产出环境） |
   | `t215_bound_at` | T215 实跑绑定日期 |
   | `rebound_at` | 本次重盖章日期；`rerun: true` 时为 `null` |
   | `reason` | 重盖章理由（为什么认为改动与 T215 运行路径无关） |

2. **门禁**（`showcase/evidence_index.py::validate_evidence_index`）：
   - `attested_source_tree_sha256 != code.source_tree_sha256` → 拒绝。
     这条是本 ADR 的执行力所在：**改哈希不改盖章就红**，重绑再也无法悄悄发生；
   - `rerun: false` 时，`t215_source_tree_sha256` 必须与当前哈希**不同**
     （否则应声明 `rerun: true`），`rebound_at >= t215_bound_at`，`reason` 非空；
   - `rerun: true` 时，两个哈希必须相同，`rebound_at` 必须为 `null`。
3. **`rerun: false` 不等于证据被重新建立。** 盖章只记录「谁在什么时候、以什么理由把
   索引重绑到新源码树」，它**不提升**证明力：证据仍然只由 `t215_source_tree_sha256`
   那棵树产出。R5 交付报告在 `rerun: false` 时必须把这一事实打印在「版本签收」小节，
   不允许只显示当前哈希。
4. **ADR-005 的全树哈希与其观察项（方案 A）维持不变**，本 ADR 不收窄哈希范围，
   也不打开那三条触发条件；两者正交：ADR-005 管「绑定什么」，本 ADR 管「重绑时留什么痕」。

## 备选方案

- **(a) 每次真重跑**：证明力零折损，但 128 block × 16 次运行的机器时间要为每一次
  呈现层改动重付一遍——ADR-005 已经把它记录为「修复的经济抑制」来源，实践也已用
  19 次纯重绑投票否决了它。
- **(b) 兑现 ADR-005 方案 A（import 闭包收窄哈希范围 + 守卫测试 + `hash_scheme` 字段）**：
  最彻底，其第 1 条触发条件（真实出现「可证明不影响运行结果的变更被迫全量重跑」的案例）
  确实已被兑现。不采纳的理由是 ADR-005 自己写下的：范围/分类型门禁是本仓库历史上最易
  出洞的门禁类别，误分类会**静默**削弱证明力；而本 ADR 要解决的恰恰是「静默」。
  该方案继续作为观察项挂起。
- **(c) 本决策**：不改变证明力、不新增分类维护负担，只把已经在发生的事情变成显式、
  可审计、机器强制的动作。代价是承认「不重跑就重盖章」这一实践存在——但它本来就存在，
  ADR 只是让它不再隐身。

## 后果

- 正面：重绑从「一行静默改动」变成「必须同时更新盖章、写明理由、且被门禁校验」；
  证据真正的产出环境（`t215_source_tree_sha256`）第一次被写进索引本身，不再只存在于
  git 历史里；R5 报告对读者如实披露。
- 负面：索引多了一个必须维护的块；忘记更新盖章会让门禁变红——这是有意的代价。
- 后续行动：
  - 每次重绑必须在同一提交内更新 `attestation`（`rebound_at` + `reason`）；
  - 若将来真的重跑 T215，把 `rerun` 置 `true`、两个哈希置同一值、`rebound_at` 置 `null`；
  - ADR-005 的方案 A 仍为观察项；若其余两条触发条件（重跑成本已实际改变修复行为、
    分类边界可机械化维护）也成立，再单独立 ADR 决定是否收窄哈希范围。
