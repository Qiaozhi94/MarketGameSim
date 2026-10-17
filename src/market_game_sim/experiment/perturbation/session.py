"""0.4.2 T1120/T1122/T1123（FR-601 / DR-601 / FR-604）：``PerturbationSession`` 的冻结格式、
逐条落盘与校验入口。

格式本身是一份数据文件——``docs/experiments/0.4.2-perturbation-session-format.json``——
而不是散在代码里的常量：字段、取值范围、记录顺序、内容哈希定义与稳定原因码都在那里，
校验入口（T1122/T1123）只消费它，不另写第二份。

冻结靠摘要登记：``FROZEN_FORMATS`` 把每个 ``format_version`` 钉到该文件的 sha256。
文件被改动而没有新建版本时 ``load_format`` 以 ``FORMAT_DRIFT`` 拒绝——格式变更只能是
「新版本 + 新登记」的显式改动，已落盘会话按其头记录声明的版本解析，不被就地改写语义
（spec FR-601 末句）。

写入与读取共用同一个逐条校验器（``_Checker``）：

* ``SessionWriter`` 每写一条记录前先过校验器，不合格即抛 ``SessionError`` 且一个字节都不写；
  每行写完立即 ``flush`` + ``fsync``，所以在任意一条动作之后终止进程，已写动作一条不丢，
  会话只是缺封口行（``UNSEALED``）。
* ``validate_session`` / ``load_session`` 不抛异常，返回 ``SessionCheck``：通过时带头记录、
  动作行、封口行、封口状态与内容哈希；不通过时带冻结记录里的稳定原因码与出错行号。
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from market_game_sim.config.serialization import SerializationError, canonical_serialize

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


# --------------------------------------------------------------------------- #
# 逐条校验（读写共用）
# --------------------------------------------------------------------------- #

SEALED = "SEALED"
UNSEALED = "UNSEALED"


class SessionError(Exception):
    """会话记录不合格；``code`` 为冻结记录 ``reason_codes`` 里的稳定原因码。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _forbidden_path(value: Any, forbidden: frozenset[str], where: str) -> str | None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in forbidden:
                return f"{where}.{key}"
            hit = _forbidden_path(item, forbidden, f"{where}.{key}")
            if hit is not None:
                return hit
    elif isinstance(value, list):
        for index, item in enumerate(value):
            hit = _forbidden_path(item, forbidden, f"{where}[{index}]")
            if hit is not None:
                return hit
    return None


def _check_value(value: Any, rule: Mapping[str, Any], where: str) -> None:
    kind = rule["type"]
    if kind == "integer":
        ok = isinstance(value, int) and not isinstance(value, bool)
    elif kind == "string":
        ok = isinstance(value, str)
    elif kind == "object":
        ok = isinstance(value, Mapping)
    elif kind == "array":
        ok = isinstance(value, list)
    else:  # pragma: no cover - 冻结记录只用上面四种类型
        raise AssertionError(f"unknown rule type {kind!r}")
    if not ok:
        raise SessionError("INVALID_VALUE", f"{where} 应为 {kind}")
    if "enum" in rule and value not in rule["enum"]:
        raise SessionError("INVALID_VALUE", f"{where} 取值 {value!r} 不在 {rule['enum']}")
    if "pattern" in rule and re.fullmatch(rule["pattern"], value) is None:
        raise SessionError("INVALID_VALUE", f"{where} 不符合 {rule['pattern']}")
    if "minimum" in rule and value < rule["minimum"]:
        raise SessionError("INVALID_VALUE", f"{where} 小于 {rule['minimum']}")
    if "maximum" in rule and value > rule["maximum"]:
        raise SessionError("INVALID_VALUE", f"{where} 大于 {rule['maximum']}")


def _check_fields(obj: Mapping[str, Any], fields: Mapping[str, Any], where: str) -> None:
    """封闭字段集：多一个给 UNKNOWN_FIELD，缺一个给 MISSING_FIELD，再逐项核值。"""
    unknown = sorted(set(obj) - set(fields))
    if unknown:
        raise SessionError("UNKNOWN_FIELD", f"{where} 含未定义字段 {unknown}")
    missing = sorted(set(fields) - set(obj))
    if missing:
        raise SessionError("MISSING_FIELD", f"{where} 缺字段 {missing}")
    for name, rule in fields.items():
        _check_value(obj[name], rule, f"{where}.{name}")


