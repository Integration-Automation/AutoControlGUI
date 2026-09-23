"""Codegen defects from the 2026-09-24 audit.

Keyword and non-identifier names produced code that did not compile; NaN and
infinity became undefined names; ``AC_execute_action`` became a facade call
with arguments the facade does not take; the executor's
``{"auto_control": [...]}`` wrapper was refused; and a Robot test name could
turn into a section header or comment.
"""
import json

import pytest

from je_auto_control.utils.codegen.codegen import generate_code, generate_code_file

ACTIONS = [["AC_type_keyboard", {"keycode": "a"}]]


@pytest.mark.parametrize("target", ["python", "pytest"])
@pytest.mark.parametrize("name", ["import", "class", "²", "½x", "流程", "ok name"])
def test_every_name_yields_code_that_compiles(name, target):
    compile(generate_code(ACTIONS, target=target, name=name), "generated", "exec")


def test_nan_and_infinity_from_json_are_defined_in_the_generated_code():
    actions = json.loads('[["AC_set_mouse_position", {"x": NaN, "y": -Infinity}]]')
    for style in ("calls", "actions"):
        code = generate_code(actions, target="python", style=style)
        namespace = {"__name__": "generated"}
        exec(compile(code, "generated", "exec"), namespace)  # nosec B102  # nosemgrep  # reason: runs only the module header; the flow function is never called
        assert "nan" in namespace and "inf" in namespace


def test_finite_values_need_no_math_import():
    assert "from math" not in generate_code(ACTIONS, target="python")


def test_execute_action_keeps_the_executor_arguments():
    code = generate_code([["AC_execute_action", {"action_list": [], "raise_on_error": True}]],
                         target="python")
    assert "ac.execute_action([['AC_execute_action'" in code


def test_other_commands_still_become_direct_calls():
    assert "ac.type_keyboard(keycode='a')" in generate_code(ACTIONS, target="python")


def test_the_executor_wrapper_is_accepted(tmp_path):
    source = tmp_path / "wrapped.json"
    source.write_text(json.dumps({"auto_control": ACTIONS}), encoding="utf-8")
    code = generate_code_file(str(source), str(tmp_path / "out.py"), target="python")
    assert "ac.type_keyboard(keycode='a')" in code
    assert (tmp_path / "out.py").read_text(encoding="utf-8") == code


@pytest.mark.parametrize("name", ["*** Keywords ***", "# nightly", "| row", "${secret} run", "a\\b"])
def test_a_robot_test_name_stays_a_test_name(name):
    line = generate_code(ACTIONS, target="robot", name=name).splitlines()[4]
    assert line and line[0] not in "*#| "
    assert "${" not in line and "\\" not in line
