"""Build retrospective views (index/timeline/summary) from exported conversations.

Reads conversations/<tool>/<session_id>.md produced by export_conversations.py
and derives three derived views:

  - index.md         : lineage tree (main session -> subagents) + tool stats
  - timeline.md      : cross-session, cross-tool chronological event timeline
  - retrospective.md : per-workflow natural-language summary

All views are regenerated from the session files' YAML frontmatter and the
tool-call lines in the bodies, so adding new sessions (re-run export) and
re-running this script keeps them consistent. No manual index maintenance.

Usage:
    python tools/build_retrospective.py [--conversations conversations]
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

TOOL_NAMES = {
    "opencode": "OpenCode",
    "claude": "Claude Code",
    "codex": "Codex CLI",
}

ORCHESTRATION_TOOLS = {
    "task",
    "spawn",
    "agent",
    "followup",
    "followup_task",
    "send_message",
    "wait_agent",
    "interrupt_agent",
    "background_output",
    "background_cancel",
    "collect",
    "toolsearch",
    "skill",
}


@dataclass
class ToolEvent:
    timestamp: str
    tool: str
    call: str


@dataclass
class SessionView:
    tool: str
    session_id: str
    title: str
    project: str
    model: str
    created_at: str
    updated_at: str
    tokens_input: int = 0
    tokens_output: int = 0
    cost: float = 0.0
    parent_id: str = ""
    thread_id: str = ""
    path: str = ""
    tool_events: list[ToolEvent] = field(default_factory=list)


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm_text = text[3:end]
    body = text[end + 4 :]
    fm: dict = {}
    for line in fm_text.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        val = val.strip()
        fm[key.strip()] = _coerce(val)
    return fm, body


def _coerce(val: str):
    try:
        return json.loads(val)
    except json.JSONDecodeError:
        return val


def load_sessions(conversations: Path) -> list[SessionView]:
    sessions: list[SessionView] = []
    for tool in ("opencode", "claude", "codex"):
        tool_dir = conversations / tool
        if not tool_dir.is_dir():
            continue
        for f in sorted(tool_dir.glob("*.md")):
            text = f.read_text(encoding="utf-8")
            fm, body = _split_frontmatter(text)
            sess = SessionView(
                tool=fm.get("tool", tool),
                session_id=str(fm.get("session_id", f.stem)),
                title=str(fm.get("title", f.stem)),
                project=str(fm.get("project", "")),
                model=str(fm.get("model", "")),
                created_at=str(fm.get("created_at", "")),
                updated_at=str(fm.get("updated_at", "")),
                tokens_input=int(fm.get("tokens_input", 0) or 0),
                tokens_output=int(fm.get("tokens_output", 0) or 0),
                cost=float(fm.get("cost", 0) or 0),
                parent_id=str(fm.get("parent_id", "")),
                thread_id=str(fm.get("thread_id", "")),
                path=f"{tool}/{f.name}",
            )
            sess.tool_events = _extract_events(body)
            sessions.append(sess)
    return sessions


def _extract_events(body: str) -> list[ToolEvent]:
    events: list[ToolEvent] = []
    current_ts = ""
    for line in body.splitlines():
        head = re.match(r"^## (user|assistant)(?: · (.+))?$", line)
        if head:
            current_ts = head.group(2) or ""
            continue
        m = re.match(r"^- \*\*tool\*\*: `(.+?)`$", line)
        if m:
            call = m.group(1)
            tool = call.split("(", 1)[0].strip()
            events.append(ToolEvent(timestamp=current_ts, tool=tool, call=call))
    return events


def _is_root(s: SessionView) -> bool:
    return not s.parent_id and not s.thread_id


def build_lineage(sessions: list[SessionView]) -> list[str]:
    by_parent: dict[str, list[SessionView]] = {}
    for s in sessions:
        if s.parent_id:
            by_parent.setdefault(s.parent_id, []).append(s)
    roots = sorted((s for s in sessions if _is_root(s)), key=lambda s: s.created_at)
    lines: list[str] = []
    for root in roots:
        lines.append(f"- **{root.title}** (`{root.tool}` · {root.created_at})")
        for child in sorted(by_parent.get(root.session_id, []), key=lambda s: s.created_at):
            lines.append(f"  - {child.title} (`{child.tool}` · {child.created_at})")
    return lines


def build_timeline(sessions: list[SessionView], summary: bool = False) -> list[str]:
    events: list[tuple[str, str, str]] = []
    for s in sessions:
        events.append((s.created_at, "session-start", f"{s.tool}/{s.title}"))
        events.append((s.updated_at, "session-end", f"{s.tool}/{s.title}"))
        for e in s.tool_events:
            if not e.timestamp:
                continue
            if summary and e.tool.lower() not in ORCHESTRATION_TOOLS:
                continue
            events.append((e.timestamp, e.tool, f"{s.tool}/{s.title}: {e.call}"))
    events.sort(key=lambda x: x[0])
    lines: list[str] = []
    for ts, kind, desc in events:
        lines.append(f"- `{ts}` **{kind}** {desc}")
    return lines


def build_retrospective(sessions: list[SessionView]) -> list[str]:
    by_parent: dict[str, list[SessionView]] = {}
    for s in sessions:
        if s.parent_id:
            by_parent.setdefault(s.parent_id, []).append(s)
    roots = sorted((s for s in sessions if _is_root(s)), key=lambda s: s.created_at)
    lines: list[str] = []
    for i, root in enumerate(roots, 1):
        lines.append(f"## 工作流 {i}: {root.title}")
        lines.append("")
        lines.append(
            f"- 工具: `{TOOL_NAMES.get(root.tool, root.tool)}` · 模型: {root.model or '-'}"
        )
        lines.append(f"- 起止: {root.created_at} → {root.updated_at}")
        if root.tokens_input or root.tokens_output:
            t_line = (
                f"- Token: in {root.tokens_input} / out {root.tokens_output}"
                f" · 成本 ${root.cost:.4f}"
            )
            lines.append(t_line)
        children = sorted(by_parent.get(root.session_id, []), key=lambda s: s.created_at)
        if children:
            lines.append("- 派生子代理:")
            for c in children:
                lines.append(f"  - {c.title} (`{c.tool}` · {c.created_at})")
        lines.append("")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Build retrospective views")
    parser.add_argument("--conversations", default="conversations")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="also write timeline-summary.md with orchestration events only",
    )
    args = parser.parse_args()

    conversations = Path(args.conversations)
    sessions = load_sessions(conversations)

    total = len(sessions)
    header = (
        "# AI 对话归档索引\n\n"
        f"> 由 `tools/build_retrospective.py` 从会话文件自动生成 · 会话总数: {total}\n\n"
        "## 工具统计\n\n| 工具 | 会话数 |\n|---|---|\n"
    )
    stats = []
    for tool in ("opencode", "claude", "codex"):
        n = sum(1 for s in sessions if s.tool == tool)
        stats.append(f"| {TOOL_NAMES.get(tool, tool)} | {n} |")
    lineage = build_lineage(sessions)
    index_lines = [
        header,
        "\n".join(stats),
        "\n## 会话血缘树\n",
        *lineage,
        "\n## 原始会话清单\n\n| 时间 | 工具 | 标题 | 模型 | 文件 |\n|---|---|---|---|---|",
    ]
    for s in sorted(sessions, key=lambda x: x.created_at):
        row = (
            f"| {s.created_at} | {TOOL_NAMES.get(s.tool, s.tool)}"
            f" | {s.title} | {s.model} | `{s.path}` |"
        )
        index_lines.append(row)
    (conversations / "index.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")

    timeline = build_timeline(sessions)
    (conversations / "timeline.md").write_text(
        "# 会话时间线\n\n> 跨会话、跨工具按时间排序的关键事件。\n\n" + "\n".join(timeline) + "\n",
        encoding="utf-8",
    )

    if args.summary:
        summary_timeline = build_timeline(sessions, summary=True)
        (conversations / "timeline-summary.md").write_text(
            "# 会话时间线（编排级摘要）\n\n> 仅保留会话起止与子代理派发/收集等编排级事件，"
            "供快速复盘协作穿插。\n\n" + "\n".join(summary_timeline) + "\n",
            encoding="utf-8",
        )
        print(f"[timeline-summary] -> {conversations / 'timeline-summary.md'}")

    retro = build_retrospective(sessions)
    (conversations / "retrospective.md").write_text(
        "# 工作流复盘概览\n\n> 按主会话（工作流）分组，列出其派生子代理与工作量。\n\n"
        + "\n".join(retro)
        + "\n",
        encoding="utf-8",
    )

    print(f"[index] {total} sessions -> {conversations / 'index.md'}")
    print(f"[timeline] {len(sessions)} sessions -> {conversations / 'timeline.md'}")
    print(f"[retrospective] -> {conversations / 'retrospective.md'}")


if __name__ == "__main__":
    main()
