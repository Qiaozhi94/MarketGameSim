"""Regression checks for review-process artifact ordering."""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_unclosed_round_has_no_premature_cycle_summary():
    """The current round remains open, so the previously premature Cycle 25 summary is absent."""
    current = (ROOT / "docs/reviews/CURRENT-doc.md").read_text(encoding="utf-8")
    retrospective = (ROOT / "docs/reviews/RETROSPECTIVE.md").read_text(encoding="utf-8")
    assert re.search(r"^round: 7$", current, re.MULTILINE)
    assert re.search(r"^stop_condition_met: false$", current, re.MULTILINE)
    assert "## 循环 25：" not in retrospective
