"""tools/verify.py 回归测试：缺工具时按失败步骤记账，而不是抛未捕获异常。

ADR006-012：在 conda 等 ruff 不在 PATH 的环境里，旧的 `_run` 直接把
FileNotFoundError 抛出，整个统一入口崩掉，其余步骤的结论一并丢失。
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _load_verify():
    """按路径加载 `tools/verify.py`——它不是包的一部分，不能直接 import。"""
    path = ROOT / "tools" / "verify.py"
    spec = importlib.util.spec_from_file_location("tools_verify_entrypoint", path)
    assert spec and spec.loader, f"无法加载 {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_run_reports_missing_tool_as_failed_step(monkeypatch, capsys):
    module = _load_verify()

    def _missing(*_args, **_kwargs):
        raise FileNotFoundError("ruff")

    monkeypatch.setattr(module.subprocess, "run", _missing)
    assert module._run(["ruff", "check", "."], "ruff check") is False
    out = capsys.readouterr().out
    assert "FAILED: ruff check" in out
    assert "找不到可执行文件：ruff" in out


def test_main_returns_nonzero_when_a_tool_is_missing(monkeypatch, capsys):
    module = _load_verify()

    def _missing(*_args, **_kwargs):
        raise FileNotFoundError("ruff")

    monkeypatch.setattr(module.subprocess, "run", _missing)
    assert module.main() == 1
    assert "verify.py 失败步骤" in capsys.readouterr().out
