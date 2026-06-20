"""Headless tests for JSON Pointer / Patch / Merge Patch. Pure stdlib, no Qt."""
import json

import pytest

import je_auto_control as ac
from je_auto_control.utils.json_patch import (
    PatchError, PatchTestFailed, apply_patch, make_merge_patch, make_patch,
    merge_patch, remove_pointer, resolve_pointer, set_pointer)


def test_pointer_resolution_rfc6901():
    doc = {"foo": ["bar", "baz"], "a/b": 1, "m~n": 2}
    assert resolve_pointer(doc, "/foo/0") == "bar"
    assert resolve_pointer(doc, "") is doc
    assert resolve_pointer(doc, "/a~1b") == 1     # ~1 -> /
    assert resolve_pointer(doc, "/m~0n") == 2     # ~0 -> ~
    assert resolve_pointer(doc, "/nope", "default") == "default"
    with pytest.raises(PatchError):
        resolve_pointer(doc, "/nope")


def test_patch_add_remove_replace():
    assert apply_patch({"foo": "bar"},
                       [{"op": "add", "path": "/baz", "value": "qux"}]) == \
        {"foo": "bar", "baz": "qux"}
    assert apply_patch({"foo": ["a", "b"]},
                       [{"op": "add", "path": "/foo/1", "value": "X"}]) == \
        {"foo": ["a", "X", "b"]}     # array insert (shift)
    assert apply_patch({"a": 1, "b": 2},
                       [{"op": "remove", "path": "/b"}]) == {"a": 1}
    assert apply_patch({"a": 1},
                       [{"op": "replace", "path": "/a", "value": 9}]) == {"a": 9}


def test_patch_move_and_copy():
    assert apply_patch({"a": {"x": 1}, "b": {}},
                       [{"op": "move", "from": "/a/x", "path": "/b/y"}]) == \
        {"a": {}, "b": {"y": 1}}
    assert apply_patch({"a": 5, "b": {}},
                       [{"op": "copy", "from": "/a", "path": "/b/c"}]) == \
        {"a": 5, "b": {"c": 5}}


def test_patch_move_into_own_child_rejected():
    with pytest.raises(PatchError):
        apply_patch({"a": {"b": 1}},
                    [{"op": "move", "from": "/a", "path": "/a/b"}])


def test_patch_test_op():
    out = apply_patch({"a": 1}, [{"op": "test", "path": "/a", "value": 1},
                                 {"op": "replace", "path": "/a", "value": 2}])
    assert out == {"a": 2}
    with pytest.raises(PatchTestFailed):
        apply_patch({"a": 1}, [{"op": "test", "path": "/a", "value": 2}])
    # bool and int stay distinct
    with pytest.raises(PatchTestFailed):
        apply_patch({"a": True}, [{"op": "test", "path": "/a", "value": 1}])


def test_patch_is_atomic():
    original = {"a": 1}
    with pytest.raises(PatchTestFailed):
        apply_patch(original, [{"op": "add", "path": "/b", "value": 2},
                               {"op": "test", "path": "/a", "value": 9}])
    assert original == {"a": 1}     # untouched on failure


def test_unknown_op_raises():
    with pytest.raises(PatchError):
        apply_patch({}, [{"op": "frobnicate", "path": "/a"}])


def test_make_patch_round_trips():
    old = {"name": "Jo", "tags": ["x", "y"], "age": 30, "nested": {"k": 1}}
    new = {"name": "Joe", "tags": ["x", "z", "w"], "nested": {"k": 2},
           "extra": True}
    patch = make_patch(old, new)
    assert apply_patch(old, patch) == new
    assert make_patch(old, old) == []


def test_merge_patch_rfc7386():
    assert merge_patch({"a": 1, "b": 2}, {"b": None, "c": 3}) == {"a": 1, "c": 3}
    assert merge_patch({"a": {"x": 1, "y": 2}}, {"a": {"y": None, "z": 3}}) == \
        {"a": {"x": 1, "z": 3}}
    assert merge_patch({"a": [1, 2]}, {"a": "str"}) == {"a": "str"}


def test_make_merge_patch_round_trips():
    old = {"a": 1, "b": 2, "c": 3}
    new = {"a": 1, "b": 9}
    patch = make_merge_patch(old, new)
    assert patch == {"b": 9, "c": None}
    assert merge_patch(old, patch) == new


def test_set_and_remove_pointer_are_pure():
    doc = {"a": {"b": 1}}
    assert set_pointer(doc, "/a/b", 9) == {"a": {"b": 9}}
    assert doc == {"a": {"b": 1}}      # original unchanged
    assert remove_pointer({"a": 1, "b": 2}, "/b") == {"a": 1}


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_apply_json_patch",
        {"doc": json.dumps({"a": 1}),
         "patch": json.dumps([{"op": "add", "path": "/b", "value": 2}])},
    ]])
    result = next(v for v in rec.values() if isinstance(v, dict))["result"]
    assert result == {"a": 1, "b": 2}

    rec2 = ac.execute_action([[
        "AC_merge_patch",
        {"doc": json.dumps({"a": 1, "b": 2}),
         "patch": json.dumps({"b": None})},
    ]])
    result2 = next(v for v in rec2.values() if isinstance(v, dict))["result"]
    assert result2 == {"a": 1}


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_resolve_pointer", "AC_apply_json_patch", "AC_make_json_patch",
            "AC_merge_patch"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_resolve_pointer", "ac_apply_json_patch", "ac_make_json_patch",
            "ac_merge_patch"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_resolve_pointer", "AC_apply_json_patch", "AC_make_json_patch",
            "AC_merge_patch"} <= cmds


def test_facade_exports():
    for attr in ("resolve_pointer", "apply_patch", "make_patch", "merge_patch",
                 "make_merge_patch", "set_pointer", "remove_pointer",
                 "PatchError", "PatchTestFailed"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
