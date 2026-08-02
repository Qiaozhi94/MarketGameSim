"""真源自校验：`tools/validate_contract_sources.py` 的 pytest 入口。

同一套判据有两个触发点，**共用同一份实现**（不是两份手抄逻辑）：

- CI 的 `contract-sources` job：不装任何依赖，最先跑，失败即中止后续；
- 本地 `pytest`：开发者不必记住还有个脚本要跑。

放在这里的理由：两份机器真源（`event_fields.json`、`traceability.json`）在被任何
实现消费之前就必须自洽，而它们**恰恰最容易在「补一个字段忘了改另一处」时漂移**——
检视报告 §35.2 记录过一次，那次是人读文档发现的。
"""

from __future__ import annotations

import importlib.util
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


def test_event_fields_schema_is_self_consistent(validator):
    """`event_fields.json` 通过自身声明的 constraint grammar。"""
    errors: list[str] = []
    validator.validate_schema(errors)
    assert errors == [], "event_fields.json 自校验失败：\n" + "\n".join(errors)


def test_traceability_covers_all_declared_requirements(validator):
    """`traceability.json` 的 ID 集合与 spec 声明一致，且 owner/scope/exit 均可解析。"""
    errors: list[str] = []
    validator.validate_trace(errors)
    assert errors == [], "traceability.json 自校验失败：\n" + "\n".join(errors)


def test_validator_exits_zero(validator):
    """脚本入口的退出码与上面两项一致——CI job 依赖的是这个返回值。"""
    assert validator.main() == 0
