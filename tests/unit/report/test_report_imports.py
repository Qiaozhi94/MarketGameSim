"""AC-005 (E5/NFR-004): report/ does NOT import kernel/book/ledger/eventlog.

Uses AST-based static analysis (same mechanism as
``tests/unit/test_core_imports.py``) to scan every ``.py`` file under
``src/market_game_sim/report/`` for forbidden imports.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_REPORT_SRC = _ROOT / "src" / "market_game_sim" / "report"

_FORBIDDEN_MODULES = {"kernel", "book", "ledger", "eventlog"}


def _get_imports(file: pathlib.Path) -> list[str]:
    tree = ast.parse(file.read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module.split(".")[0])
    return imports


def _report_files() -> list[pathlib.Path]:
    return sorted(_REPORT_SRC.rglob("*.py"))


@pytest.mark.parametrize("file", _report_files(), ids=lambda f: str(f.relative_to(_REPORT_SRC)))
def test_report_no_forbidden_imports(file: pathlib.Path) -> None:
    imports = _get_imports(file)
    forbidden = [i for i in imports if i in _FORBIDDEN_MODULES]
    assert not forbidden, f"{file.relative_to(_REPORT_SRC)} imports forbidden modules: {forbidden}"


def test_report_generate_importable() -> None:
    """``import market_game_sim.report.generate`` succeeds without error."""
    import market_game_sim.report.generate  # noqa: F401
