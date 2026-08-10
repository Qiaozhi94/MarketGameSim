"""真源自校验：`tools/validate_contract_sources.py` 的 pytest 入口。

同一套判据有两个触发点，**共用同一份实现**（不是两份手抄逻辑）：

- CI 的 `contract-sources` job：不装任何依赖，最先跑，失败即中止后续；
- 本地 `pytest`：开发者不必记住还有个脚本要跑。

**本文件的重点是负向变异测试。** 只断言「当前仓库通过」无法证明校验器在挡任何东西
——删掉一段校验逻辑，happy-path 测试仍然全绿。第 36 章正是这样发现
`ORDER_CANCELLED.order_type` 漂移的：CI 绿着，而 JSON 与文档已经不一致。

因此下面每个 `mutate_*` 都**先破坏一处真源，再断言校验器给出预期错误**。
新增校验规则时应同时新增一条变异，否则那条规则等于没有被测试。
"""

from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "tools" / "validate_contract_sources.py"


def _load_validator():
    """按路径加载 `tools/` 下的脚本——它不是包的一部分，不能直接 import。"""
    spec = importlib.util.spec_from_file_location("validate_contract_sources", VALIDATOR)
    assert spec and spec.loader, f"无法加载 {VALIDATOR}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def validator():
    return _load_validator()


