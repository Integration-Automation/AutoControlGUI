"""Generated code must not run what an action file smuggles into it.

Action files come from recordings, other people and the network. Codegen put
parameter *names* into ``key=value`` source text as written, and embedded the
Robot payload in a ``r'''...'''`` literal that a value could close; either way
the generated test ran code the action file supplied.
"""
import ast
import base64
import json
import re

from je_auto_control.utils.codegen.codegen import generate_code

_EVIL_KEY = "x=1)\nimport os; os.system('echo PWNED')\nprint(end"


def _imported_modules(code):
    return {alias.name for node in ast.walk(ast.parse(code))
            if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names}


def test_a_parameter_name_cannot_inject_statements():
    code = generate_code([["AC_type_keyboard", {_EVIL_KEY: "a"}]], target="pytest")
    compile(code, "<generated>", "exec")
    assert _imported_modules(code) == {"je_auto_control"}, code
    assert "ac.execute_action(" in code, "an unsafe key takes the executor fall-back"


def test_a_keyword_or_spaced_name_takes_the_fallback():
    for key in ("class", "two words"):
        code = generate_code([["AC_type_keyboard", {key: "a"}]], target="pytest")
        compile(code, "<generated>", "exec")
        assert "ac.execute_action(" in code


def test_a_robot_value_cannot_close_the_payload():
    evil = "'''+str(6*7)+'''"
    code = generate_code([["AC_type_keyboard", {"keycode": evil}]], target="robot")
    line = next(ln for ln in code.splitlines() if "json.loads" in ln)
    encoded = re.search(r"b64decode\('([A-Za-z0-9+/=]+)'\)", line).group(1)
    assert json.loads(base64.b64decode(encoded)) == [["AC_type_keyboard", {"keycode": evil}]]
    assert "'''" not in line


def test_a_robot_test_name_stays_on_one_cell():
    code = generate_code([["AC_click_mouse", {}]], target="robot", name="a\n*** Settings ***    x")
    # Robot reads a line starting with *** as a section header.
    assert [ln for ln in code.splitlines() if ln.startswith("***")] == [
        "*** Settings ***", "*** Test Cases ***"]
