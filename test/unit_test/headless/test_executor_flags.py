"""Executor adapters and flow commands read flags by spelling, so ``"false"`` means off.

``bool("false")`` is True: ``"ignore_case": "false"`` turned case folding on,
``"paste": "false"`` pasted over the user's clipboard, and ``"reraise":
"false"`` re-raised. The static check keeps a new adapter from calling
``bool()`` on one of its own parameters again.
"""
import ast
import pathlib

import pytest

import je_auto_control
from je_auto_control.utils.executor.flags import as_bool

_EXECUTOR = pathlib.Path(je_auto_control.__file__).parent / "utils" / "executor"
# Truthiness of data, not a flag: AC_eval_check's "truthy" operator.
_TRUTHINESS = {("action_executor.py", "_eval_check")}


@pytest.mark.parametrize("value, expected", [
    ("false", False), ("False", False), (" no ", False), ("off", False), ("0", False), ("", False),
    ("true", True), ("YES", True), ("on", True), ("1", True),
    (True, True), (False, False), (0, False), (1, True), (None, False),
])
def test_as_bool_reads_the_spelling(value, expected):
    assert as_bool(value) is expected


def _bool_of_own_parameter(tree):
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = func.args
        params = {arg.arg for arg in args.args + args.kwonlyargs + args.posonlyargs}
        for node in ast.walk(func):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "bool"
                    and len(node.args) == 1):
                arg = node.args[0]
                if isinstance(arg, ast.Name) and arg.id in params:
                    yield func.name, node.lineno
                elif (isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute)
                      and arg.func.attr == "get" and isinstance(arg.func.value, ast.Name)
                      and arg.func.value.id == "args"):
                    yield func.name, node.lineno


@pytest.mark.parametrize("module", ["action_executor.py", "flow_control.py", "flow_data_commands.py"])
def test_no_adapter_reads_a_flag_with_bool(module):
    tree = ast.parse((_EXECUTOR / module).read_text(encoding="utf-8"))
    found = [(name, line) for name, line in _bool_of_own_parameter(tree) if (module, name) not in _TRUTHINESS]
    assert not found, f"use as_bool() for flags in {module}: {found}"


def test_ignore_case_false_reaches_the_backend_as_false(monkeypatch):
    from je_auto_control.utils.accessibility import backends
    from je_auto_control.utils.accessibility.backends import base
    from je_auto_control.utils.executor.action_executor import Executor
    seen = []

    class _Backend(base.AccessibilityBackend):
        name = "fake"
        available = True

        def list_elements(self, app_name=None, max_results=200, window_title=None):
            return []

        def find_text(self, text="", ignore_case=True, name=None, role=None, app_name=None,
                      automation_id=None):
            seen.append(ignore_case)
            return True

    monkeypatch.setattr(backends, "_cached_backend", _Backend())
    Executor().execute_action([["AC_find_control_text", {"text": "Foo", "ignore_case": "false"}]])
    assert seen == [False]


def test_paste_false_types_instead_of_pasting(monkeypatch):
    from je_auto_control.utils.executor.action_executor import Executor
    from je_auto_control.utils.field_entry import field_entry
    sent = []
    monkeypatch.setattr(field_entry, "_default_sink", sent.append)
    Executor().execute_action([["AC_set_field_text", {"text": "hi", "paste": "false"}]])
    assert "set_clipboard" not in [event["op"] for event in sent]


def test_reraise_false_does_not_reraise():
    from je_auto_control.utils.executor.action_executor import Executor
    executor = Executor()

    def boom():
        raise RuntimeError("boom")

    executor.event_dict["AC_boom"] = boom
    record = executor.execute_action([["AC_try", {"body": [["AC_boom"]], "reraise": "false"}]],
                                     raise_on_error=True)
    assert "boom" in str(record)
