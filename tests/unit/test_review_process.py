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


def _h2_cycle_entries(retrospective: str) -> list[tuple[str, str, str]]:
    """Return (title, closure status, metadata block) for every H2 cycle entry."""
    headings = list(CYCLE_HEADING.finditer(retrospective))
    entries: list[tuple[str, str, str]] = []
    for index, heading in enumerate(headings):
        title = heading.group(1).strip()
        if "H2" not in title and "0.3" not in title:
            continue
        body_end = headings[index + 1].start() if index + 1 < len(headings) else len(retrospective)
        body = retrospective[heading.end() : body_end]
        metadata = body.split("\n#", 1)[0]
        status = CLOSURE_STATUS.search(body)
        entries.append((title, status.group(1).strip() if status else "", metadata))
    return entries


def _assert_h2_closure_summaries_are_evidenced(retrospective: str) -> None:
    """Closure claims need successful remote CI evidence; candidate states never land."""
    entries = _h2_cycle_entries(retrospective)
    assert entries, "retrospective must keep parseable H2 cycle entries"
    for title, status, metadata in entries:
        assert status, f"H2 cycle entry must record a closure status: {title}"
        assert not CANDIDATE_STATUS.search(status), (
            f"H2 closure status must not record a candidate/pending-CI state: {title}: {status}"
        )
        if not CLOSED_STATUS.search(status):
            continue
        segments = [s for s in re.split(r"[；。\n]", metadata) if not PENDING_EVIDENCE.search(s)]
        assert any(SUCCESSFUL_CI.search(s) for s in segments), (
            f"H2 closure claim lacks successful remote CI evidence: {title}: {status}"
        )


def test_tracked_h2_retrospective_records_only_ci_evidenced_closure():
    """Tracked H2 cycle summaries must carry successful CI evidence, never candidate states."""
    retrospective = (ROOT / "docs/reviews/RETROSPECTIVE.md").read_text(encoding="utf-8")
    _assert_h2_closure_summaries_are_evidenced(retrospective)


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


def test_h2_cycle_summary_accepts_closed_status_with_successful_remote_ci_run():
    """A post-CI final summary (已闭环 + successful run) must stay writable."""
    for heading in ("循环 24: v0.3 H2 需求排序调整检视与修复", "循环 24：v0.3 H2 修复复核"):
        legal = _retrospective_with_cycle_entry(
            "**收尾状态**: 已闭环；远端 CI run 123 全部通过", heading
        )
        _assert_h2_closure_summaries_are_evidenced(legal)


def test_h2_cycle_summary_accepts_fixed_status_without_closure_claim():
    """Factual all-fixed statuses (like historical cycle 21/22/23) stay acceptable."""
    factual = _retrospective_with_cycle_entry(
        "**收尾状态**: 4 条 High 已 fixed；CI 5 个 job 全绿",
        "循环 21: 0.3.1 H2 人在环实验规格与设计文档检视",
    )
    _assert_h2_closure_summaries_are_evidenced(factual)


def test_h2_cycle_summary_rejects_candidate_state():
    """Premature candidate summaries (historical cycle 24/25 states) must fail the gate."""
    for closure_line in (
        "**收尾状态**: 4 条 High 已 fixed；本地闭环候选，未 push，CI 待远端确认",
        "**收尾状态**：5 条全部 fixed；本地闭环候选，未 push，远端 CI 待确认",
    ):
        premature = _retrospective_with_cycle_entry(
            closure_line, "循环 24: v0.3 H2 需求排序调整检视与修复"
        )
        with pytest.raises(AssertionError, match="candidate/pending-CI"):
            _assert_h2_closure_summaries_are_evidenced(premature)


def test_h2_cycle_summary_rejects_closure_claim_without_ci_evidence():
    """已闭环 without remote CI evidence must fail even when local gates are green."""
    unevidenced = _retrospective_with_cycle_entry(
        "**收尾状态**: 已闭环；全部 High 关闭，本地 verify 全绿",
        "循环 24: v0.3 H2 需求排序调整检视与修复",
    )
    with pytest.raises(AssertionError, match="successful remote CI evidence"):
        _assert_h2_closure_summaries_are_evidenced(unevidenced)


def test_h2_cycle_summary_rejects_failed_run_as_closure_evidence():
    """A failed CI run is not closure evidence even when paired with 已闭环."""
    failed_run = _retrospective_with_cycle_entry(
        "**收尾状态**: 已闭环；远端 CI run 99 失败",
        "循环 24: v0.3 H2 需求排序调整检视与修复",
    )
    with pytest.raises(AssertionError, match="successful remote CI evidence"):
        _assert_h2_closure_summaries_are_evidenced(failed_run)


def test_h2_cycle_summary_requires_a_recorded_closure_status():
    """Dropping the closure status field must not become a bypass."""
    statusless = _retrospective_with_cycle_entry(
        "**基线**: `bed85e8` → `bbc19f2`", "循环 24: v0.3 H2 需求排序调整检视与修复"
    )
    with pytest.raises(AssertionError, match="closure status"):
        _assert_h2_closure_summaries_are_evidenced(statusless)
