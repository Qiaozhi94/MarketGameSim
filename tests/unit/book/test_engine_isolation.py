"""ADR-013: the L1a matching core must stay ledger-free.

``book/engine.py`` and ``book/orderbook.py`` may import only the standard
library and each other.  The day someone reaches into ``ledger``/``hook``/
``kernel``/``eventlog`` (or any upper layer) from the core, the split
between generic matching (L1a) and clearing/risk (L1b) is gone again.
"""

from __future__ import annotations

import ast
import pathlib
import sys

import pytest

BOOK = pathlib.Path(__file__).resolve().parents[3] / "src" / "market_game_sim" / "book"
L1A_FILES = ("engine.py", "orderbook.py")
L1A_MODULES = {"market_game_sim.book.engine", "market_game_sim.book.orderbook"}


def _violations(source: str) -> list[str]:
    bad: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                bad.append(f"relative import level={node.level}")
                continue
            names = [node.module or ""]
        else:
            continue
        for name in names:
            if name.startswith("market_game_sim"):
                if name not in L1A_MODULES:
                    bad.append(name)
            elif name.split(".")[0] not in sys.stdlib_module_names:
                bad.append(name)
    return bad


@pytest.mark.parametrize("filename", L1A_FILES)
def test_l1a_core_imports_only_stdlib_and_itself(filename: str) -> None:
    source = (BOOK / filename).read_text(encoding="utf-8")
    assert _violations(source) == []


@pytest.mark.parametrize(
    "line",
    [
        "from market_game_sim.ledger.account import Account",
        "import market_game_sim.hook.interface",
        "from market_game_sim.kernel.runner import EventKernel",
        "from market_game_sim.book.matching import match_order",
        "from . import matching",
        "import numpy",
    ],
)
def test_guard_rejects_clearing_and_third_party_imports(line: str) -> None:
    assert _violations(line) != []


def test_l1b_adapter_still_depends_on_core() -> None:
    """The adapter must route matching through the core, not re-grow its own loop."""
    source = (BOOK / "matching.py").read_text(encoding="utf-8")
    assert "from market_game_sim.book import engine" in source
    assert "engine.match(" in source
    assert "peek_best_maker" not in source
