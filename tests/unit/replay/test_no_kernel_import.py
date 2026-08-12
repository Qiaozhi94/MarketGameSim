"""T402 (AC-005, NFR-004): replay/ does NOT import kernel/book/ledger/eventlog."""

from __future__ import annotations

import ast
import pathlib

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_REPLAY_SRC = _ROOT / "src" / "market_game_sim" / "replay"

_FORBIDDEN = {"kernel", "book", "ledger", "eventlog"}


def _imports(file: pathlib.Path) -> list[str]:
    tree = ast.parse(file.read_text(encoding="utf-8"))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append(node.module.split(".")[0])
    return out


@pytest.mark.parametrize("file", sorted(_REPLAY_SRC.rglob("*.py")), ids=lambda f: f.name)
def test_replay_no_forbidden_imports(file: pathlib.Path) -> None:
    forbidden = [m for m in _imports(file) if m in _FORBIDDEN]
    assert not forbidden, f"{file.name} imports forbidden modules: {forbidden}"


def test_forbidden_module_categories_are_all_checked() -> None:
    """All four NFR-004 module categories must be in the forbidden set."""
    assert {"kernel", "book", "ledger", "eventlog"} == _FORBIDDEN


def test_replay_generate_importable() -> None:
    import market_game_sim.replay.generate  # noqa: F401
