"""Render ``report.md`` FROM ``report.json``.

This module ONLY reads from the report dict -- it never recomputes
statistics, re-reads artifact files, or derives content independently
(PR-019 / E4).
"""

from __future__ import annotations

import json
from typing import Any


def render_markdown(report: dict[str, Any]) -> str:
    """Render a human-readable Markdown report from the report.json dict.

    On success: shows metrics, conditional conclusion, robustness
    conclusion, and negative results (all as fenced JSON blocks copied
    verbatim from the report dict).

    On failure: shows the failure code, artifact_id, and message.
    """
    lines: list[str] = []
    lines.append("# Market Game Sim -- Summary Report")
    lines.append("")
    lines.append(f"- **schema_version**: {report['schema_version']}")
    lines.append(f"- **run_id**: `{report['run_id']}`")
    lines.append(f"- **manifest_hash**: `{report['manifest_hash']}`")
    lines.append(f"- **generated_at**: {report['generated_at']}")
    lines.append("")

    failure = report.get("failure")
    if failure is not None:
        lines.append("## Report Generation Failed")
        lines.append("")
        lines.append(f"- **failure.code**: `{failure['code']}`")
        lines.append(f"- **failure.artifact_id**: `{failure['artifact_id']}`")
        lines.append(f"- **failure.message**: {failure['message']}")
        lines.append("")
        lines.append(
            "All business fields (metrics, conditional_conclusion, "
            "robustness_conclusion, negative_results) are null."
        )
        lines.append("")
        return "\n".join(lines)

    # --- Metrics ---
    lines.append("## Metrics")
    lines.append("")
    lines.append("_Consumed verbatim from upstream artifacts (not recomputed)._")
    lines.append("")
    lines.append("```json")
    lines.append(_to_json(report["metrics"]))
    lines.append("```")
    lines.append("")

    # --- Conditional Conclusion ---
    lines.append("## Conditional Conclusion")
    lines.append("")
    lines.append("```json")
    lines.append(_to_json(report["conditional_conclusion"]))
    lines.append("```")
    lines.append("")

    # --- Robustness Conclusion ---
    rc = report.get("robustness_conclusion")
    lines.append("## Robustness Conclusion")
    lines.append("")
    if rc is not None:
        lines.append("```json")
        lines.append(_to_json(rc))
        lines.append("```")
    else:
        lines.append("_(null -- no robustness conclusion produced)_")
    lines.append("")

    # --- Negative Results ---
    lines.append("## Negative Results")
    lines.append("")
    lines.append("```json")
    lines.append(_to_json(report["negative_results"]))
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def _to_json(value: Any) -> str:
    """Serialize to indented JSON with sorted keys for deterministic output."""
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
