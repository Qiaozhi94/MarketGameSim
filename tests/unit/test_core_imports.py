"""T604 (KR-005): core domain layer has no third-party imports."""

import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "market_game_sim"

FORBIDDEN = {
    "numpy", "pandas", "scipy", "matplotlib", "sklearn",
    "torch", "tensorflow", "jax", "tqdm", "rich",
    "sortedcontainers", "networkx", "sympy",
}

ALLOWED_EXTERNAL = {"yaml", "__future__", "dataclasses", "typing",
                    "collections", "enum", "hashlib", "json",
                    "pathlib", "decimal", "importlib", "heapq",
                    "bisect", "math", "sys", "re", "copy",
                    "random", "os", "subprocess", "io", "tempfile",
                    "itertools", "functools", "operator", "abc"}


def _get_imports(file: pathlib.Path) -> list[str]:
    tree = ast.parse(file.read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module.split(".")[0])
    return imports


def _domain_files() -> list[pathlib.Path]:
    skip_dirs = {"__pycache__", "config"}
    files: list[pathlib.Path] = []
    for p in SRC.rglob("*.py"):
        if any(d in p.parts for d in skip_dirs):
            continue
        files.append(p)
    return files


@pytest.mark.parametrize("file", _domain_files(), ids=lambda f: str(f.relative_to(SRC)))
def test_no_forbidden_imports(file: pathlib.Path):
    imports = _get_imports(file)
    forbidden = [i for i in imports if i in FORBIDDEN]
    assert not forbidden, f"{file.name} imports {forbidden}"