class _Checker:
    """按文件顺序逐条吃记录；任何不合格都抛 ``SessionError``。"""

    def __init__(self) -> None:
        self.format: dict[str, Any] | None = None
        self.forbidden: frozenset[str] = frozenset()
        self.header: dict[str, Any] | None = None
        self.actions: list[dict[str, Any]] = []
        self.seal: dict[str, Any] | None = None
        self._limit_seqs: set[int] = set()

    def feed(self, record: Any) -> None:
        if not isinstance(record, Mapping):
            raise SessionError("NON_CANONICAL_RECORD", "记录不是 JSON 对象")
        record = dict(record)
        if self.header is None:
            self._feed_header(record)
            return
        assert self.format is not None
        hit = _forbidden_path(record, self.forbidden, "record")
        if hit is not None:
            raise SessionError("FORBIDDEN_FIELD", f"{hit} 属于对错判定、画像或身份信息")
        if self.seal is not None:
            raise SessionError("OUT_OF_ORDER", "封口行之后仍有记录")
        record_type = record.get("record_type")
        if record_type == "header":
            raise SessionError("OUT_OF_ORDER", "重复的头记录")
        if record_type == "action":
            self._feed_action(record)
        elif record_type == "seal":
            self._feed_seal(record)
        elif "record_type" not in record:
            raise SessionError("MISSING_FIELD", "记录缺 record_type")
        else:
            raise SessionError("INVALID_VALUE", f"未知 record_type {record_type!r}")

    def _feed_header(self, record: dict[str, Any]) -> None:
        if record.get("record_type") != "header":
            raise SessionError("MISSING_HEADER", "第 1 行不是头记录")
        if "format_version" not in record:
            raise SessionError("MISSING_FIELD", "头记录缺 format_version")
        version = record["format_version"]
        if (
            not isinstance(version, int)
            or isinstance(version, bool)
            or version not in FROZEN_FORMATS
        ):
            raise SessionError("UNSUPPORTED_VERSION", f"format_version {version!r} 未登记")
        self.format = load_format(version)
        self.forbidden = frozenset(self.format["forbidden_fields"]["keys"])
        hit = _forbidden_path(record, self.forbidden, "header")
        if hit is not None:
            raise SessionError("FORBIDDEN_FIELD", f"{hit} 属于对错判定、画像或身份信息")
        _check_fields(record, self.format["records"]["header"]["fields"], "header")
        self.header = record

    def _feed_action(self, record: dict[str, Any]) -> None:
        spec = self.format["records"]["action"]  # type: ignore[index]
        where = f"action[{len(self.actions) + 1}]"
        _check_fields(record, spec["fields"], where)
        _check_fields(
            record["payload"], spec["payload_by_kind"][record["kind"]], f"{where}.payload"
        )
        expected_seq = len(self.actions) + 1
        if record["action_seq"] != expected_seq:
            raise SessionError(
                "INVALID_SEQUENCE",
                f"{where} action_seq 为 {record['action_seq']}，应为 {expected_seq}",
            )
        if self.actions and record["advance_index"] < self.actions[-1]["advance_index"]:
            raise SessionError("INVALID_SEQUENCE", f"{where} advance_index 回退")
        if record["kind"] == "CANCEL":
            target = record["payload"]["target_action_seq"]
            if target not in self._limit_seqs:
                raise SessionError(
                    "INVALID_SEQUENCE", f"{where} 撤单目标 {target} 不是本会话更早的 LIMIT 动作"
                )
        elif record["kind"] == "LIMIT":
            self._limit_seqs.add(record["action_seq"])
        self.actions.append(record)

    def _feed_seal(self, record: dict[str, Any]) -> None:
        spec = self.format["records"]["seal"]  # type: ignore[index]
        _check_fields(record, spec["fields"], "seal")
        last_advance = self.actions[-1]["advance_index"] if self.actions else 0
        if record["end_advance_index"] < last_advance:
            raise SessionError("INVALID_SEQUENCE", "封口序号早于最后一条动作")
        previous = 0
        for index, item in enumerate(record["observation_digests"]):
            where = f"seal.observation_digests[{index}]"
            if not isinstance(item, Mapping):
                raise SessionError("INVALID_VALUE", f"{where} 应为 object")
            _check_fields(item, spec["observation_digest"], where)
            if item["action_seq"] <= previous or item["action_seq"] > len(self.actions):
                raise SessionError("INVALID_SEQUENCE", f"{where} action_seq 不合法")
            previous = item["action_seq"]
        expected = content_hash(self.header, self.actions)  # type: ignore[arg-type]
        if record["content_hash"] != expected:
            raise SessionError(
                "CONTENT_HASH_MISMATCH", f"封口记录 {record['content_hash']}，重算 {expected}"
            )
        self.seal = record


# --------------------------------------------------------------------------- #
# 读取与校验入口
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SessionCheck:
    """``validate_session`` 的结果。

    ``ok`` 为假时只有 ``reason_code`` / ``detail`` / ``line`` 有意义。
    """

    ok: bool
    reason_code: str | None = None
    detail: str | None = None
    line: int | None = None
    header: dict[str, Any] | None = None
    actions: tuple[dict[str, Any], ...] = ()
    seal: dict[str, Any] | None = None
    status: str | None = None
    content_hash: str | None = None
    truncated_tail: bool = False


