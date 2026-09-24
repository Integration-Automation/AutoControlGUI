"""Block commands in the action JSON Schema and the linter.

The schema was built from the dispatch table alone, so the 34 block commands
(AC_sleep, AC_loop, AC_set_var...) were missing and no action file using one
validated; unresolved annotations typed most parameters as ``"string"``. The
linter checked a block command's nested bodies but never its own arguments.
"""
import ast
import inspect
import textwrap

import pytest

from je_auto_control.utils.action_lint.linter import lint_actions
from je_auto_control.utils.action_lint.schema import build_action_schema
from je_auto_control.utils.executor.action_schema import BLOCK_REQUIRED_KEYS
from je_auto_control.utils.executor.flow_control import BLOCK_COMMANDS


def _subscripted_keys(function) -> set:
    """Keys a handler reads as ``args["key"]`` (its second parameter)."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    definition = tree.body[0]
    args_name = definition.args.args[1].arg
    return {node.slice.value for node in ast.walk(tree)
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
            and node.value.id == args_name and isinstance(node.slice, ast.Constant)}


def test_the_required_key_table_matches_the_handlers():
    from je_auto_control.utils.executor import flow_control
    compare_keys = _subscripted_keys(flow_control._compare_var)  # noqa: SLF001
    for name, handler in BLOCK_COMMANDS.items():
        derived = _subscripted_keys(handler)
        if name in ("AC_if_var", "AC_while_var"):
            derived |= compare_keys        # read through _compare_var
        assert set(BLOCK_REQUIRED_KEYS.get(name, ())) == derived, name


@pytest.mark.parametrize("action, missing", [
    (["AC_sleep", {"secs": 1}], "seconds"),
    (["AC_loop", {"body": [["AC_sleep", {"seconds": 0}]]}], "times"),
    (["AC_set_var", {"value": 1}], "name"),
    (["AC_sql_to_var", {"database": "x.db"}], "query"),
])
def test_a_block_command_missing_an_argument_is_reported(action, missing):
    issues = lint_actions([action])
    assert any(issue.code == "missing-param" and repr(missing) in issue.message
               for issue in issues), issues


def test_a_nested_block_command_is_checked_too():
    issues = lint_actions([["AC_loop", {"times": 2, "body": [["AC_sleep", {}]]}]])
    assert any("seconds" in issue.message for issue in issues)
    assert lint_actions([["AC_loop", {"times": 2, "body": [["AC_sleep", {"seconds": 0}]]}]]) == []


def test_the_schema_lists_every_known_command():
    from je_auto_control.utils.executor.action_executor import executor
    schema = build_action_schema()
    listed = {entry["prefixItems"][0]["const"] for entry in schema["items"]["oneOf"]}
    assert listed == executor.known_commands()


def test_the_schema_accepts_valid_actions_and_types_from_annotations():
    from je_auto_control.utils.json_schema.json_schema import validate_json
    schema = build_action_schema(include_only=["AC_sleep", "AC_click_mouse", "AC_set_var"])
    good = [["AC_sleep", {"seconds": 1}],
            ["AC_click_mouse", {"mouse_keycode": "mouse_left", "x": 100, "y": 200}],
            ["AC_set_var", {"name": "n", "value": 3}]]
    assert validate_json(good, schema).ok, validate_json(good, schema).errors
    assert not validate_json([["AC_sleep", {"secs": 1}]], schema).ok
    assert not validate_json([["AC_click_mouse", {"x": "far left"}]], schema).ok
