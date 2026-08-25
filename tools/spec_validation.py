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
RESEARCH_CLAIM_STATUSES = {"not-applicable", "not-established", "established"}
EVIDENCE_CLASSES = {"engineering-demonstration", "experiment-preview", "formal-research"}
KINDS = {"version-spec", "milestone"}

# frontmatter 里的布尔字段：`parse_frontmatter` 只产出字符串，因此合法值是闭集而不是
# 「Python 真值」。不做闭集校验的话，`True`/`yes` 这类变体或拼错的 key 会让依赖它的
# 门禁静默失效（fail-open）——研究声明门禁保护的是版本能否签收，不能靠拼写运气。
BOOL_FIELDS = ("research_claim_required",)
BOOL_VALUES = {"true", "false"}

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


def in_enum(value: object, allowed: set[str]) -> bool:
    """闭集判定：非字符串一律不合法，且不得让校验器自己崩掉。

    `parse_frontmatter` 对 `key:`（空值）产出的是 `[]`，直接 `value in {...}` 会抛
    `TypeError: unhashable type`——校验器崩溃和校验通过一样糟：CI 报的是堆栈，不是
    "这个字段写错了"，定位成本完全不同。
    """
    return isinstance(value, str) and value in allowed


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
    if not in_enum(kind, KINDS):
        fail(errors, f"{where}: kind={kind!r} 非法（应为 version-spec/milestone）")
    status = front.get("status")
    if not in_enum(status, STATUSES):
        fail(errors, f"{where}: status={status!r} 非法")
    research_claim_status = front.get("research_claim_status")
    if not in_enum(research_claim_status, RESEARCH_CLAIM_STATUSES):
        fail(
            errors,
            f"{where}: research_claim_status={research_claim_status!r} 非法"
            "（应为 not-applicable/not-established/established）",
        )
    evidence_class = front.get("evidence_class")
    if evidence_class is not None and not in_enum(evidence_class, EVIDENCE_CLASSES):
        fail(errors, f"{where}: evidence_class={evidence_class!r} 非法")
    for key in BOOL_FIELDS:
        value = front.get(key)
        if value is not None and not in_enum(value, BOOL_VALUES):
            fail(errors, f"{where}: {key}={value!r} 非法（只允许 true/false）")
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
    if "research_claim_status" in parse_frontmatter(design_text):
        fail(errors, f"{where} design.md 不得声明独立 research_claim_status")
    if "research_claim_status" in parse_frontmatter(tasks_text):
        fail(errors, f"{where} tasks.md 不得声明独立 research_claim_status")


def validate_research_claim(
    front: dict,
    root: pathlib.Path,
    errors: list[str],
    where: str,
    *,
    is_version: bool = False,
) -> None:
    """研究声明与工程生命周期正交，但 established 必须有正式仓库内证据。"""
    claim = front.get("research_claim_status")
    required = front.get("research_claim_required") == "true"
    if required and claim == "not-applicable":
        # 不等到 done 才报：草稿期就矛盾的配置一旦潜伏下来，等到签收那天才暴露，
        # 修的人已经不是写的人。
        fail(errors, f"{where}: research_claim_required=true 与 not-applicable 矛盾")
    if claim == "established":
        if front.get("status") != "done":
            fail(errors, f"{where}: research_claim_status=established 但 status 不是 done")
        evidence_class = front.get("evidence_class")
        if evidence_class == "experiment-preview":
            fail(errors, f"{where}: experiment-preview 是预览证据，不能建立研究声明")
        elif evidence_class != "formal-research":
            fail(errors, f"{where}: established 必须声明 evidence_class=formal-research")
        refs = front.get("research_evidence")
        if not isinstance(refs, list) or not refs:
            fail(errors, f"{where}: established 但缺 research_evidence 列表")
        else:
            for ref in refs:
                candidate = pathlib.Path(ref)
                if candidate.is_absolute():
                    fail(errors, f"{where}: research_evidence 必须是仓库内相对路径：{ref!r}")
                    continue
                resolved = (root / candidate).resolve()
                try:
                    resolved.relative_to(root.resolve())
                except ValueError:
                    fail(errors, f"{where}: research_evidence 逃逸出仓库：{ref!r}")
                    continue
                if not resolved.is_file():
                    fail(errors, f"{where}: research_evidence 不存在：{ref!r}")
    if front.get("status") == "done" and required and claim != "established":
        fail(errors, f"{where}: 该规格要求正式研究声明，status=done 时必须 established")
    if is_version and front.get("status") == "done" and claim == "not-established":
        fail(errors, f"{where}: 版本 status=done 时研究声明不得仍为 not-established")


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
    """收集全仓里程碑：id -> (milestone_dir, frontmatter)。

    重复 ID 时保留首个条目，并把重复的目录追加到 `__dups__` 列表。
    """
    out: dict[str, tuple[pathlib.Path, dict]] = {}
    for vdir in discover_versions(features_dir):
        for mdir in discover_milestones(vdir):
            front = parse_frontmatter((mdir / "spec.md").read_text(encoding="utf-8"))
            mid = front.get("id")
            if not mid:
                continue
            if mid in out:
                dups = out[mid][1].setdefault("__dups__", [])
                dups.append(mdir)
            else:
                out[mid] = (mdir, front)
    return out


