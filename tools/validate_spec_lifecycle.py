#!/usr/bin/env python3
"""规格生命周期薄 CLI（仅标准库）。

复用 `spec_validation.py` 的纯函数，对 `docs/features/` 全树执行生命周期、链接与
所有权校验。本文件只做参数解析与错误输出，不重复任何 owner/path/exit 判据。

用法：
    python tools/validate_spec_lifecycle.py [--features docs/features]
退出码 0 表示全部通过；非 0 时逐条打印失败原因。
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import spec_validation

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_FEATURES = ROOT / "docs" / "features"


def main() -> int:
    parser = argparse.ArgumentParser(description="规格生命周期校验")
    parser.add_argument("--features", type=pathlib.Path, default=DEFAULT_FEATURES)
    args = parser.parse_args()

    errors: list[str] = []
    spec_validation.validate_spec_lifecycle(args.features, ROOT, errors)
    if errors:
        print(f"规格生命周期校验失败（{len(errors)} 项）：")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("规格生命周期校验通过：frontmatter / 状态 / 前置 / 链接 / gate 门禁")
    return 0


if __name__ == "__main__":
    sys.exit(main())
