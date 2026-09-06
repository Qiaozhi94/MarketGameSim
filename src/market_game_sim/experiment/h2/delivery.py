"""T905 的隐私部分：所有者成果包与 PII 扫描（DR-301 / NFR-302 / AC-308）。

完整的交付流水线（样本流图、三类结果、代表性回放、index-only 重建）属于 T920/T921；
这里只落地"成果包里不得出现可直接识别个人的信息"这一条，以及所有者轨的证据级别
标注——它们是 AC-308 的判据，不依赖分析结果，可以先做。

PII 扫描采用**保守正则**：宁可误报也不漏报。项目本来就不采集身份信息，所以扫描命中
任何一条都说明流程出了问题，而不是"这条可以放行"。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from market_game_sim.experiment.h2 import protocol, session

#: 保守的直接标识符模式。命中即视为事故，不做白名单豁免。
_PII_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("phone", re.compile(r"(?<!\d)(?:\+?\d[\d\s-]{8,}\d)(?!\d)")),
    ("payment", re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")),
    ("id_card", re.compile(r"(?<!\d)\d{15}(?:\d{2}[\dXx])?(?!\d)")),
)


@dataclass(frozen=True, slots=True)
class OwnerBundle:
    """所有者轨成果包。证据级别固定为 experiment-preview，且标注为描述性。"""

    owner_id: str
    evidence_class: str
    marked_descriptive: bool
    research_claim_eligible: bool
    contents: dict[str, Any] = field(default_factory=dict)

    def as_text(self) -> str:
        """扫描用的扁平文本视图。"""
        parts = [self.owner_id, self.evidence_class]
        parts.extend(_flatten(self.contents))
        return "\n".join(parts)


def _flatten(value: Any) -> list[str]:
    if isinstance(value, dict):
        out: list[str] = []
        for key, item in value.items():
            out.append(str(key))
            out.extend(_flatten(item))
        return out
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            out.extend(_flatten(item))
        return out
    return [str(value)]


def build_owner_bundle(contents: dict[str, Any] | None = None) -> OwnerBundle:
    """按冻结合同构造所有者成果包的信封。

    证据级别与研究声明资格都从合同读取，不在这里硬写——合同已经把
    ``experiment-preview`` 和 ``research_claim_eligible: false`` 冻结住了。
    """
    track = protocol.load_contract()["owner_n_of_1_track"]
    return OwnerBundle(
        owner_id=session.OWNER_ID,
        evidence_class=track["evidence_class"],
        marked_descriptive=True,
        research_claim_eligible=track["research_claim_eligible"],
        contents=dict(contents or {}),
    )


def scan_for_pii(bundle: OwnerBundle | str) -> list[str]:
    """返回命中的 PII 类别；空列表表示成果包干净。"""
    text = bundle.as_text() if isinstance(bundle, OwnerBundle) else str(bundle)
    return sorted({name for name, pattern in _PII_PATTERNS if pattern.search(text)})