def validate_ids_unique(all_ids: dict[str, tuple[pathlib.Path, dict]], errors: list[str]) -> None:
    """同类 ID 全仓唯一。"""
    for mid, (mdir, front) in all_ids.items():
        for dup in front.get("__dups__", []):
            fail(errors, f"里程碑 ID {mid} 重复（{mdir} 与 {dup}）")


# --------------------------------------------------------------------------- #
# prerequisites
# --------------------------------------------------------------------------- #


# 进入这些状态即视为「实施入口」已打开（SOP §3：前置未达成时实施入口由门禁判定
# blocked）；`draft`/`ready-for-development` 允许在前置未 done 时先把文档写好。
_IMPLEMENTATION_STATUSES = {"in-progress", "review", "done"}


def validate_prerequisites(
    all_ids: dict[str, tuple[pathlib.Path, dict]], errors: list[str]
) -> None:
    """prerequisite 引用存在且无循环；结构化 ID 而非自由文本；前置未 done 时禁止
    自身进入实施状态（SOP §3 状态门）。"""
    for mid, (_dir, front) in all_ids.items():
        own_status = front.get("status")
        for pre in front.get("prerequisites", []) or []:
            if not isinstance(pre, str) or not pre:
                fail(errors, f"{mid}: prerequisite 必须是结构化 ID")
                continue
            if re.search(r"[按视]情况|按需|待定|TBD|TODO", pre):
                fail(errors, f"{mid}: prerequisite {pre!r} 是自由文本，必须用结构化 ID")
                continue
            if pre not in all_ids:
                fail(errors, f"{mid}: prerequisite {pre!r} 引用不存在的里程碑")
                continue
            if own_status in _IMPLEMENTATION_STATUSES:
                pre_status = all_ids[pre][1].get("status")
                if pre_status != "done":
                    fail(
                        errors,
                        f"{mid}: status={own_status!r} 但前置 {pre!r} 未 done"
                        f"（当前 {pre_status!r}），实施入口被前置未达成阻塞（SOP §3）",
                    )

    # 环检测：三色 DFS，只判当前路径上的回边（不误报菱形依赖）。
    graph = {mid: set(front.get("prerequisites", []) or []) for mid, (_d, front) in all_ids.items()}
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {mid: WHITE for mid in graph}

    def visit(node: str) -> bool:
        color[node] = GRAY
        for nxt in graph.get(node, ()):
            if nxt not in color:
                continue
            if color[nxt] == GRAY:
                fail(errors, f"里程碑依赖环：{node} -> {nxt}")
                return True
            if color[nxt] == WHITE and visit(nxt):
                return True
        color[node] = BLACK
        return False

    for start in list(graph):
        if color[start] == WHITE and visit(start):
            break


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
    missing = [s for s in expected if s not in actual]
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


_AC_ID = re.compile(r"AC-(\d+)")
# 只匹配 tasks.md 里真正的「范围声明」形态：`AC-001`—`AC-005`（两端都是反引号
# 包裹的 AC ID，中间用 em dash 连接）。不能退化成「AC 编号是否在全文任意位置
# 出现过」——那样即使范围声明本身过期（如 T404 仍写 AC-005），只要另一个任务
# 单独提过新 ID（如 T202 提了 `AC-006`），旧检查也会误判为通过（R014-D004 在
# 0.1.4 复核 round 3 出现过一次：门禁验证了错误的代理量）。
_AC_RANGE = re.compile(r"`AC-\d+`—`AC-(\d+)`")


def _check_ac_range_completeness(
    spec_text: str, tasks_text: str, errors: list[str], where: str
) -> None:
    """spec 验收清单新增 AC 后，tasks.md 里硬编码的 AC 范围声明必须跟着扩大
    ——否则「运行统一质量门」这类任务会静默漏掉新 AC（acceptance-mapping-gap）。"""
    spec_ac_ids = {int(n) for n in _AC_ID.findall(spec_text)}
    if not spec_ac_ids:
        return
    max_ac = max(spec_ac_ids)
    for end in _AC_RANGE.findall(tasks_text):
        if int(end) < max_ac:
            fail(
                errors,
                f"{where}: tasks.md 声明的 AC 范围上界为 AC-{end}，"
                f"未覆盖 spec 验收清单已到的 AC-{max_ac:03d}",
            )


