"""Regression checks for review-process artifact ordering."""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_unclosed_h2_round_has_no_premature_cycle_summary():
    """Tracked history must not contain an H2 summary before remote CI closure."""
    retrospective = (ROOT / "docs/reviews/RETROSPECTIVE.md").read_text(encoding="utf-8")
    assert "## 循环 24:" not in retrospective
    assert "## 循环 25：" not in retrospective
