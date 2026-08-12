#!/usr/bin/env python3
"""设计阶段真源自校验器（纯标准库）。

三份机器真源在被任何实现消费之前，必须先通过对**自身**以及**与合同文档**的校验：

- `src/market_game_sim/schema/event_fields.json`  —— 事件字段规范
- `src/market_game_sim/schema/report_artifacts.json` —— 0.1.4 报告输入 artifact Schema
- `docs/features/0.1/traceability.json` —— 需求追踪

第 33 章总结过一条原则：**每引入一个「唯一真源」，必须同时引入检验它唯一性的手段**，
否则它只是多了一个可以漂移的地方。

第 36 章给出了这条原则的反例，且反例就在本仓库里：JSON 给 `ORDER_CANCELLED` 新增
`order_type` 后，合同字段表、E-002 哈希清单、OB 向量与字段计数**全都没同步**，而本
脚本当时仍返回成功——因为它只检查了 JSON 内部的形状，没有做跨真源比较。
**「JSON 自洽」与「JSON 是唯一真源」是两件事。** §跨真源 一节的检查就是补这个洞。

所有校验函数都接收 `data`/`text` 而非硬编码读文件，以便测试注入变异输入——
只测 happy path 无法证明这些门真的会挡住错误（第 36 章 P1-U02）。

用法：
    python tools/validate_contract_sources.py
退出码 0 表示全部通过；非 0 时逐条打印失败原因。
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import spec_validation

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "src" / "market_game_sim" / "schema" / "event_fields.json"
ARTIFACT_SCHEMAS = ROOT / "src" / "market_game_sim" / "schema" / "report_artifacts.json"
TRACE = ROOT / "docs" / "features" / "0.1" / "traceability.json"
SPEC = ROOT / "docs" / "features" / "0.1" / "spec.md"
EVENT_SCHEMA_DOC = ROOT / "docs" / "contracts" / "event-schema.md"
REPORT_SPEC = ROOT / "docs" / "features" / "0.1" / "0.1.4-replay-and-report" / "spec.md"

ARTIFACT_FIELD_TYPES = {"string", "integer", "number", "boolean", "object", "array"}
ARTIFACT_SCALAR_TYPES = {"string", "integer", "number", "boolean"}
_KNOWN_CHARSETS = {"lowercase_hex"}

#: Closed set of artifact-level keys in the registry. ``format`` is BOTH the
#: upstream producer encoding AND the report consumption format: every
#: artifact is currently ``json`` (JSON table/object); ``parquet`` remains an
#: enum value for future archive-only producers but is NOT consumable by the
#: stdlib report layer (no parquet dependency, ADR-004/T507 boundary).
#: ``nullable`` allows an object artifact's value to be JSON null.
_ARTIFACT_KEYS = {
    "producer",
    "format",
    "shape",
    "nullable",
    "schema_version",
    "required_fields",
}
_ARTIFACT_FORMATS = {"json", "parquet"}


def _fail(errors: list[str], msg: str) -> None:
    errors.append(msg)


# --------------------------------------------------------------------------- #
# event_fields.json 自身
# --------------------------------------------------------------------------- #


def validate_schema_data(d: dict, errors: list[str]) -> None:
    meta = d["meta"]
    grammar = meta["constraint_grammar"]

    shape = grammar["object_shape"]
    allowed_keys = set(shape["required_keys"]) | set(shape["optional_keys"])
    then_values = set(grammar["then_values"])
    when_forms = {frozenset(f["keys"]): f for f in grammar["when_forms"]}
    value_types = set(meta["value_types"])
    structures = d["structures"]

    for sname, sdef in structures.items():
        fields = sdef["fields"]
        declared = sdef.get("leaf_field_count")
        if declared is not None and declared != len(fields):
            _fail(errors, f"{sname}: leaf_field_count={declared} 与实际 {len(fields)} 不符")

        for fname, fd in fields.items():
            where = f"{sname}.{fname}"
            if fd.get("required") != "always":
                _fail(errors, f"{where}: required 必须为 always（字段恒存在，§9 禁止省略）")
            if fd.get("value_type") not in value_types:
                _fail(errors, f"{where}: value_type={fd.get('value_type')!r} 不在 meta.value_types")
            if fd.get("value_type") == "enum" and "enum" not in fd:
                _fail(errors, f"{where}: enum 类型缺 enum 值域")
            if fd.get("hash") not in ("HASH_INCLUDE", "HASH_EXCLUDE"):
                _fail(errors, f"{where}: hash 分类缺失或非法")

            _validate_array_contract(where, fd, structures, errors)
            _validate_constraints(where, fd, fields, allowed_keys, then_values, when_forms, errors)


def _validate_array_contract(where: str, fd: dict, structures: dict, errors: list[str]) -> None:
    """数组字段的 element_structure / array_order / length 必须结构化且引用有效。"""
    if fd.get("value_type") != "array":
        return
    elem = fd.get("element_structure")
    if elem is None:
        _fail(errors, f"{where}: array 字段缺 element_structure")
    elif elem not in structures:
        _fail(errors, f"{where}: element_structure={elem!r} 指向不存在的结构")

    order = fd.get("array_order")
    if not isinstance(order, dict) or "kind" not in order:
        _fail(errors, f"{where}: array_order 必须是带 kind 的结构化对象，不能是自由文本")
    elif order["kind"] == "sort_by":
        target = structures.get(elem, {}).get("fields", {})
        if order.get("field") not in target:
            _fail(errors, f"{where}: array_order.field={order.get('field')!r} 不是 {elem} 的字段")

    length = fd.get("length")
    if length is not None and not isinstance(length, dict):
        _fail(errors, f"{where}: length 必须是结构化对象（带 kind），不能是自由文本")


def _validate_constraints(
    where: str,
    fd: dict,
    fields: dict,
    allowed_keys: set,
    then_values: set,
    when_forms: dict,
    errors: list[str],
) -> None:
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

        when = c["when"]
        form = when_forms.get(frozenset(when))
        if form is None:
            _fail(errors, f"{where}: when 形状 {sorted(when)} 未在 grammar 中声明")
            continue

        ref = when.get("field")
        if ref is not None:
            if ref not in fields:
                _fail(errors, f"{where}: when 引用了本结构不存在的字段 {ref!r}")
            else:
                # 被引用字段若是枚举，操作数必须落在其值域内——否则该 constraint 永远
                # 触发不了，是一条静默失效的规则。
                domain = fields[ref].get("enum")
                operands = when.get("in", [when.get("equals")])
                if domain is not None:
                    for op in operands:
                        if isinstance(op, str) and op not in domain:
                            _fail(
                                errors,
                                f"{where}: when 操作数 {op!r} 不在 {ref} 的 enum {domain}",
                            )

        # grammar 声明的 domain / operand_types。
        # `field` 是【字段引用】不是操作数——same_record_equals/in 的操作数在
        # equals/in 里，且已在上面按被引用字段的 enum 值域校验过。
        if "field" in when:
            continue
        form_domain = form.get("domain")
        key = next(iter(when))
        val = when[key]
        if form_domain and val not in form_domain:
            _fail(errors, f"{where}: when 操作数 {val!r} 不在 {form_domain}")
        if "bool" in form.get("operand_types", []) and not isinstance(val, bool):
            _fail(errors, f"{where}: when.{key} 应为 bool，实为 {type(val).__name__}")


# --------------------------------------------------------------------------- #
# 跨真源：JSON ↔ 事件 Schema 合同文档
# --------------------------------------------------------------------------- #


def validate_schema_against_doc(d: dict, doc: str, errors: list[str]) -> None:
    """把 T204f3 的跨真源比较提前到设计阶段。

    这一节存在的唯一理由是第 36 章的实例：`order_type` 只进了 JSON，文档、E-002 与
    向量都没跟上，而当时的校验器返回成功。
    """
    structures = d["structures"]

    # ① JSON 中的每个字段名都必须在合同文档里出现过至少一次。
    #    新增字段却忘了写进文档时，这一条立刻失败。
    #    反引号内允许限定写法：`payload.exchange`、`postings[]` 都算提到了。
    mentioned = _backtick_tokens(doc)
    for sname, sdef in structures.items():
        for fname in sdef["fields"]:
            if fname not in mentioned:
                _fail(errors, f"{sname}.{fname}: JSON 中存在，但合同文档从未提及")

    # ② E-002 的哈希清单必须与 JSON 的 HASH_INCLUDE 集合逐事件相等。
    #    这是最容易漂移、也最危险的一处：漏一个字段就意味着它静默逃出 KPI-002。
    for etype, listed in _parse_e002_table(doc).items():
        sdef = structures.get(etype)
        if sdef is None:
            _fail(errors, f"E-002 列出了 JSON 中不存在的事件类型 {etype}")
            continue
        own = set(sdef["fields"])
        expected = {k for k, v in sdef["fields"].items() if v["hash"] == "HASH_INCLUDE"}
        missing = expected - listed
        # 单元格里还会出现嵌套叶字段名（如 intents[] 的 side/price_ticks），
        # 它们不是本结构的字段，不参与「多列」判定。
        extra = (listed & own) - expected
        if missing:
            _fail(errors, f"E-002 {etype}: 漏列 JSON 中标为 HASH_INCLUDE 的字段 {sorted(missing)}")
        if extra:
            _fail(errors, f"E-002 {etype}: 多列了 JSON 中非 HASH_INCLUDE 的字段 {sorted(extra)}")

    # ③ 文档中凡写「N 项，封闭」处，N 必须与该结构的字段数相等。
    for sname, count in _parse_closed_counts(doc).items():
        actual = len(structures[sname]["fields"]) if sname in structures else None
        if actual is None:
            _fail(errors, f"封闭表引用了不存在的结构 {sname}")
        elif actual != count:
            _fail(errors, f"{sname}: 文档写「{count} 项，封闭」，JSON 实为 {actual} 项")


_E002_ROW = re.compile(r"^\| `([A-Z_]+)` \| (.+?) \|$", re.M)
# 只取 E-002 表；用「纳入哈希的字段」表头定位，避免误吃 §3 的优先级表。
_E002_SECTION = re.compile(r"\| 事件类型 \| 纳入哈希的字段 \|.*?\n\n", re.S)


def _parse_e002_table(doc: str) -> dict[str, set[str]]:
    m = _E002_SECTION.search(doc)
    if not m:
        return {}
    out: dict[str, set[str]] = {}
    for etype, cell in _E002_ROW.findall(m.group(0)):
        # 单元格里除字段名外还有说明文字与嵌套引用，只取反引号内的标识符。
        out[etype] = _backtick_tokens(cell)
    return out


_FENCE = re.compile(r"```.*?```", re.S)


def _backtick_tokens(text: str) -> set[str]:
    """取行内反引号中的标识符，拆开 `a.b` 与 `name[]` 这类限定写法。

    必须**先剥掉三反引号围栏块**：否则围栏的 ``` 会打乱行内反引号的配对，
    使匹配结果变成大段散文而不是标识符。
    """
    tokens: set[str] = set()
    for raw in re.findall(r"`([^`]+?)`", _FENCE.sub("", text)):
        for part in re.split(r"[.\[\]]", raw):
            if re.fullmatch(r"[a-z][a-z0-9_]*", part):
                tokens.add(part)
    return tokens


_CLOSED_COUNT = re.compile(r"\*\*(\w+)\*\*（\*\*?(\d+)\*\*? 项，封闭）")
_CLOSED_COUNT_ALT = re.compile(r"`(\w+)`(?:[^\n]{0,40}?)（共 \*\*?(\d+)\*\*? 项")


def _parse_closed_counts(doc: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for pat in (_CLOSED_COUNT, _CLOSED_COUNT_ALT):
        for name, n in pat.findall(doc):
            out[name] = int(n)
    return out


# --------------------------------------------------------------------------- #
# report_artifacts.json 自身及与 0.1.4 spec 的一致性
# --------------------------------------------------------------------------- #


def validate_artifact_schema_data(d: dict, errors: list[str]) -> None:
    """冻结全部报告输入的格式、版本和递归最小字段集合。"""
    if not isinstance(d.get("registry_version"), int) or d["registry_version"] < 1:
        _fail(errors, "report artifacts: registry_version 必须为正整数")
    if not isinstance(d.get("schema_id"), str) or not d["schema_id"]:
        _fail(errors, "report artifacts: schema_id 必须为非空字符串")

    artifacts = d.get("artifacts")
    if not isinstance(artifacts, dict):
        _fail(errors, "report artifacts: artifacts 必须为对象")
        return

    for artifact_id, artifact in artifacts.items():
        where = f"report artifacts.{artifact_id}"
        if not re.fullmatch(r"[a-z][a-z0-9_]*", artifact_id):
            _fail(errors, f"{where}: artifact_id 必须为 snake_case")
        if not isinstance(artifact, dict):
            _fail(errors, f"{where}: 定义必须为对象")
            continue
        if extra := set(artifact) - _ARTIFACT_KEYS:
            _fail(errors, f"{where}: 含未知 artifact 级属性 {sorted(extra)}")
        if not re.fullmatch(r"0\.1\.[23] T\d+", artifact.get("producer", "")):
            _fail(errors, f"{where}: producer 必须是精确的 0.1.2/0.1.3 task")
        artifact_format = artifact.get("format")
        if artifact_format not in _ARTIFACT_FORMATS:
            _fail(errors, f"{where}: format 只能是 {sorted(_ARTIFACT_FORMATS)}")
        if "nullable" in artifact and not isinstance(artifact["nullable"], bool):
            _fail(errors, f"{where}: nullable 必须为 bool")
        # format 与 shape 解耦：parquet 必须为 table（归档语义）；json 可为
        # table（JSON 表格投影）或 object（JSON 对象）。
        if artifact_format == "parquet" and artifact.get("shape") != "table":
            _fail(errors, f"{where}: parquet 的 shape 必须为 table")
        if artifact_format == "json" and artifact.get("shape") not in {"table", "object"}:
            _fail(errors, f"{where}: json 的 shape 必须为 table 或 object")
        if not isinstance(artifact.get("schema_version"), int) or artifact["schema_version"] < 1:
            _fail(errors, f"{where}: schema_version 必须为正整数")
        fields = artifact.get("required_fields")
        if not isinstance(fields, dict) or not fields:
            _fail(errors, f"{where}: required_fields 必须为非空对象")
            continue
        if fields.get("schema_version") != {"type": "integer"}:
            _fail(errors, f"{where}: 内容必须带 integer 类型的 schema_version")
        _validate_artifact_fields(fields, where, errors)


def _validate_artifact_fields(fields: dict, parent: str, errors: list[str]) -> None:
    for field_name, field in fields.items():
        where = f"{parent}.{field_name}"
        if not re.fullmatch(r"[a-z][a-z0-9_]*", field_name):
            _fail(errors, f"{where}: 字段名必须为 snake_case")
        if not isinstance(field, dict):
            _fail(errors, f"{where}: 字段定义必须为对象")
            continue
        allowed = {
            "type",
            "nullable",
            "required_fields",
            "additional_value_type",
            "item_type",
            "item_fields",
            "enum",
            "hex_length",
            "charset",
        }
        if extra := set(field) - allowed:
            _fail(errors, f"{where}: 含未知 Schema 属性 {sorted(extra)}")
        field_type = field.get("type")
        if field_type not in ARTIFACT_FIELD_TYPES:
            _fail(errors, f"{where}: type={field_type!r} 非法")
        if "nullable" in field and not isinstance(field["nullable"], bool):
            _fail(errors, f"{where}: nullable 必须为 bool")
        if "enum" in field:
            enum_values = field["enum"]
            if not isinstance(enum_values, list) or not enum_values:
                _fail(errors, f"{where}: enum 必须为非空数组")
            elif field_type == "string" and not all(isinstance(v, str) for v in enum_values):
                _fail(errors, f"{where}: type=string 的 enum 元素必须都是字符串")
        if "hex_length" in field:
            hex_length = field["hex_length"]
            if field_type != "string":
                _fail(errors, f"{where}: hex_length 只能用于 type=string")
            if (
                not isinstance(hex_length, int)
                or isinstance(hex_length, bool)
                or hex_length <= 0
                or hex_length % 2 != 0
            ):
                _fail(errors, f"{where}: hex_length 必须为正偶数（十六进制每字节 2 字符）")
        if "charset" in field:
            if field_type != "string":
                _fail(errors, f"{where}: charset 只能用于 type=string")
            if field["charset"] not in _KNOWN_CHARSETS:
                _fail(
                    errors,
                    f"{where}: charset={field['charset']!r} 不在已知集合 {sorted(_KNOWN_CHARSETS)}",
                )

        if field_type == "object":
            nested = field.get("required_fields")
            additional = field.get("additional_value_type")
            if nested is not None and additional is not None:
                _fail(errors, f"{where}: required_fields 与 additional_value_type 只能选一个")
            elif nested is not None:
                if not isinstance(nested, dict) or not nested:
                    _fail(errors, f"{where}: required_fields 必须为非空对象")
                else:
                    _validate_artifact_fields(nested, where, errors)
            elif additional not in ARTIFACT_SCALAR_TYPES | {"json-value"}:
                _fail(
                    errors,
                    f"{where}: object 必须冻结 required_fields 或 additional_value_type",
                )
        elif field_type == "array":
            item_type = field.get("item_type")
            if item_type not in ARTIFACT_SCALAR_TYPES | {"object"}:
                _fail(errors, f"{where}: array.item_type={item_type!r} 非法")
            elif item_type == "object":
                item_fields = field.get("item_fields")
                if not isinstance(item_fields, dict) or not item_fields:
                    _fail(errors, f"{where}: object 数组必须冻结非空 item_fields")
                else:
                    _validate_artifact_fields(item_fields, f"{where}[]", errors)


# manifest 逐 artifact 的七字段封闭清单（spec.md §4.1 与本文件 manifest_schema
# 双向核对的对象，见 validate_manifest_schema_against_spec）。
_MANIFEST_ARTIFACT_ENTRY_FIELDS = {
    "artifact_id",
    "path",
    "format",
    "schema_version",
    "producer",
    "hash_algorithm",
    "hash",
}


def validate_manifest_schema_data(d: dict, errors: list[str]) -> None:
    """冻结 artifact manifest 顶层结构，及逐 artifact 七字段封闭清单。"""
    schema = d.get("manifest_schema")
    if not isinstance(schema, dict):
        _fail(errors, "report artifacts: 缺 manifest_schema")
        return
    top = schema.get("top_level_fields")
    if not isinstance(top, dict):
        _fail(errors, "manifest_schema: top_level_fields 必须为对象")
        return
    if set(top) != {"manifest_version", "artifact_root", "artifacts"}:
        _fail(errors, f"manifest_schema: 顶层字段集合非法 {sorted(top)}")
        return
    _validate_artifact_fields(top, "manifest_schema", errors)
    entry_fields = top.get("artifacts", {}).get("item_fields", {})
    if set(entry_fields) != _MANIFEST_ARTIFACT_ENTRY_FIELDS:
        _fail(
            errors,
            "manifest_schema.artifacts[]: 字段集合必须恰为七项封闭清单 "
            f"{sorted(_MANIFEST_ARTIFACT_ENTRY_FIELDS)}，实际 {sorted(entry_fields)}",
        )
        return

    # 通用 shape 校验（_validate_artifact_fields）只保证「合法枚举/合法正偶数」，
    # 不保证「就是这个业务值」——round 4 复核证明 hex_length=62 会被 shape 校验
    # 放行。这里补精确值断言，与 hash_algorithm 的单元素 enum 同一层级严格度。
    hash_algorithm_def = entry_fields.get("hash_algorithm", {})
    if hash_algorithm_def.get("enum") != ["blake2b"]:
        _fail(
            errors,
            "manifest_schema.artifacts[].hash_algorithm: enum 必须精确为 ['blake2b']，"
            f"实际 {hash_algorithm_def.get('enum')!r}",
        )
    hash_def = entry_fields.get("hash", {})
    if hash_def.get("hex_length") != 64:
        _fail(
            errors,
            "manifest_schema.artifacts[].hash: hex_length 必须精确为 64"
            f"（blake2b digest_size=32），实际 {hash_def.get('hex_length')!r}",
        )
    if hash_def.get("charset") != "lowercase_hex":
        _fail(
            errors,
            "manifest_schema.artifacts[].hash: charset 必须精确为 'lowercase_hex'，"
            f"实际 {hash_def.get('charset')!r}",
        )


_MANIFEST_FIELD_LIST_ITEM = re.compile(r"^\s*\d+\.\s+`([a-z][a-z0-9_]*)`", re.M)
_SPEC_HASH_LENGTH = re.compile(r"固定\s*(\d+)\s*位十六进制小写摘要")


def validate_manifest_schema_against_spec(d: dict, spec_text: str, errors: list[str]) -> None:
    """spec.md §4.1 展示的七字段编号列表必须与机器 manifest_schema 双向一致。"""
    entry_fields = (
        d.get("manifest_schema", {})
        .get("top_level_fields", {})
        .get("artifacts", {})
        .get("item_fields", {})
    )
    shown = set(_MANIFEST_FIELD_LIST_ITEM.findall(spec_text))
    if shown != set(entry_fields):
        _fail(
            errors,
            f"report artifacts: manifest 七字段 spec 展示 {sorted(shown)} 与"
            f" 机器 Schema {sorted(entry_fields)} 不一致",
        )

    spec_lengths = {int(n) for n in _SPEC_HASH_LENGTH.findall(spec_text)}
    machine_length = entry_fields.get("hash", {}).get("hex_length")
    if spec_lengths and machine_length not in spec_lengths:
        _fail(
            errors,
            f"report artifacts: spec 展示的 hash 位数 {sorted(spec_lengths)} 与"
            f" 机器 Schema hex_length={machine_length!r} 不一致",
        )


_REPORT_ARTIFACT_ROW = re.compile(
    r"^\| `([a-z][a-z0-9_]*)` \| \*{0,2}(0\.1\.[23] T\d+)\*{0,2} \|", re.M
)


def validate_artifact_schemas_against_spec(d: dict, spec_text: str, errors: list[str]) -> None:
    """机器 registry 的 artifact ID/producer 必须与 0.1.4 展示表双向一致。"""
    rows = _REPORT_ARTIFACT_ROW.findall(spec_text)
    shown = dict(rows)
    if len(rows) != len(shown):
        _fail(errors, "report artifacts: spec 展示表含重复 artifact_id")
    actual = {
        artifact_id: artifact.get("producer")
        for artifact_id, artifact in d.get("artifacts", {}).items()
        if isinstance(artifact, dict)
    }
    if shown != actual:
        _fail(errors, f"report artifacts: spec 展示表 {shown} 与机器 Schema {actual} 不一致")


# --------------------------------------------------------------------------- #
# traceability.json
# --------------------------------------------------------------------------- #


def validate_trace_data(d: dict, spec_text: str, errors: list[str], root: pathlib.Path) -> None:
    """复用 spec_validation 的 owner/path/exit 判据，并补充渲染矩阵与预注册对照。"""
    spec_validation.validate_trace_data(d, spec_text, errors, root)

    _validate_rendered_matrix(d, spec_text, errors)
    _validate_preregistration(d, spec_text, errors)


_MATRIX_ROW = re.compile(r"^\| \*{0,2}((?:US|FR|KR|NFR|SC)-\d+)[^|]*\| ([^|]+) \|", re.M)


def validate_rendered_matrix(d: dict, spec_text: str, errors: list[str]) -> None:
    _validate_rendered_matrix(d, spec_text, errors)


def _validate_rendered_matrix(d: dict, spec_text: str, errors: list[str]) -> None:
    """spec 展示表的归属里程碑必须与 JSON 一致。

    没有这条时，机器源改了而读者看到旧表——NFR-002 就曾出现「表写『各里程碑各自』、
    JSON 只有 0.1.1」而 CI 全绿的情况。
    """
    for rid, owner_cell in _MATRIX_ROW.findall(spec_text):
        r = d["requirements"].get(rid)
        if r is None or r["status"] != "owned":
            continue
        shown = set(re.findall(r"0\.1\.\d", owner_cell))
        actual = {o["milestone"] for o in r["owners"]}
        if shown and shown != actual:
            _fail(errors, f"展示表 {rid}: 表内里程碑 {sorted(shown)} 与 JSON {sorted(actual)} 不符")


def _validate_preregistration(d: dict, spec_text: str, errors: list[str]) -> None:
    """`preregistration` 也是真源的一部分，同样要与 spec 的 P-* 标题集合对照。"""
    pre = d.get("preregistration", {})
    declared = set(re.findall(r"^### (P-\d+)：", spec_text, re.M))
    tracked = {k for k in pre if k.startswith("P-")}
    if missing := declared - tracked:
        _fail(errors, f"preregistration 遗漏 spec 已声明的 {sorted(missing)}")
    if extra := tracked - declared:
        _fail(errors, f"preregistration 含 spec 未声明的 {sorted(extra)}")
    for pid, entry in pre.items():
        if not pid.startswith("P-"):
            continue
        if entry.get("status") == "deferred" and not entry.get("defer_to"):
            _fail(errors, f"{pid}: deferred 但缺 defer_to")


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #


def validate_schema(errors: list[str]) -> None:
    d = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validate_schema_data(d, errors)
    validate_schema_against_doc(d, EVENT_SCHEMA_DOC.read_text(encoding="utf-8"), errors)


def validate_artifact_schemas(errors: list[str]) -> None:
    d = json.loads(ARTIFACT_SCHEMAS.read_text(encoding="utf-8"))
    validate_artifact_schema_data(d, errors)
    validate_artifact_schemas_against_spec(d, REPORT_SPEC.read_text(encoding="utf-8"), errors)
    validate_manifest_schema_data(d, errors)
    validate_manifest_schema_against_spec(d, REPORT_SPEC.read_text(encoding="utf-8"), errors)


def validate_trace(errors: list[str]) -> None:
    d = json.loads(TRACE.read_text(encoding="utf-8"))
    validate_trace_data(d, SPEC.read_text(encoding="utf-8"), errors, ROOT)


def main() -> int:
    errors: list[str] = []
    validate_schema(errors)
    validate_artifact_schemas(errors)
    validate_trace(errors)
    if errors:
        print(f"真源自校验失败（{len(errors)} 项）：")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(
        "真源自校验通过：event_fields.json + report_artifacts.json + "
        "traceability.json（含跨真源比较）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
