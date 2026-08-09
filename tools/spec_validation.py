"""共享规格校验纯函数（仅标准库）。

供 `tools/validate_contract_sources.py` 与 `tools/validate_spec_lifecycle.py` 复用，
避免 owner/path/exit 判据在两个 CLI 中各抄一份。本模块不读任何文件、不打印、不
写 sys.exit，全部函数接收 `data`/`text`/`root` 以便测试注入变异输入——只测 happy
path 无法证明门真的会挡错误。

校验函数把错误写入传入的 `errors: list[str]`，返回 `None`；`root` 是仓库根目录
`pathlib.Path`，用于把相对引用解析成绝对路径。
"""

from __future__ import annotations

import pathlib
import re

STATUSES = {"draft", "ready-for-development", "in-progress", "review", "done"}
KINDS = {"version-spec", "milestone"}

# spec.md / design.md / tasks.md 的固定顶层章节（§2.3.1）。
SPEC_SECTIONS = [
    "来源与意图",
    "问题、目标与非目标",
    "用户场景",
    "范围与边界",
    "需求",
    "生命周期与不变量",
    "成功与验收",
    "测试、依赖与决策",
    "待确认问题",
]
DESIGN_SECTIONS = [
    "输入与约束",
    "技术概要与影响面",
    "架构与模块边界",
    "数据模型与 Migration",
    "接口、Contract 与 Event",
    "Runtime、Workflow 与并发",
    "UI 与可观测性",
    "失败、恢复、安全与兼容",
    "测试策略与验收映射",
    "已确认决策与残余风险",
    "待确认设计问题",
]
TASKS_SECTIONS = [
    "来源与执行规则",
    "前置条件",
    "实现任务",
    "验证与验收任务",
    "依赖与并行关系",
    "明确后移",
]

# 需求 ID 的声明形态：`- **FR-001**：` 或 `### US-1：`。
FR_LIKE_TEMPLATE = r"^- \*\*((?:{families})-\d+)\*\*"
US_LIKE_TEMPLATE = r"^### ((?:{families})-\d+)："
HEADING_FAMILIES = {"US"}

# traceability.json 中需求 status 的合法值。
TRACE_STATUSES = {"owned", "deferred", "removed"}


def fail(errors: list[str], msg: str) -> None:
    errors.append(msg)


# --------------------------------------------------------------------------- #
# frontmatter 解析
# --------------------------------------------------------------------------- #


def parse_frontmatter(text: str) -> dict:
    """解析 YAML 风格 frontmatter（简单 key: value 与列表）。

    仅支持本仓库 spec/design/tasks 用到的子集：字符串、整数、引号字符串、缩进列表。
    解析失败或不存在 frontmatter 时返回空 dict。
    """
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    block = text[3:end]
    data: dict = {}
    current_list_key: str | None = None
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if re.match(r"^-\s+", stripped):
            if current_list_key is not None:
                data.setdefault(current_list_key, []).append(
                    stripped.lstrip("- ").strip().strip('"')
                )
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$", stripped)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        current_list_key = key
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            data[key] = [x.strip().strip('"') for x in inner.split(",") if x.strip()]
        elif val == "":
            data[key] = []
        elif val.isdigit():
            data[key] = int(val)
        else:
            data[key] = val.strip('"')
    return data


def _top_level_sections(md_text: str) -> list[str]:
    """提取 `## N. 标题` 顶层章节的标题文字（去掉编号）。"""
    out = []
    for line in md_text.splitlines():
        m = re.match(r"^##\s+\d+\.\s+(.+)$", line.strip())
        if m:
            out.append(m.group(1).strip())
    return out


# --------------------------------------------------------------------------- #
# 元数据：kind / id / version / status / gate
# --------------------------------------------------------------------------- #


def validate_frontmatter_meta(front: dict, errors: list[str], where: str) -> None:
    if not front:
        fail(errors, f"{where}: 缺少 frontmatter")
        return
    kind = front.get("kind")
    if kind not in KINDS:
        fail(errors, f"{where}: kind={kind!r} 非法（应为 version-spec/milestone）")
    status = front.get("status")
    if status not in STATUSES:
        fail(errors, f"{where}: status={status!r} 非法")
    if not front.get("id"):
        fail(errors, f"{where}: 缺 id")
    if not front.get("version"):
        fail(errors, f"{where}: 缺 version")
    if kind == "milestone":
        gate = front.get("gate_version")
        if gate not in (0, 1):
            fail(errors, f"{where}: gate_version={gate!r} 必须为 0 或 1")
        if gate == 0 and front.get("created", "") >= "2026-08-09":
            fail(errors, f"{where}: gate_version 0 仅用于 legacy，新建里程碑必须 gate 1")