_AC_DECL = re.compile(r"^- \[[ x]\]\s+\*\*(?P<ac>AC-\d+)\*\*\s*\((?P<refs>[^)]*)\)", re.M)
_BACKTICKED_ID = re.compile(r"`((?:US|FR|NFR|SC|KR|DR|TR|IR|PR|KPI|E)-?\d+)`")
_DECLARED_ID = re.compile(r"^- \*\*((?:US|FR|NFR|SC|KR|DR|TR|IR|PR|KPI)-\d+)\*\*", re.M)
_DECLARED_HEADING_ID = re.compile(r"^### ((?:US)-\d+)[：:]", re.M)
_EXIT_ROW = re.compile(r"^\|\s*(E\d+)\s*\|", re.M)
_VERIFY_TOKENS = re.compile(r"—\s*verify:\s*(?P<verify>[^\n]*(?:\n\s{6,}[^\n]*)*)", re.M)


def _declared_ids(text: str) -> set[str]:
    return set(_DECLARED_ID.findall(text)) | set(_DECLARED_HEADING_ID.findall(text))


def _ac_task_coverage(tasks_text: str) -> dict[int, list[str]]:
    """AC 编号 -> 覆盖它的任务块列表；范围声明 `AC-001`—`AC-012` 会被展开。"""
    coverage: dict[int, list[str]] = {}
    for _mark, _tid, block in _task_blocks(tasks_text):
        numbers: set[int] = set()
        for start, end in re.findall(r"`AC-(\d+)`—`AC-(\d+)`", block):
            numbers.update(range(int(start), int(end) + 1))
        numbers.update(int(n) for n in re.findall(r"`AC-(\d+)`", block))
        for number in numbers:
            coverage.setdefault(number, []).append(block)
    return coverage


def _block_has_existing_path(block: str, root: pathlib.Path) -> bool:
    """任务的 verify 段是否指向仓库内真实存在的路径。"""
    match = _VERIFY_TOKENS.search(block)
    if not match:
        return False
    for token in re.findall(r"`([^`]+)`", match.group("verify")):
        for candidate in token.split():
            candidate = candidate.strip().rstrip("；,，")
            if "/" not in candidate:
                continue
            if (root / candidate).exists():
                return True
    return False


# 「本 spec 声明的需求必须有 AC 认领」规则的引入日；此前 created 的里程碑不追溯执法
# （0.1.4 的 US-004/US-005/TR-001/SC-006 就没有 AC，规则出现时它已经 done）。
AC_COVERAGE_RULE_DATE = "2026-08-15"
# 只对这几族强制 AC 覆盖：US 用「独立测试」段自证，SC/KR 是版本级成功标准，
# 它们的验收锚点在版本根而不在里程碑。
AC_COVERED_FAMILIES = ("FR", "NFR", "DR", "TR", "IR")


def _check_requirement_ac_coverage(
    front: dict, spec_text: str, errors: list[str], where: str
) -> None:
    """本 spec 声明的每条 FR/NFR/DR/TR/IR 都必须被至少一条 AC 引用。

    D009 的成因：0.1.5 一次写下 6 条 IR/DR/TR，AC 却只引用 FR/NFR/SC——接口、数据、
    事件三类需求整体没有验收锚点，而且没有任何门禁会说话。
    """
    created = front.get("created", "")
    if not isinstance(created, str) or created < AC_COVERAGE_RULE_DATE:
        return
    body = _without_fenced_code(spec_text)
    declared = {rid for rid in _declared_ids(body) if rid.split("-")[0] in AC_COVERED_FAMILIES}
    referenced: set[str] = set()
    for match in _AC_DECL.finditer(body):
        referenced.update(_BACKTICKED_ID.findall(match.group("refs")))
    for rid in sorted(declared - referenced):
        fail(errors, f"{where}: {rid} 没有被任何 AC 引用，该需求没有验收锚点")


