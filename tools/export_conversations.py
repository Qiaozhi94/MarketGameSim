"""Export local AI CLI conversations for the current project into conversations/.

Supports three local CLI data sources:
  - OpenCode   : SQLite database ~/.local/share/opencode/opencode.db
  - Claude Code: JSONL transcripts under ~/.claude/projects/<project-encoded>/
  - Codex CLI  : JSONL rollouts under ~/.codex/sessions/**/rollout-*.jsonl

Each session is written to conversations/<tool>/<session_id>.md with a YAML
frontmatter block (tool, model, timestamps, token usage, parent link) followed
by a structured Markdown transcript. A global index.md is generated as the
entry point for AI-powered retrospectives.

Usage:
    python tools/export_conversations.py [--project-dir D:/Projects/market-game-sim]
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_PROJECT = "D:/Projects/market-game-sim"
TOOL_NAMES = {
    "opencode": "OpenCode",
    "claude": "Claude Code",
    "codex": "Codex CLI",
}


@dataclass
class Msg:
    role: str
    timestamp: str
    text: str
    tool_calls: list[str] = field(default_factory=list)
    tool_results: list[str] = field(default_factory=list)


@dataclass
class Session:
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
    messages: list[Msg] = field(default_factory=list)


def _fmt_ts(ms: int | None) -> str:
    if not ms:
        return ""
    return datetime.fromtimestamp(ms / 1000, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fmt_iso(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return iso


def _norm_project(project: str) -> str:
    return project.replace("\\", "/").rstrip("/")


def _is_project(project: str, target: str) -> bool:
    p = _norm_project(project).lower()
    t = _norm_project(target).lower()
    return p == t or p.endswith("/" + t.split("/")[-1]) and t.split("/")[-1] in p


def _sanitize(s: str, limit: int = 2000) -> str:
    s = (s or "").strip()
    if len(s) > limit:
        s = s[:limit] + "\n…[truncated]"
    return s


def export_opencode(project: str, out_dir: Path) -> list[Session]:
    db = Path.home() / ".local/share/opencode/opencode.db"
    if not db.exists():
        return []
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    sessions: list[Session] = []
    rows = cur.execute(
        """SELECT id, title, directory, model, time_created, time_updated,
                  tokens_input, tokens_output, cost, parent_id
           FROM session WHERE directory LIKE ?""",
        (f"%{project.split('/')[-1]}%",),
    ).fetchall()

    for row in rows:
        if not _is_project(row["directory"], project):
            continue
        model = row["model"] or ""
        try:
            m = json.loads(model)
            model_disp = m.get("id", model)
        except (json.JSONDecodeError, TypeError):
            model_disp = model
        sess = Session(
            tool="opencode",
            session_id=row["id"],
            title=row["title"] or row["id"],
            project=row["directory"],
            model=model_disp,
            created_at=_fmt_ts(row["time_created"]),
            updated_at=_fmt_ts(row["time_updated"]),
            tokens_input=row["tokens_input"] or 0,
            tokens_output=row["tokens_output"] or 0,
            cost=row["cost"] or 0.0,
            parent_id=row["parent_id"] or "",
        )

        msg_rows = cur.execute(
            """SELECT id, time_created, data FROM message
               WHERE session_id = ? ORDER BY time_created, id""",
            (row["id"],),
        ).fetchall()
        for mrow in msg_rows:
            try:
                mdata = json.loads(mrow["data"])
            except (json.JSONDecodeError, TypeError):
                continue
            role = mdata.get("role", "unknown")
            ts = _fmt_ts(mrow["time_created"])
            msg = Msg(role=role, timestamp=ts, text="")

            part_rows = cur.execute(
                """SELECT data FROM part WHERE message_id = ? ORDER BY time_created, id""",
                (mrow["id"],),
            ).fetchall()
            for prow in part_rows:
                try:
                    p = json.loads(prow["data"])
                except (json.JSONDecodeError, TypeError):
                    continue
                ptype = p.get("type")
                if ptype == "text":
                    msg.text += (p.get("text") or "") + "\n"
                elif ptype == "reasoning":
                    msg.text += "\n> [reasoning] " + (p.get("text") or "").strip() + "\n"
                elif ptype == "tool":
                    tool = p.get("tool", "")
                    state = p.get("state", {})
                    status = state.get("status", "")
                    inp = state.get("input", {})
                    try:
                        inp_s = json.dumps(inp, ensure_ascii=False)
                    except (TypeError, ValueError):
                        inp_s = str(inp)
                    msg.tool_calls.append(f"{tool}({_sanitize(inp_s, 500)})")
                    if status and status != "running":
                        out = state.get("output", "")
                        if isinstance(out, (dict, list)):
                            try:
                                out = json.dumps(out, ensure_ascii=False)
                            except (TypeError, ValueError):
                                out = str(out)
                        if out:
                            msg.tool_results.append(_sanitize(str(out), 800))
            if msg.text or msg.tool_calls:
                sess.messages.append(msg)
        if sess.messages:
            sessions.append(sess)
    conn.close()
    return sessions


def _claude_project_dir(project: str) -> str:
    enc = project.replace("\\", "/").lstrip("/").replace("/", "-").replace(":", "-")
    return re.sub(r"[^A-Za-z0-9-]", "-", enc)


def export_claude(project: str, out_dir: Path) -> list[Session]:
    enc = _claude_project_dir(project)
    base = Path.home() / ".claude/projects" / enc
    if not base.is_dir():
        return []
    sessions: list[Session] = []
    for f in sorted(base.glob("*.jsonl")):
        sess_id = f.stem
        msgs: list[Msg] = []
        sess = Session(
            tool="claude",
            session_id=sess_id,
            title="",
            project=project,
            model="",
            created_at="",
            updated_at="",
        )
        with f.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rtype = rec.get("type")
                ts = _fmt_iso(rec.get("timestamp"))
                if rtype == "user":
                    content = rec.get("message", {}).get("content")
                    msg = Msg(role="user", timestamp=ts, text=_claude_text(content))
                    if msg.text:
                        msgs.append(msg)
                elif rtype == "assistant":
                    message = rec.get("message", {})
                    content = message.get("content")
                    model = message.get("model", "")
                    if model and not sess.model:
                        sess.model = model
                    msg = Msg(role="assistant", timestamp=ts, text="", tool_calls=[])
                    text_parts, tool_calls = _claude_assistant(content)
                    msg.text = text_parts
                    msg.tool_calls = tool_calls
                    if msg.text or msg.tool_calls:
                        msgs.append(msg)
        if msgs:
            sess.messages = msgs
            sess.title = sess_id
            sess.updated_at = next((m.timestamp for m in reversed(msgs) if m.timestamp), "")
            sess.created_at = next((m.timestamp for m in msgs if m.timestamp), "")
            sess.updated_at = next((m.timestamp for m in reversed(msgs) if m.timestamp), "")
            sess.title = sess_id
            sessions.append(sess)
    return sessions


def _claude_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts).strip()
    return ""


def _claude_assistant(content) -> tuple[str, list[str]]:
    text = _claude_text(content)
    calls: list[str] = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                name = block.get("name", "")
                inp = block.get("input", {})
                try:
                    inp_s = json.dumps(inp, ensure_ascii=False)
                except (TypeError, ValueError):
                    inp_s = str(inp)
                calls.append(f"{name}({_sanitize(inp_s, 500)})")
    return text, calls


def export_codex(project: str, out_dir: Path) -> list[Session]:
    base = Path.home() / ".codex/sessions"
    if not base.is_dir():
        return []
    sessions: list[Session] = []
    for f in sorted(base.rglob("rollout-*.jsonl")):
        sess_meta = None
        with f.open(encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
            try:
                rec = json.loads(first)
                if rec.get("type") == "session_meta":
                    sess_meta = rec.get("payload", {})
            except json.JSONDecodeError:
                sess_meta = None
        if not sess_meta:
            continue
        cwd = sess_meta.get("cwd", "")
        if not _is_project(cwd, project):
            continue
        thread_id = sess_meta.get("session_id") or ""
        sess = Session(
            tool="codex",
            session_id=f.stem,
            title=sess_meta.get("thread_name") or f.stem,
            project=cwd,
            model=sess_meta.get("model_provider", ""),
            created_at=_fmt_iso(sess_meta.get("timestamp")),
            updated_at="",
            thread_id=thread_id,
        )
        msgs: list[Msg] = []
        with f.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rtype = rec.get("type")
                if rtype == "response_item":
                    payload = rec.get("payload", {})
                    if payload.get("type") != "message":
                        continue
                    role = payload.get("role", "")
                    if role == "developer":
                        continue
                    ts = _fmt_iso(rec.get("timestamp"))
                    content = payload.get("content", [])
                    text = _codex_text(content)
                    if text:
                        msgs.append(Msg(role=role, timestamp=ts, text=text))
        if msgs:
            sess.messages = msgs
            sess.created_at = next((m.timestamp for m in msgs if m.timestamp), "")
            sess.updated_at = next((m.timestamp for m in reversed(msgs) if m.timestamp), "")
            sessions.append(sess)
    return sessions


def _codex_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") in ("input_text", "output_text"):
                parts.append(block.get("text", ""))
        return "\n".join(parts).strip()
    return ""


def _yml(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return json.dumps(str(v), ensure_ascii=False)


def _render_session(sess: Session) -> str:
    fm = {
        "tool": sess.tool,
        "tool_name": TOOL_NAMES.get(sess.tool, sess.tool),
        "session_id": sess.session_id,
        "title": sess.title,
        "project": sess.project,
        "model": sess.model or "",
        "created_at": sess.created_at,
        "updated_at": sess.updated_at,
        "tokens_input": sess.tokens_input,
        "tokens_output": sess.tokens_output,
        "cost": round(sess.cost, 4),
    }
    if sess.parent_id:
        fm["parent_id"] = sess.parent_id
    if sess.thread_id:
        fm["thread_id"] = sess.thread_id
    header = ["---"]
    for k, v in fm.items():
        header.append(f"{k}: {_yml(v)}")
    header.append("---")
    header.append("")
    header.append(f"# {sess.title}")
    header.append("")
    for msg in sess.messages:
        ts = f" · {msg.timestamp}" if msg.timestamp else ""
        header.append(f"## {msg.role}{ts}")
        header.append("")
        for tc in msg.tool_calls:
            header.append(f"- **tool**: `{tc}`")
        if msg.tool_calls and msg.text:
            header.append("")
        if msg.text:
            header.append(msg.text.rstrip())
        for tr in msg.tool_results:
            header.append("")
            header.append("  <details><summary>tool output</summary>")
            header.append("")
            header.append("  ```text")
            header.append(tr)
            header.append("  ```")
            header.append("  </details>")
        header.append("")
    return "\n".join(header)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export AI CLI conversations")
    parser.add_argument("--project-dir", default=DEFAULT_PROJECT)
    parser.add_argument("--out", default="conversations")
    args = parser.parse_args()

    project = _norm_project(args.project_dir)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_sessions: list[Session] = []
    for tool, exporter in (
        ("opencode", export_opencode),
        ("claude", export_claude),
        ("codex", export_codex),
    ):
        tool_dir = out_dir / tool
        tool_dir.mkdir(parents=True, exist_ok=True)
        for old in tool_dir.glob("*.md"):
            old.unlink()
        sessions = exporter(project, tool_dir)
        for sess in sessions:
            (tool_dir / f"{sess.session_id}.md").write_text(_render_session(sess), encoding="utf-8")
        all_sessions.extend(sessions)
        print(f"[{tool}] exported {len(sessions)} sessions")

    print(f"[done] total {len(all_sessions)} sessions in {out_dir}")
    print("[hint] run `python tools/build_retrospective.py` to regenerate views")


if __name__ == "__main__":
    main()
