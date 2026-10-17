"""AC 测试结局门禁（`tools/ac_outcome_gate.py`）的回归测试与仓库级执法点。

循环 31 R6 d-done-gate-static-residual-bypass：静态 AST 门禁看不见模块级
``pytest.skip(allow_module_level=True)``、``importorskip``、autouse fixture 与辅助函数里的
跳过。结局门禁实跑测试，只认 passed。
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
GATE = ROOT / "tools" / "ac_outcome_gate.py"


@pytest.fixture(scope="module")
def gate():
    spec = importlib.util.spec_from_file_location("ac_outcome_gate", GATE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["ac_outcome_gate"] = module
    spec.loader.exec_module(module)
    return module


def test_repository_review_done_ac_tests_all_pass(gate):
    """执法点：review/done 里程碑点名的 AC 测试在本仓库实跑全部 passed。

    先断言要求非空且含已知锚点：选择器写坏而返回空集时，「没有失败」是平凡通过，
    整道门会悄悄失效（循环 31 R6 d-outcome-gate-selector-untested）。
    """
    required = gate.spec_validation.ac_outcome_requirements(ROOT / "docs" / "features", ROOT)
    anchor = required.get("tests/unit/agent/test_value_reference.py", {})
    assert anchor.get("test_a_reference_that_moves_once_is_caught") == ["milestone 0.4.3 AC-701"]
    assert sum(len(tests) for tests in required.values()) >= 10
    assert gate.check_repository() == []


def _milestone(
    root: pathlib.Path,
    mid: str,
    *,
    status: str = "done",
    gate_version: int = 1,
    created: str = "2026-10-01",
    tasks: str,
) -> None:
    version = root / "docs" / "features" / "9.9"
    version.mkdir(parents=True, exist_ok=True)
    (version / "spec.md").write_text("---\nkind: version-spec\n---\n", encoding="utf-8")
    mdir = version / f"{mid}-m"
    mdir.mkdir()
    (mdir / "spec.md").write_text(
        f"---\nkind: milestone\nid: {mid}\nstatus: {status}\ngate_version: {gate_version}\n"
        f"created: {created}\n---\n\n### 验收清单\n\n"
        "- [x] **AC-001** (`FR-001`): 一。\n- [x] **AC-002** (`FR-001`): 二。\n",
        encoding="utf-8",
    )
    (mdir / "tasks.md").write_text(f"## 2. 实现任务\n\n{tasks}", encoding="utf-8")


def _test_file(root: pathlib.Path, rel: str, *functions: tuple[str, str]) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            f'def {name}():\n    """{doc}"""\n    assert True\n\n\n' for name, doc in functions
        ),
        encoding="utf-8",
    )


def test_selector_picks_tests_naming_the_ac_in_review_and_done_milestones(gate, tmp_path):
    """正例：done 与 review、gate v1、规则日后创建的里程碑里，逐条点名任务的 verify 文件中
    提到该 AC 的测试被选中，未提到它的测试不被选中。"""
    _test_file(
        tmp_path,
        "tests/unit/test_a.py",
        ("test_one", "AC-001：一。"),
        ("test_two", "AC-002：二。"),
        ("test_unrelated", "没有提到任何验收条目。"),
    )
    tasks = "- [x] T001 (`AC-001`, `AC-002`): 实施 — verify: `tests/unit/test_a.py`\n"
    _milestone(tmp_path, "9.9.1", status="done", tasks=tasks)
    _milestone(tmp_path, "9.9.2", status="review", tasks=tasks)
    required = gate.spec_validation.ac_outcome_requirements(
        tmp_path / "docs" / "features", tmp_path
    )
    assert required == {
        "tests/unit/test_a.py": {
            "test_one": ["milestone 9.9.1 AC-001", "milestone 9.9.2 AC-001"],
            "test_two": ["milestone 9.9.1 AC-002", "milestone 9.9.2 AC-002"],
        }
    }


@pytest.mark.parametrize(
    ("status", "gate_version", "created", "tasks"),
    [
        (
            "draft",
            1,
            "2026-10-01",
            "- [ ] T001 (`AC-001`): 实施 — verify: `tests/unit/test_a.py`\n",
        ),
        (
            "ready-for-development",
            1,
            "2026-10-01",
            "- [ ] T001 (`AC-001`): 实施 — verify: `tests/unit/test_a.py`\n",
        ),
        ("done", 0, "2026-10-01", "- [x] T001 (`AC-001`): 实施 — verify: `tests/unit/test_a.py`\n"),
        ("done", 1, "2026-08-01", "- [x] T001 (`AC-001`): 实施 — verify: `tests/unit/test_a.py`\n"),
        (
            "done",
            1,
            "2026-10-01",
            "- [x] T001 (`AC-001`—`AC-002`): 汇总 — verify: `tests/unit/test_a.py`\n",
        ),
    ],
    ids=["draft", "ready", "gate_v0", "before_rule_date", "range_only"],
)
def test_selector_skips_out_of_scope_milestones_and_range_only_tasks(
    gate, tmp_path, status, gate_version, created, tasks
):
    """反例：draft / ready、gate v0、规则日前创建的里程碑，以及只被区间引用的任务都不选。"""
    _test_file(
        tmp_path, "tests/unit/test_a.py", ("test_one", "AC-001：一。"), ("test_two", "AC-002：二。")
    )
    _milestone(
        tmp_path, "9.9.1", status=status, gate_version=gate_version, created=created, tasks=tasks
    )
    assert (
        gate.spec_validation.ac_outcome_requirements(tmp_path / "docs" / "features", tmp_path) == {}
    )


_REQUIRED = {"tests/unit/test_feature.py": {"test_feature": ["milestone m AC-001"]}}

_BYPASSES = {
    "module_level_skip": (
        "import pytest\n\n"
        'pytest.skip("T001 pending", allow_module_level=True)\n\n\n'
        "def test_feature():\n"
        '    """AC-001：做到某事。"""\n'
        "    assert True\n"
    ),
    "module_level_importorskip": (
        "import pytest\n\n"
        'pytest.importorskip("market_game_sim_module_that_does_not_exist")\n\n\n'
        "def test_feature():\n"
        '    """AC-001：做到某事。"""\n'
        "    assert True\n"
    ),
    "autouse_fixture_skip": (
        "import pytest\n\n\n"
        "@pytest.fixture(autouse=True)\n"
        "def _pending():\n"
        '    pytest.skip("T001 pending")\n\n\n'
        "def test_feature():\n"
        '    """AC-001：做到某事。"""\n'
        "    assert True\n"
    ),
    "helper_function_skip": (
        "import pytest\n\n\n"
        "def _not_ready():\n"
        '    pytest.skip("T001 pending")\n\n\n'
        "def test_feature():\n"
        '    """AC-001：做到某事。"""\n'
        "    _not_ready()\n"
        "    assert True\n"
    ),
    "xfail_skeleton": (
        "import pytest\n\n\n"
        '@pytest.mark.xfail(strict=True, reason="T001 not implemented yet")\n'
        "def test_feature():\n"
        '    """AC-001：做到某事。"""\n'
        '    pytest.fail("T001 pending")\n'
    ),
    "unconditional_skipif": (
        "import pytest\n\n\n"
        '@pytest.mark.skipif(True, reason="always")\n'
        "def test_feature():\n"
        '    """AC-001：做到某事。"""\n'
        "    assert True\n"
    ),
    "failing_assertion": ('def test_feature():\n    """AC-001：做到某事。"""\n    assert False\n'),
}


def _write(root: pathlib.Path, source: str) -> None:
    path = root / "tests" / "unit" / "test_feature.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


@pytest.mark.parametrize("variant", sorted(_BYPASSES))
def test_gate_rejects_every_non_passing_outcome(gate, tmp_path, variant):
    _write(tmp_path, _BYPASSES[variant])
    errors = gate.run_outcome_gate(_REQUIRED, tmp_path)
    assert len(errors) == 1, (variant, errors)
    assert "milestone m AC-001" in errors[0] and "test_feature" in errors[0]


def test_gate_accepts_passing_tests_including_params_and_classes(gate, tmp_path):
    """正例：普通、参数化、类方法、条件不成立的 skipif 都按 passed 计。"""
    _write(
        tmp_path,
        "import pytest\n\n\n"
        '@pytest.mark.skipif(False, reason="环境满足时照常运行")\n'
        '@pytest.mark.parametrize("n", [1, 2])\n'
        "def test_feature(n):\n"
        '    """AC-001：做到某事。"""\n'
        "    assert n > 0\n\n\n"
        "class TestGroup:\n"
        "    def test_member(self):\n"
        '        """AC-001：类里的测试。"""\n'
        "        assert True\n",
    )
    required = {
        "tests/unit/test_feature.py": {
            "test_feature": ["milestone m AC-001"],
            "TestGroup::test_member": ["milestone m AC-001"],
        }
    }
    assert gate.run_outcome_gate(required, tmp_path) == []


def test_gate_reports_one_bad_parametrized_instance(gate, tmp_path):
    """参数化实例里只要有一个不是 passed，整条测试不算通过。"""
    _write(
        tmp_path,
        "import pytest\n\n\n"
        '@pytest.mark.parametrize("n", [1, pytest.param(2, marks=pytest.mark.skip)])\n'
        "def test_feature(n):\n"
        '    """AC-001：做到某事。"""\n'
        "    assert n > 0\n",
    )
    errors = gate.run_outcome_gate(_REQUIRED, tmp_path)
    assert len(errors) == 1 and "skipped" in errors[0]


def test_gate_with_nothing_required_runs_nothing(gate, tmp_path):
    assert gate.run_outcome_gate({}, tmp_path) == []
