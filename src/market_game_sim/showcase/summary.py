"""T203 (FR-027): showcase ``summary.md`` renderer.

``evidence_class=engineering-demonstration`` (and ``experiment-preview``)
bundles MUST carry an explicit ``不可作结论`` (not-a-conclusion) disclaimer
written by the generator, and generation FAILS if it is missing (design.md §6
/ FR-027). This is enforced by :func:`assert_disclaimer_present`, called from
the bundle builder after rendering -- a future edit that drops the disclaimer
from the renderer makes the build raise rather than ship a bundle that reads
like a research conclusion.
"""

from __future__ import annotations

from typing import Any

DISCLAIMER = "不可作结论"

_DISCLAIMER_BLOCK = (
    f"> ⚠️ {DISCLAIMER}：本成果包为工程示范（engineering-demonstration），"
    "仅证明端到端管线可运行并产出可观察产物，不构成任何研究结论、"
    "效应量主张或可外推的统计判断。"
)


def assert_disclaimer_present(text: str) -> None:
    """Raise ``ValueError`` if the ``不可作结论`` disclaimer is absent.

    FR-027 makes the disclaimer a hard generation gate, not a prose nicety:
    a bundle whose summary omits it must never be produced, because a reader
    could mistake an engineering demo for a research result.
    """
    if DISCLAIMER not in text:
        raise ValueError(
            "summary.md is missing the mandatory '不可作结论' disclaimer "
            "(FR-027); refusing to write an engineering-demonstration bundle "
            "that could be read as a research conclusion."
        )


def render_summary(
    *,
    run_id: str,
    terminated: str,
    event_count: int,
    liquidation_count: int,
    code_version: str,
    config_hash: str,
    seed: int,
    gate: str,
    evidence_class: str,
    rebuild_command: str,
    config_source: str | None = None,
    extras: dict[str, Any] | None = None,
) -> str:
    """Render the showcase ``summary.md`` as a string (always includes the
    ``不可作结论`` disclaimer when ``evidence_class`` is non-formal)."""
    lines: list[str] = []
    lines.append(f"# Showcase Bundle -- Gate {gate}")
    lines.append("")
    lines.append(f"- **evidence_class**: `{evidence_class}`")
    lines.append(f"- **gate**: `{gate}`")
    lines.append(f"- **code_version**: `{code_version}`")
    lines.append(f"- **config_hash**: `{config_hash}`")
    lines.append(f"- **seed**: `{seed}`")
    lines.append(f"- **run_id**: `{run_id}`")
    lines.append(f"- **terminated**: `{terminated}`")
    lines.append(f"- **event_count**: {event_count}")
    lines.append(f"- **liquidation_count**: {liquidation_count}")
    if config_source is not None:
        lines.append(f"- **config_source**: `{config_source}`")
    lines.append("")

    lines.append("## 重建")
    lines.append("")
    lines.append("```bash")
    lines.append(rebuild_command)
    lines.append("```")
    lines.append("")

    if extras:
        lines.append("## 产物清单")
        lines.append("")
        for name, value in extras.items():
            lines.append(f"- **{name}**: {value}")
        lines.append("")

    if evidence_class != "formal-research":
        lines.append("## 边界声明")
        lines.append("")
        lines.append(_DISCLAIMER_BLOCK)
        lines.append("")
        lines.append(
            "研究结论只能由 R5（T220）以 ``formal-research`` 证据类、经"
            "预注册协议与多重检验后写入 ``docs/experiments/``；本包不进入"
            "正式证据索引。"
        )
        lines.append("")

    return "\n".join(lines)
