# conversations/ — AI 对话归档

本目录归档本机三大 AI CLI（OpenCode、Claude Code、Codex CLI）在本项目
（`D:/Projects/market-game-sim`）内的全部会话记录，供项目结束后进行 **AI 深度复盘**。

## 结构

```text
conversations/
├── index.md           # 全局索引：血缘树 + 工具统计 + 原始会话清单
├── timeline.md        # 跨会话、跨工具按时间排序的事件时间线（全量，可能较大）
├── timeline-summary.md# 编排级摘要时间线（--summary 生成，仅子代理派发/收集等）
├── retrospective.md   # 按主会话（工作流）分组的复盘概览
├── README.md
├── opencode/          # OpenCode 会话（SQLite 导出）
├── claude/            # Claude Code 会话（JSONL 导出）
└── codex/             # Codex CLI 会话（JSONL rollout 导出）
```

三个视图（`index.md` / `timeline.md` / `retrospective.md`）由
`tools/build_retrospective.py` 从会话文件的 frontmatter 与正文自动生成，专门解决
「写 → 检视 → 返工」这类多代理穿插协作的复盘需求：

- **index.md 血缘树**：主会话 → 子代理的层级，一眼看清每个工作流驱动了哪些子代理。
- **timeline.md 时间线**：所有会话的派发/收集/工具事件按真实时间全局排序交叉，
  还原"A 写代码 → B 检视 → A 再改"的先后次序。
- **retrospective.md 复盘概览**：每个主工作流的工具、模型、token、成本及其派生子代理。

> 全量 `timeline.md` 可能很大（记录了每条工具调用，如 500KB+）。若只需快速看协作
> 穿插，用 `--summary` 生成 `timeline-summary.md`（约 8KB），只保留会话起止与子代理
> 派发/收集等编排级事件。

每个会话一个 `*.md` 文件，包含：

- **YAML frontmatter**：`tool` / `tool_name` / `session_id` / `title` / `project` /
  `model` / `created_at` / `updated_at` / `tokens_input` / `tokens_output` /
  `cost`，以及可选的 `parent_id`（子代理上级会话）、`thread_id`（Codex 顶层线程）。
- **Markdown 正文**：按时间升序的对话记录，角色以 `## user` / `## assistant`
  分段，工具调用以 `- **tool**: ...` 列出，工具输出折叠在 `<details>` 中。

## 重新生成（会话持续增长时的维护）

项目未完成、会话会持续增加。归档采用**幂等全量重导**，无需任何增量/手工维护：

```bash
python tools/export_conversations.py --project-dir "D:/Projects/market-game-sim"
python tools/build_retrospective.py --conversations conversations --summary
```

- `export` 每次清空各工具子目录再全量重写会话（当前 21 会话约 4MB，秒级完成），
  天然幂等，新增会话后重跑即可纳入。
- `build` 从会话 frontmatter 重建全部三个视图，与原始数据源解耦——新增任何会话
  都会自动进入血缘树、时间线、复盘概览。`--summary` 额外生成编排级摘要时间线。

## 复盘用法

以 `conversations/index.md` 的血缘树为入口定位工作流，用 `timeline.md` 还原穿插
次序，再用 `retrospective.md` 看每个工作流的工作量与派生子代理；需要细节时深入
对应会话文件。frontmatter 中的 token / cost / model 可用于工作量与成本分析；
`parent_id` 可还原子代理与主会话的协作关系。
