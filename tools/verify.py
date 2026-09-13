#!/usr/bin/env python3
"""本地统一验证入口（公开验证唯一入口）。

按固定顺序运行：密钥形态扫描 → 真源校验 → 生命周期/链接/所有权校验 → pytest →
ruff check → ruff format check。任一步失败即返回非零。

各底层命令仍可单独用于定位，但 README、SOP 与 CLAUDE 不再各自维护完整命令清单，
统一指向本入口。

用法：
    python tools/verify.py
退出码 0 表示全部通过；非 0 时打印失败步骤。
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _run(cmd: list[str], label: str) -> bool:
    print(f"\n== {label} ==")
    try:
        proc = subprocess.run(cmd, cwd=ROOT)
    except FileNotFoundError:
        # 工具不在 PATH（如 conda 环境下缺 ruff）时按普通失败步骤记账并指出缺哪个工具，
        # 而不是让未捕获异常把整个 verify 入口炸掉、掩盖其余步骤的结论。
        print(f"FAILED: {label}（找不到可执行文件：{cmd[0]}，请确认已安装并在 PATH 中）")
        return False
    if proc.returncode != 0:
        print(f"FAILED: {label}")
        return False
    return True


def main() -> int:
    steps = [
        ([sys.executable, "tools/check_secrets.py"], "密钥形态扫描"),
        ([sys.executable, "tools/validate_contract_sources.py"], "真源自校验"),
        ([sys.executable, "tools/validate_spec_lifecycle.py"], "规格生命周期校验"),
        ([sys.executable, "-m", "pytest", "-q"], "pytest"),
        (["ruff", "check", "."], "ruff check"),
        (["ruff", "format", "--check", "."], "ruff format check"),
    ]
    failed = []
    for cmd, label in steps:
        if not _run(cmd, label):
            failed.append(label)
    if failed:
        print(f"\nverify.py 失败步骤：{failed}")
        return 1
    print("\nverify.py 全部通过：密钥扫描 / 真源 / 生命周期 / pytest / ruff")
    return 0


if __name__ == "__main__":
    sys.exit(main())
