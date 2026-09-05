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
import re
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


def _add_unknown_artifact_level_key(d: dict) -> None:
    d["artifacts"]["market_metrics"]["unknown_key"] = True


ARTIFACT_SCHEMA_MUTATIONS = [
    pytest.param(_drop_report_artifact, "不一致", id="缺 artifact"),
    pytest.param(_set_invalid_artifact_field_type, "type='int64' 非法", id="非法字段类型"),
    pytest.param(_drop_artifact_content_version, "内容必须带", id="缺内容版本"),
    pytest.param(_unfreeze_nested_artifact_object, "必须冻结", id="嵌套对象未冻结"),
    pytest.param(_make_artifact_object_shape_ambiguous, "只能选一个", id="对象形状双定义"),
    pytest.param(
        _nest_artifact_array_without_item_schema, "item_type='array' 非法", id="数组嵌套未冻结"
    ),
    pytest.param(
        _add_unknown_artifact_level_key, "未知 artifact 级属性", id="未知 artifact 级属性"
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


# --------------------------------------------------------------------------- #
# v2 目标模型合同：跨文档单一真源
# --------------------------------------------------------------------------- #

GOAL_MODEL_IDS = ("risk_budget_linear_v1", "risk_budget_threshold_v1")
GOAL_MODEL_DOCS = (
    "docs/contracts/agent-strategy.md",
    "docs/features/0.1/0.1.5-goal-driven-flagship/spec.md",
    "docs/features/0.1/spec.md",
    "docs/decisions/003-goal-driven-agents-and-flagship-identification.md",
)


@pytest.mark.parametrize("doc", GOAL_MODEL_DOCS)
@pytest.mark.parametrize("model_id", GOAL_MODEL_IDS)
def test_goal_model_ids_are_consistent_across_docs(doc, model_id):
    """两个目标模型 ID 必须在合同、里程碑 spec、版本根与 ADR 里写法完全一致。

    `cross-feature-contract-drift` 在本仓库已复现三次（RETROSPECTIVE 循环 8/9/11）：
    一处改名、别处不改，机器无从发现，直到实现者按哪份文档写都对不上。
    """
    text = (ROOT / doc).read_text(encoding="utf-8")
    assert model_id in text, f"{doc} 未提及 {model_id}"


H2_QUESTION_DOCS = (
    "docs/market-game-sim-prd.md",
    "docs/features/0.3/spec.md",
    "docs/features/0.3/0.3.1-human-in-the-loop-experiment/spec.md",
)

H2_CONTROL_CONTRACT_DOCS = (
    "docs/features/0.3/0.3.1-human-in-the-loop-experiment/spec.md",
    "docs/features/0.3/0.3.1-human-in-the-loop-experiment/design.md",
    "docs/features/0.3/0.3.1-human-in-the-loop-experiment/tasks.md",
)


@pytest.mark.parametrize("doc", H2_QUESTION_DOCS)
def test_h2_flagship_question_uses_the_primary_reference_policy(doc):
    """Q-308 改主要反事实后，PRD、父规格和里程碑不得继续提出旧问题。"""
    text = (ROOT / doc).read_text(encoding="utf-8")
    assert "预注册纯代理参照策略" in text, f"{doc} 未声明 H2 主要参照策略"
    assert "以真实人类交易者替换一个目标驱动代理" not in text, f"{doc} 仍在提出旧 H2 问题"


@pytest.mark.parametrize("doc", H2_CONTROL_CONTRACT_DOCS)
def test_h2_primary_control_is_window_matched_not_goal_aligned(doc):
    """v0.1 没有目标对齐策略，H2 合同不得重新暗示完整效用函数已对齐。"""
    text = (ROOT / doc).read_text(encoding="utf-8")
    assert "WINDOW_MATCHED_POLICY_CONTROL" in text, f"{doc} 缺窗口匹配主对照"
    assert "ALIGNED_POLICY_CONTROL" not in text, f"{doc} 仍使用无法兑现的目标对齐名称"


def test_h2_protocol_requires_an_auditable_comparison_matrix():
    spec = (ROOT / H2_CONTROL_CONTRACT_DOCS[0]).read_text(encoding="utf-8")
    design = (ROOT / H2_CONTROL_CONTRACT_DOCS[1]).read_text(encoding="utf-8")
    assert "比较矩阵" in spec and "不声称目标函数对齐" in spec
    assert "可审计比较矩阵" in design and "不同且必须分别披露" in design


def test_h2_retrospective_preserves_nonadoption_dispositions():
    """忽略的 CURRENT/FIX-log 即使被误删，裁决理由也必须在 Git 历史中有无损兜底。"""
    retrospective = (ROOT / "docs" / "reviews" / "RETROSPECTIVE.md").read_text(encoding="utf-8")
    section = retrospective.split("### 裁决记录（从被误删的 CURRENT-doc 恢复）", 1)[1]
    section = section.split("### 审查过程稿保留约束（恢复）", 1)[0]
    for issue_id in (
        "t903-verify-time-inversion",
        "treatment-bundles-three-changes",
        "estimand-too-narrow-for-product-thesis",
        "no-agent-ablation-reference-frame",
        "primary-endpoint-occurrence-vs-severity",
    ):
        assert issue_id in section, f"缺少 {issue_id} 的裁决记录"
    assert "证据：" in section and "关闭路径" in section


def test_h2_retrospective_issue_table_is_lossless():
    """循环 21 的每条 issue 必须保持固定 13 列，不能让缺列把状态整体左移。"""
    retrospective = (ROOT / "docs" / "reviews" / "RETROSPECTIVE.md").read_text(encoding="utf-8")
    table = retrospective.split("## 循环 21:", 1)[1].split("### 裁决记录", 1)[0]
    rows = [line for line in table.splitlines() if line.startswith("| ")]
    header, *issues = rows
    assert len(header.strip("|").split("|")) == 13
    assert len(issues) == 25
    assert all(len(row.strip("|").split("|")) == 13 for row in issues)
    statuses = {row.strip("|").split("|")[6].strip() for row in issues}
    assert all(
        status.startswith(("fixed", "rejected", "partial", "tracked")) for status in statuses
    )
    by_id = {row.strip("|").split("|")[0].strip(): row for row in issues}
    assert "partial（裁决 #2）" in by_id["treatment-bundles-three-changes"]
    assert "partial（裁决 #3）" in by_id["estimand-too-narrow-for-product-thesis"]
    assert "aligned-control-policy-contract-unresolved" in by_id["treatment-bundles-three-changes"]
    assert (
        "q308-flagship-question-comparator-drift" in by_id["estimand-too-narrow-for-product-thesis"]
    )


def test_claude_ci_job_inventory_matches_workflow():
    """新增 CI job 时，开发者入口不能继续给出过期的通过项数量。"""
    guide = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "H1 interactive (Windows)" in guide
    assert "共 5 个" in guide
    assert "name: H1 interactive (Windows)" in workflow


def test_v2_goal_contract_freezes_the_decisions_design_defers_to_it():
    """design 把语义"已冻结"的部分指向合同，合同就必须真的写着这些语义。

    这条挡的是反向漂移：design 说"见合同 §5.2.3"，而合同里那一节被删掉或改名——
    读者会以为决策已定，实际实现者仍要自己发明。
    """
    contract = (ROOT / "docs" / "contracts" / "agent-strategy.md").read_text(encoding="utf-8")
    for section in ("5.2.1", "5.2.2", "5.2.3", "5.2.4"):
        assert f"#### {section}" in contract, f"合同缺 §{section}"
    # 三条被 design 明确标记为「已冻结」的决策，必须在合同里有对应文字
    assert "risk_appetite" in contract, "风险预算来源未冻结"
    assert "只允许减仓" in contract, "equity ≤ 0 的行为未冻结"
    assert "不改方向" in contract, "约束层只裁剪规模的边界未冻结"


def test_constraint_layer_uses_the_single_admission_formula():
    """约束层不得自立一套准入式——`equity − reserved` 是账户合同 §3.3 明令禁止的写法。

    它已含当前持仓保证金，再从权益里减一次就是重复扣除，会让合法目标被错误裁剪；
    §3.3 为此专门写了反例。这条锁定两份合同同口径，防止 v2 约束层再漂回旧式。
    """
    contract = (ROOT / "docs" / "contracts" / "agent-strategy.md").read_text(encoding="utf-8")
    margin = (ROOT / "docs" / "contracts" / "margin-and-account.md").read_text(encoding="utf-8")
    section = contract.split("#### 5.2.4")[1].split("## 6")[0]
    assert "reserved_after <= risk_equity" in section, "v2 约束层未使用统一准入式"
    assert "reserved_after > risk_equity" in margin, "账户合同的准入式被改动，本测试需同步"
    assert "不得写成 `equity − reserved_units` 形式" in section, "缺少对旧式的显式禁止"
    # 只禁「把可行域*定义*成减法」，不能简单查子串——禁止句本身就含这个公式，
    # 按子串判会把正确的警示文字当成违规（本测试第一版就是这样自己踩进去的）。
    assert not re.search(r"可行域\s*=\s*权益\s*[−-]", section), "可行域被重新定义成减法形式"
    assert "减仓永不因保证金被裁剪" in section, "减仓豁免未写入 v2 约束层"


# --------------------------------------------------------------------------- #
# v2 目标合同：golden vector 重算与运行族矩阵
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def goal_contract(validator) -> dict:
    return json.loads(validator.GOAL_CONTRACT.read_text(encoding="utf-8"))


def _drop_institutional_independence(d: dict) -> None:
    d["risk_appetite"]["independent_of"] = ["arm_id"]


def _model_reads_institutional_fields(d: dict) -> None:
    d["goal_models"]["risk_budget_linear_v1"]["reads_institutional_fields"] = True


def _change_linear_equation(d: dict) -> None:
    d["goal_models"]["risk_budget_linear_v1"]["equation"] = "desired = 0"


def _change_threshold_bound(d: dict) -> None:
    d["goal_models"]["risk_budget_threshold_v1"]["param_bounds"]["theta_in"]["max"] = 9999


def _change_risk_appetite_bound(d: dict) -> None:
    d["risk_appetite"]["bounds"]["max_x1000"] = 99999


def _matrix_to_blacklist(d: dict) -> None:
    d["run_family_matrix"]["policy"] = "blacklist"


def _unlisted_field_allowed(d: dict) -> None:
    d["run_family_matrix"]["unlisted_field_verdict"] = "optional"


def _allow_injection_in_spontaneous(d: dict) -> None:
    d["run_family_matrix"]["fields"]["agent_signals"]["SPONTANEOUS"] = "optional"


def _illegal_family_verdict(d: dict) -> None:
    d["run_family_matrix"]["fields"]["seed_plan"]["STRESS"] = "maybe"


def _add_unknown_run_family(d: dict) -> None:
    d["run_family_matrix"]["families"].append("UNKNOWN")


def _drop_run_family_cell(d: dict) -> None:
    d["run_family_matrix"]["fields"]["seed_plan"].pop("BENCHMARK")


def _change_declared_spontaneous_forbidden_set(d: dict) -> None:
    d["run_family_matrix"]["spontaneous_forbidden_min_set"].pop()


def _drop_required_decision_field(d: dict) -> None:
    d["structures"]["DecisionEvidenceV1"]["fields"].pop("desired_position_units")


def _drop_decision_cursor_boundary(d: dict) -> None:
    d["structures"]["DecisionEvidenceV1"]["fields"].pop("cursor_from_event_id")


def _drop_stress_events(d: dict) -> None:
    d["structures"]["StressProtocolV1"]["fields"].pop("events")


def _use_numeric_event_id(d: dict) -> None:
    d["structures"]["DecisionEvidenceV1"]["fields"]["observation_event_id"]["value_type"] = "int"


def _drop_seed_plan_matrix_row(d: dict) -> None:
    d["run_family_matrix"]["fields"].pop("seed_plan")


def _drop_degenerate_vectors(d: dict) -> None:
    d["golden_vectors"].pop("degenerate")


def _drop_linear_vector(d: dict) -> None:
    d["golden_vectors"]["linear"].pop()


def _break_degenerate_vector(d: dict) -> None:
    d["golden_vectors"]["degenerate"][0]["expected_action"] = "emit_decision"


def _drop_constraint_reason(d: dict) -> None:
    d["structures"]["DecisionEvidenceV1"]["fields"]["constraint_reason"]["enum"].pop()


def _break_linear_vector(d: dict) -> None:
    d["golden_vectors"]["linear"][0]["expected_desired"] += 1


def _break_trunc_direction(d: dict) -> None:
    # 向零取整被改成向下取整时，负数会差 1——这条专门锁 ADR-001 的取整方向
    d["golden_vectors"]["linear"][3]["expected_desired"] = -6872


def _break_threshold_vector(d: dict) -> None:
    d["golden_vectors"]["threshold"][2]["expected_desired"] = 0


def _remove_hysteresis(d: dict) -> None:
    d["golden_vectors"]["threshold"][0]["theta_out"] = 3000


def _break_pure_reduction(d: dict) -> None:
    d["golden_vectors"]["constraint"][0]["margin_check_skipped"] = False


def _break_flip_vector(d: dict) -> None:
    d["golden_vectors"]["constraint"][1]["expected_executable"] = -80


GOAL_CONTRACT_MUTATIONS = [
    pytest.param(
        _drop_institutional_independence, "独立于 leverage_tier", id="风险偏好不再独立于制度字段"
    ),
    pytest.param(
        _model_reads_institutional_fields,
        "reads_institutional_fields=false",
        id="目标模型读制度字段",
    ),
    pytest.param(_change_linear_equation, "冻结属性 equation", id="主模型方程字符串漂移"),
    pytest.param(_change_threshold_bound, "冻结属性 param_bounds", id="threshold 参数上界漂移"),
    pytest.param(_change_risk_appetite_bound, "冻结属性 bounds", id="风险偏好上界漂移"),
    pytest.param(_matrix_to_blacklist, "必须是 whitelist", id="矩阵退回黑名单"),
    pytest.param(_unlisted_field_allowed, "未列字段的判定必须是 forbidden", id="未列字段默认放行"),
    pytest.param(
        _allow_injection_in_spontaneous,
        "SPONTANEOUS 必须禁止 agent_signals",
        id="自发族放行注入字段",
    ),
    pytest.param(_illegal_family_verdict, "非法", id="非法族判定"),
    pytest.param(_add_unknown_run_family, "运行族闭集", id="增加未知运行族"),
    pytest.param(_drop_run_family_cell, "逐格覆盖三个运行族", id="运行族矩阵缺一格"),
    pytest.param(
        _change_declared_spontaneous_forbidden_set,
        "spontaneous_forbidden_min_set",
        id="自发族禁用字段声明漂移",
    ),
    pytest.param(
        _drop_required_decision_field,
        "DecisionEvidenceV1 字段闭集不符",
        id="决策证据必备字段被删除",
    ),
    pytest.param(
        _drop_decision_cursor_boundary,
        "DecisionEvidenceV1 字段闭集不符",
        id="决策证据游标边界被删除",
    ),
    pytest.param(
        _drop_stress_events,
        "StressProtocolV1 字段闭集不符",
        id="压力协议事件列表被删除",
    ),
    pytest.param(
        _use_numeric_event_id,
        "必须是 str",
        id="事件外键退回数值类型",
    ),
    pytest.param(
        _drop_seed_plan_matrix_row,
        "运行族矩阵字段闭集不符",
        id="运行族矩阵必备行被删除",
    ),
    pytest.param(
        _drop_degenerate_vectors,
        "golden_vectors 必须且只能包含",
        id="退化状态向量族被删除",
    ),
    pytest.param(_drop_linear_vector, "linear golden vector ID 闭集", id="单条目标向量被删除"),
    pytest.param(
        _break_degenerate_vector,
        "degenerate golden vector",
        id="退化状态向量语义漂移",
    ),
    pytest.param(
        _drop_constraint_reason,
        "constraint_reason 枚举闭集不符",
        id="约束原因枚举成员被删除",
    ),
    pytest.param(_break_linear_vector, "linear golden vector", id="linear 向量与方程不符"),
    pytest.param(_break_trunc_direction, "linear golden vector", id="取整方向被改成向下"),
    pytest.param(
        _break_threshold_vector, "threshold golden vector", id="threshold 保持区被改成清仓"
    ),
    pytest.param(_remove_hysteresis, "滞回", id="滞回被抹平"),
    pytest.param(_break_pure_reduction, "纯减仓", id="纯减仓不再跳过保证金检查"),
    pytest.param(_break_flip_vector, "constraint golden vector", id="翻仓向量不受新开仓段限制"),
]


@pytest.mark.parametrize("mutate, expected", GOAL_CONTRACT_MUTATIONS)
def test_goal_contract_mutations_are_rejected(validator, goal_contract, mutate, expected):
    mutated = copy.deepcopy(goal_contract)
    mutate(mutated)
    errors: list[str] = []
    validator.spec_validation.validate_goal_contract_data(mutated, errors)
    assert any(expected in e for e in errors), f"变异未被拒绝，实际错误：{errors}"


def test_goal_contract_repository_data_is_self_consistent(validator, goal_contract):
    """当前仓库的向量与方程互洽——重算无差异。"""
    errors: list[str] = []
    validator.spec_validation.validate_goal_contract_data(goal_contract, errors)
    assert errors == []


def test_goal_contract_boundary_examples_must_appear_in_doc(validator, goal_contract):
    """文档算例表与真源向量脱节时必须失败——两处各写一份是漂移的起点。"""
    doc = validator.AGENT_STRATEGY_DOC.read_text(encoding="utf-8")
    errors: list[str] = []
    validator.spec_validation.validate_goal_contract_against_doc(goal_contract, doc, errors)
    assert errors == []

    mutated = copy.deepcopy(goal_contract)
    mutated["golden_vectors"]["constraint"][1]["expected_executable"] = -4242
    errors = []
    validator.spec_validation.validate_goal_contract_against_doc(mutated, doc, errors)
    assert any("未出现在文档算例表" in e for e in errors)


def test_four_v1_structures_are_declared_with_closed_fields(goal_contract):
    """四个 V1 Schema 必须逐字段声明类型与可空性——DR-501 的机器形态。"""
    expected = {
        "InformationSetV1",
        "AgentInternalStateV1",
        "DecisionEvidenceV1",
        "StressProtocolV1",
    }
    assert set(goal_contract["structures"]) == expected
    allowed_types = set(goal_contract["meta"]["value_types"])
    for name, structure in goal_contract["structures"].items():
        assert "schema_version" in structure["fields"], f"{name} 缺 schema_version"
        for field_name, field in structure["fields"].items():
            assert field["value_type"] in allowed_types, f"{name}.{field_name} 类型非法"
            assert isinstance(field["nullable"], bool), f"{name}.{field_name} 缺 nullable"
            assert field["required"] == "always", f"{name}.{field_name} 必备性必须为 always"
            if field["value_type"] == "enum":
                assert field.get("enum"), f"{name}.{field_name} 是 enum 但没有值域"


def test_decision_evidence_records_both_cursor_boundaries(goal_contract):
    """TR-501 要求决策事件直接记录消费区间，不能只靠 observation 外键间接推断。"""
    fields = goal_contract["structures"]["DecisionEvidenceV1"]["fields"]
    assert fields["cursor_from_event_id"]["value_type"] == "str"
    assert fields["cursor_to_event_id"]["value_type"] == "str"
    assert fields["observation_event_id"]["value_type"] == "str"
