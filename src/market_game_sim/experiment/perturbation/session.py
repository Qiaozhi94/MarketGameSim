"""0.4.2 T1120（FR-601 / DR-601）：``PerturbationSession`` 的冻结格式。

格式本身是一份数据文件——``docs/experiments/0.4.2-perturbation-session-format.json``——
而不是散在代码里的常量：字段、取值范围、记录顺序、内容哈希定义与稳定原因码都在那里，
校验入口（T1122/T1123）只消费它，不另写第二份。

冻结靠摘要登记：``FROZEN_FORMATS`` 把每个 ``format_version`` 钉到该文件的 sha256。
文件被改动而没有新建版本时 ``load_format`` 以 ``FORMAT_DRIFT`` 拒绝——格式变更只能是
「新版本 + 新登记」的显式改动，已落盘会话按其头记录声明的版本解析，不被就地改写语义
（spec FR-601 末句）。
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from collections.abc import Mapping, Sequence
from typing import Any

from market_game_sim.config.serialization import canonical_serialize

ROOT = pathlib.Path(__file__).resolve().parents[4]
FORMAT_PATH = ROOT / "docs" / "experiments" / "0.4.2-perturbation-session-format.json"

#: 当前写入版本。
FORMAT_VERSION = 1

#: 已冻结版本 -> 格式文件的 sha256。只增不改。
FROZEN_FORMATS: Mapping[int, str] = {
    1: "7bcdb5df454f99de0ff61b0e8c86dfe68f962ddd09aa2b2ba45a051be04f5c0f",
}


class SessionFormatError(Exception):
    """格式文件不可用；``code`` 为稳定原因码。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def load_format(version: int = FORMAT_VERSION, path: pathlib.Path = FORMAT_PATH) -> dict[str, Any]:
    """读取并核对 ``version`` 的冻结格式记录。

    未登记的版本给 ``UNSUPPORTED_VERSION``；文件摘要与登记不符给 ``FORMAT_DRIFT``；
    文件自报的版本与请求不符给 ``FORMAT_VERSION_MISMATCH``。
    """
    pinned = FROZEN_FORMATS.get(version)
    if pinned is None:
        raise SessionFormatError("UNSUPPORTED_VERSION", f"format_version {version!r} 未登记")
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != pinned:
        raise SessionFormatError(
            "FORMAT_DRIFT", f"{path.name} 的 sha256 为 {actual}，v{version} 登记为 {pinned}"
        )
    record = json.loads(raw.decode("utf-8"))
    if record.get("format_version") != version:
        raise SessionFormatError(
            "FORMAT_VERSION_MISMATCH",
            f"{path.name} 自报 format_version {record.get('format_version')!r}，请求的是 {version}",
        )
    return record


def record_line(record: Mapping[str, Any]) -> bytes:
    """一条记录在文件里的规范行字节（含结尾 ``\\n``）。"""
    return canonical_serialize(dict(record)) + b"\n"


def content_hash(header: Mapping[str, Any], actions: Sequence[Mapping[str, Any]]) -> str:
    """头记录与动作行的内容哈希；不含封口行，封口与否都能计算（FR-601）。"""
    digest = hashlib.sha256(record_line(header))
    for action in actions:
        digest.update(record_line(action))
    return digest.hexdigest()
