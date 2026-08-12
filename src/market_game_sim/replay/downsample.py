"""T204 (spec §3.3): Downsampling for large logs.

Downsampling is allowed but the ratio/rule must be visible in the output,
and a downsampled product must NOT be used for the E1 frame-consistency
acceptance (which always runs on the full, undownsampled log).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DownsampleRule:
    """Keep every ``keep_every``-th frame starting from ``offset``."""

    keep_every: int
    offset: int = 0

    def __post_init__(self) -> None:
        if self.keep_every < 1:
            raise ValueError(f"keep_every must be >= 1, got {self.keep_every}")
        if self.offset < 0:
            raise ValueError(f"offset must be >= 0, got {self.offset}")

    def describe(self) -> str:
        return f"keep every {self.keep_every}-th frame (offset {self.offset})"


def apply_downsample(frames: list, rule: DownsampleRule) -> list:
    """Return a subsample of ``frames`` per ``rule`` (frame_index-based)."""
    return [f for f in frames if (f.frame_index - rule.offset) % rule.keep_every == 0]
