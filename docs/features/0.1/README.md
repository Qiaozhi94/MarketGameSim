# v0.1：Belief Testing Laboratory

本目录是 v0.1 版本根的稳定路径与入口。**状态唯一真源是 [`spec.md`](spec.md) 的
frontmatter**；本文只做入口与收口提示，不复制状态或需求正文。

## 结构

```text
0.1/
├─ README.md           # 本文：入口与 legacy design 规则
├─ spec.md             # 版本级研究规格（状态唯一真源）
├─ design.md           # 跨里程碑共享技术设计（承接原 plan.md）
├─ traceability.json   # requirement → milestone → exit 机器追踪真源
└─ 0.1.x-*/            # 里程碑
   ├─ spec.md
   ├─ design.md        # gate v1（0.1.4）起必选
   └─ tasks.md
```

## 里程碑

| 里程碑 | 状态（见各 spec frontmatter） | gate |
|---|---|---|
| [`0.1.1-minimal-kernel/`](0.1.1-minimal-kernel/spec.md) | done | 0 |
| [`0.1.2-leverage-and-first-experiment/`](0.1.2-leverage-and-first-experiment/spec.md) | done | 0 |
| [`0.1.3-robustness/`](0.1.3-robustness/spec.md) | in-progress | 0 |
| [`0.1.4-replay-and-report/`](0.1.4-replay-and-report/spec.md) | ready-for-development | 1 |

## Legacy design 规则

0.1.1—0.1.3 属于 **gate v0**：已经实现，不事后补写独立 `design.md`，它们继续引用版本
根 [`design.md`](design.md)，并使用 `gate_version: 0`。0.1.4 及以后（gate v1）必须
三件套齐全。

## 收口提示

**完整 v0.1 签收 = 0.1.1—0.1.4 全部退出条件通过**，且版本根 `spec.md` 状态转为
`done`。收口时在 [`docs/features/releases/`](../releases/) 下新增 `0.1.md` 记录不可变
签收信息；本目录路径保持不变，不做物理 archive。

## 相关入口

- `docs/features/README.md`：三件套与版本收口规则。
- `docs/README.md`：全仓文档所有权地图。
- `docs/market-game-sim-prd.md`：产品目标与安全边界。
