"""规格生命周期校验：`tools/spec_validation.py` / `validate_spec_lifecycle.py` 的 pytest 入口。

与 `test_contract_sources.py` 同一思路：**重点是负向变异测试**。只断言「当前仓库
通过」无法证明校验器在挡任何东西——删掉一段校验逻辑，happy-path 测试仍然全绿。

因此下面每个 `mutate_*` 都**先破坏一处输入，再断言校验器给出预期错误**。新增校验
规则时应同时新增一条变异，否则那条规则等于没有被测试。
"""

from __future__ import annotations

import importlib.util
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
            f'id: {mid}\nversion: "0.1"\nstatus: done\n'
            "gate_version: 0\ncreated: 2026-08-01\nprerequisites: []\n"
            f"---\n# {mid}\n",
            encoding="utf-8",
        )
        (mdir / "tasks.md").write_text("# tasks\n", encoding="utf-8")
    (features / "0.1" / "spec.md").write_text(
        '---\nkind: version-spec\nid: v0.1\nversion: "0.1"\nstatus: in-progress\n---\n# v\n',
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
        "gate_version: 0\ncreated: 2026-08-01\nprerequisites: []\n---\n# m\n",
        encoding="utf-8",
    )
    (features / "0.1" / "0.1.1-minimal-kernel" / "tasks.md").write_text("# t\n", encoding="utf-8")
    (features / "0.1" / "spec.md").write_text(
        f'---\nkind: version-spec\nid: v0.1\nversion: "0.1"\nstatus: {version_status}\n---\n# v\n',
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


def test_version_done_without_release_fails(sv, tmp_path):
    """STRUCT-C002: 版本 done 但缺 release 文件必报。"""
    features = _write_version_forest(tmp_path, version_status="done")
    (tmp_path / "docs" / "README.md").write_text("map\n", encoding="utf-8")
    errors: list[str] = []
    sv.validate_spec_lifecycle(features, tmp_path, errors)
    assert any("status=done 但缺 release" in e for e in errors)


def test_version_done_release_without_closed_at_fails(sv, tmp_path):
    """STRUCT-C002: release 缺 closed_at 必报。"""
    features = _write_version_forest(tmp_path, version_status="done")
    (tmp_path / "docs" / "README.md").write_text("map\n", encoding="utf-8")
    rel_dir = tmp_path / "docs" / "features" / "releases"
    rel_dir.mkdir(parents=True)
    (rel_dir / "0.1.md").write_text("# release\n", encoding="utf-8")
    errors: list[str] = []
    sv.validate_spec_lifecycle(features, tmp_path, errors)
    assert any("closed_at" in e for e in errors)


def test_version_done_with_pending_milestone_fails(sv, tmp_path):
    """STRUCT-C002: 版本 done 但某里程碑未 done 必报。"""
    features = _write_version_forest(tmp_path, version_status="done")
    # 把 0.1.1 改成 in-progress
    (features / "0.1" / "0.1.1-minimal-kernel" / "spec.md").write_text(
        '---\nkind: milestone\nid: 0.1.1\nversion: "0.1"\nstatus: in-progress\n'
        "gate_version: 0\ncreated: 2026-08-01\nprerequisites: []\n---\n# m\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "README.md").write_text("map\n", encoding="utf-8")
    rel_dir = tmp_path / "docs" / "features" / "releases"
    rel_dir.mkdir(parents=True)
    (rel_dir / "0.1.md").write_text("# release\nclosed_at: 2026-08-10\n", encoding="utf-8")
    errors: list[str] = []
    sv.validate_spec_lifecycle(features, tmp_path, errors)
    assert any("未 done" in e for e in errors)


def test_version_done_valid_closes_clean(sv, tmp_path):
    """STRUCT-C002: 版本 done + release + closed_at + 全部里程碑 done = 通过。"""
    features = _write_version_forest(tmp_path, version_status="done")
    (tmp_path / "docs" / "README.md").write_text("map\n", encoding="utf-8")
    rel_dir = tmp_path / "docs" / "features" / "releases"
    rel_dir.mkdir(parents=True)
    (rel_dir / "0.1.md").write_text("# release\nclosed_at: 2026-08-10\n", encoding="utf-8")
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


def test_dup_id_preserves_dups(sv):
    """dup-id-info-lost: collect_all_milestones 保留重复目录信息。"""
    tmp = pathlib.Path("tests/unit/fixtures_dup")
    try:
        features = tmp / "docs" / "features"
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
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