def _check_ac_references(
    spec_text: str,
    tasks_text: str,
    version_spec_text: str,
    prd_text: str,
    root: pathlib.Path,
    errors: list[str],
    where: str,
    status: str,
) -> None:
    """AC 必须引用真实存在的 requirement，且被至少一个任务的测试路径覆盖。

    `features/README.md` 的 gate v1 规则一直这样写着，但实现里只有 AC 范围上界检查——
    规则存在、执法者不存在。0.1.5 的 AC-001—AC-012 一条测试路径都没写，照样通过。
    """
    known = _declared_ids(spec_text) | _declared_ids(version_spec_text) | _declared_ids(prd_text)
    exits = set(_EXIT_ROW.findall(spec_text))
    coverage = _ac_task_coverage(tasks_text)
    path_required = status in ("ready-for-development", "in-progress", "review", "done")

    for match in _AC_DECL.finditer(_without_fenced_code(spec_text)):
        ac = match.group("ac")
        for rid in _BACKTICKED_ID.findall(match.group("refs")):
            if rid.startswith("E") and rid[1:].isdigit():
                if rid not in exits:
                    fail(errors, f"{where}: {ac} 引用的退出条件 {rid} 不在本 spec 退出条件表")
            elif rid not in known:
                fail(errors, f"{where}: {ac} 引用了未声明的 requirement {rid}")

        blocks = coverage.get(int(ac.split("-")[1]), [])
        if not blocks:
            fail(errors, f"{where}: {ac} 没有任何任务引用，验收无实施锚点")
            continue
        if path_required and not any(_block_has_existing_path(b, root) for b in blocks):
            fail(errors, f"{where}: {ac} 的覆盖任务没有一条 verify 指向仓库内真实存在的路径")


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
    _check_ac_range_completeness(spec_text, tasks_text, errors, where)


# 阶段成果门（features/README.md §阶段成果门）。规则 2026-08-14 引入；此前 created 的
# 里程碑不追溯执法——0.1.4 在规则存在之前就已 done，事后判它违规只会让门禁失去可信度。
OUTCOME_GATE_RULE_DATE = "2026-08-14"
_OUTCOME_GATE_MARK = re.compile(r"`\[成果门:(?P<gate>[A-Za-z0-9][A-Za-z0-9-]*)\]`")
_BARE_OUTCOME_GATE = re.compile(r"`\[成果门\]`")
_PHASE_HEADING = re.compile(r"^###\s+(?P<title>Phase[^\n]*)$", re.M)


def _implementation_section(tasks_text: str) -> str:
    """截出 tasks.md 第 2 节「实现任务」正文，Phase 只在这一节里合法。"""
    start = re.search(r"^##\s+2\.\s+实现任务\s*$", tasks_text, re.M)
    if not start:
        return ""
    rest = tasks_text[start.end() :]
    end = re.search(r"^##\s+\d+\.\s", rest, re.M)
    return rest[: end.start()] if end else rest


def validate_outcome_gates(
    front: dict, tasks_text: str, errors: list[str], where: str, *, today: str | None = None
) -> None:
    """每个 Phase 末尾必须有一项 `[成果门:<ID>]` 任务，且标记格式统一。

    规则本身早就写在 `features/README.md` 与模板里，但一直只靠人工检视执行——
    本仓库的历史（RETROSPECTIVE 循环 1、8）反复证明：只能靠人工发现违反的规则，
    在下一次忙碌的提交里一定会被违反。
    """
    del today  # 保留参数位以便测试注入；当前只依赖 created
    if front.get("gate_version") != 1:
        return
    created = front.get("created", "")
    if not isinstance(created, str) or created < OUTCOME_GATE_RULE_DATE:
        return

    body = _implementation_section(tasks_text)
    if not body:
        return
    if _BARE_OUTCOME_GATE.search(body):
        fail(errors, f"{where}: 成果门标记必须带 ID（`[成果门:R1]`），不接受裸 `[成果门]`")

    headings = list(_PHASE_HEADING.finditer(body))
    if not headings:
        return
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(body)
        block = body[heading.start() : end]
        title = heading.group("title").strip()
        # 只认任务块里的标记：写在散文里的 `[成果门:R1]` 不是一项可勾选、可验证的任务，
        # 把它算作成果门等于让一句话就能满足整个阶段的交付要求。
        tasks_in_phase = _task_blocks(block)
        if not any(_OUTCOME_GATE_MARK.search(b) for _mark, _tid, b in tasks_in_phase):
            fail(errors, f"{where}: 「{title}」没有成果门任务，阶段完成后无用户可打开产物")
            continue
        if not _OUTCOME_GATE_MARK.search(tasks_in_phase[-1][2]):
            fail(errors, f"{where}: 「{title}」的成果门不是本阶段最后一项任务")


# 状态回写任务用显式标记声明，不从自然语言推断。
# 上一版靠正则猜措辞（"推进 done"/"标记为 done"…），两头都不成立：换个说法就能无声
# 绕过（"更新为 done"、"设为 done"），而一句"核对 `done / established` 的前置证据"
# 又会被误判成状态转换。措辞是人写的，标记才是可判定的——与 `[成果门:R1]` 同构。
_STATUS_GATE_MARK = re.compile(r"`\[状态门\]`")
# 没有豁免：所有 gate v1 里程碑都必须有 `[状态门]`。
#
# 前两版都试图从 frontmatter 推断"这个里程碑是不是规则出现前就关闭了"：先按 created
# 早于规则日，后按 `status == done 且 created < 规则日`。两版都错，第二版还是定时炸弹
# ——0.1.5 创建于规则日前，将来一旦转 done 就自动落入豁免，那时删掉标记会静默放行。
# 根因是 **frontmatter 里根本没有"何时关闭"这个事实**，`created` 不是它的代理。
# 与其继续猜，不如取消豁免：0.1.4 的 T405 本来就是状态回写任务，回填标记是如实标注，
# 不是伪造完成。


