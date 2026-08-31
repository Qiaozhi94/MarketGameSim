"""Regression tests for the platform-independent source-tree binding.

CI checkout (Linux, LF) and a Windows ``core.autocrlf=true`` checkout hold the
same logical sources but different raw bytes; ``_source_tree_sha256`` must bind
evidence to the logical content, not to the platform representation.
"""

from __future__ import annotations

import pathlib

from market_game_sim.showcase.formal import _source_tree_sha256


def _write(path: pathlib.Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_source_tree_hash_is_eol_invariant(tmp_path: pathlib.Path) -> None:
    lf_root = tmp_path / "lf"
    crlf_root = tmp_path / "crlf"
    for root in (lf_root, crlf_root):
        _write(root / "pkg" / "__init__.py", b"VALUE = 1\n")
        _write(root / "pkg" / "mod.py", b"def f():\n    return VALUE\n")
    eol = b"\r\n" if crlf_root else b"\n"
    _write(crlf_root / "pkg" / "__init__.py", b"VALUE = 1" + eol)
    _write(crlf_root / "pkg" / "mod.py", b"def f():" + eol + b"    return VALUE" + eol)

    assert _source_tree_sha256(lf_root) == _source_tree_sha256(crlf_root)


def test_source_tree_hash_still_binds_to_content(tmp_path: pathlib.Path) -> None:
    root = tmp_path / "pkg"
    _write(root / "mod.py", b"VALUE = 1\n")
    baseline = _source_tree_sha256(root)

    _write(root / "mod.py", b"VALUE = 2\n")
    assert _source_tree_sha256(root) != baseline

    _write(root / "extra.py", b"VALUE = 1\n")
    assert _source_tree_sha256(root) != _source_tree_sha256(root.parent / "missing")
