"""Regression checks for review-process artifact ordering."""

from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]

CYCLE_HEADING = re.compile(r"^## (?:循环|Cycle)\s*\d+[:：]\s*(.+)$", re.MULTILINE)
CLOSURE_STATUS = re.compile(
    r"\*{0,2}(?:收尾状态|复盘状态)\*{0,2}\s*[:：]\s*(.*?)(?=\n- \*\*|\n#+\s|\Z)", re.DOTALL
)
CANDIDATE_STATUS = re.compile(r"候选|CI\s*待|待远端\s*CI|CI\s*未")
CLOSED_STATUS = re.compile(r"已闭环|已收口|全部关闭|全面 Go")
PENDING_EVIDENCE = re.compile(r"失败|未通过|待确认")
SUCCESSFUL_CI = re.compile(r"CI[^\n；。]*?(?:全绿|全部通过|通过|成功)|(?:run|运行)\s*\d+")


# 门的覆盖面按**版本文件**划定，不按标题关键字。
#
# 旧实现在这里写死 `if "H2" not in title and "0.3" not in title: continue`，结果 22 条
# 循环条目里只覆盖 7 条：v0.4 起的条目全部自动逃出，而把文件选择改成 glob 时写下的意图
# 恰恰是「别让新版本文件绕过这道门」——成对的两处只改了一处。
#
# 分界取 `CI_EVIDENCE_FLOOR`：v0.1/v0.2 期的循环早于「闭环必须带成功远端 CI 证据」这条
# 实践，其中 2 条（「0.1.1 方向重构与设计文档检视」「清空全部 carried-forward 遗留」）
# 声称闭环但没有 run 号；为满足今天的门去改历史记录是错的方向。分界**以下**的文件集合由
# `test_only_pre_practice_versions_are_exempt_from_the_ci_evidence_gate` 钉死，新增的版本
# 文件只能落在分界之上，因此默认纳入——覆盖面不再依赖任何人记得回来改过滤条件。
# 分界是**数值元组**而不是文件名字符串：字典序下 "0.10.md" < "0.3.md"，v0.10 会静默掉进豁免区。
CI_EVIDENCE_FLOOR = (0, 3)
GRANDFATHERED_RETROSPECTIVES = ("0.1.md", "0.2.md")
# 非循环正文的同目录文件；除它们之外的一切 .md 都按版本复盘文件纳入（见 _version_retrospectives）。
NON_CYCLE_FILES = frozenset({"RETROSPECTIVE.md", "structure-improvement-plan.md"})


def _cycle_entries(retrospective: str) -> list[tuple[str, str, str]]:
    """Return (title, closure status, metadata block) for every cycle entry."""
    headings = list(CYCLE_HEADING.finditer(retrospective))
    entries: list[tuple[str, str, str]] = []
    for index, heading in enumerate(headings):
        title = heading.group(1).strip()
        body_end = headings[index + 1].start() if index + 1 < len(headings) else len(retrospective)
        body = retrospective[heading.end() : body_end]
        metadata = body.split("\n#", 1)[0]
        status = CLOSURE_STATUS.search(body)
        entries.append((title, status.group(1).strip() if status else "", metadata))
    return entries


def _assert_closure_summaries_are_evidenced(retrospective: str) -> None:
    """Closure claims need successful remote CI evidence; candidate states never land."""
    entries = _cycle_entries(retrospective)
    assert entries, "retrospective must keep parseable cycle entries"
    for title, status, metadata in entries:
        assert status, f"cycle entry must record a closure status: {title}"
        assert not CANDIDATE_STATUS.search(status), (
            f"closure status must not record a candidate/pending-CI state: {title}: {status}"
        )
        if not CLOSED_STATUS.search(status):
            continue
        segments = [s for s in re.split(r"[；。\n]", metadata) if not PENDING_EVIDENCE.search(s)]
        assert any(SUCCESSFUL_CI.search(s) for s in segments), (
            f"closure claim lacks successful remote CI evidence: {title}: {status}"
        )


def _version_key(name: str) -> tuple[int, ...]:
    """`0.10.md` -> (0, 10)。按数值比较，不按字典序——否则 v0.10 会排到 v0.3 前面。"""
    stem = name.removesuffix(".md")
    assert all(part.isdigit() for part in stem.split(".")), (
        f"docs/reviews/{name} 不是可解析的版本复盘文件名；复盘文件必须叫 <version>.md"
        f"（非循环正文的文件请登记进 NON_CYCLE_FILES：{sorted(NON_CYCLE_FILES)}）"
    )
    return tuple(int(part) for part in stem.split("."))


def _version_retrospectives() -> list[pathlib.Path]:
    """按版本切分后的复盘文件；RETROSPECTIVE.md 只是索引，不含循环正文。

    **枚举方式是「除白名单外全部纳入」，不是 glob 匹配**：`[0-9].[0-9].md` 这种模式看着
    够用，实测却放过 `0.2.5.md`、`0.10.md` 这类文件名——它们既不进覆盖集合，也不进豁免
    集合，等于整条门禁都绕过了（本轮变异验证 C 实测）。白名单之外出现无法解析版本号的
    文件时直接失败，而不是静默跳过。过程稿（CURRENT-*.md / FIX-log.md）不在 git 里，
    也在这里排除。
    """
    paths = sorted(
        path
        for path in (ROOT / "docs" / "reviews").glob("*.md")
        if path.name not in NON_CYCLE_FILES
        and not path.name.startswith("CURRENT-")
        and path.name != "FIX-log.md"
    )
    assert paths, "docs/reviews/ 下找不到任何按版本切分的复盘文件"
    for path in paths:
        _version_key(path.name)
    return paths


