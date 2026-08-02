# Code Review Report

**Reviewed**: `tools/validate_contract_sources.py`, `tests/unit/test_contract_sources.py`,
`.github/workflows/ci.yml`，以及它们校验的两份 JSON/Markdown 合同
**Language(s)**: Python, YAML, JSON, Markdown
**Review Date**: 2026-08-02
**Severity Legend**: 🔴 Critical | 🟠 High | 🟡 Medium | 🟢 Low | 🔵 Info

---

## Executive Summary

校验脚本结构清楚、纯标准库可运行，CI、pytest 与 ruff 当前均通过；官方 GitHub 仓库也
确认 `actions/checkout@v7` 与 `actions/setup-python@v7` 是有效版本。但现有测试只证明
当前样本能通过，没有证明校验器能挡住其声称负责的漂移。最直接的证据是：JSON 新增
`ORDER_CANCELLED.order_type` 后，Markdown 字段表、E-002、向量和 147 字段计数均未同步，
而 CI 仍然全绿。

## Findings

### Correctness

#### 🟠 Schema validator 未覆盖其承诺的真源一致性 — `tools/validate_contract_sources.py`:43

**Severity**: High

**Problem**: `validate_schema()` 只检查少量字段与 constraint 外形，没有检查
`operand_types`、数组 `length/array_order` grammar、结构引用、条件枚举值、文档字段表或
E-002 集合。当前仓库已经发生可观察的漏检：JSON 有 148 个字段并给
`ORDER_CANCELLED.order_type` 标记 `HASH_INCLUDE`，合同表/E-002/向量仍没有该字段，
T204f0 仍写 147 个字段；脚本却返回成功。

**Current Code**:

```python
if fd.get("value_type") == "enum" and "enum" not in fd:
    _fail(errors, f"{where}: enum 类型缺 enum 值域")
if fd.get("hash") not in ("HASH_INCLUDE", "HASH_EXCLUDE"):
    _fail(errors, f"{where}: hash 分类缺失或非法")
```

**Suggested Fix**:

```python
validate_field_metadata(fd, meta)
validate_constraint_operands(fd, fields, grammar)
validate_array_contract(fd, fields, grammar)
validate_structure_references(d["structures"])
validate_markdown_field_tables_and_e002(d)
```

**Explanation**: “JSON 自洽”与“JSON 是唯一真源”是两件事。至少应立即同步当前
`order_type` 漂移，并让设计阶段校验执行 T204f3 的关键集合比较；否则最危险的跨真源
漂移只能等实现阶段才发现。

---

#### 🟠 Trace validator 没有验证展示表或 scope 完整性 — `tools/validate_contract_sources.py`:94

**Severity**: High

**Problem**: `tracked_id_families` 没有被消费，ID 前缀被硬编码在正则中，US 正则只接受
一位数字。多 owner 的 `scope` 仅检查“非空”，无法检测任务承诺的重叠/遗漏；展示矩阵
也完全未比较。当前 NFR-002 的 Markdown 仍写“各里程碑各自”，JSON 只有 0.1.1 owner，
CI 不会失败。

**Current Code**:

```python
DECL_PATTERNS = (
    re.compile(r"^- \*\*((?:FR|KR|NFR|SC)-\d{3})\*\*", re.M),
    re.compile(r"^### (US-\d)：", re.M),
)

if len(r["owners"]) > 1 and any(not s for s in scopes):
    _fail(errors, f"{rid}: 多 owner 必须逐个声明 scope")
```

**Suggested Fix**:

```python
patterns = compile_patterns_from(d["tracked_id_families"])
declared = extract_declared_ids(spec_text, patterns)
validate_owner_slices(rid, r["owners"], declared_scope_schema)
validate_rendered_matrix_matches_trace(d, spec_text)
```

**Explanation**: 自由文本 scope 无法证明互斥与覆盖。应把 scope 变成枚举/稳定 slice ID，
或降低合同承诺，不再声称机器能证明重叠。展示表应由 JSON 生成并做 golden diff，避免
再次出现“机器源正确、读者看到旧表”。