@pytest.fixture(scope="module")
def schema(validator) -> dict:
    return json.loads(validator.SCHEMA.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def artifact_schemas(validator) -> dict:
    return json.loads(validator.ARTIFACT_SCHEMAS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def trace(validator) -> dict:
    return json.loads(validator.TRACE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def spec_text(validator) -> str:
    return validator.SPEC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def schema_doc(validator) -> str:
    return validator.EVENT_SCHEMA_DOC.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# 正向：当前仓库自洽
# --------------------------------------------------------------------------- #


def test_repository_sources_are_consistent(validator):
    """当前仓库的两份真源与合同文档一致——脚本入口返回 0。"""
    assert validator.main() == 0


# --------------------------------------------------------------------------- #
# 负向：schema 自身
# --------------------------------------------------------------------------- #


def _mutate_unknown_predicate(d: dict) -> None:
    d["structures"]["MARGIN_CALL"]["fields"]["chain_id"]["constraints"] = [
        {"when": {"phase_of_moon": "waxing"}, "then": "null"}
    ]


def _mutate_bad_then(d: dict) -> None:
    d["structures"]["MARGIN_CALL"]["fields"]["chain_id"]["constraints"] = [
        {"when": {"always": True}, "then": "maybe_null"}
    ]


def _mutate_comment_only_constraint(d: dict) -> None:
    d["structures"]["MARGIN_CALL"]["fields"]["chain_id"]["constraints"] = [
        {"note": "只有说明、没有 when/then"}
    ]


def _mutate_dangling_field_ref(d: dict) -> None:
    d["structures"]["ORDER_ARRIVAL"]["fields"]["side"]["constraints"] = [
        {"when": {"field": "no_such_field", "equals": "SUBMIT"}, "then": "null"}
    ]


def _mutate_operand_outside_enum(d: dict) -> None:
    d["structures"]["ORDER_ARRIVAL"]["fields"]["side"]["constraints"] = [
        {"when": {"field": "action", "equals": "TELEPORT"}, "then": "null"}
    ]


def _mutate_leaf_count(d: dict) -> None:
    d["structures"]["WRITE_OFF_POSTING"]["leaf_field_count"] = 99


def _mutate_conditional_required(d: dict) -> None:
    d["structures"]["ORDER_ARRIVAL"]["fields"]["side"]["required"] = "conditional"


def _mutate_freetext_array_order(d: dict) -> None:
    d["structures"]["TRADE_SETTLE"]["fields"]["postings"]["array_order"] = "先 maker 后 taker"


def _mutate_dangling_element_structure(d: dict) -> None:
    d["structures"]["TRADE_SETTLE"]["fields"]["postings"]["element_structure"] = "NO_SUCH"


def _mutate_nullable_without_constraints(d: dict) -> None:
    d["structures"]["MARGIN_CALL"]["fields"]["chain_id"].pop("constraints")


SCHEMA_MUTATIONS = [
    pytest.param(_mutate_unknown_predicate, "未在 grammar 中声明", id="未声明谓词"),
    pytest.param(_mutate_bad_then, "不在", id="非法 then 值"),
    pytest.param(_mutate_comment_only_constraint, "缺 when 或 then", id="只有注释的 constraint"),
    pytest.param(_mutate_dangling_field_ref, "不存在的字段", id="悬空字段引用"),
    pytest.param(_mutate_operand_outside_enum, "的 enum", id="操作数越出枚举值域"),
    pytest.param(_mutate_leaf_count, "leaf_field_count", id="字段计数不符"),
    pytest.param(_mutate_conditional_required, "required 必须为 always", id="条件必备性复活"),
    pytest.param(_mutate_freetext_array_order, "array_order 必须是带 kind", id="自由文本数组顺序"),
    pytest.param(_mutate_dangling_element_structure, "指向不存在的结构", id="悬空元素结构"),
    pytest.param(_mutate_nullable_without_constraints, "必须声明 constraints", id="可空但无约束"),
]


@pytest.mark.parametrize("mutate, expected", SCHEMA_MUTATIONS)
def test_schema_mutations_are_rejected(validator, schema, mutate, expected):
    mutated = copy.deepcopy(schema)
    mutate(mutated)
    errors: list[str] = []
    validator.validate_schema_data(mutated, errors)
    assert any(expected in e for e in errors), f"变异未被拒绝，实际错误：{errors}"


# --------------------------------------------------------------------------- #
# 负向：跨真源（JSON ↔ 合同文档）
# --------------------------------------------------------------------------- #


def test_new_field_missing_from_doc_is_rejected(validator, schema, schema_doc):
    """JSON 新增字段但忘了写进合同——第 36 章 order_type 漂移的同型。"""
    mutated = copy.deepcopy(schema)
    mutated["structures"]["ORDER_CANCELLED"]["fields"]["brand_new_field"] = {
        "value_type": "int",
        "nullable": False,
        "required": "always",
        "hash": "HASH_EXCLUDE",
    }
    errors: list[str] = []
    validator.validate_schema_against_doc(mutated, schema_doc, errors)
    assert any("合同文档从未提及" in e for e in errors), errors


def test_e002_missing_hash_field_is_rejected(validator, schema, schema_doc):
    """E-002 漏列一个 HASH_INCLUDE 字段 —— 该字段会静默逃出 KPI-002。

    这条正是第 36 章的实际漂移：`order_type` 在 JSON 里是 HASH_INCLUDE，
    E-002 清单里却没有，而当时的校验器返回成功。
    """
    broken = schema_doc.replace(
        "`side`、`order_type`、`reason`、`reserved_delta_units` |",
        "`side`、`reason`、`reserved_delta_units` |",
        1,
    )
    assert broken != schema_doc, "变异未生效：E-002 的 ORDER_CANCELLED 行已改写，请同步本测试"
    errors: list[str] = []
    validator.validate_schema_against_doc(schema, broken, errors)
    assert any("漏列" in e and "order_type" in e for e in errors), errors


def test_closed_table_count_drift_is_rejected(validator, schema, schema_doc):
    """文档写「N 项，封闭」但 N 与 JSON 不符。"""
    broken = schema_doc.replace("共 **11** 项，封闭", "共 **9** 项，封闭", 1)
    assert broken != schema_doc, "变异未生效：封闭计数写法已改，请同步本测试"
    errors: list[str] = []
    validator.validate_schema_against_doc(schema, broken, errors)
    assert any("封闭" in e for e in errors), errors


# --------------------------------------------------------------------------- #
# 负向：0.1.4 report artifact Schema registry
# --------------------------------------------------------------------------- #


def _drop_report_artifact(d: dict) -> None:
    d["artifacts"].pop("effect_sizes")


def _set_invalid_artifact_field_type(d: dict) -> None:
    d["artifacts"]["market_metrics"]["required_fields"]["timestamp"]["type"] = "int64"


def _drop_artifact_content_version(d: dict) -> None:
    d["artifacts"]["pnl_bridge"]["required_fields"].pop("schema_version")


def _unfreeze_nested_artifact_object(d: dict) -> None:
    d["artifacts"]["robustness_conclusion"]["required_fields"]["elements"].pop("required_fields")


def _make_artifact_object_shape_ambiguous(d: dict) -> None:
    d["artifacts"]["liquidation_metrics"]["required_fields"]["chain_depth_counts"][
        "required_fields"
    ] = {"depth": {"type": "integer"}}


def _nest_artifact_array_without_item_schema(d: dict) -> None:
    d["artifacts"]["sample_classification"]["required_fields"]["economic_endpoint_codes"][
        "item_type"
    ] = "array"


ARTIFACT_SCHEMA_MUTATIONS = [
    pytest.param(_drop_report_artifact, "不一致", id="缺 artifact"),
    pytest.param(_set_invalid_artifact_field_type, "type='int64' 非法", id="非法字段类型"),
    pytest.param(_drop_artifact_content_version, "内容必须带", id="缺内容版本"),
    pytest.param(_unfreeze_nested_artifact_object, "必须冻结", id="嵌套对象未冻结"),
    pytest.param(_make_artifact_object_shape_ambiguous, "只能选一个", id="对象形状双定义"),
    pytest.param(
        _nest_artifact_array_without_item_schema, "item_type='array' 非法", id="数组嵌套未冻结"
    ),
]


@pytest.mark.parametrize("mutate, expected", ARTIFACT_SCHEMA_MUTATIONS)
def test_artifact_schema_mutations_are_rejected(validator, artifact_schemas, mutate, expected):
    mutated = copy.deepcopy(artifact_schemas)
    mutate(mutated)
    errors: list[str] = []
    validator.validate_artifact_schema_data(mutated, errors)
    validator.validate_artifact_schemas_against_spec(
        mutated, validator.REPORT_SPEC.read_text(encoding="utf-8"), errors
    )
    assert any(expected in e for e in errors), f"变异未被拒绝，实际错误：{errors}"


def test_artifact_schema_producer_drift_from_spec_is_rejected(validator, artifact_schemas):
    spec_text = validator.REPORT_SPEC.read_text(encoding="utf-8")
    broken = spec_text.replace(
        "| `effect_sizes` | 0.1.2 T604 |", "| `effect_sizes` | 0.1.2 T999 |", 1
    )
    assert broken != spec_text, "变异未生效：effect_sizes producer 表格已改写，请同步本测试"
    errors: list[str] = []
    validator.validate_artifact_schemas_against_spec(artifact_schemas, broken, errors)
    assert any("展示表" in e and "不一致" in e for e in errors), errors


def test_duplicate_artifact_row_in_spec_is_rejected(validator, artifact_schemas):
    spec_text = validator.REPORT_SPEC.read_text(encoding="utf-8")
    row = "| `effect_sizes` | 0.1.2 T604 |"
    broken = spec_text.replace(row, f"{row}\n{row}", 1)
    assert broken != spec_text, "变异未生效：effect_sizes 表格行已改写，请同步本测试"
    errors: list[str] = []
    validator.validate_artifact_schemas_against_spec(artifact_schemas, broken, errors)
    assert "report artifacts: spec 展示表含重复 artifact_id" in errors


# --------------------------------------------------------------------------- #
# 负向：manifest_schema（0.1.4 R014-D002 回归——manifest 七字段唯一真源）
# --------------------------------------------------------------------------- #


def test_manifest_schema_present_and_valid(validator, artifact_schemas):
    """正向对照：当前仓库 manifest_schema 通过结构与七字段封闭校验。"""
    errors: list[str] = []
    validator.validate_manifest_schema_data(artifact_schemas, errors)
    assert errors == []


def _manifest_missing_schema(d: dict) -> None:
    d.pop("manifest_schema", None)


def _manifest_extra_entry_field(d: dict) -> None:
    d["manifest_schema"]["top_level_fields"]["artifacts"]["item_fields"]["extra_field"] = {
        "type": "string"
    }


def _manifest_missing_entry_field(d: dict) -> None:
    del d["manifest_schema"]["top_level_fields"]["artifacts"]["item_fields"]["hash"]


def _manifest_extra_top_level_field(d: dict) -> None:
    d["manifest_schema"]["top_level_fields"]["extra_top"] = {"type": "string"}


def _manifest_hash_algorithm_enum_not_list(d: dict) -> None:
    entry = d["manifest_schema"]["top_level_fields"]["artifacts"]["item_fields"]
    entry["hash_algorithm"]["enum"] = "blake2b"


def _manifest_hash_algorithm_enum_wrong_element_type(d: dict) -> None:
    entry = d["manifest_schema"]["top_level_fields"]["artifacts"]["item_fields"]
    entry["hash_algorithm"]["enum"] = [1]


def _manifest_hash_hex_length_odd(d: dict) -> None:
    entry = d["manifest_schema"]["top_level_fields"]["artifacts"]["item_fields"]
    entry["hash"]["hex_length"] = 63


def _manifest_hash_hex_length_not_int(d: dict) -> None:
    entry = d["manifest_schema"]["top_level_fields"]["artifacts"]["item_fields"]
    entry["hash"]["hex_length"] = "64"


def _manifest_hash_hex_length_on_non_string(d: dict) -> None:
    entry = d["manifest_schema"]["top_level_fields"]["artifacts"]["item_fields"]
    entry["schema_version"]["hex_length"] = 64


def _manifest_hash_hex_length_wrong_value(d: dict) -> None:
    """round-4 复核复现的确切场景：64 改成 62，仍是合法正偶数，形状校验放行。"""
    entry = d["manifest_schema"]["top_level_fields"]["artifacts"]["item_fields"]
    entry["hash"]["hex_length"] = 62


def _manifest_hash_algorithm_wrong_but_valid_enum(d: dict) -> None:
    """enum 仍是合法的非空字符串数组，但值不是 blake2b——形状校验放行。"""
    entry = d["manifest_schema"]["top_level_fields"]["artifacts"]["item_fields"]
    entry["hash_algorithm"]["enum"] = ["md5"]


def _manifest_hash_charset_wrong_but_known_type(d: dict) -> None:
    entry = d["manifest_schema"]["top_level_fields"]["artifacts"]["item_fields"]
    entry["hash"]["charset"] = "uppercase_hex"


MANIFEST_SCHEMA_MUTATIONS = [
    pytest.param(_manifest_missing_schema, "缺 manifest_schema", id="缺 manifest_schema"),
    pytest.param(_manifest_extra_entry_field, "七项封闭清单", id="entry 字段超出七项"),
    pytest.param(_manifest_missing_entry_field, "七项封闭清单", id="entry 字段少于七项"),
    pytest.param(_manifest_extra_top_level_field, "顶层字段集合非法", id="顶层字段超出三项"),
    pytest.param(
        _manifest_hash_algorithm_enum_not_list,
        "enum 必须为非空数组",
        id="hash_algorithm enum 非数组",
    ),
    pytest.param(
        _manifest_hash_algorithm_enum_wrong_element_type,
        "enum 元素必须都是字符串",
        id="hash_algorithm enum 元素类型错误",
    ),
    pytest.param(_manifest_hash_hex_length_odd, "正偶数", id="hash hex_length 奇数"),
    pytest.param(_manifest_hash_hex_length_not_int, "正偶数", id="hash hex_length 非整数"),
    pytest.param(
        _manifest_hash_hex_length_on_non_string,
        "只能用于 type=string",
        id="hex_length 用在非 string 字段",
    ),
    pytest.param(
        _manifest_hash_hex_length_wrong_value,
        "hex_length 必须精确为 64",
        id="hash hex_length 合法正偶数但非 64",
    ),
    pytest.param(
        _manifest_hash_algorithm_wrong_but_valid_enum,
        "enum 必须精确为 ['blake2b']",
        id="hash_algorithm 合法 enum 但非 blake2b",
    ),
    pytest.param(
        _manifest_hash_charset_wrong_but_known_type,
        "charset",
        id="hash charset 非 lowercase_hex",
    ),
]


@pytest.mark.parametrize("mutate, expected", MANIFEST_SCHEMA_MUTATIONS)
def test_manifest_schema_mutations_are_rejected(validator, artifact_schemas, mutate, expected):
    mutated = copy.deepcopy(artifact_schemas)
    mutate(mutated)
    errors: list[str] = []
    validator.validate_manifest_schema_data(mutated, errors)
    assert any(expected in e for e in errors), f"变异未被拒绝，实际错误：{errors}"


def test_manifest_field_drift_from_spec_is_rejected(validator, artifact_schemas):
    """spec.md §4.1 的七字段编号列表与机器 manifest_schema 漂移必报。"""
    spec_text = validator.REPORT_SPEC.read_text(encoding="utf-8")
    broken = spec_text.replace("7. `hash`（字符串", "7. `checksum`（字符串", 1)
    assert broken != spec_text, "变异未生效：spec 第 7 项字段名已改写，请同步本测试"
    errors: list[str] = []
    validator.validate_manifest_schema_against_spec(artifact_schemas, broken, errors)
    assert any("manifest 七字段" in e and "不一致" in e for e in errors), errors


def test_manifest_hash_length_drift_from_spec_is_rejected(validator, artifact_schemas):
    """round-4 复核指出的双向核对缺口：spec 展示的位数与机器 hex_length 漂移必报
    ——即使机器 Schema 自身的精确值校验（validate_manifest_schema_data）没变，
    spec 文案单独改错位数也要能被 validate_manifest_schema_against_spec 抓到。"""
    spec_text = validator.REPORT_SPEC.read_text(encoding="utf-8")
    broken = spec_text.replace("固定 64 位十六进制小写摘要", "固定 128 位十六进制小写摘要", 1)
    assert broken != spec_text, "变异未生效：spec 的 hash 位数描述已改写，请同步本测试"
    errors: list[str] = []
    validator.validate_manifest_schema_against_spec(artifact_schemas, broken, errors)
    assert any("hash 位数" in e and "不一致" in e for e in errors), errors


def test_manifest_hash_length_matches_spec(validator, artifact_schemas):
    """正向对照：当前仓库 spec 展示的 64 位与机器 hex_length=64 一致，不误报。"""
    spec_text = validator.REPORT_SPEC.read_text(encoding="utf-8")
    errors: list[str] = []
    validator.validate_manifest_schema_against_spec(artifact_schemas, spec_text, errors)
    assert not any("hash 位数" in e for e in errors), errors


# --------------------------------------------------------------------------- #
# 负向：traceability
# --------------------------------------------------------------------------- #


def _drop_requirement(d: dict) -> None:
    d["requirements"].pop("FR-019")


def _drop_milestone_owner(d: dict) -> None:
    """删掉 FR-004 的 0.1.2 责任切片——「阶段 owner 丢失」这一类。"""
    d["requirements"]["FR-004"]["owners"] = d["requirements"]["FR-004"]["owners"][:1]
    d["requirements"]["FR-004"]["owners"][0].pop("scope", None)


def _duplicate_scope(d: dict) -> None:
    owners = d["requirements"]["FR-004"]["owners"]
    owners[1]["scope"] = owners[0]["scope"]


def _owned_without_owners(d: dict) -> None:
    d["requirements"]["FR-001"]["owners"] = []


def _unknown_milestone(d: dict) -> None:
    d["requirements"]["FR-001"]["owners"][0]["milestone"] = "9.9.9"


def _nonexistent_exit(d: dict) -> None:
    d["requirements"]["FR-001"]["owners"][0]["exits"] = ["E999"]


def _deferred_without_target(d: dict) -> None:
    d["requirements"]["US-6"]["status"] = "deferred"
    d["requirements"]["US-6"].pop("defer_to", None)
    d["requirements"]["US-6"]["owners"] = []


TRACE_MUTATIONS = [
    pytest.param(_drop_requirement, "遗漏 spec 已声明的 ID", id="删掉一条需求"),
    # 删掉阶段 owner 由【展示表比对】捕获：JSON 少了 0.1.2，spec 表里还写着它。
    pytest.param(_drop_milestone_owner, "展示表", id="删掉一个阶段 owner"),
    pytest.param(_duplicate_scope, "scope 重复", id="scope 重叠"),
    pytest.param(_owned_without_owners, "owners 为空", id="owned 但无 owner"),
    pytest.param(_unknown_milestone, "未知里程碑", id="未知里程碑"),
    pytest.param(_nonexistent_exit, "找不到", id="不存在的退出条件"),
    pytest.param(_deferred_without_target, "缺 defer_to", id="deferred 无目标版本"),
]


@pytest.mark.parametrize("mutate, expected", TRACE_MUTATIONS)
def test_trace_mutations_are_rejected(validator, trace, spec_text, mutate, expected):
    mutated = copy.deepcopy(trace)
    mutate(mutated)
    errors: list[str] = []
    validator.validate_trace_data(mutated, spec_text, errors, ROOT)
    assert any(expected in e for e in errors), f"变异未被拒绝，实际错误：{errors}"


def test_rendered_matrix_drift_is_rejected(validator, trace, spec_text):
    """展示表与 JSON 不符 —— 「机器源正确、读者看到旧表」这一类。"""
    mutated = copy.deepcopy(trace)
    mutated["requirements"]["FR-019"]["owners"] = [
        {"milestone": "0.1.2", "exits": ["E1"], "scope": "改到别的里程碑"}
    ]
    errors: list[str] = []
    validator.validate_rendered_matrix(mutated, spec_text, errors)
    assert any("展示表" in e for e in errors), errors


def test_multi_digit_requirement_ids_are_extracted(validator):
    """提取规则必须支持多位编号——`US-\\d` 那种写法会在 US-10 静默漏检。"""
    families = ["US", "FR"]
    text = "### US-10：某个场景\n\n- **FR-021**：某条需求\n"
    assert validator.spec_validation.declared_ids(text, families) == {"US-10", "FR-021"}
