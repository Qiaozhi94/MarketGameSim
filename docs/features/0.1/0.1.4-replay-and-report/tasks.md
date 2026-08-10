---
kind: milestone
id: 0.1.4
parent: v0.1-belief-testing-laboratory
version: "0.1"
related_features: []
topics: [replay, report]
doc_kind: tasks
gate_version: 1
created: 2026-08-01
updated: 2026-08-09
prerequisites:
  - 0.1.3
---

# 0.1.4：回放与报告 - 任务

> Spec: `spec.md` | Design: `design.md`

## 0. 来源与执行规则

- 行为与验收真相源：`spec.md`（FR-019/FR-020/SC-008，退出条件 E1—E5）。
- 技术方案与边界：`design.md`。
- 每个任务标注 `[合同引用]`，实现前先读对应章节，实现后以合同为裁判。
- 带 `[TDD]` 的任务先写失败测试；同一 Phase 内可并行项标 `[P]`。
- **任务编号只在本文件内唯一**；引用其他里程碑任务时必须带里程碑前缀
  （写 `0.1.1 T603`，不写 `T603`）。
- 完成且验证后立即把 `[ ]` 改为 `[x]`。

## 1. 前置条件

- [ ] T001 (`DQ-001`): 关闭所有阻塞性 spec/design 问题 — verify: `spec.md`、`design.md`
- [ ] T002 (`0.1.3`): 验证 0.1.3 退出证据与上游 artifact 可用 — verify: `0.1.3` 实验产物

## 2. 实现任务

### Phase 1：日志读取与状态重建

- [ ] T101 (`FR-019`, `事件 Schema §6`): 独立日志读取器——解析 `RUN_HEADER + EVENT* +
      RUN_TRAILER` 三种顶层记录，**不导入 `kernel/`**；拒绝 TI-4/TI-5 日志（§1.5）—
      verify: `tests/unit/replay/test_log_reader.py`
- [ ] T102 (`FR-019`, `0.1.1 T603`): 复用并扩展独立验证器的状态重建，账户与**订单簿**
      两类终态；0.1.1 已实现部分不重写，只增加逐帧快照能力 — verify:
      `tests/unit/replay/test_state_rebuild.py`
- [ ] T103 (`事件 Schema §4.6.3`): **逐帧状态序列**——第 0 帧由 `transaction_seq=1`
      （ACCOUNT）与 `2`（BOOK）两条初态快照构成，第 k 帧为 `transaction_seq=k+2` 提交后
      的完整状态；帧边界取事务边界。这是 E1 的输入 — verify:
      `tests/unit/replay/test_frame_sequence.py`

### Phase 2：单文件回放器

- [ ] T201 (`spec §3.1`): 单文件 HTML 产物，数据内联，**无 `fetch`、无 CDN、无外部
      字体**；构建后用断网环境打开验收（E2）— verify: `tests/integration/test_replay_offline_single_file.py`
- [ ] T202 (`FR-019`, `AC-006`): 逐帧呈现价格曲线、订单簿深度、账户权益与仓位、强平
      事件标注；时间轴以 `timestamp` 为准，可按事务或逻辑时间步进；实现拖拽定位到
      任意帧、变速播放与暂停三种交互控制 — verify:
      `tests/unit/replay/test_frame_presentation.py`
- [ ] T203 (`FR-020`, `指标字典 §1.9`): K 线视图，周期取指标字典定义，**只画已完成的
      K 线** — verify: `tests/unit/replay/test_kline.py`
- [ ] T204 (`spec §3.3`): 降采样——允许，但比例与规则必须在页面上可见；降采样产物
      不得用于 E1 验收 — verify: `tests/unit/replay/test_downsampling.py`

### Phase 3：总结报告

- [ ] T301 (`PR-019`): 报告生成，两组内容缺一不可：① 指标汇总、PnL 桥接、经济终点
      发生率、技术无效率与排除率（`metrics/`）；② 条件性结论、效应量、置信区间与失效
      边界（`analysis/` + `conclusion/`）。第 ② 组是 PR-019 核心 — verify:
      `tests/integration/test_report_artifacts.py`
- [ ] T302 (`spec §4.1`, `E4`): **artifact manifest 与不重算断言**——manifest 按七项封闭
      清单逐 artifact 声明，加载 `report_artifacts.json` 校验 producer/format/版本/字段，
      不得复制 Schema；断言 ① 改任一上游产物报告随之变化；② 报告层不执行任何统计检验
      或重新聚合。五类负向夹具：必备件缺失 / 哈希不符 / schema_version 错版 / 必备字段
      缺失或类型错误 / 出现未声明额外件——五种都必须使报告生成失败 — verify:
      `tests/unit/report/test_manifest.py`

## 3. 验证与验收任务

- [ ] T401 (`SC-008`, `KPI-012`): **逐帧一致性**（E1）——在未降采样日志上，断言回放
      重建的每一帧与 oracle 逐字段相等；oracle 是测试专用独立 observer，每事务提交后
      直接从内核对象读快照，**绝不喂给回放器**；先断言帧数与帧键集合相等再逐帧比字段；
      不得拿日志里的 SNAPSHOT 当 oracle — verify:
      `tests/integration/test_replay_frame_consistency.py`
- [ ] T402 (`spec §3.2`): 导入检查——`replay/`、`report/` 不导入 `kernel/`、`ledger/`、
      `book/`、`eventlog/`（E5，NFR-004 四类模块须与检查逐一对齐，不得漏检其中任一
      类）；复用 `0.1.1 T604` 机制 — verify: `tests/unit/replay/test_no_kernel_import.py`
- [ ] T403 (`spec E2`): 离线可用性验收——断网环境打开产物，功能完整、无控制台报错 —
      verify: 断网手动验收
- [ ] T404 (`AC-001`—`AC-006`): 运行项目统一质量门 — verify: `python tools/verify.py`
- [ ] T405: 回写 spec 验收证据、活跃索引和状态 — verify: `python tools/validate_spec_lifecycle.py`

## 4. 依赖与并行关系

- `T001 -> T101`：前置条件确认后可开始 Phase 1。
- `T101 -> T102 -> T103`：状态重建按依赖顺序。
- `T201 -> T202`：单文件产物先于逐帧呈现。
- `T301 [P]`：与 T302 修改不同文件（报告生成 vs manifest 校验），可并行。
- `T401 -> T402`：逐帧一致性先于导入检查完成（无顺序依赖，但 E1 是核心门）。

## 5. 明确后移

- 在线实时渲染 → v0.1 / D-7 已排除，离散事件仿真中「实时」无物理意义。
- 人在环交互、多运行对比看板 → v0.2+。