---

#### 🟠 Artifact 的最小 Schema 仍未实际冻结 — `specs/v0.1-belief-testing-laboratory/0.1.4-replay-and-report/spec.md`:114

**Severity**: High

**Problem**: 文档新增了“每个 artifact 还须冻结最小列/键 Schema”的要求，却没有给出
10 个 artifact 的实际列/键、类型或对应机器文件。因此 P1-T01 只是从“缺少要求”变成
“要求未来补”，尚不能标记关闭。

**Current Code**:

```text
每个 artifact_id 还须冻结最小列/键 Schema
```

**Suggested Fix**:

```json
{
  "artifact_id": "effect_sizes",
  "schema_version": 1,
  "required_columns": {"cell_id": "string", "effect": "int", "ci_low": "int"}
}
```

**Explanation**: `schema_version` 只有在被版本化对象真实存在时才有意义。可把 artifact
Schema 放入单独 JSON 真源，并由 0.1.2/0.1.3 producer 与 0.1.4 consumer 共用。

### Testing

#### 🟡 测试全部是 happy path，不能证明 guard 会失败 — `tests/unit/test_contract_sources.py`:40

**Severity**: Medium

**Problem**: 三个测试都对当前仓库调用同一实现；第三个只是重复前两个。没有临时变异
Schema/trace 的负向测试，所以删除某条校验逻辑后测试仍可能全绿。任务承诺的七组
constraint 正反夹具与 T607 三类负向夹具尚未落地。

**Current Code**:

```python
errors: list[str] = []
validator.validate_schema(errors)
assert errors == []
```

**Suggested Fix**:

```python
@pytest.mark.parametrize("mutation, expected", SCHEMA_MUTATIONS)
def test_schema_mutations_are_rejected(tmp_path, validator, mutation, expected):
    path = write_mutated_schema(tmp_path, mutation)
    assert expected in validator.validate_schema_file(path)
```

**Explanation**: 将校验函数改为接收 path/data，才能低成本注入未知谓词、错误 operand、
错误数组规则、缺 owner、重复 scope 和展示表漂移，证明每道门确实生效。

---

#### 🟡 固定 `PYTHONHASHSEED=0` 会掩盖内置 `hash()` 的跨进程不确定性 — `.github/workflows/ci.yml`:56

**Severity**: Medium

**Problem**: 注释称固定 seed 能防止误用内置 `hash()`，实际相反：同一 seed 会让错误实现在
每次 CI 中稳定，KPI-002 可能假通过。

**Current Code**:

```yaml
env:
  PYTHONHASHSEED: "0"
run: pytest
```

**Suggested Fix**:

```yaml
- run: python tests/determinism_probe.py --output seed-1.json
  env: {PYTHONHASHSEED: "1"}
- run: python tests/determinism_probe.py --output seed-2.json
  env: {PYTHONHASHSEED: "2"}
- run: python tools/compare_digests.py seed-1.json seed-2.json
```

**Explanation**: 普通测试可以固定 seed 方便复现，但确定性门必须至少跨两个不同 seed 的
独立进程比较输出，才能抓出 `hash()` 随机盐。

## Positive Observations

- 校验器只依赖标准库，适合在依赖安装前作为 CI 第一门。
- schema/trace 路径集中定义，错误信息包含结构和字段定位。
- CI 的 job 依赖关系合理，lint/test 不会绕过真源检查。
- 本地 `pytest`、ruff 和独立脚本当前均通过；官方 release 已确认两个 v7 action 有效。

## Summary

| Severity | Count |
|----------|-------|
| 🔴 Critical | 0 |
| 🟠 High | 3 |
| 🟡 Medium | 2 |
| 🟢 Low | 0 |
| 🔵 Info | 0 |

**Bottom Line**: 基础市场代码可以开始，但当前绿色 CI 还不足以支撑“机器真源已封板”；
修复三项 High 后再启动 registry/hash、T607 与 0.1.4 artifact 消费实现。