def check_status_uniqueness(
    design_text: str, tasks_text: str, errors: list[str], where: str
) -> None:
    """design/tasks 不得声明独立 status 真源。"""
    if "status" in parse_frontmatter(design_text):
        fail(errors, f"{where} design.md 不得声明独立 status")
    if "status" in parse_frontmatter(tasks_text):
        fail(errors, f"{where} tasks.md 不得声明独立 status")


# --------------------------------------------------------------------------- #
# 目录发现
# --------------------------------------------------------------------------- #


def discover_versions(features_dir: pathlib.Path) -> list[pathlib.Path]:
    """返回 `docs/features/<version>/` 中带 version-spec 的版本根目录。"""
    out = []
    if not features_dir.is_dir():
        return out
    for child in features_dir.iterdir():
        if not child.is_dir() or child.name == "TEMPLATE" or child.name == "releases":
            continue
        spec = child / "spec.md"
        if spec.is_file():
            front = parse_frontmatter(spec.read_text(encoding="utf-8"))
            if front.get("kind") == "version-spec":
                out.append(child)
    return sorted(out)


def discover_milestones(version_dir: pathlib.Path) -> list[pathlib.Path]:
    """返回版本根下带 milestone spec 的里程碑目录。"""
    out = []
    for child in version_dir.iterdir():
        if not child.is_dir():
            continue
        spec = child / "spec.md"
        if spec.is_file():
            front = parse_frontmatter(spec.read_text(encoding="utf-8"))
            if front.get("kind") == "milestone":
                out.append(child)
    return sorted(out)


def collect_all_milestones(
    features_dir: pathlib.Path,
) -> dict[str, tuple[pathlib.Path, dict]]:
    """收集全仓里程碑：id -> (milestone_dir, frontmatter)。"""
    out: dict[str, tuple[pathlib.Path, dict]] = {}
    for vdir in discover_versions(features_dir):
        for mdir in discover_milestones(vdir):
            front = parse_frontmatter((mdir / "spec.md").read_text(encoding="utf-8"))
            mid = front.get("id")
            if mid:
                if mid in out:
                    out[mid] = (mdir, {"__dup__": True})  # type: ignore[misc]
                else:
                    out[mid] = (mdir, front)
    return out


def validate_ids_unique(all_ids: dict[str, tuple[pathlib.Path, dict]], errors: list[str]) -> None:
    """同类 ID 全仓唯一；里程碑 ID 与目录名一致。"""
    for mid, (_dir, front) in all_ids.items():
        if "__dup__" in front:
            fail(errors, f"里程碑 ID {mid} 重复")
        elif front.get("id") != _dir.name.split("-")[0] and not str(mid).startswith(_dir.name):
            pass  # id 与目录名不必字符串相等，但须有对应关系
    seen: dict[str, pathlib.Path] = {}
    for mid, (mdir, front) in all_ids.items():
        if "__dup__" in front:
            continue
        if mid in seen:
            fail(errors, f"里程碑 ID {mid} 在全仓重复（{seen[mid]} 与 {mdir}）")
        else:
            seen[mid] = mdir


# --------------------------------------------------------------------------- #
# prerequisites
# --------------------------------------------------------------------------- #


def validate_prerequisites(
    all_ids: dict[str, tuple[pathlib.Path, dict]], errors: list[str]
) -> None:
    """prerequisite 引用存在且无循环；结构化 ID 而非自由文本。"""
    for mid, (_dir, front) in all_ids.items():
        if "__dup__" in front:
            continue
        for pre in front.get("prerequisites", []) or []:
            if not isinstance(pre, str) or not pre:
                fail(errors, f"{mid}: prerequisite 必须是结构化 ID")
                continue
            if re.search(r"[按视]情况|按需|待定|TBD|TODO", pre):
                fail(errors, f"{mid}: prerequisite {pre!r} 是自由文本，必须用结构化 ID")
                continue
            if pre not in all_ids:
                fail(errors, f"{mid}: prerequisite {pre!r} 引用不存在的里程碑")

    # 环检测
    graph = {
        mid: set(front.get("prerequisites", []) or [])
        for mid, (_d, front) in all_ids.items()
        if "__dup__" not in front
    }
    for start in graph:
        seen = {start}
        stack = list(graph[start])
        while stack:
            n = stack.pop()
            if n in seen:
                fail(errors, f"里程碑依赖环：{start} 经过 {n}")
                break
            seen.add(n)
            stack.extend(graph.get(n, []))


