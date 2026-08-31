"""规格生命周期校验：`tools/spec_validation.py` / `validate_spec_lifecycle.py` 的 pytest 入口。

与 `test_contract_sources.py` 同一思路：**重点是负向变异测试**。只断言「当前仓库
通过」无法证明校验器在挡任何东西——删掉一段校验逻辑，happy-path 测试仍然全绿。

因此下面每个 `mutate_*` 都**先破坏一处输入，再断言校验器给出预期错误**。新增校验
规则时应同时新增一条变异，否则那条规则等于没有被测试。
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC_VALIDATION = ROOT / "tools" / "spec_validation.py"
LIFECYCLE = ROOT / "tools" / "validate_spec_lifecycle.py"


def _load_spec_validation():
    spec = importlib.util.spec_from_file_location("spec_validation", SPEC_VALIDATION)
    assert spec and spec.loader, f"无法加载 {SPEC_VALIDATION}"
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(SPEC_VALIDATION)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def sv():
    return _load_spec_validation()


# --------------------------------------------------------------------------- #
# 正向：当前仓库自洽
# --------------------------------------------------------------------------- #


def test_repository_lifecycle_consistent(sv):
    """当前仓库的规格生命周期自洽——CLI 入口返回 0。"""
    errors: list[str] = []
    sv.validate_spec_lifecycle(ROOT / "docs" / "features", ROOT, errors)
    assert errors == []


# --------------------------------------------------------------------------- #
# frontmatter 解析
# --------------------------------------------------------------------------- #


def test_parse_frontmatter_basic(sv):
    text = (
        "---\nkind: milestone\nid: 0.1.1\nstatus: done\ngate_version: 0\n"
        "prerequisites:\n  - 0.1.1\n---\n# body"
    )
    front = sv.parse_frontmatter(text)
    assert front["kind"] == "milestone"
    assert front["status"] == "done"
    assert front["gate_version"] == 0
    assert front["prerequisites"] == ["0.1.1"]


def test_parse_frontmatter_missing(sv):
    assert sv.parse_frontmatter("# no frontmatter") == {}


def test_parse_frontmatter_inline_list(sv):
    text = "---\nkind: milestone\nprerequisites: [0.1.1, 0.1.2]\n---\n"
    front = sv.parse_frontmatter(text)
    assert front["prerequisites"] == ["0.1.1", "0.1.2"]


# --------------------------------------------------------------------------- #
# 元数据变异
# --------------------------------------------------------------------------- #


def test_invalid_status(sv):
    errors: list[str] = []
    sv.validate_frontmatter_meta(
        {
            "kind": "milestone",
            "id": "0.1.5",
            "version": "0.1",
            "status": "banana",
            "gate_version": 1,
        },
        errors,
        "x",
    )
    assert any("status" in e for e in errors)


def test_invalid_kind(sv):
    errors: list[str] = []
    sv.validate_frontmatter_meta(
        {"kind": "weird", "id": "x", "version": "0.1", "status": "draft", "gate_version": 1},
        errors,
        "x",
    )
    assert any("kind" in e for e in errors)


def test_gate0_new_milestone_fails(sv):
    errors: list[str] = []
    sv.validate_frontmatter_meta(
        {
            "kind": "milestone",
            "id": "0.1.5",
            "version": "0.1",
            "status": "draft",
            "gate_version": 0,
            "created": "2026-08-10",
        },
        errors,
        "x",
    )
    assert any("gate_version 0" in e for e in errors)


def test_gate_missing(sv):
    errors: list[str] = []
    sv.validate_frontmatter_meta(
        {"kind": "milestone", "id": "0.1.5", "version": "0.1", "status": "draft"}, errors, "x"
    )
    assert any("gate_version" in e for e in errors)


def test_research_claim_status_required_and_closed_enum(sv):
    errors: list[str] = []
    sv.validate_frontmatter_meta(
        {
            "kind": "milestone",
            "id": "0.1.5",
            "version": "0.1",
            "status": "draft",
            "research_claim_status": "maybe",
            "gate_version": 1,
        },
        errors,
        "x",
    )
    assert any("research_claim_status" in e and "非法" in e for e in errors)


def test_missing_research_claim_status_fails(sv):
    errors: list[str] = []
    sv.validate_frontmatter_meta(
        {
            "kind": "milestone",
            "id": "0.1.5",
            "version": "0.1",
            "status": "draft",
            "gate_version": 1,
        },
        errors,
        "x",
    )
    assert any("research_claim_status=None" in e for e in errors)


def test_established_requires_done_formal_evidence(sv, tmp_path):
    errors: list[str] = []
    sv.validate_research_claim(
        {
            "status": "review",
            "research_claim_status": "established",
            "evidence_class": "engineering-demonstration",
        },
        tmp_path,
        errors,
        "x",
    )
    assert any("status 不是 done" in e for e in errors)
    assert any("formal-research" in e for e in errors)
    assert any("research_evidence" in e for e in errors)


def test_established_with_repository_evidence_passes(sv, tmp_path):
    evidence = tmp_path / "docs" / "experiments" / "evidence.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_text(
        '{"research_claim_eligibility":"eligible",'
        '"experimental_validity":{"status":"informative"}}',
        encoding="utf-8",
    )
    errors: list[str] = []
    sv.validate_research_claim(
        {
            "status": "done",
            "research_claim_status": "established",
            "evidence_class": "formal-research",
            "research_evidence": ["docs/experiments/evidence.json"],
        },
        tmp_path,
        errors,
        "x",
    )
    assert errors == []


@pytest.mark.parametrize(
    "payload",
    [
        {
            "research_claim_eligibility": "ineligible",
            "experimental_validity": {"status": "informative"},
        },
        {
            "research_claim_eligibility": "eligible",
            "experimental_validity": {"status": "degenerate"},
        },
    ],
)
def test_established_rejects_ineligible_or_degenerate_evidence(sv, tmp_path, payload):
    evidence = tmp_path / "docs" / "experiments" / "evidence.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_text(json.dumps(payload), encoding="utf-8")
    errors: list[str] = []
    sv.validate_research_claim(
        {
            "status": "done",
            "research_claim_status": "established",
            "evidence_class": "formal-research",
            "research_evidence": ["docs/experiments/evidence.json"],
        },
        tmp_path,
        errors,
        "x",
    )
    assert errors


@pytest.mark.parametrize(
    "field",
    ["kind", "status", "research_claim_status", "evidence_class", "research_claim_required"],
)
def test_empty_frontmatter_value_is_reported_not_crashed(sv, field):
    """`key:`（空值）在 parse_frontmatter 里是 `[]`，闭集判定不得抛 TypeError。

    校验器崩溃与校验放行同样糟：CI 只会打出堆栈，看的人得先判断"是校验器坏了还是
    规格写错了"。这条锁定所有闭集字段都走 in_enum，报错而不是崩。
    """
    text = (
        '---\nkind: milestone\nid: 0.1.5\nversion: "0.1"\nstatus: draft\n'
        "research_claim_status: not-established\ngate_version: 1\n"
        f"{field}:\n---\n# x\n"
    )
    front = sv.parse_frontmatter(text)
    assert front[field] == [], "前提失效：空值不再解析为空列表，本测试需重写"
    errors: list[str] = []
    sv.validate_frontmatter_meta(front, errors, "x")
    assert any(field in e and "非法" in e for e in errors)


@pytest.mark.parametrize("value", ["True", "yes", "TRUE", "1"])
def test_research_claim_required_rejects_non_canonical_boolean(sv, value):
    """`parse_frontmatter` 只产字符串：非闭集写法必须报错，不能静默当成 false。

    这一条挡的是 fail-open——`research_claim_required: True` 曾经能通过元数据校验，
    然后让 `status=done` 时的研究声明门禁整条消失，且没有任何提示。
    """
    errors: list[str] = []
    sv.validate_frontmatter_meta(
        {
            "kind": "milestone",
            "id": "0.1.5",
            "version": "0.1",
            "status": "draft",
            "research_claim_status": "not-established",
            "research_claim_required": value,
            "gate_version": 1,
        },
        errors,
        "x",
    )
    assert any("research_claim_required" in e and "非法" in e for e in errors)


@pytest.mark.parametrize("value", ["true", "false"])
def test_research_claim_required_accepts_canonical_boolean(sv, value):
    errors: list[str] = []
    sv.validate_frontmatter_meta(
        {
            "kind": "milestone",
            "id": "0.1.5",
            "version": "0.1",
            "status": "draft",
            "research_claim_status": "not-established",
            "research_claim_required": value,
            "gate_version": 1,
        },
        errors,
        "x",
    )
    assert errors == []


def test_misspelled_research_claim_required_does_not_silently_disable_gate(sv, tmp_path):
    """key 拼错时门禁必须仍然拦住 done：拼写错误不得成为放行通道。

    拼错的 key 无法被闭集校验发现（校验器不知道它本该叫什么），因此第二道防线是
    版本根 `status=done` 时 `research_claim_status` 不得仍为 not-established——
    本测试锁定的正是这道防线在 required 失效时仍然生效。
    """
    errors: list[str] = []
    sv.validate_research_claim(
        {
            "status": "done",
            "research_claim_status": "not-established",
            "research_claim_requred": "true",  # 故意拼错
        },
        tmp_path,
        errors,
        "version v0.1",
        is_version=True,
    )
    assert any("not-established" in e for e in errors)


def test_experiment_preview_cannot_establish_research_claim(sv, tmp_path):
    evidence = tmp_path / "docs" / "experiments" / "evidence.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_text("{}", encoding="utf-8")
    errors: list[str] = []
    sv.validate_research_claim(
        {
            "status": "done",
            "research_claim_status": "established",
            "evidence_class": "experiment-preview",
            "research_evidence": ["docs/experiments/evidence.json"],
        },
        tmp_path,
        errors,
        "milestone 0.1.5",
    )
    assert any("experiment-preview" in e for e in errors)


def test_experiment_preview_is_a_legal_evidence_class(sv):
    """预览是里程碑级证据类别（PRD §15 成果口径），只是不能签收研究声明。"""
    errors: list[str] = []
    sv.validate_frontmatter_meta(
        {
            "kind": "milestone",
            "id": "0.1.5",
            "version": "0.1",
            "status": "in-progress",
            "research_claim_status": "not-established",
            "evidence_class": "experiment-preview",
            "gate_version": 1,
        },
        errors,
        "x",
    )
    assert errors == []


def test_research_claim_required_conflicts_with_not_applicable_before_done(sv, tmp_path):
    errors: list[str] = []
    sv.validate_research_claim(
        {
            "status": "draft",
            "research_claim_status": "not-applicable",
            "research_claim_required": "true",
        },
        tmp_path,
        errors,
        "milestone 0.1.5",
    )
    assert any("矛盾" in e for e in errors)


def test_research_spec_cannot_close_as_not_applicable_when_claim_required(sv, tmp_path):
    errors: list[str] = []
    sv.validate_research_claim(
        {
            "status": "done",
            "research_claim_status": "not-applicable",
            "research_claim_required": "true",
        },
        tmp_path,
        errors,
        "milestone 0.1.5",
    )
    assert any("必须 established" in e for e in errors)


# --------------------------------------------------------------------------- #
# 状态唯一性
# --------------------------------------------------------------------------- #


def test_design_declares_status_fails(sv):
    errors: list[str] = []
    design = "---\nkind: milestone\nstatus: done\n---\n"
    sv.check_status_uniqueness(design, "", errors, "m")
    assert any("design.md" in e and "status" in e for e in errors)


def test_design_no_status_passes(sv):
    errors: list[str] = []
    sv.check_status_uniqueness("# no frontmatter", "# no frontmatter", errors, "m")
    assert errors == []


def test_tasks_declares_research_claim_status_fails(sv):
    errors: list[str] = []
    tasks = "---\nresearch_claim_status: established\n---\n"
    sv.check_status_uniqueness("", tasks, errors, "m")
    assert any("tasks.md" in e and "research_claim_status" in e for e in errors)


# --------------------------------------------------------------------------- #
# prerequisites
# --------------------------------------------------------------------------- #


def test_prerequisite_missing(sv):
    all_ids = {
        "0.1.1": (pathlib.Path("a"), {"prerequisites": []}),
        "0.1.2": (pathlib.Path("b"), {"prerequisites": ["0.1.9"]}),
    }
    errors: list[str] = []
    sv.validate_prerequisites(all_ids, errors)
    assert any("0.1.9" in e and "不存在" in e for e in errors)


def test_prerequisite_not_done_blocks_implementation(sv):
    """SOP §3 状态门：前置未 done 时，自身不得进入 in-progress/review/done。"""
    all_ids = {
        "0.1.3": (pathlib.Path("a"), {"prerequisites": [], "status": "in-progress"}),
        "0.1.4": (pathlib.Path("b"), {"prerequisites": ["0.1.3"], "status": "in-progress"}),
    }
    errors: list[str] = []
    sv.validate_prerequisites(all_ids, errors)
    assert any("0.1.4" in e and "未 done" in e for e in errors)


def test_prerequisite_done_allows_implementation(sv):
    """正向对照：前置已 done 时，自身进入 in-progress 不应被拦。"""
    all_ids = {
        "0.1.3": (pathlib.Path("a"), {"prerequisites": [], "status": "done"}),
        "0.1.4": (pathlib.Path("b"), {"prerequisites": ["0.1.3"], "status": "in-progress"}),
    }
    errors: list[str] = []
    sv.validate_prerequisites(all_ids, errors)
    assert errors == []


def test_prerequisite_not_done_allows_ready_for_development(sv):
    """正向对照：前置未 done 时，自身仍可停在 ready-for-development（文档先行）。"""
    all_ids = {
        "0.1.3": (pathlib.Path("a"), {"prerequisites": [], "status": "in-progress"}),
        "0.1.4": (
            pathlib.Path("b"),
            {"prerequisites": ["0.1.3"], "status": "ready-for-development"},
        ),
    }
    errors: list[str] = []
    sv.validate_prerequisites(all_ids, errors)
    assert errors == []


def test_prerequisite_cycle(sv):
    all_ids = {
        "0.1.1": (pathlib.Path("a"), {"prerequisites": ["0.1.2"]}),
        "0.1.2": (pathlib.Path("b"), {"prerequisites": ["0.1.1"]}),
    }
    errors: list[str] = []
    sv.validate_prerequisites(all_ids, errors)
    assert any("环" in e for e in errors)


def test_prerequisite_free_text_fails(sv):
    all_ids = {"0.1.1": (pathlib.Path("a"), {"prerequisites": ["按需"]})}
    errors: list[str] = []
    sv.validate_prerequisites(all_ids, errors)
    assert any("结构化" in e for e in errors)


# --------------------------------------------------------------------------- #
# 链接
# --------------------------------------------------------------------------- #


def test_link_missing_file(sv, tmp_path):
    (tmp_path / "doc.md").write_text("[x](missing.md)", encoding="utf-8")
    errors: list[str] = []
    sv.check_markdown_links(
        (tmp_path / "doc.md").read_text(encoding="utf-8"), tmp_path, errors, "doc"
    )
    assert any("不存在" in e for e in errors)


def test_link_is_directory(sv, tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "doc.md").write_text("[x](sub)", encoding="utf-8")
    errors: list[str] = []
    sv.check_markdown_links(
        (tmp_path / "doc.md").read_text(encoding="utf-8"), tmp_path, errors, "doc"
    )
    assert any("目录" in e for e in errors)


def test_link_escape_out_of_repo(sv, tmp_path, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    (outside / "secret.md").write_text("x", encoding="utf-8")
    repo = tmp_path
    (repo / "doc.md").write_text(f"[x]({outside / 'secret.md'})", encoding="utf-8")
    errors: list[str] = []
    sv.check_links_out_of_repo(
        (repo / "doc.md").read_text(encoding="utf-8"), repo, repo, errors, "doc"
    )
    assert any("逃逸" in e for e in errors)


# --------------------------------------------------------------------------- #
# traceability owner/exit
# --------------------------------------------------------------------------- #


def test_owner_exit_missing(sv, tmp_path):
    ms = tmp_path / "docs" / "features" / "0.1" / "0.1.1-minimal-kernel"
    ms.mkdir(parents=True)
    (ms / "spec.md").write_text("# m\n\n| E1 | 条件 |\n", encoding="utf-8")
    d = {
        "statuses": ["owned", "deferred", "removed"],
        "requirements": {
            "FR-001": {"status": "owned", "owners": [{"milestone": "0.1.1", "exits": ["E9"]}]}
        },
    }
    milestones = {"0.1.1": "docs/features/0.1/0.1.1-minimal-kernel"}
    errors: list[str] = []
    sv.validate_owners("FR-001", d["requirements"]["FR-001"], milestones, errors, tmp_path)
    assert any("E9" in e for e in errors)


def test_owner_no_owners_fails(sv):
    d = {
        "milestones": {},
        "tracked_id_families": ["FR"],
        "statuses": ["owned"],
        "requirements": {"FR-001": {"status": "owned", "owners": []}},
    }
    errors: list[str] = []
    sv.validate_trace_data(d, "", errors, pathlib.Path("."))
    assert any("owners 为空" in e for e in errors)


def test_owner_scope_overlap_fails(sv):
    owners = [
        {"milestone": "0.1.1", "exits": ["E1"], "scope": "同"},
        {"milestone": "0.1.2", "exits": ["E2"], "scope": "同"},
    ]
    errors: list[str] = []
    sv.validate_owners(
        "FR-001", {"owners": owners}, {"0.1.1": "a", "0.1.2": "b"}, errors, pathlib.Path(".")
    )
    assert any("scope 重复" in e for e in errors)


# --------------------------------------------------------------------------- #
# gate v1：章节结构、Q/DQ
# --------------------------------------------------------------------------- #


_SPEC_TEMPLATE = (
    "## 0. 来源与意图\n## 1. 问题、目标与非目标\n## 2. 用户场景\n"
    "## 3. 范围与边界\n## 4. 需求\n## 5. 生命周期与不变量\n## 6. 成功与验收\n"
    "## 7. 测试、依赖与决策\n## 8. 待确认问题\n无"
)


def test_gate1_missing_section(sv):
    errors: list[str] = []
    spec = "## 0. 来源与意图\n## 1. 问题、目标与非目标\n"  # 缺其余章节
    sv._check_sections(spec, sv.SPEC_SECTIONS, errors, "spec")
    assert any("缺固定顶层章节" in e for e in errors)


def test_gate1_all_sections_present(sv):
    errors: list[str] = []
    sv._check_sections(_SPEC_TEMPLATE, sv.SPEC_SECTIONS, errors, "spec")
    assert errors == []


def test_ac_range_completeness_rejects_stale_upper_bound(sv):
    """acceptance-mapping-gap 回归（R014-D004）：spec 新增 AC 后 tasks 范围未跟着扩大必报。"""
    spec_text = "- [ ] **AC-005** (`X`): 一条\n- [ ] **AC-006** (`Y`): 新增一条\n"
    tasks_text = "- [ ] T404 (`AC-001`—`AC-005`): 运行统一质量门\n"
    errors: list[str] = []
    sv._check_ac_range_completeness(spec_text, tasks_text, errors, "m")
    assert any("AC-006" in e for e in errors)


def test_ac_range_completeness_passes_when_synced(sv):
    """正向对照：tasks 范围已扩大到最新 AC 编号时不报错。"""
    spec_text = "- [ ] **AC-005** (`X`): 一条\n- [ ] **AC-006** (`Y`): 新增一条\n"
    tasks_text = "- [ ] T404 (`AC-001`—`AC-006`): 运行统一质量门\n"
    errors: list[str] = []
    sv._check_ac_range_completeness(spec_text, tasks_text, errors, "m")
    assert errors == []


def test_ac_range_completeness_not_fooled_by_unrelated_mention(sv):
    """round-3 回归（R014-D004 残留）：范围声明本身过期时，即使别的任务单独提过
    新 AC ID（不是范围声明的一部分），门禁仍须报错——不能把「新 ID 在全文任意
    位置出现过」误当作「范围声明已同步」。"""
    spec_text = "- [ ] **AC-005** (`X`): 一条\n- [ ] **AC-006** (`Y`): 新增一条\n"
    tasks_text = (
        "- [ ] T202 (`FR-019`, `AC-006`): 提前引用了新 AC，但这不是范围声明\n"
        "- [ ] T404 (`AC-001`—`AC-005`): 运行统一质量门\n"
    )
    errors: list[str] = []
    sv._check_ac_range_completeness(spec_text, tasks_text, errors, "m")
    assert any("AC-006" in e for e in errors)


def test_t218_does_not_claim_delivery_acceptance_before_t220(sv):
    """R020-C004：R5 尚未生成时，T218/T219 不得提前签收其 AC。"""
    tasks_path = ROOT / "docs" / "features" / "0.1" / "0.1.5-goal-driven-flagship" / "tasks.md"
    blocks = {tid: block for _mark, tid, block in sv._task_blocks(tasks_path.read_text("utf-8"))}
    assert "R5 交付前不得提前签收 `AC-011` / `AC-012`" in blocks["T218"]
    assert "R5 交付验收仍由 T220 独占" in blocks["T219"]
    assert "本任务完成后才允许签收 `AC-011` / `AC-012`" in blocks["T220"]


def test_pending_section_free_text_fails(sv):
    md = "## 8. 待确认问题\n- 这是一个自由文本问题\n"
    errors: list[str] = []
    sv._check_pending_section(md, "待确认问题", "Q", errors, "spec")
    assert any("非规范行" in e for e in errors)


def test_pending_section_none_ok(sv):
    md = "## 8. 待确认问题\n无"
    errors: list[str] = []
    sv._check_pending_section(md, "待确认问题", "Q", errors, "spec")
    assert errors == []


def test_open_question_fails_after_ready(sv):
    md = "## 8. 待确认问题\n- [ ] Q-001: 未关闭的问题"
    errors: list[str] = []
    sv._check_open_questions(md, "待确认问题", "Q", errors, "spec")
    assert any("Q-001" in e for e in errors)


def test_closed_question_ok(sv):
    md = "## 8. 待确认问题\n- [x] Q-001: 已关闭 — 决策：结论"
    errors: list[str] = []
    sv._check_open_questions(md, "待确认问题", "Q", errors, "spec")
    assert errors == []


def test_gate1_done_rejects_open_tasks_and_ac(sv):
    errors: list[str] = []
    sv.validate_completion_state(
        "0.1.5",
        {"status": "done", "gate_version": 1},
        "- [ ] **AC-001** (`FR-001`): pending\n",
        "- [ ] **T001** (`FR-001`): pending\n",
        {},
        errors,
    )
    assert any("tasks 未完成" in e and "T001" in e for e in errors)
    assert any("AC 未完成" in e and "AC-001" in e for e in errors)


def test_gate1_done_ignores_open_task_and_ac_examples_in_fences(sv):
    errors: list[str] = []
    sv.validate_completion_state(
        "0.1.5",
        {"status": "done", "gate_version": 1},
        "```markdown\n- [ ] **AC-001** (`FR-001`): example\n```\n",
        "~~~markdown\n- [ ] **T001** (`FR-001`): example\n~~~\n",
        {},
        errors,
    )
    assert errors == []


def test_gate1_done_unclosed_fence_cannot_hide_open_task(sv):
    errors: list[str] = []
    sv.validate_completion_state(
        "0.1.5",
        {"status": "done", "gate_version": 1},
        "",
        "```markdown\nexample\n- [ ] **T001** (`FR-001`): hidden after unclosed fence\n",
        {},
        errors,
    )
    assert any("tasks 未完成" in e and "T001" in e for e in errors)


def test_legacy_done_open_tasks_require_exact_migration(sv, tmp_path):
    target = tmp_path / "0.1.5-target"
    target.mkdir()
    (target / "tasks.md").write_text(
        "- [ ] **T203** (`FR-001`): replacement\n- [ ] **T204** (`FR-002`): replacement\n",
        encoding="utf-8",
    )
    all_ids = {"0.1.5": (target, {"id": "0.1.5"})}
    errors: list[str] = []
    sv.validate_completion_state(
        "0.1.2",
        {
            "status": "done",
            "gate_version": 0,
            "legacy_open_tasks_migrated_to": "0.1.5",
        },
        "",
        "- [ ] **T404** `[migrated-to: 0.1.5/T203]` old\n"
        "- [ ] **T405** `[migrated-to: 0.1.5/T204]` old\n",
        all_ids,
        errors,
    )
    assert errors == []


def test_legacy_done_rejects_missing_or_duplicate_target(sv, tmp_path):
    target = tmp_path / "0.1.5-target"
    target.mkdir()
    (target / "tasks.md").write_text("- [ ] **T203** (`FR-001`): replacement\n", encoding="utf-8")
    all_ids = {"0.1.5": (target, {"id": "0.1.5"})}
    errors: list[str] = []
    sv.validate_completion_state(
        "0.1.2",
        {
            "status": "done",
            "gate_version": 0,
            "legacy_open_tasks_migrated_to": "0.1.5",
        },
        "",
        "- [ ] **T404** old without mapping\n"
        "- [ ] **T405** `[migrated-to: 0.1.5/T203]` old\n"
        "- [ ] **T406** `[migrated-to: 0.1.5/T203]` old\n",
        all_ids,
        errors,
    )
    assert any("T404" in e and "恰有一个" in e for e in errors)
    assert any("重复映射" in e for e in errors)


# --------------------------------------------------------------------------- #
# AC 引用：requirement 存在性与测试路径
# --------------------------------------------------------------------------- #


_SPEC_HEAD = "## 6. 成功与验收\n\n### 退出条件\n\n| ID | 条件 |\n|---|---|\n| E1 | 条件一。 |\n\n"


def _spec_with_ac(ac_line: str, declarations: str = "- **FR-001**：需求一。\n") -> str:
    return f"## 4. 需求\n\n{declarations}\n{_SPEC_HEAD}### 验收清单\n\n{ac_line}\n"


def test_ac_referencing_undeclared_requirement_fails(sv, tmp_path):
    spec = _spec_with_ac("- [ ] **AC-001** (`FR-999`): 做到某事。")
    tasks = "## 2. 实现任务\n\n- [ ] **T001** (`AC-001`): 实施 — verify: `tools/verify.py`\n"
    errors: list[str] = []
    sv._check_ac_references(spec, tasks, "", "", tmp_path, errors, "m", "draft")
    assert any("AC-001" in e and "FR-999" in e for e in errors)


def test_ac_referencing_version_root_or_prd_id_passes(sv, tmp_path):
    """AC 可以引用版本根 requirement 与 PRD 编号——0.1.4 就是这么写的。"""
    spec = _spec_with_ac("- [ ] **AC-001** (`SC-008`, `PR-018`, `E1`): 做到某事。", "")
    tasks = "## 2. 实现任务\n\n- [ ] **T001** (`AC-001`): 实施 — verify: `tools/verify.py`\n"
    errors: list[str] = []
    sv._check_ac_references(
        spec,
        tasks,
        "- **SC-008**：逐帧一致。\n",
        "- **PR-018**：回放器。\n",
        tmp_path,
        errors,
        "m",
        "draft",
    )
    assert errors == []


def test_ac_referencing_unknown_exit_fails(sv, tmp_path):
    spec = _spec_with_ac("- [ ] **AC-001** (`FR-001`, `E9`): 做到某事。")
    tasks = "## 2. 实现任务\n\n- [ ] **T001** (`AC-001`): 实施 — verify: `tools/verify.py`\n"
    errors: list[str] = []
    sv._check_ac_references(spec, tasks, "", "", tmp_path, errors, "m", "draft")
    assert any("E9" in e and "退出条件" in e for e in errors)


def test_ac_without_any_task_reference_fails(sv, tmp_path):
    spec = _spec_with_ac("- [ ] **AC-001** (`FR-001`): 无人认领。")
    tasks = "## 2. 实现任务\n\n- [ ] **T001** (`FR-001`): 实施 — verify: `tools/verify.py`\n"
    errors: list[str] = []
    sv._check_ac_references(spec, tasks, "", "", tmp_path, errors, "m", "draft")
    assert any("AC-001" in e and "没有任何任务引用" in e for e in errors)


def test_ac_range_declaration_counts_as_coverage(sv, tmp_path):
    spec = _spec_with_ac("- [ ] **AC-001** (`FR-001`): 一。\n- [ ] **AC-002** (`FR-001`): 二。")
    tasks = (
        "## 2. 实现任务\n\n"
        "- [ ] **T001** (`AC-001`—`AC-002`): 统一质量门 — verify: `tools/verify.py`\n"
    )
    errors: list[str] = []
    sv._check_ac_references(spec, tasks, "", "", tmp_path, errors, "m", "draft")
    assert errors == []


def test_missing_test_path_blocks_only_after_draft(sv, tmp_path):
    """draft 阶段允许测试尚不存在；ready-for-development 起必须指向真实路径。"""
    spec = _spec_with_ac("- [ ] **AC-001** (`FR-001`): 做到某事。")
    tasks = "## 2. 实现任务\n\n- [ ] **T001** (`AC-001`): 实施 — verify: `tests/unit/not_yet/`\n"
    draft_errors: list[str] = []
    sv._check_ac_references(spec, tasks, "", "", tmp_path, draft_errors, "m", "draft")
    assert draft_errors == []

    ready_errors: list[str] = []
    sv._check_ac_references(
        spec, tasks, "", "", tmp_path, ready_errors, "m", "ready-for-development"
    )
    assert any("真实存在的路径" in e for e in ready_errors)

    (tmp_path / "tests" / "unit" / "not_yet").mkdir(parents=True)
    fixed_errors: list[str] = []
    sv._check_ac_references(
        spec, tasks, "", "", tmp_path, fixed_errors, "m", "ready-for-development"
    )
    assert fixed_errors == []


def test_markdown_collectors_are_not_silently_empty_on_real_specs(sv):
    """采集器在真实仓库文件上必须真的采到东西。

    循环 9 的 `silent-no-op-gate`：`_TASK_DECL` 曾只认加粗写法，于是 0.1.4 的全部任务
    对三个门禁隐形——全绿、零错误，因为连输入都没采集到。空转比 fail-open 更隐蔽，
    所以每个基于正则的采集器都要有一条"在真实文件上 > 0"的断言，而不是只测构造字符串。
    """
    milestones = sorted((ROOT / "docs" / "features" / "0.1").glob("0.1.*/spec.md"))
    assert milestones, "前提失效：找不到任何里程碑 spec"
    checked = 0
    for spec_path in milestones:
        front = sv.parse_frontmatter(spec_path.read_text(encoding="utf-8"))
        if front.get("gate_version") != 1:
            continue
        checked += 1
        spec_body = sv._without_fenced_code(spec_path.read_text(encoding="utf-8"))
        tasks_text = (spec_path.parent / "tasks.md").read_text(encoding="utf-8")
        where = spec_path.parent.name
        assert sv._task_blocks(tasks_text), f"{where}: 任务采集器采到 0 条"
        assert list(sv._AC_DECL.finditer(spec_body)), f"{where}: AC 采集器采到 0 条"
        assert sv._declared_ids(spec_body), f"{where}: 需求声明采集器采到 0 条"
    assert checked >= 2, "前提失效：gate v1 里程碑少于 2 个，覆盖面不足以证明采集器有效"


def test_declared_requirement_without_ac_fails(sv):
    """IR/DR/TR 这类里程碑本地需求最容易漏——D009 就是一次写下 6 条却一条 AC 都没有。"""
    spec = _spec_with_ac(
        "- [ ] **AC-001** (`FR-001`): 只认领了 FR。",
        "- **FR-001**：需求一。\n- **IR-501**：接口需求。\n- **DR-501**：数据需求。\n",
    )
    errors: list[str] = []
    sv._check_requirement_ac_coverage({"created": "2026-08-15"}, spec, errors, "m")
    assert any("IR-501" in e and "验收锚点" in e for e in errors)
    assert any("DR-501" in e for e in errors)


def test_all_declared_requirements_covered_passes(sv):
    spec = _spec_with_ac(
        "- [ ] **AC-001** (`FR-001`, `IR-501`, `DR-501`): 全部认领。",
        "- **FR-001**：需求一。\n- **IR-501**：接口需求。\n- **DR-501**：数据需求。\n",
    )
    errors: list[str] = []
    sv._check_requirement_ac_coverage({"created": "2026-08-15"}, spec, errors, "m")
    assert errors == []


def test_us_and_sc_are_not_required_to_have_ac(sv):
    """US 用「独立测试」段自证，SC/KR 的验收锚点在版本根，不强制里程碑 AC 覆盖。"""
    spec = _spec_with_ac(
        "- [ ] **AC-001** (`FR-001`): 只认领 FR。",
        "- **FR-001**：需求一。\n- **SC-009**：成功标准。\n\n### US-501：场景\n",
    )
    errors: list[str] = []
    sv._check_requirement_ac_coverage({"created": "2026-08-15"}, spec, errors, "m")
    assert errors == []


def test_ac_coverage_rule_not_applied_before_its_introduction(sv):
    spec = _spec_with_ac(
        "- [ ] **AC-001** (`FR-001`): 只认领 FR。",
        "- **FR-001**：需求一。\n- **TR-001**：事件需求。\n",
    )
    errors: list[str] = []
    sv._check_requirement_ac_coverage({"created": "2026-08-09"}, spec, errors, "m")
    assert errors == []


@pytest.mark.parametrize(
    "decl", ["- [x] **T001** (`FR-001`): 加粗", "- [x] T001 (`FR-001`): 不加粗"]
)
def test_task_declaration_recognised_in_both_written_forms(sv, decl):
    """仓库里加粗与不加粗两种任务写法都在用。

    只认加粗形态时，0.1.4 的全部任务对 completion/migration/ID 顺序三个门禁都是隐形的
    ——`done` 时"tasks 必须全部完成"在那份文件上从未真正执行过。
    """
    blocks = sv._task_blocks(f"## 2. 实现任务\n\n{decl} — verify: `tools/verify.py`\n")
    assert [tid for _mark, tid, _block in blocks] == ["T001"]


def test_gate1_done_with_unchecked_non_bold_task_is_rejected(sv, tmp_path):
    """上一条的直接后果：非加粗未勾任务必须能挡住 gate v1 的 done。"""
    tasks = "## 2. 实现任务\n\n- [ ] T001 (`FR-001`): 还没做 — verify: `tools/verify.py`\n"
    errors: list[str] = []
    sv.validate_completion_state(
        "0.1.9", {"status": "done", "gate_version": 1}, "", tasks, {}, errors
    )
    assert any("tasks 未完成" in e and "T001" in e for e in errors)


# --------------------------------------------------------------------------- #
# 阶段成果门与任务 ID 顺序
# --------------------------------------------------------------------------- #


def _tasks_with_phases(*phases: str) -> str:
    """拼一份只含第 2 节的 tasks.md；phases 逐段给出 Phase 正文。"""
    return "## 2. 实现任务\n\n" + "\n".join(phases) + "\n\n## 3. 验证与验收任务\n"


_GATE_FRONT = {"gate_version": 1, "created": "2026-08-20"}


def test_phase_without_outcome_gate_fails(sv):
    tasks = _tasks_with_phases(
        "### Phase 1：基线\n\n- [ ] **T001** (`FR-001`): 做事 — verify: `tests/a.py`\n",
        "### Phase 2：扩展\n\n- [ ] **T002** (`FR-002`): 又做事 — verify: `tests/b.py`\n",
    )
    errors: list[str] = []
    sv.validate_outcome_gates(_GATE_FRONT, tasks, errors, "m")
    assert any("Phase 2" in e and "成果门" in e for e in errors)
    assert any("Phase 1" in e for e in errors)


def test_every_phase_with_trailing_gate_passes(sv):
    tasks = _tasks_with_phases(
        "### Phase 1：基线\n\n- [ ] **T001** (`FR-001`): 做事 — verify: `tests/a.py`\n"
        "- [ ] **T002** `[成果门:R1]` (`FR-002`): 产出成果包 — verify: `tests/b.py`\n",
        "### Phase 2：扩展\n\n"
        "- [ ] **T003** `[成果门:R2]` (`FR-003`): 产出预览 — verify: `tests/c.py`\n",
    )
    errors: list[str] = []
    sv.validate_outcome_gates(_GATE_FRONT, tasks, errors, "m")
    assert errors == []


def test_outcome_gate_must_be_last_task_in_phase(sv):
    """成果门排在阶段中间等于阶段末尾仍无可展示产物，属于同一个缺陷。"""
    tasks = _tasks_with_phases(
        "### Phase 1：基线\n\n"
        "- [ ] **T001** `[成果门:R1]` (`FR-001`): 产出成果包 — verify: `tests/a.py`\n"
        "- [ ] **T002** (`FR-002`): 收尾 — verify: `tests/b.py`\n",
    )
    errors: list[str] = []
    sv.validate_outcome_gates(_GATE_FRONT, tasks, errors, "m")
    assert any("最后一项" in e for e in errors)


def test_bare_outcome_gate_marker_rejected(sv):
    """`[成果门]` 无 ID：将来按 ID 聚合成果门时会静默漏掉，必须当场拒绝。"""
    tasks = _tasks_with_phases(
        "### Phase 1：基线\n\n- [ ] **T001** `[成果门]` (`FR-001`): 产出 — verify: `tests/a.py`\n",
    )
    errors: list[str] = []
    sv.validate_outcome_gates(_GATE_FRONT, tasks, errors, "m")
    assert any("必须带 ID" in e for e in errors)


def test_prose_outcome_gate_marker_does_not_satisfy_a_phase(sv):
    """散文里提一句 `[成果门:R1]` 不是可勾选、可验证的任务。

    round 2 的变异探测发现：Phase 里一个任务都没有、只在说明文字里出现标记时，门禁
    原本直接放行——一句话就能满足整个阶段的交付要求。
    """
    tasks = _tasks_with_phases(
        "### Phase 1：基线\n\n本阶段产物由 `[成果门:R1]` 覆盖，具体任务见别处。\n",
    )
    errors: list[str] = []
    sv.validate_outcome_gates(_GATE_FRONT, tasks, errors, "m")
    assert any("没有成果门任务" in e for e in errors)


def test_outcome_gate_rule_not_applied_before_its_introduction(sv):
    """规则 2026-08-14 引入，此前 created 的里程碑不追溯执法。"""
    tasks = _tasks_with_phases(
        "### Phase 1：基线\n\n- [ ] **T001** (`FR-001`): 做事 — verify: `tests/a.py`\n",
    )
    errors: list[str] = []
    sv.validate_outcome_gates({"gate_version": 1, "created": "2026-08-09"}, tasks, errors, "m")
    assert errors == []


def test_outcome_gate_ignores_phase_headings_outside_section_two(sv):
    """Phase 只在第 2 节合法；别处出现的同名标题不触发成果门要求。"""
    tasks = (
        "## 2. 实现任务\n\n### Phase 1：基线\n\n"
        "- [ ] **T001** `[成果门:R1]` (`FR-001`): 产出 — verify: `tests/a.py`\n\n"
        "## 4. 依赖与并行关系\n\n### Phase 9：只是叙述\n\n说明文字。\n"
    )
    errors: list[str] = []
    sv.validate_outcome_gates(_GATE_FRONT, tasks, errors, "m")
    assert errors == []


_ACTIVE = {"gate_version": 1, "status": "draft", "created": "2026-08-16"}


@pytest.mark.parametrize(
    "wording",
    [
        "回写验收证据并推进 `done / established`",
        "更新为 done",
        "设为 done",
        "把里程碑标记为 done",
    ],
)
def test_status_gate_before_other_tasks_is_rejected(sv, wording):
    """`done` 要求全部任务勾完，状态门又排在别的任务前面 → 不可满足顺序。

    判定只看 `[状态门]` 标记，与措辞无关：上一版用正则猜自然语言，"更新为 done"、
    "设为 done" 都能无声绕过，而"核对 `done / established` 的前置证据"又会被误报。
    """
    tasks = (
        "## 3. 验证与验收任务\n\n"
        f"- [ ] **T220** `[状态门]` (`FR-026`): {wording} — verify: `x`\n"
        "- [ ] **T221** `[成果门:R5]` (`FR-027`): 生成交付入口 — verify: `y`\n"
    )
    errors: list[str] = []
    sv.validate_status_writeback_is_last(_ACTIVE, tasks, errors, "m")
    assert any("不可满足顺序" in e and "T220" in e for e in errors)


def test_status_gate_as_final_task_passes(sv):
    tasks = (
        "## 3. 验证与验收任务\n\n"
        "- [ ] **T220** `[成果门:R5]` (`FR-027`): 生成交付入口 — verify: `y`\n"
        "- [ ] **T221** `[状态门]` (`FR-026`): 全部勾完后回写并推进 `done / established`"
        " — verify: `x`\n"
    )
    errors: list[str] = []
    sv.validate_status_writeback_is_last(_ACTIVE, tasks, errors, "m")
    assert errors == []


def test_prose_about_done_no_longer_false_positives(sv):
    """只提到 `done / established` 但没标 `[状态门]` 的任务不该被判成状态转换。"""
    tasks = (
        "## 3. 验证与验收任务\n\n"
        "- [ ] **T220** (`FR-026`): 核对 `done / established` 的前置证据 — verify: `x`\n"
        "- [ ] **T221** `[状态门]` (`FR-026`): 回写并推进 — verify: `y`\n"
    )
    errors: list[str] = []
    sv.validate_status_writeback_is_last(_ACTIVE, tasks, errors, "m")
    assert errors == []


@pytest.mark.parametrize("status", ["draft", "in-progress", "review", "done"])
@pytest.mark.parametrize("created", ["2026-08-09", "2026-08-14", "2026-08-20"])
def test_missing_status_gate_is_rejected_regardless_of_status_or_created(sv, status, created):
    """缺 `[状态门]` 一律失败——不按 created 或 status 推断"是否规则前已关闭"。

    前两版豁免都栽在这里：`created` 不是"何时关闭"的代理。第二版
    （`status == done and created < 规则日`）更是定时炸弹——0.1.5 创建于规则日前，
    将来转 `done` 时会自动落入豁免，那一刻删掉标记就静默放行。
    """
    tasks = "## 3.\n\n- [x] **T404** (`FR-019`): 回写状态 — verify: `x`\n"
    errors: list[str] = []
    sv.validate_status_writeback_is_last(
        {"gate_version": 1, "status": status, "created": created}, tasks, errors, "m"
    )
    assert any("缺少 `[状态门]`" in e for e in errors)


def test_duplicate_status_gate_is_rejected(sv):
    tasks = (
        "## 3.\n\n"
        "- [ ] **T220** `[状态门]` (`FR-026`): 回写 — verify: `x`\n"
        "- [ ] **T221** `[状态门]` (`FR-026`): 又回写 — verify: `y`\n"
    )
    errors: list[str] = []
    sv.validate_status_writeback_is_last(_ACTIVE, tasks, errors, "m")
    assert any("必须唯一" in e for e in errors)


def test_task_ids_must_increase_in_document_order(sv):
    tasks = (
        "## 2. 实现任务\n\n"
        "- [ ] **T202** (`FR-001`): 后面的编号 — verify: `tests/a.py`\n"
        "- [ ] **T200** (`FR-002`): 却排在前面 — verify: `tests/b.py`\n"
    )
    errors: list[str] = []
    sv.validate_task_id_order({"gate_version": 1}, tasks, errors, "m")
    assert any("递增" in e and "T200" in e for e in errors)


def test_duplicate_task_id_rejected(sv):
    tasks = (
        "## 2. 实现任务\n\n"
        "- [ ] **T201** (`FR-001`): 一 — verify: `tests/a.py`\n"
        "- [ ] **T201** (`FR-002`): 二 — verify: `tests/b.py`\n"
    )
    errors: list[str] = []
    sv.validate_task_id_order({"gate_version": 1}, tasks, errors, "m")
    assert any("重复" in e for e in errors)


def test_sequential_task_ids_pass(sv):
    tasks = (
        "## 2. 实现任务\n\n"
        "- [ ] **T201** (`FR-001`): 一 — verify: `tests/a.py`\n"
        "- [ ] **T203** (`FR-002`): 二（允许跳号，只要递增） — verify: `tests/b.py`\n"
    )
    errors: list[str] = []
    sv.validate_task_id_order({"gate_version": 1}, tasks, errors, "m")
    assert errors == []


# --------------------------------------------------------------------------- #
# 全树批量：多里程碑共存
# --------------------------------------------------------------------------- #


def test_batch_multiple_milestones(sv, tmp_path):
    """批量场景：多个里程碑并存，校验能逐个处理且错误不串位。"""
    features = tmp_path / "docs" / "features"
    for mid, name in [("0.1.1", "0.1.1-a"), ("0.1.2", "0.1.2-b")]:
        vdir = features / "0.1"
        mdir = vdir / name
        mdir.mkdir(parents=True)
        (mdir / "spec.md").write_text(
            "---\nkind: milestone\n"
            f'id: {mid}\nversion: "0.1"\nstatus: done\nresearch_claim_status: not-applicable\n'
            "gate_version: 0\ncreated: 2026-08-01\nprerequisites: []\n"
            f"---\n# {mid}\n",
            encoding="utf-8",
        )
        (mdir / "tasks.md").write_text("# tasks\n", encoding="utf-8")
    (features / "0.1" / "spec.md").write_text(
        '---\nkind: version-spec\nid: v0.1\nversion: "0.1"\nstatus: in-progress\n'
        "research_claim_status: not-applicable\n---\n# v\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "README.md").write_text("map\n", encoding="utf-8")
    errors: list[str] = []
    sv.validate_spec_lifecycle(features, tmp_path, errors)
    assert errors == []


def test_batch_duplicate_id(sv, tmp_path):
    features = tmp_path / "docs" / "features"
    for name in ["0.1.1-a", "0.1.1-b"]:
        mdir = features / "0.1" / name
        mdir.mkdir(parents=True)
        (mdir / "spec.md").write_text(
            "---\nkind: milestone\n"
            'id: 0.1.1\nversion: "0.1"\nstatus: done\n'
            "gate_version: 0\ncreated: 2026-08-01\nprerequisites: []\n"
            "---\n# dup\n",
            encoding="utf-8",
        )
    (features / "0.1" / "spec.md").write_text(
        '---\nkind: version-spec\nid: v0.1\nversion: "0.1"\nstatus: in-progress\n---\n# v\n',
        encoding="utf-8",
    )
    errors: list[str] = []
    sv.validate_spec_lifecycle(features, tmp_path, errors)
    assert any("重复" in e for e in errors)


# --------------------------------------------------------------------------- #
# round1 修复回归：链接/所有权/版本收口接线（STRUCT-C001/C002）
# --------------------------------------------------------------------------- #


def _write_version_forest(tmp_path, version_status="in-progress"):
    features = tmp_path / "docs" / "features"
    (features / "0.1" / "0.1.1-minimal-kernel").mkdir(parents=True)
    (features / "0.1" / "0.1.1-minimal-kernel" / "spec.md").write_text(
        '---\nkind: milestone\nid: 0.1.1\nversion: "0.1"\nstatus: done\n'
        "research_claim_status: not-applicable\n"
        "gate_version: 0\ncreated: 2026-08-01\nprerequisites: []\n---\n# m\n",
        encoding="utf-8",
    )
    (features / "0.1" / "0.1.1-minimal-kernel" / "tasks.md").write_text("# t\n", encoding="utf-8")
    (features / "0.1" / "spec.md").write_text(
        f'---\nkind: version-spec\nid: v0.1\nversion: "0.1"\nstatus: {version_status}\n'
        "research_claim_status: not-applicable\n---\n# v\n",
        encoding="utf-8",
    )
    return features


def test_entry_level_dead_link_rejected(sv, tmp_path):
    """STRUCT-C001: 生产入口必须执行链接校验——维护中文档里的死链必报。"""
    features = _write_version_forest(tmp_path)
    (tmp_path / "docs" / "dead.md").write_text("[x](missing.md)\n", encoding="utf-8")
    errors: list[str] = []
    sv.validate_spec_lifecycle(features, tmp_path, errors)
    assert any("dead.md" in e and "不存在" in e for e in errors)


def test_entry_level_dir_as_file_rejected(sv, tmp_path):
    """STRUCT-C001: 链接目标为目录（非文件）必报。"""
    features = _write_version_forest(tmp_path)
    (tmp_path / "docs" / "sub").mkdir()
    (tmp_path / "docs" / "d.md").write_text("[x](sub)\n", encoding="utf-8")
    errors: list[str] = []
    sv.validate_spec_lifecycle(features, tmp_path, errors)
    assert any("目录" in e for e in errors)


def test_ownership_index_missing_fails(sv, tmp_path):
    """STRUCT-C001: 缺 docs/README.md 所有权索引必报。"""
    features = _write_version_forest(tmp_path)
    errors: list[str] = []
    sv.validate_spec_lifecycle(features, tmp_path, errors)
    assert any("所有权索引" in e for e in errors)


def test_ownership_index_broken_link_fails(sv, tmp_path):
    """STRUCT-C001: docs/README.md 内的死链必报。"""
    features = _write_version_forest(tmp_path)
    (tmp_path / "docs" / "README.md").write_text("[x](missing.md)\n", encoding="utf-8")
    errors: list[str] = []
    sv.validate_spec_lifecycle(features, tmp_path, errors)
    assert any("README" in e and "不存在" in e for e in errors)


def test_ownership_status_drift_fails(sv, tmp_path):
    """STRUCT-C001: 派生入口（版本 README）声明与 spec 相悖状态必报。"""
    features = _write_version_forest(tmp_path)  # 0.1.1 = done
    (tmp_path / "docs" / "README.md").write_text("map\n", encoding="utf-8")
    vreadme = tmp_path / "docs" / "features" / "0.1" / "README.md"
    vreadme.parent.mkdir(parents=True, exist_ok=True)
    # 0.1 版本 README 声明 0.1.1 为 in-progress，与 spec 的 done 冲突
    vreadme.write_text("| 0.1.1 | in-progress |\n", encoding="utf-8")
    errors: list[str] = []
    sv.validate_spec_lifecycle(features, tmp_path, errors)
    assert any("不一致" in e for e in errors)


def test_version_done_without_release_fails(sv, tmp_path):
    """STRUCT-C002: 版本 done 但缺 release 文件必报。"""
    features = _write_version_forest(tmp_path, version_status="done")
    (tmp_path / "docs" / "README.md").write_text("map\n", encoding="utf-8")
    errors: list[str] = []
    sv.validate_spec_lifecycle(features, tmp_path, errors)
    assert any("status=done 但缺 release" in e for e in errors)


def test_version_done_release_without_closed_at_fails(sv, tmp_path):
    """STRUCT-C002: release 缺结构化 closed_at 必报。"""
    features = _write_version_forest(tmp_path, version_status="done")
    (tmp_path / "docs" / "README.md").write_text("map\n", encoding="utf-8")
    rel_dir = tmp_path / "docs" / "features" / "releases"
    rel_dir.mkdir(parents=True)
    (rel_dir / "0.1.md").write_text('---\nversion: "0.1"\n---\n# release\n', encoding="utf-8")
    errors: list[str] = []
    sv.validate_spec_lifecycle(features, tmp_path, errors)
    assert any("closed_at" in e for e in errors)


def test_version_done_prose_closed_at_bypass_fails(sv, tmp_path):
    """STRUCT-C002: 正文只提及 closed_at 但 frontmatter 无该字段，不得绕过收口。"""
    features = _write_version_forest(tmp_path, version_status="done")
    (tmp_path / "docs" / "README.md").write_text("map\n", encoding="utf-8")
    rel_dir = tmp_path / "docs" / "features" / "releases"
    rel_dir.mkdir(parents=True)
    (rel_dir / "0.1.md").write_text(
        '---\nversion: "0.1"\n---\n# release\nclosed_at 已由 2026-08-10 记录在正文中\n',
        encoding="utf-8",
    )
    errors: list[str] = []
    sv.validate_spec_lifecycle(features, tmp_path, errors)
    assert any("closed_at" in e for e in errors)


def test_version_done_with_pending_milestone_fails(sv, tmp_path):
    """STRUCT-C002: 版本 done 但某里程碑未 done 必报。"""
    features = _write_version_forest(tmp_path, version_status="done")
    # 把 0.1.1 改成 in-progress
    (features / "0.1" / "0.1.1-minimal-kernel" / "spec.md").write_text(
        '---\nkind: milestone\nid: 0.1.1\nversion: "0.1"\nstatus: in-progress\n'
        "research_claim_status: not-applicable\n"
        "gate_version: 0\ncreated: 2026-08-01\nprerequisites: []\n---\n# m\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "README.md").write_text("map\n", encoding="utf-8")
    rel_dir = tmp_path / "docs" / "features" / "releases"
    rel_dir.mkdir(parents=True)
    (rel_dir / "0.1.md").write_text(
        '---\nversion: "0.1"\nclosed_at: 2026-08-10\n---\n# release\n', encoding="utf-8"
    )
    errors: list[str] = []
    sv.validate_spec_lifecycle(features, tmp_path, errors)
    assert any("未 done" in e for e in errors)


def test_version_done_valid_closes_clean(sv, tmp_path):
    """STRUCT-C002: 版本 done + release + closed_at + 全部里程碑 done = 通过。"""
    features = _write_version_forest(tmp_path, version_status="done")
    (tmp_path / "docs" / "README.md").write_text("map\n", encoding="utf-8")
    rel_dir = tmp_path / "docs" / "features" / "releases"
    rel_dir.mkdir(parents=True)
    (rel_dir / "0.1.md").write_text(
        '---\nversion: "0.1"\nclosed_at: 2026-08-10\n---\n# release\n', encoding="utf-8"
    )
    errors: list[str] = []
    sv.validate_spec_lifecycle(features, tmp_path, errors)
    assert errors == []


def test_prereq_diamond_not_flagged_as_cycle(sv):
    """prereq-cycle-false-positive: 菱形依赖（非环）不得误报。"""
    all_ids = {
        "0.1.1": (pathlib.Path("a"), {"prerequisites": []}),
        "0.1.2": (pathlib.Path("b"), {"prerequisites": ["0.1.1"]}),
        "0.1.3": (pathlib.Path("c"), {"prerequisites": ["0.1.1"]}),
        "0.1.4": (pathlib.Path("d"), {"prerequisites": ["0.1.2", "0.1.3"]}),
    }
    errors: list[str] = []
    sv.validate_prerequisites(all_ids, errors)
    assert errors == []


def test_tasks_status_uniqueness_without_design(sv):
    """tasks-status-uniqueness-skipped: 无 design.md 时 tasks 声明 status 仍必报。"""
    errors: list[str] = []
    tasks = "---\nstatus: done\n---\n# tasks"
    sv.check_status_uniqueness("", tasks, errors, "m")
    assert any("tasks.md" in e and "status" in e for e in errors)


def test_dup_id_preserves_dups(sv, tmp_path):
    """dup-id-info-lost: collect_all_milestones 保留重复目录信息。"""
    features = tmp_path / "docs" / "features"
    for name in ["0.1.1-a", "0.1.1-b"]:
        mdir = features / "0.1" / name
        mdir.mkdir(parents=True)
        (mdir / "spec.md").write_text(
            '---\nkind: milestone\nid: 0.1.1\nversion: "0.1"\nstatus: done\n'
            "gate_version: 0\ncreated: 2026-08-01\nprerequisites: []\n---\n# d\n",
            encoding="utf-8",
        )
    (features / "0.1" / "spec.md").write_text(
        '---\nkind: version-spec\nid: v0.1\nversion: "0.1"\nstatus: in-progress\n---\n',
        encoding="utf-8",
    )
    coll = sv.collect_all_milestones(features)
    assert len(coll["0.1.1"][1].get("__dups__", [])) == 1


# --------------------------------------------------------------------------- #
# round4 修复回归：STRUCT-C001 版本无关 README 扫描 + 跨层级真相源
# --------------------------------------------------------------------------- #


def test_ownership_drift_detected_for_future_version(sv, tmp_path):
    """STRUCT-C001: 版本 README 扫描不得硬编码 0.1——未来版本漂移必报。"""
    features = _write_version_forest(tmp_path)
    (tmp_path / "docs" / "README.md").write_text("map\n", encoding="utf-8")
    # 新增第二个版本 0.2，其 README 声明 0.1.1 为 in-progress（与 spec 的 done 冲突）
    v2 = features / "0.2"
    v2.mkdir(parents=True)
    (v2 / "spec.md").write_text(
        '---\nkind: version-spec\nid: v0.2\nversion: "0.2"\nstatus: in-progress\n---\n',
        encoding="utf-8",
    )
    (v2 / "README.md").write_text("| 0.1.1 | in-progress |\n", encoding="utf-8")
    errors: list[str] = []
    sv.validate_spec_lifecycle(features, tmp_path, errors)
    assert any("0.1.1" in e and "不一致" in e for e in errors)


def test_milestone_design_redefines_invariant_fails(sv, tmp_path):
    """STRUCT-C001: 里程碑 design.md 重新定义全局不变量 C1/C2 必报。"""
    features = _write_version_forest(tmp_path)
    (tmp_path / "docs" / "README.md").write_text("map\n", encoding="utf-8")
    mdir = features / "0.1" / "0.1.1-minimal-kernel"
    (mdir / "design.md").write_text(
        "## 3. 数据模型\n\nC1: Σ position_units ≡ 0\n", encoding="utf-8"
    )
    errors: list[str] = []
    sv.validate_spec_lifecycle(features, tmp_path, errors)
    assert any("全局不变量" in e and "C1" in e for e in errors)


def test_milestone_design_without_invariant_passes(sv, tmp_path):
    """STRUCT-C001: 里程碑 design.md 不重定义不变量则通过。"""
    features = _write_version_forest(tmp_path)
    (tmp_path / "docs" / "README.md").write_text("map\n", encoding="utf-8")
    mdir = features / "0.1" / "0.1.1-minimal-kernel"
    (mdir / "design.md").write_text("## 2. 架构与模块边界\n不涉及不变量\n", encoding="utf-8")
    errors: list[str] = []
    sv.validate_spec_lifecycle(features, tmp_path, errors)
    assert not any("全局不变量" in e for e in errors)


def test_architecture_copying_invariant_fails(sv, tmp_path):
    """STRUCT-C001: architecture.md 复制字段级合同（C1:/C2: 定义式）必报。"""
    features = _write_version_forest(tmp_path)
    (tmp_path / "docs" / "README.md").write_text("map\n", encoding="utf-8")
    (tmp_path / "docs" / "market-game-sim-architecture.md").write_text(
        "## 技术不变量\n\nC1: Σ position_units ≡ 0\nC2: Σ wallet_units ≡ 0\n",
        encoding="utf-8",
    )
    errors: list[str] = []
    sv.validate_spec_lifecycle(features, tmp_path, errors)
    assert any("architecture" in e and "C1" in e for e in errors)


def test_architecture_referencing_invariant_passes(sv, tmp_path):
    """STRUCT-C001: architecture.md 仅引用 C1/C2（无定义式）则通过。"""
    features = _write_version_forest(tmp_path)
    (tmp_path / "docs" / "README.md").write_text("map\n", encoding="utf-8")
    (tmp_path / "docs" / "market-game-sim-architecture.md").write_text(
        "## 技术不变量\n守恒以 C1/C2 整数精确断言，定义见 docs/contracts/。\n",
        encoding="utf-8",
    )
    errors: list[str] = []
    sv.validate_spec_lifecycle(features, tmp_path, errors)
    assert not any("architecture" in e and "C1" in e for e in errors)


def test_architecture_colon_reference_passes(sv, tmp_path):
    """STRUCT-C005: architecture 用 C1:/C2: 冒号引用（无定义式）应通过。"""
    features = _write_version_forest(tmp_path)
    (tmp_path / "docs" / "README.md").write_text("map\n", encoding="utf-8")
    (tmp_path / "docs" / "market-game-sim-architecture.md").write_text(
        "## 技术不变量\nC1: 见 docs/contracts/conservation.md；C2: 参见上述文档。\n",
        encoding="utf-8",
    )
    errors: list[str] = []
    sv.validate_spec_lifecycle(features, tmp_path, errors)
    assert not any("architecture" in e and ("C1" in e or "C2" in e) for e in errors)


def test_milestone_design_colon_reference_passes(sv, tmp_path):
    """STRUCT-C005: 里程碑 design 用 C1:/C2: 冒号引用（无定义式）应通过。"""
    features = _write_version_forest(tmp_path)
    (tmp_path / "docs" / "README.md").write_text("map\n", encoding="utf-8")
    mdir = features / "0.1" / "0.1.1-minimal-kernel"
    (mdir / "design.md").write_text(
        "## 3. 数据模型\nC1: 见 docs/contracts/conservation.md；C2: 参见上述文档。\n",
        encoding="utf-8",
    )
    errors: list[str] = []
    sv.validate_spec_lifecycle(features, tmp_path, errors)
    assert not any("全局不变量" in e and ("C1" in e or "C2" in e) for e in errors)


def test_architecture_cross_line_reference_passes(sv, tmp_path):
    """STRUCT-C005: C1: 引用后下一行出现普通字段描述，不得跨行误判为定义。"""
    features = _write_version_forest(tmp_path)
    (tmp_path / "docs" / "README.md").write_text("map\n", encoding="utf-8")
    (tmp_path / "docs" / "market-game-sim-architecture.md").write_text(
        "## 技术不变量\nC1: 见 docs/contracts/ 文档\nwallet_units 表示钱包余额。\n",
        encoding="utf-8",
    )
    errors: list[str] = []
    sv.validate_spec_lifecycle(features, tmp_path, errors)
    assert not any("architecture" in e and ("C1" in e or "C2" in e) for e in errors)


def test_architecture_generic_equation_fails(sv, tmp_path):
    """STRUCT-C005: C1: 通用守恒方程（无预置 token）也应判为定义并拒绝。"""
    features = _write_version_forest(tmp_path)
    (tmp_path / "docs" / "README.md").write_text("map\n", encoding="utf-8")
    (tmp_path / "docs" / "market-game-sim-architecture.md").write_text(
        "## 技术不变量\nC1: cash + position = 0\n", encoding="utf-8"
    )
    errors: list[str] = []
    sv.validate_spec_lifecycle(features, tmp_path, errors)
    assert any("architecture" in e and "C1" in e for e in errors)


# --------------------------------------------------------------------------- #
# 预注册结构：模板必填项 → 真实产物
# --------------------------------------------------------------------------- #


def _write_prereg(tmp_path, items):
    exp = tmp_path / "docs" / "experiments"
    exp.mkdir(parents=True, exist_ok=True)
    (exp / "experiment-template.md").write_text(
        "# 模板\n\n" + "\n".join(f"- [ ] {i}" for i in items) + "\n", encoding="utf-8"
    )
    return exp


def test_preregistration_missing_item_is_rejected(sv, tmp_path):
    """漏项不是格式问题：少一条停止规则，"何时停止收样"就变成看着结果决定的。"""
    exp = _write_prereg(tmp_path, sv.PREREG_REQUIRED_ITEMS)
    kept = [i for i in sv.PREREG_REQUIRED_ITEMS if i != "停止规则"]
    (exp / "0.1.5-preregistration.md").write_text(
        "# 预注册\n\n" + "\n".join(f"- [x] {i}" for i in kept) + "\n", encoding="utf-8"
    )
    errors: list[str] = []
    sv.validate_preregistrations(tmp_path, errors)
    assert any("停止规则" in e and "缺少必填项" in e for e in errors)


def test_complete_preregistration_passes(sv, tmp_path):
    exp = _write_prereg(tmp_path, sv.PREREG_REQUIRED_ITEMS)
    (exp / "0.1.5-preregistration.md").write_text(
        "# 预注册\n\n" + "\n".join(f"- [x] {i}" for i in sv.PREREG_REQUIRED_ITEMS) + "\n",
        encoding="utf-8",
    )
    errors: list[str] = []
    sv.validate_preregistrations(tmp_path, errors)
    assert errors == []


@pytest.mark.parametrize("missing", ["risk_appetite", "theta_in", "theta_out", "k_x1000"])
def test_preregistration_missing_model_parameter_is_rejected(sv, tmp_path, missing):
    """T202 must freeze behavior parameters before T213 can observe results."""
    exp = _write_prereg(tmp_path, sv.PREREG_REQUIRED_ITEMS)
    kept = [item for item in sv.PREREG_REQUIRED_ITEMS if item != missing]
    (exp / "0.1.5-preregistration.md").write_text(
        "# 预注册\n\n" + "\n".join(f"- [x] {item}" for item in kept) + "\n",
        encoding="utf-8",
    )
    errors: list[str] = []
    sv.validate_preregistrations(tmp_path, errors)
    assert any(missing in error and "缺少必填项" in error for error in errors)


def test_template_drift_from_validator_is_rejected(sv, tmp_path):
    """模板与校验器闭集漂移必须报错，而不是一边悄悄失效。"""
    _write_prereg(tmp_path, [i for i in sv.PREREG_REQUIRED_ITEMS if i != "多重比较"])
    errors: list[str] = []
    sv.validate_preregistrations(tmp_path, errors)
    assert any("模板与校验器已漂移" in e for e in errors)


def test_absent_preregistration_is_silently_ok(sv, tmp_path):
    """无产物时不越权判定任务时点；有产物时仍 fail closed。"""
    _write_prereg(tmp_path, sv.PREREG_REQUIRED_ITEMS)
    errors: list[str] = []
    sv.validate_preregistrations(tmp_path, errors)
    assert errors == []


def test_repository_template_covers_all_required_items(sv):
    """真实模板必须覆盖必填闭集，防止模板与校验器漂移。"""
    errors: list[str] = []
    sv.validate_preregistrations(ROOT, errors)
    assert errors == []
    template = (ROOT / sv.PREREG_TEMPLATE).read_text(encoding="utf-8")
    for item in sv.PREREG_REQUIRED_ITEMS:
        assert item in template, f"模板缺 {item}"