def validate_session(data: bytes) -> SessionCheck:
    """校验一份会话文件的全部字节；不抛异常，失败给稳定原因码。"""
    lines = data.split(b"\n")
    tail = lines.pop()  # 以 \n 结尾时为空串；否则是写入中途被终止留下的残片
    truncated_tail = tail != b""
    checker = _Checker()
    for number, raw in enumerate(lines, start=1):
        try:
            try:
                record = json.loads(raw.decode("utf-8"))
                canonical = canonical_serialize(record)
            except (UnicodeDecodeError, json.JSONDecodeError, SerializationError, ValueError):
                raise SessionError("NON_CANONICAL_RECORD", "行不是合法 JSON 或含浮点数") from None
            if not isinstance(record, dict) or canonical != raw:
                raise SessionError("NON_CANONICAL_RECORD", "行不是规范序列化形态的 JSON 对象")
            checker.feed(record)
        except SessionError as exc:
            return SessionCheck(ok=False, reason_code=exc.code, detail=exc.message, line=number)
    if checker.header is None:
        return SessionCheck(
            ok=False, reason_code="MISSING_HEADER", detail="没有完整的头记录", line=1
        )
    if truncated_tail and checker.seal is not None:
        return SessionCheck(
            ok=False,
            reason_code="OUT_OF_ORDER",
            detail="封口行之后仍有残片",
            line=len(lines) + 1,
        )
    return SessionCheck(
        ok=True,
        header=checker.header,
        actions=tuple(checker.actions),
        seal=checker.seal,
        status=SEALED if checker.seal is not None else UNSEALED,
        content_hash=content_hash(checker.header, checker.actions),
        truncated_tail=truncated_tail,
    )


def load_session(path: str | os.PathLike[str]) -> SessionCheck:
    return validate_session(pathlib.Path(path).read_bytes())


# --------------------------------------------------------------------------- #
# 逐条落盘
# --------------------------------------------------------------------------- #


class SessionWriter:
    """头记录在创建时写入；动作逐条追加并分配 ``action_seq``；封口后不再接受记录。

    不线程安全：live 市场在 ``LiveMarket.lock`` 内调用（design §5）。
    """

    def __init__(self, path: pathlib.Path, handle: Any, checker: _Checker) -> None:
        self.path = path
        self._handle = handle
        self._checker = checker

    @classmethod
    def create(cls, path: str | os.PathLike[str], header: Mapping[str, Any]) -> SessionWriter:
        """新建会话文件并写入头记录；文件已存在即失败——已落盘会话不被改写。"""
        checker = _Checker()
        record = {"record_type": "header", **header}
        checker.feed(record)
        target = pathlib.Path(path)
        handle = open(target, "xb")  # noqa: SIM115 - 句柄随会话存续，由 close() 关闭
        writer = cls(target, handle, checker)
        writer._write(record)
        return writer

    @property
    def header(self) -> dict[str, Any]:
        assert self._checker.header is not None
        return dict(self._checker.header)

    @property
    def actions(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._checker.actions)

    @property
    def sealed(self) -> bool:
        return self._checker.seal is not None

    @property
    def content_hash(self) -> str:
        assert self._checker.header is not None
        return content_hash(self._checker.header, self._checker.actions)

    def append_action(
        self,
        *,
        advance_index: int,
        kind: str,
        payload: Mapping[str, Any],
        wall_clock_ms: int,
    ) -> dict[str, Any]:
        """追加一条动作并返回它（含分配的 ``action_seq``）；不合格即抛、不写。"""
        record = {
            "record_type": "action",
            "advance_index": advance_index,
            "action_seq": len(self._checker.actions) + 1,
            "kind": kind,
            "payload": dict(payload),
            "wall_clock_ms": wall_clock_ms,
        }
        self._feed_and_write(record)
        return record

    def seal(
        self,
        *,
        end_advance_index: int,
        event_digest: str,
        observation_digests: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        record = {
            "record_type": "seal",
            "end_advance_index": end_advance_index,
            "event_digest": event_digest,
            "observation_digests": [dict(item) for item in observation_digests],
            "content_hash": self.content_hash,
        }
        self._feed_and_write(record)
        self.close()
        return record

    def close(self) -> None:
        if not self._handle.closed:
            self._handle.close()

    def _feed_and_write(self, record: dict[str, Any]) -> None:
        if self._handle.closed and not self.sealed:
            raise SessionError("OUT_OF_ORDER", "会话已关闭")
        self._checker.feed(record)
        self._write(record)

    def _write(self, record: Mapping[str, Any]) -> None:
        self._handle.write(record_line(record))
        self._handle.flush()
        os.fsync(self._handle.fileno())
