#!/usr/bin/env python3
"""设计阶段真源自校验器（纯标准库）。

两份机器真源在被任何实现消费之前，必须先通过对**自身**的校验：

- `src/market_game_sim/schema/event_fields.json`  —— 事件字段规范
- `specs/v0.1-belief-testing-laboratory/traceability.json` —— 需求追踪

第 33 章总结过一条原则：**每引入一个「唯一真源」，必须同时引入检验它唯一性的手段**，
否则它只是多了一个可以漂移的地方。本脚本就是那个手段——它在设计阶段可运行，
不依赖任何尚未实现的内核代码。

用法：
    python tools/validate_contract_sources.py
退出码 0 表示全部通过；非 0 时逐条打印失败原因。
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "src" / "market_game_sim" / "schema" / "event_fields.json"
TRACE = ROOT / "specs" / "v0.1-belief-testing-laboratory" / "traceability.json"
SPEC = ROOT / "specs" / "v0.1-belief-testing-laboratory" / "spec.md"

# 需求 ID 的声明形态在 spec 中是固定的机械模式：`- **FR-001**：` 或 `### US-1：`。
# T607 据此提取「已声明的 ID 集合」，与 JSON 比对。这不是解析矩阵，只是提取 ID——
# 因此不构成「JSON 自己既是待检集合又是期望集合」的恒真断言。
DECL_PATTERNS = (
    re.compile(r"^- \*\*((?:FR|KR|NFR|SC)-\d{3})\*\*", re.M),
    re.compile(r"^### (US-\d)：", re.M),
)


def _fail(errors: list[str], msg: str) -> None:
    errors.append(msg)


def validate_schema(errors: list[str]) -> None:
    d = json.loads(SCHEMA.read_text(encoding="utf-8"))
    meta = d["meta"]
    grammar = meta["constraint_grammar"]

    shape = grammar["object_shape"]
    allowed_keys = set(shape["required_keys"]) | set(shape["optional_keys"])
    then_values = set(grammar["then_values"])
    when_forms = {frozenset(f["keys"]): f for f in grammar["when_forms"]}

    for sname, sdef in d["structures"].items():
        fields = sdef["fields"]
        declared = sdef.get("leaf_field_count")
        if declared is not None and declared != len(fields):
            _fail(errors, f"{sname}: leaf_field_count={declared} 与实际 {len(fields)} 不符")

        for fname, fd in fields.items():
            where = f"{sname}.{fname}"
            if fd.get("required") != "always":
                _fail(errors, f"{where}: required 必须为 always（字段恒存在，§9 禁止省略）")
            if fd.get("value_type") == "enum" and "enum" not in fd:
                _fail(errors, f"{where}: enum 类型缺 enum 值域")
            if fd.get("hash") not in ("HASH_INCLUDE", "HASH_EXCLUDE"):
                _fail(errors, f"{where}: hash 分类缺失或非法")

            constraints = fd.get("constraints")
            if fd.get("nullable") and not constraints:
                _fail(errors, f"{where}: 可空字段必须声明 constraints")
            for c in constraints or []:
                extra = set(c) - allowed_keys
                if extra:
                    _fail(errors, f"{where}: constraint 含未声明键 {sorted(extra)}")
                if "when" not in c or "then" not in c:
                    _fail(errors, f"{where}: constraint 缺 when 或 then -> {c}")
                    continue
                if c["then"] not in then_values:
                    _fail(errors, f"{where}: then={c['then']!r} 不在 {sorted(then_values)}")
                form = when_forms.get(frozenset(c["when"]))
                if form is None:
                    _fail(errors, f"{where}: when 形状 {sorted(c['when'])} 未在 grammar 中声明")
                    continue
                ref = c["when"].get("field")
                if ref is not None and ref not in fields:
                    _fail(errors, f"{where}: when 引用了本结构不存在的字段 {ref!r}")
                domain = form.get("domain")
                if domain:
                    val = next(iter(c["when"].values()))
                    if val not in domain:
                        _fail(errors, f"{where}: when 操作数 {val!r} 不在 {domain}")


def validate_trace(errors: list[str]) -> None:
    d = json.loads(TRACE.read_text(encoding="utf-8"))
    milestones = d["milestones"]
    statuses = set(d["statuses"])

    declared: set[str] = set()
    spec_text = SPEC.read_text(encoding="utf-8")
    for pat in DECL_PATTERNS:
        declared |= set(pat.findall(spec_text))

    tracked = set(d["requirements"])
    missing = declared - tracked
    extra = tracked - declared
    if missing:
        _fail(errors, f"traceability 遗漏 spec 已声明的 ID：{sorted(missing)}")
    if extra:
        _fail(errors, f"traceability 含 spec 未声明的 ID：{sorted(extra)}")

    for rid, r in d["requirements"].items():
        if r["status"] not in statuses:
            _fail(errors, f"{rid}: status={r['status']!r} 非法")
        if r["status"] == "owned":
            if not r["owners"]:
                _fail(errors, f"{rid}: status=owned 但 owners 为空")
            scopes = [o.get("scope") for o in r["owners"]]
            if len(r["owners"]) > 1 and any(not s for s in scopes):
                _fail(errors, f"{rid}: 多 owner 必须逐个声明 scope（证明无重叠、无遗漏）")
            for o in r["owners"]:
                m = o["milestone"]
                if m not in milestones:
                    _fail(errors, f"{rid}: 未知里程碑 {m}")
                    continue
                spec_path = ROOT / milestones[m] / "spec.md"
                if not spec_path.exists():
                    _fail(errors, f"{rid}: 里程碑 spec 不存在 {spec_path}")
                    continue
                text = spec_path.read_text(encoding="utf-8")
                for e in o["exits"]:
                    if not re.search(rf"^\|\s*{re.escape(e)}\s*\|", text, re.M):
                        _fail(errors, f"{rid}: {m} 的退出条件表中找不到 {e}")
        elif r["status"] == "deferred" and not r.get("defer_to"):
            _fail(errors, f"{rid}: status=deferred 但缺 defer_to")


def main() -> int:
    errors: list[str] = []
    validate_schema(errors)
    validate_trace(errors)
    if errors:
        print(f"真源自校验失败（{len(errors)} 项）：")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("真源自校验通过：event_fields.json + traceability.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