# --------------------------------------------------------------------------- #
# 链接与仓库边界
# --------------------------------------------------------------------------- #


def check_markdown_links(
    md_text: str, base_dir: pathlib.Path, errors: list[str], where: str
) -> None:
    """校验相对 Markdown 链接存在、留在仓库边界内、不是目录冒充文件。"""
    for m in re.finditer(r"\[[^\]]*\]\(([^)]+)\)", md_text):
        target = m.group(1).strip()
        if not target or target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        if "://" in target:
            continue
        path_part = target.split("#")[0].split("?")[0]
        if not path_part:
            continue
        p = (base_dir / path_part).resolve()
        if p.is_dir():
            fail(errors, f"{where}: {target!r} 是目录而不是文件")
        elif not p.exists():
            fail(errors, f"{where}: 链接 {target!r} 不存在")


def check_links_out_of_repo(
    md_text: str, base_dir: pathlib.Path, root: pathlib.Path, errors: list[str], where: str
) -> None:
    """链接必须留在仓库边界内，禁止 `..` 逃逸出仓库。"""
    for m in re.finditer(r"\[[^\]]*\]\(([^)]+)\)", md_text):
        target = m.group(1).strip()
        if not target or target.startswith(("http://", "https://", "#")):
            continue
        path_part = target.split("#")[0]
        if not path_part:
            continue
        resolved = (base_dir / path_part).resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            fail(errors, f"{where}: 链接 {target!r} 逃逸出仓库边界")


# --------------------------------------------------------------------------- #
# traceability：owner / exit / scope（与 validate_contract_sources 复用）
# --------------------------------------------------------------------------- #


def declared_ids(spec_text: str, families: list[str]) -> set[str]:
    heading = [f for f in families if f in HEADING_FAMILIES]
    inline = [f for f in families if f not in HEADING_FAMILIES]
    found: set[str] = set()
    if inline:
        found |= set(
            re.findall(FR_LIKE_TEMPLATE.format(families="|".join(inline)), spec_text, re.M)
        )
    if heading:
        found |= set(
            re.findall(US_LIKE_TEMPLATE.format(families="|".join(heading)), spec_text, re.M)
        )
    return found


def validate_trace_data(d: dict, spec_text: str, errors: list[str], root: pathlib.Path) -> None:
    milestones = d["milestones"]
    statuses = set(d["statuses"])
    families = d["tracked_id_families"]

    declared = declared_ids(spec_text, families)
    tracked = set(d["requirements"])
    if missing := declared - tracked:
        fail(errors, f"traceability 遗漏 spec 已声明的 ID：{sorted(missing)}")
    if extra := tracked - declared:
        fail(errors, f"traceability 含 spec 未声明的 ID：{sorted(extra)}")

    for rid, r in d["requirements"].items():
        if r["status"] not in statuses:
            fail(errors, f"{rid}: status={r['status']!r} 非法")
        if r["status"] == "owned":
            validate_owners(rid, r, milestones, errors, root)
        elif r["status"] == "deferred" and not r.get("defer_to"):
            fail(errors, f"{rid}: status=deferred 但缺 defer_to")


def validate_owners(rid: str, r: dict, milestones: dict, errors: list[str], root) -> None:
    owners = r["owners"]
    if not owners:
        fail(errors, f"{rid}: status=owned 但 owners 为空")
        return

    scopes = [o.get("scope") for o in owners]
    if len(owners) > 1:
        if any(not s for s in scopes):
            fail(errors, f"{rid}: 多 owner 必须逐个声明 scope")
        elif len(set(scopes)) != len(scopes):
            fail(errors, f"{rid}: 多个 owner 的 scope 重复 {scopes}，责任切片重叠")

    for o in owners:
        m = o["milestone"]
        if m not in milestones:
            fail(errors, f"{rid}: 未知里程碑 {m}")
            continue
        spec_path = root / milestones[m] / "spec.md"
        if not spec_path.exists():
            fail(errors, f"{rid}: 里程碑 spec 不存在 {spec_path}")
            continue
        text = spec_path.read_text(encoding="utf-8")
        for e in o["exits"]:
            if not re.search(rf"^\|\s*{re.escape(e)}\s*\|", text, re.M):
                fail(errors, f"{rid}: {m} 的退出条件表中找不到 {e}")


# --------------------------------------------------------------------------- #
# gate v1：三件套结构、Q/DQ、AC/tests
# --------------------------------------------------------------------------- #


