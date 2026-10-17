"""AC 测试的**结局**门禁：`review`/`done` 里程碑点名的 AC 测试必须实跑为 passed。

`spec_validation._xfailed_tests_naming` 按源码形态识别 xfail/skip，但跳过可以藏在模块级
``pytest.skip(allow_module_level=True)``、``importorskip``、autouse fixture、被调的辅助函数
里——形态无穷无尽，逐个补永远补不完（循环 31 R6 d-done-gate-static-residual-bypass）。
这里把不变量从「源码形态」换成「结局」：实跑这些测试，任何一条不是 passed（skipped、
xfailed、failed、error、未被收集）即失败。

需要 pytest 与已安装的包，所以不进 `validate_spec_lifecycle.py`（CI 的真源校验 job 不装依赖）；
由 `tests/unit/test_ac_outcome_gate.py` 在每次 pytest 中执行，也可单独运行::

    python tools/ac_outcome_gate.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import spec_validation  # noqa: E402

Requirements = dict[str, dict[str, list[str]]]


def _module_dotted(rel: str) -> str:
    return rel.removesuffix(".py").replace("/", ".")


def _outcome(case: ET.Element) -> str:
    for child in case:
        if child.tag == "skipped":
            return "xfailed" if child.get("type") == "pytest.xfail" else "skipped"
        if child.tag in ("failure", "error"):
            return child.tag
    return "passed"


def _collect_outcomes(
    junit: pathlib.Path, required: Requirements
) -> dict[tuple[str, str], list[str]]:
    """(仓库相对路径, ``Class::name``) -> 该测试（含各参数化实例）的结局列表。"""
    modules = {_module_dotted(rel): rel for rel in required}
    outcomes: dict[tuple[str, str], list[str]] = {}
    for case in ET.parse(junit).getroot().iter("testcase"):
        classname, name = case.get("classname", ""), case.get("name", "")
        base = name.split("[", 1)[0]
        for dotted, rel in modules.items():
            if classname == dotted:
                key = base
            elif classname.startswith(dotted + "."):
                key = f"{classname[len(dotted) + 1 :].replace('.', '::')}::{base}"
            else:
                continue
            outcomes.setdefault((rel, key), []).append(_outcome(case))
            break
    return outcomes


def run_outcome_gate(
    required: Requirements, root: pathlib.Path, python: str = sys.executable
) -> list[str]:
    """实跑 ``required`` 里的测试，返回结局不是 passed 的每一条（空列表即通过）。"""
    if not required:
        return []
    node_ids = [f"{rel}::{name}" for rel, tests in sorted(required.items()) for name in tests]
    with tempfile.TemporaryDirectory() as tmp:
        junit = pathlib.Path(tmp) / "junit.xml"
        proc = subprocess.run(
            [python, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={junit}"]
            + node_ids,
            cwd=root,
            capture_output=True,
            text=True,
        )
        if not junit.is_file():
            tail = (proc.stdout + proc.stderr).strip().splitlines()[-5:]
            return [f"pytest 没有产出结局记录（exit {proc.returncode}）：{' / '.join(tail)}"]
        outcomes = _collect_outcomes(junit, required)

    errors: list[str] = []
    for rel, tests in sorted(required.items()):
        for name, owners in sorted(tests.items()):
            seen = outcomes.get((rel, name), [])
            if not seen:
                verdict = "未运行（未被收集，或被模块级跳过）"
            elif any(outcome != "passed" for outcome in seen):
                verdict = "结局为 " + "/".join(sorted(set(seen)))
            else:
                continue
            errors.append(f"{'、'.join(owners)}：{rel}::{name} {verdict}，review/done 要求 passed")
    return errors


def check_repository(root: pathlib.Path = ROOT) -> list[str]:
    required = spec_validation.ac_outcome_requirements(root / "docs" / "features", root)
    return run_outcome_gate(required, root)


def main() -> int:
    errors = check_repository()
    if errors:
        print(f"AC 测试结局门禁失败（{len(errors)} 项）：")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("AC 测试结局门禁通过：review/done 里程碑点名的 AC 测试全部 passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