def validate_status_writeback_is_last(
    front: dict, tasks_text: str, errors: list[str], where: str
) -> None:
    """`[状态门]` 任务必须存在、唯一，且是全文件最后一项。

    否则形成不可满足顺序：gate v1 的 `done` 要求全部任务已勾完，而排在状态回写之后的
    任务又要求先 `done` 才轮到它。这类死锁只有在真正收口那天才会撞上——那时改的人
    通常已经不是写任务清单的人。
    """
    if front.get("gate_version") != 1:
        return
    blocks = _task_blocks(tasks_text)
    if not blocks:
        return
    marked = [
        (index, tid)
        for index, (_mark, tid, block) in enumerate(blocks)
        if _STATUS_GATE_MARK.search(block)
    ]
    if not marked:
        fail(errors, f"{where}: tasks 缺少 `[状态门]` 任务，生命周期回写没有可判定的位置")
        return
    if len(marked) > 1:
        fail(errors, f"{where}: `[状态门]` 必须唯一，实际出现在 {[tid for _i, tid in marked]}")
        return
    index, tid = marked[0]
    if index != len(blocks) - 1:
        fail(
            errors,
            f"{where}: {tid} 是 `[状态门]` 但不是最后一项任务，"
            f"与 gate v1 的 done 门形成不可满足顺序",
        )


def validate_task_id_order(front: dict, tasks_text: str, errors: list[str], where: str) -> None:
    """任务 ID 全文件唯一且按文档顺序递增（模板 §2）。

    编号顺序与执行顺序背离时，"依赖节说先做 T200、但 T200 排在 T202 后面"这类矛盾
    只能靠人读出来；递增是可机器判定的最弱约束，先把它焊死。
    """
    if front.get("gate_version") != 1:
        return
    seen: dict[str, int] = {}
    previous = -1
    previous_id = ""
    for _mark, tid, _block in _task_blocks(tasks_text):
        number = int(tid[1:])
        if tid in seen:
            fail(errors, f"{where}: 任务 ID {tid} 重复出现")
            continue
        seen[tid] = number
        if number <= previous:
            fail(errors, f"{where}: 任务 ID 未按文档顺序递增：{previous_id} 之后出现 {tid}")
        previous, previous_id = number, tid


# 任务声明有加粗（0.1.5、模板 §2）与不加粗（0.1.4）两种写法，历史上都在用。
# 只认加粗形态时，0.1.4 的全部任务对 completion/migration/ID 顺序三个门禁都是隐形的
# ——"done 时 tasks 必须全部完成"在那份文件上从未真正执行过（fail-open）。
_TASK_DECL = re.compile(r"^- \[(?P<mark>[ x])\]\s+(?:\*\*)?(?P<id>T\d+)(?:\*\*)?(?=[\s(`])", re.M)
_MIGRATION_REF = re.compile(r"\[migrated-to:\s*([0-9.]+)/((?:T)\d+)\]")
_OPEN_AC = re.compile(r"^- \[ \]\s+\*\*(AC-\d+)\*\*", re.M)


def _without_fenced_code(md_text: str) -> str:
    """移除 fenced code 内容，避免把格式示例当作真实 task/AC。"""
    lines: list[str] = []
    in_fence = False
    fence_char = ""
    for line in md_text.splitlines(keepends=True):
        stripped = line.lstrip()
        marker = stripped[:3]
        if marker in {"```", "~~~"}:
            if not in_fence:
                in_fence = True
                fence_char = marker
            elif marker == fence_char:
                in_fence = False
                fence_char = ""
            continue
        if not in_fence:
            lines.append(line)
    # 未闭合围栏不能成为隐藏后续真实 task/AC 的旁路；按原文校验可保持 fail closed。
    return md_text if in_fence else "".join(lines)


def _task_blocks(tasks_text: str) -> list[tuple[str, str, str]]:
    """返回 `(mark, task_id, block)`；block 延伸到下一个任务声明。"""
    tasks_text = _without_fenced_code(tasks_text)
    matches = list(_TASK_DECL.finditer(tasks_text))
    out = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(tasks_text)
        out.append((match.group("mark"), match.group("id"), tasks_text[match.start() : end]))
    return out


