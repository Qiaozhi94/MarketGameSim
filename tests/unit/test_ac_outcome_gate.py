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
    """执法点：review/done 里程碑点名的 AC 测试在本仓库实跑全部 passed。"""
    assert gate.check_repository() == []


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