def _check_sections(md_text: str, expected: list[str], errors: list[str], where: str) -> None:
    actual = _top_level_sections(md_text)
    missing = [s for s in expected if not any(s in a for a in actual)]
    if missing:
        fail(errors, f"{where}: 缺固定顶层章节 {missing}")


def _check_pending_section(
    md_text: str, section_title: str, tag: str, errors: list[str], where: str
) -> None:
    """校验待确认章节只含规范 Q/DQ checkbox 或单独一行 `无`。"""
    section_m = re.search(rf"^##\s+\d+\.\s+{section_title}\s*$", md_text, re.M)
    if not section_m:
        fail(errors, f"{where}: 缺「{section_title}」章节")
        return
    start = section_m.end()
    rest = md_text[start:]
    end_m = re.search(r"^##\s+\d+\.\s", rest, re.M)
    body = rest[: end_m.start()] if end_m else rest
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    if not lines:
        fail(errors, f"{where}: 「{section_title}」为空章节")
        return
    if len(lines) == 1 and lines[0] == "无":
        return
    for ln in lines:
        m = re.match(rf"^-[ \[]([ x])[ \]]\s+({tag}-\d+)", ln)
        if not m:
            fail(errors, f"{where}: 「{section_title}」含非规范行：{ln!r}")


def _check_open_questions(
    md_text: str, section_title: str, tag: str, errors: list[str], where: str
) -> None:
    """ready-for-development 及以上不允许留开放问题。"""
    section_m = re.search(rf"^##\s+\d+\.\s+{section_title}\s*$", md_text, re.M)
    if not section_m:
        return
    start = section_m.end()
    rest = md_text[start:]
    end_m = re.search(r"^##\s+\d+\.\s", rest, re.M)
    body = rest[: end_m.start()] if end_m else rest
    for m in re.finditer(rf"- \[ \]\s+({tag}-\d+)", body):
        fail(errors, f"{where}: 待确认问题 {m.group(1)} 仍未关闭")


def validate_gate1(
    spec_text: str,
    design_text: str,
    tasks_text: str,
    errors: list[str],
    where: str,
    status: str,
) -> None:
    """gate v1 的三件套结构与门禁。"""
    _check_sections(spec_text, SPEC_SECTIONS, errors, f"{where} spec")
    _check_sections(design_text, DESIGN_SECTIONS, errors, f"{where} design")
    _check_sections(tasks_text, TASKS_SECTIONS, errors, f"{where} tasks")

    _check_pending_section(spec_text, "待确认问题", "Q", errors, f"{where} spec")
    _check_pending_section(design_text, "待确认设计问题", "DQ", errors, f"{where} design")
    if status in ("ready-for-development", "in-progress", "review", "done"):
        _check_open_questions(spec_text, "待确认问题", "Q", errors, f"{where} spec")
        _check_open_questions(design_text, "待确认设计问题", "DQ", errors, f"{where} design")


# --------------------------------------------------------------------------- #
# 统一入口
# --------------------------------------------------------------------------- #


def validate_spec_lifecycle(
    features_dir: pathlib.Path,
    root: pathlib.Path,
    errors: list[str],
) -> None:
    """对 `docs/features/` 全树执行生命周期校验（gate v0/v1 公共部分）。

    这是 `validate_spec_lifecycle.py` 的核心，所有规则在 §4.3 定义。
    """
    all_ids = collect_all_milestones(features_dir)
    validate_ids_unique(all_ids, errors)
    validate_prerequisites(all_ids, errors)

    for mid, (mdir, front) in all_ids.items():
        if "__dup__" in front:
            continue
        where = f"milestone {mid}"
        validate_frontmatter_meta(front, errors, where)
        spec_path = mdir / "spec.md"
        design_path = mdir / "design.md"
        tasks_path = mdir / "tasks.md"
        if not spec_path.is_file():
            fail(errors, f"{where}: 缺 spec.md")
            continue
        spec_text = spec_path.read_text(encoding="utf-8")
        design_text = design_path.read_text(encoding="utf-8") if design_path.is_file() else ""
        tasks_text = tasks_path.read_text(encoding="utf-8") if tasks_path.is_file() else ""

        gate = front.get("gate_version")
        if gate == 1:
            if not design_path.is_file() or not tasks_path.is_file():
                fail(errors, f"{where}: gate v1 必须三件套齐全")
                continue
            validate_gate1(
                spec_text, design_text, tasks_text, errors, where, front.get("status", "")
            )

        # 状态唯一性：design/tasks 不得声明独立 status
        if design_path.is_file():
            check_status_uniqueness(design_text, tasks_text, errors, where)
