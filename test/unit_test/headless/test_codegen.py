"""Headless tests for AutoControl codegen (action list -> source code).

No PySide6 is imported; generated Python is checked for valid syntax via
``compile`` so the tests stay fast and side-effect free.
"""
import json

import pytest

import je_auto_control as ac
from je_auto_control.utils.codegen.codegen import generate_code, generate_code_file

_ACTIONS = [
    ["AC_click_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
    ["AC_type_keyboard", {"keycode": "a"}],
    ["AC_loop", {"times": 2, "body": [["AC_screen_size"]]}],
]


def _compiles(source: str) -> bool:
    compile(source, "<generated>", "exec")
    return True


def test_calls_style_maps_commands_to_facade_calls():
    code = generate_code(_ACTIONS, target="pytest", style="calls")
    assert "import je_auto_control as ac" in code
    assert "def test_recorded_flow():" in code
    assert "ac.click_mouse(mouse_keycode='mouse_left', x=500, y=500)" in code
    assert "ac.type_keyboard(keycode='a')" in code
    # flow-control falls back to the executor
    assert "ac.execute_action([['AC_loop'," in code
    assert _compiles(code)


def test_actions_style_embeds_and_replays():
    code = generate_code(_ACTIONS, target="python", style="actions")
    assert "actions = [" in code
    assert "ac.execute_action(actions)" in code
    assert 'if __name__ == "__main__":' in code
    assert _compiles(code)


def test_python_target_has_main_guard():
    code = generate_code(_ACTIONS, target="python", name="My Flow")
    assert "def my_flow():" in code
    assert "    my_flow()" in code
    assert _compiles(code)


def test_robot_target_is_self_contained():
    code = generate_code(_ACTIONS, target="robot", name="login_flow")
    assert "*** Test Cases ***" in code
    assert "Login Flow" in code
    assert "Evaluate" in code
    payload_line = [ln for ln in code.splitlines() if "json.loads" in ln][0]
    assert "AC_click_mouse" in payload_line


def test_name_is_slugged_to_valid_identifier():
    code = generate_code(_ACTIONS, target="pytest", name="123 weird-name!")
    assert "def test_flow_123_weird_name():" in code
    assert _compiles(code)


def test_unknown_target_rejected():
    with pytest.raises(ValueError):
        generate_code(_ACTIONS, target="java")


def test_unknown_style_rejected():
    with pytest.raises(ValueError):
        generate_code(_ACTIONS, style="bogus")


def test_empty_actions_rejected():
    with pytest.raises(ValueError):
        generate_code([])


def test_pytest_can_emit_automatic_failure_bundle():
    code = generate_code(_ACTIONS, failure_bundle=True, name="login")
    assert "import je_auto_control.api as ac" in code
    assert "with ac.failure_bundle_on_error(" in code
    assert "login-failure.zip" in code
    assert _compiles(code)


def test_generate_code_file_from_path(tmp_path):
    src = tmp_path / "flow.json"
    src.write_text(json.dumps(_ACTIONS), encoding="utf-8")
    out = tmp_path / "test_flow.py"
    code = generate_code_file(str(src), str(out), target="pytest")
    assert out.read_text(encoding="utf-8") == code
    assert _compiles(code)


def test_facade_reexports_codegen():
    assert ac.generate_code is generate_code
    assert ac.generate_code_file is generate_code_file


def test_executor_command_registered():
    assert "AC_generate_code" in ac.executor.known_commands()
    code = ac.execute_action(
        [["AC_generate_code", {"source": _ACTIONS, "target": "pytest"}]])
    # execute_action returns a record dict; the value is the generated code
    assert any("import je_auto_control" in str(value) for value in code.values())


def test_cli_codegen_to_file(tmp_path):
    from je_auto_control.cli import main
    src = tmp_path / "flow.json"
    src.write_text(json.dumps(_ACTIONS), encoding="utf-8")
    out = tmp_path / "gen.py"
    assert main(["codegen", str(src), "--target", "pytest", "-o", str(out)]) == 0
    assert _compiles(out.read_text(encoding="utf-8"))