def validate_completion_state(
    mid: str,
    front: dict,
    spec_text: str,
    tasks_text: str,
    all_ids: dict[str, tuple[pathlib.Path, dict]],
    errors: list[str],
) -> None:
    """done 必须真实完成；legacy 开放任务只能逐项迁移，不能伪勾。"""
    if front.get("status") != "done":
        return

    where = f"milestone {mid}"
    open_tasks = [(tid, block) for mark, tid, block in _task_blocks(tasks_text) if mark == " "]
    if front.get("gate_version") == 1:
        if open_tasks:
            fail(
                errors, f"{where}: gate v1 status=done 但 tasks 未完成 {[x[0] for x in open_tasks]}"
            )
        open_acs = _OPEN_AC.findall(_without_fenced_code(spec_text))
        if open_acs:
            fail(errors, f"{where}: gate v1 status=done 但 AC 未完成 {open_acs}")
        return

    if not open_tasks:
        return
    target_mid = front.get("legacy_open_tasks_migrated_to")
    if not target_mid:
        fail(errors, f"{where}: legacy done 含未完成任务但缺 legacy_open_tasks_migrated_to")
        return
    if target_mid not in all_ids:
        fail(errors, f"{where}: legacy 迁移目标 {target_mid!r} 不存在")
        return

    target_dir = all_ids[target_mid][0]
    target_tasks_path = target_dir / "tasks.md"
    if not target_tasks_path.is_file():
        fail(errors, f"{where}: legacy 迁移目标 {target_mid} 缺 tasks.md")
        return
    target_ids = {tid for _mark, tid, _block in _task_blocks(target_tasks_path.read_text("utf-8"))}
    used_targets: set[str] = set()
    for source_tid, block in open_tasks:
        refs = _MIGRATION_REF.findall(block)
        if len(refs) != 1:
            fail(errors, f"{where}: {source_tid} 必须恰有一个 [migrated-to: milestone/task] 映射")
            continue
        mapped_mid, mapped_tid = refs[0]
        if mapped_mid != target_mid:
            fail(errors, f"{where}: {source_tid} 映射到 {mapped_mid}，与声明目标 {target_mid} 不同")
        if mapped_tid not in target_ids:
            fail(errors, f"{where}: {source_tid} 映射到不存在的 {target_mid}/{mapped_tid}")
        target_key = f"{mapped_mid}/{mapped_tid}"
        if target_key in used_targets:
            fail(errors, f"{where}: 多个遗留任务重复映射到 {target_key}")
        used_targets.add(target_key)


# --------------------------------------------------------------------------- #
# 统一入口
# --------------------------------------------------------------------------- #


def validate_versions(
    features_dir: pathlib.Path,
    root: pathlib.Path,
    errors: list[str],
) -> None:
    """校验每个 version-spec 的元数据与状态转换（§3.1/§4.3）。"""
    for vdir in discover_versions(features_dir):
        spec_path = vdir / "spec.md"
        where = f"version {vdir.name}"
        front = parse_frontmatter(spec_path.read_text(encoding="utf-8"))
        validate_frontmatter_meta(front, errors, where)
        validate_research_claim(front, root, errors, where, is_version=True)
        if front.get("kind") != "version-spec":
            fail(errors, f"{where}: kind 必须为 version-spec")
        if front.get("gate_version") not in (None, 0):
            fail(errors, f"{where}: version-spec 不应有 gate_version")
        if front.get("status") == "done":
            # 版本 done 必须关联 release、closed_at 与全部里程碑完成证据（§5）。
            rel = root / "docs" / "features" / "releases" / f"{front.get('version')}.md"
            if not rel.is_file():
                fail(errors, f"{where}: status=done 但缺 release {rel.name}")
                continue
            release_text = rel.read_text(encoding="utf-8")
            release_front = parse_frontmatter(release_text)
            closed_at = release_front.get("closed_at")
            if not closed_at:
                fail(errors, f"{where}: release 缺结构化 closed_at 字段值")
            if release_front.get("version") not in (None, front.get("version")):
                fail(errors, f"{where}: release frontmatter version 与版本根不一致")
            for mdir in discover_milestones(vdir):
                mfront = parse_frontmatter((mdir / "spec.md").read_text(encoding="utf-8"))
                if mfront.get("status") != "done":
                    fail(errors, f"{where}: status=done 但里程碑 {mfront.get('id')} 未 done")