def test_retrospective_index_holds_no_cycle_bodies():
    """索引不得回退成第二份正文——否则切分等于没做。"""
    index = (ROOT / "docs/reviews/RETROSPECTIVE.md").read_text(encoding="utf-8")
    assert not CYCLE_HEADING.search(index)
    for path in _version_retrospectives():
        assert f"({path.name})" in index, f"{path.name} 未登记在复盘索引里"


def test_version_retrospectives_record_only_ci_evidenced_closure():
    """每条闭环声明都要带成功 CI 证据，候选状态一律不许落地。

    覆盖 `CI_EVIDENCE_FLOOR` 及以上的**全部**版本文件与其中的**全部**循环条目：
    既不许把候选状态的闭环写进新版本文件绕过，也不许靠「标题里不写 H2」绕过。
    （历史名：`test_tracked_h2_retrospective_records_only_ci_evidenced_closure`，
    v0.3 循环 9 的 H2PLAN-007 引用的就是它。）
    """
    covered = [
        path for path in _version_retrospectives() if _version_key(path.name) >= CI_EVIDENCE_FLOOR
    ]
    assert covered, f"v{CI_EVIDENCE_FLOOR} 及以上没有任何版本复盘文件，门失去了检查对象"
    combined = "\n".join(path.read_text(encoding="utf-8") for path in covered)
    _assert_closure_summaries_are_evidenced(combined)


def test_only_pre_practice_versions_are_exempt_from_the_ci_evidence_gate():
    """豁免集合是冻结的：新增版本文件只能落在分界之上，自动被上面那条门覆盖。

    没有这条断言，"按文件分界" 会退化成新的旁路面——补一个 `0.2.x.md` 就能把条目
    放进豁免区。豁免只属于早于 CI 证据实践的 v0.1/v0.2，且这件事必须是显式改动。
    """
    exempt = tuple(
        path.name
        for path in _version_retrospectives()
        if _version_key(path.name) < CI_EVIDENCE_FLOOR
    )
    assert exempt == GRANDFATHERED_RETROSPECTIVES, (
        f"CI 证据门的豁免集合变了：{exempt} != {GRANDFATHERED_RETROSPECTIVES}；"
        "新增版本复盘文件必须落在 CI_EVIDENCE_FLOOR 之上，豁免历史文件是一次性的显式决定"
    )


def _retrospective_with_cycle_entry(closure_line: str, heading: str) -> str:
    return (
        f"## {heading}\n\n"
        "- **report_type**: doc-review\n"
        f"- {closure_line}\n"
        "- **本地门禁**: `python tools/verify.py` 全部通过\n\n"
        "### 完整 issue 表\n\n"
        "| ID | 标题 |\n"
        "|---|---|\n"
    )


def test_cycle_summary_accepts_closed_status_with_successful_remote_ci_run():
    """A post-CI final summary (已闭环 + successful run) must stay writable."""
    for heading in ("循环 24: v0.3 H2 需求排序调整检视与修复", "循环 24：v0.3 H2 修复复核"):
        legal = _retrospective_with_cycle_entry(
            "**收尾状态**: 已闭环；远端 CI run 123 全部通过", heading
        )
        _assert_closure_summaries_are_evidenced(legal)


def test_cycle_summary_accepts_fixed_status_without_closure_claim():
    """Factual all-fixed statuses (like historical cycle 21/22/23) stay acceptable."""
    factual = _retrospective_with_cycle_entry(
        "**收尾状态**: 4 条 High 已 fixed；CI 5 个 job 全绿",
        "循环 21: 0.3.1 H2 人在环实验规格与设计文档检视",
    )
    _assert_closure_summaries_are_evidenced(factual)


def test_cycle_summary_rejects_candidate_state():
    """Premature candidate summaries (historical cycle 24/25 states) must fail the gate."""
    for closure_line in (
        "**收尾状态**: 4 条 High 已 fixed；本地闭环候选，未 push，CI 待远端确认",
        "**收尾状态**：5 条全部 fixed；本地闭环候选，未 push，远端 CI 待确认",
    ):
        premature = _retrospective_with_cycle_entry(
            closure_line, "循环 24: v0.3 H2 需求排序调整检视与修复"
        )
        with pytest.raises(AssertionError, match="candidate/pending-CI"):
            _assert_closure_summaries_are_evidenced(premature)


def test_cycle_summary_rejects_closure_claim_without_ci_evidence():
    """已闭环 without remote CI evidence must fail even when local gates are green."""
    unevidenced = _retrospective_with_cycle_entry(
        "**收尾状态**: 已闭环；全部 High 关闭，本地 verify 全绿",
        "循环 24: v0.3 H2 需求排序调整检视与修复",
    )
    with pytest.raises(AssertionError, match="successful remote CI evidence"):
        _assert_closure_summaries_are_evidenced(unevidenced)


def test_cycle_summary_rejects_failed_run_as_closure_evidence():
    """A failed CI run is not closure evidence even when paired with 已闭环."""
    failed_run = _retrospective_with_cycle_entry(
        "**收尾状态**: 已闭环；远端 CI run 99 失败",
        "循环 24: v0.3 H2 需求排序调整检视与修复",
    )
    with pytest.raises(AssertionError, match="successful remote CI evidence"):
        _assert_closure_summaries_are_evidenced(failed_run)


def test_cycle_summary_requires_a_recorded_closure_status():
    """Dropping the closure status field must not become a bypass."""
    statusless = _retrospective_with_cycle_entry(
        "**基线**: `bed85e8` → `bbc19f2`", "循环 24: v0.3 H2 需求排序调整检视与修复"
    )
    with pytest.raises(AssertionError, match="closure status"):
        _assert_closure_summaries_are_evidenced(statusless)