def check_ownership_index(
    features_dir: pathlib.Path,
    root: pathlib.Path,
    errors: list[str],
) -> None:
    """校验 docs/README.md 所有权索引与跨层级所有权漂移（§4.3 item 6）。

    覆盖规则：
    - 索引文件本身存在，且其链接有效、留在仓库边界内；
    - README/CLAUDE/各版本 README 不得声明与 spec frontmatter 不同的当前状态
      （§2.6：派生入口不得成为第二份状态声明）；
    - 里程碑 design.md 不得重新定义全局不变量（属 contracts/architecture 所有权，
      §2.6：Feature design 不得重新定义全局不变量）。
    """
    readme = root / "docs" / "README.md"
    if not readme.is_file():
        fail(errors, "缺 docs/README.md 所有权索引")
        return
    readme_text = readme.read_text(encoding="utf-8")
    check_markdown_links(readme_text, readme.parent, errors, "docs/README")
    check_links_out_of_repo(readme_text, readme.parent, root, errors, "docs/README")

    # 跨层级状态漂移：派生入口（CLAUDE、各版本 README）不得声明与 spec 相悖的状态。
    authoritative = _authoritative_status(root, features_dir)
    derived = [root / "CLAUDE.md"]
    derived += [vdir / "README.md" for vdir in discover_versions(features_dir)]
    for p in derived:
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        status_alt = r"(done|in-progress|ready-for-development|review|draft)"
        for mid, status in authoritative.items():
            m = re.search(rf"{re.escape(mid)}\s*[|:]\s*{status_alt}\b", text)
            if m and m.group(1) != status:
                where = f"{p.name}: 声明 {mid}={m.group(1)}"
                fail(errors, f"{where}，与 spec frontmatter {status} 不一致")

    # 跨层级真相源：里程碑 design.md 不得重新定义 contracts/architecture 拥有的全局不变量。
    check_global_invariant_ownership(features_dir, errors)
    # architecture 不得复制字段级合同 / 重定义全局不变量（§2.6）。
    check_architecture_contract_copy(root, errors)


# 全局不变量指纹：出现在里程碑 design.md 即视为「重新定义」而非「引用」。
_GLOBAL_INVARIANT_MARKERS = ("C1", "C2")

# C1/C2 定义式的可判定语法：同一行内 marker 后出现方程运算符（=、≡、Σ）。
# 不用固定 token 列表（会漏判通用方程），也不跨行 lookahead（会误吞下一行普通描述）。
_INVARIANT_DEFINITION_OPERATORS = ("=", "≡", "Σ")


def _contains_invariant_definition(text: str, marker: str) -> bool:
    """判断 `marker`（C1/C2）是否为定义式而非引用。

    可判定规则：`C1:`/`C2:` 之后**同一行**出现方程运算符（`=`/`≡`/`Σ`）即视为定义式；
    引用（`C1: 见 docs/contracts/…`、`C1/C2 见…`）同一行无运算符，故放行。不跨行
    采样，因此下一行的普通字段描述不会误归到该 marker。
    """
    for m in re.finditer(rf"{re.escape(marker)}\s*:", text):
        line_end = text.find("\n", m.end())
        if line_end < 0:
            line_end = len(text)
        tail = text[m.end() : line_end]
        if any(op in tail for op in _INVARIANT_DEFINITION_OPERATORS):
            return True
    return False


def check_global_invariant_ownership(
    features_dir: pathlib.Path,
    errors: list[str],
) -> None:
    """里程碑 design.md 不得重新定义全局不变量（§2.6）。

    版本根 design.md 是共享技术设计、可陈述不变量；里程碑级 design.md 若自行定义
    C1/C2 即视为跨层级真相源漂移（这些归 contracts/architecture 所有）。
    """
    for vdir in discover_versions(features_dir):
        for mdir in discover_milestones(vdir):
            design = mdir / "design.md"
            if not design.is_file():
                continue
            text = design.read_text(encoding="utf-8")
            for marker in _GLOBAL_INVARIANT_MARKERS:
                if _contains_invariant_definition(text, marker):
                    where = f"{mdir.name} design.md"
                    owner = "（属 contracts/architecture）"
                    fail(errors, f"{where}: 重新定义全局不变量 {marker}{owner}")


def check_architecture_contract_copy(root: pathlib.Path, errors: list[str]) -> None:
    """architecture 不得复制字段级合同或重定义全局不变量（§2.6）。

    字段级合同（如 C1/C2 守恒方程）归 `docs/contracts/` 唯一所有。architecture 只能
    *引用*（如「守恒以 C1/C2 整数精确断言」或「C1: 见 docs/contracts/…」），不得以
    定义式（`C1: Σ position_units ≡ 0` 这类带守恒方程内容）复制。本检查对
    `docs/market-game-sim-architecture.md` 生效。
    """
    arch = root / "docs" / "market-game-sim-architecture.md"
    if not arch.is_file():
        return
    text = arch.read_text(encoding="utf-8")
    for marker in _GLOBAL_INVARIANT_MARKERS:
        if _contains_invariant_definition(text, marker):
            owner = "（属 docs/contracts/）"
            fail(errors, f"architecture: 复制字段级合同/重定义不变量 {marker}{owner}")


def _authoritative_status(root: pathlib.Path, features_dir: pathlib.Path) -> dict[str, str]:
    """收集版本根与各里程碑 spec frontmatter 的权威状态。"""
    out: dict[str, str] = {}
    for vdir in discover_versions(features_dir):
        front = parse_frontmatter((vdir / "spec.md").read_text(encoding="utf-8"))
        if front.get("status"):
            out[vdir.name] = front["status"]
        for mdir in discover_milestones(vdir):
            mfront = parse_frontmatter((mdir / "spec.md").read_text(encoding="utf-8"))
            if mfront.get("status"):
                out[mfront.get("id")] = mfront["status"]
    return out


def check_docs_links(
    root: pathlib.Path,
    errors: list[str],
) -> None:
    """遍历维护中文档，校验相对链接存在且留在仓库边界内。"""
    skip = {
        "conversations",
        ".git",
        "__pycache__",
        ".claude",
        ".code-review-graph",
        ".sisyphus",
        ".pytest_cache",
        ".ruff_cache",
        "data",
    }
    for p in root.rglob("*.md"):
        rel = p.relative_to(root)
        if any(part in skip for part in rel.parts):
            continue
        text = p.read_text(encoding="utf-8")
        check_markdown_links(text, p.parent, errors, str(rel))
        check_links_out_of_repo(text, p.parent, root, errors, str(rel))


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
    validate_versions(features_dir, root, errors)
    check_ownership_index(features_dir, root, errors)
    check_docs_links(root, errors)
    validate_preregistrations(root, errors)

    for mid, (mdir, front) in all_ids.items():
        where = f"milestone {mid}"
        validate_frontmatter_meta(front, errors, where)
        validate_research_claim(front, root, errors, where)
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
            version_spec = mdir.parent / "spec.md"
            prd = root / "docs" / "market-game-sim-prd.md"
            _check_ac_references(
                spec_text,
                tasks_text,
                version_spec.read_text(encoding="utf-8") if version_spec.is_file() else "",
                prd.read_text(encoding="utf-8") if prd.is_file() else "",
                root,
                errors,
                where,
                front.get("status", ""),
            )
            _check_requirement_ac_coverage(front, spec_text, errors, where)

        validate_completion_state(mid, front, spec_text, tasks_text, all_ids, errors)
        validate_outcome_gates(front, tasks_text, errors, where)
        validate_task_id_order(front, tasks_text, errors, where)
        validate_status_writeback_is_last(front, tasks_text, errors, where)

        # 状态唯一性：design/tasks 独立检查，不依赖 design 存在
        check_status_uniqueness(design_text, tasks_text, errors, where)


# --------------------------------------------------------------------------- #
# 预注册结构：模板必填项 → 真实预注册产物
# --------------------------------------------------------------------------- #

# 预注册必填项的稳定短标签。**不从模板正文推断**——模板是散文，措辞会改；这里用显式
# 闭集，并同时校验模板自己仍然覆盖这八项，让两边漂移时立刻报错而不是一边悄悄失效。
PREREG_REQUIRED_ITEMS = (
    "处理因子的水平取值",
    "估计量定义",
    "指标定义与判据",
    "样本量与功效",
    "seed plan",
    "停止规则",
    "多重比较",
    "校准区",
)
PREREG_TEMPLATE = "docs/experiments/experiment-template.md"


def validate_preregistrations(root: pathlib.Path, errors: list[str]) -> None:
    """真实预注册产物必须覆盖模板声明的八项必填内容。

    预注册的价值全在"看到结果之前写定"，因此漏项不是格式问题：少写一条停止规则，
    "什么时候停止收样"就变成看着结果决定的——那和没有预注册没有区别。文件不存在时
    本校验静默通过（T202 尚未执行），但缺项一旦出现必须当场失败。
    """
    template_path = root / PREREG_TEMPLATE
    if template_path.is_file():
        template = template_path.read_text(encoding="utf-8")
        missing = [item for item in PREREG_REQUIRED_ITEMS if item not in template]
        if missing:
            fail(errors, f"{PREREG_TEMPLATE}: 必填清单缺失 {missing}，模板与校验器已漂移")

    experiments = root / "docs" / "experiments"
    if not experiments.is_dir():
        return
    for path in sorted(experiments.glob("*preregistration*.md")):
        text = path.read_text(encoding="utf-8")
        missing = [item for item in PREREG_REQUIRED_ITEMS if item not in text]
        if missing:
            rel = path.relative_to(root).as_posix()
            fail(errors, f"{rel}: 预注册缺少必填项 {missing}")
